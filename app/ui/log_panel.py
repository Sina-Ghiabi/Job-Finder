from __future__ import annotations

import time
from datetime import datetime

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor

if TYPE_CHECKING:  # annotation-only: never imported at runtime, no startup cost
    from PySide6.QtGui import QTextBlock
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

LOG_COLORS = {
    'info': '#8ee08e',
    'error': '#ff5c5c',
    'success': '#4caf50',
    'warning': '#e0b400',
}


class LogPanel(QWidget):
    """Small, always-visible, scrollable terminal showing everything the app is doing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 6, 20, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Log")
        title.setObjectName("HintLabel")
        header.addWidget(title)
        header.addStretch(1)
        clear_btn = QPushButton("Clear Log")
        clear_btn.setFixedHeight(26)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            "QPushButton { background-color: #232a3d; color: #e6e9f0; border: 1px solid #3a4468; "
            "border-radius: 6px; padding: 2px 14px; font-weight: 600; } "
            "QPushButton:hover { background-color: #2c3550; }"
        )
        clear_btn.clicked.connect(self.clear)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFixedHeight(260)
        self.view.setFont(QFont("Consolas", 10))
        self.view.setStyleSheet(
            "QPlainTextEdit { background-color: #0a0e17; color: #8ee08e; "
            "border: 1px solid #232a3d; border-radius: 6px; }"
        )
        layout.addWidget(self.view)

        # key -> the QTextBlock holding that key's most recent log_keyed() line, so a
        # later log_keyed() call with the same key can update that exact line in place
        # instead of appending a new one. A QTextBlock is a stable handle to its own
        # paragraph -- unlike a plain block NUMBER (an index), it stays valid even when
        # other blocks are inserted/removed elsewhere in the document, which matters
        # once log_keyed can insert a line in the MIDDLE of the document (see `group`
        # below), not only at the very end.
        self._line_blocks: dict[str, "QTextBlock"] = {}
        # group -> the QTextBlock after which the next new line for that group should
        # be inserted (its header line initially, then whichever of its own lines was
        # added most recently). This is what keeps one platform's location lines
        # visually contiguous under its own header even though several platforms run
        # concurrently and their real completion order interleaves -- without this, a
        # new line always landed at the absolute end of the document, so two platforms
        # running in parallel would interleave their lines together instead of each
        # staying grouped under its own header.
        self._group_anchor: dict[str, "QTextBlock"] = {}
        # child group -> parent group, recorded whenever a section header is created
        # nested under a parent (start_timer_line/log_section_header's `group` param)
        # -- e.g. {'preflight': 'platform:Google'}. Used by _propagate_anchor so that
        # when a GRANDCHILD line is added (e.g. a Pre-API Check item, nested two levels
        # under 'Google'), every ancestor's anchor (not just the immediate parent's)
        # gets pushed forward to that new block too. Without this, a later SIBLING
        # section (e.g. 'Known Websites:') would insert right after the parent's own
        # header line, landing BEFORE its sibling's already-added children instead of
        # after that sibling's entire subtree -- a real bug this fixes.
        self._group_parent: dict[str, str] = {}
        # key -> (QTimer, monotonic start time) for a live, independently-ticking
        # mm:ss counter kept on one key's line (see start_timer_line/stop_timer_line).
        self._timers: dict[str, tuple[QTimer, float]] = {}

    def _propagate_anchor(self, key: str | None, block) -> None:
        """Sets key's own anchor to `block`, then walks up the parent chain (see
        _group_parent) setting every ancestor's anchor to `block` too -- so the next
        sibling inserted anywhere in that ancestry lands after this entire subtree."""
        while key is not None:
            self._group_anchor[key] = block
            key = self._group_parent.get(key)

    def _is_scrolled_to_bottom(self) -> bool:
        scrollbar = self.view.verticalScrollBar()
        # A few px of tolerance so "right at the bottom" still counts even if a
        # previous append left it 1-2px short of the exact maximum.
        return scrollbar.value() >= scrollbar.maximum() - 4

    def log(self, message: str, level: str = 'info'):
        timestamp = datetime.now().strftime('%H:%M:%S')
        color = LOG_COLORS.get(level, LOG_COLORS['info'])
        text = f"[{timestamp}] {message}"

        # Only auto-scrolls to the bottom if the user was ALREADY there before this
        # line was added -- a real bug this fixes: every new log line used to force
        # the view back to the bottom unconditionally, so scrolling up to read
        # anything earlier was impossible during a busy stretch (Google's stage in
        # particular can log dozens of lines a minute).
        was_at_bottom = self._is_scrolled_to_bottom()

        # Prepends the newline separator (instead of appending one after the previous
        # call's text) so this and log_keyed() share the exact same convention -- the
        # document's last block never has a trailing empty line, so whichever method
        # is called next (this one or log_keyed) always starts cleanly on its own
        # line. A real bug this fixes: log_keyed() leaves no trailing newline after
        # its own in-place-updated text, so a plain log() call right after it used to
        # get glued onto the end of that same line instead of starting a new one.
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.view.document().isEmpty():
            cursor.insertText('\n')
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text)

        if was_at_bottom:
            scrollbar = self.view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def log_keyed(self, key: str, message: str, level: str = 'info', group: str | None = None):
        """Logs a line tagged with `key`. The first call for a given key creates a new
        line; every later call with the SAME key updates that exact line in place
        instead of appending another one -- used for a status that changes over time
        (e.g. one country's search: 'Running' -> 'Succeed').

        `group` (optional) keeps this line visually anchored right after the most
        recent line already belonging to that same group (typically a platform's own
        header key) -- e.g. every location line for 'platform:Indeed' is inserted right
        after Indeed's own most recent line, not at the absolute end of the whole log.
        Without this, several platforms running in parallel would have their location
        lines interleaved together in real completion order instead of each staying
        grouped under its own header (a real bug this fixes: Indeed and Glassdoor
        running at the same time produced lines that looked duplicated/scrambled
        because they were ordered by real-world timing, not by which platform they
        belonged to)."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        color = LOG_COLORS.get(level, LOG_COLORS['info'])
        text = f"[{timestamp}] {message}"
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))

        # Same "only auto-scroll if already at the bottom" fix as log() above.
        was_at_bottom = self._is_scrolled_to_bottom()

        existing_block = self._line_blocks.get(key)
        if existing_block is not None and existing_block.isValid():
            cursor = QTextCursor(existing_block)
            # Real bug fixed here: this used to be
            # `cursor.select(QTextCursor.LineUnderCursor)`, which selects one VISUAL
            # line -- and QPlainTextEdit word-wraps by default. Any keyed line long
            # enough to wrap (the multi-line GLOG: warnings with their numbered "1 - /
            # 2 - / 3 -" instructions, or the Claude step's own "N flagged, N screened,
            # N cached" summary) kept its wrapped remainder when it updated, leaving
            # stale text glued onto the end of the new text. Selecting the BLOCK is
            # what "replace this whole logical line" actually means.
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.setCharFormat(fmt)
            cursor.insertText(text)
            new_block = existing_block
        else:
            anchor = self._group_anchor.get(group) if group else None
            if anchor is not None and anchor.isValid():
                cursor = QTextCursor(anchor)
                cursor.movePosition(QTextCursor.EndOfBlock)
                cursor.insertBlock()
            else:
                cursor = self.view.textCursor()
                cursor.movePosition(QTextCursor.End)
                if not self.view.document().isEmpty():
                    cursor.insertBlock()
            cursor.setCharFormat(fmt)
            cursor.insertText(text)
            new_block = cursor.block()
            self._line_blocks[key] = new_block

        if group:
            self._propagate_anchor(group, new_block)

        if was_at_bottom:
            scrollbar = self.view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        return new_block

    def log_section_header(self, key: str, message: str, level: str = 'info', group: str | None = None):
        """Like log_keyed, but ALSO registers `key` as an anchor for its own future
        children (group=key) -- for a static sub-header with no live progress to tick
        (e.g. 'Known Websites:'), where a full start_timer_line/QTimer would be
        misleading since there's nothing actually running live to show. `group`
        (optional) nests this header itself under a parent section, same as
        start_timer_line."""
        if group:
            self._group_parent[key] = group
        block = self.log_keyed(key, message, level=level, group=group)
        self._propagate_anchor(key, block)

    def start_timer_line(self, key: str, label: str, group: str | None = None):
        """Logs a new line for `label` (via log_keyed) with a live mm:ss elapsed-time
        counter that ticks up once per second, entirely locally in the UI -- not tied
        to how often the backend actually reports progress. Used for a platform's
        (Indeed/LinkedIn/Glassdoor) header line, so several selected platforms running
        in parallel each show their own real, independently-moving stopwatch.

        `group` (optional) nests this header itself under a PARENT group (e.g. a
        'Pre-API Check' sub-header nested under the outer 'Google' header) -- this is
        separate from `key`, which is ALWAYS also registered as this header's own
        anchor regardless of `group`, so its own future children (logged with
        group=key) insert right after it. Without a nesting parent for headers, only
        one level of grouping (header -> its direct children) would be possible."""
        self.stop_timer_line(key, label)  # clear any stale timer still running for this key
        if group:
            self._group_parent[key] = group
        start = time.monotonic()
        self._timers[key] = (None, start)  # placeholder until the QTimer object exists below
        block = self.log_keyed(key, f"{label}  0:00", group=group)
        self._propagate_anchor(key, block)  # always usable as a parent for its own children

        timer = QTimer(self)
        timer.timeout.connect(lambda: self._tick_timer_line(key, label))
        timer.start(1000)
        self._timers[key] = (timer, start)

    def _tick_timer_line(self, key: str, label: str):
        entry = self._timers.get(key)
        if not entry:
            return
        _timer, start = entry
        elapsed = int(time.monotonic() - start)
        minutes, seconds = divmod(elapsed, 60)
        # log_keyed's in-place-update path returns the SAME QTextBlock every tick (its
        # position in the document never moves, only its text) -- so, unlike
        # start_timer_line/stop_timer_line, this must NOT touch _group_anchor[key]. A
        # real bug this fixes: 'platform:Google' ticks once a second for the whole
        # Google phase while deeper nested sections (Pre-API Check's items, Known
        # Websites, etc.) are still being added underneath it -- each of those pushes
        # _group_anchor['platform:Google'] forward via _propagate_anchor so the NEXT
        # sibling section lands after them. Overwriting it back to this header's own
        # block on every tick undid that forward push moments later, so whichever
        # section got added right after an unlucky tick landed back up at the header
        # instead of after the section that was actually added last (confirmed via a
        # real screenshot: "Known Websites" appeared in the middle of Pre-API Check's
        # own API item lines instead of after all of them).
        self.log_keyed(key, f"{label}  {minutes}:{seconds:02d}")

    def stop_timer_line(self, key: str, label: str, suffix: str = '', level: str = 'info'):
        """Stops the live ticking counter for `key` (if any) and writes one final
        line with the total elapsed time frozen, plus an optional suffix (e.g. ' —
        Completed')."""
        entry = self._timers.pop(key, None)
        if not entry:
            return
        timer, start = entry
        if timer is not None:
            timer.stop()
        elapsed = int(time.monotonic() - start)
        minutes, seconds = divmod(elapsed, 60)
        # Real bug fixed here: this used to end with `self._group_anchor[key] = block`
        # (setting only key's own anchor, not propagated up via _propagate_anchor).
        # log_keyed's in-place-update path returns the SAME block every time (its
        # position in the document never moves), so touching the anchor here at all is
        # both unnecessary AND actively wrong whenever a child was already logged under
        # `group=key` before this stop call fired (e.g. Direct Site Search's own
        # "Checking domain..." lines, logged right after start_timer_line and before
        # the crawl finishes) -- those children already pushed _group_anchor[key] (and
        # every ancestor's anchor) forward via their own log_keyed(group=...) calls, and
        # resetting it back to the header's own (unchanged) position here would discard
        # that forward progress, causing the NEXT sibling section to insert BEFORE
        # those already-added children instead of after them. This is the exact same
        # bug class already found and fixed once in _tick_timer_line (see its own
        # comment) -- the fix is identical: don't touch _group_anchor here at all.
        self.log_keyed(key, f"{label}  {minutes}:{seconds:02d}{suffix}", level=level)

    def reset_keys(self):
        """Clears all key/anchor tracking (timers, line positions, group anchors) WITHOUT
        touching the visible log text -- called before starting a new Search or Filter
        run. Without this, a second run in the same session would reuse the SAME keys
        (e.g. 'filter', 'known_sites', 'platform:Indeed', 'location:Indeed:Italy') still
        pointing at the FIRST run's old blocks, so log_keyed's in-place-update path would
        silently rewrite/resurrect those old lines (wherever they are in the scrollback)
        instead of appending fresh new ones at the current end -- a real, confirmed bug
        for the documented "just click Filter again" workflow."""
        for timer, _start in self._timers.values():
            if timer is not None:
                timer.stop()
        self._timers.clear()
        self._line_blocks.clear()
        self._group_anchor.clear()
        self._group_parent.clear()

    def clear(self):
        self.reset_keys()
        self.view.clear()
