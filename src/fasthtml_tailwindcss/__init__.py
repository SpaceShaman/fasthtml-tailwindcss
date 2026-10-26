from collections.abc import Sequence
from pathlib import Path
from weakref import finalize

from fasthtml.common import Style

from ._client import Session, configuration

__all__ = ["TailwindHead"]


class TailwindHead:
    def __init__(
        self,
        *,
        watch: bool = False,
        sources: Sequence[str | Path] | None = None,
        input: str | Path | None = None,
        css: str | None = None,
    ) -> None:
        config = configuration(watch=watch, sources=sources, input=input, css=css)
        self._session = Session(config)
        self._session.start()
        finalize(self, self._session.close)

    def __deepcopy__(self, memo):
        return self

    def __ft__(self):
        if self._session.error:
            raise RuntimeError(self._session.error)
        css = self._session.output.read_text(encoding="utf-8")
        return Style(css.replace("</", "<\\/"))
