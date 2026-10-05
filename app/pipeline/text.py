"""Small, dependency-free helpers for pulling values out of messy source rows."""
from __future__ import annotations

import html
import re
from urllib.parse import urlencode
import pandas as pd


# Same role-type terms used in the search query, offered as pick-from-a-list options
# for the Job Search page's display-only "Show only / Hide" filter.
TOPIC_KEYWORDS = [
    'DevOps', 'DevOps Engineer', 'DevOps Engineering', 'DevSecOps',
    'Platform Engineer', 'Platform Engineering',
    'MLOps', 'MLOps Engineer', 'MLOps Engineering', 'ML Ops', 'AIOps',
    'ML Platform Engineer', 'AI Platform Engineer', 'ML Infrastructure Engineer',
    'Junior', 'Entry Level', 'Graduate', 'Associate',
]


# Each platform exposes a different "how far back" filter -- these are the dropdown choices
# shown per-platform in the setup wizard, mapped to the actual value the actor expects.
LINKEDIN_DATE_OPTIONS = {
    'Past 24 hours': 'past24Hours',
    'Past week': 'pastWeek',
    'Past month': 'pastMonth',
    'Any time': 'anyTime',
}


INDEED_DATE_OPTIONS = {
    'Last 1 day': '1',
    'Last 3 days': '3',
    'Last 7 days': '7',
    'Last 14 days': '14',
    'Any time': '',
}


GLASSDOOR_DATE_OPTIONS = {
    'Last 1 day': 1,
    'Last 3 days': 3,
    'Last 7 days': 7,
    'Last 14 days': 14,
    'Last 30 days': 30,
}


# ---------------------------------------------------------------------------------------
# One list of dates for all three platforms
# ---------------------------------------------------------------------------------------
#
# The three dictionaries above are what each actor accepts, and no two of them agree:
#
#     LinkedIn    Past 24 hours · Past week · Past month · Any time
#     Indeed      Last 1 day · Last 3 days · Last 7 days · Last 14 days · Any time
#     Glassdoor   Last 1 day · Last 3 days · Last 7 days · Last 14 days · Last 30 days
#
# Three different lists means three separate choices, and a value that is perfectly ordinary
# on one platform does not exist on another. "Last 30 days" is real for Glassdoor and has
# never existed for Indeed -- and sending it cost a two-hour German search its entire Indeed
# leg, with the actor's own clear complaint never reaching the Log.
#
# So there is one list now, and it is the one Sina picks from. Each label carries the right
# value for each platform, and a platform that cannot reach that far back gets its own
# maximum instead of a value it would reject. `note` is what the wizard shows underneath, so
# the shortfall is visible rather than silent.
DATE_RANGES = [
    {'label': 'Past 24 hours',
     'linkedin': LINKEDIN_DATE_OPTIONS['Past 24 hours'],
     'indeed': INDEED_DATE_OPTIONS['Last 1 day'],
     'glassdoor': GLASSDOOR_DATE_OPTIONS['Last 1 day'],
     'note': ''},
    {'label': 'Past 3 days',
     # LinkedIn has no three-day option; a week is its narrowest wider one, and searching
     # wider then filtering is right where searching narrower would lose postings.
     'linkedin': LINKEDIN_DATE_OPTIONS['Past week'],
     'indeed': INDEED_DATE_OPTIONS['Last 3 days'],
     'glassdoor': GLASSDOOR_DATE_OPTIONS['Last 3 days'],
     'note': 'LinkedIn searches a week — it has no 3-day filter'},
    {'label': 'Past week',
     'linkedin': LINKEDIN_DATE_OPTIONS['Past week'],
     'indeed': INDEED_DATE_OPTIONS['Last 7 days'],
     'glassdoor': GLASSDOOR_DATE_OPTIONS['Last 7 days'],
     'note': ''},
    {'label': 'Past 2 weeks',
     'linkedin': LINKEDIN_DATE_OPTIONS['Past month'],
     'indeed': INDEED_DATE_OPTIONS['Last 14 days'],
     'glassdoor': GLASSDOOR_DATE_OPTIONS['Last 14 days'],
     'note': 'LinkedIn searches a month — it has no 2-week filter'},
    {'label': 'Past month',
     'linkedin': LINKEDIN_DATE_OPTIONS['Past month'],
     # Fourteen days is everything Indeed's actor offers. Asking for thirty is not merely
     # ignored, it is rejected outright and the whole Indeed leg is lost.
     'indeed': INDEED_DATE_OPTIONS['Last 14 days'],
     'glassdoor': GLASSDOOR_DATE_OPTIONS['Last 30 days'],
     'note': 'Indeed only goes back 14 days — that is its maximum'},
    {'label': 'Any time',
     'linkedin': LINKEDIN_DATE_OPTIONS['Any time'],
     'indeed': INDEED_DATE_OPTIONS['Any time'],
     # Glassdoor has no "any time"; thirty days is as far as it reaches.
     'glassdoor': GLASSDOOR_DATE_OPTIONS['Last 30 days'],
     'note': 'Glassdoor only goes back 30 days — that is its maximum'},
]

