from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QMenu,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget, QWidgetAction,
)

from app import pipeline
from app.styles import (CATEGORY_BADGE_COLORS, ENGLISH_BADGE_COLORS,
                        FALLBACK_BADGE_COLOR, SENIORITY_BADGE_COLORS,
                        SPONSORSHIP_BADGE_COLORS)
from app.ui.column_filter import ColumnFilterButton
from app.ui.confirm_dialog import TypeToConfirmDialog
from app.ui.row_button_delegate import RowButtonDelegate


def _similarity_of(job: dict) -> int:
    """How close this listing's title is to the one Sina searched, 0-100.

    A row with no score counts as 100, not 0. Those are the listings kept because they said
    nothing -- silence is not evidence, which is the rule everywhere in this app -- and
    sorting them to the bottom would treat "we could not tell" as "a poor match".
    """
    try:
        return max(0, min(100, int(job.get('field_similarity'))))   # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 100

# Three words, because the column is read at a glance down a list. The sentence behind each
# one is the tooltip.
_WORTH_LABELS = {'apply': 'Apply', 'check': 'Check first', 'skip': 'Skip'}
_WORTH_COLORS = {'apply': '#1e7d32', 'check': '#b8860b', 'skip': '#7a2e2e'}

# The sentence behind each English? badge. "English only" is the answer for silence as
# well as for a stated English-only requirement, and that is worth saying out loud.
_ENGLISH_TOOLTIPS = {
    'English only': 'Nothing here asks for a second language.\n'
                    'Most adverts never mention language at all, '
                    'and that counts as this.',
    'English + Other': 'English is named alongside a language you do not have.\n'
                       'Kept on purpose, so you judge the second one yourself.',
    'Other only': 'Asks for a language you do not have and never names English.\n'
                  'The Filter deletes these; you only see them in a raw search.',
}


# Seniority before Type, in that order, because that is the order he groups by:
# "اول بر اساس Seniority Groupby میکنی و بعد بر اساس Type".
COLUMNS = [
    "#", "Title", "Company", "Country", "Sponsorship Visa", "Seniority", "Type",
    "English?", "Details", "Match %", "Worth it?", "Found as", "Apply", "Remove",
]
SPONSORSHIP_COLUMN = 4
SENIORITY_COLUMN = 5
TYPE_COLUMN = 6
# Which of the three language shapes the posting is: English only, English + Other, or
# Other only. Sina's third classified column, and it arrived the same way the other two
# did -- as a filter he asked to be turned into a choice he makes in the table:
# "میتونی یک ستون ها اضافه کنی که بشه انتخاب کرد فقط English و English + Other Language ...
# مثل فایل Excel".
#
# THERE IS NO LANGUAGE COLUMN ANY MORE. It showed what the posting was WRITTEN in, and Sina
# removed it the moment this one existed: "وقتی ستونی English? هست دیگه Language رو پاک کن".
# The data is still on every row (`detected_language`, `needs_translation`) and still drives
# silent_about_english -- only the column went, so nothing about a verdict changed.
ENGLISH_COLUMN = 7
# What level the posting is pitched at, as a word: Intern, Junior, Mid, Senior, Lead, or
# Unspecified when it says nothing.
#
# IT IS A COLUMN RATHER THAN A FILTER, AND THAT IS THE POINT.
#
# The Level used to be a filter and nothing else: it picked a prompt, the prompt's rule 4
# deleted whatever did not match, and no row ever carried what level it actually was.
# Measured on the real Netherlands run, rule 4 fired on 19 of 90 flags. Sina's instruction
# after seeing that: "نباید Filter کنه باید اون هارو دسته بندی کنه ... اول بر اساس Seniority
# Groupby میکنی و بعد بر اساس Type و دیگه هیچی نباید حذف بشه" -- classify, do not delete,
# and let him choose here the way he chooses the Type.
#
# So rule 4 now reports instead of dropping (the `seniority` field of the screening schema),
# `rules.seniority_of` falls back to the title where Claude has not seen the row, and this
# column gets the same Excel-style filter button the Type column has.
DETAILS_COLUMN = 8
MATCH_COLUMN = 9
# Part two of Claude, over the survivors only: the listing read against Sina's own résumé,
# giving apply / check / skip with one sentence saying why. It deletes nothing by itself --
# a "skip" is flagged for the review dialog like any other verdict, because the cost of being
# wrong here is a job Sina never sees. The sentence is the tooltip; what fits and what is
# missing are on the Match % cell beside it.
WORTH_COLUMN = 10
# Which of the searched job titles found this listing. Sina filters on it -- "only the Data
# Analyst ones" -- and it exists because the Filter no longer deletes a listing for being found
# under a neighbouring title; see column_filter.py for why that changed.
#
# The similarity SCORE has no column of its own: he asked for it to go ("اون ستون Similarity رو
# هم پاک کن"). It is still read off every row to ORDER the table, which is the job he gave it
# in the first place -- closest title first, in every view.
FOUND_AS_COLUMN = 11
APPLY_COLUMN = 12
REMOVE_COLUMN = 13
ROW_HEIGHT = 44
# Every table item in this app is created fresh and then made read-only, so the target
# flag set is always the same value. Computing it once matters more than it looks:
# `~Qt.ItemIsEditable` is not a cheap C bit-flip, it goes through Python's `enum`
# module (__invert__ -> _decompose -> a list comprehension over every flag), and
# profiling a 1,000-row render showed those calls costing 508 ms of a 1,678 ms render.
# Verified equivalent: the value compares equal to the per-item
# `flags() & ~Qt.ItemIsEditable`, with ItemIsEditable cleared and every other flag kept.
#
# Built LAZILY, on first use, and NOT at import time. Constructing any Qt widget or
# QGuiApplication-dependent object before a QApplication exists is undefined behaviour:
# doing this at module level crashed the packaged .exe instantly on launch with
# 0xC0000409 (STATUS_STACK_BUFFER_OVERRUN). It survived every unit test only because the
# test harness builds a QApplication *before* importing the UI modules, while the frozen
# app imports them first -- a bug that unit tests structurally could not have caught.
_NON_EDITABLE_FLAGS = None


