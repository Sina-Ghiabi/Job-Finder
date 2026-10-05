from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)


class PreflightProblemsDialog(QDialog):
    """The one window that reports anything RoleHound could not reach.

    Sina asked for exactly this shape: "بگه مشکل اینه و اگر میتونی حلش کنی حل کن اگر نه رد
    شو" -- name the problem, offer a live fix where one genuinely exists (a missing or
    expired API key), otherwise let him skip it. Later: "اگر هر مشکلی در URL یا API بود در
    اون پنجره بهم بگه و بگه چطوری درستش کنم با هوش مصنوعی" -- so it now covers URLs as well
    as APIs, and each problem carries Claude's own step-by-step fix advice (`fix_advice`,
    written by pipeline.explain_problems).

    Shown twice per search at most: before the run for what is knowable up front, so no
    credits are spent on a broken source, and after it for whatever went quiet on the way.

    After exec(), read `self.cancelled` and `self.resolved_keys` (dict of settings_key ->
    new value, only for problems where a fix was actually entered)."""

    def __init__(self, problems: list[dict], parent=None):
        super().__init__(parent)
        self.problems = problems
        self._fix_inputs: dict[str, QLineEdit | tuple[QLineEdit, QLineEdit]] = {}
        self.resolved_keys: dict[str, str] = {}
        self.cancelled = False

        url_count = sum(1 for p in problems if p.get('kind') == 'url')
        self.setWindowTitle("RoleHound found problems")
        self.setMinimumWidth(620)
        self.setMinimumHeight(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        # Say which KIND of problem, because the two are acted on very differently: an API
        # key is pasted here and works immediately, a dead website needs looking at.
        if url_count and url_count < len(problems):
            what = (f"{len(problems) - url_count} API/source problem(s) and "
                    f"{url_count} website(s) that could not be read")
        elif url_count:
            what = f"{url_count} website(s) that could not be read"
        else:
            what = f"{len(problems)} problem(s)"
        intro = QLabel(
            f"RoleHound found {what}. Each one below says what happened and how to fix it. "
            "Anything left unfixed is simply skipped -- the rest of the search is unaffected."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(scroll, stretch=1)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)

        for problem in problems:
            content_layout.addWidget(self._build_problem_row(problem))
        content_layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        go_style = (
            "QPushButton { background-color: #2f6f4f; color: white; font-weight: 600; "
            "border: none; border-radius: 6px; padding: 8px 16px; } "
            "QPushButton:hover { background-color: #38835e; }"
        )
        # Nothing here can be fixed by typing, so there is nothing to continue PAST and no
        # search left to cancel -- this is the end-of-run report. Offering "Cancel search"
        # there would be a button that either lies or does nothing.
        if self._fix_inputs:
            cancel_btn = QPushButton("Cancel search")
            cancel_btn.clicked.connect(self._on_cancel)
            buttons.addWidget(cancel_btn)
            go_btn = QPushButton("Continue (skip whatever's still broken)")
        else:
            go_btn = QPushButton("Close")
        go_btn.setStyleSheet(go_style)
        go_btn.setDefault(True)
        go_btn.clicked.connect(self._on_continue)
        buttons.addWidget(go_btn)
        layout.addLayout(buttons)

    def _build_problem_row(self, problem: dict) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background-color: #1c2333; border: 1px solid #33405c; border-radius: 6px; }"
        )
        row_layout = QVBoxLayout(frame)
        row_layout.setContentsMargins(12, 10, 12, 10)
        row_layout.setSpacing(6)

        name_label = QLabel(f"<b>{escape(str(problem.get('name') or 'Unknown source'))}</b>")
        row_layout.addWidget(name_label)

        reason_label = QLabel(problem.get('reason') or 'Unknown problem.')
        reason_label.setWordWrap(True)
        reason_label.setStyleSheet("color: #b8c0d4;")
        row_layout.addWidget(reason_label)

        if problem.get('url'):
            # Selectable, so the address can be copied straight into a browser to check
            # the site by hand -- which is the first step of most of the advice below.
            url_label = QLabel(escape(str(problem['url'])))
            url_label.setWordWrap(True)
            url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            url_label.setStyleSheet("color: #6f7c99; font-family: Consolas, monospace;")
            row_layout.addWidget(url_label)

        advice = problem.get('fix_advice')
        if advice:
            row_layout.addWidget(self._advice_block(str(advice)))

        if not problem.get('fixable'):
            return frame

        fix_kind = problem.get('fix_kind')
        if fix_kind == 'francetravail':
            id_input = QLineEdit()
            id_input.setPlaceholderText("New Client ID")
            secret_input = QLineEdit()
            secret_input.setPlaceholderText("New Client Secret")
            row_layout.addWidget(id_input)
            row_layout.addWidget(secret_input)
            self._fix_inputs[problem['settings_key']] = (id_input, secret_input)
        else:
            key_input = QLineEdit()
            key_input.setPlaceholderText("Paste a new key here to fix it, or leave blank to skip")
            row_layout.addWidget(key_input)
            self._fix_inputs[problem['settings_key']] = key_input

        return frame

    @staticmethod
    def _advice_block(advice: str) -> QLabel:
        """Claude's fix steps, set apart from the machine-written failure reason above.

        Rendered through escape() and only then given its own line breaks: the text comes
        from a model and can contain anything, and a stray '<' in a URL or a shell snippet
        would otherwise be swallowed as markup by Qt's rich-text parser.
        """
        lines = [line.strip() for line in advice.splitlines() if line.strip()]
        body = '<br>'.join(escape(line) for line in lines)
        label = QLabel(f"<b>How to fix it</b><br>{body}")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            "color: #cbd5e8; background-color: #16203a; border-left: 3px solid #4a7dbd; "
            "padding: 8px 10px; margin-top: 4px;"
        )
        return label

    def _collect_resolved_keys(self):
        self.resolved_keys = {}
        for settings_key, widget in self._fix_inputs.items():
            if isinstance(widget, tuple):
                id_value = widget[0].text().strip()
                secret_value = widget[1].text().strip()
                if id_value and secret_value:
                    self.resolved_keys[settings_key] = f"{id_value}|||{secret_value}"
            else:
                value = widget.text().strip()
                if value:
                    self.resolved_keys[settings_key] = value

    def _on_continue(self):
        self._collect_resolved_keys()
        self.cancelled = False
        self.accept()

    def _on_cancel(self):
        self.cancelled = True
        self.reject()
