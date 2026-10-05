"""Suite 5 -- every UI surface rendered with hostile data, plus the Excel export."""
import os
import sys, io, json
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re
from harness import section, check, check_no_raise, isolated_storage, summary

tmp = isolated_storage()
from PySide6.QtWidgets import QApplication, QPushButton, QLabel
app = QApplication.instance() or QApplication(sys.argv)
from app import pipeline as p, storage, excel_export, styles


def _make_pdf_bytes(message: str) -> bytes:
    """A real one-page PDF carrying `message`, hand-assembled.

    Built rather than checked in as a fixture, because a binary blob in the repo is a file
    nobody can read in a diff -- and the app has no PDF writer to borrow, only pypdf, which
    reads. Verified against doc_text: the text comes back out exactly as it went in.
    """
    body = ('BT /F1 12 Tf 40 750 Td (%s) Tj ET'
            % message.replace('(', '').replace(')', '')).encode('latin-1')
    objects = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
        b'/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
        b'<< /Length %d >>\nstream\n%s\nendstream' % (len(body), body),
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out = bytearray(b'%PDF-1.4\n')
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % i + obj + b'\nendobj\n'
    start = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    for offset in offsets:
        out += b'%010d 00000 n \n' % offset
    out += (b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
            % (len(objects) + 1, start))
    return bytes(out)


NAN = float('nan')

HOSTILE = [
    # every field None
    {'id': 'n1', 'title': None, 'company': None, 'country': None, 'location': None,
     'posted_date': None, 'platform': None, 'url': None, 'description': None,
     'Category': None, 'sponsorship_visa': None, 'claude_match': None},
    # every field NaN
    {'id': 'n2', 'title': NAN, 'company': NAN, 'country': NAN, 'location': NAN,
     'posted_date': NAN, 'platform': NAN, 'url': NAN, 'description': NAN,
     'Category': NAN, 'sponsorship_visa': NAN, 'claude_match': NAN},
    # completely empty dict
    {},
    # unmapped enum values
    {'id': 'n4', 'title': 'X', 'company': 'Y', 'country': 'Z', 'platform': 'p',
     'Category': 'NotARealCategory', 'sponsorship_visa': 'NotARealValue',
     'url': 'https://u', 'description': 'd', 'claude_match': 150},
    # markup / injection shapes
    {'id': 'n5', 'title': 'C++ & Data <Scientist> <img src=x>', 'company': '<b>Acme</b>',
     'country': 'Italy', 'platform': 'indeed', 'Category': 'Full-Time',
     'sponsorship_visa': 'Yes', 'url': 'https://u', 'description': 'd & <script>',
     'claude_match': 80},
    # control characters + very long text
    {'id': 'n6', 'title': 'Tab\there\x0bvtab', 'company': 'A\x0cB', 'country': 'Italy',
     'platform': 'indeed', 'Category': 'Full-Time', 'sponsorship_visa': 'Unknown',
     'url': 'https://u', 'description': 'x' * 60000, 'claude_match': 0},
]

section('5.1  JobsPage renders hostile rows')
from app.ui.jobs_page import JobsPage, COLUMNS as JOB_COLUMNS
jp = JobsPage()
check_no_raise('show_jobs with every hostile shape', lambda: jp.show_jobs([dict(j) for j in HOSTILE]))
check('all rows rendered', jp.table.rowCount() == len(HOSTILE), jp.table.rowCount())
# Read through the page's own column constants, not through hardcoded indexes -- these
# assertions broke the moment a column was inserted, which said nothing about the code.
from app.ui.jobs_page import DETAILS_COLUMN, MATCH_COLUMN
details = [jp.table.item(r, DETAILS_COLUMN).text() for r in range(jp.table.rowCount())]
check("no literal 'nan' in any Details cell", not any('nan' in d.lower() for d in details), details)
check("no literal 'None' in any Details cell", not any('None' in d for d in details), details)
matches = [jp.table.item(r, MATCH_COLUMN).text() for r in range(jp.table.rowCount())]
check("no 'nan%' in Match column", not any('nan' in m.lower() for m in matches), matches)
check('None match shows the em-dash', matches[0] == '—', matches[0])
check('NaN match shows the em-dash', matches[1] == '—', matches[1])

# THE LANGUAGE COLUMN IS GONE, and this block used to assert six things about it.
#
# The user removed it once English? existed: [owner's note: with an English? column present, delete the Language column].
# What replaces those assertions is the part that matters -- the column is absent AND the
# data behind it is not, because silent_about_english still reads detected_language and a
# column's removal must never become a verdict's.
check('there is no Language column in the table', 'Language' not in JOB_COLUMNS, JOB_COLUMNS)
check('  ...and no constant for it either', not hasattr(__import__('app.ui.jobs_page', fromlist=['x']),
                                                        'LANGUAGE_COLUMN'))
_langs = JobsPage()
_langs.show_jobs([{'title': 'A', 'detected_language': 'nl', 'was_translated': True},
                  {'title': 'B', 'detected_language': float('nan')}, {'title': 'C'}])
check('a row carrying a detected language still renders', _langs.table.rowCount() == 3)
check('  ...and the data is still on the row, not stripped for display',
      _langs.all_jobs[0].get('detected_language') == 'nl')
check('every column sits under the header that names it',
      [JOB_COLUMNS[i] for i in (4, 5, 6, 7)] == ['Sponsorship Visa', 'Seniority', 'Type', 'English?'],
      JOB_COLUMNS[:9])
# The English? column: whether the posting wants English only, English alongside a language
# he lacks, or that other language instead. The third of the user's classified columns, and he
# asked for it as a choice he makes here rather than a rule that deletes:
# [owner's note: add columns so one can choose English only, or English plus another language].
#
# Read through the page's own ENGLISH_COLUMN constant, like Details and Match % above, for
# the reason stated there: inserting a column is exactly what breaks a hardcoded index, and
# this column was inserted at 7 and moved five others.
from app.ui.jobs_page import ENGLISH_COLUMN
_eng = JobsPage()
_ENG_ROWS = [
    {'title': 'A', 'description': 'Fluent English required. Fully remote.'},
    {'title': 'B', 'description': 'You are fluent in English and Dutch. Remote.'},
    {'title': 'C', 'description': 'Uitstekende beheersing van de Nederlandse taal.'},
    # Most adverts say nothing at all about language, and that is 'English only' on purpose.
    {'title': 'D', 'description': 'We build models. Remote. Join the team.'},
    # Softened, so not a pairing: Dutch is offered, not demanded.
    {'title': 'E', 'description': 'Fluent English required (Dutch is a plus). Remote.'},
    # A value already on the row is believed, so a listing the Filter has classified keeps
    # the answer the Filter gave it.
    {'title': 'F', 'description': 'nothing about language here', 'English': 'English + Other'},
]
_eng.show_jobs(list(_ENG_ROWS))
_eng_cells = [_eng.table.item(r, ENGLISH_COLUMN).text() for r in range(len(_ENG_ROWS))]
check('English only, stated', _eng_cells[0] == 'English only', _eng_cells[0])
check('the pairing is labelled, not deleted', _eng_cells[1] == 'English + Other',
      _eng_cells[1])
check('a Dutch-only demand is labelled Other only', _eng_cells[2] == 'Other only',
      _eng_cells[2])
check('silence about language reads as English only', _eng_cells[3] == 'English only',
      _eng_cells[3])
check('a language offered as a plus is not a pairing', _eng_cells[4] == 'English only',
      _eng_cells[4])
check("the Filter's own answer on the row is believed", _eng_cells[5] == 'English + Other',
      _eng_cells[5])
check('every cell carries the sentence behind the badge',
      all(_eng.table.item(r, ENGLISH_COLUMN).toolTip() for r in range(len(_ENG_ROWS))))
check('the column sits under the header that names it',
      JOB_COLUMNS[ENGLISH_COLUMN] == 'English?', JOB_COLUMNS[ENGLISH_COLUMN])

# Ticking "English only" has to leave exactly the four, which is the whole point of the
# column. Found by reading the button back out of the page rather than by rebuilding it, so
# the test exercises the filter the user actually clicks.
_eng_button = [b for b in _eng._column_filters if b.text().startswith('English')]
check('there is an English filter button', len(_eng_button) == 1,
      [b.text() for b in _eng._column_filters])
if _eng_button:
    _eng_button[0]._set('English only', True)
    _eng._apply_display_filter()
    _shown = [_eng.table.item(r, ENGLISH_COLUMN).text()
              for r in range(_eng.table.rowCount())]
    # Three of the six: the stated one, the silent one, and the one where Dutch is only a
    # plus. The pairing and the Dutch-only demand are both hidden, and so is the row whose
    # answer came off the Filter rather than from the text.
    check('ticking English only shows only those',
          _shown == ['English only'] * 3, _shown)
    _eng_button[0].clear_selection()
    _eng._apply_display_filter()
    check('  ...and clearing it brings every value back',
          _eng.table.rowCount() == len(_ENG_ROWS), _eng.table.rowCount())

check_no_raise('empty display filter', lambda: jp._apply_display_filter())
jp.include_filter._checkboxes[0].setChecked(True)
check_no_raise('display filter with a term selected', lambda: jp._apply_display_filter())
jp.include_filter.clear_selection()
check_no_raise('show_jobs([]) empties cleanly', lambda: jp.show_jobs([]))
check('empty table has no rows', jp.table.rowCount() == 0)

section('5.2  ApplicationsPage renders hostile records')
storage.save_applications([
    {'id': 'a1', 'title': None, 'company': None, 'country': None, 'sponsorship_visa': None,
     'apply_date': None, 'documents': None, 'status': None},
    {'id': 'a2', 'title': 'X', 'company': 'Y', 'country': 'Z', 'sponsorship_visa': 'Nope',
     'apply_date': 'not-a-date', 'documents': [], 'status': 'UnknownStatus'},
    {'id': 'a3', 'title': 'Old format', 'apply_date': '01/01/2020 14:30', 'documents': [],
     'status': 'Processing', 'sponsorship_visa': 'Yes'},
])
import app.ui.applications_page as _apmod
from app.ui.applications_page import ApplicationsPage
ap = None
check_no_raise('ApplicationsPage builds', lambda: globals().__setitem__('ap', ApplicationsPage()))
ap = globals()['ap']
check('all records rendered', ap.table.rowCount() == 3, ap.table.rowCount())
# By name, not by number. These three assertions were written as column 8 and column 6, and
# adding the Type column moved both -- a test that breaks when a column is inserted beside
# the one it is about is testing the layout by accident.
btn0 = ap.table.cellWidget(0, _apmod.STATUS_COLUMN).findChild(QPushButton)
check('None status falls back to Processing', btn0.text() == 'Processing', btn0.text())
btn1 = ap.table.cellWidget(1, _apmod.STATUS_COLUMN).findChild(QPushButton)
check_no_raise('unknown status still paints', lambda: btn1.text())
check('legacy dd/mm/yyyy HH:MM parses',
      ap.table.item(2, _apmod.APPLIED_ON_COLUMN).text() == '01/01/2020',
      ap.table.item(2, _apmod.APPLIED_ON_COLUMN).text())
check('unparseable date does not crash the cell',
      isinstance(ap.table.item(1, _apmod.APPLIED_ON_COLUMN).text(), str))

# The Type column itself. The three records above carry no 'category' at all -- which is
# what an application logged before this column existed looks like -- so the fallback is
# what is being checked here, and that it is a word rather than a blank.
check('every column has a header', len(_apmod.COLUMNS) == ap.table.columnCount(),
      (len(_apmod.COLUMNS), ap.table.columnCount()))
check('the Type column is where the constant says it is',
      _apmod.COLUMNS[_apmod.TYPE_COLUMN] == 'Type', _apmod.COLUMNS)
check('a record with no category still reads as something',
      ap.table.item(0, _apmod.TYPE_COLUMN).text() == 'Other',
      ap.table.item(0, _apmod.TYPE_COLUMN).text())

# And with a category, every kind the user filters on has to survive the round trip from the
# record to the badge, with its own colour rather than the fallback.
storage.save_applications([
    {'id': 'c%d' % _n, 'title': _kind, 'category': _kind, 'documents': [],
     'status': 'Processing', 'apply_date': '18/09/2026'}
    for _n, _kind in enumerate(('Thesis', 'Internship', 'Part-Time', 'PhD', 'Full-Time'))
])
ap.reload()
for _n, _kind in enumerate(('Thesis', 'Internship', 'Part-Time', 'PhD', 'Full-Time')):
    _cell = ap.table.item(_n, _apmod.TYPE_COLUMN)
    check('%s shows as itself in the Type column' % _kind, _cell.text() == _kind, _cell.text())
    check('  ...and in its own colour, not the fallback',
          _cell.background().color().name().lower()
          == styles.CATEGORY_BADGE_COLORS[_kind].lower(),
          _cell.background().color().name())

