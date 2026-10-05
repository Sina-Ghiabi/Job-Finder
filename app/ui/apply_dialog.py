from __future__ import annotations

import html

from app import pipeline

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout,
)


class ApplyDialog(QDialog):
    """Shown when the user clicks Apply on a job row: review the description and
    attach the documents (CV, cover letter, ...) used for this application."""

    def __init__(self, job: dict, parent=None):
        super().__init__(parent)
        self.job = job
        self.document_paths: list[str] = []

        self.setWindowTitle(f"Apply — {job.get('title') or 'Job'}")
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Every field is html-escaped before going into this rich-text label. Job
        # titles come straight from Google and the crawler's metadata.title with no
        # escaping, and QLabel's default AutoText format interprets them as HTML -- a
        # real title like 'C++ & Data <Scientist>' had its '<Scientist>' silently
        # swallowed as an unknown tag (verified). Qt rich text can also fetch remote
        # <img> URLs, which is worth closing off on scraped content.
        # pipeline.text_of before html.escape: escape() calls .replace() and raises
        # AttributeError on a float, so a NaN field would take the dialog down.
        header = QLabel(
            f"<b>{html.escape(pipeline.text_of(job.get('title')))}</b> — "
            f"{html.escape(pipeline.text_of(job.get('company')))} "
            f"({html.escape(pipeline.text_of(job.get('country')))})"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        desc_label = QLabel("Job description")
        desc_label.setObjectName("SectionTitle")
        layout.addWidget(desc_label)

        desc_view = QTextEdit()
        desc_view.setPlainText(pipeline.text_of(job.get('description')) or '(no description available)')
        desc_view.setReadOnly(True)
        layout.addWidget(desc_view, stretch=1)

        docs_label = QLabel("Attached documents")
        docs_label.setObjectName("SectionTitle")
        layout.addWidget(docs_label)

        self.docs_list = QListWidget()
        layout.addWidget(self.docs_list)

        docs_buttons = QHBoxLayout()
        add_btn = QPushButton("Add document…")
        add_btn.clicked.connect(self._add_documents)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        docs_buttons.addWidget(add_btn)
        docs_buttons.addWidget(remove_btn)
        docs_buttons.addStretch(1)
        layout.addLayout(docs_buttons)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        confirm_btn = QPushButton("Confirm Application")
        confirm_btn.setObjectName("ApplyButton")
        confirm_btn.clicked.connect(self._on_confirm)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(confirm_btn)
        layout.addLayout(buttons)

    def _add_documents(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select documents (CV, cover letter, ...)", "",
            "Documents (*.pdf *.doc *.docx *.txt);;All files (*.*)",
        )
        for p in paths:
            if p not in self.document_paths:
                self.document_paths.append(p)
                self.docs_list.addItem(p)

    def _remove_selected(self):
        for item in self.docs_list.selectedItems():
            path = item.text()
            if path in self.document_paths:
                self.document_paths.remove(path)
            self.docs_list.takeItem(self.docs_list.row(item))

    def _on_confirm(self):
        if not self.document_paths:
            reply = QMessageBox.question(
                self, "No documents attached",
                "You haven't attached any documents. Apply anyway?",
            )
            if reply != QMessageBox.Yes:
                return
        self.accept()
