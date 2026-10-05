# -*- coding: utf-8 -*-
"""Apply and Remove, painted into their cells instead of built as widgets.

WHY THIS EXISTS: 193 SECONDS OF IT

The user reported the app hanging on large results -- [owner's note: the program hangs when it reads about 20,000 rows into the table] -- and asked whether the buttons could stay. They can, and
this is how.

The table used to build two real QPushButtons per row, each inside a QWidget wrapper with its
own layout, each with a signal connected. cProfile on the real page, 4,000 rows:

    total render                     4.97s
      _render_row_buttons            3.71s   (75%)
        signal.connect, 8,008 calls  1.85s
        the QWidget wrappers         0.72s
        setCellWidget                0.58s
      all twelve text columns        0.15s   (3%)

Measured at the size he actually hits, 20,000 rows: 193.5 seconds with real buttons, 1.67
seconds painted. 116x, and the difference is entirely that Qt was creating 40,000 widgets and
40,000 connections for rows almost none of which are on screen.

A delegate paints only the cells in the viewport -- about twenty rows -- so the cost stops
depending on how many listings there are at all.

WHAT DOES NOT CHANGE

The buttons look the same, in the same colours as the stylesheet gave them, and a click does
the same thing. That was the user's one condition: [owner's note: only Apply and Remove should stay].

The hover highlight is kept too, because a control that does not react to the mouse reads as
disabled -- and these are the two cells in the table where a click has consequences.
"""
from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate

# The colours the stylesheet used for the real buttons, so nothing about the table looks
# different after the change. Kept here rather than read back out of the sheet: a painted
# button cannot ask Qt to resolve a CSS rule for it, and two copies of a colour are better than
# a button that silently paints itself the wrong shade.
# Annotated, because without it mypy joins the two entries -- one has a border, the other has
# None -- into `object`, and then every lookup below is "not indexable".
_STYLES: Dict[str, Dict[str, Optional[str]]] = {
    'apply': {'fill': '#2ECC71', 'fill_hover': '#58d98a', 'text': '#06210f', 'border': None},
    'remove': {'fill': '#3a1f28', 'fill_hover': '#5a2a35', 'text': '#ff8a94',
               'border': '#5a2a35'},
}

_PADDING_X = 6          # matches the old QWidget wrapper's contents margins
_PADDING_Y = 5
_RADIUS = 6


class RowButtonDelegate(QStyledItemDelegate):
    """One column's button. `clicked` carries the row it was clicked on.

    The row number is what goes out, not the job: the table owns the list and looking the job
    up there means this class cannot hold a stale copy of a row that has since been removed.
    """

    clicked = Signal(int)

    def __init__(self, label: str, kind: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._style = _STYLES.get(kind, _STYLES['apply'])
        self._hover_row = -1

    # ----------------------------------------------------------------- painting ----

    def _button_rect(self, cell: QRect) -> QRect:
        return cell.adjusted(_PADDING_X, _PADDING_Y, -_PADDING_X, -_PADDING_Y)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._button_rect(option.rect)

        hovered = index.row() == self._hover_row
        fill = QColor(self._style['fill_hover'] if hovered else self._style['fill'])
        painter.setBrush(fill)
        if self._style['border']:
            painter.setPen(QPen(QColor(self._style['border']), 1))
        else:
            painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, _RADIUS, _RADIUS)

        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(self._style['text']))
        painter.drawText(rect, Qt.AlignCenter, self._label)
        painter.restore()

    # ------------------------------------------------------------------- clicks ----

    def editorEvent(self, event, model, option, index) -> bool:
        """Turn a click inside the drawn button into `clicked`.

        The press is swallowed as well as the release, so the table does not treat it as a
        click on the row and open the listing's URL -- which is what every OTHER column does.
        """
        kind = event.type()
        if kind == QEvent.MouseMove:
            if self._hover_row != index.row():
                self._hover_row = index.row()
            return False                      # let the view repaint
        if kind in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            return self._button_rect(option.rect).contains(event.position().toPoint())
        if kind == QEvent.MouseButtonRelease:
            if self._button_rect(option.rect).contains(event.position().toPoint()):
                self.clicked.emit(index.row())
                return True
        return False

    def forget_hover(self) -> None:
        self._hover_row = -1