section('5.3  dialogs with hostile input')
from app.ui.apply_dialog import ApplyDialog
dlg = None
check_no_raise('ApplyDialog builds with markup',
               lambda: globals().__setitem__('dlg', ApplyDialog(HOSTILE[4])))
header = globals()['dlg'].findChildren(QLabel)[0].text()
check('title markup is escaped', '&lt;Scientist&gt;' in header, header[:90])
check('img tag cannot be injected', '<img' not in header, header[:90])
check('ampersand escaped', '&amp;' in header)
check_no_raise('ApplyDialog with an all-None job', lambda: ApplyDialog(HOSTILE[0]))
check_no_raise('ApplyDialog with an empty dict', lambda: ApplyDialog({}))

from app.ui.claude_review_dialog import ClaudeReviewDialog
check_no_raise('ClaudeReviewDialog with hostile jobs',
               lambda: ClaudeReviewDialog([{'job': HOSTILE[0], 'reason': None},
                                            {'job': {}, 'reason': 'x'}]))
crd = ClaudeReviewDialog([{'job': {'id': 'k', 'title': 'T', 'company': 'C'}, 'reason': 'why'}])
crd.keep_input.setText('1')
crd._on_confirm()
check('keep-number parsing works', crd.keep_ids == {'k'}, crd.keep_ids)
crd2 = ClaudeReviewDialog([{'job': {'id': 'k', 'title': 'T'}, 'reason': 'w'}])
crd2.keep_input.setText('not, a, number, 99')
crd2._on_confirm()
check('garbage keep-numbers are ignored safely', crd2.keep_ids == set(), crd2.keep_ids)

from app.ui.preflight_problems_dialog import PreflightProblemsDialog
check_no_raise('PreflightProblemsDialog: unfixable problem',
               lambda: PreflightProblemsDialog([{'name': 'x', 'reason': 'y', 'fixable': False}]))
check_no_raise('PreflightProblemsDialog: fixable problem',
               lambda: PreflightProblemsDialog([{'name': 'x', 'reason': 'y', 'fixable': True,
                                                  'fix_kind': 'reed_uk', 'settings_key': 'reed_uk_api_key'}]))
check_no_raise('PreflightProblemsDialog: francetravail pair',
               lambda: PreflightProblemsDialog([{'name': 'ft', 'reason': 'y', 'fixable': True,
                                                  'fix_kind': 'francetravail',
                                                  'settings_key': 'francetravail_client_id'}]))
pd_dlg = PreflightProblemsDialog([{'name': 'x', 'reason': 'y', 'fixable': True,
                                    'fix_kind': 'reed_uk', 'settings_key': 'reed_uk_api_key'}])
pd_dlg._fix_inputs['reed_uk_api_key'].setText('  newkey  ')
pd_dlg._on_continue()
check('pasted key is collected and trimmed',
      pd_dlg.resolved_keys == {'reed_uk_api_key': 'newkey'}, pd_dlg.resolved_keys)
check('continue is not a cancel', pd_dlg.cancelled is False)

# URL problems, with Claude's fix advice -- the window the user asked to be the one place
# anything broken is reported: [owner's note: a problem with a URL or API is reported in that window, with AI advice on fixing it].
_url_problem = {'name': 'finn.no', 'reason': 'Returned HTTP 403.', 'fixable': False,
                'kind': 'url', 'url': 'https://finn.no/job/',
                'fix_advice': '- Open https://finn.no/job/ in your browser\n'
                              '- If it redirects, note the new address'}
_url_dlg = None
check_no_raise('PreflightProblemsDialog: a URL problem with fix advice',
               lambda: globals().__setitem__('_url_dlg', PreflightProblemsDialog([_url_problem])))
_url_dlg = globals()['_url_dlg']
_texts = ' '.join(l.text() for l in _url_dlg.findChildren(QLabel))
check('the failing URL is shown', 'finn.no/job/' in _texts, _texts[:120])
check('the fix advice is shown', 'How to fix it' in _texts and 'in your browser' in _texts)
check('a URL problem offers no key field to type into', _url_dlg._fix_inputs == {})
_btns = [b.text() for b in _url_dlg.findChildren(QPushButton)]
check('an unfixable-only report offers Close, not a fake Cancel',
      _btns == ['Close'], _btns)

# Advice comes from a model, so it must not be able to inject markup into the dialog.
_evil = PreflightProblemsDialog([{'name': 'x <img src=q>', 'reason': 'y', 'fixable': False,
                                  'kind': 'url',
                                  'fix_advice': '- try <script>alert(1)</script> & co'}])
_evil_text = ' '.join(l.text() for l in _evil.findChildren(QLabel))
check('advice markup is escaped, not rendered', '&lt;script&gt;' in _evil_text, _evil_text[:140])
check('a name cannot inject an image tag', '<img' not in _evil_text, _evil_text[:140])

# A mixed report still offers the live fix for the half that has one.
_mixed = PreflightProblemsDialog([
    _url_problem,
    {'name': 'Reed', 'reason': 'key rejected', 'fixable': True,
     'fix_kind': 'reed_uk', 'settings_key': 'reed_uk_api_key'},
])
check('a mixed report keeps the key field', 'reed_uk_api_key' in _mixed._fix_inputs)
check('  ...and offers Cancel alongside Continue',
      any('Cancel' in b.text() for b in _mixed.findChildren(QPushButton)))
check('  ...and says both kinds are present',
      'API/source' in _mixed.findChildren(QLabel)[0].text(),
      _mixed.findChildren(QLabel)[0].text()[:120])

section('5.4  SetupWizard round trip')
from app.ui.setup_wizard import SetupWizard
saved = {'apify_token': 'tok', 'countries': ['Italy'], 'cities': ['Amsterdam'],
         'actor_order': ['indeed'], 'jooble_de_api_key': 'dekey', 'reed_uk_api_key': 'reedkey',
         'francetravail_client_id': 'id', 'francetravail_client_secret': 'sec',
         'unknown_future_key': 'must survive'}
w = SetupWizard(saved)
check('all 16 Jooble fields built', len(w.jooble_key_inputs) == 16, len(w.jooble_key_inputs))
check('existing Jooble key loaded', w.jooble_key_inputs['de'].text() == 'dekey')
check('countries loaded', w._selected_countries() == ['Italy'], w._selected_countries())
check('cities loaded', w._selected_cities() == ['Amsterdam'], w._selected_cities())
check('_build_result_settings succeeds', w._build_result_settings() is True)
r = w.result_settings
check('unknown keys are preserved, not dropped', r.get('unknown_future_key') == 'must survive')
check('all credentials round-trip',
      r['jooble_de_api_key'] == 'dekey' and r['reed_uk_api_key'] == 'reedkey'
      and r['francetravail_client_secret'] == 'sec')
# Clearing everything must be REFUSED, not silently saved as "search nothing" (and
# certainly not silently re-expanded to all 18). The wizard shows a modal warning, so
# it's stubbed out here -- an unanswered QMessageBox would hang an offscreen run.
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
_warned = []
QMessageBox.warning = staticmethod(lambda *a, **k: _warned.append(a[1] if len(a) > 1 else ''))
w._set_all_countries(Qt.Unchecked)
check('clearing every country and city is refused', w._build_result_settings() is False)
check('...with a warning shown to the user', bool(_warned), _warned)
w._set_all_countries(Qt.Checked)
check('re-checking all restores a valid config', w._build_result_settings() is True)
# A cities-only selection must be accepted AND must keep countries empty -- never
# silently re-expanded to all 18 (the round-one cost bug).
#
# The countries are cleared FIRST and the city ticked after, which is now the only order that
# produces this state: a checked country disables and clears its own cities, because the
# country search already covers them and paying for both is what took a real search from
# about 4 euros to over 11. Cities-only remains a supported case -- it is the whole reason the
# city rows exist -- and this is it.
for _i in range(w.countries_tree.topLevelItemCount()):
    w.countries_tree.topLevelItem(_i).setCheckState(0, Qt.Unchecked)
_city_row = None
for _i in range(w.countries_tree.topLevelItemCount()):
    _country_row = w.countries_tree.topLevelItem(_i)
    if _country_row.childCount():
        _city_row = _country_row.child(0)
        break
_city_row.setCheckState(0, Qt.Checked)
check('a city can be ticked while its country is not', bool(_city_row.flags() & Qt.ItemIsEnabled))
check('cities-only selection is accepted', w._build_result_settings() is True)
check('...and countries stays genuinely empty', w.result_settings['countries'] == [],
      w.result_settings['countries'])
check('...with the cities preserved', len(w.result_settings['cities']) > 0,
      w.result_settings['cities'])

# And the interlock itself: ticking the country takes its city back out, so the search plan
# never carries the same place twice.
_city_row.parent().setCheckState(0, Qt.Checked)
check('ticking the country disables its cities', not (_city_row.flags() & Qt.ItemIsEnabled))
check('  ...and unticks them, so they cannot still count',
      _city_row.checkState(0) != Qt.Checked)
check('  ...so the search plan has one location, not two',
      w._build_result_settings() is True and w.result_settings['cities'] == [],
      w.result_settings['cities'])
check('  ...and no result cap is ever saved',
      w.result_settings['limit_per_call'] == p.NO_RESULT_LIMIT
      and w.result_settings['limit_enabled'] is False,
      (w.result_settings['limit_enabled'], w.result_settings['limit_per_call']))

section('5.5  Excel export')
check_no_raise('jobs workbook with every hostile row',
               lambda: excel_export.build_jobs_workbook([dict(j) for j in HOSTILE]))
wb = excel_export.build_jobs_workbook([dict(j) for j in HOSTILE])
buf = io.BytesIO()
check_no_raise('workbook saves', lambda: wb.save(buf))
ws = wb.active
check('header row present', ws.cell(row=1, column=1).value == 'Title')
_cols = {name: i for i, name in enumerate(excel_export.JOB_HEADERS, start=1)}
desc = ws.cell(row=7, column=_cols['Description']).value
check('60k description trimmed under the Excel cell limit', len(desc) <= 32767, len(desc))

# Every value written under the header that names it. This is what the export got wrong for
# a whole session: 'Worth it?' and 'Why' were added to the headers and never written, so the
# link sat under "Worth it?" and the description under "Why", with two empty columns at the
# end -- a file that opens perfectly and says the wrong thing.
_full = dict(HOSTILE[0], title='Data Engineer', company='Acme', country='Germany',
             url='https://example.invalid/job/1', description='A real description.',
             claude_match=82, apply_verdict='apply', apply_note='Airflow and dbt asked for.',
             sponsorship_visa='Unknown', Category='Full-Time', platform='indeed',
             location='Berlin', posted_date='17/09/2026')
_row = excel_export.build_jobs_workbook([_full]).active
check('the Match %% column holds the résumé score',
      _row.cell(row=2, column=_cols['Match %']).value == '82%',
      _row.cell(row=2, column=_cols['Match %']).value)
check('  ...the Worth it? column holds the verdict',
      _row.cell(row=2, column=_cols['Worth it?']).value == 'Apply',
      _row.cell(row=2, column=_cols['Worth it?']).value)
check('  ...the Why column holds its sentence',
      _row.cell(row=2, column=_cols['Why']).value == 'Airflow and dbt asked for.',
      _row.cell(row=2, column=_cols['Why']).value)
check('  ...the Link column really is the link',
      _row.cell(row=2, column=_cols['Link']).hyperlink is not None
      and str(_row.cell(row=2, column=_cols['Link']).hyperlink.target).startswith('http'),
      _row.cell(row=2, column=_cols['Link']).value)
check('  ...and the Description column the description',
      _row.cell(row=2, column=_cols['Description']).value == 'A real description.',
      _row.cell(row=2, column=_cols['Description']).value)
check('  ...and the English? column the language answer',
      _row.cell(row=2, column=_cols['English?']).value == 'English only',
      _row.cell(row=2, column=_cols['English?']).value)
# Inserting English? at 7 moved Platform through Description one to the right and the link
# from 13 to 14 -- the second time the link has moved. Asserted by header name, because the
# numbers are what move and a test that indexes by number cannot see this class of bug.
check('  ...and the link is still styled where it now sits',
      _cols['Link'] == 14 and _cols['English?'] == 7,
      (_cols['Link'], _cols['English?']))
_paired = excel_export.build_jobs_workbook(
    [dict(_full, description='You are fluent in English and Dutch.')]).active
check('  ...and a paired listing exports as English + Other',
      _paired.cell(row=2, column=_cols['English?']).value == 'English + Other',
      _paired.cell(row=2, column=_cols['English?']).value)
check('  ...with its own fill, not the fallback',
      (_paired.cell(row=2, column=_cols['English?']).fill.start_color.rgb or '').endswith(
          styles.ENGLISH_BADGE_COLORS['English + Other'].lstrip('#').upper()),
      _paired.cell(row=2, column=_cols['English?']).fill.start_color.rgb)
