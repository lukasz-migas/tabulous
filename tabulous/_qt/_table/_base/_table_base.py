from __future__ import annotations
from typing import Any, NamedTuple, overload, TYPE_CHECKING
from qtpy import QtWidgets as QtW, QtGui, QtCore
from qtpy.QtCore import Signal, Qt
import pandas as pd

import numpy as np
from ._model_base import AbstractDataFrameModel
from ..._utils import show_messagebox
from ....types import FilterType


class ItemInfo(NamedTuple):
    """A named tuple for item update."""
    row: int
    column: int
    value: Any

# Flags
_EDITABLE = QtW.QAbstractItemView.EditTrigger.EditKeyPressed | QtW.QAbstractItemView.EditTrigger.DoubleClicked
_READ_ONLY = QtW.QAbstractItemView.EditTrigger.NoEditTriggers
_SCROLL_PRE_PIXEL = QtW.QAbstractItemView.ScrollMode.ScrollPerPixel


class QTableLayerBase(QtW.QTableView):
    itemChangedSignal = Signal(ItemInfo)
    selectionChangedSignal = Signal(list)
    _data_raw: pd.DataFrame
    
    def __init__(self, parent: QtW.QWidget | None = None, data: pd.DataFrame | None = None):
        super().__init__(parent)
        model = self.createModel()
        model.df = data
        self.setModel(model)
        model.dataEdited.connect(self.setDataFrameValue)
        
        self.setDataFrame(data)
        self.setVerticalScrollMode(_SCROLL_PRE_PIXEL)
        self.setHorizontalScrollMode(_SCROLL_PRE_PIXEL)
        self._editable = False
        self._zoom = 1.0
        self._initial_font_size = self.font().pointSize()
        self._initial_section_size = (
            self.horizontalHeader().defaultSectionSize(),
            self.verticalHeader().defaultSectionSize(),
        )
        self._filter_slice: FilterType | None = None

        delegate = TableItemDelegate(parent=self)
        self.setItemDelegate(delegate)
        
        # header editing signals
        self.horizontalHeader().sectionDoubleClicked.connect(self.editHorizontalHeader)
        self.verticalHeader().sectionDoubleClicked.connect(self.editVerticalHeader)

    def getDataFrame(self) -> pd.DataFrame:
        raise NotImplementedError()
    
    def setDataFrame(self) -> None:
        raise NotImplementedError()
    
    def createModel(self) -> AbstractDataFrameModel:
        raise NotImplementedError()
    
    def dataShape(self) -> tuple[int, int]:
        return self._data_raw.shape

    def tableShape(self) -> tuple[int, int]:
        model = self.model()
        nr = model.rowCount()
        nc = model.columnCount()
        return (nr, nc)

    def convertValue(self, r: int, c: int, value: Any) -> Any:
        """Convert value before updating DataFrame."""
        return value
    
    @overload
    def setDataFrameValue(self, r: int, c: int, value: Any) -> None:
        ...
    
    @overload
    def setDataFrameValue(self, r: slice, c: slice, value: pd.DataFrame) -> None:
        ...
    
    def setDataFrameValue(self, r, c, value) -> None:
        data = self._data_raw

        # convert values
        if isinstance(r, int) and isinstance(c, int):
            _value = self.convertValue(r, c ,value)
        elif isinstance(r, slice) and isinstance(c, slice):
            _value: pd.DataFrame = value
            if _value.size == 1:
                v = _value.values[0 ,0]
                _value = data.iloc[r, c].copy()
                for _ir, _r in enumerate(range(r.start, r.stop)):
                    for _ic, _c in enumerate(range(c.start, c.stop)):
                        _value.iloc[_ir, _ic] = self.convertValue(_r, _c, v)
            else:
                for _ir, _r in enumerate(range(r.start, r.stop)):
                    for _ic, _c in enumerate(range(c.start, c.stop)):
                        _value.iloc[_ir, _ic] = self.convertValue(_r, _c, _value.iloc[_ir, _ic])
        else:
            raise TypeError
        
        if self._filter_slice is None:
            r0 = r
        else:
            if callable(self._filter_slice):
                sl = self._filter_slice(data)
            else:
                sl = self._filter_slice
            
            spec = np.where(sl)[0].tolist()
            r0 = spec[r]
            self.model().updateValue(r, c, _value)
        data.iloc[r0, c] = _value
        self.itemChangedSignal.emit(ItemInfo(r, c, _value))
        self.refresh()
        return None

    def zoom(self) -> float:
        """Get current zoom factor."""
        return self._zoom
    
    def setZoom(self, value: float) -> None:
        """Set zoom factor."""
        if not 0.25 <= value <= 2.0:
            raise ValueError("Zoom factor must between 0.25 and 2.0.")
        # To keep table at the same position.
        zoom_ratio = 1 / self._zoom * value
        pos = self.verticalScrollBar().sliderPosition()
        self.verticalScrollBar().setSliderPosition(pos * zoom_ratio)
        pos = self.horizontalScrollBar().sliderPosition()
        self.horizontalScrollBar().setSliderPosition(pos * zoom_ratio)
        
        # Zoom font size
        font = self.font()
        font.setPointSize(self._initial_font_size*value)
        self.setFont(font)
        
        # Zoom section size of headers
        h, v = self._initial_section_size
        self.horizontalHeader().setDefaultSectionSize(h * value)
        self.verticalHeader().setDefaultSectionSize(v * value)
        
        # Update stuff
        self._zoom = value

    if TYPE_CHECKING:
        def itemDelegate(self) -> TableItemDelegate: ...
        def model(self) -> AbstractDataFrameModel: ...
        
    def precision(self) -> int:
        """Return table value precision."""
        return self.itemDelegate().ndigits
    
    def setPrecision(self, ndigits: int) -> None:
        """Set table value precision."""
        ndigits = int(ndigits)
        if ndigits <= 0:
            raise ValueError("Cannot set negative precision.")
        self.itemDelegate().ndigits = ndigits
    
    def editability(self) -> bool:
        """Return the editability of the table."""
        return self._editable
    
    def setEditability(self, editable: bool):
        """Set the editability of the table."""
        if editable:
            self.setEditTriggers(_EDITABLE)
        else:
            self.setEditTriggers(_READ_ONLY)
        self._editable = editable
    
    def connectItemChangedSignal(self, slot):
        self.itemChangedSignal.connect(slot)
        return slot
    
    def connectSelectionChangedSignal(self, slot):
        self.selectionChangedSignal.connect(slot)
        return slot
    
    def selectionChanged(
        self,
        selected: QtCore.QItemSelection,
        deselected: QtCore.QItemSelection,
    ) -> None:
        """Evoked when table selection range is changed."""
        self.selectionChangedSignal.emit(self.selections())
        return super().selectionChanged(selected, deselected)
    
    def selections(self) -> list[tuple[slice, slice]]:
        """Get list of selections as slicable tuples"""
        selections = self.selectionModel().selection()
        
        # selections = self.selectedRanges()
        out: list[tuple[slice, slice]] = []
        for i in range(len(selections)):
            sel = selections[i]
            r0 = sel.top()
            r1 = sel.bottom() + 1
            c0 = sel.left()
            c1 = sel.right() + 1
            out.append((slice(r0, r1), slice(c0, c1)))
        
        return out

    def setSelections(self, selections: list[tuple[slice, slice]]):
        """Set list of selections."""
        self.clearSelection()
        
        model = self.model()
        nr, nc = model.df.shape
        try:
            for sel in selections:
                r, c = sel
                r0, r1, _ = r.indices(nr)
                c0, c1, _ = c.indices(nc)
                selection = QtCore.QItemSelection(
                    model.index(r0, c0), model.index(r1 - 1, c1 - 1)
                )
                self.selectionModel().select(
                    selection, QtCore.QItemSelectionModel.SelectionFlag.Select
                )
                
        except Exception as e:
            self.clearSelection()
            raise e

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        _mod = e.modifiers()
        _key = e.key()
        if _mod & Qt.ControlModifier and _key == Qt.Key.Key_C:
            headers = _mod & Qt.ShiftModifier
            return self.copyToClipboard(headers)
        elif _mod & Qt.ControlModifier and _key == Qt.Key.Key_V:
            return self.pasteFromClipBoard()
        elif _mod == Qt.NoModifier and _key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            return self.deleteValues()
        elif (_mod in (Qt.NoModifier, Qt.ShiftModifier)
              and (Qt.Key.Key_Exclam <= _key <= Qt.Key.Key_ydiaeresis)
              ):
            # Enter editing mode
            text = QtGui.QKeySequence(_key).toString()
            if _mod != Qt.ShiftModifier:
                text = text.lower()
            self.model().setData(self.currentIndex(), text, Qt.ItemDataRole.EditRole)
            self.edit(self.currentIndex())
            focused_widget = QtW.QApplication.focusWidget()
            if isinstance(focused_widget, QtW.QLineEdit):
                focused_widget.deselect()
            return
        
        return super().keyPressEvent(e)

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        """Zoom in/out table."""
        if a0.modifiers() & Qt.ControlModifier:
            dt = a0.angleDelta().y() / 120
            zoom = self.zoom() + 0.15 * dt
            self.setZoom(min(max(zoom, 0.25), 2.0))
            return None
                
        return super().wheelEvent(a0)
    
    def copyToClipboard(self, headers: bool = True):
        """Copy currently selected cells to clipboard."""
        selections = self.selections()
        if len(selections) == 0:
            return
        r_ranges = set()
        c_ranges = set()
        for rsel, csel in selections:
            r_ranges.add((rsel.start, rsel.stop))
            c_ranges.add((csel.start, csel.stop))
        
        nr = len(r_ranges)
        nc = len(c_ranges)
        if nr > 1 and nc > 1:
            show_messagebox(
                mode="error", title="Error", text="Wrong selection range.", parent=self
            )
            return
        else:
            data = self.model().df
            if nr == 1:
                axis = 1
            else:
                axis = 0
            ref = pd.concat([data.iloc[sel] for sel in selections], axis=axis)
            ref.to_clipboard(index=headers, header=headers)
    
    def readClipBoard(self) -> pd.DataFrame:
        """Read clipboard data and return as pandas DataFrame."""
        return pd.read_clipboard(header=None)
        
    def pasteFromClipBoard(self):
        """
        Paste data to table.
        
        This function supports many types of pasting.
        1. Single selection, single data in clipboard -> just paste
        2. Single selection, multiple data in clipboard -> paste starts from the selection position.
        3. Multiple selection, single data in clipboard -> paste the same value for all the selection.
        4. Multiple selection, multiple data in clipboard -> paste only if their shape is identical.
        
        Also, if data is filtrated, pasted data also follows the filtration.
        """
        selections = self.selections()
        n_selections = len(selections)
        if n_selections == 0 or not self.editability():
            return
        elif n_selections > 1:
            return show_messagebox(
                mode="error",
                title="Error",
                text="Cannot paste with multiple selections.", 
                parent=self,
            )
        
        df = self.readClipBoard()
        
        # check size and normalize selection slices
        sel = selections[0]
        rrange, crange = sel
        rlen = rrange.stop - rrange.start
        clen = crange.stop - crange.start
        dr, dc = df.shape
        size = dr * dc

        if rlen * clen == 1 and size > 1:
            sel = (slice(rrange.start, rrange.start + dr), slice(crange.start, crange.start + dc))

        elif size > 1 and (rlen, clen) != (dr, dc):
            # If selection is column-wide or row-wide, resize them
            if rlen == self.model().df.shape[0]:
                rrange = slice(0, dr)
                rlen = dr
            if clen == self.model().df.shape[1]:
                crange = slice(0, dc)
                clen = dc
            
            if (rlen, clen) != (dr, dc):
                return show_messagebox(
                    mode="error",
                    title="Error",
                    text=f"Shape mismatch between data in clipboard {(rlen, clen)} and "
                        f"destination {(dr, dc)}.", 
                    parent=self,
                )
            else:
                sel = (rrange, crange)
    
        rsel, csel = sel
        
        # check dtype
        dtype_src = df.dtypes
        dtype_dst = self._data_raw.dtypes[csel]
        if any(a.kind != b.kind for a, b in zip(dtype_src.values, dtype_dst.values)):
            return show_messagebox(
                mode="error",
                title="Error",
                text=f"Data type mismatch between data in clipboard {list(dtype_src)} and "
                    f"destination {list(dtype_dst)}.",
                parent=self,
            )
        
        # update table
        try:
            self.setDataFrameValue(rsel, csel, df)
            
        except Exception as e:
            show_messagebox(
                mode="error",
                title=e.__class__.__name__,
                text=str(e), 
                parent=self,
            )
            raise e from None

        return None
    
    def deleteValues(self):
        """Replace selected cells with NaN."""
        selections = self.selections()
        for sel in selections:
            rsel, csel = sel
            nr = rsel.stop - rsel.start
            nc = csel.stop - csel.start
            dtypes = list(self._data_raw.dtypes[csel])
            df = pd.DataFrame(
                {c: pd.Series(np.full(nr, np.nan), dtype=dtypes[c]) for c in range(nc)}, 
            )
            self.setDataFrameValue(rsel, csel, df)

    def filter(self) -> FilterType | None:
        """Return the current filter."""
        return self._filter_slice

    def setFilter(self, sl: FilterType):
        """Set filter to the table view."""
        self._filter_slice = sl
        data_raw = self._data_raw
        
        if sl is None:
            self.model().df = data_raw
        else:
            if callable(sl):
                sl_filt = sl(data_raw)
            else:
                sl_filt = sl
            self.model().df = data_raw[sl_filt]
        self.refresh()
    
    def refresh(self) -> None:
        self.viewport().update()
        self.horizontalHeader().viewport().update()
        self.verticalHeader().viewport().update()
        return None
    
    def editHorizontalHeader(self, index: int):
        """Edit the horizontal header."""
        if not self.editability():
            return
        
        _header = self.horizontalHeader()
        _line = QtW.QLineEdit(_header)
        edit_geometry = _line.geometry()
        edit_geometry.setHeight(_header.height())
        edit_geometry.setWidth(_header.sectionSize(index))
        edit_geometry.moveLeft(_header.sectionViewportPosition(index))
        _line.setGeometry(edit_geometry)
        _line.setHidden(False)
        _line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        column_axis = self.model().df.columns
        if index < column_axis.size:
            text = column_axis[index]
        else:
            text = ""
        
        _line.setText(str(text))
        _line.setFocus()
            
        self._line = _line
        
        @_line.editingFinished.connect
        def _set_header_data():
            self._line.setHidden(True)
            self.setHorizontalHeaderValue(index, self._line.text())

    def editVerticalHeader(self, index: int):
        if not self.editability():
            return
        
        _header = self.verticalHeader()
        _line = QtW.QLineEdit(_header)
        edit_geometry = _line.geometry()
        edit_geometry.setHeight(_header.sectionSize(index))
        edit_geometry.setWidth(_header.width())
        edit_geometry.moveTop(_header.sectionViewportPosition(index))
        _line.setGeometry(edit_geometry)
        _line.setHidden(False)
        
        index_axis = self.model().df.index
        
        if index < index_axis.size:
            text = index_axis[index]
        else:
            text = ""
        
        _line.setText(str(text))
        _line.setFocus()
        _line.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._line = _line
        
        @_line.editingFinished.connect
        def _set_header_data():
            self._line.setHidden(True)
            self.setVerticalHeaderValue(index, self._line.text())

    def setHorizontalHeaderValue(self, index: int, value: Any) -> None:
        column_axis = self.model().df.columns
        _header = self.horizontalHeader()
        
        mapping = {column_axis[index]: value}
        
        self._data_raw.rename(columns=mapping, inplace=True)
        self.model().df.rename(columns=mapping, inplace=True)
        
        size_hint = _header.sectionSizeHint(index)
        if _header.sectionSize(index) < size_hint:
            _header.resizeSection(index, size_hint)

    def setVerticalHeaderValue(self, index: int, value: Any) -> None:
        index_axis = self.model().df.index
        _header = self.verticalHeader()
        
        mapping = {index_axis[index]: value}
        
        self._data_raw.rename(index=mapping, inplace=True)
        self.model().df.rename(index=mapping, inplace=True)
        _width_hint = _header.sizeHint().width()
        _header.resize(QtCore.QSize(_width_hint, _header.height()))


# modified from magicgui
class TableItemDelegate(QtW.QStyledItemDelegate):
    """Displays table widget items with properly formatted numbers."""
    
    edited = Signal(tuple)
    
    def __init__(self, parent: QtCore.QObject | None = None, ndigits: int = 4) -> None:
        super().__init__(parent)
        self.ndigits = ndigits

    def displayText(self, value, locale):
        return super().displayText(self._format_number(value), locale)

    def _format_number(self, text: str) -> str:
        """convert string to int or float if possible"""
        try:
            value: int | float | None = int(text)
        except ValueError:
            try:
                value = float(text)
            except ValueError:
                value = None
        
        ndigits = self.ndigits
        
        if isinstance(value, (int, float)):
            if 0.1 <= abs(value) < 10 ** (ndigits + 1) or value == 0:
                text = str(value) if isinstance(value, int) else f"{value:.{ndigits}f}"
            else:
                text = f"{value:.{ndigits-1}e}"

        return text