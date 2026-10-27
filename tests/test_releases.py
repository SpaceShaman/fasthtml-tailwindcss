import io
import json
import runpy
import shutil
import tomllib
from pathlib import Path
from urllib.error import HTTPError

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]


@pytest.fixture
def release_project(tmp_path, monkeypatch):
    for filename in (
        "pyproject.toml",
        "packages/cli/pyproject.toml",
        "packages/cli/binaries.json",
    ):
        destination = tmp_path / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY / filename, destination)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("upstream_changed", [False, True])
def test_release_check_preserves_post_version_or_updates_both_packages(
    release_project, monkeypatch, upstream_changed
):
    wrapper = Path("pyproject.toml")
    manifest = json.loads(Path("packages/cli/binaries.json").read_text())
    post_version = f"{manifest['version']}.post1"
    current = tomllib.loads(wrapper.read_text())["project"]["version"]
    wrapper.write_text(
        wrapper.read_text().replace(
            f'version = "{current}"', f'version = "{post_version}"', 1
        )
    )
    latest = "999.0.0" if upstream_changed else manifest["version"]
    output = release_project / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def response(request, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else request
        if "pypi.org" in url:
            raise HTTPError(url, 404, "Not found", None, None)
        if url.endswith("/LICENSE"):
            return io.BytesIO(b"MIT license")
        return io.BytesIO(
            json.dumps(
                {
                    "tag_name": f"v{latest}",
                    "assets": [
                        {"name": name, "digest": "sha256:" + "a" * 64}
                        for name in manifest["sha256"]
                    ],
                }
            ).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", response)
    runpy.run_path(str(REPOSITORY / "scripts/check_release.py"))
    expected = latest if upstream_changed else post_version
    assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == {
        "version": expected,
        "release": "true",
    }
    assert tomllib.loads(wrapper.read_text())["project"]["version"] == expected
    assert (
        tomllib.loads(Path("packages/cli/pyproject.toml").read_text())["project"][
            "version"
        ]
        == latest
    )


def test_publish_retry_keeps_only_missing_files(release_project, monkeypatch):
    published = {"wrapper.tar.gz", "cli.whl"}
    missing = "wrapper.whl"
    Path("dist").mkdir()
    for filename in (*published, missing):
        (Path("dist") / filename).touch()
    requests = []

    def response(url, **kwargs):
        requests.append(url)
        return io.BytesIO(
            json.dumps({"urls": [{"filename": name} for name in published]}).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", response)
    runpy.run_path(str(REPOSITORY / "scripts/filter_publish.py"))
    assert [path.name for path in Path("dist").iterdir()] == [missing]
    assert len(requests) == 2
