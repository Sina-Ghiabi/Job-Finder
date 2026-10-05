from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


class TypeToConfirmDialog(QDialog):
    """A deliberately heavy-handed confirmation: the user must type the exact phrase
    before the destructive action's button becomes clickable."""

    def __init__(self, phrase: str, title: str, warning: str, parent=None):
        super().__init__(parent)
        self.phrase = phrase
        self.setWindowTitle(title)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        warning_label = QLabel(warning)
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("color: #ff8a94; font-weight: 600;")
        layout.addWidget(warning_label)

        instruction = QLabel(f"To confirm, type exactly: <b>{phrase}</b>")
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.input = QLineEdit()
        self.input.setPlaceholderText(phrase)
        self.input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.input)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("Delete Everything")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setStyleSheet(
            "QPushButton { background-color: #E74C3C; color: white; font-weight: 700; "
            "border: none; border-radius: 6px; padding: 8px 16px; } "
            "QPushButton:disabled { background-color: #4a2b2b; color: #8a6a6a; } "
            "QPushButton:hover:!disabled { background-color: #ff5a4a; }"
        )
        self.confirm_btn.clicked.connect(self.accept)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(self.confirm_btn)
        layout.addLayout(buttons)

    def _on_text_changed(self, text: str):
        self.confirm_btn.setEnabled(text == self.phrase)
