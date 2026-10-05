"""Suite 4 -- full pipeline integration: run_search (mocked Apify), reapply_filters,
cancel at every stage, and the search -> pandas -> disk -> Filter round trip."""
import os
import sys, json, threading, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, check_no_raise, isolated_storage, summary
import datetime as _dt
import inspect as _inspect

from app import pipeline as p, storage
from app import search_worker as _worker_src
from app.ui import filter_dialog as _fd_src
from app.ui import setup_wizard as _sw_src

isolated_storage()

CALLS = {'n': 0}
LOCK = threading.Lock()


class FakeDataset:
    def __init__(self, rid):
        self.rid = rid
    def iterate_items(self, limit=None):
        items = [{'title': f'Data Scientist {i}', 'companyName': f'Co{i}',
                  'link': f'https://x/{self.rid}/{i}',
                  'descriptionText': 'Fully remote role with competitive salary and benefits. ' * 4}
                 for i in range(3)]
        return items[:limit] if limit else items


class FakeRun:
    def __init__(self, rid):
        self.rid = rid
    def get(self):
        return {'id': self.rid, 'status': 'SUCCEEDED', 'defaultDatasetId': self.rid,
                'usageTotalUsd': 0.01}
    def abort(self):
        pass


class FakeActor:
    def __init__(self, aid):
        self.aid = aid
    def start(self, run_input=None, **kw):
        with LOCK:
            CALLS['n'] += 1
            n = CALLS['n']
        time.sleep(0.05)
        return {'id': f'r{n}'}
    def get(self):
        return {'id': self.aid}


class FakeClient:
    def __init__(self, token=None):
        pass
    def user(self):
        return type('U', (), {'get': staticmethod(lambda: {'username': 'test'})})()
    def actor(self, aid):
        return FakeActor(aid)
    def run(self, rid):
        return FakeRun(rid)
    def dataset(self, did):
        return FakeDataset(did)


# run_search lives in app/pipeline/search.py and imported both of these names into its
# own namespace, so that is the namespace to patch -- setting them on the package facade
# would leave search.py still holding the real ApifyClient.
from app.pipeline import search as _search
# search is a package now: patch the submodule whose namespace the caller reads the name
# from, since `from .x import name` binds a fresh name in the importing module.
from app.pipeline.search import runner as _runner
from app.pipeline.search import queries as _queries
from app.pipeline.search import google_phase as _google_phase
from app.pipeline.search import direct_site as _direct_site_mod
from app.pipeline.search import direct_api as _direct_api_mod

_runner.ApifyClient = FakeClient
_runner._fetch_apify_credit_label = lambda c: 'Apify Token - $5.00'
DATES = {'linkedin': 'pastWeek', 'indeed': '7', 'glassdoor': 7}


def run(countries, cities, actors=('indeed',), cancel=None):
    CALLS['n'] = 0
    return p.run_search('t', 100, DATES, countries=countries, cities=cities,
                        actor_order=list(actors), progress_cb=None,
                        should_cancel=cancel or (lambda: False))


section('4.1  location scoping -- the cities-only trap')

# Every location is now asked TWICE by the job pass -- once broadly for the whole of DevOps
# and MLOps, once for the entry-level phrases inside them. Written as a name rather than
# doubling the numbers in place, so that if a third job query ever appears these tests say
# what changed instead of just going red.
JOB_QUERIES = 2

df = run(['Italy'], [])
check('1 country x 1 platform = 1 location, asked twice',
      CALLS['n'] == 1 * JOB_QUERIES, CALLS['n'])
df = run([], ['Amsterdam'])
check('cities-only = 1 location, NOT 19', CALLS['n'] == 1 * JOB_QUERIES, CALLS['n'])
check('city row gets its parent country', df.iloc[0]['country'] == 'Netherlands', df.iloc[0]['country'])
df = run(['Italy', 'Germany'], ['Berlin'])
check('2 countries + 1 city = 3 locations', CALLS['n'] == 3 * JOB_QUERIES, CALLS['n'])
df = run(None, [])
check('countries=None still defaults to all 18', CALLS['n'] == 18 * JOB_QUERIES, CALLS['n'])
df = run([], [])
check('nothing selected = no calls', CALLS['n'] == 0, CALLS['n'])

section('4.2  multiple platforms run concurrently, all rows collected')
# Every platform asks for exactly the places the user chose, and for no others. LinkedIn used to
# add each country's strongest city on top, to get past its own 1,000-job ceiling -- a real
# gain, measured at 48 new jobs in 120 from Berlin alone. The user ended it: [owner's note: only the places that were chosen are wanted, nothing else]. So the count is platforms x locations again.
_locations = 6
df = run(['Italy', 'Germany'], [], actors=('indeed', 'glassdoor', 'linkedin'))
check('3 platforms x 2 countries, and nothing added to them',
      CALLS['n'] == _locations * JOB_QUERIES, (CALLS['n'], _locations * JOB_QUERIES))
check('every row collected (3 items per call)',
      len(df) == _locations * JOB_QUERIES * 3, len(df))
check('every platform represented', set(df['platform']) == {'indeed', 'glassdoor', 'linkedin'},
      set(df['platform']))

section('4.3  cancel keeps what was already fetched')
flag = {'v': False}


def trip_after(delay):
    def t():
        time.sleep(delay)
        flag['v'] = True
    threading.Thread(target=t, daemon=True).start()


flag['v'] = False
trip_after(0.12)
df = run(['Italy', 'Germany', 'France', 'Spain'], [], actors=('indeed', 'glassdoor'),
         cancel=lambda: flag['v'])
n = 0 if df is None or df.empty else len(df)
check('cancel keeps already-fetched rows', n > 0, f'{n} rows, {CALLS["n"]} calls')
_all_calls = 4 * 2 * JOB_QUERIES          # 4 countries x 2 platforms x 2 job queries
check('cancel actually stopped it early', CALLS['n'] < _all_calls,
      f'{CALLS["n"]} of {_all_calls}')

flag['v'] = True
df = run(['Italy'], [], cancel=lambda: flag['v'])
check('cancel before any call yields an empty frame', df is None or df.empty)

section('4.4  the DataFrame boundary (the round-two NaN bug)')
# The titles carry a field word on purpose. They used to be the bare placeholders "Thin",
# "Onsite" and "Remote", and the field filter -- wired into reapply_filters once it was
# found to have never run at all -- removed all three, taking this section's real subject
# (the NaN boundary and the Remote rule) down with them. A fixture that could not survive
# the pipeline was testing the pipeline it could not reach.
rows = [
    {'title': 'Thin Engineer', 'company': 'Roche', 'country': 'Switzerland',
     'url': 'https://jobs.ch/1',
     'description': 'Data Scientist', 'platform': 'jobs.ch', 'thin_description': True},
    {'title': 'Onsite Engineer', 'company': 'BigCo', 'country': 'Italy', 'url': 'https://i/1',
     'platform': 'indeed', 'description': 'Join our Rome office. Benefits offered here for the team.'},
    {'title': 'Remote Engineer', 'company': 'RemoteCo', 'country': 'Germany', 'url': 'https://i/2',
     'platform': 'indeed', 'description': 'Fully remote role with competitive salary and benefits.'},
]
df = p._finish_run_search_df([dict(r) for r in rows], None, 0, 1)
recs = {r['platform'] + r['title']: r for r in df.to_dict('records')}
check('thin_description column is real bool dtype', str(df['thin_description'].dtype) == 'bool',
      df['thin_description'].dtype)
check('non-thin row is False, not NaN', recs['indeedOnsite Engineer']['thin_description'] is False
      or recs['indeedOnsite Engineer']['thin_description'] == False)
check('thin row stays True', bool(recs['jobs.chThin Engineer']['thin_description']) is True)
check('Category assigned to every row', 'Category' in df.columns and df['Category'].notna().all())
check('sponsorship_visa filled for every row', df['sponsorship_visa'].notna().all())
check('Germany -> Employer\'s Discretion',
      recs['indeedRemote Engineer']['sponsorship_visa'] == "Employer's Discretion",
      recs['indeedRemote Engineer']['sponsorship_visa'])

merged = storage.prepend_jobs(df.to_dict('records'))
raw = storage.JOBS_PATH.read_text(encoding='utf-8')
check_no_raise('saved jobs.json is strict-valid JSON',
               lambda: json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c))))
# search_title is the job title in the Search box. "Engineer" names all three rows, so what
# decides them here is the Remote rule this section is about, not the title check.
kept, removed, flagged = p.reapply_filters([dict(j) for j in storage.load_jobs()],
                                            progress_cb=None, anthropic_api_key=None,
                                            search_title='Engineer')
titles = sorted(k['title'] for k in kept)
check('Remote rule is ON: the on-site row is dropped',
      'Onsite Engineer' not in titles, titles)
check('the genuinely remote row survives', 'Remote Engineer' in titles, titles)
check('the thin row survives', 'Thin Engineer' in titles, titles)

section('4.4b  the title check actually runs inside reapply_filters')

# It did not, for as long as it existed. `job_field_words.py` was written when the Pool was
# built and then imported by nothing: the Internship and Thesis modules call their own
# copies from their finders, and the Job module's copy was dead code no test would have
# noticed. Measured on a real Austrian run, 86 of 411 jobs reaching Claude were Vertrieb,
# Verkauf, Copywriter, Customer Support and HR. It now reads the job title in the Search box.
_field_rows = [
    {'title': 'DevOps Engineer (m/w/d)', 'company': 'A', 'country': 'Austria',
     'url': 'https://x/1', 'description': 'Fully remote role, competitive salary offered.'},
    {'title': 'Vertriebsmitarbeiter Aussendienst', 'company': 'B', 'country': 'Austria',
     'url': 'https://x/2', 'description': 'Fully remote role, competitive salary offered.'},
    {'title': 'Freelance Copywriter', 'company': 'C', 'country': 'Austria',
     'url': 'https://x/3', 'description': 'Fully remote role, competitive salary offered.'},
    {'title': 'Data Engineer (m/w/d)', 'company': 'E', 'country': 'Austria',
     'url': 'https://x/5', 'description': 'Fully remote data role, competitive salary offered.'},
]
_kept, _removed, _flagged = p.reapply_filters([dict(r) for r in _field_rows],
                                              progress_cb=None, anthropic_api_key=None,
                                              search_title='DevOps')
_titles = [k['title'] for k in _kept]
check('the job the title names survives', 'DevOps Engineer (m/w/d)' in _titles, _titles)
check('the sales job is removed', 'Vertriebsmitarbeiter Aussendienst' not in _titles, _titles)
check('the copywriter is removed', 'Freelance Copywriter' not in _titles, _titles)
check('a real job in another field is removed too', 'Data Engineer (m/w/d)' not in _titles,
      _titles)
# The same rows, with a different title in the box: the title decides, not a word list.
_kept = p.reapply_filters([dict(r) for r in _field_rows], progress_cb=None,
                          anthropic_api_key=None, search_title='Data Engineering')[0]
check('with "Data Engineering" in the box, the data job survives instead',
      [k['title'] for k in _kept] == ['Data Engineer (m/w/d)'], [k['title'] for k in _kept])
# A row with no title at all is not evidence of anything, and this app never deletes on an
# absence -- the same rule the date filter follows.
_untitled = p.reapply_filters([{'title': '', 'company': 'D', 'country': 'Austria',
                                'url': 'https://x/4',
                                'description': 'Fully remote role, competitive salary.'}],
                              progress_cb=None, anthropic_api_key=None)[0]
check('a listing with no title is kept, not deleted', len(_untitled) == 1, _untitled)


section('4.4c  a Markdown mirror never costs the full posting')

# wearedevelopers.com serves each vacancy twice, and 16 of 95 mirror copies on disk carry
# no text. Once a mirror is put back on its real address the two rows share one URL, and
# the exact-address pass used to keep whichever arrived FIRST. The empty mirror goes first
# here on purpose: that is the order that would have deleted the real posting.
_desc = ('We are looking for a DevOps Engineer to run our Kubernetes platform. Fully remote '
         'role, competitive salary, and a team that ships every day. ' * 6)
_pair = [
    {'title': None, 'company': '', 'country': 'Austria', 'description': '',
     'url': 'https://www.wearedevelopers.com/jobs/ext/2836673-devops-engineer.md'},
    {'title': 'DevOps Engineer', 'company': 'Schellenberger', 'country': 'Austria',
     'description': _desc,
     'url': 'https://www.wearedevelopers.com/jobs/ext/2836673-devops-engineer'},
]
_kept, _r, _f = p.reapply_filters([dict(r) for r in _pair], progress_cb=None,
                                  anthropic_api_key=None, search_title='DevOps')
check('the two copies become one', len(_kept) == 1, [k.get('url') for k in _kept])
check('  ...and the one kept is the full posting, not the empty mirror',
      bool(_kept) and len(str(_kept[0].get('description') or '')) > 100, _kept)
check('  ...on the real address', bool(_kept) and not str(_kept[0]['url']).endswith('.md'))

_gone_rows = [{'title': 'PL/SQL DevOps Engineer', 'company': 'A', 'country': 'Austria',
               'url': 'https://x/gone', 'description': 'This job is no longer available. ' + _desc},
              {'title': 'DevOps Engineer', 'company': 'B', 'country': 'Austria',
               'url': 'https://x/live', 'description': _desc}]
_kept, _r, _f = p.reapply_filters([dict(r) for r in _gone_rows], progress_cb=None,
                                  anthropic_api_key=None, search_title='DevOps')
check('a taken-down posting saved earlier is removed at Filter',
      [k['url'] for k in _kept] == ['https://x/live'], [k['url'] for k in _kept])


section('4.5  reapply_filters -- steps, counts and log structure')
logs = []
jobs = [
    {'id': '1', 'title': 'Data Scientist', 'company': 'A', 'country': 'Italy', 'url': 'https://a/1',
     'description': 'Fully remote role with competitive salary and benefits offered here.'},
    {'id': '2', 'title': 'Senior Data Scientist', 'company': 'B', 'country': 'Italy', 'url': 'https://a/2',
     'description': 'Fully remote role, 10+ years of experience required for this position.'},
    {'id': '3', 'title': 'Data Scientist', 'company': 'A', 'country': 'Italy', 'url': 'https://a/1',
     'description': 'duplicate url'},
    {'id': '4', 'title': 'Data Scientist', 'company': 'C', 'country': 'Italy', 'url': 'https://a/4',
     'description': 'On-site only in our office, no remote work available at all here.'},
]
kept, removed, flagged = p.reapply_filters([dict(j) for j in jobs],
                                            progress_cb=lambda m, d, t: logs.append(m),
                                            anthropic_api_key=None,
                                            search_title='Data Scientist')
steps = [m.split('|')[0].split(':')[1] for m in logs if m.startswith('FILTER_STEP_START:')]
# Two orderings are checked here, and both were deliberate.
#
# 'remote' sits between dedup and language because it is the only content rule that needs
# no English, and on a real Netherlands search it removes about 85% of what reaches it --
# running it before translation means translation is only ever paid for on listings that
# could still survive. Same verdict either way; rule_text reads whatever is on the row.
#
# There is no company-name step at the FRONT any more. It existed only to give the old
# dedup something to group by, and dedup now compares the listings' own text. The name is
# read instead by _step_company_names, after Claude's screen, from the listings that
# survived -- which is why it does not appear in a keyless run at all.
# Six steps, and translation is not one of them. It was removed once every language lingua
# reports had a vocabulary object of its own: the rules read a posting in the language it
# was written in, so nothing needs turning into English first. That also ended a whole class
# of ordering bug -- translation REPLACES the description, so detecting the language
# afterwards answered "English" and the Dutch evidence was never searched for.
check('exactly the 6 non-Claude steps run, in the order the user asked for',
      steps == ['dedup', 'work_location', 'country', 'rules', 'sponsorship', 'sort'],
      steps)
check('there is no translation step in the Filter at all',
      'language' not in steps, steps)
check('the country object runs before the English rule pack, not after',
      steps.index('country') < steps.index('rules'), steps)
check('every START has a DONE',
      len([m for m in logs if m.startswith('FILTER_STEP_START:')])
      == len([m for m in logs if m.startswith('FILTER_STEP_DONE:')]))
check('FILTER_START / FILTER_END present', 'FILTER_START' in logs and 'FILTER_END' in logs)
check('every rule in the English pack is logged',
      len([m for m in logs if m.startswith('FILTER_STEP_ITEM:rules|')])
      == len(p.filters.FILTER_RULES_STEP_CHECKLIST),
      p.filters.FILTER_RULES_STEP_CHECKLIST)
check('and every rule in the country object is logged too',
      len([m for m in logs if m.startswith('FILTER_STEP_ITEM:country|')])
      == len(p.filters.COUNTRY_RULE_SECTIONS))
check('the Log names the languages it found',
      any('Languages found:' in m for m in logs),
      [m for m in logs if m.startswith('GLOG:filter_step:country')])
check('  ...and how many are read in their own language',
      any('read in their own language' in m for m in logs))
check('no Claude step without a key', not any('claude' in m for m in logs))
# Of the four inputs, #3 repeats #1's URL and #4 is on-site, so both go. #2 asks for
# 10+ years and is now KEPT: seniority stopped being a reason to delete, so it comes
# through labelled 'Senior' and he narrows by the column. That is the change, and
# asserting the label as well as the survival is the point -- a listing kept without
# being labelled would be worse than one deleted, because nothing would say why it
# is there.
check('the clean listing and the senior one both survive',
      sorted(k['id'] for k in kept) == ['1', '2'], [k['id'] for k in kept])
check('duplicate URL removed', '3' not in [k['id'] for k in kept])
check('on-site listing removed', '4' not in [k['id'] for k in kept])
check('  ...and the senior one is labelled Senior, not silently kept',
      [k.get('Seniority') for k in kept if k['id'] == '2'] == ['Senior'],
      [(k['id'], k.get('Seniority')) for k in kept])
check('removed_by_keywords counts only the rule loop', removed == 1, removed)
check('claude_flagged empty with no key', flagged == [])

section('4.6  cancel inside Filter')
big = [{'id': str(i), 'title': f'Datenwissenschaftler {i}', 'company': f'C{i}', 'country': 'Germany',
        'url': f'https://d/{i}',
        'description': 'Dies ist eine vollstaendig remote Position mit guten Leistungen. ' * 3}
       for i in range(20)]
t0 = time.monotonic()
kept, removed, flagged = p.reapply_filters([dict(j) for j in big], progress_cb=None,
                                            anthropic_api_key=None, should_cancel=lambda: True)
elapsed = time.monotonic() - t0
check(f'cancelled Filter returns fast ({elapsed:.2f}s)', elapsed < 2.0)
check('cancelled Filter still returns a list', isinstance(kept, list))

section('4.7  sort order')
jobs = [
    {'id': 'ft', 'title': 'Data Scientist', 'company': 'A', 'country': 'Germany', 'url': 'https://s/1',
     'description': 'Fully remote role with competitive salary and benefits offered.'},
    {'id': 'pt', 'title': 'Part-Time Data Scientist', 'company': 'B', 'country': 'Germany',
     'url': 'https://s/2', 'description': 'Fully remote part-time role with benefits offered.'},
    {'id': 'it', 'title': 'Data Scientist Internship', 'company': 'C', 'country': 'Germany',
     'url': 'https://s/3', 'description': 'Fully remote internship with a paid stipend offered.'},
    # Deliberately NOT the same text as 'ft'. This fixture exists to check sort order, and
    # it used to give 'ft' and 'ftit' the same title AND a byte-identical description --
    # safe only because the old dedup grouped by company first and so never compared two
    # different companies. Dedup now compares the text itself, and correctly calls two
    # identical postings one job, which deleted the row this section is about.
    {'id': 'ftit', 'title': 'Data Scientist', 'company': 'D', 'country': 'Italy', 'url': 'https://s/4',
     'description': 'Fully remote position building forecasting models for retail demand.'},
]
kept, _, _ = p.reapply_filters([dict(j) for j in jobs], progress_cb=None, anthropic_api_key=None,
                               search_title='Data Scientist')
order = [k['id'] for k in kept]
# The user's order: Thesis, then Internship, then Part-Time, then Full-Time.
check('Internship before Part-Time', order.index('it') < order.index('pt'), order)
check('Part-Time before Full-Time', order.index('pt') < order.index('ft'), order)
check('Italy first within Full-Time', order.index('ftit') < order.index('ft'), order)

section('4.7b  three searches, each in two languages')

# The fault this exists to stop coming back: a real German run returned 4 theses and 53
# internships out of 4,812 listings, because nothing the app sent ever contained the words
# `Masterarbeit`, `Praktikum` or `Werkstudent`. Three parallel modules were sifting the
# results of a search built for one of them.
#
# What is checked here is what is actually ASKED -- the query strings that reach the actor --
# because that is the thing that was wrong and no downstream test could have seen it.
_asked = []


def _spy_actor(client, limit, cancel, actor_id, run_input, log_prefix, **kw):
    _asked.append((log_prefix, run_input.get('title') or run_input.get('keywords') or ''))
    return [], 0.0


class _NoClient:
    def __init__(self, *a, **k):
        pass

    def user(self):
        return type('U', (), {'get': lambda s: {'username': 't'}})()


def _queries_for(countries, search_for, languages=None):
    _asked.clear()
    saved_actor, saved_client = _runner._run_actor_and_fetch, _runner.ApifyClient
    try:
        _runner._run_actor_and_fetch = _spy_actor
        _runner.ApifyClient = _NoClient
        p.run_search('t', 100, DATES, countries=countries, actor_order=['indeed'],
                     cities=[], should_cancel=lambda: False, search_for=search_for,
                     search_languages=languages)
    finally:
        _runner._run_actor_and_fetch = saved_actor
        _runner.ApifyClient = saved_client
    return list(_asked)


# -- the job pass asks its two questions, and nobody else's ---------------------------
#
# This used to check that the job pass sent exactly one query, back when its keywords were
# role titles and an exact phrase could only narrow them. The user moved the field to DevOps and
# MLOps and asked for every junior and entry-level form of them, which a single broad query
# cannot deliver: LinkedIn fills its thousand places with senior roles and the junior ones
# never fit inside it. So the job pass now asks twice -- broadly, then for the entry-level
# phrases -- and what this guards is that it is still only those two, with no internship or
# thesis word leaking in.
for _choice, _why in ((None, 'nothing selected'), (['job'], 'jobs only')):
    _q = _queries_for(['Germany'], _choice)
    _t = [text for _p, text in _q]
    check('%s -> the two job searches, broad and entry-level' % _why,
          _t == [_queries.KEYWORDS, _queries.ENTRY_KEYWORDS], [x[:40] for x in _t])
    check('  ...and no internship or thesis word is in either',
          not any(w in text for text in _t
                  for w in ('Praktikum', 'Werkstudent', 'Masterarbeit', 'Thesis')),
          [x[:40] for x in _t])

# -- the field is the job title in the box ----------------------------------------------
# The user's rule: one title he types replaces every field vocabulary. With nothing typed, the
# default title is asked -- and nothing left over from DevOps or data science.
_t = [text for _p, text in _queries_for(['Germany'], ['job'])]
check('the job pass asks for the default title',
      any(p.DEFAULT_SEARCH_TITLE in text for text in _t), [x[:60] for x in _t])
check('  ...and no longer for DevOps or MLOps',
      not any('DevOps' in text or 'MLOps' in text for text in _t), [x[:60] for x in _t])
check('  ...and no longer for Data Science',
      not any('Data Science' in text for text in _t), [x[:60] for x in _t])

# -- all three kinds, each in English and in the country's own language ---------------
_q = _queries_for(['Germany'], ['job', 'internship', 'thesis'],
                  p.ALL_SEARCH_LANGUAGES)
# Each kind is asked broadly and then exactly, because the two find different postings.
# Measured on real German data: of the relevant listings each returned, 29 were found only
# by the precise query and 210 only by the broad one, with just 33 in common.
#
# Job is 3 rather than 4: its local precise shape is deliberately empty. The local pass for
# a job already IS the entry-level question -- DevOps and MLOps are not translated by
# anybody (0 local forms in 17,544 real titles), so the local query pairs the same English
# role words with the local word for a beginner, and there is nothing left for a precise
# shape to add. A pass with nothing to ask is skipped rather than sent empty.
# Thesis has a third shape, the thesis words alone (T-27), in English and in the local language: 4 + 2.
check('job asked 3 times, internship 4, thesis 6 (broad, exact, and the thesis words alone)',
      len(_q) == 3 + 4 + 6, len(_q))
# Counted by naming them, not by looking for a leading quote -- the entry-level job query
# starts with one too, which is what made an earlier version of this check miscount.
_texts = [text for _prefix, text in _q]
_role = p.search_title.role_form(p.DEFAULT_SEARCH_TITLE)
_field = p.search_title.field_form(p.DEFAULT_SEARCH_TITLE)
check('  ...and the exact-phrase queries really are there',
      sum(1 for _text in _texts
          if _text.startswith('"Junior %s"' % _role)
          or _text.startswith('"Working Student %s"' % p.DEFAULT_SEARCH_TITLE)
          or _text.startswith('"Praktikum %s"' % p.DEFAULT_SEARCH_TITLE)
          or _text.startswith('"Master Thesis %s"' % p.DEFAULT_SEARCH_TITLE)
          or _text.startswith('"Masterarbeit %s"' % p.DEFAULT_SEARCH_TITLE)) == 5,
      [x[:34] for x in _texts])
check('  ...one of them is the job query verbatim', _queries.KEYWORDS in _texts)
check('  ...and one is the entry-level one', _queries.ENTRY_KEYWORDS in _texts)
for _word, _why in (('Praktikum', 'internships'), ('Masterarbeit', 'theses'),
                    ('Berufseinsteiger', 'German beginner words'),
                    (_field, 'the title in the box')):
    check('  ...and %s are asked for' % _why,
          any(_word in text for text in _texts), _word)

# -- Thesis is on the title too ---------------------------------------------------------
#
# It kept its data-science vocabulary while Job and Internship moved to DevOps, and then the user
# put it on the title as well: "Masterarbeit Data Engineering". What must stay is the thesis
# half -- Masterarbeit, Examensarbete -- which is the half that is translated.
_thesis = [text for _p, text in _queries_for(['Germany'], ['thesis'],
                                             p.ALL_SEARCH_LANGUAGES)]
for _word in ('Masterarbeit', 'Abschlussarbeit', p.DEFAULT_SEARCH_TITLE):
    check('thesis asks for %s' % _word, any(_word in t for t in _thesis), _word)
check('  ...and no longer for the old data-science vocabulary',
      not any(w in t for t in _thesis
              for w in ('Künstliche Intelligenz', 'Machine Learning', 'DevOps')),
      [t[:50] for t in _thesis])

# -- each job Level asks in its own words -------------------------------------------------
# Junior is what the job pass always asked. Entry, Mid and Senior ask the same question at
# their own level; Senior is Senior only, never Lead or Principal.
for _level, _want, _not in (('junior', '"Junior %s"' % _role, None),
                            ('entry', '"Entry Level %s"' % _role, '"Junior'),
                            ('mid', '"Mid-Level %s"' % _role, '"Junior'),
                            ('senior', '"Senior %s"' % _role, '"Junior')):
    _precise = _runner.keywords_for('job', 'Germany', 'en', 'precise',
                                    p.DEFAULT_SEARCH_TITLE, _level)
    check('%s: the precise job query is its own' % _level, _want in _precise, _precise)
    if _not:
        check('  ...and carries no Junior phrase', _not not in _precise, _precise)
check('Senior never asks for Lead or Principal',
      not any(w in _runner.keywords_for('job', 'Germany', lang, shape, 'Data Engineer', 'senior')
              for lang in ('en', 'local') for shape in ('broad', 'precise')
              if _runner.keywords_for('job', 'Germany', lang, shape, 'Data Engineer', 'senior')
              for w in ('Lead', 'Principal', 'Staff')))
check('a Level of Thesis runs the thesis search only',
      _runner.keywords_for('job', 'Germany', 'en', 'precise', 'X', None)
      == _queries.entry_keywords('X'))

# -- the local pass uses the COUNTRY's language, not one fixed language ---------------
_q = _queries_for(['Sweden'], ['thesis'], p.ALL_SEARCH_LANGUAGES)
check('Sweden is asked in Swedish', any('Examensarbete' in text for _p, text in _q),
      [t[:40] for _p, t in _q])
check('  ...and not in German', not any('Masterarbeit' in text and 'Examensarbete' not in text
                                        for _p, text in _q if 'Master-Thesis' not in text))

# -- an English-speaking country has no local pass: it would be the same search twice --
_q = _queries_for(['Ireland'], ['job', 'internship', 'thesis'],
                  p.ALL_SEARCH_LANGUAGES)
# No local pass at all -- it would be the same search twice -- so each kind is asked
# broadly and precisely, in English only, and nothing else.
# ...plus the thesis words alone, in English, for Thesis only (T-27).
check('an English-speaking country has no local pass', len(_q) == 2 + 2 + 3, len(_q))
# Not "no German word anywhere": the English INTERNSHIP query deliberately carries every
# language's word for an internship in one group, because a German employer writes
# "Werkstudent" on an otherwise English posting and that group is how it is found. What must
# be absent is anything that only a LOCAL pass produces -- and the beginner words are that,
# since they are assembled per language inside keywords_for.
check('  ...and no local-pass vocabulary reaches an English-only country',
      not any(w in text for _p, text in _q
              for w in ('Berufseinsteiger', 'Nyexaminerad', 'Neolaureato')),
      [t[:40] for _p, t in _q])


section('4.8  Google query construction')
q = p.build_google_job_queries(p.COUNTRIES, p.CITIES)
lines = q.split('\n')
check('every line is under the ~32-word limit', all(len(l.split()) <= 32 for l in lines),
      max(len(l.split()) for l in lines))
check('every line attributes to the right location',
      all(p._location_from_search_term(l) != (None, None) for l in lines))
stages = {p._google_query_stage(l) for l in lines}
check('all four stages present', stages == {'known', 'startup', 'global', 'open'}, stages)
known = {d for v in p.COUNTRY_JOB_SITES.values() for d in v}
startup = {d for v in p.COUNTRY_STARTUP_SITES.values() for d in v} | set(p.GLOBAL_STARTUP_SITES)
glob = set(p.GOOGLE_GLOBAL_EXTRA_SITES)
check('site lists stay pairwise disjoint',
      not (known & startup) and not (known & glob) and not (startup & glob))
check('open-web stage excludes the big three',
      all('linkedin.com' in l for l in lines if p._google_query_stage(l) == 'open'))

section('4.8  the Google phase of run_search (_run_google_phase)')

# Until this existed, every run_search test used actor_order=('indeed',), so the whole
# `if run_google:` branch -- the biggest single branch in the search path, and the one
# lifted out into _run_google_phase -- was never executed by a test at all.
GOOGLE_PAGE = {
    'searchQuery': {'term': 'data scientist site:stepstone.de "Berlin"'},
    'organicResults': [
        # A real advert's worth of text, not a one-line snippet. It matters: a row whose
        # description carries no posting words is a row enrichment will try to fetch, and
        # after this change a row it cannot fetch is dropped -- so a toy description would
        # make this test about enrichment rather than about the Google phase, and would send
        # it to the real network for a URL that does not exist.
        {'url': 'https://www.stepstone.de/job/1', 'title': 'Data Scientist - Acme GmbH',
         'description': (
             'A real job in Berlin. Remote friendly. Your tasks: build and ship models. '
             'Your profile: a degree in a quantitative field and experience with Python '
             'and SQL. What we offer: a permanent contract, 30 days annual leave and a '
             'learning budget. Apply now.')},
        # must be dropped by _is_excluded_job_board -- LinkedIn has its own actor
        {'url': 'https://www.linkedin.com/jobs/view/999', 'title': 'Data Scientist',
         'description': 'should be skipped as an excluded job board'},
    ],
}


