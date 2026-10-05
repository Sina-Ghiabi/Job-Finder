"""Suite 3 -- persistence: round trips, corruption, migration, hostile values."""
import os
import sys, json, math, shutil
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, check_no_raise, isolated_storage, summary
from app import storage, excel_export
from app import pipeline as p

tmp = isolated_storage()


def strict(path):
    """True only if the file parses as STRICT JSON (no NaN/Infinity literals)."""
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


section('3.1  non-finite floats never reach disk')
NAN, INF = float('nan'), float('inf')
shapes = {
    'flat nan': [{'id': '1', 'x': NAN}],
    'flat +inf': [{'id': '1', 'x': INF}],
    'flat -inf': [{'id': '1', 'x': -INF}],
    'list nan': [{'id': '1', 'a': [1.0, NAN, 3.0]}],
    'dict nan': [{'id': '1', 'a': {'b': NAN}}],
    'triple nested': [{'id': '1', 'a': {'b': [{'c': [NAN, INF]}]}}],
    'tuple nan': [{'id': '1', 'a': (1.0, NAN)}],
    'all at once': [{'id': '1', 'a': NAN, 'b': [INF], 'c': {'d': -INF}, 'e': 'fine'}],
}
for label, payload in shapes.items():
    check_no_raise(f'save_jobs: {label}', lambda pl=payload: storage.save_jobs(pl))
    check_no_raise(f'strict-valid JSON: {label}', lambda: strict(storage.JOBS_PATH))
    check_no_raise(f'save_applications: {label}', lambda pl=payload: storage.save_applications(pl))
    check_no_raise(f'strict-valid applications: {label}', lambda: strict(storage.APPLICATIONS_PATH))
check_no_raise('save_settings with nan', lambda: storage.save_settings({'k': NAN, 'ok': 1}))
check_no_raise('strict-valid settings', lambda: strict(storage.SETTINGS_PATH))

section('3.2  finite values are untouched')
payload = [{'id': '1', 'f': 1.5, 'i': 42, 's': 'text', 'n': None, 'b': True,
            'l': [1, 'two', None], 'd': {'k': 'v'}, 'neg': -0.001, 'zero': 0.0}]
storage.save_jobs(payload)
back = storage.load_jobs()[0]
for k, v in payload[0].items():
    check(f'round-trip {k}', back.get(k) == v, f'{back.get(k)!r} != {v!r}')

section('3.3  unicode, emoji and control characters survive')
payload = [{'id': '1', 'title': 'Datenwissenschaftler (m/w/d) — Köln 🚀',
            'company': 'Ünïcodé Ltd', 'description': 'Персидский • العربية • 中文 • \t tab'}]
storage.save_jobs(payload)
back = storage.load_jobs()[0]
check('unicode title survives', back['title'] == payload[0]['title'], back['title'])
check('emoji survives', '🚀' in back['title'])
check('non-latin scripts survive', 'العربية' in back['description'])
check('file is not ascii-escaped', 'Köln' in storage.JOBS_PATH.read_text(encoding='utf-8'))

section('3.4  corrupt / missing files degrade gracefully')
for label, content in [('truncated', '[{"id": "1"'), ('not json', 'hello world'),
                       ('empty', ''), ('wrong type', '"a string"')]:
    storage.JOBS_PATH.write_text(content, encoding='utf-8')
    # 'wrong type' used to assert load_jobs() == 'a string' -- it documented the bug
    # rather than the requirement. load_jobs is annotated `-> list[dict]`, so handing
    # back a bare string means every caller iterates over CHARACTERS. Valid JSON of the
    # wrong shape is now treated the same as unparseable JSON: nothing.
    check(f'load_jobs({label}) -> []', storage.load_jobs() == [], storage.load_jobs())
storage.JOBS_PATH.unlink(missing_ok=True)
check('load_jobs with no file -> []', storage.load_jobs() == [])
storage.APPLICATIONS_PATH.write_text('{bad', encoding='utf-8')
check('load_applications(corrupt) -> []', storage.load_applications() == [])
storage.SETTINGS_PATH.write_text('{bad', encoding='utf-8')
check('load_settings(corrupt) -> {}', storage.load_settings() == {})

section('3.5  legacy status migration')
storage.save_applications([{'id': 'a', 'status': 'Accepted'}, {'id': 'b', 'status': 'Rejected'},
                           {'id': 'c', 'status': 'Processing'}, {'id': 'd'}])
