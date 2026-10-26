import gc
import time

import pytest
from fasthtml.common import Div, FastHTML

from fasthtml_tailwindcss import TailwindHead, _client


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
    monkeypatch.setattr(_client, "user_cache_path", lambda *a, **kw: tmp_path / "cache")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="example"\nversion="0.1.0"\n'
    )
    (tmp_path / "components.py").write_text('classes = "p-4 bg-blue-500"\n')
    config = _client.configuration(
        watch=False, sources=["components.py"], input=None, css=None
    )
    helpers.append(_client.cache_directory(config))
    yield tmp_path
    gc.collect()
    helpers.extend(path.parent for path in (tmp_path / "cache").glob("*/pid"))


@pytest.fixture
def application(project):
    def create_app(**options):
        head = TailwindHead(sources=["components.py"], **options)
        app = FastHTML(sess_cls=None, hdrs=[head])

        @app.get("/")  # ty: ignore[unresolved-attribute]  # FastHTML registers HTTP methods dynamically.
        def get():
            return Div("Hello", cls="p-4 bg-blue-500")

        return app, head

    return create_app
