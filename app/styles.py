"""Central QSS stylesheet -- dark, modern, professional look."""

APP_STYLESHEET = """
* {
    font-family: 'Segoe UI', 'Vazirmatn', sans-serif;
    font-size: 13px;
}

QWidget {
    background-color: #0f1420;
    color: #e6e9f0;
}

QMainWindow {
    background-color: #0f1420;
}

/* ---- Top navigation bar ---- */
#NavBar {
    background-color: #141a2b;
    border-bottom: 1px solid #232a3d;
}

#NavBar QPushButton {
    background-color: transparent;
    border: none;
    padding: 14px 22px;
    color: #9aa4bd;
    font-weight: 600;
    border-bottom: 3px solid transparent;
}

#NavBar QPushButton:hover {
    color: #ffffff;
}

#NavBar QPushButton:checked {
    color: #ffffff;
    border-bottom: 3px solid #5b8cff;
}

#BrandLabel {
    color: #ffffff;
    font-size: 17px;
    font-weight: 700;
    padding: 0 20px;
}

/* ---- Buttons ---- */
QPushButton {
    background-color: #232a3d;
    color: #e6e9f0;
    border: 1px solid #30384f;
    border-radius: 6px;
    padding: 8px 16px;
}

QPushButton:hover {
    background-color: #2c3550;
}

QPushButton:pressed {
    background-color: #1c2233;
}

QPushButton#PrimaryButton {
    background-color: #5b8cff;
    color: #ffffff;
    border: none;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #7aa0ff;
}

QPushButton#PrimaryButton:disabled {
    background-color: #384062;
    color: #7c85a3;
}

QPushButton#ApplyButton {
    background-color: #2ECC71;
    color: #06210f;
    font-weight: 700;
    border: none;
    padding: 6px 14px;
}

QPushButton#ApplyButton:hover {
    background-color: #58d98a;
}

QPushButton#ApplyButton:disabled {
    background-color: #2b4438;
    color: #6c8578;
}

/* Table-row buttons. Defined here rather than via a per-widget setStyleSheet() call
   because the Jobs and Applications tables build one of each PER ROW, and Qt re-parses
   the CSS string every single time -- measured at ~200 ms per 1,000 rows for the two
   inline stylesheets these replace. As part of the app-wide sheet they're parsed once. */
QPushButton#RowApplyButton {
    background-color: #2ECC71;
    color: #06210f;
    font-weight: 700;
    border: none;
    padding: 2px 14px;
}

QPushButton#RowApplyButton:hover {
    background-color: #58d98a;
}

QPushButton#RowRemoveButton {
    background-color: #3a1f28;
    color: #ff8a94;
    border: 1px solid #5a2a35;
    border-radius: 6px;
    font-weight: 700;
}

QPushButton#RowRemoveButton:hover {
    background-color: #5a2a35;
}

QPushButton#RowDownloadButton {
    padding: 2px 10px;
}

QPushButton#RowEditButton {
    padding: 2px 10px;
}

/* The two destructive header buttons ("Clear Search" / "Clear My Applications") --
   same colours as a row Remove button, also moved off per-widget setStyleSheet. */
QPushButton#DangerButton {
    background-color: #3a1f28;
    color: #ff8a94;
    border: 1px solid #5a2a35;
}

QPushButton#DangerButton:hover {
    background-color: #5a2a35;
}

/* ---- Inputs ---- */
QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color: #171d2e;
    border: 1px solid #2c3450;
    border-radius: 6px;
    padding: 7px 10px;
    color: #e6e9f0;
    selection-background-color: #5b8cff;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #5b8cff;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #171d2e;
    border: 1px solid #2c3450;
    selection-background-color: #5b8cff;
    color: #e6e9f0;
}

QCheckBox {
    spacing: 8px;
}

QLabel#SectionTitle {
    font-size: 15px;
    font-weight: 700;
    color: #ffffff;
    padding-top: 6px;
}

QLabel#PlatformTitle {
    font-size: 13px;
    font-weight: 700;
    color: #ffffff;
    padding: 6px 0 4px 0;
}

QLabel#HintLabel {
    color: #8b93ad;
}

/* ---- Table ---- */
QTableWidget {
    background-color: #141a2b;
    alternate-background-color: #171e33;
    gridline-color: #232a3d;
    border: 1px solid #232a3d;
    border-radius: 8px;
    selection-background-color: #26314f;
    selection-color: #ffffff;
}

QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #202739;
}

QHeaderView::section {
    background-color: #1a2136;
    color: #b7c0dc;
    padding: 10px 8px;
    border: none;
    border-bottom: 2px solid #2c3450;
    font-weight: 600;
}

QScrollBar:vertical {
    background: #0f1420;
    width: 12px;
}
QScrollBar::handle:vertical {
    background: #2c3450;
    border-radius: 6px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #3a4468;
}

/* ---- Progress bar ---- */
QProgressBar {
    background-color: #171d2e;
    border: 1px solid #2c3450;
    border-radius: 6px;
    text-align: center;
    color: #e6e9f0;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #5b8cff;
    border-radius: 6px;
}

/* ---- Dialogs ---- */
QDialog {
    background-color: #141a2b;
}

QMessageBox {
    background-color: #141a2b;
}
"""

