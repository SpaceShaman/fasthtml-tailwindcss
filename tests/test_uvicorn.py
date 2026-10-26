import time

import pytest

from fasthtml_tailwindcss import _client


@pytest.mark.skipif(
    __import__("os").name == "nt",
    reason="POSIX process-group shutdown for this reload test",
)
@pytest.mark.parametrize("watch", [False, True])
def test_real_uvicorn_reload(project, helpers, watch):
    import os
    import signal
    import socket
    import subprocess
    import sys
    from urllib.error import URLError
    from urllib.request import urlopen

    source = project / "main.py"
    source.write_text(f"""import os
from pathlib import Path
from fasthtml.common import FastHTML, Div
from fasthtml_tailwindcss import TailwindHead, _client
_client.user_cache_path = lambda *a, **kw: Path({str(project / "cache")!r})
app = FastHTML(sess_cls=None, hdrs=[TailwindHead(watch={watch!r}, sources=["main.py"])])
@app.get("/")
def get():
    return Div("first", cls="p-4")
@app.get("/pid")
def pid():
    return str(os.getpid())
""")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def response(path="/"):
        try:
            with urlopen(base + path, timeout=1) as res:
                return res.read().decode()
        except (OSError, URLError):
            return ""

    config = _client.configuration(
        watch=watch, sources=["main.py"], input=None, css=None
    )
    directory = _client.cache_directory(config)
    with (project / "uvicorn.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--reload",
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
            helper_pid = (directory / "pid").read_text()
            output = directory / "style.css"
            timestamp = output.stat().st_mtime_ns
            source.write_text(
                source.read_text().replace(
                    '"first", cls="p-4"', '"second", cls="text-7xl"'
                )
            )
            deadline = time.monotonic() + 20
            while ">second</div>" not in response():
                assert time.monotonic() < deadline, (
                    project / "uvicorn.log"
                ).read_text()
                time.sleep(0.1)
            assert response("/pid") != pid
            assert (directory / "pid").read_text() == helper_pid
            if watch:
                while ".text-7xl" not in response():
                    assert time.monotonic() < deadline
                    time.sleep(0.1)
            else:
                assert output.stat().st_mtime_ns == timestamp
                assert ".text-7xl" not in response()
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=15)
