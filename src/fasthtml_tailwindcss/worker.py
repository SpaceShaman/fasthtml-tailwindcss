import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from filelock import FileLock, Timeout

from .compiler import binary_path, input_css, stop_process
from .config import TailwindConfig, state_directory

IDLE_TIMEOUT = 15


class Worker:
    def __init__(self, config_text: str):
        self.config_text = config_text
        values = json.loads(config_text)
        values["sources"] = tuple(values["sources"])
        self.config = TailwindConfig(**values)
        self.directory = state_directory(self.config)
        self.output = Path(self.config.root) / self.config.output
        self.stopping = False

    def stop(self, *_args) -> None:
        self.stopping = True

    def start_compiler(self) -> subprocess.Popen:
        source = self.directory / "input.css"
        source.write_text(input_css(self.config), encoding="utf-8")
        command = [
            str(binary_path()),
            "-i",
            str(source),
            "-o",
            str(self.directory / "building.css"),
            "--watch=always",
        ]
        with (self.directory / "compiler.log").open("w") as log:
            return subprocess.Popen(
                command,
                cwd=self.config.root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env={**os.environ, "NO_COLOR": "1"},
            )

    def publish_css(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        css = (self.directory / "building.css").read_bytes()
        if not self.output.exists() or self.output.read_bytes() != css:
            temporary = self.output.with_name(self.output.name + ".tmp")
            temporary.write_bytes(css)
            temporary.replace(self.output)
        (self.directory / "ready").write_text(self.config_text, encoding="utf-8")

    def idle(self) -> bool:
        return time.time() - (self.directory / "heartbeat").stat().st_mtime > IDLE_TIMEOUT

    def expired(self) -> bool:
        if not self.idle():
            return False
        try:
            with FileLock(str(self.directory / "startup.lock"), timeout=0):
                if not self.idle():
                    return False
                (self.directory / "pid").unlink(missing_ok=True)
                return True
        except Timeout:
            return False

    def monitor(self, process: subprocess.Popen) -> None:
        with (self.directory / "compiler.log").open(
            encoding="utf-8", errors="replace"
        ) as log:
            pending = ""
            while not self.stopping:
                if (self.directory / "stop").exists() or self.expired():
                    return
                code = process.poll()
                pending += log.read()
                message, _, pending = pending.rpartition("\n")
                if re.search(r"\bDone in\b", message):
                    self.publish_css()
                if code is not None:
                    details = (self.directory / "compiler.log").read_text(
                        encoding="utf-8", errors="replace"
                    )
                    raise RuntimeError(f"Tailwind stopped (exit {code}):\n{details}")
                time.sleep(0.1)

    def run(self) -> None:
        process = None
        (self.directory / "active.json").write_text(self.config_text, encoding="utf-8")
        (self.directory / "pid").write_text(str(os.getpid()), encoding="utf-8")
        try:
            process = self.start_compiler()
            self.monitor(process)
        except (OSError, RuntimeError) as error:
            (self.directory / "error").write_text(str(error), encoding="utf-8")
        finally:
            if process is not None:
                stop_process(process)
            (self.directory / "pid").unlink(missing_ok=True)
            (self.directory / "active.json").unlink(missing_ok=True)


def main(config_text: str) -> None:
    worker = Worker(config_text)
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        if signum := getattr(signal, name, None):
            signal.signal(signum, worker.stop)
    with FileLock(str(worker.directory / "worker.lock"), timeout=0):
        worker.run()


if __name__ == "__main__":
    main(sys.argv[1])