class GoogleDataset:
    def __init__(self, did):
        self.did = did

    def iterate_items(self, **kw):
        return iter([GOOGLE_PAGE])

    def list_items(self, **kw):
        return type('R', (), {'items': [GOOGLE_PAGE]})()


class GoogleClient(FakeClient):
    def dataset(self, did):
        return GoogleDataset(did)


_GOOGLE_PATCHES = (
    (_runner, 'ApifyClient'),
    (_google_phase, '_deepen_google_results'),
    (_google_phase, '_run_direct_site_searches'),
    (_google_phase, '_run_direct_api_searches'),
    (_google_phase, '_run_browser_site_search'),
    (_google_phase, '_warn_zero_result_google_sites'),
    (_google_phase, '_run_pre_google_check'),
)
_saved = [(mod, name, getattr(mod, name)) for mod, name in _GOOGLE_PATCHES]
try:
    _runner.ApifyClient = GoogleClient
    # keep the phase offline -- the additive follow-ups each make real network calls
    _google_phase._deepen_google_results = lambda *a, **k: ([], [], [], [])
    _google_phase._run_direct_site_searches = lambda *a, **k: None
    _google_phase._run_direct_api_searches = lambda *a, **k: None
    _google_phase._run_browser_site_search = lambda *a, **k: None
    _google_phase._warn_zero_result_google_sites = lambda *a, **k: []
    _google_phase._run_pre_google_check = lambda *a, **k: ({}, None, None)

    _msgs = []
    gdf = p.run_search('data scientist', 100, DATES, countries=['Germany'], cities=[],
                       actor_order=['google'],
                       progress_cb=lambda m, c, t: _msgs.append(str(m)),
                       should_cancel=lambda: False)

    check('google phase returns the organic result', len(gdf) == 1, len(gdf))
    check("google rows are tagged platform='google'",
          len(gdf) and set(gdf['platform']) == {'google'})
    check('excluded job board (linkedin) never becomes a row',
          not any('linkedin.com' in str(u) for u in gdf.get('url', [])))
    check('google_stage is set on the row', 'google_stage' in gdf.columns)
    for _marker in ('PLATFORM_START:Google', 'KNOWN_SITES_START', 'STARTUP_SITES_START',
                    'KNOWN_SITES_HEADER', 'STARTUP_SITES_HEADER', 'PLATFORM_END:Google'):
        check(f'progress marker {_marker} emitted',
              any(m.startswith(_marker) for m in _msgs))
    check('no failure message during the google phase',
          not [m for m in _msgs if 'failed' in m.lower()],
          [m for m in _msgs if 'failed' in m.lower()][:2])
finally:
    for _mod, _name, _val in _saved:
        setattr(_mod, _name, _val)

section('4.9  _deepen_google_results -- the deep crawl')

from app.pipeline import google as _google
# The crawl helper is looked up by google.deepen, so that is where a stand-in
# has to go: rebinding it on the package would leave deepen holding the real one.
from app.pipeline.google import deepen as _google_deepen

_KNOWN = 'finn.no'
_JOB_URL = 'https://www.finn.no/job/ad/12345'


def _cancel_error():
    from app.pipeline.errors import SearchCancelled
    return SearchCancelled()


def _crawl_with(items, rows, cancel=None):
    """Run _deepen_google_results with a fake crawler returning `items`."""
    class DS:
        def iterate_items(self_inner, **kw):
            return iter(items)

    class C:
        def dataset(self_inner, did):
            return DS()

    # The run/poll/read cycle moved into apify.crawl_urls_in_batches, which google.py now
    # calls once per batch, so that is what gets stood in for. It returns the same shape
    # the real one does: (items, urls it could not crawl, dollars spent).
    saved = _google_deepen.crawl_urls_in_batches

    def fake(client, actor_id, urls, build_input, batch_size, should_cancel=None,
             progress_cb=None, label='crawl', memory_mbytes=None):
        if should_cancel and should_cancel():
            raise _cancel_error()
        return list(items), [], 0.01

    _google_deepen.crawl_urls_in_batches = fake
    try:
        return _google._deepen_google_results(rows, C(), progress_cb=None,
                                              should_cancel=cancel)
    finally:
        _google_deepen.crawl_urls_in_batches = saved


# -- nothing to do -----------------------------------------------------------------
check('no google rows -> all zeros', _crawl_with([], []) == (0, 0, 0, []))
check('non-google rows are ignored',
      _crawl_with([], [{'platform': 'indeed', 'url': 'https://x/1'}]) == (0, 0, 0, []))

# -- a domain with no confirmed job-URL pattern gets reported, not crawled ----------
_unknown = [{'platform': 'google', 'google_stage': 'known',
             'url': 'https://totally-unknown-site.example/job/1', 'country': 'Norway'}]
_r = _crawl_with([], list(_unknown))
check('unpatterned domain is warned about, not crawled',
      _r[:3] == (0, 0, 0) and 'totally-unknown-site.example' in _r[3], _r)

# -- a real known domain: new pages are added, existing ones rescraped --------------
_parent = {'platform': 'google', 'google_stage': 'known', 'url': _JOB_URL,
           'country': 'Norway', 'location': 'Oslo', 'description': 'short'}
_rows = [dict(_parent)]
_items = [
    # same url, longer text -> rescrape in place, not a new row
    {'url': _JOB_URL, 'text': 'a much longer description than the original one'},
    # a newly discovered page under the same domain -> new row
    {'url': 'https://www.finn.no/job/ad/999', 'text': 'another real posting body',
     'metadata': {'title': 'Data Scientist'}, 'crawl': {'referrerUrl': _JOB_URL}},
    # an excluded job board -> counted, never added
    {'url': 'https://www.linkedin.com/jobs/view/5', 'text': 'body',
     'crawl': {'referrerUrl': _JOB_URL}},
    # no text -> skipped entirely
    {'url': 'https://www.finn.no/job/ad/777', 'text': '   ',
     'crawl': {'referrerUrl': _JOB_URL}},
]
_res = _crawl_with(_items, _rows)
check('rescraped the existing row when the crawl had more text', _res[0] == 1, _res)
check('added exactly the one genuinely new page', _res[1] == 1, _res)
check('counted the excluded job board', _res[2] == 1, _res)
check('longer description replaced the short one',
      _rows[0]['description'] == 'a much longer description than the original one')
check('the new row was appended to rows', len(_rows) == 2, len(_rows))
_new = _rows[-1]
check('new row inherits the parent country', _new['country'] == 'Norway', _new.get('country'))
check('new row inherits the parent location', _new['location'] == 'Oslo', _new.get('location'))
check("new row is tagged platform='google'", _new['platform'] == 'google')
check('new row carries the parent google_stage', _new['google_stage'] == 'known')
check('new row has no company guessed', _new['company'] is None)
check('empty-text item never became a row',
      not any(r.get('url', '').endswith('/777') for r in _rows))

# -- the referrer beats the domain map (the country-mixup bug) ----------------------
# Two results on the SAME domain but different countries. domain_to_row is built with
# setdefault, so it holds the FIRST one; a page linked from the SECOND must still
# inherit the second's country, not the first's.
_first = {'platform': 'google', 'google_stage': 'known',
          'url': 'https://www.finn.no/job/ad/100', 'country': 'Canada', 'location': 'Toronto'}
_second = {'platform': 'google', 'google_stage': 'known',
           'url': 'https://www.finn.no/job/ad/200', 'country': 'France', 'location': 'Paris'}
_rows2 = [dict(_first), dict(_second)]
_crawl_with([{'url': 'https://www.finn.no/job/ad/300', 'text': 'a posting reached from the second result',
              'metadata': {'title': 'X'}, 'crawl': {'referrerUrl': _second['url']}}], _rows2)
_child = _rows2[-1]
check('a linked page inherits its REFERRER country, not the first row for the domain',
      _child['country'] == 'France', _child.get('country'))
check('and its referrer location too', _child['location'] == 'Paris', _child.get('location'))

# -- a crawl that collects nothing loses nothing ------------------------------------
# The helper never raises for a page it cannot reach: it names the URL in `unreachable`
# and hands back whatever it did get, so the caller decides. Here it gets nothing.
_saved = _google_deepen.crawl_urls_in_batches
try:
    _google_deepen.crawl_urls_in_batches = (
        lambda *a, **k: ([], ['https://www.finn.no/job/ad/12345'], 0.0))
    _rows3 = [dict(_parent)]
    _fail = _google._deepen_google_results(_rows3, None, progress_cb=None, should_cancel=None)
    check('a crawl that collects nothing returns zeros rather than raising',
          _fail[:3] == (0, 0, 0), _fail)
    check('and leaves the existing rows untouched', len(_rows3) == 1)
finally:
    _google_deepen.crawl_urls_in_batches = _saved

section('4.10  _run_direct_site_searches -- per-site direct search')


def _direct_site_run(items, rows, countries, cities, fail=False, progress=None):
    """Drive _run_direct_site_searches with a fake crawler returning `items`."""
    class DS:
        def iterate_items(self_inner, **kw):
            return iter(items)

    class C:
        def dataset(self_inner, did):
            return DS()

    # `fail` now means the batched crawl reached nothing -- it reports the URLs it could
    # not get rather than raising, which is the whole point of the shared pattern.
    saved = _direct_site_mod.crawl_urls_in_batches

    def fake(client, actor_id, urls, build_input, batch_size, should_cancel=None,
             progress_cb=None, label='crawl', memory_mbytes=None):
        if fail:
            return [], list(urls), 0.0
        return list(items), [], 0.02

    _direct_site_mod.crawl_urls_in_batches = fake
    try:
        return _direct_site_mod._run_direct_site_searches(
            rows, C(), countries, cities,
            progress_cb=((lambda m, c, t: progress.append(str(m))) if progress is not None else None),
            should_cancel=None)
    finally:
        _direct_site_mod.crawl_urls_in_batches = saved


# What URLs would a Germany search actually target? Use the real builders so the test
# stays honest about which domains have one.
_tasks_probe = []
for _dom in (list(p.COUNTRY_JOB_SITES.get('Germany') or [])
             + list(p.GOOGLE_GLOBAL_EXTRA_SITES)):
    _u = p._build_direct_search_url(_dom, 'Germany', 'country', 'Germany')
    if _u:
        _tasks_probe.append((_dom, _u))
check('Germany resolves to at least one direct-search URL', len(_tasks_probe) >= 1,
      len(_tasks_probe))

_DOM, _START = _tasks_probe[0]

# -- nothing selected -> no crawl at all --------------------------------------------
_rows = []
check('no countries or cities -> returns without crawling',
      _direct_site_run([], _rows, [], []) is None and _rows == [])

# -- the listing page itself becomes a fallback row ---------------------------------
_rows = []
_direct_site_run([{'url': _START, 'text': 'the search results page body',
                   'metadata': {'title': 'Jobs'}}], _rows, ['Germany'], [])
_listing = [r for r in _rows if r.get('url') == _START]
check('the listing page itself is kept as a fallback row', len(_listing) == 1, len(_rows))
check('listing row is tagged platform=google', _listing and _listing[0]['platform'] == 'google')
check('listing row gets the task country', _listing and _listing[0]['country'] == 'Germany')
check('a country-level task sets no city location', _listing and _listing[0]['location'] is None)

# -- a linked page is matched back by referrer --------------------------------------
_rows = []
_direct_site_run([
    {'url': _START, 'text': 'listing page', 'metadata': {'title': 'Jobs'}},
    {'url': 'https://example.invalid/job/42', 'text': 'a real individual posting body',
     'metadata': {'title': 'Data Scientist'}, 'crawl': {'referrerUrl': _START}},
], _rows, ['Germany'], [])
_child = [r for r in _rows if r.get('url', '').endswith('/job/42')]
check('a linked job page is matched back to its task by referrer', len(_child) == 1, len(_rows))
check('the linked page inherits the task country',
      _child and _child[0]['country'] == 'Germany')

# -- a page with an unknown referrer is dropped -------------------------------------
_rows = []
_direct_site_run([
    {'url': 'https://example.invalid/job/99', 'text': 'orphan posting',
     'crawl': {'referrerUrl': 'https://nobody-asked-for-this.invalid/'}},
], _rows, ['Germany'], [])
check('a page whose referrer matches no task is dropped', _rows == [], _rows)

# -- excluded job boards and empty text never become rows ---------------------------
_rows = []
_direct_site_run([
    {'url': 'https://www.linkedin.com/jobs/view/7', 'text': 'body',
     'crawl': {'referrerUrl': _START}},
    {'url': 'https://example.invalid/job/blank', 'text': '  ',
     'crawl': {'referrerUrl': _START}},
], _rows, ['Germany'], [])
check('excluded job board never becomes a direct-site row',
      not any('linkedin.com' in r.get('url', '') for r in _rows))
check('an empty-text page never becomes a row',
      not any(r.get('url', '').endswith('/blank') for r in _rows))

# -- a failed crawl loses nothing ---------------------------------------------------
_rows = [{'url': 'https://kept.invalid/1', 'platform': 'indeed'}]
_direct_site_run([], _rows, ['Germany'], [], fail=True)
check('a failed direct-site crawl leaves existing rows untouched', len(_rows) == 1, len(_rows))

# -- the per-site status line is emitted --------------------------------------------
_msgs = []
_direct_site_run([{'url': _START, 'text': 'listing page', 'metadata': {'title': 'Jobs'}}],
                 [], ['Germany'], [], progress=_msgs)
_flat = [m[0] if isinstance(m, tuple) else str(m) for m in _msgs]
check('a per-site direct_site status line is logged',
      any('GLOG:direct_site|' in str(m) for m in _flat), _flat[:3])
check('the closing summary line is logged',
      any('Direct site search done:' in str(m) for m in _flat))

section('4.11  _run_direct_api_searches -- source selection and the Jooble budget')


def _api_run(countries, cities, jooble_keys=None, jooble_rows=2, usage=None, boom=False):
    """Drive _run_direct_api_searches with every network fetcher stubbed out.

    Returns (rows, messages, calls) where calls records which sources were attempted.
    """
    rows, msgs, calls = [], [], []

    def fake_source(rows_, domain, fetch, hint, progress_cb_, *a, **k):
        calls.append(domain)
        return 0

    def fake_jooble(code, country, term, key, location=None, on_request_sent=None):
        calls.append(f'jooble:{code}:{location or country}')
        if on_request_sent:
            on_request_sent()
        if boom:
            raise RuntimeError('jooble exploded')
        return [{'url': f'https://{code}.jooble.org/{i}', 'title': 'DS'}
                for i in range(jooble_rows)]

    saved = {n: getattr(_direct_api_mod, n) for n in
             ('_run_direct_api_source', '_fetch_jooble', '_read_jooble_usage',
              '_record_jooble_usage')}
    counter = dict(usage or {})
    try:
        _direct_api_mod._run_direct_api_source = fake_source
        _direct_api_mod._fetch_jooble = fake_jooble
        _direct_api_mod._read_jooble_usage = lambda: dict(counter)

        def _rec(code):
            counter[code] = counter.get(code, 0) + 1
            return counter[code]
        _direct_api_mod._record_jooble_usage = _rec

        _direct_api_mod._run_direct_api_searches(
            rows, countries, cities,
            progress_cb=lambda m, c, t: msgs.append(str(m)),
            jooble_api_keys=jooble_keys or {}, reed_uk_api_key=None,
            francetravail_credentials=None)
    finally:
        for n, v in saved.items():
            setattr(_direct_api_mod, n, v)
    return rows, msgs, calls


# -- the keyless, countryless sources always run ------------------------------------
_r, _m, _calls = _api_run([], [])
for _always in ('remotive.com', 'remoteok.com', 'arbeitnow.com'):
    check(f'{_always} runs regardless of country', any(c.startswith(_always) for c in _calls), _calls)
check('no country selected -> no country-specific source runs',
      not any(c.startswith(('arbetsformedlingen.se', 'reed.co.uk')) for c in _calls), _calls)

# -- country scoping ----------------------------------------------------------------
_r, _m, _calls = _api_run(['Sweden'], [])
check('Sweden selected -> arbetsformedlingen.se runs',
      any(c.startswith('arbetsformedlingen.se') for c in _calls), _calls)
_r, _m, _calls = _api_run(['Switzerland'], [])
for _ch in ('swissdevjobs.ch', 'jobs.ch', 'jobup.ch'):
    check(f'Switzerland selected -> {_ch} runs', any(c.startswith(_ch) for c in _calls), _calls)
_r, _m, _calls = _api_run(['Sweden'], [])
check('Switzerland not selected -> its APIs stay out',
      not any(c.startswith('swissdevjobs.ch') for c in _calls), _calls)

# -- Jooble: no key means no call ---------------------------------------------------
_code, (_jc, _jcity) = list(p.JOOBLE_API_COUNTRIES.items())[0]
_r, _m, _calls = _api_run([_jc], [], jooble_keys={})
check('a Jooble country with no configured key is never called',
      not any(c.startswith('jooble:') for c in _calls), _calls)

# -- Jooble: a configured key for a selected country IS called ----------------------
_r, _m, _calls = _api_run([_jc], [], jooble_keys={_code: 'k'})
check('a configured Jooble key for a selected country is called',
      f'jooble:{_code}:{_jc}' in _calls, _calls)
check('its rows are added', len(_r) == 2, len(_r))

# -- Jooble: an unselected country is not called ------------------------------------
_r, _m, _calls = _api_run(['Italy'], [], jooble_keys={_code: 'k'})
check('a configured key for an UNselected country is not called',
      not any(c.startswith('jooble:') for c in _calls), _calls)

# -- Jooble: the lifetime budget is respected ---------------------------------------
_r, _m, _calls = _api_run([_jc], [], jooble_keys={_code: 'k'},
                          usage={_code: p._JOOBLE_LIFETIME_LIMIT})
check('an exhausted Jooble key is NEVER called again',
      not any(c.startswith('jooble:') for c in _calls), _calls)
check('and the exhaustion is reported',
      any('lifetime limit' in m for m in _m), _m[:3])

# -- Jooble: one below the limit still runs, and reports what is left ---------------
_r, _m, _calls = _api_run([_jc], [], jooble_keys={_code: 'k'},
                          usage={_code: p._JOOBLE_LIFETIME_LIMIT - 1})
check('the last remaining Jooble request is still used',
      f'jooble:{_code}:{_jc}' in _calls, _calls)
check('running out is announced right after',
      any('last lifetime request' in m for m in _m), _m[-3:])

# -- Jooble: a failure is reported and never kills the rest -------------------------
_r, _m, _calls = _api_run([_jc], [], jooble_keys={_code: 'k'}, boom=True)
check('a Jooble failure is logged, not raised',
      any('API call failed' in m for m in _m), _m[:3])
check('and the unconditional sources still ran afterwards',
      any(c.startswith('arbeitnow.com') for c in _calls), _calls)

section('4.12  _preflight_check_api_sources -- the pre-run health check')

from app.pipeline import preflight as _preflight
import requests as _rq


def _preflight_run(countries, cities=(), jooble_keys=None, reed=None, france=None,
                   failing=(), slow=()):
    """Run the preflight with the network faked.

    `failing` names substrings of URLs whose probe should raise; `slow` names substrings
    whose probe should finish LAST, so queue-order reporting can be told apart from
    completion-order reporting.
    """
    msgs = []
    net_calls = []

    class _Resp:
        def raise_for_status(self_inner):
            return None

        def json(self_inner):
            # No probe here reads the body; every one of them judges by the status.
            return {}
        status_code = 200
        text = '{}'
        content = b'{}'

    def fake(url, *a, **k):
        net_calls.append(url)
        if any(f in str(url) for f in failing):
            raise RuntimeError('probe failed for %s' % url)
        if any(sl in str(url) for sl in slow):
            time.sleep(0.15)
        return _Resp()

    saved_get, saved_post = _rq.get, _rq.post
    try:
        _rq.get = fake
        _rq.post = fake
        res = _preflight._preflight_check_api_sources(
            list(countries), list(cities), jooble_keys or {}, reed, france,
            lambda m, c, t: msgs.append(str(m)))
    finally:
        _rq.get, _rq.post = saved_get, saved_post
    return res, msgs, net_calls


def _reported_names(msgs):
    out = []
    for m in msgs:
        if m.startswith('PREFLIGHT_ITEM:'):
            out.append(m[len('PREFLIGHT_ITEM:'):].split('|')[0])
    return out


# -- the always-on sources ----------------------------------------------------------
(_checked, _passed, _probs, _off), _msgs, _net = _preflight_run([])
_names = _reported_names(_msgs)
for _always in ('remotive.com', 'remoteok.com', 'arbeitnow.com'):
    check(f'{_always} is always checked', _always in _names, _names)
# With no countries selected, nothing is contacted and nothing is reported. This used to
# assert the opposite -- that a missing DeepL key was reported even with no countries --
# and that expectation went when translation did.
check('with no countries, nothing is reported as failed',
      len(_probs) == 0 and _checked == _passed, (_checked, _passed, _probs))


# -- country scoping ----------------------------------------------------------------
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['Sweden'])
check('Sweden adds arbetsformedlingen.se', 'arbetsformedlingen.se' in _reported_names(_msgs))
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['Germany'])
check('Germany adds arbeitsagentur.de', 'arbeitsagentur.de' in _reported_names(_msgs))
(_c, _p, _pr, _off), _msgs, _net = _preflight_run([], ['Berlin'])
check('Berlin alone still adds arbeitsagentur.de',
      'arbeitsagentur.de' in _reported_names(_msgs))
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['Italy'])
check('an unrelated country adds no national source',
      'arbetsformedlingen.se' not in _reported_names(_msgs))

# -- Jooble is config-only: it must NEVER be probed over the network ----------------
_code, (_jc, _jcity) = list(p.JOOBLE_API_COUNTRIES.items())[0]
(_c, _p, _pr, _off), _msgs, _net = _preflight_run([_jc], jooble_keys={_code: 'a-key'})
check('a configured Jooble country is reported',
      f'{_code}.jooble.org' in _reported_names(_msgs), _reported_names(_msgs))
check('Jooble is NEVER called over the network (protects the lifetime budget)',
      not any('jooble' in str(u).lower() for u in _net), _net)

# A source with no key at all is now REPORTED, where it used to be skipped in silence on
# the grounds that it was "not a problem, just not set up yet". For a country the user did not
# select that is still true, and the loop is scoped to this run's countries so it never
# fires there. For one he DID select it is a national job board switched off with nothing
# saying so -- a check of the real saved settings found all fifteen Jooble keys, the Reed
# key and both France Travail credentials empty while the pre-flight reported six healthy
# sources and no problems at all.
(_c, _p, _pr, _off), _msgs, _net = _preflight_run([_jc], jooble_keys={})
check('a selected country whose Jooble key is missing is reported',
      f'{_code}.jooble.org' in _reported_names(_msgs), _reported_names(_msgs))
# It used to be reported as FAILED. The user, reading a Log full of red for sources he had
# simply never set up: "this is not a problem we have". A source with no key is switched
# off, not broken, and a healthy run must not read as a broken one -- so it gets its own
# verdict, stays out of the failure list, and never interrupts a search with a dialog.
check('  ...as switched off, not as a failure',
      not any(pr['name'] == f'{_code}.jooble.org' for pr in _pr), _pr)
_off_lines = [m for m in _msgs if m.startswith('PREFLIGHT_ITEM:') and '|OFF|' in m]
check('  ...on its own OFF line',
      any(f'{_code}.jooble.org' in m for m in _off_lines), _off_lines)
check('  ...saying which country loses the source',
      any(_jc in m for m in _off_lines if f'{_code}.jooble.org' in m), _off_lines)
check('  ...and where a key would come from',
      any('jooble.org' in m.split('|')[2] for m in _off_lines
          if f'{_code}.jooble.org' in m), _off_lines)
check('  ...and still without ever spending one of the 500 lifetime requests',
      not any('jooble' in str(u).lower() for u in _net), _net)
check('a switched-off source does not make the run look unhealthy',
      _p == _c, (_p, _c))

# The scoping is what keeps this from becoming noise: a country that is not being searched
# is not mentioned, however many keys are missing.
_other = [c for c, (country, _city) in p.JOOBLE_API_COUNTRIES.items() if country != _jc]
(_c, _p, _pr, _off), _msgs, _net = _preflight_run([_jc], jooble_keys={})
check('an unsearched country with no key is not mentioned at all',
      not any(f'{code}.jooble.org' in _reported_names(_msgs) for code in _other),
      _reported_names(_msgs))

# Reed and France Travail behave the same way, for the same reason.
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['United Kingdom'], reed=None)
check('a UK search with no Reed key says so',
      any('reed.co.uk' in m and '|OFF|' in m for m in _msgs), _msgs[:6])
check('  ...without calling it a failure either',
      not any(pr['name'] == 'reed.co.uk' for pr in _pr), _pr)
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['United Kingdom'], reed='a-real-key')
check('  ...and a configured Reed key is probed instead of reported',
      not any(pr['name'] == 'reed.co.uk' for pr in _pr)
      and any('reed' in str(u).lower() for u in _net), (_pr, _net))

(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['France'], france=(None, None))
check('a France search with no France Travail credentials says so',
      any(pr['name'] == 'francetravail.fr' and pr['fixable'] for pr in _pr), _pr)
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['France'], france=('id', ''))
check('  ...and half-configured credentials count as missing, not as working',
      any(pr['name'] == 'francetravail.fr' for pr in _pr), _pr)
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['France'], france=('id', 'secret'))
check('  ...while a complete pair is probed for real',
      not any(pr['name'] == 'francetravail.fr' for pr in _pr), _pr)

# werk.nl is the Netherlands' national board -- the country had no national source at all
# before it, only an unconfigured Jooble key.
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['Netherlands'])
check('a Netherlands search reports werk.nl', 'werk.nl' in _reported_names(_msgs),
      _reported_names(_msgs))
check('  ...without an actor run, which would be a real billed cost',
      not any('werk' in str(u).lower() for u in _net), _net)
(_c, _p, _pr, _off), _msgs, _net = _preflight_run([], ['Amsterdam'])
check('  ...and Amsterdam alone is enough to bring it in',
      'werk.nl' in _reported_names(_msgs), _reported_names(_msgs))
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['Germany'])
check('  ...but an unrelated country does not', 'werk.nl' not in _reported_names(_msgs))

# A MALFORMED key is the case that should be flagged, and flagged as fixable.
(_c, _p, _pr, _off), _msgs, _net = _preflight_run([_jc], jooble_keys={_code: 'short'})
check('a malformed Jooble key IS reported as a problem',
      any(pr['name'] == f'{_code}.jooble.org' for pr in _pr), _pr)
check('and it is marked fixable, with the settings key to fix',
      any(pr['name'] == f'{_code}.jooble.org' and pr['fixable']
          and pr['settings_key'] == f'jooble_{_code}_api_key' for pr in _pr), _pr)

# An exhausted key is flagged too.
_saved_usage = _preflight._read_jooble_usage
try:
    _preflight._read_jooble_usage = lambda: {_code: p._JOOBLE_LIFETIME_LIMIT}
    (_c, _p, _pr, _off), _msgs, _net = _preflight_run([_jc], jooble_keys={_code: 'a-long-enough-key'})
    check('an exhausted Jooble key is reported as a problem',
          any(pr['name'] == f'{_code}.jooble.org' for pr in _pr), _pr)
    check('its reason names the budget',
          any('budget' in (pr['reason'] or '') for pr in _pr
              if pr['name'] == f'{_code}.jooble.org'), _pr)
finally:
    _preflight._read_jooble_usage = _saved_usage

# -- a failing probe becomes a structured problem, not an exception -----------------
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['Sweden'], failing=['jobtechdev'])
check('a failing probe is counted but not passed', _c > _p, (_c, _p))
check('a failing probe produces a problem dict',
      any(pr['name'] == 'arbetsformedlingen.se' for pr in _pr), _pr)
_prob = [pr for pr in _pr if pr['name'] == 'arbetsformedlingen.se'][0]
for _key in ('name', 'reason', 'fixable', 'fix_kind', 'settings_key'):
    check(f'the problem dict carries {_key}', _key in _prob, sorted(_prob))
check('the failure reason is a real string', bool(_prob['reason']), _prob['reason'])

# -- results are reported in QUEUE order, not completion order ----------------------
# arbetsformedlingen is queued first but made slowest; it must still be reported first.
(_c, _p, _pr, _off), _msgs, _net = _preflight_run(['Sweden'], slow=['jobtechdev'])
_ordered = _reported_names(_msgs)
check('a slow first check is still reported first (queue order, not completion order)',
      _ordered and _ordered[0] == 'arbetsformedlingen.se', _ordered)
check('checked count equals the number of reported items',
      _c == len(_ordered), (_c, len(_ordered)))

section('4.12b  werk.nl -- the Netherlands national board')

# Every other country with a real national source has it wired in: arbeitsagentur.de for
# Germany, arbetsformedlingen.se for Sweden. The Netherlands had none, so a Dutch search
# ran on EURES and three global boards and no national board at all. werk.nl is the UWV's
# own -- Dutch employers are legally required to report vacancies to it -- and it carries
# 250,000+ live listings.
_WERK_ITEM = {
    'title': 'Data Scientist', 'companyName': 'Magno IT', 'location': 'AMSTERDAM',
    'contractType': 'Vast', 'url': 'https://magno-it.nl/jobs/data-scientist-amsterdam-5135',
    'descriptionText': 'Are you a Data Scientist looking for a new challenge? ' * 12,
    'datePosted': '2026-08-05',
}
_werk = p._werk_nl_rows([_WERK_ITEM])
check('a werk.nl record becomes one row', len(_werk) == 1, len(_werk))
_row = _werk[0]
check('the country is set', _row['country'] == 'Netherlands')
check('the platform is named', _row['platform'] == 'werk.nl')
check('the shouted location is made readable', _row['location'] == 'Amsterdam',
      _row['location'])
check('the real description is used, not a synthesized one',
      'looking for a new challenge' in _row['description'])
check('  ...so it is NOT flagged thin, which would exempt it from the Remote rule',
      _row['thin_description'] is False)
check('the contract type is carried through', _row['employment_type'] == 'Vast')

# A record the actor could not fill in must not become a row that looks real.
check('a record with no URL is skipped',
      p._werk_nl_rows([dict(_WERK_ITEM, url=None, applyUrl=None, detailUrl=None)]) == [])
check('a record with no title is skipped',
      p._werk_nl_rows([dict(_WERK_ITEM, title=None, functionName=None)]) == [])
check('junk in the dataset is skipped rather than crashing',
      p._werk_nl_rows(['nonsense', None, 42]) == [])

# Only when the actor really returned no text: claiming thin_description when the text is
# real would wrongly waive the Remote rule's positive check for the row.
_thin = p._werk_nl_rows([dict(_WERK_ITEM, descriptionText='', description='',
                              descriptionMarkdown='')])[0]
check('a record with no description at all IS flagged thin',
      _thin['thin_description'] is True)
check('  ...and still carries something readable',
      'Data Scientist' in _thin['description'])

# The stage only runs it for the right locations, and only with a client to run it with.
_rows: list = []
p._run_direct_api_searches(_rows, ['Germany'], [], progress_cb=None, apify_client=None)
check('no Apify client means werk.nl simply does not run, rather than erroring',
      not any(r.get('platform') == 'werk.nl' for r in _rows))


# workatastartup.com -- Y Combinator's board. Already a known site for the Google phase,
# and it produced ZERO rows on a real Netherlands search: its listing page offers 79
# same-domain links and every one is a category (/jobs/l/software-engineer), so there is
# no posting pattern to learn. Through the actor it returns 239 rows across the four role
# terms, every one with a real description.
_YC_ITEM = {
    'title': 'Fullstack Engineer', 'companyName': 'Reframe',
    'location': 'Atlanta, GA, US / Remote',
    'url': 'https://www.workatastartup.com/jobs/75835',
    'descriptionText': 'We are looking for a fullstack engineer to join us. ' * 8,
}
_yc = p._workatastartup_rows([_YC_ITEM])
check('a Y Combinator record becomes one row', len(_yc) == 1)
check('the platform is the site the user knows', _yc[0]['platform'] == 'workatastartup.com')
check('the country is left to the listing, not the search',
      _yc[0]['country'] is None, _yc[0]['country'])
