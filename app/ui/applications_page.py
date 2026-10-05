from __future__ import annotations

import webbrowser
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app import pipeline, storage
from app.storage import STATUS_CHOICES, STATUS_COLORS
from app.styles import (
    CATEGORY_BADGE_COLORS, FALLBACK_BADGE_COLOR, SENIORITY_BADGE_COLORS,
    SPONSORSHIP_BADGE_COLORS,
)
from app.ui.confirm_dialog import TypeToConfirmDialog
from app.ui.manual_application_dialog import ManualApplicationDialog

# Seniority before Type, the same order as the Jobs table and the same order he groups by.
COLUMNS = [
    "#", "Title", "Company", "Country", "Sponsorship Visa", "Seniority", "Type",
    "Days Ago", "Applied On", "Documents", "Status", "Remove",
]
SPONSORSHIP_COLUMN = 4
SENIORITY_COLUMN = 5
# What kind of work this was -- Thesis, Internship, Part-Time, PhD, Full-Time. The record
# has carried it since the first application was ever logged (`'category'` in
# storage.add_application), and nothing showed it: the list said what he applied to but not
# what sort of thing it was, so a list of forty applications could not answer "how many of
# these were internships?". Placed where the Jobs page puts the same badge, with the same
# colours, so the two tables read as one table.
TYPE_COLUMN = 6
APPLIED_AGO_COLUMN = 7
APPLIED_ON_COLUMN = 8
DOCUMENTS_COLUMN = 9
STATUS_COLUMN = 10
REMOVE_COLUMN = 11
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


def _parse_apply_date(apply_date: str | None):
    if not apply_date:
        return None
    for fmt in ('%d/%m/%Y', '%d/%m/%Y %H:%M'):
        try:
            return datetime.strptime(apply_date, fmt).date()
        except ValueError:
            continue
    return None


def _clean_apply_date_text(apply_date: str | None) -> str:
    parsed = _parse_apply_date(apply_date)
    return parsed.strftime('%d/%m/%Y') if parsed else (apply_date or '')


def _days_ago_text(apply_date: str | None) -> str:
    applied = _parse_apply_date(apply_date)
    if applied is None:
        return ''
    days = (datetime.now().date() - applied).days
    if days <= 0:
        return 'Today'
    if days == 1:
        return '1 day ago'
    return f'{days} days ago'


class ApplicationsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        title = QLabel("My Applications")
        title.setObjectName("SectionTitle")
        top_row.addWidget(title)
        top_row.addStretch(1)
        # For applications made outside RoleHound -- on LinkedIn, or a company's own site.
        # Without this the list was a record of what the app found, not of what Sina has
        # actually applied to, and only the second one is worth keeping.
        self.add_by_hand_btn = QPushButton("Add by hand")
        self.add_by_hand_btn.setToolTip("Record a job you applied to somewhere else.")
        self.add_by_hand_btn.clicked.connect(self._add_by_hand)
        top_row.addWidget(self.add_by_hand_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.reload)
        top_row.addWidget(refresh_btn)
        self.clear_applications_btn = QPushButton("Clear My Applications")
        self.clear_applications_btn.setObjectName("DangerButton")
        self.clear_applications_btn.clicked.connect(self._confirm_clear_all)
        top_row.addWidget(self.clear_applications_btn)
        layout.addLayout(top_row)

        self.count_label = QLabel("0 applications.")
        self.count_label.setObjectName("HintLabel")
        layout.addWidget(self.count_label)

        hint = QLabel("Click anywhere on a row to open the original listing. "
                      "“Add by hand” records a job you applied to somewhere else.")
        hint.setObjectName("HintLabel")
        layout.addWidget(hint)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setCursor(QCursor(Qt.PointingHandCursor))
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(SPONSORSHIP_COLUMN, 175)
        self.table.setColumnWidth(SENIORITY_COLUMN, 110)
        self.table.setColumnWidth(TYPE_COLUMN, 120)
        self.table.setColumnWidth(APPLIED_AGO_COLUMN, 110)
        self.table.setColumnWidth(APPLIED_ON_COLUMN, 110)
        self.table.setColumnWidth(DOCUMENTS_COLUMN, 110)
        self.table.setColumnWidth(STATUS_COLUMN, 150)
        self.table.setColumnWidth(REMOVE_COLUMN, 110)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

        self.applications: list[dict] = []
        self.reload()

    def reload(self):
        scroll_position = self.table.verticalScrollBar().value()
        self.applications = storage.load_applications()
        self.table.setRowCount(len(self.applications))
        count = len(self.applications)
        self.count_label.setText(f"{count} application{'s' if count != 1 else ''}.")

        for row_idx, record in enumerate(self.applications):
            self._set_item(row_idx, 0, str(row_idx + 1))
            self._set_item(row_idx, 1, pipeline.text_of(record.get('title')))
            self._set_item(row_idx, 2, pipeline.text_of(record.get('company')))
            self._set_item(row_idx, 3, pipeline.text_of(record.get('country')))

            # text_of for the same reason as the Jobs page: a NaN here is truthy
            # and reaches QTableWidgetItem as a float, raising OverflowError.
            sponsorship = pipeline.text_of(record.get('sponsorship_visa')) or 'Unknown'
            sponsorship_badge = QTableWidgetItem(sponsorship)
            sponsorship_badge.setFlags(_non_editable_flags())
            sponsorship_badge.setForeground(QColor('#ffffff'))
            sponsorship_badge.setBackground(QColor(SPONSORSHIP_BADGE_COLORS.get(sponsorship, FALLBACK_BADGE_COLOR)))
            self.table.setItem(row_idx, SPONSORSHIP_COLUMN, sponsorship_badge)

            # 'category', lower case: the job dict spells it 'Category' and the record
            # spells it 'category' -- see storage.add_application, which does the renaming.
            # Reading the wrong one here would show every row as 'Other' and look like a
            # pipeline fault rather than a typo.
            # 'seniority' lower case, like 'category': add_application does the renaming.
            level = pipeline.text_of(record.get('seniority')) or 'Unspecified'
            level_badge = QTableWidgetItem(level)
            level_badge.setFlags(_non_editable_flags())
            level_badge.setForeground(QColor('#ffffff'))
            level_badge.setBackground(
                QColor(SENIORITY_BADGE_COLORS.get(level, FALLBACK_BADGE_COLOR)))
            self.table.setItem(row_idx, SENIORITY_COLUMN, level_badge)

            category = pipeline.text_of(record.get('category')) or 'Other'
            category_badge = QTableWidgetItem(category)
            category_badge.setFlags(_non_editable_flags())
            category_badge.setForeground(QColor('#ffffff'))
            category_badge.setBackground(
                QColor(CATEGORY_BADGE_COLORS.get(category, FALLBACK_BADGE_COLOR)))
            self.table.setItem(row_idx, TYPE_COLUMN, category_badge)

            self._set_item(row_idx, APPLIED_AGO_COLUMN, _days_ago_text(record.get('apply_date')))
            self._set_item(row_idx, APPLIED_ON_COLUMN, _clean_apply_date_text(record.get('apply_date')))

            doc_count = len(record.get('documents') or [])
            docs_btn = QPushButton("Download")
            docs_btn.setObjectName("RowDownloadButton")
            docs_btn.setCursor(_hand_cursor())
            docs_btn.setToolTip(f"Download Job Description.txt + {doc_count} attached document(s) as a .zip")
            docs_btn.setFixedHeight(ROW_HEIGHT - 10)
            docs_btn.clicked.connect(lambda _checked=False, r=record: self._download_documents(r))
            self.table.setCellWidget(row_idx, DOCUMENTS_COLUMN, self._wrap(docs_btn))

            # `or`, not a .get() default: the default only fires when the KEY is
            # MISSING, so a record whose status is explicitly None rendered a blank,
            # unlabelled button. Exactly the same shape as the Jobs page's `platform`
            # bug, which has now been fixed twice -- this was its third home, and it
            # failed quietly (QPushButton(None) reads as a parent argument) rather than
            # crashing, which is why two earlier audits walked past it.
            current = pipeline.text_of(record.get('status')) or 'Processing'
            status_btn = QPushButton(current)
            status_btn.setCursor(_hand_cursor())
            status_btn.setFixedHeight(ROW_HEIGHT - 10)
            self._paint_status(status_btn, current)

            status_menu = QMenu(status_btn)
            for choice in STATUS_CHOICES:
                action = status_menu.addAction(choice)
                action.triggered.connect(
                    lambda _checked=False, c=choice, r=record, b=status_btn: self._on_status_changed(r, c, b)
                )
            status_btn.setMenu(status_menu)

            self.table.setCellWidget(row_idx, STATUS_COLUMN, self._wrap(status_btn))

            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("RowRemoveButton")
            remove_btn.setCursor(_hand_cursor())
            remove_btn.setFixedHeight(ROW_HEIGHT - 10)
            remove_btn.clicked.connect(lambda _checked=False, r=record: self._remove_application(r))
            self.table.setCellWidget(row_idx, REMOVE_COLUMN, self._wrap(remove_btn))

            self.table.setRowHeight(row_idx, ROW_HEIGHT)

        self.table.verticalScrollBar().setValue(scroll_position)

    @staticmethod
    def _wrap(widget: QWidget) -> QWidget:
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(widget)
        return cell

    def _set_item(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(_non_editable_flags())
        self.table.setItem(row, col, item)

    def _paint_status(self, button: QPushButton, status: str):
        color = STATUS_COLORS.get(status, '#888')
        button.setText(status)
        button.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: #10131c; font-weight: 700; "
            f"border: none; border-radius: 6px; padding: 4px 6px; }} "
            f"QPushButton::menu-indicator {{ width: 0px; }}"
        )

    def _on_status_changed(self, record: dict, new_status: str, button: QPushButton):
        record['status'] = new_status
        storage.update_application_status(record['id'], new_status)
        self._paint_status(button, new_status)

    def _add_by_hand(self):
        """Record an application made outside RoleHound.

        Goes through storage.add_application like every other one, so the row that appears
        is an ordinary row: the status menu, Download, Remove and the Excel export all work
        on it without being told where it came from.
        """
        dialog = ManualApplicationDialog(self)
        if dialog.exec() != ManualApplicationDialog.Accepted:
            return
        try:
            storage.add_application(dialog.job, dialog.documents, dialog.apply_date())
        except Exception as exc:                                       # noqa: BLE001
            # Copying attached documents touches the filesystem, and a file that has moved
            # or a folder that cannot be written must not lose what he just typed in
            # silently.
            QMessageBox.critical(self, "Could not add the application", str(exc))
            return
        self.reload()

    def _confirm_clear_all(self):
        dialog = TypeToConfirmDialog(
            "Clear My Applications",
            "Clear all logged applications",
            f"This permanently deletes all {len(self.applications)} logged application(s) "
            "and their attached documents. This cannot be undone.",
            self,
        )
        if dialog.exec() == TypeToConfirmDialog.Accepted:
            storage.clear_applications()
            self.reload()

    def _download_documents(self, record: dict):
        default_name = storage.default_zip_name(record)
        default_path = str(Path.home() / 'Downloads' / default_name)
        target_path, _ = QFileDialog.getSaveFileName(
            self, "Save documents", default_path, "Zip files (*.zip)"
        )
        if not target_path:
            return
        try:
            storage.build_documents_zip(record, target_path)
        except Exception as e:
            QMessageBox.critical(self, "Download failed", str(e))
            return
        QMessageBox.information(self, "Download complete", f"Saved to:\n{target_path}")

    def _remove_application(self, record: dict):
        storage.delete_application(record['id'])
        self.reload()

    def _on_cell_clicked(self, row, column):
        if column in (DOCUMENTS_COLUMN, STATUS_COLUMN, REMOVE_COLUMN):
            return  # these columns have their own interactive widgets
        if row < 0 or row >= len(self.applications):
            return
        url = self.applications[row].get('url')
        if url:
            webbrowser.open(url)