# The Seniority column, which classifies rather than filters -- see jobs_page's
# SENIORITY_COLUMN for why that changed. One hue family, light to dark with the level, so the
# column reads as a scale at a glance and a glance is what a column filter is for.
# 'Unspecified' is deliberately the grey one: it is a real answer, not a missing value, but it
# is not a rung on the ladder.
SENIORITY_BADGE_COLORS = {
    'Intern': '#2E9E5B',
    'Junior': '#3B8ED6',
    'Mid': '#3B6FD6',
    'Senior': '#4A5578',
    'Lead': '#6E5AC8',
    'Unspecified': '#6B7280',
}


# The English? column, and the three colours say what the badges mean rather than just
# telling them apart: green for the one he is looking for, amber for the one he has to read
# before deciding, red for the one the Filter deletes -- which he only ever sees in a raw
# search, so it should look like what it is.
ENGLISH_BADGE_COLORS = {
    'English only': '#2E9E5B',
    'English + Other': '#C98A2E',
    'Other only': '#7A2E2E',
}


CATEGORY_BADGE_COLORS = {
    'Full-Time': '#4A5578',
    'Part-Time': '#3B6FD6',
    'Internship': '#2E9E5B',
    'Thesis': '#8B5CE0',
    # A doctoral or postdoctoral post: its own kind of work, so its own badge. Kept
    # next to Thesis in hue because they sit next to each other in the sort order,
    # and distinct enough that the two never read as the same thing at a glance.
    'PhD': '#6E5AC8',
    'Contract': '#C98A2E',
    'Temporary': '#B08A2E',
    'Volunteer': '#2E9E9E',
    'Other': '#C9536B',
}

# The single fallback colour for any badge whose value has no entry in the tables
# below. Six digits, deliberately: this exact concept used to be spelled '#555' at the
# Qt call sites and '555555' in the Excel export, and that mismatch IS how the original
# export crash happened -- Qt's QColor accepts 3-digit CSS shorthand, openpyxl's
# PatternFill raises "Colors must be aRGB hex values" on it. One constant, valid for
# both renderers, imported by every call site.
FALLBACK_BADGE_COLOR = '#555555'

SPONSORSHIP_BADGE_COLORS = {
    'Yes': '#1b7a3d',
    # Real, serious bug fixed here: '#555' is a 3-digit CSS-shorthand hex -- Qt's
    # QColor (used everywhere in the desktop UI) accepts that shorthand just fine, but
    # openpyxl's Color/PatternFill (used by excel_export.py's badge cells) does NOT --
    # it requires an exact 6-digit (RGB) or 8-digit (ARGB) hex string and raises
    # ValueError: "Colors must be aRGB hex values" otherwise. Since 'Unknown' is the
    # single most common Sponsorship Visa value in real usage (the default for every
    # country without a real sponsor-list source), this meant Export Excel crashed on
    # almost every real export the moment it tried to color that badge cell -- caught
    # by MainWindow.handle_export's own except-and-report, so it failed with an error
    # dialog rather than silently, but a real, reproducible, high-impact break of a
    # core feature nonetheless. Found via a real openpyxl workbook-build test.
    'Unknown': '#555555',
    "Employer's Discretion": '#5c4fa8',
}

# Company Popularity (formerly here: FAME_BADGE_COLORS, a 5-level badge from a
# per-company Claude web-search check) was removed entirely -- see pipeline.py's own
# comment above where _apply_company_fame_to_jobs used to be for why. The one useful,
# free signal it had (a listing found via the Startup Websites Search stage) now shows
# as a "Startup" suffix on the Type badge instead (pipeline.display_category), reusing
# CATEGORY_BADGE_COLORS' own colors -- no separate color table needed for it.
