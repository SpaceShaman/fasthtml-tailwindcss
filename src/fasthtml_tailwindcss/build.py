import argparse
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from .compiler import binary_path, input_css
from .config import STATE_DIRECTORY, TailwindConfig


def app_head(specification: str):
    module_name, separator, object_name = specification.partition(":")
    if not separator or not module_name or not object_name:
        raise ValueError("Use an application reference such as app.main:app")
    sys.path.insert(0, str(Path.cwd()))
    module_spec = importlib.util.find_spec(module_name)
    if module_spec is None or module_spec.origin is None:
        raise ModuleNotFoundError(f"Cannot locate application module {module_name!r}")
    os.chdir(Path(module_spec.origin).resolve().parent)
    sys.path.insert(0, str(Path.cwd()))
    value = importlib.import_module(module_name)
    for part in object_name.split("."):
        value = getattr(value, part)
    from . import TailwindHead

    heads = [
        item for item in getattr(value, "hdrs", ()) if isinstance(item, TailwindHead)
    ]
    if len(heads) != 1:
        raise ValueError("The application must have exactly one TailwindHead in hdrs")
    return heads[0]


def build(config: TailwindConfig) -> None:
    root = Path(config.root)
    directory = root / STATE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "build-input.css"
    source.write_text(input_css(config), encoding="utf-8")
    output = root / config.output
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(binary_path()), "-i", str(source), "-o", str(output), "--minify"],
        cwd=root,
        env={**os.environ, "NO_COLOR": "1"},
        check=True,
    )
    print(f"Built {output}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="fasthtml-tailwindcss")
    commands = parser.add_subparsers(dest="command", required=True)
    build_command = commands.add_parser("build")
    build_command.add_argument(
        "app", help="Python app reference, for example app.main:app"
    )
    build(app_head(parser.parse_args().app)._config)


if __name__ == "__main__":
    main()
