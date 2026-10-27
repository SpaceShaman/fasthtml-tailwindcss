import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

STATE_DIRECTORY = ".fasthtml-tailwindcss"


@dataclass(frozen=True)
class TailwindConfig:
    root: str
    sources: tuple[str, ...]
    input: str | None
    css: str
    output: str
    version: str


def config_json(config: TailwindConfig) -> str:
    return json.dumps(asdict(config), sort_keys=True)


def configuration(
    *,
    sources: Sequence[str | Path] | None,
    input: str | Path | None,
    css: str | None,
    output: str | Path = "./static/tailwind.css",
) -> TailwindConfig:
    if isinstance(sources, (str, Path)):
        raise TypeError("sources must be a sequence of paths, for example ['app']")
    root = Path.cwd().resolve()
    input_path = (root / input).resolve() if input is not None else None
    if input_path is not None and not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_path = Path(output)
    if output_path.is_absolute():
        output_path = output_path.resolve().relative_to(root)
    output_path = Path(os.path.normpath(output_path))
    if output_path.is_absolute() or ".." in output_path.parts:
        raise ValueError("output must be inside the working directory")
    if sources is None:
        sources = [root] if input is None else []
    return TailwindConfig(
        root=str(root),
        sources=tuple(str((root / path).resolve()) for path in sources),
        input=str(input_path) if input_path is not None else None,
        css=css or "",
        output=output_path.as_posix(),
        version=version("fasthtml-tailwindcss"),
    )


def state_directory(config: TailwindConfig) -> Path:
    return Path(config.root) / STATE_DIRECTORY