loaded = storage.load_applications()
check('Accepted -> Accept', loaded[0]['status'] == 'Accept')
check('Rejected -> Reject', loaded[1]['status'] == 'Reject')
check('Processing untouched', loaded[2]['status'] == 'Processing')
check('missing status left alone', 'status' not in loaded[3])
check('migration persisted to disk', 'Accepted' not in storage.APPLICATIONS_PATH.read_text(encoding='utf-8'))

section('3.6  prepend_jobs / delete_job / clear')
storage.clear_jobs()
merged = storage.prepend_jobs([{'title': 'A'}, {'title': 'B'}])
check('prepend assigns ids', all(j.get('id') for j in merged))
check('ids are unique', len({j['id'] for j in merged}) == 2)
merged2 = storage.prepend_jobs([{'title': 'C'}])
check('new jobs go on top', merged2[0]['title'] == 'C' and len(merged2) == 3, [j['title'] for j in merged2])
remaining = storage.delete_job(merged2[0]['id'])
check('delete_job removes exactly one', len(remaining) == 2)
check('delete_job with unknown id is a no-op', len(storage.delete_job('nope')) == 2)
storage.clear_jobs()
check('clear_jobs empties the file', storage.load_jobs() == [])

section('3.7  applications lifecycle + documents')
storage.clear_applications()
doc = tmp / 'cv.txt'
doc.write_text('my cv', encoding='utf-8')
rec = storage.add_application({'title': 'T', 'company': 'C', 'country': 'Italy',
                               'sponsorship_visa': 'Yes', 'url': 'https://u',
                               'description': 'JD text', 'Category': 'Full-Time'}, [str(doc)])
check('record has an id', bool(rec.get('id')))
check('sponsorship_visa carried over', rec['sponsorship_visa'] == 'Yes')
check('category mapped from Category', rec['category'] == 'Full-Time')
check('apply_date is dd/mm/yyyy', len(rec['apply_date'].split('/')) == 3, rec['apply_date'])
check('document was copied, not referenced',
      rec['documents'] and Path(rec['documents'][0]).exists()
      and Path(rec['documents'][0]) != doc)
check('missing source file is skipped, not fatal',
      storage.add_application({'title': 'T2'}, ['C:/does/not/exist.pdf'])['documents'] == [])
storage.update_application_status(rec['id'], 'Accept')
check('status update persists',
      [a for a in storage.load_applications() if a['id'] == rec['id']][0]['status'] == 'Accept')
folder = storage.DOCUMENTS_DIR / rec['id']
check('documents folder exists before delete', folder.is_dir())
storage.delete_application(rec['id'])
check('delete_application removes the folder', not folder.exists())
storage.clear_applications()
check('clear_applications empties the list', storage.load_applications() == [])
check('clear_applications recreates the documents dir', storage.DOCUMENTS_DIR.is_dir())

section('3.8  documents zip')
storage.clear_applications()
d1 = tmp / 'a.txt'; d1.write_text('one', encoding='utf-8')
rec = storage.add_application({'title': 'T', 'company': 'Zip Co', 'description': 'The JD.'}, [str(d1)])
target = tmp / 'out.zip'
storage.build_documents_zip(rec, str(target))
import zipfile
with zipfile.ZipFile(target) as zf:
    names = zf.namelist()
    check('zip nests everything in one folder', all(n.startswith('out/') for n in names), names)
    check('zip contains the JD', 'out/Job Description.txt' in names, names)
    check('zip contains the attachment', 'out/a.txt' in names, names)
    check('JD content is right', zf.read('out/Job Description.txt').decode() == 'The JD.')
check('default_zip_name sanitizes',
      storage.default_zip_name({'company': 'A/B:C*D'}) == 'ABCD_Documents.zip',
      storage.default_zip_name({'company': 'A/B:C*D'}))
check('default_zip_name handles no company',
      storage.default_zip_name({}) == 'Company_Documents.zip')

section('3.9  large payload')
big = [{'id': str(i), 'title': f'Job {i}', 'description': 'x' * 5000} for i in range(2000)]
check_no_raise('save 2,000 jobs with 5k descriptions', lambda: storage.save_jobs(big))
check('all 2,000 round-trip', len(storage.load_jobs()) == 2000)
check('file is strict-valid', bool(strict(storage.JOBS_PATH)))

