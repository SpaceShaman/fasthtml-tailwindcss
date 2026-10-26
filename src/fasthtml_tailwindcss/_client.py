import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from contextlib import asynccontextmanager, suppress
from importlib.metadata import version
from pathlib import Path

from filelock import FileLock, Timeout
from platformdirs import user_cache_path

IDLE_TIMEOUT = 15


def configuration(*, watch, sources, input, css):
    if isinstance(sources, (str, Path)):
        raise TypeError("sources must be a sequence of paths, for example ['app']")
    cwd = Path.cwd().resolve()
    root = next(
        (p for p in (cwd, *cwd.parents) if (p / "pyproject.toml").is_file()), cwd
    )
    input_path = (root / input).resolve() if input is not None else None
    if input_path is not None and not input_path.is_file():
        raise FileNotFoundError(input_path)
    if sources is None:
        sources = [root] if input is None else []
    return {
        "root": str(root),
        "watch": watch,
        "sources": [str((root / path).resolve()) for path in sources],
        "input": str(input_path) if input_path is not None else None,
        "css": css or "",
        "version": version("fasthtml-tailwindcss"),
    }


def cache_directory(config):
    key = hashlib.sha256(config["root"].encode()).hexdigest()[:24]
    return user_cache_path("fasthtml-tailwindcss", appauthor=False) / key


def running(directory):
    try:
        with FileLock(str(directory / "worker.lock"), timeout=0):
            return False
    except Timeout:
        return True


def stop_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class Session:
    def __init__(self, config):
        self.config = config
        self.directory = cache_directory(config)
        self.output = self.directory / "style.css"
        self.error = ""

    def connect(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with FileLock(str(self.directory / "startup.lock"), timeout=30):
            self.wait_for_previous_worker()
            if running(self.directory):
                self.check_configuration()
            else:
                self.start_worker()
            (self.directory / "heartbeat").touch()

    def wait_for_previous_worker(self):
        deadline = time.monotonic() + 10
        while running(self.directory) and not (self.directory / "pid").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("Tailwind helper is not responding")
            time.sleep(0.05)

    def check_configuration(self):
        config = json.loads((self.directory / "config.json").read_text())
        if config != self.config:
            raise RuntimeError(
                "Tailwind settings differ from the active session. Stop all servers for this project and wait 15 seconds before restarting."
            )

    def start_worker(self):
        for name in ("style.css", "error", "pid"):
            (self.directory / name).unlink(missing_ok=True)
        (self.directory / "config.json").write_text(
            json.dumps(self.config), encoding="utf-8"
        )
        (self.directory / "heartbeat").touch()
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        with (self.directory / "helper.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "fasthtml_tailwindcss._worker",
                    str(self.directory),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=os.name != "nt",
                creationflags=flags,
            )
        deadline = time.monotonic() + 10
        while not (self.directory / "pid").exists():
            if process.poll() is not None or time.monotonic() > deadline:
                stop_process(process)
                raise RuntimeError(
                    (self.directory / "helper.log").read_text()
                    or "Cannot start Tailwind helper"
                )
            time.sleep(0.05)

    async def wait_for_css(self):
        deadline = time.monotonic() + 120
        while not self.output.exists():
            if self.error:
                raise RuntimeError(self.error)
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Tailwind initial build timed out; see compiler.log in the cache"
                )
            await asyncio.sleep(0.05)

    async def heartbeat(self):
        while True:
            error = self.directory / "error"
            if error.exists():
                self.error = error.read_text(encoding="utf-8")
            elif not running(self.directory):
                self.error = "Tailwind helper stopped; restart the application"
            if self.error:
                return
            (self.directory / "heartbeat").touch()
            await asyncio.sleep(2)

    @asynccontextmanager
    async def lifespan(self):
        await asyncio.to_thread(self.connect)
        heartbeat = asyncio.create_task(self.heartbeat())
        try:
            await self.wait_for_css()
            yield self
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
