import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from filelock import FileLock

from ._client import IDLE_TIMEOUT, stop_process


def input_css(config):
    def quote(path):
        return json.dumps(Path(path).as_posix(), ensure_ascii=False)

    base = (
        f"@import {quote(config['input'])};"
        if config["input"]
        else '@import "tailwindcss" source(none);'
    )
    sources = "\n".join(f"@source {quote(path)};" for path in config["sources"])
    return f"{base}\n{sources}\n{config['css']}\n"


class Worker:
    def __init__(self, directory):
        self.directory = directory
        self.config = json.loads((directory / "config.json").read_text())
        self.output = directory / "style.css"
        self.stopping = False

    def stop(self, *_):
        self.stopping = True

    def start_compiler(self):
        source = self.directory / "input.css"
        source.write_text(input_css(self.config), encoding="utf-8")
        executable = "tailwindcss.exe" if os.name == "nt" else "tailwindcss"
        binary = Path(__file__).parent / "bin" / executable
        mode = "--watch=always" if self.config["watch"] else "--minify"
        command = [
            str(binary),
            "-i",
            str(source),
            "-o",
            str(self.directory / "building.css"),
            mode,
        ]
        with (self.directory / "compiler.log").open("w") as log:
            return subprocess.Popen(
                command,
                cwd=self.config["root"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                env={**os.environ, "NO_COLOR": "1"},
            )

    def publish_css(self):
        css = (self.directory / "building.css").read_bytes()
        if self.output.exists() and self.output.read_bytes() == css:
            return
        temporary = self.directory / "published.tmp"
        temporary.write_bytes(css)
        temporary.replace(self.output)

    def idle(self):
        heartbeat = (self.directory / "heartbeat").stat().st_mtime
        return time.time() - heartbeat > IDLE_TIMEOUT

    def expired(self):
        if not self.idle():
            return False
        with FileLock(str(self.directory / "startup.lock"), timeout=30):
            if not self.idle():
                return False
            (self.directory / "pid").unlink(missing_ok=True)
            return True

    def check_exit(self, code):
        if code is None:
            return
        if code == 0 and not self.config["watch"] and self.output.exists():
            return
        details = (self.directory / "compiler.log").read_text(
            encoding="utf-8", errors="replace"
        )
        raise RuntimeError(f"Tailwind stopped (exit {code}):\n{details}")

    def monitor(self, process):
        with (self.directory / "compiler.log").open(
            encoding="utf-8", errors="replace"
        ) as log:
            pending = ""
            while not self.stopping:
                code = process.poll()
                pending += log.read()
                message, _, pending = pending.rpartition("\n")
                if re.search(r"\bDone in\b", message):
                    self.publish_css()
                self.check_exit(code)
                if self.expired():
                    return
                time.sleep(0.1)

    def run(self):
        process = None
        (self.directory / "pid").write_text(str(os.getpid()))
        try:
            process = self.start_compiler()
            self.monitor(process)
        except (OSError, RuntimeError) as error:
            (self.directory / "error").write_text(str(error), encoding="utf-8")
        finally:
            if process is not None:
                stop_process(process)
            (self.directory / "pid").unlink(missing_ok=True)


def main(directory):
    worker = Worker(directory)
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        if signum := getattr(signal, name, None):
            signal.signal(signum, worker.stop)
    with FileLock(str(directory / "worker.lock"), timeout=0):
        worker.run()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