section('3.x  a damaged or legacy jobs.json -- the file IS the asset')

# A search costs real Apify credit, so jobs.json is not a cache: it is the thing the user
# paid for. Every one of these must fail SAFE -- return nothing, never raise, and never
# leave the file in a worse state than it was found.

import json as _json

_BAD_FILES = [
    ('empty file', ''),
    ('whitespace only', '   \n  '),
    ('truncated mid-object', '[{"id": "a", "title": "Data Sci'),
    ('not JSON at all', 'this is not json'),
    ('a JSON object, not a list', '{"jobs": []}'),
    ('a JSON string', '"hello"'),
    ('null', 'null'),
    ('a list of non-objects', '[1, 2, 3]'),
    ('bare NaN (invalid JSON)', '[{"id": "a", "claude_match": NaN}]'),
    ('deeply nested junk', _json.dumps([{'a': {'b': {'c': [1, 2, {'d': None}]}}}])),
    ('a legacy row with none of the new fields', '[{"title": "Old Job", "url": "https://x/1"}]'),
    ('utf-8 BOM', '\ufeff[{"id":"a","title":"T","url":"https://x/1"}]'),
]

for _label, _content in _BAD_FILES:
    isolated_storage()
    storage.JOBS_PATH.write_text(_content, encoding='utf-8')
    try:
        _loaded = storage.load_jobs()
        _raised = None
    except Exception as _e:
        _loaded = None
        _raised = '%s: %s' % (type(_e).__name__, _e)
    check(f'load_jobs survives {_label}', _raised is None, _raised)
    check(f'  ...and returns a list for {_label}', isinstance(_loaded, list), type(_loaded).__name__)

# A legacy row must still render and still be saveable -- The user may have a jobs.json from
# before Category/sponsorship_visa/the language cache existed.
isolated_storage()
storage.JOBS_PATH.write_text('[{"title": "Old Job", "url": "https://x/1"}]', encoding='utf-8')
_old = storage.load_jobs()
check('a legacy row loads', len(_old) == 1, _old)
check_no_raise('a legacy row can be re-saved', lambda: storage.save_jobs(_old))
check_no_raise('a legacy row survives the Filter',
               lambda: p.reapply_filters(list(_old), progress_cb=None, anthropic_api_key=None))

# The same for applications.
for _label, _content in _BAD_FILES[:8]:
    isolated_storage()
    storage.APPLICATIONS_PATH.write_text(_content, encoding='utf-8')
    try:
        _apps = storage.load_applications()
        _raised = None
    except Exception as _e:
        _apps = None
        _raised = '%s: %s' % (type(_e).__name__, _e)
    check(f'load_applications survives {_label}', _raised is None, _raised)

# And settings -- a broken settings.json must not lock the user out of the app.
for _label, _content in _BAD_FILES[:8]:
    isolated_storage()
    storage.SETTINGS_PATH.write_text(_content, encoding='utf-8')
    try:
        _st = storage.load_settings()
        _raised = None
    except Exception as _e:
        _st = None
        _raised = '%s: %s' % (type(_e).__name__, _e)
    check(f'load_settings survives {_label}', _raised is None, _raised)
    check(f'  ...and returns a dict for {_label}', isinstance(_st, dict), type(_st).__name__)


section('3.y  first run on a clean machine -- nothing exists yet')

isolated_storage()
for _f in (storage.JOBS_PATH, storage.APPLICATIONS_PATH, storage.SETTINGS_PATH):
    if _f.exists():
        _f.unlink()
check('load_settings on a clean machine returns a dict',
      isinstance(storage.load_settings(), dict))
check('load_jobs on a clean machine returns an empty list', storage.load_jobs() == [])
check('load_applications on a clean machine returns an empty list',
      storage.load_applications() == [])
check_no_raise('saving works before any file exists',
               lambda: storage.save_jobs([{'id': 'x', 'title': 'T', 'url': 'https://x/1'}]))
check('and reads back', len(storage.load_jobs()) == 1)


section('3.z  Excel export of an ENRICHED description (Excel caps cells at 32,767)')

