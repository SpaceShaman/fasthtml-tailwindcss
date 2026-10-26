import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def github_json(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "fasthtml-tailwindcss",
    }
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return json.load(response)


current = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
release = github_json(
    "https://api.github.com/repos/tailwindlabs/tailwindcss/releases/latest"
)
latest = release["tag_name"].removeprefix("v")
if not re.fullmatch(r"\d+\.\d+\.\d+", latest):
    raise ValueError(f"Expected a stable Tailwind release, got {latest!r}")
if tuple(map(int, latest.split("."))) > tuple(
    map(int, current.split(".post")[0].split("."))
):
    expected = json.loads(Path("binaries.json").read_text())["sha256"]
    hashes = {}
    for asset in release["assets"]:
        if asset["name"] in expected:
            digest = asset.get("digest", "")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise RuntimeError(f"Missing SHA256 digest for {asset['name']}")
            hashes[asset["name"]] = digest.removeprefix("sha256:")
    if hashes.keys() != expected.keys():
        raise RuntimeError("Upstream release is missing a supported platform")
    Path("binaries.json").write_text(
        json.dumps({"version": latest, "sha256": hashes}, indent=2) + "\n"
    )
    with urlopen(
        f"https://raw.githubusercontent.com/tailwindlabs/tailwindcss/v{latest}/LICENSE",
        timeout=30,
    ) as response:
        Path("TAILWIND-LICENSE").write_bytes(response.read())
    subprocess.run(["uv", "version", latest, "--frozen", "--no-sync"], check=True)
    current = latest


try:
    with urlopen(
        f"https://pypi.org/pypi/fasthtml-tailwindcss/{current}/json", timeout=30
    ) as response:
        filenames = {item["filename"] for item in json.load(response)["urls"]}
except HTTPError as error:
    if error.code != 404:
        raise
    filenames = set()

tags = [
    "manylinux_2_28_x86_64",
    "manylinux_2_28_aarch64",
    "musllinux_1_2_x86_64",
    "musllinux_1_2_aarch64",
    "macosx_13_0_x86_64",
    "macosx_13_0_arm64",
    "win_amd64",
]
expected_files = {f"fasthtml_tailwindcss-{current}-py3-none-{tag}.whl" for tag in tags}
expected_files.add(f"fasthtml_tailwindcss-{current}.tar.gz")
with open(os.environ["GITHUB_OUTPUT"], "a") as output:
    output.write(
        f"version={current}\nrelease={str(not expected_files <= filenames).lower()}\n"
    )
