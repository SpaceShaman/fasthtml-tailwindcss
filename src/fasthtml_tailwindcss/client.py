import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, Lock, Thread

from filelock import FileLock, Timeout

from .compiler import stop_process
from .config import (
    TailwindConfig,
    config_json,
    prepare_state_directory,
    state_directory,
)


def running(directory: Path) -> bool:
    try:
        with FileLock(str(directory / "worker.lock"), timeout=0):
            return False
    except Timeout:
        return True


class Session:
    def __init__(self, config: TailwindConfig):
        self.config_text = config_json(config)
        self.directory = state_directory(config)
        self.output = Path(config.root) / config.output
        self.error = ""
        self._closed = Event()
        self._start_lock = Lock()
        self._thread = Thread(target=self.heartbeat, daemon=True)
        self._started = False

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self.connect()
            self._thread.start()
            try:
                self.wait_for_css()
                self._started = True
            except BaseException:
                self.close()
                raise

    def connect(self) -> None:
        prepare_state_directory(self.directory)
        with FileLock(str(self.directory / "startup.lock"), timeout=30):
            (self.directory / "heartbeat").touch()
            self.wait_for_worker()
            if not running(self.directory):
                self.start_worker()

    def wait_for_worker(self) -> None:
        deadline = time.monotonic() + 10
        while running(self.directory):
            active = self.directory / "active.json"
            if active.is_file() and (self.directory / "pid").exists():
                if active.read_text(encoding="utf-8") == self.config_text:
                    return
                (self.directory / "stop").touch()
            if time.monotonic() > deadline:
                raise RuntimeError("Tailwind helper did not stop after settings changed")
            time.sleep(0.05)

    def start_worker(self) -> None:
        for name in ("error", "pid", "active.json", "ready", "stop"):
            (self.directory / name).unlink(missing_ok=True)
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        with (self.directory / "helper.log").open("w") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "fasthtml_tailwindcss.worker",
                    self.config_text,
                ],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=os.name != "nt",
                creationflags=flags,
            )
        deadline = time.monotonic() + 10
        pid = self.directory / "pid"
        while not pid.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                stop_process(process)
                raise RuntimeError(
                    (self.directory / "helper.log").read_text()
                    or "Cannot start Tailwind helper"
                )
            time.sleep(0.05)

    def wait_for_css(self) -> None:
        deadline = time.monotonic() + 120
        ready = self.directory / "ready"
        while (
            not ready.is_file()
            or ready.read_text(encoding="utf-8") != self.config_text
        ):
            error = self.directory / "error"
            if error.is_file():
                raise RuntimeError(error.read_text(encoding="utf-8"))
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Tailwind initial build timed out; see compiler.log in .fasthtml-tailwindcss"
                )
            time.sleep(0.05)

    def heartbeat(self) -> None:
        while not self._closed.is_set():
            error = self.directory / "error"
            if error.is_file():
                self.error = error.read_text(encoding="utf-8")
            elif not running(self.directory):
                self.error = "Tailwind helper stopped; restart the application"
            if self.error:
                return
            (self.directory / "heartbeat").touch()
            self._closed.wait(2)

    def close(self) -> None:
        self._closed.set()
        if self._thread.ident is not None:
            self._thread.join()