# Enrichment turns 40-character stubs into multi-thousand-character descriptions, and one
# real listing in testing ran to 28,465. Excel refuses any cell over 32,767 characters, so
# this is a limit the app can now actually reach.
import io as _io
_HUGE = 'Responsibilities and requirements. ' * 3000     # ~102,000 chars
_job = {'id': 'big', 'title': 'Data Scientist', 'company': 'Acme', 'country': 'Germany',
        'location': 'Berlin', 'platform': 'arbeitsagentur.de', 'url': 'https://x/1',
        'posted_date': '2026-01-01', 'description': _HUGE,
        'Category': 'Full-Time', 'sponsorship_visa': 'Unknown'}
check('the test description really is over Excel\'s limit', len(_HUGE) > 32767, len(_HUGE))
_wb = None
check_no_raise('build_jobs_workbook survives a 100k-character description',
               lambda: excel_export.build_jobs_workbook([_job]))
_wb = excel_export.build_jobs_workbook([_job])
_buf = _io.BytesIO()
check_no_raise('and the workbook actually saves', lambda: _wb.save(_buf))
_cell_lengths = [len(str(c.value)) for row in _wb.active.iter_rows() for c in row
                 if c.value is not None]
check('no cell exceeds Excel\'s 32,767 limit',
      max(_cell_lengths) <= 32767, max(_cell_lengths))

section('3.x  an unreadable file is reported, not silently emptied')

# These loaders return empty rather than raising, which keeps the app alive through a
# OneDrive sync conflict or a half-finished write. Until this existed they also said
# nothing -- so a damaged jobs.json looked exactly like a search that found nothing, and
# the next search would overwrite it. The user asked for the opposite: [owner's note: show a red mark wherever something goes wrong, so a problem is visible].

storage.take_load_problems()  # start from a clean slate

# -- unparseable ---------------------------------------------------------------------
storage.JOBS_PATH.write_text('{ this is not json', encoding='utf-8')
_jobs = storage.load_jobs()
_problems = storage.take_load_problems()
check('a corrupt jobs.json still returns a list, not a crash', _jobs == [], _jobs)
check('  ...and the problem is recorded', len(_problems) == 1, _problems)
check('  ...naming the file', 'jobs.json' in _problems[0], _problems[0])
check('  ...and saying the listings are missing from this session',
      'missing' in _problems[0].lower(), _problems[0])
check('  ...and warning that another search would overwrite it',
      'overwrite' in _problems[0].lower(), _problems[0])
check('taking the problems clears them', storage.take_load_problems() == [])

# -- valid JSON, wrong shape ----------------------------------------------------------
for _bad, _label in (('null', 'null'), ('"hello"', 'a string'), ('{"a": 1}', 'an object')):
    storage.JOBS_PATH.write_text(_bad, encoding='utf-8')
    storage.load_jobs()
    _p = storage.take_load_problems()
    check(f'jobs.json containing {_label} is reported, not silently empty',
          len(_p) == 1 and 'wrong shape' in _p[0], _p)

storage.SETTINGS_PATH.write_text('[]', encoding='utf-8')
_s = storage.load_settings()
_p = storage.take_load_problems()
check('a wrong-shape settings.json is reported', len(_p) == 1 and 'settings.json' in _p[0], _p)
check('  ...and says the API keys are missing', 'API keys' in _p[0], _p[0])
check('  ...while still returning a usable empty dict', _s == {}, _s)

storage.APPLICATIONS_PATH.write_text('{}', encoding='utf-8')
storage.load_applications()
_p = storage.take_load_problems()
check('a wrong-shape applications.json is reported',
      len(_p) == 1 and 'applications.json' in _p[0], _p)

# -- partly damaged: some rows survive, and that is still worth saying ----------------
storage.JOBS_PATH.write_text('[{"id": "ok"}, 5, null, "x"]', encoding='utf-8')
_jobs = storage.load_jobs()
_p = storage.take_load_problems()
check('the good rows of a partly damaged jobs.json are kept', len(_jobs) == 1, _jobs)
check('  ...and the dropped ones are reported', len(_p) == 1 and '3 entry' in _p[0], _p)

# -- a healthy file must stay silent, or the red lines stop meaning anything ----------
storage.save_jobs([{'id': 'a', 'title': 'T'}])
storage.load_jobs()
storage.save_settings({'apify_token': 'x'})
storage.load_settings()
storage.save_applications([])
storage.load_applications()
check('a healthy read reports nothing at all', storage.take_load_problems() == [])

