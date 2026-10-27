import gc
import time

import pytest
from fasthtml.common import Div, FastHTML, StaticImmutable

from fasthtml_tailwindcss import TailwindHead, config


@pytest.fixture(scope="session")
def helpers():
    directories = []
    yield directories
    deadline = time.monotonic() + 25
    while any((p / "pid").exists() for p in directories):
        assert time.monotonic() < deadline, (
            "Helper did not shut down after losing clients"
        )
        time.sleep(0.1)


@pytest.fixture
def project(tmp_path, monkeypatch, helpers):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="example"\nversion="0.1.0"\n'
    )
    (tmp_path / "components.py").write_text('classes = "p-4 bg-blue-500"\n')
    helpers.append(tmp_path / config.STATE_DIRECTORY)
    (tmp_path / "static").mkdir()
    yield tmp_path
    gc.collect()


@pytest.fixture
def application(project):
    def create_app(**options):
        options.setdefault("watch", True)
        head = TailwindHead(sources=["components.py"], **options)
        app = FastHTML(sess_cls=None, hdrs=[head])
        app.mount("/static", StaticImmutable(directory="static"), name="static")

        @app.route("/")
        def get():
            return Div("Hello", cls="p-4 bg-blue-500")

        return app, head

    return create_app