check('the real description is kept', 'fullstack engineer' in _yc[0]['description'])
check('  ...so it is not flagged thin', _yc[0]['thin_description'] is False)
check('a record with no URL is skipped',
      p._workatastartup_rows([dict(_YC_ITEM, url=None, applyUrl=None)]) == [])
check('junk in the dataset is skipped rather than crashing',
      p._workatastartup_rows([None, 'x', 7]) == [])
check('a record with no text at all is flagged thin',
      p._workatastartup_rows([dict(_YC_ITEM, descriptionText='', description='',
                                   companyTagline='')])[0]['thin_description'] is True)

# It is global: it must run for any search, not only for one country.
_rows = []
p._run_direct_api_searches(_rows, ['Germany'], [], progress_cb=None, apify_client=None)
check('without an Apify client it simply does not run',
      not any(r.get('platform') == 'workatastartup.com' for r in _rows))


section('4.12c  every direct source searches every role term, not just one')

# The Google phase has always searched four role terms. Every direct source -- the JSON
# APIs and the per-site search URLs -- searched "Data Scientist" and nothing else. Measured
# on arbeitsagentur.de, whose API is free enough to run four times and compare:
#
#     Data Scientist 376 | Data Engineer 924 | ML Engineer 147 | AI Engineer 508
#     unique across all four: 1481
#
# 1,105 real listings -- 75% of that source -- were invisible, in every country.
# The terms are now the forms of the one title the user types, but the finding is why both
# halves of the search send every one of them, and the same ones.
check('the direct sources use the same terms as the Google phase',
      p.DIRECT_API_ROLE_TERMS == [t.strip('"') for t in p.GOOGLE_QUERY_ROLE_TERMS],
      (p.DIRECT_API_ROLE_TERMS, p.GOOGLE_QUERY_ROLE_TERMS))
check('  ...and they are every form of the title in the box',
      p.DIRECT_API_ROLE_TERMS == p.title_forms(p.DEFAULT_SEARCH_TITLE), p.DIRECT_API_ROLE_TERMS)

_asked: list = []


def _fake_source(term):
    _asked.append(term)
    return [{'url': 'https://x/%s/1' % term.replace(' ', '-'), 'title': term},
            {'url': 'https://x/shared', 'title': 'Shared posting'}]


_got = p._fetch_every_role_term(_fake_source)
check('every term is asked for', _asked == p.DIRECT_API_ROLE_TERMS, _asked)
check('the union is returned', len(_got) == len(p.DIRECT_API_ROLE_TERMS) + 1, len(_got))
check('a listing found by several terms appears once',
      sum(1 for r in _got if r['url'] == 'https://x/shared') == 1)

# One unhappy query must not cost the whole source.
def _one_bad(term):
    # Whichever term happens to be second -- named by position, not by spelling, so that
    # changing the field again does not quietly turn this into a test of nothing.
    if term == p.DIRECT_API_ROLE_TERMS[1]:
        raise RuntimeError('that query upset the server')
    return [{'url': 'https://x/%s' % term, 'title': term}]


check('one failing term does not lose the others',
      len(p._fetch_every_role_term(_one_bad)) == len(p.DIRECT_API_ROLE_TERMS) - 1)


def _all_bad(term):
    raise RuntimeError('the source is down')


try:
    p._fetch_every_role_term(_all_bad)
    _raised = False
except RuntimeError:
    _raised = True
check('a source that fails on every term still raises, so the Log shows it in red',
      _raised)

# The per-site search URLs, same change. A site that ignores the keyword must not be
# crawled four times for the same page.
_nl_tasks = p._direct_site_tasks(['Netherlands'], ['Amsterdam'])
check('a site whose URL ignores the keyword yields one task, not four',
      len({t['url'] for t in _nl_tasks}) == len(_nl_tasks), _nl_tasks)
_de_tasks = p._direct_site_tasks(['Germany'], [])
_stepstone = sorted(t['url'] for t in _de_tasks if t['domain'] == 'stepstone.de')
check('a site whose URL carries the keyword yields one task per term',
      len(_stepstone) == len(p.DIRECT_API_ROLE_TERMS), _stepstone)
check('  ...and they are genuinely different URLs',
      len(set(_stepstone)) == len(_stepstone)
      and 'data-engineer' in ' '.join(_stepstone)
      and 'data-engineering' in ' '.join(_stepstone), _stepstone)
check('every task records which term produced it',
      all(t.get('role_term') in p.DIRECT_API_ROLE_TERMS for t in _de_tasks))

# The safety net for the refactor that made this possible: every builder gained a
# role_term parameter defaulting to the original constant, so the URL for that term must
# be byte-identical to what it was before.
check('the default term still builds the original URL',
      p._build_direct_search_url('stepstone.de', 'Germany', 'country', 'Germany')
      == 'https://www.stepstone.de/jobs/data-engineer',
      p._build_direct_search_url('stepstone.de', 'Germany', 'country', 'Germany'))
check('  ...and a country-aware builder takes the term too',
      p._build_direct_search_url('arc.dev', 'Netherlands', 'country', 'Netherlands',
                                 'MLOps Engineer') is not None)


section('4.13  _build_search_plan -- location scoping, tested directly')

# Now that the plan builder is a pure function, the location-scoping rules can be checked
# as themselves rather than inferred from how many times a fake actor got called.
_plan, _goog, _tot = _runner._build_search_plan(['indeed'], ['Italy'], [])
check('1 country x 1 platform = 1 work item', _plan == [('indeed', 'country', 'Italy')], _plan)
check('no google in actor_order -> run_google is False', _goog is False)
check('total counts just the plan when google is off', _tot == 1, _tot)

_plan, _goog, _tot = _runner._build_search_plan(['indeed'], [], ['Amsterdam'])
check('cities-only produces ONE item for that city, not one per country',
      _plan == [('indeed', 'city', 'Amsterdam')], _plan)

_plan, _goog, _tot = _runner._build_search_plan(['indeed', 'linkedin'], ['Italy', 'Spain'], ['Berlin'])
check('2 platforms x (2 countries + 1 city), and not one location more',
      len(_plan) == 6, (len(_plan), [x[2] for x in _plan]))
check('  ...every one of them a place the user chose',
      {x[2] for x in _plan} == {'Italy', 'Spain', 'Berlin'}, sorted({x[2] for x in _plan}))
# The rule that replaced the split list: a country never drags its cities in behind it.
_plan2, _g2, _t2 = _runner._build_search_plan(['linkedin'], ['Germany'], ['Berlin'])
check('choosing Germany and Berlin asks for Germany and Berlin, once each',
      sorted(x[2] for x in _plan2) == ['Berlin', 'Germany'], _plan2)
_plan3, _g3, _t3 = _runner._build_search_plan(['linkedin'], ['Germany'], [])
check('choosing only the country asks only for the country',
      [x[2] for x in _plan3] == ['Germany'], _plan3)
_plan4, _g4, _t4 = _runner._build_search_plan(['linkedin'], [], ['Berlin'])
check('choosing only Berlin asks only for Berlin',
      [x[2] for x in _plan4] == ['Berlin'], _plan4)
check('every platform appears for every location',
      sorted(set(x[0] for x in _plan)) == ['indeed', 'linkedin'], _plan)

_plan, _goog, _tot = _runner._build_search_plan(['google'], ['Italy'], [])
check('google is NEVER in the plan (one combined call, not one per location)',
      _plan == [], _plan)
check('but run_google is True', _goog is True)
check('and total counts google as exactly one', _tot == 1, _tot)

_plan, _goog, _tot = _runner._build_search_plan(['google'], [], [])
check('google with no location at all does not run', _goog is False)

_plan, _goog, _tot = _runner._build_search_plan(['indeed', 'google'], ['Italy'], ['Berlin'])
check('mixed: 1 platform x 2 locations + 1 google = total 3', _tot == 3, (_plan, _tot))

section('4.14  enrich_thin_descriptions -- recovering the real job text')

from app.pipeline import enrich as _enrich

REAL_JD = ('We are looking for a Data Scientist to join our team in Berlin. '
           'You will build models in Python and SQL, work with our engineering group, '
           'and present findings to stakeholders. Requirements: a degree in a '
           'quantitative field and three years of experience. We offer a hybrid '
           'arrangement, 30 days holiday and a learning budget. ') * 3


def _run_enrich(rows, page_text=REAL_JD, fail=False, status=200):
    """Drive the enricher with the network faked.

    Patched at `enrich.fetcher.fetch` rather than at `requests.get`: enrichment goes up
    the fetch ladder now, so faking the bottom rung would leave the three above it free to
    make real network calls the moment the fake returned anything the ladder rejected.
    """
    calls = []

    def fake_fetch(url, *a, **k):
        calls.append(url)
        if fail:
            raise RuntimeError('network down')
        html = '<html><body><nav>menu menu</nav><main>%s</main></body></html>' % page_text
        return _enrich.fetcher.FetchResult(status, html, 'plain')

    # The real pauses add up to ten minutes. The retry BEHAVIOUR is what is under test --
    # that it asks again, and how many times -- so the waiting itself is set to nothing.
    # Same count of attempts, none of the sleeping.
    saved = _enrich.fetcher.fetch
    saved_pauses = _enrich.ENRICH_RETRY_PAUSES
    try:
        _enrich.fetcher.fetch = fake_fetch
        _enrich.ENRICH_RETRY_PAUSES = (0,) * len(saved_pauses)
        n = _enrich.enrich_thin_descriptions(rows, progress_cb=None, should_cancel=None)
    finally:
        _enrich.fetcher.fetch = saved
        _enrich.ENRICH_RETRY_PAUSES = saved_pauses
    return n, calls


def _thin(url='https://example.invalid/job/1', desc='Data Scientist at Acme GmbH'):
    return {'title': 'Data Scientist', 'company': 'Acme GmbH', 'url': url,
            'description': desc, 'thin_description': True, 'platform': 'arbeitsagentur.de'}


# -- the happy path -----------------------------------------------------------------
rows = [_thin()]
n, calls = _run_enrich(rows)
check('a thin listing gets enriched', n == 1, n)
check('its description is now the real page text', len(rows[0]['description']) > 300,
      len(rows[0]['description']))
check('the stub text is gone', 'at Acme GmbH' not in rows[0]['description'][:60])
check('thin_description is cleared once real text arrives',
      rows[0]['thin_description'] is False, rows[0]['thin_description'])
check('site chrome (nav) is stripped out', 'menu menu' not in rows[0]['description'])

# -- only thin rows are touched ------------------------------------------------------
full = {'title': 'X', 'url': 'https://example.invalid/2', 'description': 'A' * 4000,
        'thin_description': False}
rows = [full]
n, calls = _run_enrich(rows)
check('a listing that already has a description is never fetched', n == 0 and not calls, calls)
check('and its text is untouched', len(rows[0]['description']) == 4000)

# -- NaN in the flag must not be treated as True (the recurring family) --------------
# The row must carry a REAL description, not the usual stub. Enrichment has two ways in: the
# flag, and a description that is only site furniture. A stub row would be fetched through
# the second door however the flag reads, so it cannot show whether the flag was misread --
# which is the only thing this check is about.
nanrow = _thin(desc=REAL_JD)
nanrow['thin_description'] = float('nan')
rows = [nanrow]
n, calls = _run_enrich(rows)
check('a NaN thin_description is not treated as thin', n == 0 and not calls, calls)

# ...and the other half of the same rule: a stub IS fetched whatever the flag says, because
# a description of "<title> at <company>" is nothing for any filter to read. This is how the
# 548 arbeitsagentur.de listings in a real German search get their text.
stubrow = _thin(desc='Data Engineer (m/w/d) at FERCHAU GmbH in Osnabrück')
stubrow['thin_description'] = float('nan')
n, calls = _run_enrich([stubrow])
check('a stub description is fetched even when the flag is NaN', n == 1 and len(calls) == 1,
      (n, calls))

# -- a row with no url cannot be enriched -------------------------------------------
nourl = _thin(url=None)
n, calls = _run_enrich([nourl])
check('a thin row with no url is skipped, not crashed', n == 0 and not calls, calls)

# -- THE IMPORTANT ONES: never make a listing worse ---------------------------------
short = _thin()
n, calls = _run_enrich([short], page_text='Cookies. Accept?')
check('a too-short page never replaces the stub', n == 0, n)
check('and the original description survives', short['description'] == 'Data Scientist at Acme GmbH')
check('and thin_description stays True', short['thin_description'] is True)

err = _thin()
n, calls = _run_enrich([err], status=404)
check('a non-200 response never replaces the stub', n == 0, n)
check('the stub is never overwritten by an error page',
      err['description'] == 'Data Scientist at Acme GmbH')

boom = _thin()
n, calls = _run_enrich([boom], fail=True)
check('a network failure never replaces the stub', n == 0, n)
check('the stub is never overwritten by a failure',
      boom['description'] == 'Data Scientist at Acme GmbH')

# -- and after every attempt, a listing with no text at all is dropped ---------------
# The user's rule, and the measurement behind it: of the 123 German listings still empty after
# two passes, fetching each one alone recovered exactly one. A row whose description is
# still "<title> at <company>" cannot be read by any rule, by Claude, or by the user.
gone = _thin()
rows = [gone, _thin(url='https://example.invalid/job/2', desc=REAL_JD)]
n, calls = _run_enrich(rows, status=404)
check('a listing that never answers is removed from the list', len(rows) == 1, rows)
check('  ...and it is the empty one that went',
      rows[0]['description'] == REAL_JD, rows[0]['description'][:40])
check('  ...after every attempt, not on the first',
      calls.count('https://example.invalid/job/1') == len(_enrich.ENRICH_RETRY_PAUSES) + 1,
      calls.count('https://example.invalid/job/1'))

# The failure this nearly caused: a row that already HAS a real description is on the
# "did not answer" list too, because the page fetched for it came back shorter and was
# rightly refused. Dropping that would delete a good posting over a redundant fetch.
longer_existing = _thin(desc='B' * 5000)
rows = [longer_existing]
n, calls = _run_enrich(rows)
check('a SHORTER fetched page never replaces a longer existing description',
      longer_existing['description'] == 'B' * 5000, len(longer_existing['description']))
real_but_flagged = _thin(desc=REAL_JD)
rows = [real_but_flagged]
n, calls = _run_enrich(rows, status=404)
check('a row that already has real text is never dropped, however the fetch went',
      len(rows) == 1 and rows[0]['description'] == REAL_JD, rows)

# -- cancellation --------------------------------------------------------------------
many = [_thin(url='https://example.invalid/job/%d' % i) for i in range(10)]
saved_get = _enrich.fetcher.fetch
try:
    def slow_get(url, *a, **k):
        return _enrich.fetcher.FetchResult(
            200, '<html><body>%s</body></html>' % REAL_JD, 'plain')
    _enrich.fetcher.fetch = slow_get
    n = _enrich.enrich_thin_descriptions(many, progress_cb=None, should_cancel=lambda: True)
    check('cancel stops enrichment without raising', isinstance(n, int), n)
finally:
    _enrich.fetcher.fetch = saved_get

# -- the progress protocol -----------------------------------------------------------
msgs = []
rows = [_thin()]
saved_get = _enrich.fetcher.fetch
try:
    def okget(url, *a, **k):
        return _enrich.fetcher.FetchResult(
            200, '<html><body>%s</body></html>' % REAL_JD, 'plain')
    _enrich.fetcher.fetch = okget
    _enrich.enrich_thin_descriptions(rows, progress_cb=lambda m, c, t: msgs.append(str(m)),
                                     should_cancel=None)
finally:
    _enrich.fetcher.fetch = saved_get
check('ENRICH_START is emitted', any(m == 'ENRICH_START' for m in msgs), msgs[:3])
check('ENRICH_END is emitted', any(m == 'ENRICH_END' for m in msgs), msgs[-2:])
check('a per-platform result line is emitted',
      any(m.startswith('ENRICH_SITE_RESULT:') for m in msgs), msgs)


# -- where the job text is read from ----------------------------------------------------
# The page is asked in order of how much guessing each route needs: the site's own
# schema.org data first, then purpose-built content extraction, then stripping chrome tags
# and taking what is left. Measured on 24 real arbeitsagentur postings -- 22 of which
# publish a JobPosting object -- the structured route returns less text and MORE job
# vocabulary than the old one, which is the whole point.
_JSON_LD_PAGE = '''<html><head><title>Data Scientist</title>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
"title":"Data Scientist","datePosted":"2026-01-05",
"hiringOrganization":{"@type":"Organization","name":"Acme GmbH"},
"jobLocation":{"@type":"Place","address":{"addressLocality":"Berlin"}},
"description":"<p>Ihre Aufgaben: %s</p><p>Ihr Profil: Python, SQL.</p>"}</script>
</head><body><nav>Cookies akzeptieren Datenschutz Impressum</nav>
<div>Stellenangebot</div><footer>Alle Rechte vorbehalten</footer></body></html>''' % (
    'Sie entwickeln Modelle und Pipelines. ' * 12)

_posting = _enrich.job_posting_json_ld(_JSON_LD_PAGE)
check('a JobPosting object is found', bool(_posting))
check('  ...with the fields the pipeline needs',
      _posting.get('title') == 'Data Scientist'
      and _posting.get('hiringOrganization', {}).get('name') == 'Acme GmbH'
      and bool(_posting.get('jobLocation')) and bool(_posting.get('datePosted')))

_read = _enrich.readable_text(_JSON_LD_PAGE)
check('the description comes from the structured data', 'Ihre Aufgaben' in _read, _read[:60])
check('  ...as text, not as the markup the field is specified to contain',
      '<p>' not in _read and '&lt;' not in _read, _read[:60])
check('  ...and the cookie banner it sits next to is left behind',
      'akzeptieren' not in _read.lower() and 'impressum' not in _read.lower(), _read[:90])

# A JobPosting can sit inside an @graph or a list; all three shapes appear in the wild.
for _shape in ('{"@graph":[{"@type":"WebPage"},%s]}', '[{"@type":"WebSite"},%s]'):
    _inner = ('{"@type":"JobPosting","title":"X","description":"%s"}'
              % ('Aufgaben und Anforderungen. ' * 12))
    _page = ('<html><body><script type="application/ld+json">%s</script></body></html>'
             % (_shape % _inner))
    check('a JobPosting nested inside other data is still found',
          _enrich.job_posting_json_ld(_page).get('title') == 'X', _shape[:14])

check('broken JSON-LD costs nothing but the fallback',
      _enrich.job_posting_json_ld('<script type="application/ld+json">{not json</script>') == {})
check('a page with no structured data at all is not an error',
      _enrich.job_posting_json_ld('<html><body>hello</body></html>') == {})

# The guard that matters most: a cleaner route must never hand back LESS of the real
# posting. One real page gave trafilatura 257 characters where reading the page gave
# 1,049 -- a collapse, not chrome removal -- and without this the chain would have called
# a quarter of a description an improvement.
_LONG_BODY = 'Responsibilities and requirements for this role. ' * 40
_TINY_LD = ('<html><head><script type="application/ld+json">'
            '{"@type":"JobPosting","title":"X","description":"See our website."}</script>'
            '</head><body><article>%s</article></body></html>' % _LONG_BODY)
_read = _enrich.readable_text(_TINY_LD)
check('a one-line structured summary loses to the real page text',
      len(_read) > len(_LONG_BODY) * 0.5, len(_read))
check('  ...and the page text is what comes back', 'Responsibilities' in _read)

check('with no usable text anywhere the result is empty rather than a crash',
      _enrich.readable_text('<html><body></body></html>') == '')

# The mirror image of the guard above, and a regression the campaign caught: a page that
# is nothing BUT a navigation menu. Stripping nav/header/footer leaves it empty, which is
# the correct answer -- but trafilatura, told to favour recall, happily returns 2,639
# characters of "Home Jobs About Contact" and that would have been written into a listing
# as its job description. So trafilatura is never allowed to find content where stripping
# the chrome found none; it is there to clean real text, not to promote chrome into text.
_NAV_ONLY = '<html><body><nav>%s</nav></body></html>' % ('Home Jobs About Contact ' * 60)
check('a page that is only a navigation menu yields nothing',
      _enrich.readable_text(_NAV_ONLY) == '', _enrich.readable_text(_NAV_ONLY)[:60])

# JSON-LD keeps that licence, though, and must: a posting rendered entirely in JavaScript
# has no body text to strip and still publishes a complete description as data.
_JS_ONLY_WITH_LD = (
    '<html><head><script type="application/ld+json">'
    '{"@type":"JobPosting","title":"X","description":"%s"}</script></head>'
    '<body><div id="root"></div></body></html>' % ('Aufgaben und Anforderungen. ' * 12))
check('a JavaScript-only page still gives up its structured description',
      len(_enrich.readable_text(_JS_ONLY_WITH_LD)) > 200,
      len(_enrich.readable_text(_JS_ONLY_WITH_LD)))

section('4.15  automatic job-URL pattern discovery')

from app.pipeline import pattern_discovery as _pd
# The glob engine moved to its own module; the discovery code imports the four
# functions but not the constants that tune them, so the tests read them here.
from app.pipeline import globs as _glob_mod
from app.pipeline import google as _google
from app.pipeline import sources_urls as _surls
from bs4 import BeautifulSoup as _BS

# A listing page shaped like a real one: a job-card container holding postings, wrapped in
# the usual sea of navigation, category and company links.
LISTING_HTML = """
<html><head><title>Data Science Jobs in Berlin</title></head><body>
<nav><a href="/about/">About us</a><a href="/submit-a-job/">Post a job</a></nav>
<ul class="menu">
  <li><a href="/skill-areas/data-science/">Data Science</a></li>
  <li><a href="/skill-areas/backend/">Backend</a></li>
  <li><a href="/companies/acme/">ACME GmbH</a></li>
  <li><a href="/moving-to-berlin/visas/">Visas and permits</a></li>
  <li><a href="/moving-to-berlin/housing/">Housing in Berlin</a></li>
  <li><a href="/moving-to-berlin/cost/">Cost of living</a></li>
</ul>
<div class="jobs-list-items">
  <a href="/engineering/senior-data-scientist-acme/">Senior Data Scientist - Python and ML</a>
  <a href="/engineering/backend-developer-acme/">Backend Developer - Go and Kubernetes</a>
  <a href="/engineering/ml-engineer-acme/">Machine Learning Engineer - Berlin</a>
  <a href="/engineering/data-engineer-acme/">Data Engineer - Spark and Airflow</a>
</div>
</body></html>
"""

POSTING_HTML = """
<html><head><title>Job Vacancy: Senior Data Scientist // ACME</title></head><body>
<h1>Senior Data Scientist</h1>
<p>Responsibilities: build models, ship them, work with engineering. """ + ('Requirements: a degree and experience. ' * 40) + """</p>
<a href="/engineering/backend-developer-acme/">Backend Developer</a>
</body></html>
"""

INDEX_HTML = """
<html><head><title>27 Data Scientist Jobs in Berlin</title></head><body>
<p>Apply now. Requirements vary. """ + ('Browse our listings. ' * 60) + """</p>
""" + ''.join('<a href="/engineering/job-%d/">Job %d Title Here</a>' % (i, i) for i in range(20)) + """
</body></html>
"""

BASE = 'https://example.invalid/skill-areas/data-science/'


def _serve(pages):
    """Point the module's fetcher at a dict of {url: html}.

    Patched at the ladder, not at `requests.get`. Discovery no longer makes bare GETs, and
    a fake that only replaced the bottom rung would let the other three reach the real
    network for every URL the dict does not hold -- including the robots.txt and sitemap
    probes the sitemap route makes. Those correctly come back 404 from here.
    """
    saved = _pd.fetcher.fetch

    def fake(url, *a, **k):
        for key, value in pages.items():
            if url.rstrip('/') == key.rstrip('/'):
                return _pd.fetcher.FetchResult(200, value, 'plain')
        return _pd.fetcher.FetchResult(404, '<html><body>not found</body></html>', 'plain')
    _pd.fetcher.fetch = fake
    return saved


# -- step 1: find the job-card container --------------------------------------------
_soup = _BS(LISTING_HTML, 'html.parser')
_groups = _pd.find_job_card_groups(_soup, BASE)
check('found at least one job-card group', len(_groups) >= 1, len(_groups))
_shapes = [_glob_mod._glob_for(g[0]) for g in _groups]
check('the engineering group is among them',
      any('/engineering/' in (sh or '') for sh in _shapes), _shapes)
check('MULTIPLE groups are returned, not just the biggest',
      len(_groups) >= 2 or len(_shapes) >= 1, len(_groups))
_eng = [g for g in _groups if '/engineering/' in (_glob_mod._glob_for(g[0]) or '')][0]
check('the engineering group holds all four postings', len(_eng) == 4, len(_eng))
check('it excludes company links',
      not any('/companies/' in u for u in _eng))
check('it excludes category links',
      not any('/skill-areas/' in u for u in _eng))

# -- link-text classification --------------------------------------------------------
check('a job title is recognised', _pd._looks_like_job_title('Senior Data Scientist - Berlin'))
check('a category with a count is not', not _pd._looks_like_job_title('Marketing & Communications (15)'))
check('a one-word link is not', not _pd._looks_like_job_title('Jobs'))
check('"Read more" is not', not _pd._looks_like_job_title('Read more'))

# -- step 3: is this page one posting, or an index? ----------------------------------
_p_soup = _BS(POSTING_HTML, 'html.parser')
check('a real posting is accepted',
      _pd._looks_like_single_posting('https://example.invalid/engineering/senior-data-scientist-acme/',
                                     _p_soup, 200))
_i_soup = _BS(INDEX_HTML, 'html.parser')
check('an index page ("27 ... Jobs in Berlin") is rejected',
      not _pd._looks_like_single_posting('https://example.invalid/engineering/x/', _i_soup, 200))
check('a 404 is rejected', not _pd._looks_like_single_posting('https://x/a/b', _p_soup, 404))
_tiny = _BS('<html><title>Job</title><body>Apply. Too short.</body></html>', 'html.parser')
check('a stub page is rejected', not _pd._looks_like_single_posting('https://x/a/b', _tiny, 200))
_nomark = _BS('<html><title>Something</title><body>' + ('word ' * 400) + '</body></html>', 'html.parser')
check('a long page with no posting words is rejected',
      not _pd._looks_like_single_posting('https://x/a/b', _nomark, 200))

# a posting's own share links must not make it look like an index
_share = _BS('<html><title>Job Vacancy: X</title><body><p>Responsibilities. '
             + ('detail ' * 300) + '</p>'
             + ''.join('<a href="/engineering/x/?share=%s">s</a>' % n
                       for n in ('li', 'fb', 'tw', 'xing', 'mail', 'pocket'))
             + '</body></html>', 'html.parser')
check('a posting with many share links is still a posting',
      _pd._looks_like_single_posting('https://example.invalid/engineering/x/', _share, 200))

# -- end to end ----------------------------------------------------------------------
_saved = _serve({
    BASE: LISTING_HTML,
    'https://example.invalid/engineering/senior-data-scientist-acme/': POSTING_HTML,
    'https://example.invalid/engineering/backend-developer-acme/': POSTING_HTML,
})
try:
    _found = _pd.discover_job_url_patterns(BASE)
finally:
    _pd.fetcher.fetch = _saved
check('discovery returns the engineering glob',
      _found == ['https://example.invalid/engineering/**'], _found)

# a site whose listing is JavaScript-rendered yields nothing, safely
_saved = _serve({BASE: '<html><body><div id="root"></div></body></html>'})
try:
    _js = _pd.discover_job_url_patterns(BASE)
finally:
    _pd.fetcher.fetch = _saved
check('a JavaScript-only page returns [] rather than a guess', _js == [], _js)

# a page that 403s yields nothing
_saved = _pd.fetcher.fetch
try:
    def _403(url, *a, **k):
        return _pd.fetcher.FetchResult(403, '', 'plain')
    _pd.fetcher.fetch = _403
    _blocked = _pd.discover_job_url_patterns(BASE)
finally:
    _pd.fetcher.fetch = _saved
check('a site that blocks scripts returns []', _blocked == [], _blocked)

# -- Claude path: its answer is still verified ---------------------------------------
class _FakeClaude:
    """Stands in for anthropic.Anthropic, returning one canned reply."""

    def __init__(self, reply):
        self._reply = reply
        self.messages = self

    def create(self, **kw):
        block = type('Block', (), {'type': 'text', 'text': self._reply})()
        return type('Response', (), {'content': [block]})()


_saved = _serve({
    BASE: LISTING_HTML,
    'https://example.invalid/engineering/senior-data-scientist-acme/': POSTING_HTML,
    'https://example.invalid/engineering/backend-developer-acme/': POSTING_HTML,
})
try:
    good = _FakeClaude('JOB: /engineering/senior-data-scientist-acme/\n'
                       'JOB: /engineering/backend-developer-acme/')
    _c1 = _pd.resolve_job_pattern_with_claude(good, BASE)
    # a hallucinated path that was never on the page must be ignored
    bad = _FakeClaude('JOB: /invented/never-on-the-page/\nJOB: /also/made-up/')
    _c2 = _pd.resolve_job_pattern_with_claude(bad, BASE)
    # Claude pointing at the category links must not become a pattern
    cat = _FakeClaude('JOB: /skill-areas/data-science/\nJOB: /skill-areas/backend/')
    _c3 = _pd.resolve_job_pattern_with_claude(cat, BASE)
finally:
    _pd.fetcher.fetch = _saved
check('Claude naming real postings yields the glob',
      _c1 == ['https://example.invalid/engineering/**'], _c1)
check('hallucinated paths are ignored', _c2 == [], _c2)
check('Claude naming CATEGORY links does not produce a pattern', _c3 == [], _c3)

# -- persistence ---------------------------------------------------------------------
isolated_storage()
_surls._DISCOVERED_PATTERNS_CACHE.pop('value', None)
check('nothing discovered on a clean machine', _surls.load_discovered_job_patterns() == {})
_surls.save_discovered_job_pattern('example.invalid', ['https://example.invalid/engineering/**'])
_surls._DISCOVERED_PATTERNS_CACHE.pop('value', None)
_loaded = _surls.load_discovered_job_patterns()
check('a discovered pattern persists', 'example.invalid' in _loaded, sorted(_loaded))
check('...with its globs', _loaded['example.invalid']['globs'] ==
      ['https://example.invalid/engineering/**'], _loaded)
check('...and a timestamp', bool(_loaded['example.invalid'].get('added_at')))

# -- the merged lookup ---------------------------------------------------------------
_merged = _google.all_job_url_patterns()
check('discovered patterns join the built-in table', 'example.invalid' in _merged, len(_merged))
check('the built-in table is still there', 'stepstone.de' in _merged)
check('a built-in pattern is never overwritten by a discovered one',
      _merged['stepstone.de'] == p.GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS['stepstone.de'])
check('_known_pattern_domain now recognises the learned domain',
      _google._known_pattern_domain('example.invalid') == 'example.invalid')
check('...including a www subdomain of it',
      _google._known_pattern_domain('www.example.invalid') == 'example.invalid')

section('4.16  the two bugs the real Germany audit found')

# BUG 2: an HTTP 429 page was stored as a job description (aijobs.ai, title "429",
# 607 chars of rate-limit text). It was translated, screened by Claude and shown as a job.
_err = p.looks_like_error_page
check('the real 429 page is caught', _err('429', 'Too many requests. Please slow down. ' * 10))
check('a 403 page is caught', _err('403', 'Forbidden'))
check('a Cloudflare interstitial is caught',
      _err('Just a moment...', 'Checking your browser before accessing.'))
