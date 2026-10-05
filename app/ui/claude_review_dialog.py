from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

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


class ClaudeReviewDialog(QDialog):
    """Shows every listing Claude flagged in its final pass, with its reason, and asks
    the user to confirm before anything is actually deleted."""

    def __init__(self, flagged_items: list[dict], parent=None):
        super().__init__(parent)
        self.flagged_items = flagged_items  # [{'job': dict, 'reason': str}, ...]
        self.keep_ids: set[str] = set()

        self.setWindowTitle("Claude flagged some listings")
        self.setMinimumSize(720, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel(f"Claude flagged {len(flagged_items)} listing(s) for review")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(
            "These already passed the keyword filters, but Claude thinks they should be "
            "dropped for the reason shown. Type the row numbers you want to KEEP anyway "
            "(comma-separated), or leave blank to remove all of them."
        )
        hint.setWordWrap(True)
        hint.setObjectName("HintLabel")
        layout.addWidget(hint)

        self.table = QTableWidget(len(flagged_items), 4)
        self.table.setHorizontalHeaderLabels(["#", "Title", "Company", "Claude's reason"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(2, 140)

        for row_idx, item in enumerate(flagged_items):
            job = item['job']
            self._set_item(row_idx, 0, str(row_idx + 1))
            self._set_item(row_idx, 1, job.get('title') or '')
            self._set_item(row_idx, 2, job.get('company') or '')
            self._set_item(row_idx, 3, item.get('reason') or '')
        layout.addWidget(self.table, stretch=1)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Keep numbers:"))
        self.keep_input = QLineEdit()
        self.keep_input.setPlaceholderText("e.g. 1, 4, 7 — leave blank to remove all")
        input_row.addWidget(self.keep_input, stretch=1)
        layout.addLayout(input_row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancel (keep everyone)")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = QPushButton("Remove Flagged")
        confirm_btn.setObjectName("PrimaryButton")
        confirm_btn.clicked.connect(self._on_confirm)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(confirm_btn)
        layout.addLayout(buttons)

    def _set_item(self, row, col, text):
        item = QTableWidgetItem(text)
        item.setFlags(_non_editable_flags())
        self.table.setItem(row, col, item)

    def _on_confirm(self):
        keep_numbers = set()
        text = self.keep_input.text().strip()
        if text:
            for part in text.split(','):
                part = part.strip()
                if part.isdigit():
                    keep_numbers.add(int(part))

        for idx, item in enumerate(self.flagged_items, start=1):
            if idx in keep_numbers:
                job_id = item['job'].get('id')
                if job_id:
                    self.keep_ids.add(job_id)

        self.accept()