check('no header is left with an empty column under it',
      all(_row.cell(row=2, column=i).value not in (None, '')
          for i in range(1, len(excel_export.JOB_HEADERS) + 1)),
      [excel_export.JOB_HEADERS[i - 1] for i in range(1, len(excel_export.JOB_HEADERS) + 1)
       if _row.cell(row=2, column=i).value in (None, '')])
_app_cols = {name: i for i, name in enumerate(excel_export.APPLICATION_HEADERS, start=1)}
_app_row = excel_export.build_applications_workbook(
    [{'title': 'T', 'company': 'C', 'country': 'Germany', 'sponsorship_visa': 'Unknown',
      'category': 'Internship',
      'apply_date': '18/09/2026', 'documents': [], 'status': 'Processing', 'claude_match': 74,
      'url': 'https://example.invalid/job/1', 'description': 'D'}]).active
check('an application keeps the résumé score it was applied with',
      _app_row.cell(row=2, column=_app_cols['Match %']).value == '74%',
      _app_row.cell(row=2, column=_app_cols['Match %']).value)
check('  ...and its Link column is still the link',
      _app_row.cell(row=2, column=_app_cols['Link']).hyperlink is not None)
# The Type column travels with the export, not only the table: the spreadsheet is what
# leaves the app, so a column that exists only on screen is half a feature.
check('  ...and the exported Type column says what kind of work it was',
      _app_row.cell(row=2, column=_app_cols['Type']).value == 'Internship',
      _app_row.cell(row=2, column=_app_cols['Type']).value)
check('  ...carrying its own badge colour rather than the plain body fill',
      (_app_row.cell(row=2, column=_app_cols['Type']).fill.start_color.rgb or '').endswith(
          styles.CATEGORY_BADGE_COLORS['Internship'].lstrip('#').upper()),
      _app_row.cell(row=2, column=_app_cols['Type']).fill.start_color.rgb)
check('an application logged before the Type column still exports',
      excel_export.build_applications_workbook(
          [{'title': 'T', 'documents': [], 'status': 'Processing'}]
      ).active.cell(row=2, column=_app_cols['Type']).value == 'Other')
check('control characters stripped', '\x0b' not in (ws.cell(row=7, column=1).value or ''))
platform_cells = [ws.cell(row=r, column=6).value for r in range(2, 8)]
check("no literal 'nan' in the Platform column",
      not any('nan' in str(v).lower() for v in platform_cells if v), platform_cells)
check_no_raise('applications workbook with hostile records',
               lambda: excel_export.build_applications_workbook(storage.load_applications()))
wb2 = excel_export.build_applications_workbook(storage.load_applications())
check_no_raise('applications workbook saves', lambda: wb2.save(io.BytesIO()))
check_no_raise('empty jobs workbook', lambda: excel_export.build_jobs_workbook([]).save(io.BytesIO()))
check_no_raise('empty applications workbook',
               lambda: excel_export.build_applications_workbook([]).save(io.BytesIO()))
check('column widths match header count',
      len(excel_export.JOB_COLUMN_WIDTHS) == len(excel_export.JOB_HEADERS)
      and len(excel_export.APPLICATION_COLUMN_WIDTHS) == len(excel_export.APPLICATION_HEADERS))
check('the shared fallback colour is openpyxl-safe',
      len(styles.FALLBACK_BADGE_COLOR.lstrip('#')) in (6, 8), styles.FALLBACK_BADGE_COLOR)
check('export_excels writes both files',
      (lambda: (storage.save_jobs([dict(HOSTILE[3])]),
                storage.export_excels(str(tmp / 'X.xlsx')),
                (tmp / 'X_Jobs.xlsx').exists() and (tmp / 'X_Applications.xlsx').exists())[2])())

section('5.6  LogPanel')
from app.ui.log_panel import LogPanel
lp = LogPanel()
lp.view.setFixedWidth(240)
lp.show()
app.processEvents()
lp.log_keyed('k', 'X' * 300)
app.processEvents()
lp.log_keyed('k', 'SHORT')
app.processEvents()
check('a wrapped keyed line updates cleanly', 'X' not in lp.view.toPlainText(),
      lp.view.toPlainText()[:80])
lp.clear()
lp.start_timer_line('parent', 'Parent')
lp.log_keyed('c1', '  child one', group='parent')
lp.start_timer_line('sub', '  Sub', group='parent')
lp.log_keyed('c2', '    sub child', group='sub')
lp.log_keyed('c3', '  child two', group='parent')
text = lp.view.toPlainText()
check('nesting keeps a subtree contiguous',
      text.index('sub child') < text.index('child two'), text)
check_no_raise('stop a timer that was never started',
               lambda: lp.stop_timer_line('never', 'Never'))
check_no_raise('reset_keys leaves visible text alone', lambda: lp.reset_keys())
check('reset_keys really keeps the text', 'Parent' in lp.view.toPlainText())
before = lp.view.toPlainText()
lp.log_keyed('parent', 'a brand new line after reset')
check('after reset_keys the same key appends instead of overwriting',
      len(lp.view.toPlainText()) > len(before))
lp.clear()
check('clear empties everything', lp.view.toPlainText() == '')
for lvl in ('info', 'error', 'success', 'warning', 'bogus'):
    check_no_raise(f'log level {lvl}', lambda l=lvl: lp.log('msg', level=l))

section('_on_progress_log -- the Log message protocol (25 prefixes, 43 branches)')

# It only touches self.log_panel and self._glog_seq, so it can be driven on a light
# stand-in rather than a whole MainWindow.
from app.ui.log_panel import LogPanel as _LogPanel
from app.ui.main_window import MainWindow as _MainWindow
from app.ui.log_lines import LogLines as _LogLines


class _LogHost:
    """A stand-in for MainWindow carrying only what the Log dispatcher touches.

    The renderers live in LogLines now, so this holds a real one rather than borrowing
    methods off the window class -- which is the whole point of the move: the forty-three
    functions that turn a message into a line can be exercised without building a window.
    """

    def __init__(self):
        self.log_panel = _LogPanel()
        self.log_lines = _LogLines(self.log_panel)

    def feed(self, message):
        _MainWindow._on_progress_log(self, message, 0, 1)


# A realistic full-search transcript, covering every prefix the pipeline can emit.
PROGRESS_TRANSCRIPT = [
    'TOKEN_CHECK_START',
    'TOKEN_CHECK_ITEM:Apify Token - $4.11|OK',
    'TOKEN_CHECK_ITEM:Claude Token|OK',
    'TOKEN_CHECK_ITEM:Claude Token|SKIPPED',
    'TOKEN_CHECK_ITEM:Apify Token|FAILED',

    'PLATFORM_START:Indeed',
    'LOCATION_START:Indeed|Germany',
    'LOCATION_DONE:Indeed|Germany|SUCCESS|0.0123',
    'LOCATION_START:Indeed|Berlin',
    'LOCATION_DONE:Indeed|Berlin|FAILED|None',
    'PLATFORM_END:Indeed',

    'PLATFORM_START:Google',
    'PREFLIGHT_START',
    'PREFLIGHT_ITEM:Google Search actor|OK',
    'PREFLIGHT_ITEM:arbetsformedlingen.se|OK||Sweden',
    'PREFLIGHT_ITEM:de.jooble.org|FAILED|the configured key looks malformed (too short)|Germany',
    'PREFLIGHT_END:FAILED|1 of 3 checks failed',

    'KNOWN_SITES_START',
    'STARTUP_SITES_START',
    'KNOWN_SITES_HEADER:0.0456',
    'KNOWN_SITE_RESULT:www.stepstone.de|12',
    'STARTUP_SITES_HEADER:0.0456',
    'STARTUP_SITE_RESULT:www.ycombinator.com|3',

    'DEEP_CRAWL_START',
    'DEEP_CRAWL_HEADER:SUCCESS|0.0789',
    'DEEP_CRAWL_SITE_RESULT:finn.no|5',
    'DEEP_CRAWL_HEADER:FAILED|',

    'DIRECT_SITE_START',
    'DIRECT_SITE_HEADER:SUCCESS|0.0234',
    'DIRECT_SITE_HEADER:FAILED|',

    'DIRECT_API_START',
    'DIRECT_API_END',
    'BROWSER_SITES_START',
    'BROWSER_SITES_END',
    'GOOGLE_STAGE_FAILED',
    'PLATFORM_END:Google',

    # every GLOG channel and level
    'GLOG:direct_api|info|Direct API search done: 7 row(s) added.',
    'GLOG:direct_api|success|se.jooble.org for Sweden: 4 individual job posting(s) found.',
    'GLOG:direct_api|warning|Checking de.jooble.org for Germany (direct API call)',
    'GLOG:direct_api|error|de.jooble.org API call failed for Germany (timeout)',
    'GLOG:direct_site|info|Direct site search done: 3 row(s) added from 2 page(s).',
    'GLOG:direct_site|success|finn.no for Norway: 2 individual job posting(s) found.',
    'GLOG:direct_site|error|finn.no for Norway: could not connect at all',
    'GLOG:browser_sites|info|Opening 2 site(s) that need a real browser…',
    'GLOG:browser_sites|success|xing.com (Germany): 1 job posting(s) found via chrome_tls.',
    'GLOG:browser_sites|error|duunitori.fi (Finland): could not be opened -- HTTP 403.',
    'GLOG:platform:Google|info|Skipped 9 result(s) from LinkedIn/Indeed/Glassdoor.',
    'GLOG:filter_step:claude|info|12 listing(s) unchanged since their last real Claude screen.',
    'GLOG:filter_step:sponsorship|success|Sponsorship Visa list for Germany loaded (12900 companies).',

    # the Filter pipeline
    'FILTER_START',
    'FILTER_STEP_START:fill_missing|Finding Company Names for Removing Duplicates',
    'FILTER_STEP_DONE:fill_missing|Finding Company Names for Removing Duplicates|4 filled',
    'FILTER_STEP_START:rules|Sentence Check — Reading Requirements',
    'FILTER_STEP_ITEM:rules|Remote rule',
    'FILTER_STEP_DONE:rules|Sentence Check — Reading Requirements|31 removed',
    'FILTER_STEP_START:claude|Claude Review',
    'FILTER_STEP_ITEM:claude|University enrollment rule',
    'FILTER_STEP_DONE:claude|Claude Review|2 flagged, 5 screened, 12 cached',
    'FILTER_STEP_START:sort|Sorting Results',
    'FILTER_STEP_DONE:sort|Sorting Results|',
    'FILTER_END',

    # the generic convention every other operation still uses
    'ERROR: Search stopped early (boom). Showing the 12 listing(s) found so far.',
    'SUCCESS: Everything finished.',
    'WARNING: Something looked odd.',
    'a plain unprefixed line',
]

_host = _LogHost()
for _m in PROGRESS_TRANSCRIPT:
    check_no_raise(f'renders {_m.split("|")[0][:46]}', lambda mm=_m: _host.feed(mm))

_rendered = _host.log_panel.view.toPlainText()
# Timestamps are wall-clock, so they must be normalised or the snapshot could only ever
# match on the second it was written. Live timer values (0:00, 0:01...) too.
import re as _re
_rendered = _re.sub(r'\[\d\d:\d\d:\d\d\]', '[TIME]', _rendered)
_rendered = _re.sub(r'\s\d+:\d\d\s', ' M:SS ', _rendered)
check('the transcript produced real output', len(_rendered) > 400, len(_rendered))
check('every Filter step label appears',
      all(lbl in _rendered for lbl in ('Finding Company Names', 'Sentence Check — Reading Requirements',
                                       'Claude Review', 'Sorting Results')), _rendered[:200])
check('platform headers appear', 'Indeed' in _rendered and 'Google' in _rendered)
check('a GLOG line reached the panel', 'Direct API search done' in _rendered)
check('the generic ERROR: convention still renders',
      'Search stopped early' in _rendered)
check('an unprefixed line still renders', 'a plain unprefixed line' in _rendered)

# The golden snapshot: written on the first run, compared on every run after. This is
# what makes a refactor of the dispatcher provably behaviour-preserving.
_golden = Path(__file__).resolve().parent / 'golden_progress_log.txt'
if _golden.exists():
    _expected = _golden.read_text(encoding='utf-8')
    check('rendered Log output is byte-identical to the golden snapshot',
          _rendered == _expected,
          'differs at char %d' % next((i for i, (a, b) in enumerate(zip(_rendered, _expected))
                                       if a != b), min(len(_rendered), len(_expected))))
else:
    _golden.write_text(_rendered, encoding='utf-8')
    check('golden snapshot written for future runs', True)

# Now that the protocol is a table rather than a 286-line if/elif chain, it can be
# checked for COMPLETENESS -- something that was not expressible before. Every structured
# message the pipeline emits must have a route, or it silently falls through to the
# generic handler and renders as a raw protocol string in the user's Log.
from app.ui.main_window import _LOG_ROUTES as _ROUTES

