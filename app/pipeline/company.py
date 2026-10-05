"""Working out a listing's real employer name."""
from __future__ import annotations

import re

from .rules import (_normalize_text)


# Legal-entity suffix words stripped before comparing two company names -- a job ad and
# an official register routinely spell the same company differently ("Booking.com" vs
# "Booking.com B.V."). Sina explicitly flagged this: a small naming difference must
# never cause a real match to be missed.
_LEGAL_SUFFIX_WORDS = {
    'bv', 'nv', 'bvba', 'holding', 'holdings', 'group', 'groep', 'gmbh', 'ag',
    'ltd', 'limited', 'llc', 'inc', 'incorporated', 'corp', 'corporation', 'co',
    'plc', 'sarl', 'sa', 'spa', 'srl', 'oy', 'ab', 'as', 'aps',
}


def _normalize_company_name(name: str) -> str:
    """Lowercases, strips punctuation, and drops legal-entity suffix words, so
    'Booking.com B.V.' and 'Booking.com' (or 'BOOKING COM') compare equal even before
    any fuzzy matching is needed."""
    name = (name or '').lower()
    # Periods and slashes are removed WITHOUT inserting a space first, so a
    # punctuated suffix collapses into one token matching _LEGAL_SUFFIX_WORDS ('B.V.'
    # -> 'bv', 'A/S' -> 'as', 'ApS' already has none) instead of leaving stray
    # single-letter fragments ('b', 'v' / 'a', 's') that the word-filter below can
    # never recognise as a suffix and so never actually strips.
    name = name.replace('.', '').replace('/', '')
    name = re.sub(r'[^\w\s]', ' ', name)
    words = [w for w in name.split() if w not in _LEGAL_SUFFIX_WORDS]
    return ' '.join(words).strip()


# Hard ceiling on billed, web-search-backed company legal-name lookups per Filter run.
# Each one is a real, separately-charged Claude web search; a first Filter run over a
# large UK/US dataset could otherwise fire hundreds of them with no warning and no way
# to stop it. Every resolved name is cached permanently, so a run that hits this ceiling
# simply picks up where it left off next time -- coverage is only delayed, never lost.
_MAX_LEGAL_NAME_LOOKUPS_PER_RUN = 25


_COMPANY_LEGAL_NAME_ANSWER_PATTERN = re.compile(r'ANSWER:\s*(.+)', re.IGNORECASE)


# Company legal-name resolution -- previously ran INSIDE claude_screen_one (a second,
# addendum-driven task tacked onto the same KEEP/DROP/MATCH call), with zero dedup: a
# company posting 5 listings triggered 5 separate real, billed web searches for the
# exact same legal name, every single Filter run. Now it's a fully separate,
# dedicated call (_resolve_company_legal_name below), invoked at most ONCE per unique
# (country, normalized company name) EVER, cached to disk with no expiry (see
# _load_company_legal_name_cache/_save_company_legal_name_cache) and checked BEFORE
# ever considering a real API call -- see _apply_sponsor_list_matches_to_jobs, which is
# now the single place this whole feature lives.
_COMPANY_LEGAL_NAME_SYSTEM_PROMPT = """You resolve a company's exact, officially registered legal entity name in a specific country, for a job-search sponsorship-visa cross-reference tool.

Use your web search tool to find the company's exact, officially registered legal entity name in the given country -- the name it's registered under with the relevant national business/chamber-of-commerce register (for example, including its real legal suffix, such as B.V., N.V., Ltd., or GmbH). If the given company name is already the correct full legal name, just confirm it as-is. If you cannot find a confident, verifiable answer after searching, answer UNKNOWN instead -- never guess or fabricate a legal suffix.

Respond with ONLY one line, nothing else:
ANSWER: <the resolved legal company name, or UNKNOWN>"""


def _company_legal_name_cache_path():
    from app import storage
    return storage.DATA_DIR / 'company_legal_names.json'


def _load_company_legal_name_cache() -> dict:
    """{country: {normalized_company: legal_name_or_null}}, no expiry -- a company's
    officially registered legal name essentially never changes, unlike the sponsor
    lists themselves (which DO refresh periodically, see _SPONSOR_LIST_CACHE_MAX_AGE_DAYS).
    Never raises -- a missing/corrupt cache file just means starting fresh, not
    breaking Filter."""
    import json
    path = _company_legal_name_cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_company_legal_name_cache(cache: dict) -> None:
    import json
    path = _company_legal_name_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass  # cache write is best-effort -- the freshly-resolved names are still used this run


# Company Popularity (formerly here: a per-unique-company Claude web-search call,
# 'Startup'/'Unknown'/'Known'/'Well Known'/'Famous') was removed entirely -- Sina asked
# for it gone since it was the single biggest remaining recurring Claude cost (one
# real, separately-billed web-search call per unique company on every Filter run) and,
# in real use, mostly just returned 'Unknown' anyway (traced to two real causes:
# Google-sourced listings frequently have no extractable company name at all, and the
# regex-based extractor -- see _extract_company_from_text below -- occasionally
# extracted the wrong text, e.g. a job title instead of a company, guaranteeing
# 'Unknown'). Its one genuinely free signal (google_stage == 'startup', already known
# with no Claude call) was kept and repurposed into the Type badge instead -- see
# display_category() above.


# The regex company GUESS that used to live here is gone. It existed for exactly one
# reason -- give a Google-sourced row something for the old dedup to group by -- and
# that dedup is gone too: _remove_duplicates_list now compares the listings' own text,
# so it never needs a company name at all.
#
# Removing it was not just tidying. The guess was documented to return a job title
# instead of an employer ("Data Science Expert" out of "Data Science Expert - Mercor
# Jobs"), and once nothing needed it, every remaining effect it had was harmful: it fed
# dedup_title_key a "company" that was part of the real job title, it made a nameless
# row look named so the Claude employer step skipped it, and it handed that invented
# name to a government sponsor-register match.
#
# A company name is now wanted for one thing only -- that register match -- and it is
# read by claude_name_employer_one, after the filters have run, from the listings that
# survived, quoting the words in the posting that name the employer.


def _strip_company_from_title(title: str | None, normalized_company: str) -> str:
    """Removes an (already-normalized) company name from a title, ONLY for
    near-duplicate similarity comparison in _remove_duplicates_list below -- never for
    display. A title like 'Acme Corp - Data Scientist' otherwise compares poorly
    against a clean 'Data Scientist' from another source, even though they're the same
    posting -- exactly the case a Google-sourced row hits once _fill_missing_company_
    names has extracted its company from that same title text. Safe precisely because
    titles are only ever compared WITHIN one already-matched (company, country) group
    -- stripping a company name here can never make two DIFFERENT companies' listings
    look alike, since they're never compared against each other in the first place."""
    normalized_title = _normalize_text(title)
    if normalized_company and normalized_company in normalized_title:
        stripped = normalized_title.replace(normalized_company, ' ')
        return re.sub(r'\s+', ' ', stripped).strip()
    return normalized_title
