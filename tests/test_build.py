import shutil
import subprocess

import pytest


@pytest.mark.parametrize("reference", ["main:app", "app.main:app"])
def test_build_uses_application_directory(project, reference):
    directory = project / "app"
    directory.mkdir()
    (directory / "components.py").write_text('classes = "p-4"\n')
    (directory / "main.py").write_text(
        "from fasthtml.common import FastHTML, StaticImmutable\n"
        "from fasthtml_tailwindcss import TailwindHead\n"
        "from components import classes\n"
        'app = FastHTML(hdrs=[TailwindHead(watch=True, sources=["components.py"])])\n'
        'app.mount("/static", StaticImmutable(directory="static"), name="static")\n'
    )
    command = shutil.which("fasthtml-tailwindcss")
    assert command is not None
    result = subprocess.run(
        [command, "build", reference],
        cwd=directory if reference == "main:app" else project,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert ".p-4{" in (directory / "static" / "tailwind.css").read_text()
    assert not (project / "static" / "tailwind.css").exists()
    assert not (directory / ".fasthtml-tailwindcss" / "pid").exists()
