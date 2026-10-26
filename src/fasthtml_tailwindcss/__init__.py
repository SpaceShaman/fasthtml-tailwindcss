from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from fasthtml.common import FastHTML, Style

from ._client import Session, configuration

__all__ = ["TailwindHead"]


class TailwindHead:
    def __init__(
        self,
        app: FastHTML,
        *,
        watch: bool = False,
        sources: Sequence[str | Path] | None = None,
        input: str | Path | None = None,
        css: str | None = None,
    ) -> None:
        if getattr(app.state, "_tailwind_head", None) is not None:
            raise ValueError("Register only one TailwindHead per application")
        self._config = configuration(watch=watch, sources=sources, input=input, css=css)
        self._session: Session | None = None
        self._original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = self.lifespan
        app.state._tailwind_head = self

    @asynccontextmanager
    async def lifespan(self, application):
        try:
            async with Session(self._config).lifespan() as session:
                self._session = session
                async with self._original_lifespan(application) as state:
                    yield state
        finally:
            self._session = None

    def __deepcopy__(self, memo):

        return self

    def __ft__(self):
        if self._session is None:
            raise RuntimeError("TailwindHead requires ASGI lifespan; do not disable it")
        if self._session.error:
            raise RuntimeError(self._session.error)
        css = self._session.output.read_text(encoding="utf-8")

        return Style(css.replace("</", "<\\/"))