def _non_editable_flags():
    global _NON_EDITABLE_FLAGS
    if _NON_EDITABLE_FLAGS is None:
        _NON_EDITABLE_FLAGS = QTableWidgetItem().flags() & ~Qt.ItemIsEditable
    return _NON_EDITABLE_FLAGS

# One shared cursor for every row button rather than a fresh QCursor per button per row.
# Lazy for the same reason as _non_editable_flags above: a QCursor built at import time,
# before QApplication exists, is what crashed the packaged .exe on startup.
_HAND_CURSOR = None


def _hand_cursor():
    global _HAND_CURSOR
    if _HAND_CURSOR is None:
        _HAND_CURSOR = QCursor(Qt.PointingHandCursor)
    return _HAND_CURSOR


def _match_color(match_percent: int) -> str:
    """80-100 -> strong green, 50-79 -> yellow, below 50 -> red."""
    if match_percent >= 80:
        return '#1b7a3d'
    if match_percent >= 50:
        return '#e0b400'
    return '#b3261e'


class CheckableFilterButton(QToolButton):
    """A dropdown button with a checklist inside -- pick topics from a fixed list
    instead of typing free text."""

    selectionChanged = Signal()

    def __init__(self, label: str, options: list[str], parent=None):
        super().__init__(parent)
        self._label = label
        self._checkboxes: list[QCheckBox] = []

        self.setPopupMode(QToolButton.InstantPopup)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        menu = QMenu(self)
        for option in options:
            checkbox = QCheckBox(option, menu)
            checkbox.toggled.connect(self._on_toggled)
            action = QWidgetAction(menu)
            action.setDefaultWidget(checkbox)
            menu.addAction(action)
            self._checkboxes.append(checkbox)
        self.setMenu(menu)

        self._update_text()

    def _on_toggled(self):
        self._update_text()
        self.selectionChanged.emit()

    def _update_text(self):
        count = len(self.selected())
        self.setText(f"{self._label} ({count}) ▾" if count else f"{self._label} ▾")

    def selected(self) -> list[str]:
        return [cb.text().lower() for cb in self._checkboxes if cb.isChecked()]

    def clear_selection(self):
        for cb in self._checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._update_text()


