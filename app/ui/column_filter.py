# -*- coding: utf-8 -*-
"""Excel-style column filters for the Jobs table: tick the values you want to see.

The user asked for this by name: [owner's note: in the table, columns can be filtered to chosen values like Excel, for example only those with Sponsorship or only Data Analyst].

WHY IT MATTERS MORE THAN IT LOOKS

It replaced a rule that DELETED listings. The Filter used to decide, from a similarity score,
which job titles were close enough to be worth seeing -- and the scores turned out not to
track reality: "Analytics Engineer" scored 70 while only 15% of what it brought in was really
the work he wants, and "Quantitative Analyst" scored 65 against a measured 78%. Any threshold
built on that is a coin toss, and a wrong call there is a job he never learns existed.

Hiding is reversible; deleting is not. So everything related is now kept, and this is where he
chooses what to look at -- on the real listings, with the counts in front of him, changing his
mind as often as he likes. His own summary: [owner's note: bring everything related, and the choice of what to show is made afterwards].

HOW IT BEHAVES

* The values offered are the ones actually PRESENT in the current results, each with its
  count. A filter that offers "Germany" when no German listing is there would be a way to
  choose an empty table, and the counts are what make the choice informed.
* Nothing ticked means no filtering on that column -- the normal state, and the one that must
  never hide anything. An empty selection is "show everything", never "show nothing".
* A value that disappears from the results keeps its tick, silently, so a new search does not
  throw away a choice that will apply again next time. It is simply not offered.
* Every column's filter is ANDed with the others, and the Jobs table's own "Show only" term
  filter, because that is what Excel does and it is what "only those with sponsorship AND in
  the Netherlands" means.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QLabel, QMenu, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget, QWidgetAction)


class ColumnFilterButton(QPushButton):
    """One column's filter: a button that opens the list of values present, with tick boxes.

    `changed` fires whenever the selection changes, and the owner re-renders.
    """

    changed = Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._chosen: set = set()
        self._values: list = []
        # The widgets of the open panel, kept so a tick or "Select none" can be shown IN PLACE.
        # The panel is never torn down and rebuilt while it is open -- see offer().
        self._ticks: dict = {}
        self._all_button = None
        self._rebuild_when_closed = False
        self.setCursor(Qt.PointingHandCursor)
        self._menu = QMenu(self)
        self._menu.aboutToHide.connect(self._rebuild_if_waiting)
        self.setMenu(self._menu)
        self._show_label()

    # ------------------------------------------------------------------ the values ----

    def offer(self, counted) -> None:
        """The values present now, as [(value, count)], most common first."""
        new_values = list(counted or [])
        # THE CRASH THIS GUARDS (Windows, Qt6Widgets access violation, twice in one morning,
        # right after a Filter and while using a column filter): every tick and every re-render
        # called this, and this destroyed the panel -- with the mouse over it, the tick that
        # had just been clicked, and the menu open -- so Qt was handed a deleted widget.
        # Nothing about the values had changed in the tick case, so now nothing is rebuilt;
        # and when they have changed (a new Filter result) an OPEN menu is left alone and
        # rebuilt the moment it closes.
        if new_values == self._values and self._menu.actions():
            self._show_label()
            return
        self._values = new_values
        if self._menu.isVisible():
            self._rebuild_when_closed = True
        else:
            self._rebuild()
        self._show_label()

    def _rebuild_if_waiting(self) -> None:
        if self._rebuild_when_closed:
            self._rebuild_when_closed = False
            self._rebuild()

    def selected(self) -> set:
        """The ticked values. Empty means no filtering on this column."""
        return set(self._chosen)

    def keeps(self, value) -> bool:
        """Does this column's filter admit that value? Empty selection admits everything."""
        return not self._chosen or str(value) in self._chosen

    def clear_selection(self) -> None:
        self._chosen = set()
        self._show_ticks()
        self._show_label()

    def _show_ticks(self) -> None:
        """Bring the open panel's boxes and its first button in line with the selection."""
        for value, tick in self._ticks.items():
            tick.blockSignals(True)
            tick.setChecked(value in self._chosen)
            tick.blockSignals(False)
        if self._all_button is not None:
            self._all_button.setText('Show all' if self._chosen else 'Select none')

    # ------------------------------------------------------------------- the menu ----

    def _rebuild(self) -> None:
        # Detached and deleted LATER: never destroyed in the middle of an event it is handling.
        for action in self._menu.actions():
            self._menu.removeAction(action)
            action.deleteLater()
        self._ticks = {}
        self._all_button = None
        if not self._values:
            empty = QWidgetAction(self._menu)
            note = QLabel('  Nothing to filter on yet.  ')
            note.setStyleSheet('color: #6b7280; padding: 6px;')
            empty.setDefaultWidget(note)
            self._menu.addAction(empty)
            return

        # One scrollable panel of tick boxes rather than a menu of checkable actions: a menu
        # closes on every click, and choosing four countries would mean opening it four times.
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(4)

        all_button = QPushButton('Show all' if self._chosen else 'Select none')
        all_button.setFlat(True)
        all_button.clicked.connect(self._toggle_all)
        box.addWidget(all_button)
        self._all_button = all_button

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        box.addWidget(line)

        for value, count in self._values:
            tick = QCheckBox('%s   (%d)' % (value, count))
            tick.setChecked(value in self._chosen)
            tick.toggled.connect(lambda on, v=value: self._set(v, on))
            box.addWidget(tick)
            self._ticks[value] = tick

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(270)
        scroll.setMaximumHeight(360)

        action = QWidgetAction(self._menu)
        action.setDefaultWidget(scroll)
        self._menu.addAction(action)

    def _toggle_all(self) -> None:
        if self._chosen:
            self._chosen = set()
        else:
            # "Select none" ticks nothing and means nothing is shown for this column, which is
            # a legitimate thing to ask for -- but it is reached through a button that says so
            # rather than by unticking every value one at a time.
            self._chosen = {'\x00 nothing'}
        self._show_ticks()
        self._show_label()
        self.changed.emit()

    def _set(self, value, on) -> None:
        self._chosen.discard('\x00 nothing')
        if on:
            self._chosen.add(str(value))
        else:
            self._chosen.discard(str(value))
        if self._all_button is not None:
            self._all_button.setText('Show all' if self._chosen else 'Select none')
        self._show_label()
        self.changed.emit()

    def _show_label(self) -> None:
        """The button says what it is doing, not what it is."""
        present = {value for value, _count in self._values}
        chosen_here = self._chosen & present
        if not self._chosen:
            self.setText('%s: all' % self._label)
            self.setToolTip('Showing every value. Click to choose.')
        elif not chosen_here:
            self.setText('%s: none' % self._label)
            self.setToolTip('Nothing chosen from this column, so nothing is shown.')
        elif len(chosen_here) == 1:
            self.setText('%s: %s' % (self._label, next(iter(chosen_here))))
            self.setToolTip('Click to change.')
        else:
            self.setText('%s: %d of %d' % (self._label, len(chosen_here), len(present)))
            self.setToolTip(', '.join(sorted(chosen_here)))
