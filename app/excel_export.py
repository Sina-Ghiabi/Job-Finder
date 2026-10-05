"""Builds professionally-styled Excel workbooks for the Jobs and Applications exports --
colored header, zebra rows, colored Type/Status badges, clickable links, frozen header."""
from __future__ import annotations

import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app import pipeline
from app.storage import STATUS_COLORS
from app.styles import (CATEGORY_BADGE_COLORS, ENGLISH_BADGE_COLORS,
                        FALLBACK_BADGE_COLOR, SENIORITY_BADGE_COLORS,
                        SPONSORSHIP_BADGE_COLORS)

ACCENT_COLOR = '5B8CFF'
HEADER_TEXT_COLOR = 'FFFFFF'
ZEBRA_COLOR = 'F2F5FC'
BORDER_COLOR = 'DCE3F0'
DARK_TEXT_COLOR = '1A2036'

HEADER_FONT = Font(name='Calibri', size=11, bold=True, color=HEADER_TEXT_COLOR)
HEADER_FILL = PatternFill('solid', fgColor=ACCENT_COLOR)
BODY_FONT = Font(name='Calibri', size=10.5, color=DARK_TEXT_COLOR)
LINK_FONT = Font(name='Calibri', size=10.5, color=ACCENT_COLOR, underline='single')
THIN_BORDER = Border(
    bottom=Side(style='thin', color=BORDER_COLOR),
    top=Side(style='thin', color=BORDER_COLOR),
    left=Side(style='thin', color=BORDER_COLOR),
    right=Side(style='thin', color=BORDER_COLOR),
)
HEADER_ROW_HEIGHT = 24
BODY_ROW_HEIGHT = 42

# openpyxl style objects are immutable value objects that the workbook interns into a
# shared style table anyway, so building a fresh one per CELL is pure waste. A 1,000-row
# jobs export creates 10 cells a row: that was ~10,000 Alignment objects plus a Font,
# Fill and Alignment for every badge, and profiling showed the time going almost entirely
# into openpyxl's own descriptor/serialisation machinery rather than our code. Built once
# here and shared; the only genuinely per-cell value is a badge's fill COLOUR, which is
# memoised by colour in _badge_fill below.
BODY_ALIGNMENT = Alignment(vertical='top', wrap_text=True)
CENTER_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)
HEADER_ALIGNMENT = Alignment(horizontal='center', vertical='center', wrap_text=True)
LINK_ALIGNMENT = Alignment(horizontal='center', vertical='center')
BADGE_FONT = Font(name='Calibri', size=10.5, bold=True, color='FFFFFF')
DARK_BADGE_FONT = Font(name='Calibri', size=10.5, bold=True, color=DARK_TEXT_COLOR)
ZEBRA_FILL = PatternFill('solid', fgColor=ZEBRA_COLOR)
NO_FILL = PatternFill(fill_type=None)

_BADGE_FILLS: dict = {}


def _badge_fill(color_hex: str) -> PatternFill:
    """One PatternFill per distinct colour, reused across every row that needs it --
    there are only a handful of badge colours in the whole app."""
    clean = color_hex.lstrip('#').upper()
    fill = _BADGE_FILLS.get(clean)
    if fill is None:
        fill = PatternFill('solid', fgColor=clean)
        _BADGE_FILLS[clean] = fill
    return fill

# Real, reproducible crash fixed here: openpyxl REJECTS these control characters
# outright (openpyxl.utils.exceptions.IllegalCharacterError) rather than escaping or
# dropping them -- and this app's descriptions are raw scraped page text from
# websiteContentScraper and the deep crawler, which genuinely contains them. A single
# such character anywhere in any listing failed the whole Export Excel run. This is the
# same class of bug as the '#555' three-digit-hex colour crash already fixed in
# styles.py: a different illegal-value rule in the same library, on the same export path.
_ILLEGAL_EXCEL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')

