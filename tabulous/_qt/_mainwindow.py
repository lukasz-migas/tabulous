from __future__ import annotations
from typing import TYPE_CHECKING, Callable, TypeVar
from qtpy import QtWidgets as QtW, QtGui
from qtpy.QtWidgets import QAction
from qtpy.QtCore import Qt, QEvent

from ._table_stack import QTabbedTableStack
from ._utils import search_name_from_qmenu
from ..types import TabPosition

if TYPE_CHECKING:
    from ..widgets import TableViewer
    from typing_extensions import ParamSpec
    _P = ParamSpec("_P")

_R = TypeVar("_R")


class _QtMainWidgetBase(QtW.QWidget):
    _table_viewer: TableViewer
    _tablestack: QTabbedTableStack
    _toolbar: QtW.QToolBar
    
    def __init__(
        self,
        tab_position: TabPosition | str = TabPosition.top,
    ):
        super().__init__()
        tab_position = TabPosition(tab_position)
        self._tablestack = QTabbedTableStack(tab_position=tab_position.name)
        self.setCentralWidget(self._tablestack)
    
    def setCentralWidget(self, wdt: QtW.QWidget):
        """Set the splitter widget."""
        raise NotImplementedError()
    
    def toolBarVisible(self) -> bool:
        """Visibility of toolbar"""
        raise NotImplementedError()
    
    def setToolBarVisible(self, visible: bool):
        """Set visibility of toolbar"""
        raise NotImplementedError()
    
    def addDefaultToolBar(self):
        raise NotImplementedError()
    

class QMainWidget(_QtMainWidgetBase):
    def __init__(self, tab_position: TabPosition | str = TabPosition.top):
        super().__init__(tab_position)
        self._toolbar = None
        
    def setCentralWidget(self, wdt: QtW.QWidget):
        """Mimicking QMainWindow's method by adding a widget to the layout."""
        _layout = QtW.QVBoxLayout()
        _layout.setContentsMargins(0, 0, 0, 0)
        _layout.addWidget(wdt)
        self.setLayout(_layout)
    
    if TYPE_CHECKING:
        def layout(self) -> QtW.QVBoxLayout:
            ...

    def toolBarVisible(self) -> bool:
        if self._toolbar is None:
            return False
        else:
            return self._toolbar.isVisible()
    
    def setToolBarVisible(self, visible: bool):
        if visible and self._toolbar is None:
            from ._toolbar import QTableStackToolBar
            self._toolbar = QTableStackToolBar(self)
            self.layout().insertWidget(0, self._toolbar)
        
        return self._toolbar.setVisible(visible)

class QMainWindow(QtW.QMainWindow, _QtMainWidgetBase):
    _table_viewer: TableViewer
    _instances: list['QMainWindow'] = []

    def __init__(
        self,
        tab_position: TabPosition | str = TabPosition.top,
    ):
        super().__init__()
        _QtMainWidgetBase.__init__(self, tab_position=tab_position)
        self.setWindowTitle("tabulous")
        from ._toolbar import QTableStackToolBar
        self._toolbar = QTableStackToolBar(self)
        self.addToolBar(self._toolbar)
        self._tablestack.setMinimumSize(600, 400)
        QMainWindow._instances.append(self)

    def addDockWidget(
        self, 
        qwidget: QtW.QWidget,
        *,
        name: str = "",
        area: str = "right",
        allowed_areas: list[str] = None,
    ):
        from .._qt._dockwidget import QtDockWidget

        name = name or qwidget.objectName()
        dock = QtDockWidget(
            self,
            qwidget,
            name=name.replace("_", " "),
            area=area,
            allowed_areas=allowed_areas,
        )

        super().addDockWidget(QtDockWidget.areas[area], dock)
        return dock
    
    @classmethod
    def currentViewer(cls) -> TableViewer:
        """Return the current TableViewer widget."""
        window = cls._instances[-1] if cls._instances else None
        return window._table_viewer if window else None
    
    def event(self, e: QEvent):
        if e.type() == QEvent.Type.Close:
            # when we close the MainWindow, remove it from the instances list
            try:
                QMainWindow._instances.remove(self)
            except ValueError:
                pass
        if e.type() in {QEvent.Type.WindowActivate, QEvent.Type.ZOrderChange}:
            # upon activation or raise_, put window at the end of _instances
            try:
                inst = QMainWindow._instances
                inst.append(inst.pop(inst.index(self)))
            except ValueError:
                pass
        return super().event(e)

    def registerAction(self, location: str) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
        locs = location.split(">")
        if len(locs) < 2:
            raise ValueError("Location must be 'XXX>YYY>ZZZ' format.")
        menu = self.menuBar()
        for loc in locs[:-1]:
            a = search_name_from_qmenu(menu, loc)
            if a is None:
                menu = menu.addMenu(loc)
            else:
                menu = a.menu()
                if menu is None:
                    i = locs.index(loc)
                    err_loc = ">".join(locs[:i])
                    raise TypeError(f"{err_loc} is not a menu.")
                
        def wrapper(f: Callable):
            action = QAction(locs[-1], self)
            action.triggered.connect(f)
            menu.addAction(action)
            return f
        return wrapper

    def toolBarVisible(self) -> bool:
        return self._toolbar.isVisible()
    
    def setToolBarVisible(self, visible: bool):
        return self._toolbar.setVisible(visible)