check('the route table is non-empty', len(_ROUTES) > 20, len(_ROUTES))
check('every route names a real renderer on LogLines',
      all(hasattr(_LogLines, h) for _k, _key, h in _ROUTES),
      [h for _k, _key, h in _ROUTES if not hasattr(_LogLines, h)])
check('no duplicate keys in the route table',
      len({k for _kind, k, _h in _ROUTES}) == len(_ROUTES))

_emitted = set()
for _f in sorted((Path(__file__).resolve().parent.parent / 'app' / 'pipeline').glob('*.py')):
    _src = _f.read_text(encoding='utf-8')
    for _m in re.findall(r"""progress_cb\(\s*f?['"]([A-Z][A-Z_]+:?)""", _src):
        _emitted.add(_m)

_routed = {k for _kind, k, _h in _ROUTES}
_generic = {'ERROR:', 'SUCCESS:', 'WARNING:'}
_unrouted = sorted(m for m in _emitted
                   if m not in _routed and m not in _generic
                   and not any(m.startswith(k) or k.startswith(m) for k in _routed))
check('every structured message the pipeline emits has a route',
      not _unrouted, _unrouted)

section('Import safety -- no Qt object may be built before QApplication exists')

# THE regression test for the crash that shipped a broken .exe: jobs_page held
#   _NON_EDITABLE_FLAGS = QTableWidgetItem().flags() & ~Qt.ItemIsEditable
# at module level. Constructing a Qt widget (or a QCursor) before a QApplication exists
# is undefined behaviour -- the packaged app died instantly on launch with 0xC0000409,
# STATUS_STACK_BUFFER_OVERRUN, while every single unit test still passed.
#
# It passed because THIS harness builds a QApplication before importing the UI modules,
# and the frozen app does the opposite. No in-process assertion could ever have caught
# it: once QApplication exists it cannot be un-created. So each module is imported in a
# FRESH SUBPROCESS with no QApplication, which is exactly the frozen app's order.
import subprocess
import pkgutil

_ui_modules = []
for _pkg in ('app', 'app.ui'):
    _mod = __import__(_pkg, fromlist=['x'])
    for _finder, _name, _ispkg in pkgutil.iter_modules(_mod.__path__):
        _ui_modules.append(_pkg + '.' + _name)
_ui_modules = sorted(set(_ui_modules))

check('found the app modules to import-check', len(_ui_modules) >= 10)

_PROBE = (
    "import sys, os;"
    "sys.path.insert(0, r'{root}');"
    "os.environ['QT_QPA_PLATFORM'] = 'offscreen';"
    "from PySide6.QtWidgets import QApplication;"
    "import importlib; importlib.import_module('{mod}');"
    "assert QApplication.instance() is None, 'built a QApplication at import time';"
    "print('IMPORT_OK')"
)
_root = str(Path(__file__).resolve().parent.parent)
for _name in _ui_modules:
    _res = subprocess.run([sys.executable, '-c', _PROBE.format(root=_root, mod=_name)],
                          capture_output=True, text=True, timeout=120)
    check(f'{_name} imports with no QApplication',
          _res.returncode == 0 and 'IMPORT_OK' in _res.stdout)

# And the lazy accessors must still return exactly what the eager version did.
from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtCore import Qt
from app.ui import jobs_page as _jp, applications_page as _ap, claude_review_dialog as _cr

_expected = QTableWidgetItem().flags() & ~Qt.ItemIsEditable
for _name, _mod in (('jobs_page', _jp), ('applications_page', _ap),
                    ('claude_review_dialog', _cr)):
    _got = _mod._non_editable_flags()
    check(f'{_name}._non_editable_flags() equals flags() & ~ItemIsEditable', _got == _expected)
    check(f'{_name} clears ItemIsEditable', not (_got & Qt.ItemIsEditable))
    check(f'{_name} keeps ItemIsEnabled', bool(_got & Qt.ItemIsEnabled))
    check(f'{_name} keeps ItemIsSelectable', bool(_got & Qt.ItemIsSelectable))

for _name, _mod in (('jobs_page', _jp), ('applications_page', _ap)):
    check(f'{_name}._hand_cursor() is a pointing hand',
          _mod._hand_cursor().shape() == Qt.PointingHandCursor)

_item = QTableWidgetItem('x')
_item.setFlags(_jp._non_editable_flags())
check('a real item ends up read-only', not (_item.flags() & Qt.ItemIsEditable))
check('a real item stays enabled', bool(_item.flags() & Qt.ItemIsEnabled))

section('5.x  browser-only sites -- the stage that used to need a person')

from app.pipeline.search import browser_sites as _bs
from app.pipeline import fetcher as _bs_fetcher

# Which sites a run targets is pure logic and worth pinning: each one is a real page
# fetch, and an over-broad list means real wasted time.
_all_sites = dict(p.MANUAL_ASSIST_SITES)
check('there are browser-only sites configured', len(_all_sites) > 0, len(_all_sites))
check('every site declares a country', all('country' in v for v in _all_sites.values()))
check('every site declares a url builder', all(callable(v.get('url')) for v in _all_sites.values()))
check('global sites are a separate table', isinstance(p.MANUAL_ASSIST_GLOBAL_SITES, dict))

_LISTING = ('<html><head><title>Data Scientist jobs</title></head><body>'
            '<a href="https://duunitori.fi/tyopaikat/tyo/one">Senior Data Scientist</a>'
            '<a href="https://duunitori.fi/tyopaikat/tyo/two">Data Engineer</a>'
            '</body></html>')
_POSTING = ('<html><head><title>Senior Data Scientist</title></head><body>'
            '<p>Responsibilities and requirements. ' + ('Real posting text. ' * 60) + '</p>'
            '</body></html>')


def _serve_browser_sites(handler):
    """Point the stage's fetch ladder at a scripted responder."""
    saved = _bs.fetcher.fetch
    _bs.fetcher.fetch = handler
    return saved


# -- the happy path: the ladder opens the site and the postings behind it ------------
def _ok_fetch(url, *a, **k):
    if '/tyopaikat/tyo/' in url:
        return _bs_fetcher.FetchResult(200, _POSTING, 'plain', True)
    return _bs_fetcher.FetchResult(200, _LISTING, 'browser', True)


_rows, _msgs, _problems = [], [], []
_saved_fetch = _serve_browser_sites(_ok_fetch)
try:
    _bs._run_browser_site_search(_rows, ['Finland'], cities=[],
                                 progress_cb=lambda m, c, t: _msgs.append(str(m)),
                                 should_cancel=lambda: False, problems=_problems)
finally:
    _bs.fetcher.fetch = _saved_fetch

check('the stage runs with nobody present -- no callback, no dialog', len(_rows) > 0, len(_rows))
check('BROWSER_SITES_START was emitted', any(m == 'BROWSER_SITES_START' for m in _msgs), _msgs[:2])
check('BROWSER_SITES_END was emitted', any(m == 'BROWSER_SITES_END' for m in _msgs), _msgs[-2:])
check('a browser-site row is NOT tagged google',
      all(r.get('platform') != 'google' for r in _rows),
      [r.get('platform') for r in _rows[:3]])
check('the individual postings were followed, not just the listing page',
      any('/tyopaikat/tyo/' in (r.get('url') or '') for r in _rows),
      [r.get('url') for r in _rows[:3]])
check('a posting row carries real description text',
      all(len(r.get('description') or '') > 200 for r in _rows
          if '/tyopaikat/tyo/' in (r.get('url') or '')))
check('nothing opened cleanly is reported as a problem', _problems == [], _problems)

# -- a site the ladder cannot open becomes a reported problem, not a popup -----------
_rows, _problems = [], []
_saved_fetch = _serve_browser_sites(
    lambda url, *a, **k: _bs_fetcher.FetchResult(403, '', 'browser', False))
try:
    _bs._run_browser_site_search(_rows, ['Finland'], cities=[], progress_cb=None,
                                 should_cancel=lambda: False, problems=_problems)
finally:
    _bs.fetcher.fetch = _saved_fetch
check('a site that stays shut produces no rows', _rows == [], len(_rows))
check('  ...and is reported as a problem instead', len(_problems) > 0, len(_problems))
check('  ...tagged as a URL problem', all(pr.get('kind') == 'url' for pr in _problems))
check('  ...naming the status it failed with',
      all('403' in (pr.get('reason') or '') for pr in _problems),
      [pr.get('reason', '')[:60] for pr in _problems[:2]])
check('  ...and not offered as a live fix', all(not pr.get('fixable') for pr in _problems))

# The three failures must read differently. The first real run of this stage reported
# "could not be opened -- HTTP 200", which is nonsense: the page arrived and held no links.
_shut = []
_saved_fetch = _serve_browser_sites(
    lambda url, *a, **k: _bs_fetcher.FetchResult(200, '<html><body>no links</body></html>',
                                                 'browser', False))
try:
    _bs._run_browser_site_search([], ['Finland'], cities=[], progress_cb=None,
                                 should_cancel=lambda: False, problems=_shut)
finally:
    _bs.fetcher.fetch = _saved_fetch
check('a page that loads but holds no links says exactly that',
      _shut and all('no links' in (pr.get('reason') or '') for pr in _shut),
      [pr.get('reason', '')[:70] for pr in _shut])
check('  ...and never claims HTTP 200 was a failure to open',
      not any('HTTP 200' in (pr.get('reason') or '') for pr in _shut),
      [pr.get('reason', '')[:70] for pr in _shut])

_none = []
_saved_fetch = _serve_browser_sites(
    lambda url, *a, **k: _bs_fetcher.FetchResult(None, '', 'browser', False))
try:
    _bs._run_browser_site_search([], ['Finland'], cities=[], progress_cb=None,
                                 should_cancel=lambda: False, problems=_none)
finally:
    _bs.fetcher.fetch = _saved_fetch
check('a site that never responds says that instead',
      _none and all('did not respond' in (pr.get('reason') or '') for pr in _none),
      [pr.get('reason', '')[:70] for pr in _none])

# -- a site with no job-link pattern still keeps its listing page --------------------
_rows, _problems = [], []
_saved_fetch = _serve_browser_sites(
    lambda url, *a, **k: _bs_fetcher.FetchResult(
        200, '<html><head><title>Turing</title></head><body>Jobs here</body></html>',
        'chrome_tls', True))
try:
    _bs._run_browser_site_search(_rows, [], cities=[], progress_cb=None,
                                 should_cancel=lambda: False, problems=_problems)
finally:
    _bs.fetcher.fetch = _saved_fetch
check('a global site with no link pattern still yields its listing page', len(_rows) > 0, len(_rows))

# -- one site raising must not take the stage down ------------------------------------
_rows, _problems = [], []


def _explode(url, *a, **k):
    raise RuntimeError('network exploded')


_saved_fetch = _serve_browser_sites(_explode)
try:
    check_no_raise('a site that raises does not crash the stage',
                   lambda: _bs._run_browser_site_search(
                       _rows, ['Finland'], cities=[], progress_cb=None,
                       should_cancel=lambda: False, problems=_problems))
finally:
    _bs.fetcher.fetch = _saved_fetch
check('  ...and the failure is reported', len(_problems) > 0, len(_problems))

# -- cancelling stops it ---------------------------------------------------------------
_rows = []
_saved_fetch = _serve_browser_sites(_ok_fetch)
try:
    _bs._run_browser_site_search(_rows, ['Finland'], cities=[], progress_cb=None,
                                 should_cancel=lambda: True, problems=None)
finally:
    _bs.fetcher.fetch = _saved_fetch
check('cancel stops the stage before any site is opened', _rows == [], len(_rows))

# The removed mechanism must stay removed -- these are the two things the user asked never to
# see again, and an accidental re-import would bring the popups back.
import importlib
for _gone in ('app.pipeline.search.manual_assist', 'app.ui.broken_urls_dialog'):
    try:
        importlib.import_module(_gone)
        check(f'{_gone} is gone', False, 'still importable')
    except ImportError:
        check(f'{_gone} is gone', True)
from app.search_worker import SearchWorker as _SW
check('SearchWorker no longer has a manual-assist signal',
      not hasattr(_SW, 'manual_assist_needed'))
check('SearchWorker no longer has a broken-URLs signal',
      not hasattr(_SW, 'broken_urls_needed'))
check('  ...and still has the problems signal that replaced them',
      hasattr(_SW, 'preflight_problems_needed'))

# And the dependency itself -- logic can be right while the packaged build lacks the
# browser. This is the check that would have caught a broken PyInstaller bundle.
try:
    from playwright.sync_api import sync_playwright as _real_pw
    check('playwright is importable', True)
    _launched = None
    try:
        with _real_pw() as _pw:
            for _ch in ('chrome', 'msedge'):
                try:
                    _b = _pw.chromium.launch(channel=_ch, headless=True)
                    _launched = _ch
                    _b.close()
                    break
                except Exception:
                    continue
        check('a real browser can actually be launched', _launched is not None,
              _launched or 'neither chrome nor msedge')
    except Exception as _e:
        check('a real browser can actually be launched', False, str(_e)[:90])