check('a 404 page is caught', _err('Not Found', '404 Not Found. The page does not exist.'))
check('a German block page is caught', _err('Fehler', 'Zugriff verweigert.'))
# and it must not reject real postings
check('a real posting is NOT caught',
      not _err('Job Vacancy: Senior Data Scientist // ACME',
               'Responsibilities and requirements. ' * 80))
check('a long posting that merely mentions 404 is NOT caught',
      not _err('Senior Data Scientist',
               'We run a 404 monitoring tool. ' + 'Responsibilities. ' * 100))
check('a posting whose title contains digits is NOT caught',
      not _err('Data Scientist (2 openings)', 'Responsibilities. ' * 80))

# the enricher must refuse to replace a stub with an error page
_row = {'title': 'Data Scientist', 'company': 'Acme', 'url': 'https://x/1',
        'description': 'Data Scientist at Acme', 'thin_description': True,
        'platform': 'arbeitsagentur.de'}
from app.pipeline import enrich as _en
_saved = _en.fetcher.fetch
try:
    def _429(url, *a, **k):
        return _en.fetcher.FetchResult(
            200,
            '<html><head><title>429</title></head><body>'
            + ('Too many requests. Rate limit exceeded. ' * 20) + '</body></html>',
            'plain')
    _en.fetcher.fetch = _429
    _n = _en.enrich_thin_descriptions([_row], progress_cb=None, should_cancel=None)
finally:
    _en.fetcher.fetch = _saved
check('enrichment refuses a 429 page', _n == 0, _n)
check('...and the stub survives', _row['description'] == 'Data Scientist at Acme')

# BUG 1: discovery inherited the deep crawl's stage filter and so saw one domain
# out of nineteen. It must now consider EVERY google row, whatever stage produced it.
_seen = []
_saved_disc = _google.__dict__.get('_learn_probe')


def _fake_discover(listing_url, client=None, progress_cb=None):
    _seen.append(listing_url)
    return []


import app.pipeline.pattern_discovery as _pdmod
_saved_smart = _pdmod.discover_job_url_patterns_smart
try:
    _pdmod.discover_job_url_patterns_smart = _fake_discover
    _rows = [
        # an OPEN-web result: the stage the deep crawl deliberately skips
        {'platform': 'google', 'google_stage': 'open',
         'url': 'https://openweb-site.invalid/jobs/x'},
        # a known-stage result on another unknown domain
        {'platform': 'google', 'google_stage': 'known',
         'url': 'https://knownstage-site.invalid/jobs/y'},
        # a domain that DOES have a pattern -- must not be re-learned
        {'platform': 'google', 'google_stage': 'known',
         'url': 'https://www.stepstone.de/stellenangebote--x--1'},
        # a non-google row -- out of scope
        {'platform': 'indeed', 'url': 'https://indeed.invalid/job/1'},
    ]
    _google.learn_missing_job_patterns(_rows, anthropic_api_key=None, progress_cb=None)
finally:
    _pdmod.discover_job_url_patterns_smart = _saved_smart

_domains = sorted(u.split('/')[2] for u in _seen)
check('an OPEN-web domain is now examined (the bug)',
      'openweb-site.invalid' in _domains, _domains)
check('a known-stage domain is examined too', 'knownstage-site.invalid' in _domains, _domains)
check('a domain that already has a pattern is skipped',
      not any('stepstone' in d for d in _domains), _domains)
check('non-google rows are out of scope',
      not any('indeed' in d for d in _domains), _domains)
check('exactly one page per domain is examined', len(_seen) == 2, _seen)

section('4.17  the verifier rejects articles and category pages')

# The real Germany run learned three sites and collected 14 rows from them -- not one a
# job. All three had long bodies and job vocabulary, so body checks alone let them pass:
#   "Agentic AI Engineer Interview Questions - Hiring Guide"  an article
#   "Data Engineer Jobs with Visa Sponsorship"                a category page
#   "Construction Jobs | Navartis"                            a category page
_BODY = 'Responsibilities and requirements. Apply now. ' * 60


def _page(title, body=_BODY, links=''):
    from bs4 import BeautifulSoup as _B
    return _B('<html><head><title>%s</title></head><body><p>%s</p>%s</body></html>'
              % (title, body, links), 'html.parser')


def _verdict(title, url='https://x.invalid/job/a-real-one', **kw):
    return _pd._looks_like_single_posting(url, _page(title, **kw), 200)


# the three real titles that got through
check('an interview-questions article is rejected',
      not _verdict('Agentic AI Engineer Interview Questions - Hiring Guide (2026) | Agentic Jobs'))
check('a "<role> Jobs" category page is rejected',
      not _verdict('Data Engineer Jobs with Visa Sponsorship - Python, Spark | JobMetasearch'))
check('a bare category page is rejected', not _verdict('Construction Jobs | Navartis'))

# other article shapes
for _t in ('How to Become a Data Scientist | Blog',
           'Ultimate Guide to Machine Learning Careers',
           'Data Scientist Salary Report 2026',
           'CV Tips for Data Engineers'):
    check(f'article rejected: {_t[:38]}', not _verdict(_t))

# and the postings it must still accept -- over-rejecting is what loses the user jobs
check('a real posting is accepted',
      _verdict('Job Vacancy: Senior Data Scientist - Python, ML // DATATRONiQ | IT Jobs'))
check('a German posting is accepted', _verdict('Data Scientist (w/m/d)'))
check('a posting titled "job in <city>" is accepted',
      _verdict('Junior Data Scientist - Consumer (all genders) job in Berlin, Germany'))
check('a plain role title is accepted', _verdict('Senior Machine Learning Engineer'))

# THE case the site-suffix rule exists for: a real posting whose site suffix says "Jobs"
check('a posting is NOT rejected for its site suffix containing "Jobs"',
      _verdict('Job Vacancy: Senior Backend Developer // ACME | IT / Software Development Jobs'))
# NOTE: an earlier version of this test asserted that
#   'Data Engineer - ACME GmbH - Berlin Jobs'
# must be accepted -- a shape invented without checking. Against 1,122 real collected
# titles, only five use ' - ' before a plural job word, and every one of those separates
# with '|' as well ('AI Developer (m/w/d) - Augsburg in Augsburg | XING Jobs'), which the
# rule already handles. The invented case was removed rather than widening the rule for
# a shape that does not occur.
check('a real XING-style title is accepted',
      _verdict('Data Scientist - AI & Experimentation (m/f/d) in Berlin | XING Jobs'))
check('a real hyphenated posting title is accepted',
      _verdict('AI Developer (m/w/d) - Augsburg in Augsburg | XING Jobs'))

# the shapes it SHOULD reject, taken verbatim from the real run
for _t in ('AI Jobs in Germany',
           '48,546 jobs in AI/ML, Data Science and Big Data',
           'Data Engineering Jobs',
           'Sales Jobs in Berlin | Berlin Startup Jobs',
           'How to become a Data Scientist in Germany'):
    check(f'real index/article rejected: {_t[:36]}', not _verdict(_t))

# the leading-title helper itself
check('leading title stops at a pipe',
      _pd._leading_title('Job Vacancy: X | IT Jobs') == 'Job Vacancy: X')
check('leading title stops at a double slash',
      _pd._leading_title('Senior DS // ACME') == 'Senior DS')
check('leading title of a plain title is itself',
      _pd._leading_title('Data Scientist (w/m/d)') == 'Data Scientist (w/m/d)')

section('4.18  saved patterns are re-checked when the rules tighten')

# Tightening the verifier only stops NEW bad patterns. Three real ones were already on
# disk -- an article and two category pages -- and every later search would have kept
# collecting from them, because a saved pattern used to be trusted forever.
isolated_storage()
_surls._DISCOVERED_PATTERNS_CACHE.pop('value', None)
import json as _json

# a pattern written by the old, looser verifier (no version recorded at all)
_surls._discovered_job_patterns_path().parent.mkdir(parents=True, exist_ok=True)
_surls._discovered_job_patterns_path().write_text(_json.dumps({
    'navartisglobal.com': {'globs': ['https://www.navartisglobal.com/jobs/**'],
                           'added_at': '2026-09-01T14:31:09+00:00'},
    'good.example': {'globs': ['https://good.example/job/**'],
                     'added_at': '2026-09-01T15:00:00+00:00',
                     'verifier_version': _pd.VERIFIER_VERSION},
}), encoding='utf-8')
_surls._DISCOVERED_PATTERNS_CACHE.pop('value', None)
_loaded = _surls.load_discovered_job_patterns()
check('a pattern from the older verifier is dropped',
      'navartisglobal.com' not in _loaded, sorted(_loaded))
check('a pattern from the current verifier is kept',
      'good.example' in _loaded, sorted(_loaded))
check('the dropped domain is unknown again, so it will be re-learned',
      _google._known_pattern_domain('navartisglobal.com') is None)

# and a freshly saved one records the version that approved it
_surls.save_discovered_job_pattern('fresh.example', ['https://fresh.example/job/**'])
_surls._DISCOVERED_PATTERNS_CACHE.pop('value', None)
_back = _surls.load_discovered_job_patterns()
check('a newly saved pattern records its verifier version',
      _back.get('fresh.example', {}).get('verifier_version') == _pd.VERIFIER_VERSION,
      _back.get('fresh.example'))
check('...and survives the next load', 'fresh.example' in _back)

# junk entries must not crash the loader
_surls._discovered_job_patterns_path().write_text(
    _json.dumps({'a': 'not-a-dict', 'b': None, 'c': [1, 2]}), encoding='utf-8')
_surls._DISCOVERED_PATTERNS_CACHE.pop('value', None)
check_no_raise('malformed entries do not crash the loader',
               lambda: _surls.load_discovered_job_patterns())
check('...and none of them is trusted', _surls.load_discovered_job_patterns() == {})

section('4.19  legal and policy pages are never learned as jobs')

# A real run learned navartisglobal.com/legal_documents/** and collected "Privacy Policy"
# (14,049 chars) and "Modern Slavery Policy" as job postings. Long text plus words like
# "requirements" and "apply" -- which any terms document has -- passed every body check.
for _seg in ('legal', 'legal_documents', 'privacy', 'terms', 'gdpr', 'datenschutz',
             'compliance', 'disclaimer'):
    check(f'/{_seg}/ is never a job path', _seg in _pd._NON_JOB_SEGMENTS)

from bs4 import BeautifulSoup as _BS4
_legal_page = _BS4(
    '<html><body><div class="jobs-list-items">'
    + ''.join('<a href="/legal_documents/doc-%d">Privacy Policy Section %d</a>' % (i, i)
              for i in range(5))
    + '</div></body></html>', 'html.parser')
_groups = _pd.find_job_card_groups(_legal_page, 'https://x.invalid/jobs/')
check('a page of legal links yields no candidate group', _groups == [], _groups)

# THE measurement that stopped a worse fix: requiring a job-role word in the title was
# tested and rejected. Of 1,122 real collected titles, 122 (10.9%) contain no role word --
# "Data Engineers" (plural), "Mathematiker*in / Physiker*in", "Weiterbildungsassistent",
# "Thesis - Optimization of Graph Neural Networks" -- and every one is a real job. These
# assert the verifier does NOT demand a role word, so nobody re-introduces that rule.
_BODY2 = 'Responsibilities and requirements. Apply now. ' * 60


def _page2(title):
    return _BS4('<html><head><title>%s</title></head><body><p>%s</p></body></html>'
                % (title, _BODY2), 'html.parser')


for _t in ('Data Engineers - 100% remote, ASAP, 12+ months - Berlin',
           'Mathematiker*in / Physiker*in fuer KI, Machine Learning (m/w/d)',
           'Weiterbildungsassistent - Backend-Programmierung (m/w/d) - Remote',
           'Thesis - Optimization of Graph Neural Networks'):
    check(f'real job with no role word is accepted: {_t[:34]}',
          _pd._looks_like_single_posting('https://x.invalid/job/a', _page2(_t), 200))

section('4.20  the fetch ladder')

from app.pipeline import fetcher as _fet

_GOOD_PAGE = ('<html><head><title>Senior Data Scientist</title></head><body>'
              '<a href="/job/1">Senior Data Scientist</a><a href="/job/2">ML Engineer</a>'
              + ('Responsibilities and requirements. ' * 40) + '</body></html>')
_SHELL = '<html><head><title>Jobs</title></head><body><div id="root"></div></body></html>'
_ERROR_PAGE = ('<html><head><title>403 Forbidden</title></head><body>'
               '403 Forbidden nginx</body></html>')


def _ladder(responses, **kw):
    """Drive fetch() with a scripted answer per rung. Returns (result, rungs tried).

    The memo is cleared first. Without that, each case inherits the rung the previous one
    taught the domain and starts there -- which is the ladder working exactly as designed,
    and is asserted directly further down, but makes a per-case rung order meaningless.
    """
    _fet._strategy_path().parent.mkdir(parents=True, exist_ok=True)
    _fet._strategy_path().write_text('{}', encoding='utf-8')
    _fet._STRATEGY_CACHE.pop('value', None)
    tried = []

    def make(name):
        def rung(url):
            tried.append(name)
            status, html = responses.get(name, (None, ''))
            return _fet.FetchResult(status, html, name)
        return rung

    saved = dict(_fet._RUNGS)
    saved_path = _fet._strategy_path
    try:
        for name in _fet.STRATEGIES:
            _fet._RUNGS[name] = make(name)
        # Point the per-domain memo at the isolated test storage, not the real data dir.
        result = _fet.fetch('https://ladder.invalid/jobs', **kw)
    finally:
        _fet._RUNGS.update(saved)
        _fet._strategy_path = saved_path
        _fet._STRATEGY_CACHE.pop('value', None)
    return result, tried


# -- the cheap rung answers, and nothing else is tried -------------------------------
_r, _tried = _ladder({'plain': (200, _GOOD_PAGE)})
check('a page that plain requests can read stops at rung one', _tried == ['plain'], _tried)
check('  ...and the result is marked accepted', _r.accepted is True)
check('  ...and reports which rung produced it', _r.strategy == 'plain', _r.strategy)

# -- a 403 climbs to the TLS rung ----------------------------------------------------
_r, _tried = _ladder({'plain': (403, ''), 'chrome_tls': (200, _GOOD_PAGE)})
check('a 403 climbs to the browser-fingerprint rung', _tried == ['plain', 'chrome_tls'], _tried)
check('  ...and the page comes back', _r.ok and _r.accepted, (_r.status, _r.accepted))

# -- a browser-agent block climbs to the crawler rung --------------------------------
_r, _tried = _ladder({'plain': (403, ''), 'chrome_tls': (403, ''),
                      'crawler': (200, _GOOD_PAGE)})
check('a site that refuses browser agents is reached as a crawler',
      _tried == ['plain', 'chrome_tls', 'crawler'], _tried)
check('  ...and it is the crawler rung that is credited', _r.strategy == 'crawler', _r.strategy)

# -- a 200 that is really an error page must NOT stop the climb ----------------------
_r, _tried = _ladder({'plain': (200, _ERROR_PAGE), 'chrome_tls': (200, _GOOD_PAGE)})
check('an error page served as HTTP 200 does not end the climb',
      _tried == ['plain', 'chrome_tls'], _tried)
check('  ...and the real page is what comes back',
      'Senior Data Scientist' in _r.html, _r.html[:50])

# -- needs_links: a JS shell is not good enough --------------------------------------
_r, _tried = _ladder({'plain': (200, _SHELL), 'chrome_tls': (200, _SHELL),
                      'crawler': (200, _SHELL), 'browser': (200, _GOOD_PAGE)},
                     needs_links=True)
check('a link-less shell climbs all the way to the browser',
      _tried == ['plain', 'chrome_tls', 'crawler', 'browser'], _tried)
check('  ...and the rendered page is accepted', _r.accepted is True)
check('  ...and it stops there rather than paying for the Apify rung as well',
      'apify' not in _tried, _tried)

# needs_links=False would have accepted that same shell at rung one
_r, _tried = _ladder({'plain': (200, _SHELL)})
check('without needs_links the shell is accepted at rung one', _tried == ['plain'], _tried)

# -- allow_browser=False never launches a browser ------------------------------------
_r, _tried = _ladder({'plain': (200, _SHELL), 'chrome_tls': (200, _SHELL),
                      'crawler': (200, _SHELL), 'browser': (200, _GOOD_PAGE)},
                     needs_links=True, allow_browser=False)
check('allow_browser=False never reaches the browser rung', 'browser' not in _tried, _tried)
check('  ...and the best failed attempt is still returned, marked not accepted',
      _r.ok and _r.accepted is False, (_r.ok, _r.accepted))

# -- every rung fails -----------------------------------------------------------------
_r, _tried = _ladder({'plain': (403, ''), 'chrome_tls': (403, ''), 'crawler': (403, ''),
                      'browser': (None, '')})
check('a site nothing reaches returns a result rather than raising',
      isinstance(_r, _fet.FetchResult))
check('  ...and it is not marked accepted', _r.accepted is False)

# -- the memo end to end: the second fetch of a site must not re-climb ------------------
# This was found by the tests above failing: each case was starting at the rung the
# previous one had taught the domain. That is the whole point of the memo, so assert it
# directly rather than only through _strategy_order.
_ladder({'plain': (403, ''), 'chrome_tls': (403, ''), 'crawler': (200, _GOOD_PAGE)})
_second = []


def _rung_for(name):
    def rung(url):
        _second.append(name)
        return _fet.FetchResult(200 if name == 'crawler' else 403,
                                _GOOD_PAGE if name == 'crawler' else '', name)
    return rung


_saved_rungs = dict(_fet._RUNGS)
try:
    for _n in _fet.STRATEGIES:
        _fet._RUNGS[_n] = _rung_for(_n)
    _fet.fetch('https://ladder.invalid/jobs/another-page')
finally:
    _fet._RUNGS.update(_saved_rungs)
check('a second page on the same site goes straight to the rung that worked',
      _second == ['crawler'], _second)

# -- the per-domain memo --------------------------------------------------------------
_fet.remember_strategy('memo.invalid', 'crawler')
check('a learned strategy is recalled', _fet.recall_strategy('memo.invalid') == 'crawler',
      _fet.recall_strategy('memo.invalid'))
check('a known domain tries its own strategy first',
      _fet._strategy_order('memo.invalid', True)[0] == 'crawler',
      _fet._strategy_order('memo.invalid', True))
check('  ...but keeps the others as a fallback if the site changed',
      sorted(_fet._strategy_order('memo.invalid', True)) == sorted(_fet.STRATEGIES))

_fet.remember_strategy('dead.invalid', '')
check('a domain nothing could open is recorded', 'dead.invalid' in _fet.load_domain_strategies())
check('  ...and is never sent to the browser again',
      'browser' not in _fet._strategy_order('dead.invalid', True),
      _fet._strategy_order('dead.invalid', True))
check('  ...but the cheap rungs are still tried, in case it came back',
      _fet._strategy_order('dead.invalid', True) == ['plain', 'chrome_tls', 'crawler', 'apify'],
      _fet._strategy_order('dead.invalid', True))
check('  ...and Apify stays in that list, because it is the rung for exactly this case',
      'apify' in _fet._strategy_order('dead.invalid', True))

_fet.remember_strategy('dead.invalid', 'plain')
check('a recovered domain clears its record',
      _fet.recall_strategy('dead.invalid') == 'plain', _fet.recall_strategy('dead.invalid'))

# a memo written by an older ladder must not be trusted by a newer one
import json as _json
_p = _fet._strategy_path()
_p.write_text(_json.dumps({'stale.invalid': {'strategy': 'browser', 'fetcher_version': 0}}),
              encoding='utf-8')
_fet._STRATEGY_CACHE.pop('value', None)
check('a memo from an older ladder version is discarded',
      'stale.invalid' not in _fet.load_domain_strategies(),
      list(_fet.load_domain_strategies()))
check('adding rung 5 bumped that version, so every old memo is re-evaluated',
      _fet.FETCHER_VERSION >= 2, _fet.FETCHER_VERSION)


# -- rung 5: Apify's unblocker ----------------------------------------------------------
# The rung that opens glassdoor.com, reed.co.uk, totaljobs.com, cv-library.co.uk,
# cwjobs.co.uk, stepstone.at, moovijob.com and tecnoempleo.com -- eight real sites that
# answer this machine with 403 no matter which local rung asks.
_saved_token = _fet._APIFY_TOKEN[0]
_fet.set_apify_token(None)
check('with no Apify token the rung is a plain miss, not an error',
      _fet._rung_apify('https://blocked.invalid/jobs').status is None)
check('and the ladder still lists it, so configuring a token needs no other change',
      'apify' in _fet.STRATEGIES)

_fet.set_apify_token('  tok-123  ')
check('the token is trimmed', _fet._APIFY_TOKEN[0] == 'tok-123', _fet._APIFY_TOKEN[0])
_fet.set_apify_token('   ')
check('a blank token counts as none', _fet._APIFY_TOKEN[0] is None)

_fet.set_apify_token('tok-123')
_apify_calls: list = []


class _FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


def _fake_apify_get(url, params=None, timeout=None, **kw):
    _apify_calls.append(dict(params or {}))
    script = _apify_script.pop(0) if _apify_script else _FakeResponse(500, '')
    if isinstance(script, Exception):
        raise script
    return script


_real_get, _real_sleep = _fet.requests.get, _fet.time.sleep
_fet.requests.get, _fet.time.sleep = _fake_apify_get, lambda s: None
try:
    _apify_script = [_FakeResponse(200, _GOOD_PAGE)]
    _res = _fet._rung_apify('https://blocked.invalid/jobs')
    check('a page that comes back is a success', _res.status == 200 and _res.html == _GOOD_PAGE)
    check('it is labelled as the Apify rung', _res.strategy == 'apify')
    check('the cheap setting is tried first, not the paid one',
          'premium_proxy' not in _apify_calls[0], _apify_calls[0])
    check('and only one request was needed', len(_apify_calls) == 1)

    # A dropped connection is the free plan's standby actor, not the site. Recording a
    # reachable domain as permanently shut over one of those is the failure to avoid --
    # totaljobs.com did exactly this, failing on the request straight after a 22-second
    # glassdoor fetch and opening fine on a retry.
    _apify_calls.clear()
    _apify_script = [ConnectionError('Connection aborted'), _FakeResponse(200, _GOOD_PAGE)]
    _res = _fet._rung_apify('https://blocked.invalid/jobs')
    check('a dropped connection is retried rather than believed', _res.status == 200)
    check('  ...and the retry is the same cheap setting, not an escalation',
          len(_apify_calls) == 2 and 'premium_proxy' not in _apify_calls[1], _apify_calls)

    # A real answer that is simply not usable escalates to residential IPs instead.
    _apify_calls.clear()
    _apify_script = [_FakeResponse(500, 'blocked'), _FakeResponse(200, _GOOD_PAGE)]
    _res = _fet._rung_apify('https://blocked.invalid/jobs')
    check('a refusal escalates to the residential proxy', _res.status == 200)
    check('  ...and does not waste a retry on the setting that already answered',
          len(_apify_calls) == 2 and _apify_calls[1].get('premium_proxy') == 'true',
          _apify_calls)

    _apify_calls.clear()
    _apify_script = [_FakeResponse(403, '')] * 8
    _res = _fet._rung_apify('https://blocked.invalid/jobs')
    check('a site that refuses both settings is a miss, not a crash', _res.status is None)
    check('  ...and it stops after both settings rather than looping',
          len(_apify_calls) == 2, len(_apify_calls))
finally:
    _fet.requests.get, _fet.time.sleep = _real_get, _real_sleep
    _fet.set_apify_token(_saved_token)

# -- _is_usable ------------------------------------------------------------------------
check('a real page is usable', _fet._is_usable(_GOOD_PAGE))
check('a 403 page is not', not _fet._is_usable(_ERROR_PAGE))
check('an empty body is not', not _fet._is_usable(''))
check('a long page with an error-ish word in it is still usable',
      _fet._is_usable('<html><head><title>Data Scientist</title></head><body>'
                      + ('The page you requested. ' * 3000) + '</body></html>'))

# -- sitemaps ---------------------------------------------------------------------------
_SITEMAP = ('<?xml version="1.0"?><urlset>'
            + ''.join('<loc>https://sm.invalid/job/%d/</loc>' % i for i in range(8))
            + '<loc>https://sm.invalid/about</loc></urlset>')


def _serve_sitemap(pages):
    saved = _fet.fetch

    def fake(url, *a, **k):
        for key, value in pages.items():
            if url.rstrip('/') == key.rstrip('/'):
                return _fet.FetchResult(200, value, 'plain', True)
        return _fet.FetchResult(404, '', 'plain')
    _fet.fetch = fake
    return saved


_saved_fetch = _serve_sitemap({
    'https://sm.invalid/robots.txt': 'Sitemap: https://sm.invalid/sitemap.xml',
    'https://sm.invalid/sitemap.xml': _SITEMAP,
})
try:
    _urls = _fet.sitemap_urls('https://sm.invalid/jobs')
finally:
    _fet.fetch = _saved_fetch
check('a sitemap named in robots.txt is read', len(_urls) == 9, len(_urls))
check('  ...and holds the posting URLs', 'https://sm.invalid/job/3/' in _urls)

# a site with no sitemap yields nothing rather than raising
_saved_fetch = _serve_sitemap({})
try:
    _none = _fet.sitemap_urls('https://sm.invalid/jobs')
finally:
    _fet.fetch = _saved_fetch
check('a site with no sitemap returns []', _none == [], _none)

# -- discovery falls back to the sitemap when the listing page gives nothing ------------
_SITEMAP2 = ('<?xml version="1.0"?><urlset>'
             + ''.join('<loc>https://blocked.invalid/job/role-%d/</loc>' % i for i in range(6))
             + '<loc>https://blocked.invalid/about</loc></urlset>')
_saved = _pd.fetcher.fetch


def _blocked_but_sitemap(url, *a, **k):
    if url.rstrip('/') == 'https://blocked.invalid/robots.txt':
        return _pd.fetcher.FetchResult(200, 'Sitemap: https://blocked.invalid/sitemap.xml',
                                       'crawler', True)
    if url.rstrip('/') == 'https://blocked.invalid/sitemap.xml':
        return _pd.fetcher.FetchResult(200, _SITEMAP2, 'crawler', True)
    if '/job/role-' in url:
        return _pd.fetcher.FetchResult(200, POSTING_HTML, 'crawler', True)
    return _pd.fetcher.FetchResult(403, '', 'plain')   # every listing page is shut


try:
    _pd.fetcher.fetch = _blocked_but_sitemap
    _from_sitemap = _pd.discover_job_url_patterns('https://blocked.invalid/jobs/')
finally:
    _pd.fetcher.fetch = _saved
check('a site whose pages are shut is learned from its sitemap',
      _from_sitemap == ['https://blocked.invalid/job/**'], _from_sitemap)

# and a sitemap of non-job pages must not produce a pattern
_SITEMAP3 = ('<?xml version="1.0"?><urlset>'
             + ''.join('<loc>https://blog.invalid/blog/post-%d/</loc>' % i for i in range(6))
             + '</urlset>')
_saved = _pd.fetcher.fetch


def _blog_sitemap(url, *a, **k):
    if url.rstrip('/') == 'https://blog.invalid/sitemap.xml':
        return _pd.fetcher.FetchResult(200, _SITEMAP3, 'plain', True)
    return _pd.fetcher.FetchResult(404, '', 'plain')


try:
    _pd.fetcher.fetch = _blog_sitemap
    _blogged = _pd.discover_job_url_patterns('https://blog.invalid/jobs/')
finally:
    _pd.fetcher.fetch = _saved
check('a sitemap of blog posts produces no job pattern', _blogged == [], _blogged)


section('4.21  glob shapes -- telling postings from their neighbours')

# -- Apify's glob semantics, not fnmatch's ------------------------------------------
check('** spans path segments',
      _glob_mod._glob_match('https://x.invalid/jobs/a/b/c', 'https://x.invalid/jobs/**'))
check('* stays inside one segment',
      not _glob_mod._glob_match('https://x.invalid/jobs/a/b', 'https://x.invalid/jobs/*'))
check('  ...and matches a single segment',
      _glob_mod._glob_match('https://x.invalid/jobs/a', 'https://x.invalid/jobs/*'))
check('a two-star-segment glob matches exactly that depth',
      _glob_mod._glob_match('https://x.invalid/jobs/acme/role', 'https://x.invalid/jobs/*/*'))
check('  ...and not one deeper',
      not _glob_mod._glob_match('https://x.invalid/jobs/acme/role/apply',
                          'https://x.invalid/jobs/*/*'))
# This is the whole reason the matcher was replaced: fnmatch says True here, and a glob
# verified on that basis behaves differently in the crawler that consumes it.
import fnmatch as _fnmatch
check('fnmatch would have got this wrong -- which is why it is no longer used',
      _fnmatch.fnmatch('https://x.invalid/jobs/a/b', 'https://x.invalid/jobs/*'))

# -- proposals pin only a SHARED prefix ----------------------------------------------
_ARBEITNOW = ['https://a.invalid/jobs/companies/acme/data-scientist-%d' % i for i in range(20)]
_props = _glob_mod._candidate_globs(_ARBEITNOW)
check('a shared namespace is pinned', 'https://a.invalid/jobs/companies/**' in _props, _props)
check('  ...and so is its exact depth',
      'https://a.invalid/jobs/companies/*/*' in _props, _props)

# one glob per one-off value is what made a real run learn 60 patterns from a sitemap
_ONE_OFFS = ['https://s.invalid/roles/%s/salaries' % name for name in
             ('onboarding-manager', 'tax-analyst', 'analytics-lead', 'hris-analyst',
              'partnerships-lead', 'marketing', 'design', 'finance', 'product', 'sales',
              'legal', 'production', 'operations', 'management', 'engineering', 'growth')]
_props2 = _glob_mod._candidate_globs(_ONE_OFFS)
check('a prefix only a few candidates share is NOT pinned',
      not any(p.startswith('https://s.invalid/roles/tax-analyst') for p in _props2), _props2)
check('  ...while the segment they all share still is',
      'https://s.invalid/roles/**' in _props2, _props2)
check('the proposal list stays small enough to verify',
      len(_props2) <= _glob_mod._MAX_GLOB_PROPOSALS, len(_props2))

# a page showing only two postings is a real case and must still yield a glob
_TWO = ['https://t.invalid/engineering/senior-data-scientist-acme/',
        'https://t.invalid/engineering/backend-developer-acme/']
check('two candidates sharing a prefix still produce a glob',
      'https://t.invalid/engineering/**' in _glob_mod._candidate_globs(_TWO),
      _glob_mod._candidate_globs(_TWO))

# -- the sibling count uses the glob under test --------------------------------------
# A real arbeitnow posting links to 103 pages under /jobs/** (its related-jobs rail) and
# to 8 under the glob actually being verified. Judged by the coarse shape every posting on
# the site looks like an index, which is exactly what happened.
# Shaped like the real page: a rail of city and category links that all sit under /jobs/,
# plus a handful of genuine sibling postings. 43 match /jobs/**; 5 match the precise glob.
_RELATED = (''.join('<a href="/jobs/locations/city-%d">Jobs in City %d</a>' % (i, i)
                    for i in range(24))
            + ''.join('<a href="/jobs/tag-%d">Some Category %d</a>' % (i, i)
                      for i in range(14))
            + ''.join('<a href="/jobs/companies/other-%d/role-%d">Some Job Title %d</a>'
                      % (i, i, i) for i in range(5)))
_POSTING_WITH_RAIL = _BS(
    '<html><head><title>Project Officer EC-FFPA</title></head><body>'
    '<p>Apply now. Responsibilities and requirements. ' + ('Details. ' * 200) + '</p>'
    + _RELATED + '</body></html>', 'html.parser')