# -- a missing file is not a problem either: that is a first run ----------------------
storage.JOBS_PATH.unlink()
check('a missing jobs.json returns empty', storage.load_jobs() == [])
check('  ...and is not reported as damage', storage.take_load_problems() == [])


section('3.x  the search checkpoint -- surviving a crash mid-run')

# Why this exists: a three-hour German search was killed by a segmentation fault inside a C
# library, part-way through fetching the 722 postings it had just found. No traceback, no
# chance to catch it -- and every listing collected went with it, because run_search held
# the whole run in memory and wrote nothing until it returned. Three hours and $6.40 of
# Apify credit. The only defence against a crash that cannot be caught is to have already
# written the rows down.

from app.pipeline import checkpoint as _checkpoint  # noqa: E402

_rows = [{'title': 'Werkstudent Data Science', 'url': 'https://example.invalid/1'},
         {'title': 'Masterarbeit KI', 'url': 'https://example.invalid/2'}]
_checkpoint.save('search pass 2 of 6', _rows)
_back = storage.load_search_checkpoint()
check('a checkpoint survives to be read back', bool(_back), _back)
check('  ...with the stage it died in', _back['stage'] == 'search pass 2 of 6', _back['stage'])
check('  ...and every listing', _back['count'] == 2 and len(_back['rows']) == 2, _back['count'])
check('  ...intact', _back['rows'][0]['title'] == 'Werkstudent Data Science')

# A finished search removes its own, and THAT is what gives the file its meaning: one found
# at startup means the last search did not finish.
_checkpoint.clear()
check('a finished search clears its checkpoint', storage.load_search_checkpoint() is None)

# The rule that matters most: this is insurance, and insurance that can cost you the thing
# it insures is worse than none. Nothing here may ever raise into the search.
check_no_raise('an unserialisable row never breaks the search',
               lambda: _checkpoint.save('x', [object()]))
storage.SEARCH_CHECKPOINT_PATH.write_text('{ not json', encoding='utf-8')
check('a corrupt checkpoint reads as nothing rather than raising',
      storage.load_search_checkpoint() is None)
check('  ...and is reported rather than swallowed', bool(storage.take_load_problems()))
check_no_raise('clearing a checkpoint that is not there is fine', _checkpoint.clear)


section('3.bank  the Bank -- the pool a Filter reads from and can never eat')
# Why this exists: jobs.json holds what the LAST Filter kept. Before the Bank, running the
# Filter a second time -- for another Level, or for Not Remote -- re-filtered the survivors
# of the first run, so the only way back to the full pool was to pay Apify for the same
# search again. Everything below is that guarantee, stated as tests.
storage.clear_jobs()
check('a Bank that was never written reads as nothing, not as a crash',
      storage.load_bank() == ([], ''), storage.load_bank())
storage.clear_bank()
check('an emptied Bank reads as no listings', storage.load_bank()[0] == [])
_pool = [{'title': 'Data Scientist', 'url': 'https://example.invalid/1'},
         {'title': 'Senior Data Scientist', 'url': 'https://example.invalid/2'},
         {'title': 'Junior Data Scientist', 'url': 'https://example.invalid/3'}]
check('a search banks its whole pool', storage.add_to_bank(_pool) == 3)
_rows, _when = storage.load_bank()
check('  ...and it reads back intact', len(_rows) == 3 and _rows[0]['title'] == 'Data Scientist')
check('  ...with the date it was searched', _when[:2] == '20', _when)

# The guarantee itself: a Filter saves its survivors, and the Bank does not change.
storage.save_jobs([_pool[2]])
_rows, _when = storage.load_bank()
check('a Filter that keeps 1 of 3 leaves all 3 in the Bank', len(_rows) == 3, len(_rows))
check('  ...while the saved listings are the survivors', len(storage.load_jobs()) == 1)

# Re-searching the same city must not double the Bank, and the newest copy of a posting
# wins -- it is the one whose description was just read.
_again = [{'title': 'Data Scientist', 'url': 'https://example.invalid/1',
           'description': 'freshly enriched'},
          {'title': 'Machine Learning Engineer', 'url': 'https://example.invalid/4'}]
check('a second search adds only what is new', storage.add_to_bank(_again) == 4)
_rows, _when = storage.load_bank()
_first = [j for j in _rows if j['url'].endswith('/1')]
check('  ...no posting is banked twice', len(_first) == 1, len(_first))
check('  ...and the newer copy wins', _first[0].get('description') == 'freshly enriched')
check('  ...newest first', _rows[0]['url'].endswith('/1'), _rows[0]['url'])