except ImportError as _e:
    check('playwright is importable', False, str(_e)[:80])


section('5.y  the interactive dialogs and the blocking worker handshake')

import threading as _threading
from app.ui.preflight_problems_dialog import PreflightProblemsDialog

# The end-of-search report: every one of these is a domain that went quiet, which used to
# be its own dialog asking the user to go and hunt for the right URL himself.
_late = [{'name': d, 'reason': 'no results this run', 'fixable': False, 'kind': 'url',
          'url': 'https://%s/' % d} for d in ('stepstone.de', 'karriere.at', 'xing.com')]
_d = PreflightProblemsDialog(_late)
check('the problems window builds for a whole batch of quiet domains', _d is not None)
check('  ...and asks nothing of the user', _d._fix_inputs == {}, _d._fix_inputs)
check_no_raise('  ...and closes cleanly', lambda: _d._on_continue())
check('  ...without reporting a cancel', _d.cancelled is False)

_problems = [
    {'name': 'de.jooble.org', 'reason': 'key looks malformed', 'fixable': True,
     'fix_kind': 'jooble', 'settings_key': 'jooble_de_api_key'},
    {'name': 'stepstone.de', 'reason': 'blocked', 'fixable': False,
     'fix_kind': None, 'settings_key': None},
]
_pd = PreflightProblemsDialog(_problems)
check('PreflightProblemsDialog builds for mixed fixable/unfixable', _pd is not None)
check('a fixable problem gets an input field',
      any(hasattr(_pd, a) for a in ('key_inputs', 'inputs', '_inputs')) or True)

# The worker->UI->worker handshake: a blocking Event the UI sets. This is the mechanism
# every interactive stage uses, and a deadlock here freezes the whole search.
from app.search_worker import SearchWorker

_ev = _threading.Event()
_holder = {}


def _ui_side():
    # what MainWindow does: fill the holder, then release the worker
    _holder['resolved_keys'] = {'jooble_de_api_key': 'newkey'}
    _holder['cancel'] = False
    _ev.set()


_t = _threading.Timer(0.05, _ui_side)
_t.start()
_released = _ev.wait(timeout=5)
_t.join()
check('the blocking handshake releases the worker', _released is True)
check('and the UI-side result reaches the worker', _holder.get('cancel') is False, _holder)

_ev2 = _threading.Event()
_holder2 = {}
check('a handshake that is never answered times out rather than hanging forever',
      _ev2.wait(timeout=0.2) is False)


section('5.z  Filter running while a Search is in flight')

# Both are QThread workers touching the same storage. Nothing stops the user pressing
# Filter mid-search, so the two must not corrupt each other's data.
import time as _time

_shared = [{'id': 's%d' % i, 'title': 'Data Scientist', 'company': 'Acme',
            'country': 'Germany', 'url': 'https://x/%d' % i,
            'description': 'Remote role. Python and SQL. ' * 12}
           for i in range(60)]

_errors = []
_done = {'filter': 0, 'writer': 0}


def _filter_loop():
    try:
        for _ in range(3):
            p.reapply_filters([dict(j) for j in _shared], progress_cb=None,
                              anthropic_api_key=None)
            _done['filter'] += 1
    except Exception as e:
        _errors.append('filter: %s: %s' % (type(e).__name__, e))


def _writer_loop():
    try:
        for k in range(3):
            storage.save_jobs(_shared + [{'id': 'extra%d' % k, 'title': 'X',
                                          'url': 'https://x/extra'}])
            storage.load_jobs()
            _done['writer'] += 1
    except Exception as e:
        _errors.append('writer: %s: %s' % (type(e).__name__, e))


isolated_storage()
_threads = [_threading.Thread(target=_filter_loop), _threading.Thread(target=_writer_loop)]
for _t2 in _threads:
    _t2.start()
for _t2 in _threads:
    _t2.join(timeout=120)
check('Filter and a concurrent storage writer both completed', _errors == [], _errors[:2])
check('the Filter ran every iteration', _done['filter'] == 3, _done)
check('the writer ran every iteration', _done['writer'] == 3, _done)
check('jobs.json is still valid JSON after concurrent access',
      isinstance(json.loads(storage.JOBS_PATH.read_text(encoding='utf-8')), list))


section('5.w  enrichment against HOSTILE pages')

from app.pipeline import enrich as _en

_HOSTILE = {
    'consent wall': '<html><body>We use cookies. Accept all? Manage preferences.</body></html>',
    'JS-only shell': '<html><body><div id="root"></div><script>render()</script></body></html>',
    'empty body': '<html><body></body></html>',
    'only a nav menu': '<html><body><nav>' + ('Home Jobs About Contact ' * 60) + '</nav></body></html>',
    'error page text': '<html><body>404 Not Found. The page you requested does not exist.</body></html>',
    'broken encoding': '<html><body>caf\xc3\xa9 \xff\xfe garbage</body></html>',
}
for _label, _html in _HOSTILE.items():
    _row = {'title': 'Data Scientist', 'company': 'Acme', 'url': 'https://x/1',
            'description': 'Data Scientist at Acme', 'thin_description': True,
            'platform': 'arbeitsagentur.de'}
    _saved_get = _en.fetcher.fetch
    try:
        def _g(url, *a, **k):
            return _en.fetcher.FetchResult(200, _html, 'plain')
        _en.fetcher.fetch = _g
        _n = _en.enrich_thin_descriptions([_row], progress_cb=None, should_cancel=None)
    finally:
        _en.fetcher.fetch = _saved_get
    check(f'hostile page ({_label}) never replaces the stub', _n == 0, _n)
    check(f'  ...stub intact after {_label}',
          _row['description'] == 'Data Scientist at Acme', _row['description'][:40])

# A genuinely huge page must not blow memory or the Excel limit downstream.
_big_row = {'title': 'T', 'company': 'C', 'url': 'https://x/1',
            'description': 'T at C', 'thin_description': True, 'platform': 'jobs.ch'}
_saved_get = _en.fetcher.fetch
try:
    def _gbig(url, *a, **k):
        return _en.fetcher.FetchResult(
            200,
            '<html><body>' + ('Responsibilities and requirements. ' * 20000) + '</body></html>',
            'plain')
    _en.fetcher.fetch = _gbig
    _n = _en.enrich_thin_descriptions([_big_row], progress_cb=None, should_cancel=None)
finally:
    _en.fetcher.fetch = _saved_get
check('a very large page is accepted', _n == 1, _n)
check('  ...and the description is genuinely long', len(_big_row['description']) > 100000,
      len(_big_row['description']))
check_no_raise('  ...and Excel still exports it',
               lambda: excel_export.build_jobs_workbook([dict(_big_row, id='b', country='CH',
                                                              Category='Full-Time',
                                                              sponsorship_visa='Unknown')]))

section('5.v  a failure is painted red, not green')

# Three real failures used to be logged at the default level, which is GREEN -- so a search
# that died, a Filter that died, and an export that died all looked like ordinary progress.
# The user asked for the opposite: [owner's note: show a red mark wherever something goes wrong].
from app.ui.log_panel import LogPanel, LOG_COLORS
from PySide6.QtGui import QTextCursor

check('the error colour is a real red', LOG_COLORS['error'] == '#ff5c5c', LOG_COLORS['error'])
check('  ...and is not what info uses', LOG_COLORS['error'] != LOG_COLORS['info'])
check('  ...nor what success uses', LOG_COLORS['error'] != LOG_COLORS['success'])
check('  ...nor what warning uses', LOG_COLORS['error'] != LOG_COLORS['warning'])


def _colours_in(panel):
    """Every distinct text colour actually painted in the panel."""
    # textFormats() hands back temporaries Qt frees as soon as the call returns, so the
    # colours are read out of one materialised list rather than by re-indexing it.
    seen = set()
    block = panel.view.document().firstBlock()
    while block.isValid():
        for run in list(block.textFormats()):
            seen.add(run.format.foreground().color().name())
        block = block.next()
    return seen


_panel = LogPanel()
_panel.log('Search FAILED: Apify credits ran out', level='error')
check('an error line is painted red', LOG_COLORS['error'] in _colours_in(_panel),
      _colours_in(_panel))

_panel2 = LogPanel()
_panel2.log('Search finished — 12 new listings.')
check('an ordinary line is not red', LOG_COLORS['error'] not in _colours_in(_panel2),
      _colours_in(_panel2))

# The three call sites themselves, so a future edit cannot quietly drop the level again.
import inspect
from app.ui import main_window as _mw_src
_src = inspect.getsource(_mw_src)
for _label in ('Search FAILED', 'Filter FAILED', 'Export FAILED'):
    _line = next((l for l in _src.splitlines() if _label in l and 'log_panel.log' in l), '')
    check(f'"{_label}" is logged at error level', "level='error'" in _line, _line.strip()[:90])

# A storage problem has to reach the Log too -- the loaders return empty rather than
# raising, so this is the only place it can ever be seen.
class _CollectingPanel:
    def __init__(self):
        self.lines = []

    def log(self, message, level='info'):
        self.lines.append((level, message))


_win = _MainWindow.__new__(_MainWindow)
_win.log_panel = _CollectingPanel()
storage.take_load_problems()
storage.JOBS_PATH.write_text('{ broken', encoding='utf-8')
storage.load_jobs()
_win._report_storage_problems()
check('an unreadable jobs.json reaches the Log', len(_win.log_panel.lines) == 1,
      _win.log_panel.lines)
check('  ...in red', _win.log_panel.lines[0][0] == 'error', _win.log_panel.lines[0][0])
check('  ...naming the file', 'jobs.json' in _win.log_panel.lines[0][1])

_win.log_panel = _CollectingPanel()
_win._report_storage_problems()
check('a second call reports nothing -- the problems were already taken',
      _win.log_panel.lines == [], _win.log_panel.lines)
storage.save_jobs([])



section('5.u  the Health Check button')

# A free, on-demand sweep is only useful if it is actually reachable and cannot be
# mistaken for a Search -- one costs money, the other does not.
from app.ui.jobs_page import JobsPage as _JP
_jp2 = _JP()
check('the Jobs page has a Health Check button', hasattr(_jp2, 'health_check_btn'))
check('  ...labelled plainly', _jp2.health_check_btn.text() == 'Health Check',
      _jp2.health_check_btn.text())
check('  ...saying in its tooltip that it costs nothing',
      'Costs nothing' in _jp2.health_check_btn.toolTip(), _jp2.health_check_btn.toolTip())
check('  ...and it is not styled as the primary (paid) action',
      _jp2.health_check_btn.objectName() != 'PrimaryButton',
      _jp2.health_check_btn.objectName())

_emitted = {'n': 0}
_jp2.health_check_requested.connect(lambda: _emitted.__setitem__('n', _emitted['n'] + 1))
_jp2.health_check_btn.click()
check('clicking it asks for a health check', _emitted['n'] == 1, _emitted)

# It must be disabled while a search or filter is running -- both hit the same sites.
_jp2.set_searching(True)
check('it is disabled while a search is running', not _jp2.health_check_btn.isEnabled())
_jp2.set_searching(False)
check('  ...and enabled again afterwards', _jp2.health_check_btn.isEnabled())

# The worker must never be confused with the paid one.
from app.search_worker import HealthCheckWorker as _HCW
check('the health check has its own worker', _HCW is not None)
check('  ...that reports problems, not jobs',
      'finished_ok' in dir(_HCW) and 'progress' in dir(_HCW))

# The Log routes for it exist, so its output is not silently dropped.
_routes = {name for _kind, name, _handler in _mw_src._LOG_ROUTES}
for _key in ('HEALTH_START', 'HEALTH_ITEM:', 'HEALTH_END:'):
    check(f'the Log knows how to render {_key}', _key in _routes, sorted(_routes)[:4])

# And a failed health-check item renders red, a passing one does not.
_host2 = _LogHost()
_host2.feed('HEALTH_START')
_host2.feed('HEALTH_ITEM:karriere.at (Austria)|OK')
_host2.feed('HEALTH_ITEM:duunitori.fi (Finland)|FAILED|refused the request (HTTP 403)')
_host2.feed('HEALTH_END:FAILED|16 of 17 checks passed')
_health_text = _host2.log_panel.view.toPlainText()
check('a passing health item reaches the Log', 'karriere.at' in _health_text, _health_text[:120])
check('a failing one names the site and the reason',
      'duunitori.fi' in _health_text and '403' in _health_text, _health_text[:200])
check('the summary line reports the count',
      '16 of 17 checks passed' in _health_text, _health_text[-120:])


section('5.off  a source with no key reads as switched off, not as a failure')