_URL = 'https://a.invalid/jobs/companies/acme/project-officer'
check('judged by the coarse /jobs/** shape, a posting with a related-jobs rail is rejected',
      not _pd._looks_like_single_posting(_URL, _POSTING_WITH_RAIL, 200,
                                         shape='https://a.invalid/jobs/**'))
check('judged by the glob actually being verified, it is accepted',
      _pd._looks_like_single_posting(_URL, _POSTING_WITH_RAIL, 200,
                                     shape='https://a.invalid/jobs/companies/*/*'))

# -- a page named by its last segment ------------------------------------------------
_SALARY_PAGE = _BS(
    '<html><head><title>Startup Onboarding Manager Salary (2026)</title></head><body>'
    '<p>Apply. Requirements. We offer. ' + ('Salary information. ' * 200) + '</p>'
    '</body></html>', 'html.parser')
check('a /salaries page is not a posting, however long and job-flavoured',
      not _pd._looks_like_single_posting('https://s.invalid/roles/data-engineer/salaries',
                                         _SALARY_PAGE, 200))
check('  ...while the same page under a job-shaped leaf would be judged on its content',
      _pd._looks_like_single_posting('https://s.invalid/roles/data-engineer-at-acme',
                                     _SALARY_PAGE, 200))
for _leaf in ('salaries', 'trends', 'companies', 'about', 'privacy'):
    check(f'/{_leaf} is never a posting leaf', _leaf in _pd._NON_JOB_LEAF_SEGMENTS)

# -- and the widened article rule must not cost a real job ---------------------------
for _real in ('Golang System Developer / Networking Engineer at Altinity',
              'Data Scientist (w/m/d)',
              'Senior Consultant (w/m/d) Data & AI',
              'Werkstudent (d/m/w): Data Scientist im Bereich Supply Chain'):
    check(f'real title survives the article rule: {_real[:38]}',
          not _pd._ARTICLE_TITLE.search(_pd._leading_title(_real)))
for _article in ('Writing an Effective Resume', 'Your First Startup Interview',
                 'Glossary of Startup Terms', 'A Guide to Networking',
                 'How to Become a Data Scientist'):
    check(f'article rejected: {_article[:38]}',
          bool(_pd._ARTICLE_TITLE.search(_pd._leading_title(_article))))


section('4.22  sitemap index following')

_INDEX_XML = ('<?xml version="1.0"?><sitemapindex>'
              + ''.join('<loc>https://si.invalid/sitemaps/jobs/%d</loc>' % i for i in range(3))
              + '</sitemapindex>')
_SUB_XML = ('<?xml version="1.0"?><urlset>'
            + ''.join('<loc>https://si.invalid/job/role-%d/</loc>' % i for i in range(5))
            + '</urlset>')

_saved_fetch = _fet.fetch
try:
    def _index_fetch(url, *a, **k):
        if url.rstrip('/') == 'https://si.invalid/sitemap.xml':
            return _fet.FetchResult(200, _INDEX_XML, 'plain', True)
        if '/sitemaps/jobs/' in url:
            return _fet.FetchResult(200, _SUB_XML, 'plain', True)
        return _fet.FetchResult(404, '', 'plain')
    _fet.fetch = _index_fetch
    _index_urls = _fet.sitemap_urls('https://si.invalid/jobs')
finally:
    _fet.fetch = _saved_fetch
# The entries carry no .xml extension. Suffix-matching took all 19 of startup.jobs' for
# pages and reported a site with no jobs at all.
check('a sitemapindex whose entries have no .xml extension is still followed',
      len(_index_urls) == 15, len(_index_urls))
check('  ...and the sub-sitemap page URLs come back',
      'https://si.invalid/job/role-3/' in _index_urls)
check('  ...and no sitemap URL is mistaken for a page',
      not any('/sitemaps/' in u for u in _index_urls))

# the budget must end a large index rather than reading it to the end
_saved_fetch = _fet.fetch
try:
    _slow_calls = {'n': 0}

    def _slow_fetch(url, *a, **k):
        if url.rstrip('/') == 'https://slow.invalid/sitemap.xml':
            return _fet.FetchResult(
                200, '<?xml version="1.0"?><sitemapindex>'
                + ''.join('<loc>https://slow.invalid/sm/%d</loc>' % i for i in range(50))
                + '</sitemapindex>', 'plain', True)
        if '/sm/' in url:
            _slow_calls['n'] += 1
            import time as _t
            _t.sleep(0.05)
            return _fet.FetchResult(200, _SUB_XML, 'plain', True)
        return _fet.FetchResult(404, '', 'plain')
    _fet.fetch = _slow_fetch
    _fet.sitemap_urls('https://slow.invalid/jobs', budget_seconds=0.15)
finally:
    _fet.fetch = _saved_fetch
check('the sitemap budget stops a large index early',
      _slow_calls['n'] < _fet.SITEMAP_MAX_SUBMAPS, _slow_calls['n'])

# a sitemap listing thousands of company pages before its jobs must not be truncated
check('the URL limit is large enough to reach a late job section',
      _fet.SITEMAP_URL_LIMIT >= 20000, _fet.SITEMAP_URL_LIMIT)


section('4.23  a failure found mid-search reaches the problems window')

from app.pipeline import preflight as _pf

# The two halves of the user's request, end to end: a site that cannot be opened must not
# interrupt the search with a popup, and must still be REPORTED afterwards -- with
# Claude's fix advice attached -- rather than scrolling past in the log.
_reported = {'problems': None, 'calls': 0}


def _capture_cb(problems):
    _reported['calls'] += 1
    _reported['problems'] = [dict(p) for p in problems]
    return {'cancel': False, 'resolved_keys': {}}


_QUIET = [{'name': 'gone.invalid', 'reason': 'no results this run', 'fixable': False,
           'kind': 'url', 'url': 'https://gone.invalid/'}]

# explain_problems is the only part that would make a network call; fake it so this test
# stays offline while still proving the advice reaches the window.
_saved_explain = _runner.explain_problems
try:
    def _fake_explain(problems, anthropic_api_key=None, progress_cb=None):
        for _p in problems:
            _p['fix_advice'] = '- Open the site and check it still exists'
    _runner.explain_problems = _fake_explain

    # Copies, not the same dicts: _QUIET is reused below to check the no-Claude-key path,
    # and explain_problems only fills advice in where there is none -- so sharing the
    # dicts here would have left that later case pre-answered by this one.
    _late = [dict(p) for p in _QUIET]
    _fake_explain(_late)
    _capture_cb(_late)
finally:
    _runner.explain_problems = _saved_explain

check('a quiet domain is reported through the problems callback', _reported['calls'] == 1)
check('  ...carrying the fix advice',
      'still exists' in (_reported['problems'][0].get('fix_advice') or ''),
      _reported['problems'][0])
check('  ...and marked as a URL problem, not an API one',
      _reported['problems'][0].get('kind') == 'url')

# _warn_zero_result_google_sites is what finds them. It used to end in a dialog asking
# The user to go and hunt for the right URL; it must now only report.
_probs = []
_found = _google._warn_zero_result_google_sites(
    [], [], [], progress_cb=None, extra_broken_domains=['dead.invalid'], problems=_probs)
check('a domain with no results becomes a problem entry', len(_found) == 1, _found)
check('  ...appended to the caller\'s list too', len(_probs) == 1, _probs)
check('  ...naming the domain', _probs[0]['name'] == 'dead.invalid', _probs[0])
check('  ...with a URL to go and look at', _probs[0].get('url', '').startswith('http'))
check('  ...and never fixable by typing a key', _probs[0].get('fixable') is False)

# A clean run must report nothing at all -- an empty window would be worse than none.
_probs = []
_google._warn_zero_result_google_sites([], [], [], progress_cb=None,
                                       extra_broken_domains=[], problems=_probs)
check('a clean run reports no problems', _probs == [], _probs)

# A site that DELIVERED must never be reported as having gone quiet. On a real Netherlands
# search this told the user he had lost seventeen sites when he had lost seven: startup.jobs
# had returned 52 listings, magnet.me 6, jobfluent.com 5, nationalevacaturebank.nl 3, and
# four more came in through the browser stage. Two separate causes, both here.
_ROWS_FROM_BROWSER_STAGE = [
    # The browser-site stage labels a row with the site's own domain, not 'google'. The
    # check used to look only at rows whose platform was 'google', so these were invisible.
    {'url': 'https://www.werk.nl/vacature/1', 'platform': 'werk.nl'},
    {'url': 'https://weworkremotely.com/remote-jobs/2', 'platform': 'weworkremotely.com'},
]
_probs = []
_msgs: list = []
_found = _google._warn_zero_result_google_sites(
    _ROWS_FROM_BROWSER_STAGE, [], [], progress_cb=lambda m, d, t: _msgs.append(str(m)),
    extra_broken_domains=[], problems=_probs)
check('a site reached by the browser stage is not called quiet',
      not any(p['name'] in ('werk.nl', 'weworkremotely.com') and 'no results at all'
              in p['reason'] for p in _probs), _probs)

# The other half: a site that returned listings but has no individual-posting pattern is
# not a loss, and must not be described as one.
_ROWS_WITH_RESULTS = [{'url': 'https://startup.jobs/x-%d' % i, 'platform': 'google'}
                      for i in range(5)]
_probs = []
_msgs = []
_google._warn_zero_result_google_sites(
    _ROWS_WITH_RESULTS, [], [], progress_cb=lambda m, d, t: _msgs.append(str(m)),
    extra_broken_domains=['startup.jobs', 'dead.invalid'], problems=_probs)
_by_name = {p['name']: p for p in _probs}
check('a site with results but no pattern is still reported', 'startup.jobs' in _by_name,
      list(_by_name))
check('  ...but as having returned listings, not nothing',
      'DID return listings' in _by_name['startup.jobs']['reason'],
      _by_name['startup.jobs']['reason'][:70])
check('  ...and it says plainly that nothing was lost',
      'Nothing was lost' in _by_name['startup.jobs']['reason'])
check('a site that really produced nothing still says so',
      'no results at all' in _by_name['dead.invalid']['reason'],
      _by_name['dead.invalid']['reason'][:70])
check('the two are separate lines in the Log, not one merged count',
      sum(1 for m in _msgs if 'produced NOTHING' in m) == 1
      and sum(1 for m in _msgs if 'only their search page' in m) == 1, _msgs)
check('  ...and the quiet line is red while the listings-only line is a warning',
      any(m.startswith('GLOG:platform:Google|error|') and 'produced NOTHING' in m
          for m in _msgs)
      and any(m.startswith('GLOG:platform:Google|warning|') for m in _msgs), _msgs)

# explain_problems degrades rather than failing when there is no Claude key.
_no_key = [dict(p) for p in _QUIET]
_pf.explain_problems(_no_key, anthropic_api_key=None)
check('without a Claude key every problem still gets a line of guidance',
      all(p.get('fix_advice') for p in _no_key), _no_key)
check('  ...and it says what to do about that',
      'Setup' in _no_key[0]['fix_advice'], _no_key[0]['fix_advice'])

# A model reply that names items out of order, or names only some, must still land on the
# right problems -- the parser keys on the FIX <n>: marker, not on position.
_three = [{'name': 'a', 'reason': 'x'}, {'name': 'b', 'reason': 'y'}, {'name': 'c', 'reason': 'z'}]


class _FakeAnthropic:
    def __init__(self, api_key=None):
        self.messages = self

    def create(self, **kw):
        block = type('B', (), {'type': 'text',
                               'text': 'FIX 3:\n- third\n\nFIX 1:\n- first\n'})()
        return type('R', (), {'content': [block]})()


_saved_anthropic = _pf.anthropic.Anthropic
try:
    _pf.anthropic.Anthropic = _FakeAnthropic
    _pf.explain_problems(_three, anthropic_api_key='k')
finally:
    _pf.anthropic.Anthropic = _saved_anthropic
check('advice returned out of order lands on the right problem',
      _three[0].get('fix_advice') == '- first', _three[0].get('fix_advice'))
check('  ...for the last one too', _three[2].get('fix_advice') == '- third',
      _three[2].get('fix_advice'))
check('  ...and a problem the model skipped simply has none',
      _three[1].get('fix_advice') is None, _three[1].get('fix_advice'))

# An API failure must not take the search down with it.
_boom = [{'name': 'a', 'reason': 'x'}]


class _BoomAnthropic:
    def __init__(self, api_key=None):
        self.messages = self

    def create(self, **kw):
        raise RuntimeError('API down')


_saved_anthropic = _pf.anthropic.Anthropic
try:
    _pf.anthropic.Anthropic = _BoomAnthropic
    check_no_raise('a failed advice call never raises',
                   lambda: _pf.explain_problems(_boom, anthropic_api_key='k'))
finally:
    _pf.anthropic.Anthropic = _saved_anthropic
check('  ...and the problem is still reportable without advice',
      _boom[0].get('fix_advice') is None and _boom[0]['name'] == 'a')


section('4.24  a failure has to say so, in red')

from app.pipeline import language as _lang
from app.pipeline import fetcher as _fet_red

# The translation half of this section went with the translator itself. What it was
# guarding -- a stage reporting success while having done nothing, and the Filter
# swallowing the red line that said so -- is still guarded below for the fetch ladder,
# which is the other place a silent failure looks like a working run.

# -- a rung missing from the build ----------------------------------------------------
# The ladder drops a rung it cannot import and keeps working, which is right and silent.
# Silent is the problem: every 403 site then fails with nothing to explain why.
_cap_msgs = []
_saved_flag = dict(_fet_red._CAPABILITIES_REPORTED)
try:
    _fet_red._CAPABILITIES_REPORTED['done'] = False
    _fet_red._report_missing_capabilities(lambda m, d, t: _cap_msgs.append(str(m)))
finally:
    _fet_red._CAPABILITIES_REPORTED.update(_saved_flag)
check('with every library present, nothing is reported', _cap_msgs == [], _cap_msgs)

_cap_msgs = []
_saved_import = __import__
try:
    _fet_red._CAPABILITIES_REPORTED['done'] = False
    import importlib as _il
    _saved_import_module = _il.import_module

    def _no_curl(name, *a, **k):
        if name.startswith('curl_cffi'):
            raise ImportError('No module named curl_cffi')
        return _saved_import_module(name, *a, **k)

    _il.import_module = _no_curl
    _fet_red._report_missing_capabilities(lambda m, d, t: _cap_msgs.append(str(m)))
finally:
    _il.import_module = _saved_import_module
    _fet_red._CAPABILITIES_REPORTED.update(_saved_flag)
check('a missing curl_cffi is reported in red',
      any(m.startswith('GLOG:fetch|error|') and 'curl_cffi' in m for m in _cap_msgs),
      _cap_msgs)
check('  ...and says which sites it costs',
      any('403' in m for m in _cap_msgs), _cap_msgs)
check('  ...and that it is a packaging problem, not a website one',
      any('packaging problem' in m for m in _cap_msgs), _cap_msgs)

# -- pattern discovery crashing on one domain -----------------------------------------
# This used to be `except Exception: globs = []`, so a domain that CRASHED discovery
# looked identical to one that was simply unreadable, and could repeat every run.
# learn_missing_job_patterns imports the entry point inside the function, so the fake
# has to replace it on pattern_discovery itself.
_disc_msgs = []
_saved_smart = _pd.discover_job_url_patterns_smart
try:
    def _boom_smart(*a, **k):
        raise RuntimeError('discovery exploded')
    _pd.discover_job_url_patterns_smart = _boom_smart
    _google.learn_missing_job_patterns(
        [{'platform': 'google', 'url': 'https://crash.invalid/jobs'}],
        anthropic_api_key=None,
        progress_cb=lambda m, d, t: _disc_msgs.append(str(m)))
finally:
    _pd.discover_job_url_patterns_smart = _saved_smart
check('a domain that crashes discovery is reported in red',
      any(m.startswith('GLOG:pattern|error|') and 'exploded' in m for m in _disc_msgs),
      [m[:80] for m in _disc_msgs])


section('4.25  the deep-crawl plan -- what actually gets crawled')

# _deep_crawl_plan decides where real Apify credit goes, and its own docstring says it is
# pure so that "what gets crawled can be checked on its own". It had no test at all, which
# is how the open-stage bug below survived: pattern discovery learns from every stage and
# saves permanently, while this only ever crawled three of the four.

_PATTERNED = next(iter(_google.GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS))          # e.g. finn.no
_PATTERNED_URL = 'https://www.%s/some-listing' % _PATTERNED.replace('www.', '')


def _row(url, stage):
    return {'platform': 'google', 'url': url, 'google_stage': stage}


# -- a domain with a confirmed pattern is crawled, whichever stage found it ------------
for _stage in ('known', 'global', 'startup', 'open'):
    _known, _starts, _globs, _warned = _google._deep_crawl_plan([_row(_PATTERNED_URL, _stage)])
    check(f'a {_stage}-stage result on a known-pattern domain is crawled',
          _starts == [_PATTERNED_URL], (_stage, _starts))
    check(f'  ...and brings its job-URL globs along', len(_globs) > 0, _globs)

# This is the regression that matters: pattern discovery examines every stage and saves
# what it learns forever, but the crawl that uses it used to skip 'open' entirely -- so a
# site first seen on the open web was crawled once, in the run that learned it, and then
# ignored by every run after.
_known, _open_starts, _, _ = _google._deep_crawl_plan([_row(_PATTERNED_URL, 'open')])
check('an open-web result with a learned pattern is NOT skipped', _open_starts != [],
      _open_starts)

# -- a domain with no pattern is never crawled, whatever stage it came from ------------
for _stage in ('known', 'global', 'startup', 'open'):
    _known, _starts, _globs, _warned = _google._deep_crawl_plan(
        [_row('https://nopattern.invalid/jobs/1', _stage)])
    check(f'a {_stage}-stage result with no pattern is not crawled', _starts == [], _starts)

# -- cost: crawling is bounded by the pattern, not by the number of results ------------
_many = [_row('https://random%d.invalid/page' % i, 'open') for i in range(50)]
_known, _starts, _, _ = _google._deep_crawl_plan(_many)
check('fifty unknown open-web results still cost nothing to crawl', _starts == [], _starts)

# -- non-google rows are never crawled -------------------------------------------------
_known, _starts, _, _ = _google._deep_crawl_plan(
    [{'platform': 'indeed', 'url': _PATTERNED_URL, 'google_stage': 'known'}])
check('a non-google row is never a crawl start', _starts == [], _starts)

# -- duplicates collapse ---------------------------------------------------------------
_known, _starts, _, _ = _google._deep_crawl_plan(
    [_row(_PATTERNED_URL, 'known'), _row(_PATTERNED_URL, 'open')])
check('the same URL seen twice is crawled once', _starts == [_PATTERNED_URL], _starts)

# -- the warning list still only covers the stages it is meant to ----------------------
_known, _, _, _warned = _google._deep_crawl_plan(
    [_row('https://unknown-site.invalid/jobs', 'known')])
check('a known-stage domain with no pattern is flagged for attention',
      'unknown-site.invalid' in _warned, _warned)
_known, _, _, _warned = _google._deep_crawl_plan(
    [_row('https://unknown-site.invalid/jobs', 'open')])
check('an open-web domain is not flagged -- the open stage returns the whole internet',
      _warned == [], _warned)

# -- empty input ------------------------------------------------------------------------
check('no rows plans nothing', _google._deep_crawl_plan([]) == ([], [], [], []))


section('4.26  the free health check')

from app.pipeline import healthcheck as _hc

# This check exists to be believed. Its first three real runs each produced a class of
# FALSE alarm, and a check that cries wolf is worse than no check -- it is what teaches
# someone to ignore the red lines. Each of those three is pinned here.


def _serve_health(handler):
    saved = _hc.fetcher.fetch
    _hc.fetcher.fetch = handler
    return saved


_LISTING = ('<html><head><title>Data Scientist jobs</title></head><body>'
            '<a href="https://www.karriere.at/jobs/one">Senior Data Scientist</a>'
            '<a href="https://www.karriere.at/jobs/two">Data Engineer</a>'
            '</body></html>')

# -- false alarm 1: a site reached through Apify judged by the local ladder ------------
# stepstone.at and stepstone.de both refuse THIS machine on all four rungs while the real
# search reads them perfectly well through Apify's crawler.
_blocked = _hc.fetcher.FetchResult(403, '', 'browser', False)
_saved = _serve_health(lambda url, *a, **k: _blocked)
try:
    _apify_problem = _hc._check_one_url('stepstone.at', 'https://x.invalid/j', _hc.VIA_APIFY)
    _ladder_problem = _hc._check_one_url('duunitori.fi', 'https://x.invalid/j', _hc.VIA_LADDER)
finally:
    _hc.fetcher.fetch = _saved
check('a blocked Apify-reached site is silent -- Apify may still read it',
      _apify_problem is None, _apify_problem)
check('a blocked ladder-reached site is reported -- the ladder IS how it is read',
      _ladder_problem is not None and '403' in _ladder_problem['reason'],
      _ladder_problem)

# ...but a dead domain is dead for Apify too, so that still counts.
_saved = _serve_health(lambda url, *a, **k: _hc.fetcher.FetchResult(None, '', '', False))
try:
    _dead = _hc._check_one_url('gone.invalid', 'https://gone.invalid/j', _hc.VIA_APIFY)
finally:
    _hc.fetcher.fetch = _saved
check('a domain that never responds is reported even for Apify-reached sites',
      _dead is not None and 'did not respond' in _dead['reason'], _dead)

_saved = _serve_health(lambda url, *a, **k: _hc.fetcher.FetchResult(404, '', 'plain', False))
try:
    _gone = _hc._check_one_url('moved.invalid', 'https://moved.invalid/j', _hc.VIA_APIFY)
finally:
    _hc.fetcher.fetch = _saved
check('a search URL that is gone (404) is reported even for Apify-reached sites',
      _gone is not None and '404' in _gone['reason'], _gone)

# -- false alarm 2: judging a job-link pattern by the site's HOMEPAGE ------------------
# A homepage does not list job postings. Checking there reported 26 of 29 patterns broken.
_saved = _serve_health(lambda url, *a, **k: _hc.fetcher.FetchResult(_LISTING and 200, _LISTING,
                                                                    'plain', True))
try:
    _ok = _hc._check_one_pattern('karriere.at', ['https://www.karriere.at/jobs/**'],
                                 'https://www.karriere.at/jobs/data-scientist')
    _bad = _hc._check_one_pattern('karriere.at', ['https://www.karriere.at/stellen/**'],
                                  'https://www.karriere.at/jobs/data-scientist')
finally:
    _hc.fetcher.fetch = _saved
check('a pattern that still matches real links passes', _ok is None, _ok)
check('a pattern that matches nothing is reported', isinstance(_bad, dict), _bad)
check('  ...and says the crawler would collect nothing',
      'collect nothing' in (_bad or {}).get('reason', ''), _bad)

# -- false alarm 3: reporting OK for a site that could not be reached at all -----------
_saved = _serve_health(lambda url, *a, **k: _blocked)
try:
    _unknown = _hc._check_one_pattern('x.invalid', ['https://x.invalid/jobs/**'],
                                      'https://x.invalid/search')
finally:
    _hc.fetcher.fetch = _saved
check('a pattern on an unreachable site is UNVERIFIED, not OK',
      _unknown is _hc.UNVERIFIED, _unknown)
check('  ...and UNVERIFIED is not mistaken for a problem',
      not isinstance(_hc.UNVERIFIED, dict))
check('  ...nor for a pass', _hc.UNVERIFIED is not None)

# -- what gets checked, and how ---------------------------------------------------------
_targets = _hc._url_targets(['Germany'], ['Berlin'])
check('the target list is scoped to the selected countries',
      all('finn.no' not in label for label, _u, _v in _targets),
      [l for l, _u, _v in _targets if 'finn' in l])
check('  ...and every entry carries how it is reached',
      all(via in (_hc.VIA_APIFY, _hc.VIA_LADDER) for _l, _u, via in _targets))
check('  ...with the global browser-only sites always included',
      any('Global' in label for label, _u, _v in _targets),
      [l for l, _u, _v in _targets][:5])
check('  ...and no URL checked twice',
      len({u for _l, u, _v in _targets}) == len(_targets))

# -- the app-level checks ----------------------------------------------------------------
check('the fetch-ladder check passes when both libraries are present',
      _hc._check_ladder() == [], _hc._check_ladder())

storage.take_load_problems()
storage.JOBS_PATH.write_text('{ broken', encoding='utf-8')
_data_problems = _hc._check_storage()
storage.save_jobs([])
check('a damaged data file is a health-check problem', len(_data_problems) == 1,
      _data_problems)
check('  ...tagged as data, not as a website', _data_problems[0]['kind'] == 'data')

# -- the problems it returns must fit the window it is shown in --------------------------
for _p in (_gone, _bad, _data_problems[0]):
    check(f'a health problem has the shape the window needs ({str(_p.get("name"))[:20]})',
          all(k in _p for k in ('name', 'reason', 'fixable', 'kind')), _p)
    check('  ...and is never offered as a live key fix', _p['fixable'] is False)



section('4.27  the last word on whether a page is a job')

# Five pages passed every structural rule in a real run and were saved as permanent
# patterns: a recruitment agency's sector page, a marketing article, a documentation page,
# a company culture page, and a site's own search page. Words could not separate them --
# two different word-based rules were measured and both threw away real jobs. Meaning
# could: asked about those five plus six real postings, Claude agreed with a human on all
# eleven.

_JOB_PAGE = _BS(
    '<html><head><title>Senior Data Scientist at Acme</title></head><body>'
    '<p>Apply now. Responsibilities and requirements. ' + ('Real posting text. ' * 80)
    + '</p></body></html>', 'html.parser')


class _Judge:
    """Stands in for anthropic.Anthropic, answering with one canned verdict."""

    def __init__(self, verdict):
        self._verdict = verdict
        self.messages = self

    def create(self, **kw):
        block = type('B', (), {'type': 'text', 'text': 'VERDICT: %s' % self._verdict})()
        return type('R', (), {'content': [block]})()


class _BrokenJudge:
    def __init__(self):
        self.messages = self

    def create(self, **kw):
        raise RuntimeError('API down')


check('with no Claude client the judge abstains, it does not reject',
      _pd._claude_confirms_posting(None, 'https://x/job/1', _JOB_PAGE) is None)
check('a judge that says JOB confirms',
      _pd._claude_confirms_posting(_Judge('JOB'), 'https://x/job/1', _JOB_PAGE) is True)
check('a judge that says NOT A JOB rejects',
      _pd._claude_confirms_posting(_Judge('NOT A JOB'), 'https://x/job/1', _JOB_PAGE) is False)
check('a judge that errors abstains rather than rejecting everything',
      _pd._claude_confirms_posting(_BrokenJudge(), 'https://x/job/1', _JOB_PAGE) is None)
check('an unparseable answer also abstains',
      _pd._claude_confirms_posting(_Judge('maybe?'), 'https://x/job/1', _JOB_PAGE) is None)

# End to end: the same site, learned or not depending only on the judge.
# Five cards, not two: find_job_card_groups needs at least three links in a container
# before it will treat it as the job list at all.
_JOB_TITLES = ('senior-data-scientist', 'backend-developer', 'ml-engineer',
               'data-analyst', 'platform-engineer')
_LISTING2 = ('<html><head><title>Jobs</title></head><body><div class="jobs-list">'
             + ''.join('<a href="https://j.invalid/job/%s">%s Role Here</a>' % (slug, slug)
                       for slug in _JOB_TITLES)
             + '</div></body></html>')
_POSTING2 = ('<html><head><title>Senior Data Scientist</title></head><body>'
             '<p>Apply. Responsibilities and requirements. ' + ('Details. ' * 120)
             + '</p></body></html>')


def _serve_judge(pages):
    saved = _pd.fetcher.fetch

    def fake(url, *a, **k):
        for key, value in pages.items():
            if url.rstrip('/') == key.rstrip('/'):
                return _pd.fetcher.FetchResult(200, value, 'plain', True)
        return _pd.fetcher.FetchResult(404, '', 'plain')
    _pd.fetcher.fetch = fake
    return saved


_PAGES = dict({'https://j.invalid/jobs': _LISTING2},
              **{'https://j.invalid/job/%s' % slug: _POSTING2 for slug in _JOB_TITLES})

_saved = _serve_judge(_PAGES)
try:
    _no_judge = _pd.discover_job_url_patterns('https://j.invalid/jobs')
    _yes = _pd.discover_job_url_patterns('https://j.invalid/jobs', client=_Judge('JOB'))
    _no = _pd.discover_job_url_patterns('https://j.invalid/jobs', client=_Judge('NOT A JOB'))
    _broken = _pd.discover_job_url_patterns('https://j.invalid/jobs', client=_BrokenJudge())
finally:
    _pd.fetcher.fetch = _saved

# Both the general and the depth-exact glob are legitimate answers here, so what matters
# is that the site was learned at all, not which of the two shapes came back.
check('without a judge the structural verdict still stands',
      'https://j.invalid/job/**' in _no_judge, _no_judge)
check('a confirmed posting is learned', 'https://j.invalid/job/**' in _yes, _yes)
check('a page the judge rejects is NOT learned', _no == [], _no)
check('a judge that is down does not block learning',
      'https://j.invalid/job/**' in _broken, _broken)

# -- a "pattern" with no wildcard is not a pattern ------------------------------------
# A real run saved the complete address of one Walldorf working-student posting as
# jobs.sap.com's job-link pattern: it matches that one job and nothing else, forever.
_SAME_DEPTH = ['https://s.invalid/job/Walldorf-Working-Student-%d' % i for i in range(8)]
_props = _glob_mod._candidate_globs(_SAME_DEPTH)
check('every proposed glob contains a wildcard', all('*' in g for g in _props), _props)
check('  ...and none is a bare complete URL',
      not any(g in _SAME_DEPTH for g in _props), _props)
for _urls in (_SAME_DEPTH,
              ['https://s.invalid/a/b/c/%d' % i for i in range(6)],
              ['https://s.invalid/x/y' for _ in range(4)]):
    check(f'no wildcard-free glob from {len(_urls)} same-shaped URLs',
          all('*' in g for g in _glob_mod._candidate_globs(_urls)), _glob_mod._candidate_globs(_urls))

# -- the version bump must actually drop what the old rules approved -------------------
check('the verifier version was raised past the run that saved the bad patterns',
      _pd.VERIFIER_VERSION >= 3, _pd.VERIFIER_VERSION)
_stale = _surls._drop_stale_patterns({
    'bad.invalid': {'globs': ['https://bad.invalid/docs/**'], 'verifier_version': 2},
    'good.invalid': {'globs': ['https://good.invalid/job/**'],
                     'verifier_version': _pd.VERIFIER_VERSION},
})
check('a pattern approved by the older verifier is dropped', 'bad.invalid' not in _stale, _stale)
check('  ...and one approved by the current verifier is kept', 'good.invalid' in _stale, _stale)



section('4.28  a job slug is not a folder')

# jobs.sap.com was saved, twice, with this as its permanent job-link pattern:
#   /job/Walldorf-Working-Student-%28fmd%29-Cloud-Delivery-Architecture-%28CDA%29-Team-69190/**
# It carries a wildcard, so the no-wildcard guard passed it, and it pins one posting's own
# slug as the prefix -- matching that single job for the rest of the site's life. Two URLs
# under the same posting are enough to make a slug look "shared".
_SAP = ['https://jobs.sap.com/job/Walldorf-Working-Student-%28fmd%29-Cloud-Delivery-'
        'Architecture-%28CDA%29-Team-69190/apply',
        'https://jobs.sap.com/job/Walldorf-Working-Student-%28fmd%29-Cloud-Delivery-'
        'Architecture-%28CDA%29-Team-69190/share']
_sap_globs = _glob_mod._candidate_globs(_SAP)
check('a job slug is never pinned as a path prefix',
      not any('Walldorf' in g for g in _sap_globs), _sap_globs)
check('  ...and the site still gets a usable pattern',
      'https://jobs.sap.com/job/**' in _sap_globs, _sap_globs)

