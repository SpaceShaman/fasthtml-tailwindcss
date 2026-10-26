import hashlib
import json
import os
import platform
import shutil
import tempfile
from pathlib import Path
from urllib.request import urlopen

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

TARGETS = {
    "linux-x64": "manylinux_2_28_x86_64",
    "linux-arm64": "manylinux_2_28_aarch64",
    "linux-x64-musl": "musllinux_1_2_x86_64",
    "linux-arm64-musl": "musllinux_1_2_aarch64",
    "macos-x64": "macosx_13_0_x86_64",
    "macos-arm64": "macosx_13_0_arm64",
    "windows-x64": "win_amd64",
}


def native_target():
    system = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(
        platform.system()
    )
    arch = {"x86_64": "x64", "AMD64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine()
    )
    target = f"{system}-{arch}"
    if system == "linux" and (
        platform.libc_ver()[0] == "musl" or any(Path("/lib").glob("ld-musl-*.so.1"))
    ):
        target += "-musl"
    return target


def download_binary(url, binary, expected):
    if binary.exists() and hashlib.sha256(binary.read_bytes()).hexdigest() == expected:
        return
    with tempfile.TemporaryDirectory() as temporary:
        download = Path(temporary) / binary.name
        with urlopen(url, timeout=120) as response, download.open("wb") as destination:
            shutil.copyfileobj(response, destination)
        if hashlib.sha256(download.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Checksum mismatch for {url}")
        shutil.copyfile(download, binary)


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if self.target_name != "wheel":
            return
        root = Path(self.root)
        manifest = json.loads((root / "binaries.json").read_text())
        if self.metadata.version.split(".post")[0] != manifest["version"]:
            raise ValueError("Package version must match binaries.json")
        target = os.environ.get("TAILWIND_BUILD_TARGET", native_target())
        if target not in TARGETS:
            raise RuntimeError(f"No official standalone Tailwind binary for {target}")
        suffix = ".exe" if target.startswith("windows-") else ""
        asset = f"tailwindcss-{target}{suffix}"
        expected = manifest["sha256"][asset]
        binary = root / "src" / "fasthtml_tailwindcss" / "bin" / f"tailwindcss{suffix}"
        binary.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/tailwindlabs/tailwindcss/releases/download/v{manifest['version']}/{asset}"
        download_binary(url, binary, expected)
        binary.chmod(0o755)
        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{TARGETS[target]}"
        build_data["artifacts"].append(
            f"src/fasthtml_tailwindcss/bin/tailwindcss{suffix}"
        )