# Excel's own hard per-cell limit. openpyxl writes a longer string without complaining,
# but Excel then reports the file as corrupt when opening it, so it's trimmed here.
_MAX_EXCEL_CELL_CHARS = 32767
_TRUNCATION_NOTE = '\n\n[... truncated to fit Excel\'s 32,767-character cell limit]'


def _xl(value):
    """Makes any value safe to write into a worksheet cell. Applied to every text cell
    in both workbooks below -- not just descriptions, since a scraped title or company
    name can carry the same characters.

    Runs pandas' NaN through pipeline.text_of first: a NaN reaching a cell used to be
    written as a bare float (and crashed outright on the .capitalize() line below)."""
    if value is None or isinstance(value, float):
        value = pipeline.text_of(value)
    if not isinstance(value, str):
        return value
    cleaned = _ILLEGAL_EXCEL_CHARS.sub(' ', value)
    if len(cleaned) > _MAX_EXCEL_CELL_CHARS:
        cleaned = cleaned[:_MAX_EXCEL_CELL_CHARS - len(_TRUNCATION_NOTE)] + _TRUNCATION_NOTE
    return cleaned


def _description_for_export(job: dict) -> str:
    """The listing for a spreadsheet cell, with any removal note moved to the front.

    The note is written on the END of the listing, which is where it belongs everywhere
    else -- and exactly where Excel's 32,767-character cell limit cuts. Measured on the
    Bank: 4 of 8,133 real listings are longer than that, so for those four the reason a
    job was removed would be the one thing missing from the export, precisely when it is
    wanted. Moving it to the front makes the truncation eat the posting instead.
    """
    from app.pipeline.drop_note import drop_note_of, listing_text_without_note

    text = pipeline.text_of(job.get('description'))
    note = drop_note_of(job)
    if not note:
        return text
    return note + '\n\n' + listing_text_without_note(text)


def _write_header(ws: Worksheet, headers: list[str]):
    ws.append(headers)
    ws.row_dimensions[1].height = HEADER_ROW_HEIGHT
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        cell.border = THIN_BORDER
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"


def _style_body_row(ws: Worksheet, row_idx: int, col_count: int,
                    styled_columns: frozenset[int] | set[int] = frozenset()):
    """styled_columns are 1-based column indices already given their own font/fill/alignment
    (badges, links) -- those are left alone apart from the border; everything else gets the
    plain zebra-striped body style."""
    ws.row_dimensions[row_idx].height = BODY_ROW_HEIGHT
    is_even = row_idx % 2 == 0
    fill = ZEBRA_FILL if is_even else NO_FILL
    for col_idx in range(1, col_count + 1):
        cell = ws.cell(row=row_idx, column=col_idx)
        cell.border = THIN_BORDER
        if col_idx in styled_columns:
            continue
        cell.fill = fill
        cell.font = BODY_FONT
        cell.alignment = BODY_ALIGNMENT


def _badge_cell(ws: Worksheet, row_idx: int, col_idx: int, text: str, color_hex: str):
    cell = ws.cell(row=row_idx, column=col_idx, value=_xl(text))
    cell.fill = _badge_fill(color_hex)
    cell.font = BADGE_FONT
    cell.alignment = CENTER_ALIGNMENT
    return cell


def _link_cell(ws: Worksheet, row_idx: int, col_idx: int, url: str, label: str = 'Open ↗'):
    cell = ws.cell(row=row_idx, column=col_idx)
    # text_of first: a NaN url is TRUTHY, so the caller's `or ''` passes the float
    # straight through, and openpyxl then raises
    # "Hyperlink.target should be <class 'str'> but value is <class 'float'>" --
    # failing the whole Export Excel run. Unlike the value cells, this one never went
    # through _xl (which already handles floats), so it was the last unguarded field.
    url = pipeline.text_of(url)
    if url:
        cell.value = label
        cell.hyperlink = url
        cell.font = LINK_FONT
    cell.alignment = LINK_ALIGNMENT
    return cell