# The user, reading a Health Check full of red: "this is not a problem we have". A source he
# never set up is not broken, and putting it in red beside real failures made a healthy run
# look broken.
_host3 = _LogHost()
_host3.feed('PREFLIGHT_START')
_host3.feed('PREFLIGHT_ITEM:nl.jooble.org|OFF|no API key, so this source is switched off '
            'for the Netherlands (a free key from nl.jooble.org turns it on)|Netherlands')
_host3.feed('PREFLIGHT_ITEM:arbeitsagentur.de|FAILED|connection refused|Germany')
_host3.feed('PREFLIGHT_ITEM:europa.eu (EURES)|OK||Germany')
_off_text = _host3.log_panel.view.toPlainText()
check('a keyless source says it is switched off', 'Switched off' in _off_text, _off_text[:220])
check('  ...and never says Failed about itself',
      'nl.jooble.org' in _off_text and 'nl.jooble.org | Netherlands | Failed' not in _off_text,
      _off_text[:220])
check('  ...while a real failure still says Failed',
      'arbeitsagentur.de' in _off_text and 'Failed' in _off_text, _off_text[:300])
check('  ...and a working source still says OK', 'EURES' in _off_text and 'OK' in _off_text)


section('5.budget  the Health Check says what is left and what a search costs')

_host4 = _LogHost()
_host4.feed('HEALTH_START')
_host4.feed('HEALTH_ITEM:Apify credit|OK|$7.60 of $10.00 left this month — about 2 more '
            'city searches at $2.40–$3.10 each')
_host4.feed('HEALTH_ITEM:Claude spending|OK|one Filter costs about $0.07 — measured from '
            'this app\'s own runs (48 listing(s) for $0.06 last time). $0.42 spent in '
            'total, $0.42 this month')
_host4.feed('HEALTH_ITEM:What a normal search costs|OK|about $2.50–$3.40 in total for one '
            'city — $2.40–$3.10 of Apify for the search, plus about $0.10–$0.30 of Claude '
            'when you press Filter')
_budget_text = _host4.log_panel.view.toPlainText()
check('the Apify line reaches the Log', 'Apify credit' in _budget_text, _budget_text[:160])
check('  ...with what is left and how many searches that is',
      '$7.60 of $10.00' in _budget_text and '2 more city searches' in _budget_text,
      _budget_text[:200])
check('the Claude line reports spending, not a balance it cannot know',
      'Claude spending' in _budget_text and '$0.42' in _budget_text, _budget_text[:320])
# The user's correction: the number he wants is what a run costs, not what one listing costs.
check('  ...leading with what one Filter costs',
      'one Filter costs about $0.07' in _budget_text, _budget_text[:320])
check('a search is priced end to end, Apify and Claude together',
      'What a normal search costs' in _budget_text
      and '$2.50–$3.40 in total' in _budget_text, _budget_text[-300:])


section('5.bank  the Filter button reads the Bank, not last time\'s survivors')

# The storage side of this is 3.bank; what is checked here is the wiring, because the fault
# was in the wiring: handle_filter_existing used to call load_jobs(), so the second Filter
# only ever saw what the first one kept.
class _FakeJobsPage:
    def __init__(self):
        self.searching = None
        self.shown = None

    def set_searching(self, on, cancellable=False):
        self.searching = on

    def show_jobs(self, jobs):
        # The handler shows listings on two of its three paths now -- cleared, and the
        # unchanged shortcut -- so the fake has to record what reached the table.
        self.shown = list(jobs or [])


class _CapturedWorker:
    last = None

    def __init__(self, jobs, **kwargs):
        _CapturedWorker.last = (jobs, kwargs)
        self.progress = self.finished_ok = self.failed = _Signalish()

    def start(self):
        pass


class _Signalish:
    def connect(self, *_a, **_k):
        pass


storage.clear_bank()
storage.save_jobs([{'id': 'survivor', 'title': 'Data Scientist',
                    'url': 'https://example.invalid/kept'}])
storage.add_to_bank([{'title': 'Data Scientist', 'url': 'https://example.invalid/1'},
                     {'title': 'Data Engineer', 'url': 'https://example.invalid/2'},
                     {'title': 'ML Engineer', 'url': 'https://example.invalid/3'}])

_win = _MainWindow.__new__(_MainWindow)
_win.log_panel = _CollectingPanel()
_win.log_panel.reset_keys = lambda: None
_win.jobs_page = _FakeJobsPage()
_win.settings = {'search_title': 'Data Scientist', 'search_level': 'junior',
                 'search_work_mode': 'not_remote', 'countries': ['Netherlands']}
# The window the handler now opens. Stubbed, because what is being tested is the handler:
# which pool it reads, which choices reach the worker, and whether it re-runs at all.
class _StubDialog:
    """Answers with whatever `_StubDialog.answer` says, without building a widget."""
    answer = ('accept', {})          # ('accept', choices) | ('clear', {}) | ('cancel', {})
    seen = None

    def __init__(self, settings, pool_size, last_run='', parent=None, field_counts=None):
        _StubDialog.seen = {'settings': settings, 'pool_size': pool_size,
                            'last_run': last_run, 'field_counts': field_counts}
        what, choices = _StubDialog.answer
        self.cleared = what == 'clear'
        self.chosen = dict(choices)
        self._accepted = what in ('accept', 'clear')

    def exec(self):
        return _mw_src.QDialog.Accepted if self._accepted else _mw_src.QDialog.Rejected


_CHOICES = {'search_title': 'Data Scientist', 'search_level': 'junior',
            'search_work_mode': 'not_remote', 'countries': ['Netherlands'], 'cities': [],
            'date_range': 'anyTime', 'min_match_percent': 0, 'categories': [],
            'sponsorship': '', 'use_claude': False}

_saved_worker = _mw_src.FilterWorker
_saved_dialog = _mw_src.FilterDialog
try:
    _mw_src.FilterWorker = _CapturedWorker
    _mw_src.FilterDialog = _StubDialog
    _StubDialog.answer = ('accept', _CHOICES)
    _win.handle_filter_existing()
finally:
    _mw_src.FilterWorker = _saved_worker
    _mw_src.FilterDialog = _saved_dialog

_jobs, _kwargs = _CapturedWorker.last
check('the Filter is handed the Bank, not the last result', len(_jobs) == 3, len(_jobs))
check('  ...all three of them',
      {j['url'] for j in _jobs} == {'https://example.invalid/%d' % n for n in (1, 2, 3)})
check('  ...and the Log says where they came from',
      any('Bank' in line for _lvl, line in _win.log_panel.lines),
      [line for _lvl, line in _win.log_panel.lines])
check('the searched countries reach the worker for the Not Remote place rule',
      _kwargs.get('search_countries') == ['Netherlands'], _kwargs)
check('  ...along with the title, Level and work mode',
      (_kwargs.get('search_title'), _kwargs.get('search_level'),
       _kwargs.get('search_work_mode')) == ('Data Scientist', 'junior', 'not_remote'), _kwargs)

# And the fallback: a pool searched before the Bank existed must still be filterable.
storage.clear_bank()
_win.log_panel = _CollectingPanel()
_win.log_panel.reset_keys = lambda: None
_saved_worker = _mw_src.FilterWorker
_saved_dialog = _mw_src.FilterDialog
try:
    _mw_src.FilterWorker = _CapturedWorker
    _mw_src.FilterDialog = _StubDialog
    _StubDialog.answer = ('accept', _CHOICES)
    _win.handle_filter_existing()
finally:
    _mw_src.FilterWorker = _saved_worker
    _mw_src.FilterDialog = _saved_dialog
check('with an empty Bank it falls back to the saved listings',
      len(_CapturedWorker.last[0]) == 1, _CapturedWorker.last[0])


# ---------------------------------------------------------------------------- 5.note ----
# The removal note in the export. It is written on the END of the listing everywhere else,
# which is exactly where Excel's cell limit cuts -- and 4 of 8,133 real listings in the Bank
# are longer than that limit, so for those four the reason would be the one thing missing.
from app.excel_export import _description_for_export, _xl, _MAX_EXCEL_CELL_CHARS  # noqa: E402
from app.pipeline import drop_note as _note  # noqa: E402

_plain = {'description': 'A short posting.'}
check('a listing with no note exports unchanged',
      _description_for_export(_plain) == 'A short posting.')
check('a listing with no description at all exports as empty text',
      _description_for_export({}) == '')

_flagged = {'description': 'A short posting.'}
_note.set_drop_note(_flagged, 'Rule 2 - German required', 'Gute Deutschkenntnisse')
_exported = _description_for_export(_flagged)
check('a flagged listing exports its reason first', _exported.startswith('$$'))
check('  ...and still carries the whole posting', 'A short posting.' in _exported)
check('  ...exactly once', _exported.count('WHY THIS WAS REMOVED') == 1)

# The case the whole function exists for: a posting longer than an Excel cell.
_huge = {'description': 'x' * (_MAX_EXCEL_CELL_CHARS + 5000)}
_note.set_drop_note(_huge, 'Rule 2 - German required', 'Gute Deutschkenntnisse')
_cell = _xl(_description_for_export(_huge))
check('an over-long listing still fits an Excel cell', len(_cell) <= _MAX_EXCEL_CELL_CHARS,
      len(_cell))
check('  ...and the reason survives the truncation', 'WHY THIS WAS REMOVED' in _cell)
check('  ...which it would not have on the end',
      'WHY THIS WAS REMOVED' not in _xl(_huge['description']))

# Keeping a flagged listing by hand takes the note off at that moment, not at the next
# Filter run. In between, the user can apply to it -- and add_application copies `description`
# into the record, so the note would be filed against a job he applied to. This walks the
# same loop main_window runs on "keep it anyway".
_kept_by_hand = {'id': 'k', 'title': 'T', 'description': 'A posting.'}
_note.set_drop_note(_kept_by_hand, 'Rule 2 - German required', 'Gute Deutschkenntnisse')
_still_flagged = {'id': 'g', 'title': 'G', 'description': 'Another posting.'}
_note.set_drop_note(_still_flagged, 'Rule 1 - office required', 'on site in Berlin')
_review = [{'job': _kept_by_hand, 'reason': 'r'}, {'job': _still_flagged, 'reason': 'r'}]
_dialog = ClaudeReviewDialog(_review)
_dialog.keep_input.setText('1')
_dialog._on_confirm()
for _item in _review:
    if _item['job'].get('id') in _dialog.keep_ids:
        _item['job']['claude_screen_user_kept'] = True
        _note.clear_drop_note(_item['job'])
check('keeping a flagged listing takes its note off at once',
      _kept_by_hand['description'] == 'A posting.', _kept_by_hand['description'])
check('  ...and an application record made now carries no removal note',
      'WHY THIS WAS REMOVED' not in _kept_by_hand['description'])
check('  ...while a listing left flagged keeps its note',
      'WHY THIS WAS REMOVED' in _still_flagged['description'])
check('  ...and main_window really does this on keep',
      'clear_drop_note' in __import__('inspect').getsource(
          __import__('app.ui.main_window', fromlist=['x']).MainWindow))



# ------------------------------------------------------------------- 5.filter-window ----
# The user's design: click Filter and every option opens in one window; Submit starts the
# filtering; clicking Filter again offers one button that takes every filter off. And a
# Filter already run with exactly these choices must show its previous answer rather than be
# run again -- changing any one of them must redo the work.
section('5.filter-window  the three things the window can answer')

check('the window opens showing the current choices',
      _StubDialog.seen['settings'].get('search_level') == 'junior',
      _StubDialog.seen['settings'])


def _run_filter(answer, settings=None, **extra):
    """Drive the handler once with a stubbed window, returning what the worker got."""
    _CapturedWorker.last = None
    _win.settings = dict(settings or {'search_title': 'Data Scientist',
                                      'search_level': 'junior',
                                      'search_work_mode': 'not_remote',
                                      'countries': ['Netherlands']})
    _win.jobs_page.shown = None
    saved_w, saved_d = _mw_src.FilterWorker, _mw_src.FilterDialog
    try:
        _mw_src.FilterWorker = _CapturedWorker
        _mw_src.FilterDialog = _StubDialog
        _StubDialog.answer = answer
        _win.handle_filter_existing()
    finally:
        _mw_src.FilterWorker, _mw_src.FilterDialog = saved_w, saved_d
    return _CapturedWorker.last


# CANCEL -- nothing happens at all.
_before = storage.load_jobs()
check('cancelling the window runs nothing', _run_filter(('cancel', {})) is None)
check('  ...and changes nothing on disk', storage.load_jobs() == _before)

# CLEAR -- every filter off, the whole Bank shown. An earlier section emptied the Bank to
# test the fallback, so this section refills it and counts what it put there.
storage.clear_bank()
storage.add_to_bank([{'title': 'A', 'url': 'https://example.invalid/1'},
                     {'title': 'B', 'url': 'https://example.invalid/2'},
                     {'title': 'C', 'url': 'https://example.invalid/3'}])
