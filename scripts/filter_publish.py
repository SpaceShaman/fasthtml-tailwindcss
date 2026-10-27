import json
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


def published_files(project, release):
    try:
        with urlopen(
            f"https://pypi.org/pypi/{project}/{release}/json", timeout=30
        ) as response:
            return {item["filename"] for item in json.load(response)["urls"]}
    except HTTPError as error:
        if error.code == 404:
            return set()
        raise


for path in (Path("pyproject.toml"), Path("packages/cli/pyproject.toml")):
    project = tomllib.loads(path.read_text())["project"]
    published = published_files(project["name"], project["version"])
    for artifact in Path("dist").iterdir():
        if artifact.name in published:
            artifact.unlink()
