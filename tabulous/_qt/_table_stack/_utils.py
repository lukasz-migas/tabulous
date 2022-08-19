from __future__ import annotations
from qtpy import QtWidgets as QtW, QtCore


def create_temporal_line_edit(
    rect: QtCore.QRect,
    parent: QtW.QWidget,
    text: str,
) -> QtW.QLineEdit:
    line = QtW.QLineEdit(parent=parent)
    geometry = line.geometry()
    geometry.setWidth(rect.width())
    geometry.setHeight(rect.height())
    geometry.moveCenter(rect.center())
    geometry.adjust(4, 4, -2, -2)
    line.setGeometry(geometry)
    line.setText(text)
    line.setHidden(False)
    line.setFocus()
    line.selectAll()
    return line