# Same forgiveness as jobs.json: this file is the only copy of what a search paid for.
storage.take_load_problems()
storage.BANK_PATH.write_text('{ not json', encoding='utf-8')
check('a corrupt Bank reads as empty rather than raising', storage.load_bank() == ([], ''))
check('  ...and is reported, not swallowed', bool(storage.take_load_problems()))
storage.BANK_PATH.write_text('["not", "a", "bank"]', encoding='utf-8')
check('a Bank of the wrong shape reads as empty', storage.load_bank() == ([], ''))
check('  ...and is reported too', bool(storage.take_load_problems()))
storage.BANK_PATH.write_text('{"saved_at": "x", "rows": [{"url": "u"}, 7, null]}',
                             encoding='utf-8')
_rows, _when = storage.load_bank()
check('a damaged row is dropped, not the whole pool', len(_rows) == 1, len(_rows))
check('  ...and that too is reported', bool(storage.take_load_problems()))
check_no_raise('banking an empty search is fine', lambda: storage.add_to_bank([]))



# --------------------------------------------------------------------- 3.signature ----
# The user's rule for the Filter dialog: re-filtering with the same choices shows the previous
# answer instead of paying for it again, and changing ANY one of them redoes the work.
#
# So this module has exactly one way to be wrong that matters -- saying two runs are the same
# when they are not -- and it costs either a stale answer or a wasted Claude bill. Every
# input is tested for making a difference, one at a time.
from app.pipeline import filter_signature as _sig

_BASE = {'search_title': 'Data Science', 'search_level': 'junior',
         'search_work_mode': 'remote', 'countries': ['Germany'], 'cities': [],
         'date_range': 'anyTime', 'min_match_percent': 0, 'categories': [],
         'sponsorship': '', 'use_claude': True}


def _sign(**overrides):
    return _sig.filter_signature(dict(_BASE, **overrides), 'pool-1', 'resume-1', 'prompt-1')


check('the same choices give the same signature', _sign() == _sign())
check('  ...and it is a hex digest', len(_sign()) == 64 and all(c in '0123456789abcdef'
                                                               for c in _sign()))

# Every single choice must move it. A key added to the dialog and forgotten here would
# silently reuse the previous answer, which is this module's one real failure mode.
for _key, _other in (('search_title', 'Data Engineering'),
                     ('search_level', 'senior'),
                     ('search_work_mode', 'not_remote'),
                     ('countries', ['Germany', 'Austria']),
                     ('cities', ['Berlin']),
                     ('date_range', 'pastWeek'),
                     ('min_match_percent', 50),
                     ('categories', ['Internship']),
                     ('sponsorship', 'Yes'),
                     ('use_claude', False)):
    check('changing %s changes the signature' % _key, _sign(**{_key: _other}) != _sign(),
          _key)

# And the three things outside the dialog that decide whether an answer is still valid.
check('a new pool changes it',
      _sig.filter_signature(_BASE, 'pool-2', 'resume-1', 'prompt-1') != _sign())
check('a new resume changes it',
      _sig.filter_signature(_BASE, 'pool-1', 'resume-2', 'prompt-1') != _sign())
check('an edited prompt changes it',
      _sig.filter_signature(_BASE, 'pool-1', 'resume-1', 'prompt-2') != _sign())

# What must NOT change it, because the user picked the same thing either way.
check('the order of ticked countries does not change it',
      _sign(countries=['Austria', 'Germany']) == _sign(countries=['Germany', 'Austria']))
check('  ...nor does surrounding whitespace', _sign(countries=[' Germany ']) == _sign())
check('  ...nor an empty extra entry', _sign(countries=['Germany', '']) == _sign())
check('  ...nor a number given as text', _sign(min_match_percent='0') == _sign())

# The pool fingerprint: what a new search does to it, and what a re-fetch does not.
_pool = [{'url': 'https://a.invalid/1'}, {'url': 'https://a.invalid/2'}]
check('the same pool fingerprints the same',
      _sig.pool_fingerprint(_pool) == _sig.pool_fingerprint(list(reversed(_pool))))
check('a listing added changes it',
      _sig.pool_fingerprint(_pool + [{'url': 'https://a.invalid/3'}])
      != _sig.pool_fingerprint(_pool))