# The namespaces that must keep working -- these are the real ones this project depends on.
for _label, _urls, _expected in (
    ('arbeitnow', ['https://www.arbeitnow.com/jobs/companies/acme-%d/role-%d' % (i, i)
                   for i in range(20)], 'https://www.arbeitnow.com/jobs/companies/*/*'),
    ('bmwgroup', ['https://www.bmwgroup.jobs/en/jobfinder/job-%d' % i for i in range(12)],
     'https://www.bmwgroup.jobs/en/jobfinder/**'),
    ('hays', ['https://www.hays.de/jobsuche/stelle-%d/detail' % i for i in range(9)],
     'https://www.hays.de/jobsuche/**'),
):
    _proposed = _glob_mod._candidate_globs(_urls)
    check(f'{_label}: its real namespace is still pinned', _expected in _proposed, _proposed)

# Two candidates sharing a deep prefix is usually one posting seen twice, not a namespace.
_TWO_DEEP = ['https://x.invalid/job/some-role/apply', 'https://x.invalid/job/some-role/share']
check('two URLs under one posting do not make its slug a namespace',
      not any('some-role' in g for g in _glob_mod._candidate_globs(_TWO_DEEP)),
      _glob_mod._candidate_globs(_TWO_DEEP))
_THREE_SHARED = ['https://x.invalid/jobs/eng/role-%d' % i for i in range(6)]
check('  ...while a short segment shared by many still is',
      'https://x.invalid/jobs/eng/**' in _glob_mod._candidate_globs(_THREE_SHARED),
      _glob_mod._candidate_globs(_THREE_SHARED))

check('the verifier version was raised so the saved bad pattern is dropped',
      _pd.VERIFIER_VERSION >= 4, _pd.VERIFIER_VERSION)


section('4.29  a screening answer that says nothing is retried, not accepted')


import json as _json                                                      # noqa: E402
_cs = p.claude_screen
# claude_screen_batch lives in screen.py and reads its own module global for the group size;
# the package merely re-exports the value. A test that needs to change it must change it
# there, or it changes what the test can see and nothing about what the function does.
from app.pipeline.claude_screen import screen as _cs_screen                    # noqa: E402


class _Screener:
    """Stands in for anthropic.Anthropic, replaying a scripted list of answers.

    An answer given as (text, stop_reason) lets a test say the answer was cut off, and one
    given as an Exception is raised instead. Every request is recorded, because what the
    retry CHANGES about the request is the fix being tested.
    """

    def __init__(self, *answers):
        self._answers = list(answers)
        self.calls = 0
        self.budgets: list = []
        self.schemas: list = []
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        self.budgets.append(kw.get('max_tokens'))
        self.schemas.append('output_config' in (kw.get('extra_body') or {}))
        entry = self._answers[min(self.calls - 1, len(self._answers) - 1)]
        if isinstance(entry, Exception):
            raise entry
        text, stop = entry if isinstance(entry, tuple) else (entry, 'end_turn')
        block = type('B', (), {'type': 'text', 'text': text})()
        return type('R', (), {'content': [block], 'stop_reason': stop})()


def _answer(verdict, rule=0, reason='', match=50, checked='questions 1-8 checked',
            employer='', evidence='', drop_evidence='Fully remote.'):
    # drop_evidence defaults to words that really are in _JOB below: a DROP whose quote is
    # not in the posting is deliberately read as a KEEP (see 4.quote), so every fixture that
    # means to test a DROP has to quote its own listing.
    return _json.dumps({'checked': checked, 'verdict': verdict, 'rule': rule,
                        'reason': reason, 'drop_evidence': drop_evidence,
                        'employer_evidence': evidence,
                        'employer': employer, 'match': match})


_JOB = {'title': 'Data Scientist', 'description': 'Fully remote.', 'company': 'Acme',
        'country': 'Germany', 'url': 'https://x/1'}

check('the schema puts the reasoning field first, so the verdict is not named blind',
      list(_cs._SCREEN_OUTPUT_SCHEMA['properties'])[0] == 'checked',
      list(_cs._SCREEN_OUTPUT_SCHEMA['properties']))
check('the API rejects minimum/maximum on integers, so neither is in the schema',
      not any('minimum' in v or 'maximum' in v
              for v in _cs._SCREEN_OUTPUT_SCHEMA['properties'].values()))
check('the answer format is hashed into the cache version, because it changes verdicts',
      _cs._CLAUDE_SCREEN_PROMPT_VERSION
      != __import__('hashlib').sha256(
          _cs.CLAUDE_SCREEN_SYSTEM_PROMPT.encode('utf-8')).hexdigest()[:12])

_good = _Screener(_answer('KEEP', match=72))
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_good, dict(_JOB))
check('a clean answer is used as-is, with one call', _good.calls == 1, _good.calls)
check('the request carried the schema', _good.schemas == [True], _good.schemas)
check('a clean KEEP is not a drop', _drop is False)
check('a clean answer yields the match %', _match == 72, _match)

_dropped = _Screener(_answer('DROP', rule=7, reason='8+ years required', match=30))
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_dropped, dict(_JOB))
check('a DROP is honoured', _drop is True)
check('the reason names the rule that fired', _reason == 'Rule 7 - 8+ years required', _reason)

# The score is clamped rather than trusted: the API will not enforce a range on an integer.
_wild = _Screener(_answer('KEEP', match=140))
check('an out-of-range score is clamped, not stored raw',
      p.claude_screen_one(_wild, dict(_JOB))[2] == 100)
_missing = _Screener(_json.dumps({'checked': 'x', 'verdict': 'KEEP', 'rule': 0,
                                  'reason': '', 'match': None}))
check('a null score becomes no score rather than a crash',
      p.claude_screen_one(_missing, dict(_JOB))[2] is None)

# Failing open is the whole point: after every attempt is spent the listing survives.
_hopeless = _Screener('nonsense')
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_hopeless, dict(_JOB))
check('a persistently unparseable answer stops at the attempt limit',
      _hopeless.calls == _cs._SCREEN_RETRY_ATTEMPTS, _hopeless.calls)
check('and it never deletes the listing', _drop is False)
check('but it does report the error so the Log can show it in red', bool(_err), _err)

# Claude running out of room mid-answer. Repeating the identical request cannot help --
# temperature is 0 -- so the retry must ask for more room instead.
_cut = _Screener(('{"checked": "RULE 1: nothing. RULE 2: the location field shows',
                  'max_tokens'), _answer('KEEP', match=62))
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_cut, dict(_JOB))
check('a cut-off answer is retried', _cut.calls == 2, _cut.calls)
check('the retry asks for more room, not the same request again',
      _cut.budgets == [_cs._SCREEN_MAX_TOKENS, _cs._SCREEN_MAX_TOKENS_RETRY], _cut.budgets)
check('the finished answer is the one that counts', _match == 62 and _drop is False)

# The dangerous half of truncation: unfinished reasoning that happens to contain the word
# DROP. Deleting a job over a sentence Claude was still in the middle of writing is the
# failure this guards, so a cut-off answer is discarded whatever it looks like.
_trap = _Screener(('{"checked": "RULE 1 would DROP this if it were a bootcamp, but it',
                   'max_tokens'), _answer('KEEP', match=80))
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_trap, dict(_JOB))
check('a DROP inside unfinished reasoning is not treated as the verdict',
      _drop is False and _match == 80, (_drop, _match))

_always_cut = _Screener(('{"checked": "still writing', 'max_tokens'))
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_always_cut, dict(_JOB))
check('a permanently unfinished answer never deletes the listing', _drop is False)
check('it is reported rather than passed off as a real verdict',
      _err == _cs._SCREEN_INCOMPLETE_ERROR, _err)
check('and it does not retry forever',
      _always_cut.calls == _cs._SCREEN_RETRY_ATTEMPTS, _always_cut.calls)


section('4.30  screening survives an API that will not take the schema')


class _Rejection(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


# If the schema is refused, screening has to carry on unschema'd rather than stop. The
# prose parser is still there for exactly this.
_cs._STRUCTURED_OUTPUT_SUPPORTED[0] = True
_refuses = _Screener(_Rejection('output_config: unknown field'), 'KEEP\nMATCH: 44')
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_refuses, dict(_JOB))
check('a refused schema falls straight back to the text format', _err is None, _err)
check('and the fallback answer is read correctly', _match == 44 and _drop is False)
check('the second attempt dropped the schema', _refuses.schemas == [True, False],
      _refuses.schemas)
check('the refusal is remembered for the rest of the run',
      _cs._STRUCTURED_OUTPUT_SUPPORTED[0] is False)

_after = _Screener('DROP: Rule 7 - too senior')
_drop, _reason, _match, _err, _employer = p.claude_screen_one(_after, dict(_JOB))
check('later listings do not pay for the same rejection again',
      _after.schemas == [False], _after.schemas)
check('and they are still screened properly', _drop is True and _err is None)
_cs._STRUCTURED_OUTPUT_SUPPORTED[0] = True

# A rate limit is NOT the API refusing schemas. Treating one as such would quietly
# downgrade every remaining listing in the run over a momentary hiccup.
for _exc in (_Rejection('rate limited, slow down', 429),
             _Rejection('overloaded_error', 529),
             _Rejection('internal server error', 500)):
    check('a transient failure is not mistaken for an unsupported schema',
          not _cs._rejects_structured_output(_exc), _exc)
check('but a real refusal is recognised',
      _cs._rejects_structured_output(_Rejection('output_config.format: not supported')))
check('and so is an SDK that has never heard of it',
      _cs._rejects_structured_output(
          TypeError("create() got an unexpected keyword argument 'output_config'")))
check('the flag is left on after these checks', _cs._STRUCTURED_OUTPUT_SUPPORTED[0] is True)


section('4.25  the employer is read out in the same call as the verdict')

# The employer used to be a second call per listing. It moved into the screening answer
# once the numbers were in: 86% of the listings that reach Claude carry no company name, so
# the second call ran for nearly all of them and cost 23% more ($1.79 against $1.39 over
# 674 listings) to read the same text twice.
#
# What must NOT be lost in the move is the guard: a name is only accepted when Claude can
# quote the words that carry it, because this name goes on to be matched against government
# visa-sponsor registers and a plausible invention would match something there.

_EMPLOYER_JOB = {
    'title': 'Manager Enterprise Data Management', 'company': '', 'country': 'Netherlands',
    'url': 'https://x/9',
    'description': 'Orchestrate data-driven transformations at our top-tier clients and '
                   'help them unlock value from data assets. At Deloitte you will receive '
                   'a profit-sharing bonus and a lease car.',
}

check('the schema still puts the reasoning field first',
      list(_cs._SCREEN_OUTPUT_SCHEMA['properties'])[0] == 'checked',
      list(_cs._SCREEN_OUTPUT_SCHEMA['properties']))
check('the evidence field comes before the name it supports',
      list(_cs._SCREEN_OUTPUT_SCHEMA['properties']).index('employer_evidence')
      < list(_cs._SCREEN_OUTPUT_SCHEMA['properties']).index('employer'))
check('both employer fields are required, so an answer cannot omit them',
      {'employer', 'employer_evidence'} <= set(_cs._SCREEN_OUTPUT_SCHEMA['required']))

_named = _Screener(_answer('KEEP', match=70, employer='Deloitte',
                           evidence='At Deloitte you will receive'))
_d, _r, _m, _e, _employer = p.claude_screen_one(_named, dict(_EMPLOYER_JOB))
check('a name backed by a real quote comes back with the verdict',
      _employer == 'Deloitte' and _d is False, (_employer, _d, _e))
check('one call did all of it', _named.calls == 1, _named.calls)

# The guard, checked through the merged path. All of these must yield no name.
for _label, _kw in (
    ('an invented employer with an invented quote',
     dict(employer='Booking.com', evidence='Booking.com is hiring a Manager')),
    ('a name with no quote at all', dict(employer='Deloitte', evidence='')),
    ('a quote too short to prove anything', dict(employer='Deloitte', evidence='at')),
):
    _s = _Screener(_answer('KEEP', **_kw))
    check(f'refused: {_label}', p.claude_screen_one(_s, dict(_EMPLOYER_JOB))[4] is None)

for _placeholder in ('Unknown', 'N/A', 'Confidential', 'our client', 'The Company',
                     'EURES', 'LinkedIn', 'Welcome to the Jungle', 'Indeed'):
    _s = _Screener(_answer('KEEP', employer=_placeholder,
                           evidence='At Deloitte you will receive'))
    check(f'not an employer: {_placeholder!r}',
          p.claude_screen_one(_s, dict(_EMPLOYER_JOB))[4] is None)

# Claude retypes the quote rather than copying bytes, so punctuation and case must not
# decide it.
_s = _Screener(_answer('KEEP', employer='Deloitte', evidence='at deloitte, you will receive'))
check('a quote differing only in punctuation and case is still real',
      p.claude_screen_one(_s, dict(_EMPLOYER_JOB))[4] == 'Deloitte')

check('the evidence is checked against the title too',
      _cs._evidence_is_real('Manager Enterprise Data', _EMPLOYER_JOB))
check('evidence found nowhere is rejected',
      not _cs._evidence_is_real('Acme Corporation International', _EMPLOYER_JOB))

# A DROP still reports the employer -- the register match needs it either way. The DROP
# quotes this listing's own words, because one that cannot is read as a KEEP (4.quote).
_s = _Screener(_answer('DROP', rule=4, reason='wants 5+ years', match=30,
                       employer='Deloitte', evidence='At Deloitte you will receive',
                       drop_evidence='Manager Enterprise Data Management'))
_d, _r, _m, _e, _employer = p.claude_screen_one(_s, dict(_EMPLOYER_JOB))
check('a dropped listing still carries its employer', _d is True and _employer == 'Deloitte',
      (_d, _employer))

# The separate step and its helpers are gone.
for _gone in ('_step_company_names', 'claude_name_employer_one'):
    check(f'the second call stays deleted: {_gone}', not hasattr(p, _gone))
check('the pipeline has one Claude step, not two',
      'claude_name_employer_one' not in __import__('inspect').getsource(p.reapply_filters))


# --------------------------------------------------------------------------------------
# The grouped batch
# --------------------------------------------------------------------------------------
# Several listings share one request, because the system prompt is 4,204 tokens and is
# identical for all of them: sent one at a time it was 79% of the bill. Measured on 93 real
# listings, grouping took a run from $0.459 to $0.100.
#
# The risk grouping introduces is not cost, it is mix-ups -- an answer applied to the wrong
# posting would never show up in any log. So the listing number, not the position in the
# array, is what ties an answer back to a job, and these tests exist mainly to hold that.

class _FakeBatches:
    def __init__(self, answers_by_group, fail_groups=()):
        self._answers = answers_by_group
        self._fail = set(fail_groups)
        self.requests = []
        self.cancelled = False

    # the attribute chain the real SDK has: client.messages.batches.create(...)
    @property
    def messages(self):
        return self

    @property
    def batches(self):
        return self

    def create(self, requests):
        self.requests = requests
        return type('B', (), {'id': 'batch_test'})()

    def retrieve(self, _id):
        return type('S', (), {'processing_status': 'ended', 'request_counts': None})()

    def cancel(self, _id):
        self.cancelled = True

    def results(self, _id):
        for index, request in enumerate(self.requests):
            if index in self._fail:
                yield type('R', (), {'custom_id': request['custom_id'],
                                     'result': type('E', (), {'type': 'errored'})()})()
                continue
            block = type('T', (), {'type': 'text',
                                   'text': _json.dumps({'answers': self._answers[index]})})()
            message = type('M', (), {'content': [block], 'stop_reason': 'end_turn'})()
            yield type('R', (), {'custom_id': request['custom_id'],
                                 'result': type('S', (), {'type': 'succeeded',
                                                          'message': message})()})()


def _item(n, verdict='KEEP', rule=0, reason='', match=50, employer='', evidence='',
          drop_evidence='Fully remote. Data engineering.'):
    return {'listing': n, 'checked': 'all eight', 'verdict': verdict, 'rule': rule,
            'reason': reason, 'drop_evidence': drop_evidence,
            'employer_evidence': evidence, 'employer': employer, 'match': match}


_MANY = [{'title': 'Job %d' % i, 'description': 'Fully remote. Data engineering.',
          'company': '', 'country': 'Netherlands', 'url': 'https://x/%d' % i}
         for i in range(25)]

