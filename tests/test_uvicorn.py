import os
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from fasthtml_tailwindcss import config


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX process-group shutdown for this reload test",
)
@pytest.mark.parametrize("watch", [False, True])
def test_real_uvicorn_reload(project, watch):
    source = project / "main.py"
    source.write_text(f"""import os
from fasthtml.common import FastHTML, Div, StaticImmutable
from fasthtml_tailwindcss import TailwindHead
app = FastHTML(sess_cls=None, hdrs=[TailwindHead(watch={watch!r}, sources=["main.py"])])
app.mount("/static", StaticImmutable(directory="static"), name="static")
@app.route("/")
def get():
    return Div("first", cls="p-4")
@app.route("/pid")
def pid():
    return str(os.getpid())
""")
    (project / "static" / "tailwind.css").write_text(".p-4{padding:1rem}")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def response(path="/"):
        try:
            with urlopen(base + path, timeout=1) as res:
                return res.read().decode()
        except OSError:
            return ""

    directory = project / config.STATE_DIRECTORY
    with (project / "uvicorn.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--reload",
                "--no-access-log",
                "--port",
                str(port),
            ],
            cwd=project,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 20
            while ">first</div>" not in response():
                assert process.poll() is None, (project / "uvicorn.log").read_text()
                assert time.monotonic() < deadline, (
                    project / "uvicorn.log"
                ).read_text()
                time.sleep(0.1)
            pid = response("/pid")
            helper_pid = (directory / "pid").read_text() if watch else None
            output = project / "static" / "tailwind.css"
            timestamp = output.stat().st_mtime_ns
            source.write_text(
                source.read_text().replace(
                    '"first", cls="p-4"', '"second", cls="text-7xl"'
                )
            )
            deadline = time.monotonic() + 20
            while "Reloading..." not in (project / "uvicorn.log").read_text():
                assert process.poll() is None, (project / "uvicorn.log").read_text()
                assert time.monotonic() < deadline, (
                    project / "uvicorn.log"
                ).read_text()
                source.touch()
                time.sleep(0.3)
            while ">second</div>" not in response():
                assert time.monotonic() < deadline, (
                    project / "uvicorn.log"
                ).read_text()
                time.sleep(0.1)
            assert response("/pid") != pid
            if watch:
                while ".text-7xl" not in output.read_text():
                    assert time.monotonic() < deadline
                    time.sleep(0.1)
                assert (directory / "pid").read_text() == helper_pid
            else:
                assert output.stat().st_mtime_ns == timestamp
                assert ".text-7xl" not in output.read_text()
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=15)
