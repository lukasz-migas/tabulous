from __future__ import annotations
from typing import TYPE_CHECKING
from qtpy import QtWidgets as QtW, QtCore, QtGui
from qtpy.QtCore import Qt
import pandas as pd

from ..._keymap import QtKeys
from ....types import HeaderInfo

if TYPE_CHECKING:
    from qtpy.QtCore import pyqtBoundSignal
    from ._table_base import QMutableTable
    from ._enhanced_table import _QTableViewEnhanced
    from ._header_view import QDataFrameHeaderView


class _QTableLineEdit(QtW.QLineEdit):
    """LineEdit widget with dtype checker and custom defocusing."""

    def __init__(
        self,
        parent: QtCore.QObject | None = None,
        table: QMutableTable | None = None,
        pos: tuple[int, int] = (0, 0),
    ):
        super().__init__(parent)
        self._table = table
        self._pos = pos
        self.textChanged.connect(self._on_text_changed)

    def parentTableView(self) -> _QTableViewEnhanced:
        return self.parent().parent()

    def isTextValid(self) -> bool:
        """True if text is valid for this cell."""
        raise NotImplementedError()

    def _on_text_changed(self, text: str) -> None:
        """Change text color to red if invalid."""
        palette = QtGui.QPalette()
        if self.isTextValid():
            col = Qt.GlobalColor.black
        else:
            col = Qt.GlobalColor.red

        palette.setColor(QtGui.QPalette.ColorRole.Text, col)
        self.setPalette(palette)
        return None

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle key press events."""
        keys = QtKeys(event)
        pos = self.cursorPosition()
        nchar = len(self.text())
        r, c = self._pos
        if keys.is_moving():
            if pos == 0 and keys == "Left" and c >= 0:
                self.parentTableView().setFocus()
                self._table._qtable_view._selection_model.move_to(r, c - 1)
                return
            elif (
                pos == nchar
                and keys == "Right"
                and c < self._table.model().columnCount() - 1
                and self.selectedText() == ""
            ):
                self.parentTableView().setFocus()
                self._table._qtable_view._selection_model.move_to(r, c + 1)
                return
            elif keys == "Up" and r >= 0:
                self.parentTableView().setFocus()
                self._table._qtable_view._selection_model.move_to(r - 1, c)
                return
            elif keys == "Down" and r < self._table.model().rowCount() - 1:
                self.parentTableView().setFocus()
                self._table._qtable_view._selection_model.move_to(r + 1, c)
                return

        return super().keyPressEvent(event)


class _QHeaderLineEdit(_QTableLineEdit):
    """Line edit used for editing header text."""

    ALIGNMENT: Qt.AlignmentFlag

    def _get_index(self) -> int:
        raise NotImplementedError()

    def _get_rect(self, index: int) -> QtCore.QRect:
        raise NotImplementedError()

    def _get_pandas_axis(self) -> pd.Index:
        raise NotImplementedError()

    def _get_signal(self) -> pyqtBoundSignal:
        raise NotImplementedError()

    def __init__(
        self,
        parent: QDataFrameHeaderView,
        table: QMutableTable | None = None,
        pos: tuple[int, int] = (0, 0),
    ):
        super().__init__(parent, table, pos)

        index = self._get_index()
        geometry = self._get_rect(index)
        geometry.adjust(2, 1, -2, -1)
        self.setGeometry(geometry)
        self.setAlignment(self.ALIGNMENT)
        self.setHidden(False)

        df_axis = self._get_pandas_axis()
        if index < df_axis.size:
            old_value = df_axis[index]
            text = str(old_value)
        else:
            # spreadsheet
            old_value = None
            text = ""

        @self.editingFinished.connect
        def _set_header_data():
            self.editingFinished.disconnect()
            value = self.text()
            err = None
            if not self.isTextValid():
                err = ValueError(f"Duplicated name {value!r}")
            elif value != text and value:
                self._get_signal().emit(HeaderInfo(index, value, text))
            table = self._table._qtable_view
            table.setFocus()
            self.deleteLater()
            if err:
                raise err
            return None

        self.setText(str(old_value))
        self.selectAll()
        self.setFocus()

    def isTextValid(self) -> bool:
        """True if text is valid for this cell."""
        text = self.text()
        pd_index = self._get_pandas_axis()
        idx = self._get_index()
        not_in = text not in pd_index
        if idx < pd_index.size:
            return text == pd_index[idx] or not_in
        else:
            return not_in


class QVerticalHeaderLineEdit(_QHeaderLineEdit):
    ALIGNMENT = Qt.AlignmentFlag.AlignLeft

    def _get_index(self) -> int:
        return self._pos[0]

    def _get_rect(self, index: int) -> QtCore.QRect:
        header = self._table._qtable_view.verticalHeader()
        width = header.width()
        height = header.sectionSize(index)
        left = header.rect().left()
        top = header.sectionViewportPosition(index)
        return QtCore.QRect(left, top, width, height)

    def _get_pandas_axis(self) -> pd.Index:
        return self._table.model().df.index

    def _get_signal(self):
        return self._table.rowChangedSignal


class QHorizontalHeaderLineEdit(_QHeaderLineEdit):
    ALIGNMENT = Qt.AlignmentFlag.AlignCenter

    def _get_index(self) -> int:
        return self._pos[1]

    def _get_rect(self, index: int) -> QtCore.QRect:
        header = self._table._qtable_view.horizontalHeader()
        width = header.sectionSize(index)
        height = header.height()
        left = header.sectionViewportPosition(index)
        top = header.rect().top()
        return QtCore.QRect(left, top, width, height)

    def _get_pandas_axis(self) -> pd.Index:
        return self._table.model().df.columns

    def _get_signal(self):
        return self._table.columnChangedSignal


class QCellLineEdit(_QTableLineEdit):
    def isTextValid(self) -> bool:
        """True if text is valid for this cell."""
        r, c = self._pos
        try:
            self._table.convertValue(r, c, self.text())
        except Exception:
            return False
        return True