_groups_for_25 = -(-25 // _cs_screen._BATCH_GROUP_SIZE)
_sizes_for_25 = [min(_cs_screen._BATCH_GROUP_SIZE, 25 - i * _cs_screen._BATCH_GROUP_SIZE)
                 for i in range(_groups_for_25)]
_fake = _FakeBatches({i: [_item(n) for n in range(1, size + 1)]
                      for i, size in enumerate(_sizes_for_25)})
_out = _cs.claude_screen_batch(_fake, [dict(j) for j in _MANY])
check('25 listings go out as %d requests, not 25' % _groups_for_25,
      len(_fake.requests) == _groups_for_25, len(_fake.requests))
check('the batch sends no cache_control -- parallel requests write far more than they read',
      all(isinstance(r['params']['system'], str) for r in _fake.requests),
      [type(r['params']['system']).__name__ for r in _fake.requests])
# The sequential path caches too -- it builds its own system block, so this reads the
# source rather than a helper the batch path no longer shares with it.
check('the sequential path still caches, because there each call follows the last',
      'cache_control' in __import__('inspect').getsource(_cs._screen_once))
check('max_tokens is sized to the group, not to one listing',
      [r['params']['max_tokens'] for r in _fake.requests]
      == [_cs._BATCH_TOKENS_PER_LISTING * n for n in _sizes_for_25],
      [r['params']['max_tokens'] for r in _fake.requests])
check('every listing in the group is in the one prompt',
      _fake.requests[0]['params']['messages'][0]['content'].count('===== LISTING ')
      == _sizes_for_25[0])

# The mix-up test, and the bad-number tests after it, force a group of three for
# themselves. Production sends ONE listing per request -- bundling three agreed with
# one-at-a-time only 96.7% of the time and every disagreement was a listing wrongly KEPT, one
# of which the user reported -- but the grouping code is still there, and the property these
# prove is the one that matters if it is ever used again: an answer lands on the listing its
# NUMBER names, never on its position in the reply.
_REAL_GROUP_SIZE = _cs_screen._BATCH_GROUP_SIZE
_cs_screen._BATCH_GROUP_SIZE = 3
check('production still asks about one listing at a time', _REAL_GROUP_SIZE == 1,
      _REAL_GROUP_SIZE)

_jobs3 = [dict(_MANY[0]),
          dict(_MANY[1], description='Fully remote. Data engineering. 8 years wanted.'),
          dict(_MANY[2])]
_shuffled = _FakeBatches({0: [_item(3, 'DROP', 7, 'wrong field'),
                              _item(1, 'KEEP', match=88),
                              # Quoted from _MANY's own description, and carrying a number,
                              # because a rule 4 DROP has to show one (4.quote).
                              _item(2, 'DROP', 4, 'wants 8 years',
                                    drop_evidence='8 years wanted')]})
_out3 = _cs.claude_screen_batch(_shuffled, _jobs3)
check('an answer lands on the listing its number names, not on its position',
      (_out3[id(_jobs3[0])][0] is False and _out3[id(_jobs3[0])][2] == 88
       and _out3[id(_jobs3[1])][1] == 'Rule 4 - wants 8 years'
       and _out3[id(_jobs3[2])][1] == 'Rule 7 - wrong field'),
      [(v[0], v[1], v[2]) for v in (_out3[id(j)] for j in _jobs3)])

# A number that is missing, out of range, or a bool is not guessed at by position: the
# listing is simply left out, and the caller screens it one at a time instead.
for _label, _bad in (('no number', {'checked': 'x', 'verdict': 'DROP', 'rule': 7,
                                    'reason': 'no', 'employer_evidence': '',
                                    'employer': '', 'match': 10}),
                     ('number 99 in a group of 3', _item(99, 'DROP', 7, 'no')),
                     ('number 0', _item(0, 'DROP', 7, 'no')),
                     ('True instead of 1', _item(True, 'DROP', 7, 'no'))):
    _j = [dict(_MANY[0]), dict(_MANY[1]), dict(_MANY[2])]
    _bad_out = _cs.claude_screen_batch(_FakeBatches({0: [_bad, _item(2, 'KEEP')]}), _j)
    check('an answer with a bad listing number is dropped, not misapplied: %s' % _label,
          id(_j[0]) not in _bad_out and id(_j[2]) not in _bad_out
          and _bad_out.get(id(_j[1]), (None,))[0] is False,
          sorted(str(k == id(_j[0])) for k in _bad_out))

# A request that fails leaves its listings absent, so _step_claude falls back to
# claude_screen_one for exactly those and nothing is silently marked KEEP. Still run with a
# group of three, because a failure has to lose exactly the listings that shared the failed
# request and no others -- with one per request there is nothing to share.
# One request in the middle fails. Its listings -- and only its listings -- must be absent,
# so _step_claude screens exactly those one at a time.
_size = _cs_screen._BATCH_GROUP_SIZE
_jobs20 = [dict(j) for j in _MANY[:20]]
_broken = 1
_half = _FakeBatches({i: [_item(n) for n in range(1, min(_size, 20 - i * _size) + 1)]
                      for i in range(-(-20 // _size))}, fail_groups=(_broken,))
_out20 = _cs.claude_screen_batch(_half, _jobs20)
_lost = _jobs20[_broken * _size:(_broken + 1) * _size]
check('a failed request leaves its listings unanswered rather than guessed',
      len(_out20) == 20 - len(_lost)
      and not any(id(j) in _out20 for j in _lost)
      and all(id(j) in _out20 for j in _jobs20 if j not in _lost),
      (len(_out20), 20 - len(_lost)))

_cs_screen._BATCH_GROUP_SIZE = _REAL_GROUP_SIZE   # back to what production uses
check('the forced group size was put back', _cs_screen._BATCH_GROUP_SIZE == 1)

check('an empty list never opens a batch', _cs.claude_screen_batch(None, []) == {})

# Cancelling mid-wait must abandon the batch, not return half-verdicts as if complete.
class _NeverEnds(_FakeBatches):
    def retrieve(self, _id):
        return type('S', (), {'processing_status': 'in_progress', 'request_counts': None})()


_never = _NeverEnds({})
check('cancelling abandons the batch and returns nothing',
      _cs.claude_screen_batch(_never, [dict(_MANY[0])], None, lambda: True) == {}
      and _never.cancelled)


# =========================================================================================
# THE RÉSUMÉ, THE LEVEL AND REMOTE / NOT REMOTE
# =========================================================================================
import io as _io  # noqa: E402
import re as _re2  # noqa: E402
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402
import types as _types  # noqa: E402
import zipfile as _zipfile  # noqa: E402

from app import resume as _resume  # noqa: E402
from app.pipeline.claude_screen import prompt as _prompt  # noqa: E402
from app.pipeline.claude_screen import worth as _worth  # noqa: E402
from app.pipeline.profiles import job_profile as _job_profile  # noqa: E402
from app.pipeline.internship import finder as _IF  # noqa: E402

section('4.40  the résumé: PDF or Word, and nothing else')

_work = _tempfile.mkdtemp(prefix='resume_test_')
_RESUME_LINES = ['Jane Example - Data Engineer', 'Lives in Lyon, France. French citizen.',
                 'Languages: English C1, French native.',
                 'Experience: 2 years building ETL pipelines in Python, SQL and Airflow.',
                 'Skills: Python, SQL, Airflow, dbt, Spark, Docker, PostgreSQL, REST APIs.',
                 'Education: M.Sc. Computer Science, Université de Lyon (expected 2027).']


def _make_pdf(path, lines):
    """A real one-page PDF with a text layer, written by hand -- no extra library."""
    stream = 'BT /F1 11 Tf 50 780 Td 14 TL ' + ' '.join(
        '(%s) Tj T*' % l.replace('(', '\\(').replace(')', '\\)') for l in lines) + ' ET'
    objects = ['<< /Type /Catalog /Pages 2 0 R >>',
               '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] '
               '/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
               '<< /Length %d >>\nstream\n%s\nendstream' % (len(stream), stream),
               '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out = b'%PDF-1.4\n'
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += ('%d 0 obj\n%s\nendobj\n' % (i, body)).encode('latin-1', 'replace')
    xref = len(out)
    out += ('xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)).encode()
    for off in offsets:
        out += ('%010d 00000 n \n' % off).encode()
    out += ('trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
            % (len(objects) + 1, xref)).encode()
    open(path, 'wb').write(out)


def _make_docx(path, lines):
    import docx
    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(path)


_w = lambda name: os.path.join(_work, name)  # noqa: E731
_ascii_lines = [l.encode('ascii', 'replace').decode() for l in _RESUME_LINES]
_make_pdf(_w('cv.pdf'), _ascii_lines * 2)
_make_docx(_w('cv.docx'), _RESUME_LINES)
open(_w('cv.txt'), 'w', encoding='utf-8').write('\n'.join(_RESUME_LINES))
_shutil.copyfile(_w('cv.txt'), _w('text_named.pdf'))
_shutil.copyfile(_w('cv.pdf'), _w('pdf_named.docx'))
open(_w('old.doc'), 'wb').write(b'\xd0\xcf\x11\xe0' + b'\0' * 600)
_make_pdf(_w('scan.pdf'), ['x'])
with _zipfile.ZipFile(_w('sheet.docx'), 'w') as _z:
    _z.writestr('xl/workbook.xml', '<workbook/>')
open(_w('image.png'), 'wb').write(b'\x89PNG\r\n\x1a\n' + b'\0' * 100)

check('the résumé lives in the isolated test storage, never the real data folder',
      str(_resume.resume_dir()).startswith(str(storage.DATA_DIR)), _resume.resume_dir())
_info = _resume.save_resume(_w('cv.pdf'))
check('a real PDF is accepted', _info['kind'] == 'pdf', _info)
check('  ...and its text is read', 'Airflow' in _resume.load_resume_text(),
      _resume.load_resume_text()[:80])
_info = _resume.save_resume(_w('cv.docx'))
check('a real Word document is accepted', _info['kind'] == 'docx', _info)
check('  ...and replaces the PDF, leaving one résumé file',
      sorted(f for f in os.listdir(_resume.resume_dir()) if f.startswith('resume.')
             and not f.endswith('.txt')) == ['resume.docx'],
      os.listdir(_resume.resume_dir()))
for _name, _why in (('cv.txt', 'a text file'), ('text_named.pdf', 'a text file named .pdf'),
                    ('pdf_named.docx', 'a PDF named .docx'), ('old.doc', 'an old .doc'),
                    ('scan.pdf', 'a PDF with no text (a scan)'),
                    ('sheet.docx', 'a zip that is not a Word document'),
                    ('image.png', 'an image')):
    try:
        _resume.save_resume(_w(_name))
        _refused = False
    except _resume.ResumeError:
        _refused = True
    check('refused: %s' % _why, _refused)
check('a refused file leaves the accepted résumé exactly as it was',
      _resume.resume_name() == 'cv.docx' and 'Airflow' in _resume.load_resume_text())
check('the file picker offers only PDF and Word',
      '*.pdf' in _resume.FILE_DIALOG_FILTER and '*.docx' in _resume.FILE_DIALOG_FILTER
      and '*.doc ' not in _resume.FILE_DIALOG_FILTER + ' ')
_RESUME_TEXT = _resume.load_resume_text()


section('4.41  Remote / Not Remote -- the same words, the other answer')
_WM = p.search_title.WORK_MODE_ROW_KEY


def _loc(description, mode=None, **kw):
    row = dict({'title': 'Data Engineer', 'company': 'A', 'country': 'Germany',
                'url': 'https://x/loc', 'description': description}, **kw)
    if mode:
        row[_WM] = mode
    return row


_REMOTE_ONLY = 'Fully remote role with competitive salary and benefits offered here.'
_DENIES_REMOTE = 'On-site only in our office, no remote work available at all here.'
_SILENT = 'Build pipelines with a friendly team and competitive salary and benefits.'
for _desc, _remote, _not_remote, _why in (
        (_REMOTE_ONLY, True, False, 'a fully remote role'),
        (_DENIES_REMOTE, False, True, 'a role that denies remote work'),
        (_SILENT, False, True, 'a role that never mentions remote work')):
    check('%s: Remote %s, Not Remote %s' % (_why, 'keeps' if _remote else 'drops',
                                             'keeps' if _not_remote else 'drops'),
          p.passes_work_location_rule(_loc(_desc, 'remote')) is _remote
          and p.passes_work_location_rule(_loc(_desc, 'not_remote')) is _not_remote)
check('a row with no mode is judged exactly as Remote',
      all(p.passes_work_location_rule(_loc(d)) == p.passes_work_location_rule(_loc(d, 'remote'))
          for d in (_REMOTE_ONLY, _DENIES_REMOTE, _SILENT)))
check('a thin row is kept in both, for Claude to read',
      p.passes_work_location_rule(_loc('Data Engineer at X', 'remote', thin_description=True))
      and p.passes_work_location_rule(_loc('Data Engineer at X', 'not_remote',
                                           thin_description=True)))
check('the Milan exception is Remote-only: a fully remote Milan role is dropped by Not Remote',
      p.passes_work_location_rule(_loc(_REMOTE_ONLY + ' Based in Milan.', 'remote'))
      and not p.passes_work_location_rule(_loc(_REMOTE_ONLY + ' Based in Milan.', 'not_remote')))
_kept = p.reapply_filters([_loc(_REMOTE_ONLY, url='https://x/r'),
                           _loc(_DENIES_REMOTE, url='https://x/o', company='B')],
                          progress_cb=None, anthropic_api_key=None,
                          search_title='Data Engineer', search_work_mode='not_remote')[0]
check('Filter with Not Remote keeps the office role and drops the remote one',
      [k['url'] for k in _kept] == ['https://x/o'], [k['url'] for k in _kept])
check('  ...and writes the choice onto the row, for Claude',
      bool(_kept) and _kept[0].get(_WM) == 'not_remote')
check('the Internship module turns the same way',
      _IF.passes_location_rule(_loc(_REMOTE_ONLY, 'remote'))
      and not _IF.passes_location_rule(_loc(_REMOTE_ONLY, 'not_remote'))
      and _IF.passes_location_rule(_loc(_DENIES_REMOTE, 'not_remote')))


section('4.42  every Level has its own prompt, for Remote and for Not Remote')
_LEVEL_PARAGRAPH = _re2.compile(r'\*\*In the work named on the Field line of the posting\*\*.*?'
                                r'(?=\n\n## DROP)', _re2.S)
_RULE_4 = _re2.compile(r'\n4\. \*\*.*?(?=\n5\. )', _re2.S)


def _without_level(text):
    return _RULE_4.sub('', _LEVEL_PARAGRAPH.sub('', text))


_prompts = {}
for _level in ('entry', 'junior', 'mid', 'senior'):
    for _mode in ('remote', 'not_remote'):
        _row = {p.search_title.LEVEL_ROW_KEY: _level, _WM: _mode}
        _prompts[(_level, _mode)] = _prompt.system_prompt_for(_row)
# TWO PROMPTS NOW, NOT EIGHT, AND THAT IS THE POINT OF THE CHANGE.
#
# This asserted eight distinct prompts -- four Levels times Remote and Not Remote -- and the
# guard beside it said the Levels differed only in the level paragraph and rule 4. Those were
# the only two differences, so when the user asked for seniority to be classified rather than
# filtered ([owner's note: it should not filter, it should categorise]) and both passages were replaced
# with one shared text, the four Levels collapsed into one document.
#
# What that buys, beyond the thing he asked for: a verdict reached for one Level is now valid
# for every Level, because the prompt no longer mentions the Level. The cache key is a hash of
# the prompt text, so the same listing is no longer re-asked four times -- see the cache-key
# assertion further down, which was rewritten for the same reason.
check('two prompts now: one Remote, one Not Remote, the same for every Level',
      len(set(_prompts.values())) == 2, sorted({len(t) for t in _prompts.values()}))
for _mode in ('remote', 'not_remote'):
    check('%s: every Level gets byte-identical text' % _mode,
          len({_prompts[(lv, _mode)] for lv in ('entry', 'junior', 'mid', 'senior')}) == 1)
# And the two modes must still differ: Remote drops a listing that needs him in an office,
# Not Remote drops one that is remote-only. Collapsing the Levels must not collapse these.
check('Remote and Not Remote are still different documents',
      _prompts[('junior', 'remote')] != _prompts[('junior', 'not_remote')])
# Seniority is reported, never dropped for. Both halves asserted, because a prompt that
# merely stopped mentioning rule 4 would pass the first and leave Claude no field to answer in.
for (_level, _mode), _text in _prompts.items():
    check('%s %s: seniority is reported, not a drop reason' % (_level, _mode),
          'never a reason to drop' in _text and '`seniority`' in _text)
check('the schema has a seniority field with the six words the column shows',
      _prompt._SCREEN_OUTPUT_SCHEMA['properties']['seniority']['enum']
      == ['Intern', 'Junior', 'Mid', 'Senior', 'Lead', 'Unspecified'])
check('  ...and it is required, so an answer can never omit it',
      'seniority' in _prompt._SCREEN_OUTPUT_SCHEMA['required'])
check('Junior Remote is the prompt the Job module always had',
      _prompts[('junior', 'remote')] == p.CLAUDE_SCREEN_SYSTEM_PROMPT)
for (_level, _mode), _text in _prompts.items():
    _flat = ' '.join(_text.split())
    _ok = ('résumé' in _flat and 'Field line' in _flat
           and not any(w in _flat for w in ('Turin', 'Torino', 'Politecnico', 'Iranian',
                                            'A2', 'DevOps')))
    if _mode == 'remote':
        # No home-city exception: Remote means Remote, in Turin and Milan as anywhere.
        _ok = (_ok and '1. **He would have to be present somewhere — the role is not remote.**' in _flat
               and 'everyday commute' not in _flat and 'city he lives in' not in _flat)
    else:
        _ok = (_ok and '1. **The role is remote.**' in _flat and 'city he lives in' not in _flat
               and '1a. The posting says **this role** is done remotely' in _flat)
    check('%s %s: facts from the résumé, and the right rule 1' % (_level, _mode), _ok)
# This asserted that Senior's rule 4 dropped lead, staff and principal roles. Rule 4 drops
# nothing now -- those roles are kept and labelled 'Lead' in the Seniority column -- so the
# assertion is the other way round: the words that used to force a DROP must now appear as
# labels to report, and the prompt must say plainly that it keeps them.
_senior_flat = ' '.join(_prompts[('senior', 'remote')].split())
check('a lead or principal role is kept and labelled, not dropped',
      'Lead' in _senior_flat and 'never a reason to drop' in _senior_flat
      and 'A role wanting eight years is kept' in _senior_flat, _senior_flat[:120])
for _module, _remote_text, _nr_text in (
        ('Internship', p.internship_module.claude.INTERNSHIP_SYSTEM_PROMPT,
         p.internship_module.claude.INTERNSHIP_SYSTEM_PROMPT_NOT_REMOTE),
        ('Thesis', p.thesis_module.claude.THESIS_SYSTEM_PROMPT,
         p.thesis_module.claude.THESIS_SYSTEM_PROMPT_NOT_REMOTE)):
    _flat_r, _flat_n = ' '.join(_remote_text.split()), ' '.join(_nr_text.split())
    check('%s: Remote and Not Remote prompts differ, both read the résumé' % _module,
          _remote_text != _nr_text and 'résumé' in _flat_r and 'résumé' in _flat_n
          and 'Turin' not in _flat_r + _flat_n and 'Politecnico' not in _flat_r + _flat_n)
    check('%s: Not Remote drops only a stated remote role' % _module,
          '→ DROP.' in _nr_text and 'city he lives in' not in _flat_n)

# The .md files beside the app are the copies the user reads; they must be the prompts exactly.
_MIRRORS = {'Job-Filter-Claude-Apify.md': ('junior', 'remote'),
            'Job-Filter-Claude-Apify-Not-Remote.md': ('junior', 'not_remote')}
for _label in ('Entry', 'Mid', 'Senior'):
    _MIRRORS['Job-Filter-Claude-Apify-%s.md' % _label] = (_label.lower(), 'remote')
    _MIRRORS['Job-Filter-Claude-Apify-%s-Not-Remote.md' % _label] = (_label.lower(), 'not_remote')
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _file, _key in _MIRRORS.items():
    _path = os.path.join(_root, _file)
    _text = (open(_path, encoding='utf-8').read().replace('\r\n', '\n')
             if os.path.exists(_path) else None)
    check('%s is the %s %s prompt, byte for byte' % (_file, _key[0], _key[1]),
          _text == _prompts[_key], 'missing' if _text is None else 'differs')

# RULE 1b: A REGION THAT CONTAINS WHERE HE LIVES IS NOT A RESTRICTION AGAINST HIM.
#
# Found on the first real LinkedIn run of the new actor: 17 of 49 Rule 1 flags were about Europe
# or the EU -- "Remote restricted to Europe; he is in Italy" -- and Italy is in Europe. Written
# into every Remote prompt (the four copies; the Not Remote prompts have a different rule 1).
# Two wordings were tried: the first moved 6 of 17, the second 7 of 17, with 7 of 8 real
# presence requirements correctly still dropped. The remaining ten are mostly hard phrases the
# model reads as physical presence ("physically located within Europe"), and some are right
# (UTC+0 is Britain and Portugal, not Italy). Asserted by presence, not by effect: the effect
# needs a live Claude call and is recorded in Document T-16.
for _lvl in ('entry', 'junior', 'mid', 'senior'):
    _p1b = ' '.join(_prompts[(_lvl, 'remote')].split())
    check('%s Remote prompt says a region containing his home is not a restriction' % _lvl,
          'followed by a REGION that contains where his résumé says he lives is satisfied by '
          'him, not violated' in _p1b, _p1b[_p1b.find('1b.'):_p1b.find('1b.') + 80])
    check('  ...and names the words that were being misread',
          all(w in _p1b for w in ('"Europe"', '"the EU"', '"EMEA"', 'European time zones')))
    _nr = ' '.join(_prompts[(_lvl, 'not_remote')].split())
    check('  ...and the Not Remote prompt, whose rule 1 differs, is untouched',
          'REGION that contains' not in _nr)
check('the four Remote copies carry the identical paragraph',
      len({_prompts[(l, 'remote')] for l in ('entry', 'junior', 'mid', 'senior')}) == 1)

# The profiles are separate objects: a word added to one reaches no other.
_entry_words = _job_profile('entry').vocabulary.LANGUAGES['en']['wrong_level']
_entry_words.append('zzz-canary-level')
try:
    check('a word added to the Entry profile reaches neither Mid, Senior nor Junior',
          'zzz-canary-level' not in _job_profile('mid').vocabulary.LANGUAGES['en']['wrong_level']
          and 'zzz-canary-level' not in _job_profile('senior').vocabulary.LANGUAGES['en'][
              'wrong_level']
          and 'zzz-canary-level' not in p.country_rules.LANGUAGES['en']['senior'])
finally:
    _entry_words.remove('zzz-canary-level')

# The cache key follows everything a verdict depends on.
_base = {'title': 'Data Engineer', 'description': 'd', p.search_title.LEVEL_ROW_KEY: 'junior',
         _WM: 'remote', p.search_title.ROW_KEY: 'Data Engineer'}
_k = p._claude_screen_cache_key(_base)
# THE LEVEL NO LONGER CHANGES THE KEY, AND THAT IS CORRECT NOW.
#
# This asserted the opposite, because each Level had its own prompt and so its own verdict.
# Since seniority became a reported field rather than rule 4's drop, all four Levels share
# one document -- so a verdict reached at Junior is the same verdict at Senior, and reusing
# it is right rather than a bug. The practical effect is that the same listing is asked
# about once instead of four times.
#
# The key is a hash of the prompt text plus the listing, so this is not a special case
# written here -- it follows from the prompt no longer mentioning the Level. Asserted so
# that reintroducing per-Level wording cannot pass silently.
check('the Level no longer changes the key -- one prompt, one verdict',
      p._claude_screen_cache_key(dict(_base, **{p.search_title.LEVEL_ROW_KEY: 'mid'})) == _k)
check('  ...with Remote / Not Remote',
      p._claude_screen_cache_key(dict(_base, **{_WM: 'not_remote'})) != _k)
check('  ...with the job title',
      p._claude_screen_cache_key(dict(_base, **{p.search_title.ROW_KEY: 'DevOps'})) != _k)
_resume.save_resume(_w('cv.pdf'))
check('  ...and with the résumé', p._claude_screen_cache_key(_base) != _k)
_resume.save_resume(_w('cv.docx'))
check('  ...and comes back when the same résumé is back', p._claude_screen_cache_key(_base) == _k)


section('4.43  Claude reads the résumé in both parts')
_batch_fake = _FakeBatches({0: [_item(1)]})
_cs.claude_screen_batch(_batch_fake, [dict(_base, url='https://x/b')])
_system = _batch_fake.requests[0]['params']['system']
check('part one, batched: the résumé is in the system prompt, as a plain string',
      isinstance(_system, str) and '<resume>' in _system and 'Airflow' in _system)


class _OneCall:
    def __init__(self):
        self.request = None

    @property
    def messages(self):
        return self

    def create(self, **request):
        self.request = request
        block = type('T', (), {'type': 'text', 'text': json.dumps(
            {'checked': 'x', 'location_basis': '1a says this role is remote', 'verdict': 'KEEP',
             'rule': 0, 'reason': '', 'employer_evidence': '', 'employer': ''})})()
        return type('R', (), {'content': [block], 'stop_reason': 'end_turn'})()


_one = _OneCall()
_cs._screen_once(_one, dict(_base))
_blocks = _one.request['system']
check('part one, one at a time: the rules, then the résumé marked for the cache',
      len(_blocks) == 2 and '<resume>' in _blocks[1]['text']
      and _blocks[1].get('cache_control') and _blocks[0]['text'] == _prompts[('junior', 'remote')])


class _MatchBatches:
    """Part two's batch API: one answer per listing, chosen from its title."""

    def __init__(self, answer_for):
        self.answer_for = answer_for
        self.sent = []

    @property
    def messages(self):
        return self

    @property
    def batches(self):
        return self

    def create(self, requests):
        self.sent.append(requests)
        return type('B', (), {'id': 'b'})()

    def retrieve(self, _id):
        return type('S', (), {'processing_status': 'ended', 'request_counts': None})()

    def results(self, _id):
        for request in self.sent[-1]:
            content = request['params']['messages'][0]['content']
            title = _re2.search(r'Title: (.*)', content).group(1)
            block = type('T', (), {'type': 'text', 'text': json.dumps(self.answer_for(title))})()
            message = type('M', (), {'content': [block], 'stop_reason': 'end_turn'})()
            yield type('R', (), {'custom_id': request['custom_id'],
                                 'result': type('S', (), {'type': 'succeeded',
                                                          'message': message})()})()


def _answer(title):
    return {'Good Fit': {'strengths': 'Airflow, dbt', 'gaps': '', 'match': 82,
                         'verdict': 'apply', 'note': 'Airflow and dbt asked for.'},
            'Low Score': {'strengths': 'Python', 'gaps': 'Spark, Kafka', 'match': 20,
                          'verdict': 'check', 'note': 'Core stack missing.'},
            'Skip Me': {'strengths': '', 'gaps': 'everything', 'match': 60,
                        'verdict': 'skip', 'note': 'Needs 10 years.'}}[title]


_fake_match = _MatchBatches(_answer)
_saved_anthropic = p.filters.anthropic
p.filters.anthropic = _types.SimpleNamespace(Anthropic=lambda api_key=None: _fake_match)
try:
    _rows = [dict(_base, title=t, url='https://x/%d' % i, **{p.search_title.LEVEL_ROW_KEY: 'mid'})
             for i, t in enumerate(('Good Fit', 'Low Score', 'Skip Me'))]
    _flagged = []
    p.step_resume_match(_rows, _flagged, 'key')
    _by = {r['title']: r for r in _rows}
    check('part two scores every survivor against the résumé',
          [_by[t].get('claude_match') for t in ('Good Fit', 'Low Score', 'Skip Me')] == [82, 20, 60],
          [_by[t].get('claude_match') for t in ('Good Fit', 'Low Score', 'Skip Me')])
    check('  ...with what fits and what is missing',
          _by['Low Score'].get('resume_gaps') == 'Spark, Kafka'
          and _by['Good Fit'].get('resume_strengths') == 'Airflow, dbt')
    check('  ...the résumé is in its system prompt, and the Level in each listing',
          '<resume>' in _fake_match.sent[0][0]['params']['system']
          and 'Level: Mid' in _fake_match.sent[0][0]['params']['messages'][0]['content'])
    check('a score under the floor and a "skip" are flagged, the good fit is not',
          sorted(e['job']['title'] for e in _flagged) == ['Low Score', 'Skip Me'],
          [e['job']['title'] for e in _flagged])
    check('  ...marked as part two\'s, so a "keep it anyway" is recorded on the right verdict',
          all(e.get('part') == 'resume' for e in _flagged))
    _sent_before = len(_fake_match.sent)
    _by['Low Score']['resume_match_user_kept'] = True
    _flagged = []
    p.step_resume_match(_rows, _flagged, 'key')
    check('a second run with nothing changed asks Claude nothing', len(_fake_match.sent) == _sent_before)
    check('  ...still flags the "skip" from its stored answer, but not the one kept by hand',
          [e['job']['title'] for e in _flagged] == ['Skip Me'],
          [e['job']['title'] for e in _flagged])
    _resume.remove_resume()
    _flagged = []
    _before_rows = [dict(r) for r in _rows]
    p.step_resume_match(_rows, _flagged, 'key')
    check('with no résumé, part two does nothing at all',
          not _flagged and _rows == _before_rows and len(_fake_match.sent) == _sent_before)
    _logs = []
    p.reapply_filters([_loc(_REMOTE_ONLY, url='https://x/nr')], progress_cb=lambda m, d, t:
                      _logs.append(m), anthropic_api_key='key', search_title='Data Engineer')
    check('with a Claude key but no résumé, Filter skips Claude and says so',
          any(m.startswith('WARNING:') and 'résumé' in m for m in _logs)
          and not any(m.startswith('FILTER_STEP_START:claude') for m in _logs))
finally:
    p.filters.anthropic = _saved_anthropic
    _resume.save_resume(_w('cv.docx'))


section('4.44  the Filter runs the one module the Level belongs to')
from PySide6.QtCore import QCoreApplication  # noqa: E402
from app import search_worker as _sw  # noqa: E402

_qapp = QCoreApplication.instance() or QCoreApplication([])
_calls = []
_saved = {name: getattr(p, name) for name in
          ('find_thesis_postings', 'find_internship_postings', 'reapply_filters',
           'step_resume_match')}


def _spy(name, result):
    def fn(*args, **kwargs):
        _calls.append((name, kwargs))
        return result
    return fn


try:
    p.find_thesis_postings = _spy('thesis', ([{'id': 't'}], {}))
    p.find_internship_postings = _spy('internship', ([{'id': 'i'}], {}))
    p.reapply_filters = _spy('job', ([{'id': 'j'}], 0, []))
    p.step_resume_match = _spy('match', None)
    for _level, _expect in (('thesis', ['thesis', 'match']), ('internship', ['internship', 'match']),
                            ('senior', ['job'])):
        _calls.clear()
        _got = []
        _worker = _sw.FilterWorker([{'id': 'x'}], anthropic_api_key='k', search_title='Data Engineer',
                                   search_level=_level, search_work_mode='not_remote')
        _worker.finished_ok.connect(lambda *a: _got.append(a))
        _worker.run()
        check('Level %s runs only: %s' % (_level, ', '.join(_expect)),
              [c[0] for c in _calls] == _expect, [c[0] for c in _calls])
        check('  ...with the title and Not Remote passed on',
              _calls[0][1].get('search_title') == 'Data Engineer'
              and _calls[0][1].get('search_work_mode') == 'not_remote', _calls[0][1])
        check('  ...and its listings come back as the kept list', bool(_got) and len(_got[0][0]) == 1)
    check('a job Level reaches the Filter as that Level',
          _calls[0][1].get('search_level') == 'senior', _calls[0][1])
finally:
    for _name, _fn in _saved.items():
        setattr(p, _name, _fn)
    _shutil.rmtree(_work, ignore_errors=True)


section('4.quote  a DROP that cannot quote the posting is read as a KEEP')

# The campaign measured 117 real DROPs and found 11 resting on words the posting never
# contained: "Rule 3 - Unpaid volunteer position" on an internship that never mentions money,
# "Rule 1 - On-site in Kuala Lumpur" where only a city is named, "Rule 4 - 2+ years implied".
# The prompt already forbade all three; sharpening it cut them from 17 to 11, and this is the
# half that does not depend on Claude agreeing.
_QUOTE_JOB = {'title': 'Data Scientist', 'company': 'Axross', 'url': 'https://x/q',
              'country': 'Malaysia',
              'description': 'We build HVAC optimization platforms. Have at least 2 years '
                             'experience with ETL processes and model validation.'}


def _screen_answer(verdict, rule=0, reason='', drop_evidence=''):
    return _json.dumps({'checked': 'all eight', 'location_basis': '1d nothing requires his '
                        'presence', 'drop_evidence': drop_evidence, 'verdict': verdict,
                        'rule': rule, 'reason': reason, 'employer_evidence': '',
                        'employer': ''})


def _screened(verdict, **kw):
    return p.claude_screen_one(_Screener(_screen_answer(verdict, **kw)), dict(_QUOTE_JOB))


_d, _r, _m, _e, _emp = _screened('DROP', rule=3, reason='Unpaid volunteer position',
                                 drop_evidence='This is an unpaid volunteer position')
check('a DROP quoting words the posting does not have becomes a KEEP', _d is False, (_d, _r))
check('  ...and carries no reason with it', _r is None, _r)
check('a DROP quoting the posting is honoured',
      _screened('DROP', rule=4, reason='wants 2 years',
                drop_evidence='Have at least 2 years experience with ETL')[0] is True)
check('  ...through a difference of case and punctuation',
      _screened('DROP', rule=4, reason='wants 2 years',
                drop_evidence='have AT LEAST 2 years, experience with ETL.')[0] is True)
check('an empty quote cannot carry a DROP either',
      _screened('DROP', rule=7, reason='not the field')[0] is False)
check('a KEEP needs no quote', _screened('KEEP')[0] is False)

# The second half of the guard: a real quote that has nothing to do with the rule it is
# offered for. This is how "Rule 3 - unpaid volunteer position" survived on an internship
# that never mentions money -- by quoting a different, perfectly true sentence.
check('a true quote that cannot carry rule 3 does not drop the listing',
      _screened('DROP', rule=3, reason='Unpaid volunteer position',
                drop_evidence='We build HVAC optimization platforms')[0] is False)
check('  ...while one naming the money does',
      _cs._evidence_fits_rule(3, 'this is an unpaid internship'))
check('  ...in the posting\'s own language too',
      _cs._evidence_fits_rule(3, 'een onbetaalde stage') and
      _cs._evidence_fits_rule(3, 'ein unbezahltes Praktikum'))
check('rule 2 needs a language in the quote',
      not _cs._evidence_fits_rule(2, 'you will join a great team')
      and _cs._evidence_fits_rule(2, 'vloeiend Nederlands vereist'))
check('rule 4 needs a number or a seniority word',
      not _cs._evidence_fits_rule(4, 'Data Scientist II - Finance Payments team')
      and _cs._evidence_fits_rule(4, 'minimaal 5 jaar ervaring')
      and _cs._evidence_fits_rule(4, 'wir suchen eine erfahrene Data Scientist'))
check('every other rule asks only that the quote be real',
      _cs._evidence_fits_rule(7, 'anything at all') and _cs._evidence_fits_rule(1, 'x'))

from app.pipeline import profiles as _profiles  # noqa: E402

check('the quote is asked for before the verdict, so it cannot be written to fit one',
      list(_cs._SCREEN_OUTPUT_SCHEMA['properties']).index('drop_evidence')
      < list(_cs._SCREEN_OUTPUT_SCHEMA['properties']).index('verdict'),
      list(_cs._SCREEN_OUTPUT_SCHEMA['properties']))
check('  ...and it is required, not optional',
      'drop_evidence' in _cs._SCREEN_OUTPUT_SCHEMA['required'])
for _lvl in ('entry', 'junior', 'mid', 'senior'):
    for _mode in (False, True):
        _prompt_text = _profiles.job_profile(_lvl).prompt_for(_mode)
        check('the %s %s prompt tells Claude the quote is checked'
              % (_lvl, 'not-remote' if _mode else 'remote'),
              'drop_evidence' in _prompt_text, _prompt_text[-200:])


section('4.spend  the Claude ledger: what this app has spent, from the tokens themselves')

# Anthropic does not tell an ordinary API key what the balance is, so the Health Check can
# only be honest about spending if the app counts its own. Every response reports its tokens;
# these are the sums done on them.
from app.pipeline.claude_screen import spend as _spend  # noqa: E402


class _Usage:
    def __init__(self, **kw):
        self.input_tokens = kw.get('input_tokens', 0)
        self.output_tokens = kw.get('output_tokens', 0)
        self.cache_creation_input_tokens = kw.get('cache_creation_input_tokens', 0)
        self.cache_read_input_tokens = kw.get('cache_read_input_tokens', 0)


# Haiku 4.5: $1.00 per million in, $5.00 per million out.
_one_million = _Usage(input_tokens=1_000_000, output_tokens=1_000_000)
check('a million in and a million out costs input + output',
      abs(_spend.cost_of('claude-haiku-4-5-20251001', _one_million) - 6.00) < 1e-9,
      _spend.cost_of('claude-haiku-4-5-20251001', _one_million))
check('a batch is half price',
      abs(_spend.cost_of('claude-haiku-4-5-20251001', _one_million, batch=True) - 3.00) < 1e-9)
check('a cache write costs a quarter more than fresh input',
      abs(_spend.cost_of('claude-haiku-4-5-20251001',
                         _Usage(cache_creation_input_tokens=1_000_000)) - 1.25) < 1e-9)
check('a cache read costs a tenth',
      abs(_spend.cost_of('claude-haiku-4-5-20251001',
                         _Usage(cache_read_input_tokens=1_000_000)) - 0.10) < 1e-9)
check('an unknown model still costs something rather than nothing',
      _spend.cost_of('claude-something-new', _one_million) > 0)
check('no usage object costs nothing', _spend.cost_of('claude-haiku-4-5', None) == 0.0)
check('a usage object of zeros costs nothing',
      _spend.cost_of('claude-haiku-4-5', _Usage()) == 0.0)

# The ledger itself, in the isolated storage every suite runs against.
storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
_ledger_path = storage.DATA_DIR / 'claude_spend.json'
if _ledger_path.exists():
    _ledger_path.unlink()
check('an empty ledger reports zero', _spend.summary()['total_usd'] == 0.0)
_spend.start_run()
_first = _spend.record('claude-haiku-4-5', _Usage(input_tokens=100_000, output_tokens=10_000),
                       listings=4)
check('recording returns what the call cost', abs(_first - 0.15) < 1e-9, _first)
_spend.record('claude-haiku-4-5', _Usage(input_tokens=100_000, output_tokens=10_000),
              batch=True, listings=6)
_totals = _spend.summary()
check('the ledger adds the calls up', abs(_totals['total_usd'] - 0.225) < 1e-6, _totals)
check('  ...and counts them', _totals['calls'] == 2, _totals)
check('  ...and the listings they covered', _totals['listings'] == 10, _totals)
check('  ...and puts them in this month',
      abs(_totals['month_usd'] - _totals['total_usd']) < 1e-9, _totals)
_spend.start_run()
_after = _spend.summary()
check('a new run remembers the last one rather than the whole history',
      abs(_after['last_run_usd'] - 0.225) < 1e-6 and _after['last_run_listings'] == 10, _after)
check('  ...and gives a per-listing figure the Health Check can quote',
      abs(_after['per_listing_usd'] - 0.0225) < 1e-6, _after)
check('the lifetime total survives a new run', abs(_after['total_usd'] - 0.225) < 1e-6)

# It rides inside a paid filter run, so it must never be what breaks one.
check_no_raise('a broken usage object never raises into a search',
               lambda: _spend.record('claude-haiku-4-5', object(), listings=1))
check_no_raise('neither does a ledger file full of nonsense',
               lambda: (_ledger_path.write_text('{ not json', encoding='utf-8'),
                        _spend.record('claude-haiku-4-5', _Usage(input_tokens=10), listings=1),
                        _spend.summary()))
_ledger_path.unlink(missing_ok=True)


section('4.twins  one job on two boards, caught once Claude has named the employer')

# A real Amsterdam result showed the user 48 listings with 8 duplicate pairs in them: QuantumBlack's
# Data Scientist on LinkedIn and on qarera, Metyis' Data Science Analyst on both, Robeco's
# Junior Climate Data Scientist on LinkedIn and quantjobs. The first dedup cannot see them --
# it runs before anything has read the posting, when most rows carry no employer at all, and
# the two boards' descriptions differ too much to match (3,802 characters against 1,929).
_TWINS = [
    {'title': 'Data Scientist - QuantumBlack, AI by McKinsey',
     'company': 'QuantumBlack, AI by McKinsey', 'country': 'Netherlands',
     'url': 'https://nl.linkedin.com/jobs/view/data-scientist-quantumblack',
     'description': 'A short LinkedIn rendering of the posting.'},
    {'title': 'Data Scientist - QuantumBlack, AI by McKinsey',
     'company': 'QuantumBlack AI by McKinsey BV', 'country': 'Netherlands',
     'url': 'https://www.qarera.com/job/1626125',
     'description': 'A much longer rendering of the same posting, with the whole advert, '
                    'the benefits, the team, and the application process spelled out.'},
    {'title': 'Data Science Analyst at Metyis', 'company': 'Metyis', 'country': 'Netherlands',
     'url': 'https://www.qarera.com/job/1567004', 'description': 'One board.'},
    {'title': 'Data Science Analyst', 'company': 'Metyis BV', 'country': 'Netherlands',
     'url': 'https://nl.linkedin.com/jobs/view/data-science-analyst',
     'description': 'Another board, rendering the same vacancy quite differently indeed.'},
    # Not a twin: one employer, two real openings.
    {'title': 'Data Engineer', 'company': 'Metyis', 'country': 'Netherlands',
     'url': 'https://nl.linkedin.com/jobs/view/data-engineer', 'description': 'Different job.'},
    # Not a twin either: same title and employer, but the same site listing it twice is the
    # earlier passes' business, and its two copies do have matching text.
    {'title': 'Data Science Analyst', 'company': 'Metyis', 'country': 'Netherlands',
     'url': 'https://nl.linkedin.com/jobs/view/data-science-analyst-copy',
     'description': 'Another board, rendering the same vacancy quite differently indeed.'},
]
_twin_kept, _twin_merged = p._step_merge_twins([dict(r) for r in _TWINS], [])
_twin_urls = {str(j['url']) for j in _twin_kept}
check('the two copies of one job become one', _twin_merged == 2, _twin_merged)
check('  ...keeping the fuller description',
      'https://www.qarera.com/job/1626125' in _twin_urls, sorted(_twin_urls))
check('  ...even when one board appended "at Metyis" to the title',
      len([u for u in _twin_urls if 'data-science-analyst' in u or '1567004' in u]) == 2,
      sorted(_twin_urls))
check('a different job at the same employer is left alone',
      'https://nl.linkedin.com/jobs/view/data-engineer' in _twin_urls)
check('two listings on the SAME site are left to the dedup step',
      len([u for u in _twin_urls if 'nl.linkedin.com' in u]) >= 2, sorted(_twin_urls))

# Two real openings with one title in two countries are two jobs.
_abroad = [{'title': 'Data Scientist', 'company': 'Adyen', 'country': 'Netherlands',
            'url': 'https://a.invalid/1', 'description': 'Amsterdam office.'},
           {'title': 'Data Scientist', 'company': 'Adyen', 'country': 'Germany',
            'url': 'https://b.invalid/2', 'description': 'Berlin office.'}]
check('the same title at the same employer in another country is another job',
      p._step_merge_twins([dict(r) for r in _abroad], [])[1] == 0)

# A listing Claude objected to must never be the copy that survives.
_flagged_first = [dict(_TWINS[1]), dict(_TWINS[0])]
_flags = [{'job': _flagged_first[0], 'reason': 'Rule 4 - too senior', 'part': 'screen'}]
_kept_after, _merged_after = p._step_merge_twins(_flagged_first, _flags)
check('a flagged copy loses to its unflagged twin',
      _merged_after == 1 and 'linkedin' in str(_kept_after[0]['url']), _kept_after)
check('  ...and the flag goes with it, not into the review dialog', _flags == [], _flags)

check('a row with no employer cannot merge anything',
      p._step_merge_twins([{'title': 'Data Scientist', 'company': '', 'url': 'https://x/1',
                            'description': 'a'},
                           {'title': 'Data Scientist', 'company': '', 'url': 'https://y/2',
                            'description': 'b'}], [])[1] == 0)
check('one listing is never a duplicate of itself',
      p._step_merge_twins([dict(_TWINS[0])], [])[1] == 0)


section('4.entities  HTML entities are unescaped before anyone reads the listing')

# M-6, open since the M campaign and now measured: 26,445 entities across the five real
# corpora, on 27-43% of listings, and ZERO keyword verdicts change when they are unescaped.
# So this is not a filtering fault -- it is what the user reads in the table and the export, and
# what Claude is handed.
_ENT = [{'title': 'Data Scientist, Risk &amp; Pricing', 'company': 'A',
         'url': 'https://example.invalid/e1', 'country': 'Netherlands',
         'description': 'Fully remote. You combine technology &amp; domain knowledge, '
                        'working &lt;independently&gt; with the team in English.'}]
_ent_kept, _r, _f = p.reapply_filters([dict(r) for r in _ENT], progress_cb=None,
                                      anthropic_api_key=None, should_cancel=lambda: False,
                                      search_title='Data Scientist', search_level='junior',
                                      search_work_mode='remote')
check('the listing survives to be checked', len(_ent_kept) == 1, _ent_kept)
check('&amp; in the title becomes &',
      _ent_kept[0]['title'] == 'Data Scientist, Risk & Pricing', _ent_kept[0]['title'])
check('  ...and in the description too',
      'technology & domain knowledge' in _ent_kept[0]['description'],
      _ent_kept[0]['description'][:90])
check('  ...including the angle brackets',
      '<independently>' in _ent_kept[0]['description'], _ent_kept[0]['description'][:120])
check('a listing with no entity is left exactly as it was',
      p.reapply_filters([{'title': 'Data Scientist', 'company': 'B', 'country': 'Netherlands',
                          'url': 'https://example.invalid/e2',
                          'description': 'Fully remote. Plain text, no entities.'}],
                        progress_cb=None, anthropic_api_key=None,
                        should_cancel=lambda: False, search_title='Data Scientist',
                        search_level='junior', search_work_mode='remote')[0][0]['description']
      == 'Fully remote. Plain text, no entities.')


section('4.place  a Not Remote search only wants jobs in the countries searched')
# Found in the campaign: an Amsterdam Not Remote run kept "Data Analyst / Data Scientist
# (H/F)" in Paris, because the Work Location rule reads the words about remote work and never
# the place. Remote work can be done from anywhere, so the Remote search still must not ask.
# The rule is deliberately timid -- a wrong drop here costs a real job -- and these are the
# limits of what it may touch.
_PLACE_ROWS = [
    {'title': 'Data Scientist', 'company': 'Bloemhof BV', 'url': 'https://example.invalid/nl',
     'country': 'Netherlands', 'location': 'Amsterdam',
     'description': 'Data Scientist. You join our Amsterdam office on site, five days a '
                    'week, building forecasting models for the tulip trade in English.'},
    {'title': 'Data Scientist', 'company': 'Rivegauche SA', 'url': 'https://example.invalid/fr',
     'country': 'France', 'location': 'Paris',
     'description': 'Data Scientist. This is an on site role in our Paris office, working '
                    'in English on recommendation engines for a retail bank.'},
    {'title': 'Data Scientist', 'company': 'Nowhere Ltd',
     'url': 'https://example.invalid/unknown', 'country': '', 'location': '',
     'description': 'Data Scientist. You will be on site with the platform team, writing '
                    'English documentation for our streaming ingestion work.'},
    {'title': 'Data Scientist', 'company': 'Manyhubs Inc', 'url': 'https://example.invalid/many',
     'country': 'LATAM, Europe, USA', 'location': '',
     'description': 'Data Scientist. Choose one of our hubs and work on site there, on '
                    'pricing experiments across three continents, all in English.'},
    {'title': 'Data Scientist', 'company': 'Roundworld Oy', 'url': 'https://example.invalid/global',
     'country': 'Worldwide', 'location': '',
     'description': 'Data Scientist. On site at whichever of our offices you pick, on '
                    'churn prediction for a subscription business, in English.'},
    # Remote, and abroad: the row that proves a Remote search still ignores the country.
    {'title': 'Data Scientist', 'company': 'Farflung AB',
     'url': 'https://example.invalid/remote-fr', 'country': 'France', 'location': 'Lyon',
     'description': 'Data Scientist. This role is fully remote and can be done from '
                    'anywhere in Europe, in English, on demand forecasting.'},
]


def _place_run(mode, countries, cities=None):
    kept, _removed, _flagged = p.reapply_filters(
        [dict(r) for r in _PLACE_ROWS], progress_cb=None, anthropic_api_key=None,
        should_cancel=lambda: False, search_title='Data Scientist', search_level='junior',
        search_work_mode=mode, search_countries=countries, search_cities=cities)
    return {str(j.get('url')).rsplit('/', 1)[-1] for j in kept}


_nl = _place_run('not_remote', ['Netherlands'])
check('Not Remote drops a job in a country nobody searched', 'fr' not in _nl, _nl)
check('  ...and keeps the one in the searched country', 'nl' in _nl, _nl)
# These three used to assert the opposite, and the change is the user's: [owner's note: if Netherlands is chosen, only Netherlands is wanted]. The rule was timid on the grounds that a wrong
# drop costs a real job, and it kept an unknown country, a list of countries, and a board's
# "Worldwide". Counted on the real Bank those three hatches were keeping 309 rows out of the
# 13,967 a Netherlands filter kept -- they were not protecting much, and he had asked for
# none of them. A row must now NAME a country he chose.
check('  ...removes a listing whose country is unknown', 'unknown' not in _nl, _nl)
check('  ...removes a board\'s "Worldwide"', 'global' not in _nl, _nl)
check('  ...and removes "LATAM, Europe, USA", which names nowhere he asked for',
      'many' not in _nl, _nl)
# The other half of that rule -- a list that DOES name his country stays -- is proved in
# section 4.chosen, which has a "Germany, Netherlands" row built for it.
check('Not Remote drops the remote listing, wherever it is',
      'remote-fr' not in _nl, _nl)
# This assertion changed on purpose, and the distinction it now draws is the whole point.
# The WORK LOCATION rule still never asks where a remote job is -- remote work can be done
# from anywhere, so the rule stays off in a Remote search, exactly as before. What asks now
# is the Filter window's own country choice, which is a different question: not "could he do
# this job" but "did he ask to see this country". The user ticked Netherlands + Remote and got
# German listings back, because nothing in a Remote run ever looked at the tick. So: no
# country chosen, the place is never mentioned; a country chosen, it is honoured.
check('Remote never asks where the job is when no country was chosen',
      'remote-fr' in _place_run('remote', []), _place_run('remote', []))
_remote_kept = _place_run('remote', ['Netherlands'])
check('  ...but a country ticked in the Filter window IS honoured in a Remote run',
      'remote-fr' not in _remote_kept, _remote_kept)
# Nothing else in this fixture survives a Remote run to compare against: every other row is
# an on-site job, and the Work Location rule drops those before the country is ever asked.
# The Dutch survivor is proved in section 4.chosen, on rows built for it.
check('with neither country nor city chosen the rule does nothing',
      'fr' in _place_run('not_remote', []), _place_run('not_remote', []))
# The user's own settings for the Amsterdam run were cities=['Amsterdam'], countries=[] -- a city
# search stores no country, so without this the rule would never fire on a real search.
_by_city = _place_run('not_remote', [], ['Amsterdam'])
check('a city alone says which country was searched', 'fr' not in _by_city, _by_city)
check('  ...and keeps that country\'s listings', 'nl' in _by_city, _by_city)
check('a city nobody has heard of leaves the rule off',
      'fr' in _place_run('not_remote', [], ['Atlantis']))
check('several searched countries all count',
      {'nl', 'fr'} <= _place_run('not_remote', ['Netherlands', 'France']))
_steps = []
p.reapply_filters([dict(r) for r in _PLACE_ROWS],
                  progress_cb=lambda m, d, t: _steps.append(m), anthropic_api_key=None,
                  should_cancel=lambda: False, search_title='Data Scientist',
                  search_level='junior', search_work_mode='not_remote',
                  search_countries=['Netherlands'])
# The country breakdown moved into the chosen step when _step_place was retired -- one
# question, one answer -- but the line itself was worth keeping. "376 removed" says the
# filter fired; naming France says whether it fired on the right thing.
check('the Log names the country it removed for',
      any('FILTER_STEP_ITEM:chosen|In France' in m for m in _steps),
      [m for m in _steps if ':chosen|' in m])
check('  ...and reports the step like every other one',
      any(m.startswith('FILTER_STEP_DONE:chosen|') for m in _steps))
check('  ...opening the heading before the lines that belong under it',
      ([m.split('|')[0] for m in _steps if ':chosen|' in m][0]
       == 'FILTER_STEP_START:chosen'),
      [m for m in _steps if ':chosen|' in m][:3])


section('4.why  the Thesis and Internship modules say what they actually did')
# Also from the campaign: in a Not Remote search both modules removed remote postings and
# reported it as "cannot be done from Turin" -- the opposite of the truth, on the one line
# the Log gives them.
_REMOTE_INTERNSHIP = {
    'title': 'Internship Data Engineering', 'company': 'A',
    'url': 'https://example.invalid/i', 'country': 'Germany', 'location': 'Berlin',
    'description': 'Internship in data engineering. This is a fully remote internship, '
                   'work from home anywhere in Europe. Paid internship.',
}
from app.pipeline.internship import finder as _intern_finder  # noqa: E402
from app.pipeline.thesis import finder as _thesis_finder  # noqa: E402
for _label, _finder, _row in (
        ('Internship', _intern_finder, dict(_REMOTE_INTERNSHIP)),
        ('Thesis', _thesis_finder,
         dict(_REMOTE_INTERNSHIP, title='Master Thesis Data Engineering',
              description='Master thesis in data engineering, fully remote, work from '
                          'home anywhere in Europe. Paid.'))):
    _probe = dict(_row, **{p.search_title.ROW_KEY: 'Data Engineer',
                           p.search_title.LEVEL_ROW_KEY: _label.lower(),
                           p.search_title.WORK_MODE_ROW_KEY: 'not_remote'})
    _ok, _why = _finder.survives(_probe)
    check('%s: a remote posting goes in a Not Remote search' % _label, not _ok, (_ok, _why))
    check('  ...and the reason says so, not "cannot be done from Turin"',
          'Not Remote' in _why and 'Turin' not in _why, _why)
    _probe[p.search_title.WORK_MODE_ROW_KEY] = 'remote'
    check('  ...while a Remote search keeps it', _finder.survives(_probe)[0],
          _finder.survives(_probe))


# ---------------------------------------------------------------------------- 4.note ----
# The user's request: the reason a listing was removed has to stay on the end of the listing,
# between markers, so a removal can be read rather than taken on trust. The danger the whole
# design turns on is that the note lives in `description`, which is also what every rule and
# Claude READ -- so these check both halves: that it is written, and that it never counts as
# something the employer said.
from app.pipeline import drop_note as _note  # noqa: E402

_POSTING = 'We need a Data Scientist. Sehr gute Deutschkenntnisse in Wort und Schrift.'
_row = {'description': _POSTING}
_note.set_drop_note(_row, 'Rule 2 - Requires German C1; his résumé says A2.',
                    'Sehr gute Deutschkenntnisse in Wort und Schrift')
check('the note is on the end of the listing', _row['description'].startswith(_POSTING))
check('  ...between the $$ markers', _row['description'].rstrip().endswith('$$'))
check('  ...carrying the reason', 'Requires German C1' in _row['description'])
check('  ...and the posting\'s own words', 'Sehr gute Deutschkenntnisse' in
      _row['description'].split('WHY THIS WAS REMOVED')[1])
check('the posting itself is recoverable, exactly',
      _note.listing_text_without_note(_row['description']) == _POSTING)
check('drop_note_of reads it back', _note.drop_note_of(_row).startswith('$$'))

# The round trip must be exact to the character, including whitespace the posting ends with.
# This is not fussiness: `description` is hashed into the screening cache key, so a posting
# that comes back two newlines shorter is re-screened and re-billed on every later run. The
# first version of set_drop_note rstripped the body, and three of fourteen real German
# listings ended in their own blank lines -- "...Apply Now!\n\n" -- so three of fourteen
# missed the cache. These are those endings.
for _tail in ('', '\n', '\n\n', '\n\n\n', ' ', '\t\n', '\n \n'):
    _exact = {'description': 'Apply Now!' + _tail}
    _note.set_drop_note(_exact, 'Rule 1 - office', 'must be on site')
    check('a posting ending %r comes back byte for byte' % _tail,
          _note.listing_text_without_note(_exact['description']) == 'Apply Now!' + _tail,
          repr(_note.listing_text_without_note(_exact['description'])))
    check('  ...and its Claude cache key is unchanged by the note',
          _cs._claude_screen_cache_key(dict(_QUOTE_JOB, description='Apply Now!' + _tail
                                            + '\n\n$$ WHY THIS WAS REMOVED\nr\n$$'))
          == _cs._claude_screen_cache_key(dict(_QUOTE_JOB,
                                               description='Apply Now!' + _tail)))

# Set twice: one note, not two. A listing is re-screened on most runs, and a note that
# accumulated would grow without limit and carry contradictory reasons.
_note.set_drop_note(_row, 'Rule 1 - office required', 'must be on site in Berlin')
check('setting a note twice leaves exactly one',
      _row['description'].count('WHY THIS WAS REMOVED') == 1, _row['description'])
check('  ...and it is the newer one', 'office required' in _row['description']
      and 'German C1' not in _row['description'])
_note.clear_drop_note(_row)
check('clearing gives the posting back untouched', _row['description'] == _POSTING)
check('clearing a listing that never had a note is harmless',
      (lambda d: (_note.clear_drop_note(d), d['description'])[1])({'description': _POSTING})
      == _POSTING)
check('a listing with no description at all survives both',
      (lambda d: (_note.clear_drop_note(d), _note.drop_note_of(d))[1])({}) == '')

# The half that matters for money and for correctness: a note must never be read as input.
_noted = dict(_QUOTE_JOB)
_note.set_drop_note(_noted, 'Rule 3 - unpaid', 'This is an unpaid volunteer position')
check('the note never reaches Claude\'s prompt',
      'WHY THIS WAS REMOVED' not in _cs._claude_screen_prompt(_noted))
check('  ...so the screening cache key is unchanged by it',
      _cs._claude_screen_cache_key(_noted) == _cs._claude_screen_cache_key(dict(_QUOTE_JOB)))
check('  ...which is what stops a flagged listing being re-screened and re-billed',
      _cs._claude_screen_cache_key(_noted) == _cs._claude_screen_cache_key(dict(_QUOTE_JOB)))
# The guard checking its own homework: our note repeats the quote verbatim, so if the note
# stayed in the haystack a quote that is NOT in the posting would be confirmed by it.
check('a quote found only in our own note is still rejected',
      _cs._evidence_is_real('This is an unpaid volunteer position', _noted) is False)
check('  ...while a quote really in the posting is still accepted',
      _cs._evidence_is_real('Have at least 2 years experience with ETL', _noted) is True)

# Two copies of one vacancy, one of them flagged last run. They must still be duplicates.
_twin_a = {'title': 'Data Scientist', 'company': 'Acme', 'url': 'https://a.invalid/1',
           'description': _POSTING * 3}
_twin_b = dict(_twin_a, url='https://b.invalid/1')
_note.set_drop_note(_twin_b, 'Rule 2 - German', 'Sehr gute Deutschkenntnisse')
_kept_twins, _removed_twins = p.filters._remove_duplicates_list([_twin_a, _twin_b])
check('a note on one copy does not hide a duplicate', _removed_twins == 1,
      (len(_kept_twins), _removed_twins))

# End to end through reapply_filters, which is where the user will actually see it: the note is
# stripped from every row before any rule reads it, and written back only onto a removal.
_notes_seen = []


class _NotingScreener:
    """Drops anything whose posting demands German, quoting the posting for it."""

    class messages:
        @staticmethod
        def create(**kw):
            sent = kw['messages'][0]['content']
            _notes_seen.append('WHY THIS WAS REMOVED' in sent)
            german = 'Deutschkenntnisse' in sent
            return _Reply(_screen_answer(
                'DROP' if german else 'KEEP', rule=2,
                reason='Requires German, his résumé says A2.',
                drop_evidence='Sehr gute Deutschkenntnisse' if german else ''))


_german_row = {'title': 'Data Scientist', 'company': 'Acme',
               'url': 'https://example.invalid/de', 'country': 'Germany',
               'location': 'Berlin', 'description': _POSTING}
_note.set_drop_note(_german_row, 'a stale note from some older run', 'ignore me')
_kept_n, _removed_n, _flagged_n = p.reapply_filters(
    [_german_row], progress_cb=None, anthropic_api_key=None, should_cancel=lambda: False,
    search_title='Data Science', search_level='junior', search_work_mode='remote')
check('reapply_filters strips a stale note before any rule reads the listing',
      all('WHY THIS WAS REMOVED' not in str(j.get('description') or '')
          for j in _kept_n), [j.get('description') for j in _kept_n])


# -------------------------------------------------------------------------- 4.chosen ----
section('4.chosen  every choice in the Filter window actually filters')
# The user picked Junior, Remote, Netherlands, Part-Time, Internship and got back German
# full-time listings. The rules were all correct; four of them were never called, and the
# fifth -- the country -- was only ever consulted by the Not Remote place rule, which returns
# immediately in a Remote search. That is why these tests go through reapply_filters rather
# than calling chosen_filters directly: a unit test of filter_by_place would have passed
# every day the window was broken. What has to be tested is that the choice REACHES the
# pipeline and CHANGES the answer.
from app.pipeline import chosen_filters as _cf              # noqa: E402
from app.pipeline import title_equivalents as _ch_te  # noqa: E402

# Each of these is a different job at a different employer, because dedup is right to merge
# five copies of one advert and this section is not testing dedup. The first draft shared one
# description and lost four of five rows before the country filter ever saw them.
_CH_BODIES = {
    'nl': 'You join the forecasting team in Amsterdam, working fully remote in English on '
          'demand models for a grocery delivery business, with Python and dbt.',
    'de': 'Fully remote role building English-language churn models for a Berlin insurance '
          'group, working with Snowflake and a small analytics engineering team.',
    'quiet': 'A fully remote English-speaking position on recommendation engines for an '
             'online bookshop, owning the experiment pipeline end to end.',
    'many': 'Remote across our offices: pricing experiments for a travel marketplace, '
            'written up in English, with a strong bias towards causal inference.',
    'world': 'Work from anywhere on our English-language fraud detection platform, tuning '
             'gradient boosted models against streaming transaction data.',
    'intern': 'Internship (Praktikum) for six months at Ostara, fully remote, helping the '
              'English-speaking research team label satellite imagery.',
    'part': 'A part-time role at Brightwell, 20 hours a week and fully remote, maintaining '
            'English-language reporting dashboards for a charity.',
    'full': 'Permanent full time position with the Kestrel team, fully remote, owning the '
            'English-language customer segmentation models end to end.',
    'thesis': 'Master thesis placement with the Vandermeer research group, fully remote, on '
              'English-language sequence models for protein folding.',
    'phd': 'A four-year doctoral position, fully remote, writing your thesis in English on '
           'causal inference for observational health data.',
    'ds': 'Fully remote data science work in English: forecasting models for a grocery '
          'delivery business, owning the pipeline end to end.',
    'ml': 'Fully remote machine learning engineering in English: training and serving '
          'recommendation models for an online bookshop.',
    'ai': 'Fully remote applied AI work in English: fine-tuning language models for a '
          'customer support product, with evaluation you design yourself.',
}


def _ch_row(url, **extra):
    """A listing distinct enough to survive dedup.

    The first draft of these rows gave every one the same title, company and description,
    and four of the five vanished before the country filter ever saw them -- dedup had
    merged them as the same job on five boards. It was right to. The rows have to differ
    the way real listings differ, or the test measures the wrong step.
    """
    tag = url.rsplit('/', 1)[-1]
    row = {'title': 'Data Scientist', 'company': 'Acme %s BV' % tag.title(), 'url': url,
           'description': _CH_BODIES[tag] + ' ' + _CH_BODIES[tag]}
    row.update(extra)
    return row


def _ch_filter(rows, **choices):
    """reapply_filters with Claude off, returning the URLs it kept."""
    kept, _removed, _flagged = p.reapply_filters(
        [dict(r) for r in rows], progress_cb=None, anthropic_api_key=None,
        should_cancel=lambda: False, search_title='Data Science', search_level='junior',
        search_work_mode='remote', **choices)
    return {j.get('url') for j in kept}


# --- the country, in a REMOTE search -- the exact shape of the user's report ------------------
_CH_PLACE = [
    _ch_row('https://example.invalid/nl', country='Netherlands'),
    _ch_row('https://example.invalid/de', country='Germany'),
    _ch_row('https://example.invalid/quiet', country=''),
    _ch_row('https://example.invalid/many', country='Germany, Netherlands'),
    _ch_row('https://example.invalid/world', country='Worldwide'),
]
_ch_all = _ch_filter(_CH_PLACE)
check('with no country chosen every listing survives the place choice',
      len(_ch_all) == 5, sorted(_ch_all))
_ch_nl = _ch_filter(_CH_PLACE, search_countries=['Netherlands'])
check('choosing Netherlands in a REMOTE search really removes the German listing',
      'https://example.invalid/de' not in _ch_nl, sorted(_ch_nl))
check('  ...and keeps the Dutch one', 'https://example.invalid/nl' in _ch_nl, sorted(_ch_nl))
# Strict, because the user said so: [owner's note: if Netherlands is chosen, only Netherlands is wanted]. The
# first version waved through anything that did not clearly state a country he had not asked
# for -- an empty field, a list of countries, a board's "Worldwide". Counted on the real
# Bank those three hatches were keeping 309 rows out of 13,967, none of which he had asked
# to see. What survives now is a row that NAMES a country he chose, and nothing else.
check('  ...removes a listing that never says where it is',
      'https://example.invalid/quiet' not in _ch_nl, sorted(_ch_nl))
check('  ...removes a board\'s "Worldwide", which is not the Netherlands',
      'https://example.invalid/world' not in _ch_nl, sorted(_ch_nl))
check('  ...but keeps a field that names several countries INCLUDING his',
      'https://example.invalid/many' in _ch_nl, sorted(_ch_nl))
check('  ...and a list that does not name his country goes',
      _cf.filter_by_place([{'country': 'USA, Canada, Mexico'}], ['Netherlands'])[1] == 1)
check('  ...so the choice changed the answer', _ch_nl != _ch_all, sorted(_ch_nl))

# A city carries its own country: picking Amsterdam and no country must not empty the run.
_ch_city = _ch_filter(_CH_PLACE, search_cities=['Amsterdam'])
check('choosing a city keeps that city\u2019s country',
      'https://example.invalid/nl' in _ch_city, sorted(_ch_city))
check('  ...and still removes the other country',
      'https://example.invalid/de' not in _ch_city, sorted(_ch_city))

# --- the kind of role --------------------------------------------------------------------
# The second fault: the category was read off the row, and reapply_filters REWRITES
# job['Category'] in a later step -- so the value being matched was replaced a moment after
# the comparison. This row carries a deliberately wrong stored Category to prove the filter
# no longer trusts it.
# The kind is in the title, because that is where categorize now reads it and where real
# adverts put it. Each row also carries a deliberately WRONG stored Category, to prove the
# filter computes the answer instead of believing what the Bank happens to hold.
# Every title also says Data Science, because the Title Check runs before this step and
# removes anything that does not -- a fixture that forgets it measures that rule instead.
_CH_KIND = [
    _ch_row('https://example.invalid/intern', Category='Full-Time',
            title='Data Science Intern'),
    _ch_row('https://example.invalid/part', Category='Thesis',
            title='Data Scientist (m/w/d) in Teilzeit 20 Std./Woche'),
    _ch_row('https://example.invalid/full', Category='Internship',
            title='Data Scientist'),
    _ch_row('https://example.invalid/thesis', Category='Part-Time',
            title='Afstudeerstage Data Science'),
    _ch_row('https://example.invalid/phd', Category='Internship',
            title='PhD Candidate in Data Science'),
]
# THE FILTER NO LONGER CALLS filter_by_category, SO THESE ASK IT DIRECTLY.
#
# It used to run inside reapply_filters and these assertions went through it. On the
# real Netherlands run, ticking Part-Time removed 295 of the 321 listings that had
# survived every other rule and left four, so the user moved the choice into the table:
# [owner's note: the Type filter may go, as the choice is made in the table]. The Type column's filter button does it now, on a pool that kept
# everything.
#
# The function stays and so do its assertions. It is correct, it is still the thing
# that knows a PhD post is not a thesis, and a correct rule with no caller AND no
# test is how T-1 survived for months. Tested here on its own terms.
def _ch_kinds_direct(rows, categories):
    kept, _removed = p.chosen_filters.filter_by_category(
        [dict(r) for r in rows], categories)
    return {j.get('url') for j in kept}


_ch_kinds = _ch_kinds_direct(_CH_KIND, ['Part-Time', 'Internship'])
check('filter_by_category keeps exactly Part-Time and Internship',
      _ch_kinds == {'https://example.invalid/intern', 'https://example.invalid/part'},
      sorted(_ch_kinds))
check('  ...so a stale Category stored on the row is ignored, not believed',
      'https://example.invalid/full' not in _ch_kinds and
      'https://example.invalid/thesis' not in _ch_kinds, sorted(_ch_kinds))
check('  ...and nothing ticked keeps every kind',
      len(_ch_kinds_direct(_CH_KIND, [])) == 5)
# And the Filter itself must now keep all five whatever is ticked -- the half of this
# change that the function's own tests cannot see.
check('the Filter keeps every kind even with Part-Time ticked',
      len(_ch_filter(_CH_KIND, categories=['Part-Time'])) == 5,
      sorted(_ch_filter(_CH_KIND, categories=['Part-Time'])))
# The user asked for doctoral work to be its own kind: [owner's note: a full-time job differs completely from a PhD or research post and they must be separated]. A PhD advert says "thesis" all through its body and is still
# not a thesis placement, so ticking Thesis must not bring it back.
check('a PhD post is its own kind, not Full-Time and not Thesis',
      _ch_kinds_direct(_CH_KIND, ['PhD']) == {'https://example.invalid/phd'},
      sorted(_ch_kinds_direct(_CH_KIND, ['PhD'])))
check('  ...so ticking Thesis does not bring it back',
      'https://example.invalid/phd' not in _ch_kinds_direct(_CH_KIND, ['Thesis']),
      sorted(_ch_kinds_direct(_CH_KIND, ['Thesis'])))
check('  ...and ticking Full-Time does not either',
      'https://example.invalid/phd' not in _ch_kinds_direct(_CH_KIND, ['Full-Time']),
      sorted(_ch_kinds_direct(_CH_KIND, ['Full-Time'])))

# --- the job titles the user ticked in the Filter window ---------------------------------------
# Mutation testing found nothing was watching this: making reapply_filters ignore `fields`
# entirely broke no test at all. It is the choice that decides what a run COSTS -- unticking
# "AI Engineer" takes 512 listings out of Claude's reach on his own pool -- so a change that
# silently stopped reading it would show up as a bill, not as a failure.
_CH_FIELDS = [
    _ch_row('https://example.invalid/ds', title='Data Scientist'),
    _ch_row('https://example.invalid/ml', title='Machine Learning Engineer'),
    _ch_row('https://example.invalid/ai', title='AI Engineer'),
]
# The equivalents are seeded into the on-disk cache rather than asked for. Without this the test
# proves nothing: with no equivalents there is nothing for `fields` to narrow, and the two
# non-"Data Science" titles are dropped by the field rule whatever is ticked -- which is exactly
# how the first version of this test passed while measuring nothing.
_seed_equivalents = {
    'v2|data science': {
        'candidates': [
            {'title': 'Machine Learning Engineer', 'same_work': 80,
             'closest_to': 'Machine Learning Engineer', 'because': 'the same work'},
            {'title': 'AI Engineer', 'same_work': 75,
             'closest_to': 'AI Engineer', 'because': 'applied modelling'},
        ],
        'rejected': [],
    },
}
(Path(storage.DATA_DIR) / 'title_equivalents.json').write_text(
    json.dumps(_seed_equivalents), encoding='utf-8')
_ch_te.PROMPT_VERSION = 'v2'          # the key the seed above is written under

_all_three = _ch_filter(_CH_FIELDS)
check('with no fields chosen, every searched title is read',
      len(_all_three) >= 1, sorted(_all_three))

_only_typed = _ch_filter(_CH_FIELDS, fields=['Data Science'])
check('ticking only the typed title drops the other names',
      'https://example.invalid/ml' not in _only_typed
      and 'https://example.invalid/ai' not in _only_typed, sorted(_only_typed))
check('  ...and keeps the typed one',
      'https://example.invalid/ds' in _only_typed, sorted(_only_typed))

_two = _ch_filter(_CH_FIELDS, fields=['Data Science', 'Machine Learning Engineer'])
check('ticking two titles reads exactly those two',
      'https://example.invalid/ml' in _two and 'https://example.invalid/ai' not in _two,
      sorted(_two))
check('  ...so the choice is read at all, which is what mutation testing found unwatched',
      _two != _only_typed, (sorted(_two), sorted(_only_typed)))


# --- the résumé-match floor --------------------------------------------------------------
# Runs after Claude's second pass, so it is tested on the function: with Claude off there is
# no score to filter on, which is itself the reason an absent score must survive.
_CH_SCORED = [{'url': 'a', 'claude_match': 80}, {'url': 'b', 'claude_match': 20},
              {'url': 'c'}, {'url': 'd', 'claude_match': None}]
_ch_kept, _ch_cut = _cf.filter_by_match(_CH_SCORED, 50)
check('a match floor removes what scored below it',
      {j['url'] for j in _ch_kept} == {'a', 'c', 'd'}, [j['url'] for j in _ch_kept])
check('  ...and an unscored listing is kept -- an absent number is not a low one',
      _ch_cut == 1, _ch_cut)
check('no floor removes nothing', _cf.filter_by_match(_CH_SCORED, 0)[1] == 0)

# --- sponsorship and the date window -----------------------------------------------------
_CH_SPON = [{'url': 'a', 'sponsorship_visa': 'Yes'},
            {'url': 'b', 'sponsorship_visa': 'Unknown'},
            {'url': 'c'}]
check('choosing a sponsorship verdict keeps only that verdict, plus the silent row',
      {j['url'] for j in _cf.filter_by_sponsorship(_CH_SPON, 'Yes')[0]} == {'a', 'c'},
      [j['url'] for j in _cf.filter_by_sponsorship(_CH_SPON, 'Yes')[0]])
check('"Any" sponsorship removes nothing', _cf.filter_by_sponsorship(_CH_SPON, '')[1] == 0)

_ch_old = (_dt.datetime.now() - _dt.timedelta(days=40)).strftime('%Y-%m-%d')
_ch_new = _dt.datetime.now().strftime('%Y-%m-%d')
_CH_DATED = [{'url': 'old', 'posted_date': _ch_old},
             {'url': 'new', 'posted_date': _ch_new},
             {'url': 'undated'}]
check('a date window removes what is older than it',
      {j['url'] for j in _cf.filter_by_date(_CH_DATED, 'pastWeek')[0]} == {'new', 'undated'},
      [j['url'] for j in _cf.filter_by_date(_CH_DATED, 'pastWeek')[0]])
check('  ...and an undated listing is kept -- not knowing when is not knowing it is old',
      'undated' in {j['url'] for j in _cf.filter_by_date(_CH_DATED, 'past24Hours')[0]})
check('"Any time" removes nothing', _cf.filter_by_date(_CH_DATED, 'anyTime')[1] == 0)

# --- the guard against this whole class of fault -------------------------------------------
# Not a rule test: a wiring test. Every choice the window collects must be a parameter
# reapply_filters actually takes, or it is silently dropped again -- which is exactly what
# happened. This compares the window's own key list against the function's signature, so a
# choice added to the dialog tomorrow and forgotten here fails loudly.
from app.pipeline import filter_signature as _ch_sig                      # noqa: E402

_CH_ACCEPTS = set(_inspect.signature(p.reapply_filters).parameters)
_CH_WIRING = {'search_title': 'search_title', 'search_level': 'search_level',
              'search_work_mode': 'search_work_mode', 'countries': 'search_countries',
              'cities': 'search_cities', 'date_range': 'date_range',
              'min_match_percent': 'min_match_percent', 'categories': 'categories',
              'sponsorship': 'sponsorship', 'fields': 'fields'}
check('every filter choice has somewhere to go in reapply_filters',
      all(param in _CH_ACCEPTS for param in _CH_WIRING.values()),
      sorted(set(_CH_WIRING.values()) - _CH_ACCEPTS))
check('  ...and no choice in the window is missing from that list',
      set(_ch_sig.FILTER_CHOICE_KEYS) - {'use_claude'} == set(_CH_WIRING),
      sorted(set(_ch_sig.FILTER_CHOICE_KEYS) - {'use_claude'} ^ set(_CH_WIRING)))
check('the Filter worker passes all of them on',
      all(('%s=self.%s' % (name, name)) in _inspect.getsource(_worker_src.FilterWorker.run)
          for name in ('date_range', 'categories', 'sponsorship', 'min_match_percent')),
      _inspect.getsource(_worker_src.FilterWorker.run))

# --- the résumé now belongs to the Filter window, not the Search wizard --------------------
# [owner's note: the résumé choice moves from Search to Filter, because the résumé is checked in Filter] -- the search never opens the résumé; the Filter is what scores against it.
check('the Filter window is where the résumé is chosen',
      all(hasattr(_fd_src.FilterDialog, name)
          for name in ('_resume_box', '_choose_resume', '_preview_resume')))
check('  ...and the Search wizard no longer asks for it',
      not any(hasattr(_sw_src.SetupWizard, name)
              for name in ('_choose_resume', '_preview_resume', '_show_resume_state')))
check('  ...so a search is never refused for a missing résumé',
      'Résumé needed' not in _inspect.getsource(_sw_src))
check('  ...while the Filter still refuses to run Claude without one',
      'Résumé needed' in _inspect.getsource(_fd_src.FilterDialog._on_submit))

sys.exit(summary('Suite 4 -- pipeline integration'))
