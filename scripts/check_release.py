import json
import os
import re
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


def project_version(path):
    return tomllib.loads(Path(path).read_text())["project"]["version"]


def set_project_version(path, version):
    path = Path(path)
    text = path.read_text()
    path.write_text(
        re.sub(r'(?m)^version = "[^"]+"$', f'version = "{version}"', text, count=1)
    )


def pypi_files(name, version):
    try:
        with urlopen(
            f"https://pypi.org/pypi/{name}/{version}/json", timeout=30
        ) as response:
            return {item["filename"] for item in json.load(response)["urls"]}
    except HTTPError as error:
        if error.code != 404:
            raise
        return set()


manifest_path = Path("packages/cli/binaries.json")
cli_project = Path("packages/cli/pyproject.toml")
cli_license = Path("packages/cli/TAILWIND-LICENSE")
wrapper_project = Path("pyproject.toml")
wrapper_version = project_version(wrapper_project)
cli_version = project_version(cli_project)
manifest = json.loads(manifest_path.read_text())
if cli_version.split(".post")[0] != manifest["version"]:
    raise ValueError("CLI package version must match binaries.json")
release = github_json(
    "https://api.github.com/repos/tailwindlabs/tailwindcss/releases/latest"
)
latest = release["tag_name"].removeprefix("v")
if not re.fullmatch(r"\d+\.\d+\.\d+", latest):
    raise ValueError(f"Expected a stable Tailwind release, got {latest!r}")

if tuple(map(int, latest.split("."))) > tuple(
    map(int, cli_version.split(".post")[0].split("."))
):
    hashes = {}
    for asset in release["assets"]:
        if asset["name"] in manifest["sha256"]:
            digest = asset.get("digest", "")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise RuntimeError(f"Missing SHA256 digest for {asset['name']}")
            hashes[asset["name"]] = digest.removeprefix("sha256:")
    if hashes.keys() != manifest["sha256"].keys():
        raise RuntimeError("Upstream release is missing a supported platform")
    manifest_path.write_text(
        json.dumps({"version": latest, "sha256": hashes}, indent=2) + "\n"
    )
    with urlopen(
        f"https://raw.githubusercontent.com/tailwindlabs/tailwindcss/v{latest}/LICENSE",
        timeout=30,
    ) as response:
        cli_license.write_bytes(response.read())
    set_project_version(cli_project, latest)
    set_project_version(wrapper_project, latest)
    wrapper_version = cli_version = latest

wrapper_expected = {
    f"fasthtml_tailwindcss-{wrapper_version}-py3-none-any.whl",
    f"fasthtml_tailwindcss-{wrapper_version}.tar.gz",
}
tags = [
    "manylinux_2_28_x86_64",
    "manylinux_2_28_aarch64",
    "musllinux_1_2_x86_64",
    "musllinux_1_2_aarch64",
    "macosx_13_0_x86_64",
    "macosx_13_0_arm64",
    "win_amd64",
]
cli_expected = {
    f"fasthtml_tailwindcss_cli-{cli_version}-py3-none-{tag}.whl" for tag in tags
}
cli_expected.add(f"fasthtml_tailwindcss_cli-{cli_version}.tar.gz")
wrapper_missing = wrapper_expected - pypi_files(
    "fasthtml-tailwindcss", wrapper_version
)
cli_missing = cli_expected - pypi_files("fasthtml-tailwindcss-cli", cli_version)

with open(os.environ["GITHUB_OUTPUT"], "a") as output:
    output.write(f"version={wrapper_version}\n")
    output.write(f"release={str(bool(wrapper_missing or cli_missing)).lower()}\n")