check('a listing removed changes it',
      _sig.pool_fingerprint(_pool[:1]) != _sig.pool_fingerprint(_pool))
check('a re-fetched description does NOT change it',
      _sig.pool_fingerprint([dict(r, description='new text') for r in _pool])
      == _sig.pool_fingerprint(_pool))
check('an empty pool has a fingerprint of its own',
      _sig.pool_fingerprint([]) != _sig.pool_fingerprint(_pool))

# The Log line the user reads to know what he is looking at.
check('describe names the level and the mode',
      'Junior' in _sig.describe(_BASE) and 'Remote' in _sig.describe(_BASE))
check('  ...and says Not Remote when that is what was chosen',
      'Not Remote' in _sig.describe(dict(_BASE, search_work_mode='not_remote')))
check('  ...and names the countries', 'Germany' in _sig.describe(_BASE))
check('  ...and stays readable with no choices at all',
      _sig.describe({}) == 'everything')
check('  ...and mentions a match floor only when one is set',
      '%' not in _sig.describe(_BASE)
      and '50%' in _sig.describe(dict(_BASE, min_match_percent=50)))



# ------------------------------------------------------------------------- 3.by-hand ----
section('3.by-hand  an application the user typed in himself')
# [owner's note: an application may have been made on LinkedIn and need adding by hand] -- he
# applies to things RoleHound never found, and a record of what he has applied to is only
# useful if it is all of it. The design decision under test: a hand-entered application goes
# through add_application like every other one, so there is ONE record shape. If it did not,
# the status menu, the documents folder, Remove and the Excel export would each need to know
# about a second kind of row, and the two definitions would drift the first time a field was
# added -- which has already happened once in this very function's curated dict.
from datetime import datetime as _hand_dt                                # noqa: E402

_today = _hand_dt.now().strftime('%d/%m/%Y')
_hand = storage.add_application(
    {'title': 'Data Scientist', 'company': 'Adyen', 'country': 'Netherlands',
     'location': 'Amsterdam', 'url': 'https://www.linkedin.com/jobs/view/123',
     'platform': 'LinkedIn', 'Category': 'Internship', 'sponsorship_visa': 'Yes',
     'description': 'Applied through LinkedIn Easy Apply.', 'added_by_hand': True},
    [], '17/04/2026')
check('a hand-entered application is saved', bool(_hand.get('id')))
check('  ...on the day he says he applied, not today',
      _hand['apply_date'] == '17/04/2026', _hand['apply_date'])
check('  ...and is marked as entered by hand', _hand['added_by_hand'] is True)
check('  ...with the same fields as any other record',
      {'title', 'company', 'country', 'status', 'documents', 'url'} <= set(_hand),
      sorted(_hand))
check('  ...starting in the same status as any other', _hand['status'] == 'Processing')
check('  ...and the Type column has something to show',
      _hand['category'] == 'Internship', _hand['category'])
check('  ...so the page loads it like the rest',
      any(r['id'] == _hand['id'] for r in storage.load_applications()))

# An application made through the app must be unchanged by any of this.
_normal = storage.add_application({'title': 'Data Engineer', 'company': 'Booking'}, [])
check('an ordinary application still defaults to today',
      _normal['apply_date'] == _today, _normal['apply_date'])
check('  ...and is not marked as entered by hand', _normal['added_by_hand'] is False)
check('a blank date falls back to today, rather than writing an empty one',
      storage.add_application({'title': 'X'}, [], '   ')['apply_date'] == _today)

# Documents attached by hand are copied into the application's own folder, so Download works
# on this row for the same reason it works on the others.
_hand_doc = Path(tmp) / 'cover_letter.pdf'
_hand_doc.write_bytes(b'%PDF-1.4 a real enough file')
_hand_docs = storage.add_application({'title': 'With papers', 'added_by_hand': True},
                                     [str(_hand_doc)], '01/01/2026')
check('documents attached by hand are copied in', len(_hand_docs['documents']) == 1,
      _hand_docs['documents'])
check('  ...into this application\u2019s own folder, not left where they were',
      str(_hand_docs['id']) in _hand_docs['documents'][0], _hand_docs['documents'][0])
check('  ...and the copy really exists',
      Path(_hand_docs['documents'][0]).exists(), _hand_docs['documents'][0])


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