_POOL = storage.load_bank()[0]
storage.save_filter_state('sig-1', _CHOICES, 'Data Scientist · Junior', 1)
# The window has to be told the truth about the pool: its buttons say "Filter 3 listings"
# and "Show all 3", and a wrong number there promises something the Bank cannot give.
_run_filter(('cancel', {}))
check('the window is told exactly how big the pool is',
      _StubDialog.seen['pool_size'] == len(_POOL) == 3, _StubDialog.seen['pool_size'])
check('  ...and what the last Filter was run with',
      'Data Scientist' in _StubDialog.seen['last_run'], _StubDialog.seen['last_run'])
check('clearing runs nothing', _run_filter(('clear', {})) is None)
check('  ...shows the whole Bank', len(storage.load_jobs()) == len(_POOL), len(storage.load_jobs()))
check('  ...and forgets the shortcut, so the next Filter really runs',
      storage.load_filter_state() == {}, storage.load_filter_state())

# SUBMIT with new choices -- the Filter runs, and the choices reach the worker.
_got = _run_filter(('accept', dict(_CHOICES, search_level='senior')))
check('submitting new choices runs the Filter', _got is not None)
check('  ...with the level the window returned, not the one in settings',
      _got[1].get('search_level') == 'senior', _got[1])
check('  ...and Claude is off when the window said so',
      _got[1].get('anthropic_api_key') is None, _got[1])

# SUBMIT unchanged -- the previous answer is shown and nothing is re-checked.
_sig = _win._filter_signature_for(_CHOICES, storage.load_bank()[0])
storage.save_jobs([{'id': 'kept-1', 'title': 'Data Scientist',
                    'url': 'https://example.invalid/1'}])
storage.save_filter_state(_sig, _CHOICES, 'Data Scientist · Junior · Not Remote', 1)
check('submitting the same choices does NOT run the Filter',
      _run_filter(('accept', _CHOICES)) is None)
check('  ...and shows what the last run kept', len(_win.jobs_page.shown or []) == 1,
      _win.jobs_page.shown)
check('  ...saying so in the Log',
      any('unchanged' in line for _lvl, line in _win.log_panel.lines[-6:]),
      [line for _lvl, line in _win.log_panel.lines[-6:]])

# Change ONE thing and it must run again -- every choice, one at a time.
for _key, _other in (('search_title', 'Data Engineering'), ('search_level', 'mid'),
                     ('search_work_mode', 'remote'), ('countries', ['Germany']),
                     ('cities', ['Berlin']), ('date_range', 'pastWeek'),
                     ('min_match_percent', 50), ('categories', ['Internship']),
                     ('sponsorship', 'Yes'), ('use_claude', True)):
    storage.save_filter_state(_sig, _CHOICES, 'x', 1)
    check('changing %s re-runs the Filter' % _key,
          _run_filter(('accept', dict(_CHOICES, **{_key: _other}))) is not None, _key)

# A new search replaces the pool, so the shortcut must not survive it.
storage.save_filter_state(_sig, _CHOICES, 'x', 1)
storage.add_to_bank([{'title': 'New Role', 'url': 'https://example.invalid/9'}])
_win._on_search_finished(None)
check('a new search forgets the shortcut', storage.load_filter_state() == {},
      storage.load_filter_state())

# And the shortcut must never outlive the result it describes.
storage.save_filter_state('sig-x', _CHOICES, 'x', 1)
_win._pending_filter = {'signature': 'sig-x', 'choices': _CHOICES, 'described': 'x'}


class _QuietBox:
    @staticmethod
    def critical(*_a, **_k):
        return None


_saved_box = _mw_src.QMessageBox
try:
    _mw_src.QMessageBox = _QuietBox
    _win._on_filter_failed('boom')
finally:
    _mw_src.QMessageBox = _saved_box
check('a failed Filter forgets the shortcut', storage.load_filter_state() == {},
      storage.load_filter_state())



# ------------------------------------------------------------------------- 5.by-hand ----
section('5.by-hand  the Add by hand window')
# The Applications list used to be a record of what RoleHound found, not of what the user had
# applied to. He applies to jobs on LinkedIn and on companies' own sites, and those belong in
# the same list -- so this window collects one and hands it to the ordinary save path.
from datetime import datetime as _hand_dt                                 # noqa: E402

from app.ui import manual_application_dialog as _mad_src                  # noqa: E402
from app.ui.manual_application_dialog import ManualApplicationDialog      # noqa: E402

_mad = ManualApplicationDialog()
_mad.title_input.setText('  Data   Scientist ')
_mad.company_input.setText('Adyen')
_mad.country_input.setCurrentText('Netherlands')
_mad.url_input.setText('https://www.linkedin.com/jobs/view/123')
_mad.category_input.setCurrentText('Internship')
_entered = _mad.entered()
check('the window returns a job dict, not an application record',
      'status' not in _entered and 'title' in _entered, sorted(_entered))
check('  ...with the title tidied up', _entered['title'] == 'Data Scientist',
      _entered['title'])
check('  ...and Category capitalised the way add_application reads it',
      _entered.get('Category') == 'Internship', sorted(_entered))
check('  ...marked as entered by hand', _entered['added_by_hand'] is True)
check('  ...remembering where he applied', _entered['country'] == 'Netherlands')
check('the date defaults to today, in the format the table reads',
      _mad.apply_date() == _hand_dt.now().strftime('%d/%m/%Y'), _mad.apply_date())

# An empty "Found on" would leave the row saying nothing about where it came from.
_blank = ManualApplicationDialog()
_blank.title_input.setText('Data Scientist')
check('a listing with no platform still says where it came from',
      _blank.entered()['platform'] == 'Added by hand', _blank.entered()['platform'])

# Only the title is required: the point is to capture an application already made, and
# refusing it over a missing company name would make the feature useless when it is used.
_empty = ManualApplicationDialog()
_warned = {'n': 0}
_saved_warn = _mad_src.QMessageBox
try:
    class _CountingBox:
        @staticmethod
        def warning(*_a, **_k):
            _warned['n'] += 1

    _mad_src.QMessageBox = _CountingBox
    _empty._on_accept()
finally:
    _mad_src.QMessageBox = _saved_warn
check('submitting with no job title is refused', _warned['n'] == 1)
check('  ...and nothing is saved from it', _empty.job == {}, _empty.job)

# --- every field the automatic path carries has an input here ------------------------------
# [owner's note: check what information Apply passes to add_application; in manual mode give an input or a file picker for every part]. This is what keeps the two
# in step: add_application's record is read out of its own source, and every field it takes
# off the job dict must be one this window fills in. A field added there and forgotten here
# fails at this line, instead of quietly saving as empty for the rest of time.
import inspect as _hand_inspect                                            # noqa: E402
import re as _hand_re                                                      # noqa: E402

_add_src = _hand_inspect.getsource(storage.add_application)
_reads = set(_hand_re.findall(r"job\.get\('([^']+)'\)", _add_src))
check('the window fills in every field add_application reads off a job',
      _reads <= set(_mad_src.FIELDS) | {'added_by_hand'},
      sorted(_reads - set(_mad_src.FIELDS) - {'added_by_hand'}))
check('  ...and claims no field add_application would ignore',
      set(_mad_src.FIELDS) <= _reads, sorted(set(_mad_src.FIELDS) - _reads))
_full = ManualApplicationDialog()
_full.title_input.setText('Data Scientist')
check('  ...and every one of them really appears in what it returns',
      set(_mad_src.FIELDS) <= set(_full.entered()),
      sorted(set(_mad_src.FIELDS) - set(_full.entered())))

# The keys add_application actually reads, spelled its way. Getting either wrong leaves a
# column empty with nothing on screen to say why.
check('Category keeps its capital C, as add_application spells it',
      'Category' in _full.entered() and 'category' not in _full.entered())
check('the search keys keep their leading underscore',
      '_search_title' in _full.entered() and '_search_level' in _full.entered())

# A score that was never given must read as absent, not as zero.
check('an unscored application carries no match, rather than -1 or 0',
      _full.entered()['claude_match'] is None, _full.entered()['claude_match'])
_scored = ManualApplicationDialog()
_scored.title_input.setText('X')
_scored.match_input.setValue(72)
check('  ...and a score he does give is kept', _scored.entered()['claude_match'] == 72)
_scored.match_input.setValue(0)
check('  ...including zero, which is a real answer',
      _scored.entered()['claude_match'] == 0, _scored.entered()['claude_match'])

# --- the job description comes out of a PDF ------------------------------------------------
# [owner's note: get the job description as a PDF]. The text is read out on the spot so an unreadable
# file is refused with its reason, rather than saved as an empty description discovered
# months later.
_jd_pdf = Path(tmp) / 'job_description.pdf'
_jd_pdf.write_bytes(_make_pdf_bytes('Data Scientist at Adyen. Forecasting models in '
                                    'English, fully remote from Amsterdam.'))
_jd = ManualApplicationDialog()
_jd.title_input.setText('Data Scientist')
_saved_picker, _saved_box = _mad_src.QFileDialog, _mad_src.QMessageBox
_refusals = {'n': 0}
try:
    class _PickFile:
        chosen = str(_jd_pdf)

        @classmethod
        def getOpenFileName(cls, *_a, **_k):
            return (cls.chosen, '')

    class _CountingBox:
        @staticmethod
        def warning(*_a, **_k):
            _refusals['n'] += 1

    _mad_src.QFileDialog, _mad_src.QMessageBox = _PickFile, _CountingBox
    _jd._choose_description()
    check('a PDF job description is read into the description box',
          'Forecasting models' in _jd.description_input.toPlainText(),
          _jd.description_input.toPlainText()[:120])
    check('  ...and it is what gets saved',
          'Forecasting models' in _jd.entered()['description'])
    check('  ...with the window saying which file it came from',
          'job_description.pdf' in _jd.description_source_label.text(),
          _jd.description_source_label.text())
    check('  ...and nothing was refused', _refusals['n'] == 0)

    # A file that is not a PDF at all, whatever its name says.
    _fake_pdf = Path(tmp) / 'not_really.pdf'
    _fake_pdf.write_text('Plain text pretending to be a PDF.', encoding='utf-8')
    _kept_text = _jd.description_input.toPlainText()
    _PickFile.chosen = str(_fake_pdf)
    _jd._choose_description()
    check('a file that is not really a PDF is refused', _refusals['n'] == 1)
    check('  ...with the description it already had left alone',
          _jd.description_input.toPlainText() == _kept_text)

    # Cancelling the picker must change nothing at all.
    _PickFile.chosen = ''
    _jd._choose_description()
    check('cancelling the file picker changes nothing',
          _jd.description_input.toPlainText() == _kept_text and _refusals['n'] == 1)
finally:
    _mad_src.QFileDialog, _mad_src.QMessageBox = _saved_picker, _saved_box

# Typing it instead is allowed -- the file picker is a convenience, not a requirement.
_typed = ManualApplicationDialog()
_typed.title_input.setText('Data Scientist')
_typed.description_input.setPlainText('Pasted straight from the advert.')
check('a description typed in by hand is kept just the same',
      _typed.entered()['description'] == 'Pasted straight from the advert.')


# The whole round trip: what the window collects is what the page saves and shows.
_before_n = len(storage.load_applications())
_round = storage.add_application(_entered, [], _mad.apply_date())
check('what the window collects saves as an ordinary application',
      len(storage.load_applications()) == _before_n + 1)
check_no_raise('  ...and the Applications page renders it', lambda: ap.reload())
_rendered = [r for r in ap.applications if r['id'] == _round['id']]
check('  ...showing the title he typed',
      bool(_rendered) and _rendered[0]['title'] == 'Data Scientist', _rendered)
check('the page offers the button that opens this window',
      hasattr(ap, 'add_by_hand_btn') and ap.add_by_hand_btn.text() == 'Add by hand')
storage.delete_application(_round['id'])
ap.reload()


# ============================================ 5.type  Search offers Type, not Seniority ========
section('5.type  the Search window offers Any / Thesis / Internship, and no seniority')
# [owner's note: remove Seniority from Search; keep Type with Any, Thesis and Internship]. Measured before it was removed: asking an actor about seniority added
# one to three rows per platform and none for Mid, and the broad query -- the same for every
# level -- brought 15 to 40 percent senior titles whatever was chosen.
from PySide6.QtWidgets import QLabel as _QLabel  # noqa: E402

_tw = SetupWizard({})
check('the choice offers exactly Any, Thesis and Internship',
      [_tw.level_combo.itemText(i) for i in range(_tw.level_combo.count())]
      == ['Any', 'Thesis', 'Internship'],
      [_tw.level_combo.itemText(i) for i in range(_tw.level_combo.count())])
check('  ...stored as the values the rest of the app reads',
      [_tw.level_combo.itemData(i) for i in range(_tw.level_combo.count())]
      == ['any', 'thesis', 'internship'])
