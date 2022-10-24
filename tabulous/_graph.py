from __future__ import annotations
from contextlib import contextmanager
from typing import Callable, Any, Hashable, MutableMapping, TypeVar
import weakref
from .widgets import TableBase


class Graph:
    """Calculation graph object that works in a table."""

    def __init__(
        self,
        table: TableBase,
        func: Callable[[], Any],
        sources: list[tuple[slice, slice]],
    ):
        self._sources = sources
        self._func = func
        self._table_ref = weakref.ref(table)
        self._callback_blocked = False

    def __hash__(self) -> int:
        return id(self)

    @property
    def table(self) -> TableBase:
        return self._table_ref()

    @contextmanager
    def blocked(self):
        was_blocked = self._callback_blocked
        self._callback_blocked = True
        try:
            yield
        finally:
            self._callback_blocked = was_blocked

    def update(self):
        """Update the graph."""
        table = self.table
        if table is None:
            return self.disconnect()

        if not self._callback_blocked:
            with self.blocked():
                self._func()

        return None

    def connect(self):
        self.table.events.data.connect(self.update)
        # First exception should be considered as a wrong expression.
        # Disconnect the callback.
        try:
            self.update()
        except Exception:
            self.disconnect()
            raise
        return None

    def disconnect(self):
        self.table.events.data.disconnect(self.update)
        return None


_K = TypeVar("_K", bound=Hashable)


class GraphManager(MutableMapping[_K, Graph]):
    """Calculation graph manager."""

    def __init__(self):
        self._graphs: dict[_K, Graph] = {}
        self._update_blocked = False

    def __getitem__(self, key: _K) -> Graph:
        return self._graphs[key]

    def __setitem__(self, key: _K, value) -> None:
        if not self._update_blocked:
            self._graphs[key] = value

    def __delitem__(self, key: _K) -> None:
        if not self._update_blocked:
            del self._graphs[key]

    def __len__(self) -> int:
        return len(self._graphs)

    def __iter__(self):
        return iter(self._graphs)

    @contextmanager
    def blocked(self):
        was_blocked = self._update_blocked
        self._update_blocked = True
        try:
            yield
        finally:
            self._update_blocked = was_blocked