DATE_RANGE_LABELS = [entry['label'] for entry in DATE_RANGES]
DEFAULT_DATE_RANGE = 'Past month'


def date_settings_for(label: str) -> dict:
    """The per-platform values for one of DATE_RANGE_LABELS.

    The single place a date choice becomes actor input. Anything not in the list falls back
    to the default rather than being passed through -- an unrecognised value reaches the
    actor as a rejected request, which is exactly the failure this table exists to end.
    """
    for entry in DATE_RANGES:
        if entry['label'] == label:
            return {'linkedin': entry['linkedin'], 'indeed': entry['indeed'],
                    'glassdoor': entry['glassdoor']}
    return date_settings_for(DEFAULT_DATE_RANGE)


def date_range_note(label: str) -> str:
    """What the wizard shows under the picker: where a platform cannot reach that far."""
    for entry in DATE_RANGES:
        if entry['label'] == label:
            # str() because a row of DATE_RANGES holds both strings and the integer
            # Glassdoor wants, so its value type is the union of the two.
            return str(entry['note'])
    return ''


def dig(d, path, default=None):
    cur = d
    for part in path.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur if cur not in (None, '') else default


def strip_html(text):
    if not text:
        return text
    text = re.sub('<[^<]+?>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def first_present(item, *paths, default=None):
    for p in paths:
        v = dig(item, p)
        if v:
            return v
    return default


def _qs(**params) -> str:
    return urlencode({k: v for k, v in params.items() if v is not None})


_JOOBLE_WARN_THRESHOLD = 50  # start warning once fewer than this many calls remain


# Both USCIS' and open.canada.ca's real download endpoints sit behind a WAF that
# blocks Python's `requests` specifically -- confirmed via real, direct testing:
# `requests.get(..., headers={'User-Agent': 'Mozilla/5.0'})` gets a 403 (USCIS) or the
# WAF's own tiny "Request Rejected" HTML page (open.canada.ca) even with a full,
# realistic browser header set, while the exact same URL succeeds immediately through
# curl (both Windows' own built-in curl.exe and Git Bash's) -- almost certainly TLS/
# HTTP client fingerprinting (e.g. Akamai Bot Manager, common on .gov sites), not
# anything about the headers themselves. curl.exe ships built into Windows 10
# (1803+)/11 by default, confirmed present at the path below via a real check, so
# shelling out to it is a reliable, dependency-free way around this for these two
# sources specifically -- every other sponsor-list fetcher above uses plain `requests`
# since neither IND nor gov.uk block it.
_CURL_EXE = r'C:\Windows\system32\curl.exe'


def _run_direct_api_source(rows: list[dict], name: str, fetch_callable, help_text: str, progress_cb=None) -> int:
    """Runs one direct-API source's fetch_callable() (a zero-arg closure already bound
    to its own params), logging the same yellow-checking / green-success / red-error
    3-step pattern every direct-API source below shares -- collapses what used to be
    ~15-20 lines of near-identical try/except/progress_cb boilerplate per source (11
    near-duplicate copies) down to one call each. GLOG:direct_api|... (not a plain
    WARNING:/SUCCESS:/ERROR:) so these lines nest under "Direct API Search" in the Log
    instead of appearing flat at the very end, unindented -- the same real bug fixed
    for Direct Site Search above. Returns how many rows were added (0 on error)."""
    if progress_cb:
        progress_cb(f"GLOG:direct_api|info|Checking {name} (direct API call)", 0, 1)
    try:
        new_rows = fetch_callable()
        rows.extend(new_rows)
        if progress_cb:
            progress_cb(f"GLOG:direct_api|success|{name}: {len(new_rows)} individual job posting(s) found.", 0, 1)
        return len(new_rows)
    except Exception as e:
        if progress_cb:
            progress_cb(
                f"GLOG:direct_api|error|{name} API call failed ({e}) -- please check manually:\n"
                f"    1 - {help_text}\n"
                f"    2 - If it works fine there, the API/endpoint may have changed\n"
                f"    3 - Send back what you find so it can be fixed",
                0, 1,
            )
        return 0


def text_of(value) -> str:
    """A job field as displayable text -- '' for anything that isn't real text.

    Replaces the `(job.get(x) or '')` idiom that was repeated per field across the Jobs
    table and the Excel export. That idiom handles None but NOT pandas' NaN, because NaN
    is truthy: it sails through `or ''` and then `.capitalize()` raises
    `AttributeError: 'float' object has no attribute 'capitalize'` (verified, on both the
    Jobs page and the export path). The neighbouring location/posted_date cells had the
    milder version of the same bug -- they rendered a literal 'nan' to the user."""
    if value is None:
        return ''
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass  # not a scalar pandas understands -- fall through and stringify
    return value if isinstance(value, str) else str(value)


def is_true_flag(value) -> bool:
    """True only for a genuine True -- the one safe way to read an OPTIONAL boolean field
    off a job dict in this app.

    This exists because of a real, critical bug: `if row.get('thin_description'):` looks
    obviously correct and is not. Only four of the ~20 row builders set that key, and
    every row in a search goes through `pd.DataFrame(rows)` in _finish_run_search_df --
    where pandas fills a missing key with NaN. `float('nan')` is TRUTHY in Python, so the
    plain truthiness test returned True for EVERY row, which silently disabled both
    passes_work_location_rule's positive check and lacks_english_mention for the whole dataset
    (an on-site Indeed listing with no remote wording anywhere was verified surviving
    Filter). It also survived save_jobs/load_jobs, so it kept applying on later runs.

    `is True` alone isn't enough either: once every row in a batch happens to carry the
    key, pandas gives the column a real bool dtype and hands back numpy.bool_(True),
    which `is True` rejects. pd.isna() handles None, NaN and numpy scalars alike, so this
    is correct for every shape the value can actually arrive in."""
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass  # not a scalar pandas understands (a list/str/etc.) -- fall through
    return bool(value)


PLATFORM_LABELS = {
    'indeed': 'Indeed', 'glassdoor': 'Glassdoor', 'linkedin': 'LinkedIn',
    'google': 'Google (countries & cities) — extra cost per listing',
}


# Every platform the wizard can offer, including ones not in DEFAULT_ACTOR_ORDER -- 'google'
# is opt-in only (unchecked by default even for first-time users) since it costs more per
# listing than the other three, but it still needs to always appear in the checklist.
ALL_PLATFORMS = ['indeed', 'glassdoor', 'linkedin', 'google']


# A crawler that gets throttled or blocked receives a real HTTP response with a real body,
# and nothing downstream can tell that apart from a job posting: one such page came back
# from aijobs.ai titled "429" with 607 characters of rate-limit text, and was translated,
# screened by Claude and shown as a job. These are the shapes that give it away.
_ERROR_PAGE_TITLE = re.compile(r'^\s*(\d{3})\s*$')
_ERROR_PAGE_TEXT = re.compile(
    r'\b(too many requests|rate limit|request throttled|access denied|forbidden|'
    r'are you a robot|verify you are human|checking your browser|cloudflare|'
    r'temporarily unavailable|service unavailable|page not found|404 not found|'
    r'zugriff verweigert|seite nicht gefunden)\b', re.I)


def looks_like_error_page(title, text) -> bool:
    """Is this fetched page an error, block or rate-limit response rather than content?

    Deliberately conservative: a real posting can mention "access" or "unavailable" in
    passing, so a match in the BODY only counts when the body is also too short to be a
    posting. A bare status code as the whole title is decisive on its own.
    """
    title_text = text_of(title).strip()
    if _ERROR_PAGE_TITLE.match(title_text):
        return True
    body = text_of(text)
    if len(body) < 1200 and _ERROR_PAGE_TEXT.search(body):
        return True
    if len(body) < 1200 and _ERROR_PAGE_TEXT.search(title_text):
        return True
    return False
