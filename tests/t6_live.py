"""Suite 6 -- LIVE. Real network calls to every free API, a real Claude screening, and
one real (small, budget-aware) Apify actor run. Costs real money; kept minimal.

Uses the PACKAGED app's credentials (%APPDATA%\\JobDesk\\settings.json) -- the dev
data/settings.json points at an Apify account that has already hit its monthly cap.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, check_no_raise, isolated_storage, summary
from app import pipeline as p, storage

isolated_storage()
CFG = json.loads((Path(os.environ['APPDATA']) / 'JobDesk' / 'settings.json').read_text(encoding='utf-8'))
APIFY = CFG.get('apify_token')
CLAUDE = CFG.get('anthropic_api_key')

section('6.1  free JSON APIs -- real calls, real row shapes')
LIVE = [
    ('arbetsformedlingen.se', lambda: p._fetch_arbetsformedlingen_se('Data Scientist')),
    ('arbeitsagentur.de', lambda: p._fetch_arbeitsagentur_de('Data Scientist', None)),
    ('europa.eu (EURES)', lambda: p._fetch_eures('Data Scientist', ['de'])),
    ('remotive.com', lambda: p._fetch_remotive('Data Scientist')),
    ('remoteok.com', lambda: p._fetch_remoteok('Data Scientist')),
    ('arbeitnow.com', lambda: p._fetch_arbeitnow_sponsorship('Data Scientist')),
    ('swissdevjobs.ch', lambda: p._fetch_swissdevjobs('Data Scientist')),
    ('jobs.ch', lambda: p._fetch_jobcloud('jobs.ch', 'Data Scientist')),
    ('jobup.ch', lambda: p._fetch_jobcloud('jobup.ch', 'Data Scientist')),
]
if CFG.get('reed_uk_api_key'):
    LIVE.append(('reed.co.uk', lambda: p._fetch_reed_uk('Data Scientist', CFG['reed_uk_api_key'])))

# Sources confirmed dead, with evidence. A live suite that keeps asserting these work
# reports a failure every run for something nobody can fix, which trains you to ignore it
# -- so they are asserted to fail GRACEFULLY instead: a clear message, no crash, and the
# rest of the search unaffected. Remove an entry here the day the site comes back.
KNOWN_DEAD = {
    # swissdevjobs.ch answers HTTP 200 but serves an HTML sign-up page, and the whole
    # site redirects to devitjobs.jobcopilot.com/signup?utm_source=sdj_old -- acquired or
    # shut down and folded into JobCopilot.
    'swissdevjobs.ch': 'jobcopilot',
}

# Sources whose feed is "the newest N jobs anywhere" rather than a search index: a term can
# legitimately match nothing today and everything tomorrow. Value is how to prove the feed
# itself still works.
MAY_MATCH_NOTHING = {
    'remoteok.com': lambda: p._fetch_remoteok('engineer'),
}

all_live_rows = []
for name, fn in LIVE:
    if name in KNOWN_DEAD:
        try:
            rows = fn()
            check(f'{name}: is back from the dead (remove it from KNOWN_DEAD)',
                  len(rows) > 0, f'{len(rows)} rows')
        except Exception as e:
            check(f'{name}: dead source fails gracefully, not with a raw parse error',
                  not isinstance(e, ValueError) or 'json' not in type(e).__name__.lower(),
                  f'{type(e).__name__}: {str(e)[:90]}')
            check(f'{name}: and the failure says what happened',
                  KNOWN_DEAD[name] in str(e).lower() or 'shut down' in str(e).lower(),
                  str(e)[:110])
        time.sleep(0.4)
        continue
    try:
        rows = fn()
        ok = check(f'{name}: real call succeeded', True)
        if not rows and name in MAY_MATCH_NOTHING:
            # remoteok.com's feed is the hundred newest remote jobs worldwide, whatever they
            # happen to be -- on a real run it held no Data Scientist at all while "engineer"
            # returned 44. Asserting a fixed term always matches makes this fail for a
            # perfectly healthy source, so the question becomes "is the feed alive": if a
            # common word finds nothing either, the source really is broken.
            rows = MAY_MATCH_NOTHING[name]()
            check(f'{name}: the feed is alive (the term simply matched nothing)',
                  len(rows) > 0, f'{len(rows)} rows for the fallback term')
        check(f'{name}: returned real listings', len(rows) > 0, f'{len(rows)} rows')
        if rows:
            r = rows[0]
            check(f'{name}: row shape complete',
                  all(k in r for k in ('title', 'company', 'country', 'url', 'description', 'platform')),
                  sorted(set(('title', 'company', 'country', 'url', 'description', 'platform')) - set(r)))
            check(f'{name}: reports its real source', r['platform'] == name.split(' ')[0]
                  or r['platform'] == name, r.get('platform'))
            check(f'{name}: url is real', str(r.get('url', '')).startswith('http'), r.get('url'))
            all_live_rows.extend(rows[:5])
        print(f'         -> {len(rows)} real rows, e.g. {str(rows[0].get("title"))[:56]!r}' if rows else '')
    except Exception as e:
        check(f'{name}: real call succeeded', False, f'{type(e).__name__}: {str(e)[:140]}')
    time.sleep(0.4)

section('6.2  real rows survive the real Filter')
check('collected real rows from several sources', len(all_live_rows) > 10, len(all_live_rows))
# The sources above were asked for "Data Scientist", so that is the job title in the Search
# box for this run -- otherwise the title check correctly removes everything they returned.
kept, removed, flagged = p.reapply_filters([dict(r) for r in all_live_rows],
                                            progress_cb=None, anthropic_api_key=None,
                                            search_title='Data Scientist')
check('Filter ran on real data without crashing', isinstance(kept, list))
print(f'         -> {len(all_live_rows)} real rows in, {len(kept)} kept, {removed} removed by rules')
check('some real listings survive (the pipeline is not eating everything)', len(kept) > 0, len(kept))
check('every survivor has a sponsorship_visa verdict',
      all(k.get('sponsorship_visa') in ('Yes', 'Unknown', "Employer's Discretion") for k in kept))
check('every survivor has a Category', all(k.get('Category') for k in kept))
thin_kept = [k for k in kept if p.is_true_flag(k.get('thin_description'))]
print(f'         -> {len(thin_kept)} of the survivors came from thin-description sources')

section('6.3  real save/reload of real data')
merged = storage.prepend_jobs([dict(k) for k in kept])
raw = storage.JOBS_PATH.read_text(encoding='utf-8')
check_no_raise('real jobs.json is strict-valid JSON',
               lambda: json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c))))
check('everything round-trips', len(storage.load_jobs()) == len(merged))
from app import excel_export
import io as _io
check_no_raise('real data exports to Excel',
               lambda: excel_export.build_jobs_workbook(storage.load_jobs()).save(_io.BytesIO()))

section('6.4  live Claude screening, both parts')
if not CLAUDE:
    check('Claude key configured', False, 'no key -- skipping')
else:
    import anthropic
    from app import resume as _resume

    # Claude reads every fact about the candidate from the résumé, so a live run needs one.
    # A made-up one, written here: the real résumé is Sina's and belongs in the app's data
    # folder, not in a test. isolated_storage() has already moved that folder somewhere
    # temporary, so this cannot touch his.
    import docx as _docx
    _fixture = Path(storage.DATA_DIR) / 'fixture_cv.docx'
    _doc = _docx.Document()
    for _line in ('Jane Example - Data Scientist',
                  'Lives in Lyon, France. French citizen, no visa needed in the EU.',
                  'Languages: English C1, French native. No German.',
                  'Experience: 2 years of Python, SQL, pandas and scikit-learn on retail '
                  'forecasting models, plus ETL pipelines in Airflow.',
                  'Skills: Python, SQL, pandas, scikit-learn, PyTorch, Airflow, dbt, Docker.',
                  'Education: M.Sc. Data Science, Université de Lyon, expected 2027.'):
        _doc.add_paragraph(_line)
    _doc.save(str(_fixture))
    _resume.save_resume(_fixture)
    check('a résumé is in place for the live run', len(_resume.load_resume_text()) > 200)

    client = anthropic.Anthropic(api_key=CLAUDE)
    real = kept[0] if kept else {'title': 'Data Scientist', 'description': 'Remote role.'}
    drop, reason, match, err, employer = p.claude_screen_one(client, real)
    check('live claude_screen_one returned no error', err is None, err)
    check('drop is a real bool', isinstance(drop, bool))
    # Part one decides and no longer scores -- the Match % is part two's, against the résumé.
    check('part one returns no score of its own', match is None, match)
    print(f'         -> real listing {str(real.get("title"))[:44]!r}: drop={drop} reason={reason}')

    # Part two, live: the same batch the Filter sends, over a few real listings.
    _for_match = [dict(k, **{p.search_title.LEVEL_ROW_KEY: 'junior',
                             p.search_title.ROW_KEY: 'Data Scientist'}) for k in kept[:3]]
    _flagged_live = []
    p.step_resume_match(_for_match, _flagged_live, CLAUDE)
    _scores = [j.get('claude_match') for j in _for_match]
    _verdicts = [j.get('apply_verdict') for j in _for_match]
    print('         -> résumé match %s, verdicts %s' % (_scores, _verdicts))
    check('every listing comes back with a real percentage',
          all(isinstance(s, int) and 0 <= s <= 100 for s in _scores), _scores)
    check('  ...and an apply / check / skip verdict',
          all(v in ('apply', 'check', 'skip') for v in _verdicts), _verdicts)
    check('  ...and says what fits or what is missing',
          all((j.get('resume_strengths') or j.get('resume_gaps')) for j in _for_match),
          [(j.get('resume_strengths'), j.get('resume_gaps')) for j in _for_match])
    check('  ...and stores a cache key, so a re-run is free',
          all(j.get('resume_match_cache_key') for j in _for_match))

    sample = [dict(k) for k in kept[:3]]
    # Record every screen's error text. A live run failed this check twice with nothing but
    # `[True, True, False]` to go on, and reproducing it outside the full suite proved
    # impossible -- three separate attempts all passed. The error string is the one piece
    # of evidence that makes the next failure diagnosable instead of a guessing game.
    from app.pipeline import filters as _filters_mod
    _screen_errors = []
    _real_screen = _filters_mod.claude_screen_one

    def _watched_screen(_client, _job):
        _result = _real_screen(_client, _job)
        if _result[3]:
            _screen_errors.append(f'{str(_job.get("title"))[:40]}: {str(_result[3])[:160]}')
        return _result

    _filters_mod.claude_screen_one = _watched_screen
    try:
        k2, _, f2 = p.reapply_filters(sample, progress_cb=None, anthropic_api_key=CLAUDE,
                                      search_title='Data Scientist')
    finally:
        _filters_mod.claude_screen_one = _real_screen
    check('full Filter with a live Claude key completes', isinstance(k2, list))
    check('every screened listing got a cache key',
          all(j.get('claude_screen_cache_key') for j in k2),
          _screen_errors or [bool(j.get('claude_screen_cache_key')) for j in k2])
    calls = {'n': 0}
    real_create = client.messages.create
    # claude_screen.py does its own `import anthropic`, and every module shares the one
    # module object, so patching the real module reaches it. `p.anthropic` no longer
    # exists now that the pipeline is a package rather than a single module.
    import anthropic as _anthropic
    orig_cls = _anthropic.Anthropic

    class Counting:
        """Counts both kinds of billed call: one listing at a time, and a queued batch --
        part two sends only batches, so counting messages.create alone would call a paid
        run free."""

        def __init__(self, api_key=None):
            self._c = orig_cls(api_key=api_key)
            self.messages = self

        @property
        def batches(self):
            return self

        def create(self, **kw):
            calls['n'] += 1
            if 'requests' in kw:                     # messages.batches.create
                return self._c.messages.batches.create(**kw)
            return self._c.messages.create(**kw)

        def retrieve(self, *a, **kw):
            return self._c.messages.batches.retrieve(*a, **kw)

        def results(self, *a, **kw):
            return self._c.messages.batches.results(*a, **kw)

        def cancel(self, *a, **kw):
            return self._c.messages.batches.cancel(*a, **kw)

    _anthropic.Anthropic = Counting
    try:
        p.reapply_filters([dict(j) for j in k2], progress_cb=None, anthropic_api_key=CLAUDE,
                          search_title='Data Scientist')
    finally:
        _anthropic.Anthropic = orig_cls
    check('a second Filter run makes ZERO new Claude calls, in either part (cache works live)',
          calls['n'] == 0, calls['n'])

section('6.5  live Apify -- one small real actor run')
if not APIFY:
    check('Apify token configured', False, 'no token -- skipping')
else:
    from apify_client import ApifyClient
    import requests
    client = ApifyClient(APIFY)
    check_no_raise('Apify token is valid', lambda: client.user().get())
    lim = requests.get('https://api.apify.com/v2/users/me/limits',
                       headers={'Authorization': f'Bearer {APIFY}'}, timeout=20).json()['data']
    used = lim['current'].get('monthlyUsageUsd', 0)
    cap = lim['limits'].get('maxMonthlyUsageUsd', 0)
    print(f'         -> Apify usage ${used:.2f} of ${cap:.2f}')
    check('budget remains for a real run', cap - used > 0.3, f'${cap - used:.2f} left')
    check_no_raise('pre-flight actor check is free and works',
                   lambda: p._preflight_check_google(client, ['Italy'], [], ['google'], None))
    if cap - used > 0.3:
        run_input = {'queries': '"Data Scientist" jobs Italy site:infojobs.net',
                     'maxPagesPerQuery': 1, 'websiteContentScraper': {'enable': False}}
        t0 = time.monotonic()
        try:
            run = p._run_actor_cancellable(client, p.GOOGLE_SEARCH_ACTOR, run_input)
            status = run.get('status')
            check('real Google actor run SUCCEEDED', status == 'SUCCEEDED', status)
            ds = p._get_default_dataset_id(run)
            check('dataset id resolved via the helper', bool(ds), ds)
            pages = list(client.dataset(ds).iterate_items())
            check('real pages returned', len(pages) > 0, len(pages))
            if pages:
                term = p._search_term_from_page(pages[0])
                loc_type, loc = p._location_from_search_term(term)
                check('real query attributed to the right country',
                      (loc_type, loc) == ('country', 'Italy'), (loc_type, loc))
                results = pages[0].get('organicResults') or []
                check('real organic results present', len(results) > 0, len(results))
                normalized = [p.normalize_google_search_result(r, loc_type, loc)
                              for r in results[:3] if not p._is_excluded_job_board(r.get('url'))]
                check('real results normalize cleanly',
                      all(n.get('url') and n.get('country') == 'Italy' for n in normalized),
                      normalized[:1])
            print(f'         -> real actor run in {time.monotonic() - t0:.0f}s, '
                  f'cost ${run.get("usageTotalUsd", 0) or 0:.4f}')
        except Exception as e:
            check('real Google actor run SUCCEEDED', False, f'{type(e).__name__}: {str(e)[:140]}')

sys.exit(summary('Suite 6 -- LIVE APIs'))