# ------------------------------------------------------------------------ 3.doc-text ----
section('3.doc-text  reading the words out of a PDF or Word file')
# This machinery was private to the résumé module until the hand-entered application needed
# it too -- its job description comes in as a PDF. Two copies of "how do you get the words
# out of a PDF" would drift the first time one was fixed, which is exactly what happened with
# Rule 5 across ten prompt files. So it lives in one module now. The résumé's own behaviour
# is unchanged (suite 4.40 proves that); this section proves the shared reader itself.
from app import doc_text as _dt_mod                                       # noqa: E402
from app import resume as _dt_resume                                      # noqa: E402

_dt_dir = Path(tmp) / 'doc_text'
_dt_dir.mkdir(parents=True, exist_ok=True)


def _refused(path):
    """The message a refused file produces, or None if it was accepted."""
    try:
        _dt_mod.read_document_text(path)
    except _dt_mod.DocumentError as exc:
        return str(exc)
    return None


_dt_pdf = _dt_dir / 'advert.pdf'
_dt_pdf.write_bytes(_make_pdf_bytes('Data Scientist at Adyen, fully remote in English.'))
_dt_kind, _dt_text = _dt_mod.read_document_text(_dt_pdf)
check('a real PDF is read as a PDF', _dt_kind == 'pdf', _dt_kind)
check('  ...and its words come back exactly', 'Data Scientist at Adyen' in _dt_text,
      _dt_text[:100])

_dt_txt = _dt_dir / 'advert.txt'
_dt_txt.write_text('Just a text file.', encoding='utf-8')
check('a .txt file is refused', _refused(_dt_txt) is not None)
check('  ...and the message names the file it means',
      'advert.txt' in (_refused(_dt_txt) or ''), _refused(_dt_txt))

_dt_fake = _dt_dir / 'fake.pdf'
_dt_fake.write_text('Plain text wearing a .pdf name.', encoding='utf-8')
check('a text file renamed .pdf is refused on what is inside it, not its name',
      _refused(_dt_fake) is not None, _refused(_dt_fake))

_dt_doc = _dt_dir / 'old.doc'
_dt_doc.write_bytes(b'\xd0\xcf\x11\xe0 an old Word file')
check('an old .doc is refused, with what to do about it',
      'Save As' in (_refused(_dt_doc) or ''), _refused(_dt_doc))

_dt_empty = _dt_dir / 'empty.pdf'
_dt_empty.write_bytes(b'')
check('an empty file is refused', 'empty' in (_refused(_dt_empty) or '').lower(),
      _refused(_dt_empty))
check('a file that is not there is refused, not crashed on',
      _refused(_dt_dir / 'nothing_here.pdf') is not None)

check('tidy collapses blank runs without touching the words',
      _dt_mod.tidy('  Data   Scientist \n\n\n\n  at Adyen  ') == 'Data Scientist\n\nat Adyen',
      repr(_dt_mod.tidy('  Data   Scientist \n\n\n\n  at Adyen  ')))
check('  ...and nothing at all tidies to nothing, rather than raising',
      _dt_mod.tidy(None) == '')

# The alias that keeps every existing caller working after the move.
check('resume.ResumeError is the same class, so every except still catches it',
      _dt_resume.ResumeError is _dt_mod.DocumentError)
check('  ...and resume still publishes what it always published',
      _dt_resume.ACCEPTED_EXTENSIONS == ('.pdf', '.docx')
      and _dt_resume.MAX_BYTES == _dt_mod.MAX_BYTES)

# The résumé keeps its own extra rule on top of the shared reader: a file with almost no
# text in it is a scanned CV, and cannot be judged against. The shared reader accepts it,
# because "can these words be read" is a different question from "is this a usable résumé".
_dt_thin = _dt_dir / 'scanned.pdf'
_dt_thin.write_bytes(_make_pdf_bytes('CV'))
check('the shared reader accepts a nearly empty PDF', _refused(_dt_thin) is None)
try:
    _dt_resume.read_resume_file(_dt_thin)
    _thin_message = None
except _dt_resume.ResumeError as _exc:
    _thin_message = str(_exc)
check('  ...but the résumé still refuses it as a scan', _thin_message is not None)
check('  ...saying what to do about it', 'scanned' in (_thin_message or ''), _thin_message)

sys.exit(summary('Suite 3 -- storage'))
