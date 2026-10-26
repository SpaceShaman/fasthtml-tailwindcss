import hashlib
import json
import os
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path
from threading import Event, Thread

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
    settings = json.dumps(config, sort_keys=True).encode()
    key = hashlib.sha256(settings).hexdigest()[:24]
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
        self._closed = Event()
        self._thread = Thread(target=self.heartbeat, daemon=True)

    def connect(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with FileLock(str(self.directory / "startup.lock"), timeout=30):
            self.wait_for_previous_worker()
            if not running(self.directory):
                self.start_worker()
            (self.directory / "heartbeat").touch()

    def wait_for_previous_worker(self):
        deadline = time.monotonic() + 10
        while running(self.directory) and not (self.directory / "pid").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("Tailwind helper is not responding")
            time.sleep(0.05)

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

    def wait_for_css(self):
        deadline = time.monotonic() + 120
        while not self.output.exists():
            if self.error:
                raise RuntimeError(self.error)
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Tailwind initial build timed out; see compiler.log in the cache"
                )
            time.sleep(0.05)

    def heartbeat(self):
        while not self._closed.is_set():
            error = self.directory / "error"
            if error.exists():
                self.error = error.read_text(encoding="utf-8")
            elif not running(self.directory):
                self.error = "Tailwind helper stopped; restart the application"
            if self.error:
                return
            (self.directory / "heartbeat").touch()
            self._closed.wait(2)

    def start(self):
        self.connect()
        self._thread.start()
        try:
            self.wait_for_css()
        except BaseException:
            self.close()
            raise

    def close(self):
        self._closed.set()
        self._thread.join()