class JobsPage(QWidget):
    apply_requested = Signal(dict)
    remove_requested = Signal(str)
    filter_requested = Signal()
    health_check_requested = Signal()
    clear_all_requested = Signal()
    cancel_search_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_jobs: list[dict] = []  # everything that's saved, unfiltered
        self.jobs: list[dict] = []      # what's currently rendered (after the display filter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        self.status_label = QLabel("No search run yet.")
        self.status_label.setObjectName("HintLabel")
        top_row.addWidget(self.status_label)
        top_row.addStretch(1)
        self.new_search_btn = QPushButton("New Search")
        self.new_search_btn.setObjectName("PrimaryButton")
        top_row.addWidget(self.new_search_btn)
        self.filter_btn = QPushButton("Filter")
        self.filter_btn.setToolTip("Re-check every saved listing against the current filters (Remote rule, seniority, etc.)")
        self.filter_btn.clicked.connect(self.filter_requested.emit)
        top_row.addWidget(self.filter_btn)
        self.health_check_btn = QPushButton("Health Check")
        self.health_check_btn.setToolTip(
            "Check every job site, API and saved job-link pattern against the real web. "
            "Costs nothing -- no Apify credit is spent -- and reports anything that has "
            "broken since the last time, so a search is not paid for to find out.")
        self.health_check_btn.clicked.connect(self.health_check_requested.emit)
        top_row.addWidget(self.health_check_btn)
        self.clear_search_btn = QPushButton("Clear Search")
        self.clear_search_btn.setObjectName("DangerButton")
        self.clear_search_btn.clicked.connect(self._confirm_clear_all)
        top_row.addWidget(self.clear_search_btn)
        layout.addLayout(top_row)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_row.addWidget(self.progress_bar, stretch=1)
        self.cancel_search_btn = QPushButton("Cancel Search")
        self.cancel_search_btn.setVisible(False)
        self.cancel_search_btn.setObjectName("DangerButton")
        self.cancel_search_btn.setToolTip("Stop the search now and show whatever listings were already found.")
        self.cancel_search_btn.clicked.connect(self.cancel_search_requested.emit)
        progress_row.addWidget(self.cancel_search_btn)
        layout.addLayout(progress_row)

        display_filter_row = QHBoxLayout()
        display_filter_row.setSpacing(8)

        self.include_filter = CheckableFilterButton("Show only", pipeline.TOPIC_KEYWORDS)
        self.include_filter.selectionChanged.connect(self._apply_display_filter)
        display_filter_row.addWidget(self.include_filter)

        reset_display_filter_btn = QPushButton("Reset")
        reset_display_filter_btn.clicked.connect(self._clear_display_filter)
        display_filter_row.addWidget(reset_display_filter_btn)
        display_filter_row.addStretch(1)
        layout.addLayout(display_filter_row)

        # One filter per column, Excel-style: the values actually present, with counts, and
        # you tick the ones you want. See column_filter.py -- these replaced a similarity
        # threshold that DELETED listings on a score that turned out not to track reality.
        #
        # `reader` is how a value is read off a listing, so the filter and the table cell can
        # never disagree about what a row's Country or Type is.
        self._column_filters = []
        column_filter_row = QHBoxLayout()
        column_filter_row.setSpacing(8)
        for label, reader in (
                ('Country', lambda job: pipeline.text_of(job.get('country')) or 'Unknown'),
                ('Sponsorship', lambda job: (pipeline.text_of(job.get('sponsorship_visa'))
                                             or 'Unknown')),
                ('Seniority', lambda job: (pipeline.text_of(job.get('Seniority'))
                                          or pipeline.seniority_of(job))),
                ('Type', lambda job: pipeline.display_category(job) or 'Unknown'),
                # The column he asked for: tick "English only" and nothing else shows.
                # Read the same way the cell reads it, through the classifier, so the
                # list of values and the badges can never disagree.
                ('English', lambda job: (pipeline.text_of(job.get('English'))
                                        or pipeline.english_requirement_of(job))),
                ('Found as', lambda job: (pipeline.text_of(job.get('field_matched_as'))
                                          or 'the title you searched')),
        ):
            button = ColumnFilterButton(label)
            button.changed.connect(self._apply_display_filter)
            button._reader = reader          # noqa: SLF001 -- read back in _apply_display_filter
            self._column_filters.append(button)
            column_filter_row.addWidget(button)
        reset_columns_btn = QPushButton("Show all values")
        reset_columns_btn.clicked.connect(self._clear_column_filters)
        column_filter_row.addWidget(reset_columns_btn)
        column_filter_row.addStretch(1)
        layout.addLayout(column_filter_row)

        hint = QLabel(
            "Click anywhere on a row to open the listing · use Apply to track an application. "
            "The filters above only change what's displayed here — they delete nothing. "
            "Rows are ordered by how close their title is to the one you searched."
        )
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setCursor(QCursor(Qt.PointingHandCursor))
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(SPONSORSHIP_COLUMN, 175)
        # By name. This said 5, which was Type before Seniority was inserted ahead of it --
        # the second hard-coded index in this file that the new column moved, and exactly
        # what M-9 warns about.
        self.table.setColumnWidth(SENIORITY_COLUMN, 120)
        self.table.setColumnWidth(TYPE_COLUMN, 150)  # fits a "... Startup" suffix
        self.table.setColumnWidth(ENGLISH_COLUMN, 130)  # fits "English + Other"
        self.table.setColumnWidth(MATCH_COLUMN, 90)
        self.table.setColumnWidth(WORTH_COLUMN, 96)
        self.table.setColumnWidth(FOUND_AS_COLUMN, 190)
        self.table.setColumnWidth(APPLY_COLUMN, 110)
        self.table.setColumnWidth(REMOVE_COLUMN, 110)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        # Apply and Remove are painted, not built. The delegate draws only the rows on screen,
        # which is what took a 20,000-row render from 193 seconds to under two.
        #
        # Mouse tracking is on so the buttons can light up under the pointer: without it Qt
        # sends no MouseMove to the delegate and the two cells where a click has consequences
        # would be the only ones in the table that never react.
        self.table.setMouseTracking(True)
        self._apply_delegate = RowButtonDelegate('Apply', 'apply', self.table)
        self._apply_delegate.clicked.connect(self._on_apply_clicked)
        self.table.setItemDelegateForColumn(APPLY_COLUMN, self._apply_delegate)
        self._remove_delegate = RowButtonDelegate('Remove', 'remove', self.table)
        self._remove_delegate.clicked.connect(self._on_remove_clicked)
        self.table.setItemDelegateForColumn(REMOVE_COLUMN, self._remove_delegate)

        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

    def set_progress(self, message: str, done: int, total: int):
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done)
        self.status_label.setText(message)

    def set_searching(self, is_searching: bool, cancellable: bool = False):
        self.new_search_btn.setEnabled(not is_searching)
        self.filter_btn.setEnabled(not is_searching)
        self.health_check_btn.setEnabled(not is_searching)
        self.clear_search_btn.setEnabled(not is_searching)
        # Only a real Search (not Filter) can be cancelled mid-run -- FilterWorker has
        # no cancel mechanism, so the button only shows when the caller opts in.
        self.cancel_search_btn.setVisible(is_searching and cancellable)
        if not is_searching:
            self.progress_bar.setVisible(False)

    def _confirm_clear_all(self):
        dialog = TypeToConfirmDialog(
            "Clear My Search",
            "Clear all saved job listings",
            f"This permanently deletes all {len(self.all_jobs)} saved job listing(s). "
            "This cannot be undone.",
            self,
        )
        if dialog.exec() == TypeToConfirmDialog.Accepted:
            self.clear_all_requested.emit()

    def show_jobs(self, jobs: list[dict]):
        self.all_jobs = jobs
        self._apply_display_filter()

    def _clear_display_filter(self):
        self.include_filter.clear_selection()
        self._apply_display_filter()

    def _clear_column_filters(self):
        for button in self._column_filters:
            button.clear_selection()
        self._apply_display_filter()

    def _offer_column_values(self):
        """Give each column filter the values actually present, with counts, most common first.

        Read off `all_jobs`, not off what is currently shown: offering only the values that
        survive the current filters would make a choice unreachable the moment it was
        deselected -- tick Germany, and Netherlands disappears from the list that would let
        you tick it back.
        """
        for button in self._column_filters:
            counted: dict = {}
            for job in self.all_jobs:
                try:
                    value = str(button._reader(job))       # noqa: SLF001
                except Exception:
                    value = 'Unknown'
                counted[value] = counted.get(value, 0) + 1
            button.offer(sorted(counted.items(), key=lambda kv: (-kv[1], kv[0])))

    def _apply_display_filter(self):
        include_terms = self.include_filter.selected()
        self._offer_column_values()

        def matches(job: dict) -> bool:
            # text_of, not `or ''`: a NaN field is truthy and would put the literal
            # text "nan" into the searchable haystack, so a filter term like "an"
            # could match a listing with no description at all.
            haystack = (pipeline.text_of(job.get('title')) + ' '
                        + pipeline.text_of(job.get('description'))).lower()
            if include_terms and not any(term in haystack for term in include_terms):
                return False
            # ANDed with the term filter and with each other, which is what "only the ones
            # with sponsorship AND in the Netherlands" means.
            for button in self._column_filters:
                try:
                    value = str(button._reader(job))       # noqa: SLF001
                except Exception:
                    value = 'Unknown'
                if not button.keeps(value):
                    return False
            return True

        filtered = [j for j in self.all_jobs if matches(j)]
        # Closest title first, and that is Sina's rule for every view: "هرچی گفتم نشون بده
        # حتما Order اش بر اساس بیشترین شباهت باشه". A listing with no score sorts as 100,
        # because it was kept for saying nothing rather than for being a distant match.
        filtered.sort(key=lambda job: -_similarity_of(job))
        self._render(filtered)

        total = len(self.all_jobs)
        shown = len(filtered)
        narrowed = bool(include_terms) or any(b.selected() for b in self._column_filters)
        if narrowed:
            self.status_label.setText(
                f"{shown} of {total} listings shown — the rest are hidden, not deleted.")
        else:
            self.status_label.setText(f"{total} listing(s).")

    # Rendering cost, measured: about 6 seconds for 2,500 rows, which a search can now
    # produce since the direct APIs were paginated. Roughly ten objects go in per row --
    # eight items plus two cell widgets and their layout wrappers -- and that is where the
    # time goes.
    #
    # Suspending painting around the fill was tried and measured at 1.00x: no difference
    # at all, so it was removed rather than left in looking like an optimisation. Two
    # earlier readings suggested a widget leak and a large speedup; both were measurement
    # artifacts -- Qt defers widget deletion, so counting or timing without first flushing
    # DeferredDelete events sees the previous render still in memory. With the flush, the
    # widget count is flat across renders and nothing leaks.
    #
    # Making this genuinely fast needs the per-row buttons to stop being real widgets,
    # which is a redesign rather than a tweak.
    def _render(self, jobs: list[dict]):
        self.jobs = jobs
        scroll_position = self.table.verticalScrollBar().value()
        self.table.setRowCount(0)
        self.table.setRowCount(len(jobs))
        for row_idx, job in enumerate(jobs):
            self._set_item(row_idx, 0, str(row_idx + 1))
            self._set_item(row_idx, 1, pipeline.text_of(job.get('title')))
            self._set_item(row_idx, 2, pipeline.text_of(job.get('company')))
            self._set_item(row_idx, 3, pipeline.text_of(job.get('country')))
            self._render_sponsorship_cell(row_idx, job)
            self._render_seniority_cell(row_idx, job)
            self._render_category_cell(row_idx, job)
            self._render_english_cell(row_idx, job)
            self._render_details_cells(row_idx, job)
            self._render_match_cell(row_idx, job)
            self._render_worth_cell(row_idx, job)
            self._set_item(row_idx, FOUND_AS_COLUMN,
                           pipeline.text_of(job.get('field_matched_as'))
                           or 'the title you searched')
            self._render_row_buttons(row_idx, job)
            self.table.setRowHeight(row_idx, ROW_HEIGHT)

        self.table.verticalScrollBar().setValue(scroll_position)

    def _render_sponsorship_cell(self, row_idx, job):
        """The Sponsorship Visa badge.

        text_of, not `or 'Unknown'`. Real crash this fixes: a NaN sponsorship_visa is
        TRUTHY, so `or` let the float through to QTableWidgetItem, which raised
        OverflowError ("Value -9223372036854775808 exceeds limits of type int") -- and
        because that happens mid-render, ONE bad row blanked the entire Jobs page.
        """
        sponsorship = pipeline.text_of(job.get('sponsorship_visa')) or 'Unknown'
        badge = QTableWidgetItem(sponsorship)
        badge.setFlags(_non_editable_flags())
        badge.setForeground(QColor('#ffffff'))
        badge.setBackground(QColor(SPONSORSHIP_BADGE_COLORS.get(sponsorship,
                                                                FALLBACK_BADGE_COLOR)))
        self.table.setItem(row_idx, SPONSORSHIP_COLUMN, badge)

    def _render_category_cell(self, row_idx, job):
        """The Type badge.

        The category used for the colour stays the clean base value ('Full-Time', not
        'Full-Time Startup'), so CATEGORY_BADGE_COLORS and CATEGORY_ORDER sorting are
        unaffected -- the "... Startup" suffix is a display-time addition only.
        """
        category = pipeline.text_of(job.get('Category')) or 'Other'
        badge = QTableWidgetItem(pipeline.display_category(job))
        badge.setFlags(_non_editable_flags())
        badge.setForeground(QColor('#ffffff'))
        badge.setBackground(QColor(CATEGORY_BADGE_COLORS.get(category, FALLBACK_BADGE_COLOR)))
        # By name, not by the literal 5 it used to be. Inserting Seniority before Type moved
        # it, and a hard-coded index is how M-9 happens -- one column added, every later cell
        # silently one place out.
        self.table.setItem(row_idx, TYPE_COLUMN, badge)

    def _render_seniority_cell(self, row_idx, job):
        """The Seniority badge: Intern, Junior, Mid, Senior, Lead, or Unspecified.

        A plain QTableWidgetItem, like Type and Sponsorship, and deliberately not a widget:
        the render is about ten objects per row already and 6 seconds for 2,500 rows, and
        the per-row buttons are the only widgets that earn their cost.

        seniority_of prefers Claude's own answer (the `seniority` field that replaced rule 4)
        and falls back to the title where Claude never saw the row. Read through it rather
        than off job['Seniority'] so a row banked before this column existed still shows a
        word instead of a blank.
        """
        level = pipeline.text_of(job.get('Seniority')) or pipeline.seniority_of(job)
        badge = QTableWidgetItem(level)
        badge.setFlags(_non_editable_flags())
        badge.setForeground(QColor('#ffffff'))
        badge.setBackground(QColor(SENIORITY_BADGE_COLORS.get(level, FALLBACK_BADGE_COLOR)))
        self.table.setItem(row_idx, SENIORITY_COLUMN, badge)

    def _render_english_cell(self, row_idx, job):
        """The English? badge: English only, English + Other, or Other only.

        Read through english_requirement_of rather than off job['English'], for the same
        reason the Seniority cell is: a listing banked before this column existed carries no
        such key, and a blank cell in a column he filters on would read as "no answer" when
        the answer is there to be had from the text.

        The tooltip carries the sentence behind the badge, because "English only" is the
        answer for a posting that never mentions language at all -- which is most of them --
        and that is worth saying somewhere rather than leaving him to infer it.
        """
        need = (pipeline.text_of(job.get('English'))
                or pipeline.english_requirement_of(job))
        badge = QTableWidgetItem(need)
        badge.setFlags(_non_editable_flags())
        badge.setForeground(QColor('#ffffff'))
        badge.setBackground(QColor(ENGLISH_BADGE_COLORS.get(need, FALLBACK_BADGE_COLOR)))
        badge.setToolTip(_ENGLISH_TOOLTIPS.get(need, ''))
        self.table.setItem(row_idx, ENGLISH_COLUMN, badge)

    def _render_details_cells(self, row_idx, job):
        """The platform / location / date line.

        pipeline.text_of, not `or ''`. Two rounds of bug here: `.get('platform', '')` only
        defaulted when the KEY was missing, so an explicit None crashed with "'NoneType'
        object has no attribute 'capitalize'". `or ''` fixed that but NOT pandas' NaN, which
        is truthy -- it sails through and raises the same AttributeError for a float, while
        location and posted_date rendered a literal 'nan' to the user.
        """
        details = (
            f"{pipeline.text_of(job.get('platform')).capitalize()} · "
            f"{pipeline.text_of(job.get('location'))} · "
            f"{pipeline.text_of(job.get('posted_date'))}"
        )
        self._set_item(row_idx, DETAILS_COLUMN, details)

    def _match_percent_of(self, job):
        """The one score, whichever module wrote it -- or None.

        Three modules screen a Filter run and each records its score under its own key, so
        the column reads all three. Without this a thesis and an internship arrived with an
        em dash where their score should be: the row had been judged and the number thrown
        away on the way to the screen.

        `is not None` alone is not enough -- a NaN match passes it and renders as "nan%"
        with a red badge. Same NaN-truthiness family as the details line above.
        """
        match_percent = next(
            (job.get(key) for key in ('claude_match', 'thesis_claude_match',
                                      'internship_claude_match')
             if job.get(key) is not None), None)
        if match_percent is not None and match_percent != match_percent:
            return None
        return match_percent

    def _render_match_cell(self, row_idx, job):
        """The Match %, with what fits and what is missing as its tooltip."""
        match_percent = self._match_percent_of(job)
        item = QTableWidgetItem(f"{match_percent}%" if match_percent is not None else "—")
        item.setFlags(_non_editable_flags())
        item.setTextAlignment(Qt.AlignCenter)
        if match_percent is not None:
            item.setForeground(QColor('#ffffff'))
            item.setBackground(QColor(_match_color(match_percent)))
        # The Match % is read against the résumé Sina uploaded; what fits and what is
        # missing are the reasons behind the number, so they sit on it as its tooltip.
        strengths = pipeline.text_of(job.get('resume_strengths')).strip()
        gaps = pipeline.text_of(job.get('resume_gaps')).strip()
        if strengths or gaps:
            item.setToolTip("\n\n".join(
                part for part in (("Fits your résumé: " + strengths) if strengths else '',
                                  ("Missing from your résumé: " + gaps) if gaps else '')
                if part))
        self.table.setItem(row_idx, MATCH_COLUMN, item)

    def _render_worth_cell(self, row_idx, job):
        """"Worth it?" -- apply, check or skip -- with Claude's one-line reason."""
        worth = pipeline.text_of(job.get('apply_verdict')).strip().lower()
        note = pipeline.text_of(job.get('apply_note')).strip()
        item = QTableWidgetItem(_WORTH_LABELS.get(worth, "—"))
        item.setFlags(_non_editable_flags())
        item.setTextAlignment(Qt.AlignCenter)
        if worth in _WORTH_COLORS:
            item.setForeground(QColor('#ffffff'))
            item.setBackground(QColor(_WORTH_COLORS[worth]))
        if note:
            item.setToolTip(note)
        self.table.setItem(row_idx, WORTH_COLUMN, item)

    def _render_row_buttons(self, row_idx, job):
        """The two cells Apply and Remove are PAINTED into -- see row_button_delegate.

        There is deliberately almost nothing here. This used to build two QPushButtons, each
        in a QWidget wrapper with a layout and a connected signal, and that was 75% of the
        entire render: 193 seconds for the 20,000 rows Sina reported the app hanging on. The
        delegate draws the same buttons for the twenty rows actually on screen, which took the
        same 20,000 rows to 1.67 seconds.
        """
        self._set_item(row_idx, APPLY_COLUMN, '')
        self._set_item(row_idx, REMOVE_COLUMN, '')

    def _on_apply_clicked(self, row_idx: int) -> None:
        """Apply, from the painted button. The row is looked up now rather than captured.

        The old buttons each closed over their own job dict, which meant 20,000 lambdas each
        holding a row. The delegate reports a row NUMBER, and the list it indexes is the one
        currently displayed -- so a stale row cannot be applied to.
        """
        if 0 <= row_idx < len(self.jobs):
            self.apply_requested.emit(self.jobs[row_idx])

    def _on_remove_clicked(self, row_idx: int) -> None:
        if 0 <= row_idx < len(self.jobs):
            self._confirm_remove(self.jobs[row_idx])

    def _set_item(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(_non_editable_flags())
        self.table.setItem(row, col, item)

    def _confirm_remove(self, job: dict):
        job_id = job.get('id')
        if job_id:
            self.remove_requested.emit(job_id)

    def _on_cell_clicked(self, row, column):
        if column in (APPLY_COLUMN, REMOVE_COLUMN):
            return  # these columns have their own buttons
        if row < 0 or row >= len(self.jobs):
            return
        url = self.jobs[row].get('url')
        if url:
            webbrowser.open(url)
