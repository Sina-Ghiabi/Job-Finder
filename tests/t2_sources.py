"""Suite 2 -- every data source's row shape, built by the REAL fetcher code with
mocked HTTP, then pushed through the REAL Filter."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, check_no_raise, isolated_storage, summary
from app import pipeline as p

isolated_storage()

REQUIRED_KEYS = {'title', 'company', 'location', 'country', 'posted_date', 'url', 'description', 'platform'}


class Resp:
    """A fake requests response.

    `headers` carries a JSON content-type by default because fetchers legitimately check
    it -- _fetch_swissdevjobs does, to tell a real API response apart from the HTML
    sign-up page that domain now serves. A mock missing a field the real object always
    has produces a failure that looks like a code bug and is not one.
    """

    def __init__(self, payload, status=200, content_type='application/json'):
        self._p = payload
        self.status_code = status
        self.headers = {'content-type': content_type}
        self.text = payload if isinstance(payload, str) else ''

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


# The pipeline is a package now, and each submodule does its own `import requests`.
# Patching the requests MODULE itself still reaches all of them, because they all hold
# a reference to the same module object -- which is what these helpers always really
# relied on, they just used to spell it `p.requests`.
import requests as _requests
from pathlib import Path


def with_get(payload):
    orig = _requests.get
    _requests.get = lambda *a, **k: Resp(payload)
    return orig


def with_post(payload):
    orig = _requests.post
    _requests.post = lambda *a, **k: Resp(payload)
    return orig


def validate(name, rows, expect_platform=None, expect_thin=None, expect_country=None):
    check(f'{name}: returned rows', bool(rows), f'{len(rows)} rows')
    if not rows:
        return
    r = rows[0]
    missing = REQUIRED_KEYS - set(r)
    check(f'{name}: has every required key', not missing, sorted(missing))
    if expect_platform is not None:
        check(f'{name}: platform == {expect_platform!r}', r.get('platform') == expect_platform,
              r.get('platform'))
    if expect_thin is not None:
        check(f'{name}: thin_description == {expect_thin}',
              p.is_true_flag(r.get('thin_description')) is expect_thin, r.get('thin_description'))
    if expect_country is not None:
        check(f'{name}: country == {expect_country!r}', r.get('country') == expect_country,
              r.get('country'))
    check(f'{name}: url is a real string', isinstance(r.get('url'), str) and r['url'].startswith('http'),
          r.get('url'))
    check(f'{name}: never tags itself google',
          r.get('platform') != 'google' or name.startswith('crawler'), r.get('platform'))


# ============================================================ arbeitsformedlingen
section('2.1  arbetsformedlingen.se (Sweden)')
o = with_get({'hits': [{'id': '1', 'headline': 'Data Scientist',
                        'employer': {'name': 'Svensk AB'},
                        'workplace_address': {'municipality': 'Stockholm'},
                        'publication_date': '2026-08-01',
                        'webpage_url': 'https://arbetsformedlingen.se/1',
                        'description': {'text': 'A full job description here. ' * 8}}]})
try:
    rows = p._fetch_arbetsformedlingen_se('Data Scientist')
    validate('arbetsformedlingen', rows, 'arbetsformedlingen.se', False, 'Sweden')
finally:
    _requests.get = o

# ============================================================ arbeitsagentur
section('2.2  arbeitsagentur.de (Germany, thin)')
o = with_get({'ergebnisliste': [
    {'referenznummer': 'X-1', 'stellenangebotsTitel': 'Data Scientist', 'firma': 'Jenoptik AG',
     'datumErsteVeroeffentlichung': '2026-08-01',
     'stellenlokationen': [{'adresse': {'ort': 'Jena'}}]},
    {'referenznummer': 'X-2', 'stellenangebotsTitel': 'Data Engineer', 'firma': '',
     'datumErsteVeroeffentlichung': '2026-08-02', 'stellenlokationen': []},
    {'stellenangebotsTitel': 'No referenznummer -- must be skipped', 'firma': 'X'},
]})
try:
    rows = p._fetch_arbeitsagentur_de('Data Scientist', None)
    validate('arbeitsagentur', rows, 'arbeitsagentur.de', True, 'Germany')
    check('arbeitsagentur: row without referenznummer skipped', len(rows) == 2, len(rows))
    # The job title in the Search box, set to what both rows are about: this section tests
    # that thin rows survive, not the title check, which Suite 1 tests on its own.
    kept, _, _ = p.reapply_filters([dict(r) for r in rows], progress_cb=None, anthropic_api_key=None,
                                   search_title='Data')
    check('arbeitsagentur: BOTH rows survive Filter (incl. the empty-firma one)',
          len(kept) == 2, f'{len(kept)} of 2')
finally:
    _requests.get = o

# ============================================================ jooble
section('2.3  jooble (thin, usage-counted)')
o = with_post({'jobs': [{'title': 'Data Scientist', 'company': 'Zalando', 'location': 'Berlin',
                         'link': 'https://de.jooble.org/jdp/1', 'updated': '2026-08-01',
                         'snippet': 'A truncated snippet of the job description here.'}]})
counted = []
try:
    rows = p._fetch_jooble('de', 'Germany', 'Data Scientist', 'k', on_request_sent=lambda: counted.append(1))
    validate('jooble', rows, 'de.jooble.org', True, 'Germany')
    check('jooble: usage callback fired exactly once', len(counted) == 1, len(counted))
    kept, _, _ = p.reapply_filters([dict(r) for r in rows], progress_cb=None, anthropic_api_key=None,
                                   search_title='Data Scientist')
    check('jooble: row survives Filter', len(kept) == 1, len(kept))
finally:
    _requests.post = o

# ============================================================ reed
section('2.4  reed.co.uk')
o = with_get({'results': [{'jobId': 99, 'jobTitle': 'Data Scientist', 'employerName': 'Reed Co',
                           'locationName': 'London', 'date': '01/08/2026',
                           'jobUrl': 'https://www.reed.co.uk/jobs/99',
                           'jobDescription': 'Fully remote role. ' * 12}]})
try:
    rows = p._fetch_reed_uk('Data Scientist', 'key')
    validate('reed', rows, 'reed.co.uk', False, 'United Kingdom')
finally:
    _requests.get = o

# ============================================================ eures
section('2.5  europa.eu (EURES)')
o = with_post({'jvs': [{'id': 'E1', 'title': 'Data Scientist',
                        'employer': {'name': 'EU Corp'}, 'creationDate': 1785000000000,
                        'locationMap': {'DE': ['x']},
                        'description': 'Fully remote EU role. ' * 10},
                       {'id': 'E2', 'title': 'Unknown country', 'locationMap': {'ZZ': []}}]})
try:
    rows = p._fetch_eures('Data Scientist', ['de'])
    validate('eures', rows, 'europa.eu (EURES)', False, 'Germany')
    check('eures: unmappable country row dropped, not guessed', len(rows) == 1, len(rows))
    check('eures: posted_date parsed from epoch millis',
          isinstance(rows[0]['posted_date'], str) and '2026' in rows[0]['posted_date'],
          rows[0]['posted_date'])
finally:
    _requests.post = o

# ============================================================ remotive / remoteok
section('2.6  remotive.com / remoteok.com')
o = with_get({'jobs': [{'title': 'Data Scientist', 'company_name': 'RemoteCo',
                        'candidate_required_location': 'Worldwide', 'publication_date': '2026-08-01',
                        'url': 'https://remotive.com/1', 'description': 'Remote role. ' * 12}]})
try:
    validate('remotive', p._fetch_remotive('Data Scientist'), 'remotive.com', False)
finally:
    _requests.get = o

o = with_get([{'legal': 'notice object with no id'},
              {'id': 'r1', 'position': 'Data Scientist', 'company': 'OkCo', 'location': 'Remote',
               'date': '2026-08-01', 'url': 'https://remoteok.com/1',
               'description': 'A remote data scientist role.', 'tags': ['data']},
              {'id': 'r2', 'position': 'Chef', 'company': 'X', 'description': 'cooking', 'tags': []}])
try:
    rows = p._fetch_remoteok('Data Scientist')
    validate('remoteok', rows, 'remoteok.com', False)
    check('remoteok: legal-notice object skipped and non-matching role filtered',
          len(rows) == 1, len(rows))
finally:
    _requests.get = o

# ============================================================ swissdevjobs / jobcloud
section('2.7  swissdevjobs.ch / JobCloud (both thin)')
o = with_get([{'name': 'Data Scientist', 'company': 'Sonar', 'actualCity': 'Geneva',
               'activeFrom': '2026-08-01', 'jobUrl': 'ds-sonar', 'technologies': ['Python'],
               'techCategory': 'Data', 'metaCategory': 'Data Scientist'}])
try:
    rows = p._fetch_swissdevjobs('Data Scientist')
    validate('swissdevjobs', rows, 'swissdevjobs.ch', True, 'Switzerland')
    kept, _, _ = p.reapply_filters([dict(r) for r in rows], progress_cb=None, anthropic_api_key=None,
                                   search_title='Data Scientist')
    check('swissdevjobs: survives Filter', len(kept) == 1, len(kept))
finally:
    _requests.get = o

for domain in ('jobs.ch', 'jobup.ch'):
    o = with_get({'documents': [{'id': '1', 'title': 'Data Scientist',
                                 'company': {'name': 'Roche'}, 'place': 'Basel',
                                 'publicationDate': '2026-08-01'}]})
    try:
        rows = p._fetch_jobcloud(domain, 'Data Scientist')
        validate(domain, rows, domain, True, 'Switzerland')
        check(f'{domain}: detail path is right',
              (f'/{"en/vacancies/detail" if domain == "jobs.ch" else "en/jobs/detail"}/') in rows[0]['url'],
              rows[0]['url'])
    finally:
        _requests.get = o

# ============================================================ arbeitnow
section('2.8  arbeitnow.com (sponsorship type-a)')
o = with_get({'data': [
    {'slug': 'a1', 'title': 'Data Scientist', 'company_name': 'BerlinCo', 'location': 'Berlin',
     'created_at': 1785000000, 'url': 'https://arbeitnow.com/a1',
     'description': 'Remote data scientist role. ' * 8, 'tags': []},
    {'slug': 'a2', 'title': 'Data Scientist', 'company_name': 'X', 'location': 'Atlantis',
     'url': 'https://arbeitnow.com/a2', 'description': 'data scientist', 'tags': []},
]})
try:
    rows = p._fetch_arbeitnow_sponsorship('Data Scientist')
    validate('arbeitnow', rows, 'arbeitnow.com', False, 'Germany')
    check('arbeitnow: unmappable location dropped, never guessed', len(rows) == 1, len(rows))
    check('arbeitnow: tags sponsorship_visa=Yes', rows[0].get('sponsorship_visa') == 'Yes')
finally:
    _requests.get = o

# ============================================================ cross-source invariants
section('2.9  cross-source invariants')
import io
# The pipeline is a package now, so these invariants have to be checked across every
# module in it, not one file -- and located relative to this test rather than by an
# absolute path that only existed on one machine.
_pkg = Path(__file__).resolve().parent.parent / 'app' / 'pipeline'
# rglob, not glob: search/ is a subpackage now, and its modules are exactly the ones
# these invariants are about.
src = '\n'.join(io.open(f, encoding='utf-8').read() for f in sorted(_pkg.rglob('*.py')))
code = '\n'.join(l.split('  #')[0] for l in src.split('\n') if not l.strip().startswith('#'))
check("only crawler rows still tag platform='google'", code.count("'platform': 'google'") == 3,
      code.count("'platform': 'google'"))
check('every thin source sets the flag', code.count("'thin_description': True") == 4,
      code.count("'thin_description': True"))
check('no fetcher sets was_translated', code.count("'was_translated':") == 0)

# ------------------------------------------------------------------- 2.first-page ----
# _paginate_rows kept whatever earlier pages returned when a later one failed, which is
# right. It did the same for page ONE, which is not: nothing has been collected yet, so
# there is nothing to protect, and the caller gets an empty list indistinguishable from a
# search that genuinely matched nothing.
#
# Found on 23 September 2026. EURES answered 990 rows in the morning and HTTP 403 in the
# afternoon (europa.eu redirects a blocked caller to sorry.ec.europa.eu), and the app
# reported neither -- just zero rows. That is O-7 in its worst direction: not a working
# source called broken, but a broken source called quiet.
_paginate = p.sources_apis._paginate_rows


def _page(answers):
    """A fake fetch_page: answers[i] is page i+1, and an Exception instance is raised."""
    def fetch(page):
        got = answers[page - 1] if page <= len(answers) else []
        if isinstance(got, Exception):
            raise got
        return got
    return fetch


_row = lambda n: {'url': 'https://example.invalid/%d' % n, 'title': 't', 'company': 'c'}

check_no_raise('pages that all work are read through',
               lambda: _paginate(_page([[_row(1)], [_row(2)], []])))
check('  ...and every row is kept',
      len(_paginate(_page([[_row(1)], [_row(2)], []]))) == 2)

# A later page failing keeps what the earlier ones gave.
check('a failure on page two keeps page one',
      len(_paginate(_page([[_row(1)], RuntimeError('boom')]))) == 1)

# Page one failing is the source failing, and it must say so.
_raised = None
try:
    _paginate(_page([RuntimeError('403 Forbidden')]))
except Exception as _e:
    _raised = _e
check('a failure on page ONE is raised, not swallowed', isinstance(_raised, RuntimeError),
      _raised)
check('  ...carrying the real reason', '403' in str(_raised), str(_raised))

# An empty first page is not a failure -- it is a search that matched nothing.
check('an empty first page is still an empty result, not an error',
      _paginate(_page([[]])) == [])


# --------------------------------------------------------------------- 2.timeouts ----
# remoteok.com has no search endpoint: one call returns its entire 623KB board. Measured five
# times in a row on a healthy connection it took 34.7s, 34.0s, 38.0s and 43.5s -- so the 30s
# ceiling it used to have, and the 15s the Health Check used, were both below the source's
# normal speed.
#
# That is worse than a slow source. It made a working one invisible: every real search dropped
# it silently, and the Health Check called it broken before nearly every run -- the same fault
# as O-7 wearing a different hat. Both numbers looked perfectly reasonable, which is why
# nobody questioned them; the measurement is what caught it.
import re  # noqa: E402
from app.pipeline.sources_apis import _REMOTEOK_TIMEOUT_SECONDS as _ROK  # noqa: E402

check('remoteok gets a ceiling above its measured worst case', _ROK >= 60, _ROK)
_apis = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'pipeline', 'sources_apis.py'), encoding='utf-8').read()
_pre = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'pipeline', 'preflight.py'), encoding='utf-8').read()
check('the fetcher uses the named constant, not a literal',
      '_REMOTEOK_API_URL, headers={\'User-Agent\': \'Mozilla/5.0\'},\n                        '
      'timeout=_REMOTEOK_TIMEOUT_SECONDS' in _apis)
check('  ...and so does the Health Check, so the two cannot disagree',
      'timeout=_REMOTEOK_TIMEOUT_SECONDS' in _pre)
check('  ...and no 15- or 30-second literal is left on a remoteok call',
      not re.search(r'_REMOTEOK_API_URL[^)]{0,160}timeout=(?:15|30)\b', _apis + _pre, re.S))

sys.exit(summary('Suite 2 -- data sources'))