# A real fault fixed here: 'Worth it?' and 'Why' were added to these headers when the
# second Claude pass was built, and the rows below were never widened to match -- so every
# export put the link under "Worth it?" and the description under "Why", with two empty
# columns at the end. The count is now asserted in the test suite, since a mismatch here is
# silent: the file opens perfectly and says the wrong thing.
JOB_HEADERS = [
    'Title', 'Company', 'Country', 'Sponsorship Visa', 'Seniority', 'Type', 'English?',
    'Platform', 'Location', 'Posted Date', 'Match %', 'Worth it?', 'Why', 'Link',
    'Description',
]
JOB_COLUMN_WIDTHS = [34, 24, 16, 16, 14, 16, 16, 12, 22, 14, 10, 12, 46, 10, 70]

# What the résumé match's verdict is called in the export, so a column of one-word values
# reads the same as the Jobs page.
WORTH_LABELS = {'apply': 'Apply', 'check': 'Check first', 'skip': 'Skip'}


def build_jobs_workbook(jobs: list[dict]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Job Listings'
    _write_header(ws, JOB_HEADERS)

    for i, job in enumerate(jobs):
        row_idx = i + 2
        ws.cell(row=row_idx, column=1, value=_xl(job.get('title') or ''))
        ws.cell(row=row_idx, column=2, value=_xl(job.get('company') or ''))
        ws.cell(row=row_idx, column=3, value=_xl(job.get('country') or ''))

        sponsorship = pipeline.text_of(job.get('sponsorship_visa')) or 'Unknown'
        _badge_cell(ws, row_idx, 4, sponsorship, SPONSORSHIP_BADGE_COLORS.get(sponsorship, FALLBACK_BADGE_COLOR))

        # Color follows the clean base Category (CATEGORY_BADGE_COLORS has no entry
        # for the "... Startup"-suffixed text itself) -- see pipeline.display_category.
        # Seniority, which classifies rather than filters -- the column the Jobs table
        # shows beside it, read the same way so the two can never disagree.
        level = pipeline.text_of(job.get('Seniority')) or pipeline.seniority_of(job)
        _badge_cell(ws, row_idx, 5, level,
                    SENIORITY_BADGE_COLORS.get(level, FALLBACK_BADGE_COLOR))

        category = pipeline.text_of(job.get('Category')) or 'Other'
        color = CATEGORY_BADGE_COLORS.get(category, FALLBACK_BADGE_COLOR)
        _badge_cell(ws, row_idx, 6, pipeline.display_category(job), color)

        # English?, the third classified column, in the same place it sits in the table:
        # after Type. Everything below it moved one to the right, which is the M-9 failure
        # waiting to happen -- the test asserts each cell BY HEADER NAME for that reason.
        need = (pipeline.text_of(job.get('English'))
                or pipeline.english_requirement_of(job))
        _badge_cell(ws, row_idx, 7, need,
                    ENGLISH_BADGE_COLORS.get(need, FALLBACK_BADGE_COLOR))

        ws.cell(row=row_idx, column=8, value=_xl(pipeline.text_of(job.get('platform')).capitalize()))
        ws.cell(row=row_idx, column=9, value=_xl(job.get('location') or ''))
        ws.cell(row=row_idx, column=10, value=_xl(job.get('posted_date') or ''))
        # The résumé match: the score, the verdict, and the sentence behind it. A NaN score
        # is left blank rather than written as "nan%" -- the same guard the table uses.
        match = job.get('claude_match')
        if isinstance(match, bool) or not isinstance(match, (int, float)) or match != match:
            match_text = ''
        else:
            match_text = '%d%%' % int(match)
        ws.cell(row=row_idx, column=11, value=_xl(match_text))
        worth = pipeline.text_of(job.get('apply_verdict')).strip().lower()
        ws.cell(row=row_idx, column=12, value=_xl(WORTH_LABELS.get(worth, '')))
        ws.cell(row=row_idx, column=13, value=_xl(job.get('apply_note') or ''))
        _link_cell(ws, row_idx, 14, job.get('url') or '')
        ws.cell(row=row_idx, column=15, value=_xl(_description_for_export(job)))

        # 4 Sponsorship, 5 Seniority, 6 Type, 7 English?, 14 the link -- each already carries
        # its own fill or font. The link has now moved twice, from 12 to 13 when Seniority
        # was inserted and from 13 to 14 for English?; missing that is exactly the M-9
        # failure, and it is why the test reads these positions off the header names.
        _style_body_row(ws, row_idx, len(JOB_HEADERS), styled_columns={4, 5, 6, 7, 14})

    for i, width in enumerate(JOB_COLUMN_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    return wb


APPLICATION_HEADERS = [
    'Title', 'Company', 'Country', 'Sponsorship Visa', 'Seniority', 'Type',
    'Applied On', 'Documents', 'Status', 'Match %', 'Link', 'Job Description',
]
APPLICATION_COLUMN_WIDTHS = [34, 24, 16, 16, 14, 14, 14, 12, 14, 10, 10, 70]


def build_applications_workbook(applications: list[dict]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = 'My Applications'
    _write_header(ws, APPLICATION_HEADERS)

    for i, record in enumerate(applications):
        row_idx = i + 2
        ws.cell(row=row_idx, column=1, value=_xl(record.get('title') or ''))
        ws.cell(row=row_idx, column=2, value=_xl(record.get('company') or ''))
        ws.cell(row=row_idx, column=3, value=_xl(record.get('country') or ''))

        sponsorship = pipeline.text_of(record.get('sponsorship_visa')) or 'Unknown'
        _badge_cell(ws, row_idx, 4, sponsorship, SPONSORSHIP_BADGE_COLORS.get(sponsorship, FALLBACK_BADGE_COLOR))

        # The same badge the Applications table shows, with the same colours. 'category'
        # lower case, because that is how the record spells it.
        level = pipeline.text_of(record.get('seniority')) or 'Unspecified'
        _badge_cell(ws, row_idx, 5, level,
                    SENIORITY_BADGE_COLORS.get(level, FALLBACK_BADGE_COLOR))

        category = pipeline.text_of(record.get('category')) or 'Other'
        _badge_cell(ws, row_idx, 6, category,
                    CATEGORY_BADGE_COLORS.get(category, FALLBACK_BADGE_COLOR))

        ws.cell(row=row_idx, column=7, value=_xl(record.get('apply_date') or ''))

        doc_count = len(record.get('documents') or [])
        ws.cell(row=row_idx, column=8, value=f"{doc_count} file(s)")

        status = pipeline.text_of(record.get('status')) or 'Processing'
        # The fourth site that had its own hard-coded fallback literal for the same
        # concept ('888888' here, '#555' in the Qt paths, '555555' in the two above).
        # Unified for the reason in styles.FALLBACK_BADGE_COLOR's own comment: one of
        # those spellings is invalid for openpyxl, and having four of them is precisely
        # how that crash got shipped the first time.
        color = STATUS_COLORS.get(status, FALLBACK_BADGE_COLOR)
        badge = _badge_cell(ws, row_idx, 9, status, color)
        badge.font = DARK_BADGE_FONT

        # The résumé match as it stood when this was applied to (storage keeps it on the
        # record), so the export says why this one was worth an evening.
        match = record.get('claude_match')
        ws.cell(row=row_idx, column=10, value=_xl(
            '%d%%' % int(match) if isinstance(match, (int, float))
            and not isinstance(match, bool) and match == match else ''))
        _link_cell(ws, row_idx, 11, record.get('url') or '')
        ws.cell(row=row_idx, column=12, value=_xl(record.get('description') or ''))

        # The cells that carry their own fill or font and must not be restyled:
        # Sponsorship Visa (4), the new Type badge (5), Status (8) and the link (10).
        # 4 Sponsorship, 5 Seniority, 6 Type, 9 Status, 11 the link. Each moved by one
        # when Seniority was inserted.
        _style_body_row(ws, row_idx, len(APPLICATION_HEADERS),
                        styled_columns={4, 5, 6, 9, 11})

    for i, width in enumerate(APPLICATION_COLUMN_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    return wb