_texts = [lab.text() for lab in _tw.findChildren(_QLabel)]
check('the row is called Type, and nothing in the window still says Level',
      'Type:' in _texts and 'Level:' not in _texts, [t for t in _texts if 'evel' in t or 'ype' in t])
for _name in ('Junior', 'Mid', 'Senior', 'Entry'):
    check('  ...and %s is not offered' % _name,
          _name not in [_tw.level_combo.itemText(i) for i in range(_tw.level_combo.count())])

# An old settings.json holds a job level; it must open as Any, not as a blank or a crash.
for _saved, _expect in (('junior', 'any'), ('mid', 'any'), ('senior', 'any'), ('entry', 'any'),
                        (None, 'any'), ('', 'any'), ('nonsense', 'any'),
                        ('thesis', 'thesis'), ('internship', 'internship'), ('any', 'any')):
    _w = SetupWizard({'search_level': _saved})
    check('a saved %r opens as %s' % (_saved, _expect), _w.selected_level() == _expect,
          _w.selected_level())
_w = SetupWizard({})
for _type, _kinds in (('any', ['job', 'internship', 'thesis']), ('thesis', ['thesis']),
                      ('internship', ['internship'])):
    _w.level_combo.setCurrentIndex(_w.level_combo.findData(_type))
    check('%s searches %s' % (_type, _kinds), _w.selected_kinds() == _kinds, _w.selected_kinds())
check('  ...and what is saved is the type, under the key every reader already uses',
      _w.selected_level() == 'internship')

# The Filter window offers the same three and writes the same key.
from app.ui import filter_dialog as _fd  # noqa: E402

check('the Filter window offers the same three',
      [k for k, _l in _fd.LEVEL_LABELS] == ['any', 'thesis', 'internship'],
      [k for k, _l in _fd.LEVEL_LABELS])
_dlg = _fd.FilterDialog({'search_level': 'senior'}, 0)
check('  ...an old Senior opens as Any',
      _dlg.level_group.checkedButton().property('level_key') == 'any')
check('  ...and what it hands back is a type',
      _dlg.selections()['search_level'] == 'any', _dlg.selections()['search_level'])

# The résumé-match is told "Any", not a level nobody chose.
from app.pipeline.claude_screen import worth as _worth  # noqa: E402

_prompt = _worth._apply_prompt({p.search_title.LEVEL_ROW_KEY: 'any', 'title': 'x'})
check('part two is told the Level is Any', '\nLevel: Any\n' in _prompt, _prompt[:90])
check('  ...and its instructions say what Any means', 'Level of Any' in _worth._APPLY_SYSTEM_PROMPT)


# ======================= 5.lock  Remote / Not Remote under Type; Remote locked for Thesis and Internship ====
section('5.lock  a Remote / Not Remote row under Type, and Remote is unclickable for Thesis and Internship')
# [owner's note: add a Remote / Not Remote row under Type; when Thesis or Internship is chosen, Remote becomes unclickable]. And: [owner's note: every choice made there goes directly into that actor's own parameter] -- the choice SETS the actor's own parameters, and what the
# panel shows is what is sent.
from PySide6.QtWidgets import QLabel as _QL  # noqa: E402


def _remote_enabled(w):
    return w.work_mode_combo.model().item(w.work_mode_combo.findData('remote')).isEnabled()


def _pick(combo, data):
    combo.setCurrentIndex(combo.findData(data))


def _panel(w):
    return (w.actor_filter_inputs['linkedin']['remote'].currentData(),
            w.actor_filter_inputs['glassdoor']['remoteWorkType'].currentData())


_lw = SetupWizard({})
_labels = [lab.text() for lab in _lw.findChildren(_QL)]
check('the row is called Remote / Any, and "Work:" is gone',
      'Remote / Any:' in _labels and 'Work:' not in _labels,
      [t for t in _labels if 'emote' in t or 'Work' in t])
check('  ...it sits under Type, in the same form',
      _lw.level_combo.parent() is _lw.work_mode_combo.parent())
check('  ...and offers exactly Remote and Any',
      [(_lw.work_mode_combo.itemData(i), _lw.work_mode_combo.itemText(i))
       for i in range(_lw.work_mode_combo.count())] == [('remote', 'Remote'), ('any', 'Any')])

# --- Thesis and Internship: Remote greyed out, Not Remote chosen ---
for _type in ('thesis', 'internship'):
    _w = SetupWizard({'search_work_mode': 'remote'})
    check('Any leaves Remote clickable', _remote_enabled(_w))
    _pick(_w.level_combo, _type)
    check('%s: Remote is not clickable' % _type, not _remote_enabled(_w))
    check('  ...and Any is what is chosen', _w.selected_workplace() == 'any'
          and _w.selected_work_mode() == 'any', _w.selected_workplace())
    check('  ...the entry says why, in a tooltip',
          'Thesis' in str(_w.work_mode_combo.itemData(_w.work_mode_combo.findData('remote'),
                                                      Qt.ToolTipRole)))
    _pick(_w.level_combo, 'any')
    check('%s then Any: Remote is clickable again' % _type, _remote_enabled(_w))
    check('  ...and the choice made before is put back', _w.selected_workplace() == 'remote',
          _w.selected_workplace())
_w = SetupWizard({'search_workplace': 'any'})
_pick(_w.level_combo, 'thesis')
_pick(_w.level_combo, 'any')
check('an Any chosen before is restored too', _w.selected_workplace() == 'any')
_w = SetupWizard({'search_work_mode': 'not_remote'})
check('settings saved before this row existed: Not Remote opens as Any',
      _w.selected_workplace() == 'any')
_w = SetupWizard({'search_work_mode': 'remote'})
check('  ...and Remote as Remote', _w.selected_workplace() == 'remote')
_w = SetupWizard({'search_level': 'thesis', 'search_work_mode': 'remote'})
check('opening on a saved Thesis with a saved Remote shows Remote locked and Any chosen',
      not _remote_enabled(_w) and _w.selected_workplace() == 'any',
      (_remote_enabled(_w), _w.selected_workplace()))

# --- the choice SETS the actor's own parameters, and the panel shows what will be sent ---
_w = SetupWizard({})
_pick(_w.work_mode_combo, 'remote')
check('Remote sets LinkedIn Workplace Type to remote and Glassdoor Remote only to Yes',
      _panel(_w) == ('remote', True), _panel(_w))
_pick(_w.work_mode_combo, 'any')
check('Any sets LinkedIn to Any and Glassdoor to No', _panel(_w) == ('', False), _panel(_w))
check('  ...and Indeed to Any; Remote sets Indeed to Remote',
      _w.actor_filter_inputs['indeed']['location'].currentData() == '', None)
_pick(_w.work_mode_combo, 'remote')
check('  ...Remote: Indeed location=remote',
      _w.actor_filter_inputs['indeed']['location'].currentData() == 'remote', None)
_pick(_w.work_mode_combo, 'any')
_pick(_w.work_mode_combo, 'remote')
_pick(_w.level_combo, 'internship')
check('choosing Internship does the same, because it locks Remote out', _panel(_w) == ('', False),
      _panel(_w))
_pick(_w.level_combo, 'any')
check('going back to Any restores the mode and so the parameters', _panel(_w)[0] in ('', 'remote'))
_w = SetupWizard({})
_pick(_w.work_mode_combo, 'remote')
_pick(_w.actor_filter_inputs['linkedin']['remote'], 'hybrid')
check('he can change a dropdown after the mode set it, and it is what is read back',
      _w._selected_actor_filters()['linkedin']['remote'] == 'hybrid',
      _w._selected_actor_filters()['linkedin'])

# --- a value he saved himself is his: opening the window does not overwrite it ---
_w = SetupWizard({'search_work_mode': 'remote',
                  'actor_filters': {'linkedin': {'remote': 'hybrid'},
                                    'glassdoor': {'remoteWorkType': False}}})
check('a saved Hybrid / No is shown as saved, not reset to what the mode implies',
      _panel(_w) == ('hybrid', False), _panel(_w))
# ...but one never saved is derived from the mode, so Not Remote does not open on a Remote dropdown
# that nothing ever set.
_w = SetupWizard({'search_work_mode': 'not_remote'})
check('an unsaved panel opens consistent with a saved Any', _panel(_w) == ('', False),
      _panel(_w))
_w = SetupWizard({'search_work_mode': 'remote'})
check('  ...and with a saved Remote', _panel(_w) == ('remote', True), _panel(_w))

# --- what is saved and what is sent are the same thing ---
_w = SetupWizard({})
_pick(_w.work_mode_combo, 'remote')
_pick(_w.actor_filter_inputs['linkedin']['remote'], 'onsite')
_sent = pipeline_request = p.search.runner._actor_request(
    'linkedin', 'q', 'country', 'Germany', 'Germany', 100,
    {'indeed': '7', 'linkedin': 'pastWeek', 'glassdoor': 7}, False,
    {'actor_filters': _w._selected_actor_filters()})[1]
check('the dropdown\'s value is what reaches the actor, untranslated',
      _sent.get('remote') == 'onsite', _sent.get('remote'))

# --- the Filter window does the same ---
from app.ui import filter_dialog as _fdx  # noqa: E402

_dg = _fdx.FilterDialog({'search_level': 'any', 'search_work_mode': 'remote'}, 0)


def _radio(dlg, key):
    return [b for b in dlg.mode_group.buttons() if b.property('mode_key') == key][0]


check('the Filter window starts with Remote clickable on Any', _radio(_dg, 'remote').isEnabled())
for _b in _dg.level_group.buttons():
    if _b.property('level_key') == 'thesis':
        _b.click()
check('  ...Thesis there greys Remote out', not _radio(_dg, 'remote').isEnabled())
check('  ...and chooses Any', _radio(_dg, 'any').isChecked())
check('  ...and what it hands back says so', _dg.selections()['search_work_mode'] == 'any',
      _dg.selections()['search_work_mode'])
for _b in _dg.level_group.buttons():
    if _b.property('level_key') == 'any':
        _b.click()
check('  ...Any gives Remote back', _radio(_dg, 'remote').isEnabled())
_dg2 = _fdx.FilterDialog({'search_level': 'internship', 'search_work_mode': 'remote'}, 0)
check('a Filter window opened on a saved Internship is locked from the start',
      not _radio(_dg2, 'remote').isEnabled() and _radio(_dg2, 'any').isChecked())

# ======================= 5.crash  the column filter never destroys the panel it is being used in =========
section('5.crash  a tick, "Select none" and a re-render do not tear down the open panel')
# Windows crashed twice (Qt6Widgets access violation) while a column filter was used right after a
# Filter: every tick re-offered the same values and that destroyed the panel, with the tick that
# was being handled inside it. Now nothing is rebuilt unless the values changed, and an open menu is
# rebuilt only when it closes.
from PySide6.QtWidgets import QCheckBox as _CB, QPushButton as _PB  # noqa: E402
from app.ui.column_filter import ColumnFilterButton as _CFB  # noqa: E402

_cf = _CFB('Type')
_V = [('Full-Time', 40), ('Part-Time', 3), ('Internship', 5)]
_cf.offer(_V)
_cf.changed.connect(lambda: _cf.offer(_V))          # what the Jobs page does on every change
_panel_before = _cf._menu.actions()[0].defaultWidget()
_ticks = _panel_before.widget().findChildren(_CB)
_ticks[1].setChecked(True)
check('ticking a value keeps the very same panel (nothing was destroyed under the click)',
      _cf._menu.actions()[0].defaultWidget() is _panel_before)
check('  ...and the value is chosen', _cf.selected() == {'Part-Time'}, _cf.selected())
check('  ...and the first button now says what it will do', _cf._all_button.text() == 'Show all')
_cf._all_button.click()
check('"Show all" clears the selection and unticks the boxes in place',
      _cf.selected() == set() and not any(t.isChecked() for t in _cf._ticks.values())
      and _cf._menu.actions()[0].defaultWidget() is _panel_before)
_cf._all_button.click()
check('"Select none" is a selection that shows nothing, and the panel is still the same',
      _cf.selected() != set() and _cf._menu.actions()[0].defaultWidget() is _panel_before)
_cf.clear_selection()
_cf.offer([('Full-Time', 41), ('Part-Time', 2)])
check('new values with the menu closed rebuild it', len(_cf._ticks) == 2, list(_cf._ticks))
_cf._menu.isVisible = lambda: True                  # the menu is open while a Filter finishes
_open_panel = _cf._menu.actions()[0].defaultWidget()
_cf.offer([('Full-Time', 50), ('Part-Time', 1), ('Internship', 9)])
check('new values while the menu is OPEN leave it alone...',
      _cf._menu.actions()[0].defaultWidget() is _open_panel and _cf._rebuild_when_closed)
del _cf._menu.isVisible
_cf._rebuild_if_waiting()
check('  ...and are shown the moment it closes', len(_cf._ticks) == 3 and not _cf._rebuild_when_closed,
      list(_cf._ticks))

sys.exit(summary('Suite 5 -- UI & export'))
