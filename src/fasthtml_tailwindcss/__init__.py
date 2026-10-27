from collections.abc import Sequence
from pathlib import Path
from weakref import finalize

from fasthtml.common import Link, vurl

from .client import Session
from .config import configuration

__all__ = ["TailwindHead"]


class TailwindHead:
    def __init__(
        self,
        *,
        watch: bool = False,
        sources: Sequence[str | Path] | None = None,
        input: str | Path | None = None,
        css: str | None = None,
        output: str | Path = "./static/tailwind.css",
    ) -> None:
        self._config = configuration(
            sources=sources, input=input, css=css, output=output
        )
        (Path(self._config.root) / self._config.output).parent.mkdir(
            parents=True, exist_ok=True
        )
        self._session = Session(self._config) if watch else None
        if self._session is not None:
            finalize(self, self._session.close)

    def __deepcopy__(self, memo):
        return self

    def __ft__(self):
        if self._session is not None:
            self._session.start()
            if self._session.error:
                raise RuntimeError(self._session.error)
        path = "/" + self._config.output
        return Link(rel="stylesheet", href=vurl(path, root=self._config.root))
