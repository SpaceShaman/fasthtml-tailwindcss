import json
import subprocess
from importlib import import_module
from pathlib import Path

from .config import TailwindConfig


def binary_path():
    try:
        package = import_module("fasthtml_tailwindcss_cli")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            'Install fasthtml-tailwindcss with the "dev" extra to use Tailwind'
        ) from error
    return package.binary_path()


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def input_css(config: TailwindConfig) -> str:
    def quote(path):
        return json.dumps(Path(path).as_posix(), ensure_ascii=False)

    base = (
        f"@import {quote(config.input)};"
        if config.input
        else '@import "tailwindcss" source(none);'
    )
    sources = "\n".join(f"@source {quote(path)};" for path in config.sources)
    return f"{base}\n{sources}\n{config.css}\n"
