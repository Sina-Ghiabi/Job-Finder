"""Per-site search-URL builders for the direct and browser-only searches."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

from .text import (_qs)
from .search_title import DEFAULT_SEARCH_TITLE, field_form, role_form, title_forms
from .geo import (
    COUNTRY_ISO2,
    _WEAREDEVELOPERS_CITY_SLUGS,
    _WEAREDEVELOPERS_COUNTRY_SLUGS,
)


# ---------------------------------------------------------------------------
# Direct site search URLs -- bypassing Google's location text-matching entirely
# ---------------------------------------------------------------------------
# Sina pushed back hard on relying purely on Google full-text matching for location:
# a page on a real job board might never literally contain the word "Oslo" (a
# genuinely relevant "Remote" listing usually doesn't name a city at all), and a real
# test with Jooble showed the opposite failure too -- Google can also be fooled into
# matching the WRONG place entirely (a US "Oslo, Minnesota" result for a Norway
# search). The fix: for domains where research found a real, structured location
# search mechanism (a URL parameter, path segment, or subdomain that the SITE ITSELF
# uses to filter results -- not just text Google happens to have indexed), build that
# URL directly and feed it straight to the crawler, instead of ever asking Google to
# guess. This is purely ADDITIVE to the existing Google-based known/global stages
# (which keep running unchanged) -- a real result from a direct URL just gets merged
# in alongside whatever Google already found, so this can only add coverage, never
# remove it.
#
# A full research pass covered all 55 COUNTRY_JOB_SITES domains + all 11
# GOOGLE_GLOBAL_EXTRA_SITES domains. Three categories were deliberately left OUT of
# `DIRECT_SEARCH_URL_BUILDERS` below, and still rely on Google exclusively:
# 1. **JSON-API-only mechanisms** (arbeitsagentur.de, arbetsformedlingen.se,
#    francetravail.fr) -- their confirmed real mechanism is a REST API returning JSON,
#    not an HTML page the website-content-crawler can extract <a href> links from.
#    Needs its own HTTP+JSON integration (a genuinely different, larger engineering
#    task -- francetravail.fr's API also requires registered API credentials Job Finder
#    doesn't have) -- left as a known future gap, not attempted here.
# 2. **No real mechanism found at all** -- confirmed via research (and, for several of
#    these, a further real Apify `playwright:adaptive` test against a guessed search URL
#    -- see "Real, live testing" in README.md) to be JS-rendered SPAs whose keyword
#    search never reflects in the URL at all (werk.nl, nationalevacaturebank.nl,
#    app.welcometothejungle.com, vdab.be, actiris.brussels, jobat.be, leforem.be,
#    karrierestart.no, jobnet.dk, empleate.gob.es), login-gated even for search
#    (adem.public.lu, and werk.nl's search also redirects through a real DigiD login),
#    form-only with a JS `href="#!"` click-handler instead of a real link (eluta.ca), or
#    a genuine "trap" the sites' own research explicitly warned against hand-constructing
#    (wellfound.com's own support docs say not to; aijobs.ai's city-looking path was
#    tested and confirmed to silently return country-wide results only).
#    work.turing.com and work.mercor.com were originally placed here too ("no browsable
#    listing at all") -- wrong, corrected once Sina actually opened both in his own
#    browser before logging in and found real search boxes and real results; see
#    MANUAL_ASSIST_GLOBAL_SITES, since they're a different failure mode (real search,
#    but role cards have no real `<a href>` for _deepen_google_results to use here).
#    sapoemprego.pt belongs here too, confirmed by a real A/B test: a nonsense
#    query returned the exact same generic "featured" listings as a real one -- its
#    keyword parameter is silently ignored, not just unconfirmed.
# 3. **No confirmed keyword-search parameter** -- net-empregos.com has a confirmed
#    *location* parameter, but no confirmed way to combine it with a role/keyword
#    search, so a direct URL couldn't be built with real confidence (its
#    /pesquisa-empregos.asp search page shows a login wall regardless of query params,
#    confirmed via a real fetch -- an old-style ASP form, likely POST-only); empleate.gob.es
#    and europa.eu (EURES) similarly lack a simple, confirmed URL scheme (province-only
#    SPA; country/NUTS-region codes needing a lookup table plus a JS-rendered detail
#    page, respectively). infojobs.net is NOT in this category despite looking like it at
#    first -- see _direct_url_infojobs_net below.
#
# Every URL below is built from research findings, but not every one was verified at
# the exact combination Job Finder actually needs (e.g. a confirmed city+keyword pattern
# on a *different* city, applied here to Oslo/Berlin/Vienna/Amsterdam/Copenhagen) --
# `_run_direct_site_searches` below checks whether each constructed URL actually
# yields real job links once crawled, and logs a yellow warning (in the same
# 3-step format as the other warnings) for any one that doesn't, so a wrong guess
# surfaces itself instead of failing silently.
# What a builder searches for when it is not handed a title -- the default title's role
# form. A real search always hands every builder the title Sina typed.
_DIRECT_ROLE_TERM = role_form(DEFAULT_SEARCH_TITLE)

# Every direct source -- the JSON APIs and the per-site search URLs above -- used to search
# for _DIRECT_ROLE_TERM and nothing else, while the Google phase has always searched four
# role terms. That one word was hiding most of the market.
#
# Measured on arbeitsagentur.de, whose API is free so the whole thing could be run four
# times and compared:
#
#     "Data Scientist"             376 listings   <- all the app was ever asking for
#     "Data Engineer"              924
#     "Machine Learning Engineer"  147
#     "AI Engineer"                508
#     ------------------------------------
#     unique across all four      1481 listings
#
# 1,105 real listings -- 75% of what that one source holds -- were invisible, in every
# country, from every direct API. The terms are the same four the Google phase uses, so
# the two halves of the search now ask the same question.
#
# THE TERMS THEMSELVES have since moved to DevOps and MLOps, but the shape of that
# measurement is why there are still exactly four of them. These sources are called once
# PER TERM, so a fifth term is a fifth call to every API and every one of the 28 sites; and
# one term is not enough, which is the whole finding above. The four below were chosen to
# overlap as little as possible -- "DevOps Engineer" and "Platform Engineer" are the same
# job under two names and a posting rarely carries both, so each one earns its call.
# Now the forms of ONE title rather than four hand-picked roles, since the field became the
# title Sina types. These are only the default's; run_search builds them from the title in
# the box (see terms_for_pass).
DIRECT_API_ROLE_TERMS = list(title_forms(DEFAULT_SEARCH_TITLE))

# ...and the same idea for the other two passes. These sources take one plain phrase, not a
# boolean query, so each pass sends a handful of phrases that each pair a kind word with a
# role word -- which is the only way to ask an API like arbeitsagentur.de for "an internship
# in data" rather than for every internship in Germany.
#
# German is over-represented on purpose and it is not a bias: arbeitsagentur.de and EURES are
# the two sources these terms mostly reach, both are German-language, and a German employer
# writes "Masterarbeit" and "Werkstudent", never "master thesis".
DIRECT_API_INTERNSHIP_TERMS = [
    'Praktikum %s' % role_form(DEFAULT_SEARCH_TITLE), 'Werkstudent %s' % role_form(DEFAULT_SEARCH_TITLE),
    '%s Internship' % role_form(DEFAULT_SEARCH_TITLE), 'Working Student %s' % role_form(DEFAULT_SEARCH_TITLE),
]

# The subject form of the title, because a thesis is about a subject: "Masterarbeit Data
# Engineering". These were nine hand-written data-science phrases until Sina put Thesis on
# the title too; they are kept out of the public repository.
DIRECT_API_THESIS_TERMS = [
    'Masterarbeit %s' % field_form(DEFAULT_SEARCH_TITLE),
    'Abschlussarbeit %s' % field_form(DEFAULT_SEARCH_TITLE),
    'Master Thesis %s' % field_form(DEFAULT_SEARCH_TITLE),
    'Thesis %s' % field_form(DEFAULT_SEARCH_TITLE),
]


def _fetch_every_role_term(fetch_one, terms=None) -> list:
    """Run one source's fetcher once per role term and return the union.

    Deduplicated on URL, because the terms overlap heavily -- a "Senior Data Scientist /
    ML Engineer" posting answers to three of them -- and a source that returned the same
    listing four times would inflate every count in the Log and make the real dedup step
    do work this can do for free.

    A term that fails does not take the others down with it: one source being briefly
    unhappy about one query should cost that query, not the whole source. If EVERY term
    fails the last error is raised, so a genuinely broken source still reports as broken.
    """
    seen: set = set()
    collected: list = []
    last_error: Exception | None = None
    any_ok = False
    for term in (terms or DIRECT_API_ROLE_TERMS):
        try:
            rows = fetch_one(term) or []
        except Exception as exc:
            last_error = exc
            continue
        any_ok = True
        for row in rows:
            key = row.get('url') or (row.get('title'), row.get('company'))
            if key in seen:
                continue
            seen.add(key)
            collected.append(row)
    if not any_ok and last_error is not None:
        raise last_error
    return collected


def _direct_url_finn_no(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    q = _qs(q=role_term, location='1.20001.20061' if (loc_type == 'city' and location == 'Oslo') else None)
    return f'https://www.finn.no/job/search?{q}'


def _direct_url_arbeidsplassen_nav_no(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    base = f'https://arbeidsplassen.nav.no/stillinger?{_qs(q=role_term)}'
    if loc_type == 'city' and location == 'Oslo':
        return base + '&municipals[]=OSLO.OSLO'
    return base


def _direct_url_jobindex_dk(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    city = 'koebenhavn' if (loc_type == 'city' and location == 'Copenhagen') else ''
    path = f'/jobsoegning/{city}' if city else '/jobsoegning'
    return f'https://www.jobindex.dk{path}?{_qs(q=role_term, lang="en")}'


def _direct_url_it_jobbank_dk(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    city = 'koebenhavn' if (loc_type == 'city' and location == 'Copenhagen') else ''
    path = f'/jobsoegning/{city}' if city else '/jobsoegning'
    return f'https://www.it-jobbank.dk{path}?{_qs(lang="en", q=role_term)}'


# jobly.fi has a confirmed job-URL pattern (see GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS
# above) but was missed when the rest of the builders were first written -- Finland
# has no defined city in CITIES, so this only ever needs the country-wide English path.
def _direct_url_jobly_fi(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.jobly.fi/en/jobs/{role_term.lower().replace(" ", "-")}'


# te-palvelut.fi's real successor. Its keyword search box looked JS-only at first --
# guessed params (haku=, keyword=, ammatti=) were all silently ignored, returning the
# same unfiltered ~11,700 results every time -- but Sina found the real one by hand:
# ?q=... . Confirmed via a real test: 16 genuine "Data Scientist" postings (Poolia IT,
# Terveystalo, etc.), matching exactly what Sina saw in his own browser. Finland has no
# defined city in CITIES, so this is country-wide only.
def _direct_url_tyomarkkinatori_fi(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat?{_qs(q=role_term)}'


def _direct_url_karriere_at(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    city = '/wien' if (loc_type == 'city' and location == 'Vienna') else ''
    return f'https://www.karriere.at/jobs/{role_term.lower().replace(" ", "-")}{city}'


def _direct_url_stepstone_at(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    city = '/in-wien' if (loc_type == 'city' and location == 'Vienna') else ''
    return f'https://www.stepstone.at/jobs/{role_term.lower().replace(" ", "-")}{city}'


def _direct_url_stepstone_de(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    city = '/in-berlin' if (loc_type == 'city' and location == 'Berlin') else ''
    return f'https://www.stepstone.de/jobs/{role_term.lower().replace(" ", "-")}{city}'


def _direct_url_xing_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    if loc_type == 'city' and location == 'Berlin':
        return f'https://www.xing.com/jobs/search?{_qs(keywords=role_term, location="Berlin", radius=20)}'
    return f'https://www.xing.com/jobs/search?{_qs(keywords=role_term)}'


def _direct_url_iamexpat_de(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    city = '/berlin' if (loc_type == 'city' and location == 'Berlin') else ''
    return f'https://www.iamexpat.de/career/jobs-germany{city}'


def _direct_url_iamexpat_nl(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    city = '/amsterdam' if (loc_type == 'city' and location == 'Amsterdam') else ''
    return f'https://www.iamexpat.nl/career/jobs-netherlands{city}'


def _direct_url_moovijob_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return 'https://en.moovijob.com/job-offers/jobs-luxembourg'


def _direct_url_swissdevjobs_ch(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    # A real live test found /jobs/all (guessed as a "whole of Switzerland" fallback)
    # returns a genuine 403 -- confirmed via a plain WebFetch too, so it's not an Apify-
    # specific block, the URL itself just doesn't exist. The only confirmed pattern is
    # /jobs/{category}/{city} for a SPECIFIC city (Zurich, Geneva were the confirmed
    # examples), and Switzerland has no defined city in CITIES, so there's no safe
    # single-city substitute that wouldn't silently exclude the rest of the country.
    # Returning None here means Switzerland's country-wide search just stays on the
    # Google-only path for this domain, same as any other domain with no confirmed
    # country-wide URL.
    return None


def _direct_url_itjobs_pt(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.itjobs.pt/emprego?{_qs(q=role_term)}'


def _direct_url_tecnoempleo_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.tecnoempleo.com/ofertas-trabajo/?{_qs(te=role_term)}'


# Previously categorized as "confirmed location parameter, no confirmed keyword combo"
# -- but Spain has no defined city in CITIES anyway, so a location parameter was never
# actually useful here. What matters is a plain keyword search, and a real fetch found
# one: /ofertas-trabajo/{role-slug} showed 16 genuine "Data Scientist" postings in Spain
# (PEPPER, Sopra Steria, TRS Staffing, etc.), matching the already-confirmed
# GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS entry (/**/of-i**).
def _direct_url_infojobs_net(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.infojobs.net/ofertas-trabajo/{role_term.lower().replace(" ", "-")}'


def _direct_url_apec_fr(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    # A real live test found this URL (motsCles= alone, no lieux= region param)
    # redirects to apec.fr's LOGIN page instead of showing search results -- research
    # only confirmed the `lieux=` param at region level (711 = Île-de-France), never a
    # working param-free "whole of France" search, so this was a guess that turned out
    # wrong. France already has strong coverage via hellowork.com (confirmed working)
    # and francetravail.fr (API-only, not attempted) -- returning None here leaves
    # apec.fr on the Google-only path rather than risk hitting the login wall again.
    return None


def _direct_url_hellowork_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.hellowork.com/fr-fr/emploi/recherche.html?{_qs(k=role_term)}'


def _direct_url_reed_co_uk(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.reed.co.uk/jobs/{role_term.lower().replace(" ", "-")}-jobs'


def _direct_url_totaljobs_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.totaljobs.com/jobs/{role_term.lower().replace(" ", "-")}'


def _direct_url_cv_library_co_uk(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.cv-library.co.uk/{role_term.lower().replace(" ", "-")}-jobs'


def _direct_url_cwjobs_co_uk(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.cwjobs.co.uk/jobs/{role_term.lower().replace(" ", "-")}'


def _direct_url_wearedevelopers_com(location, loc_type, country, role_term=_DIRECT_ROLE_TERM):
    if loc_type == 'city' and location in _WEAREDEVELOPERS_CITY_SLUGS:
        country_slug = _WEAREDEVELOPERS_COUNTRY_SLUGS.get(country)
        if country_slug:
            return f'https://www.wearedevelopers.com/jobs/l/{country_slug}/{_WEAREDEVELOPERS_CITY_SLUGS[location]}'
    country_slug = _WEAREDEVELOPERS_COUNTRY_SLUGS.get(country)
    if not country_slug:
        return None
    return f'https://www.wearedevelopers.com/jobs/l/{country_slug}'


def _direct_url_dice_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.dice.com/jobs?{_qs(q=role_term)}'


def _direct_url_ziprecruiter_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.ziprecruiter.com/jobs-search?{_qs(search=role_term)}'


def _direct_url_jobbank_gc_ca(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://www.jobbank.gc.ca/jobsearch/jobsearch?{_qs(searchstring=role_term)}'


# seek.com.au has no direct-search builder -- a real live test found it returns
# `Received blocked status code: 403` on nearly every individual job page it
# discovers, triggering Crawlee's automatic session-rotation retry dance (several
# attempts per link) on each one. With dozens of job links found from one listing
# page, this compounded into 26+ minutes of wasted retries for only 3 real postings,
# and appeared to starve other domains sharing the same batched run of their own
# time/resource budget (a `careerone.com.au` request failed outright in the same
# batch, despite a plain fetch to that exact URL working fine in isolation). Not
# worth the wait, and it was already confirmed bot-blocked in the original site
# research pass -- also removed from GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS below so
# _deepen_google_results doesn't risk the same retry storm whenever seek.com.au shows
# up in a regular Google result. Stays on the Google-only path (without deep-crawl).


# careerone.com.au has no direct-search builder -- an isolated real live test (no
# other domains competing in the batch) still found `Received blocked status code:
# 403` on every single individual job page discovered, same failure pattern as
# seek.com.au, confirming this is careerone.com.au's own bot-blocking, not resource
# contention from sharing a batch with seek.com.au. The listing page itself loads
# fine, but the whole point of this feature is reaching individual postings. Also
# removed from GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS below for the same reason
# documented for seek.com.au. Stays on the Google-only path (without deep-crawl).


def _direct_url_jora_com(location, loc_type, role_term=_DIRECT_ROLE_TERM):
    return f'https://au.jora.com/j?{_qs(q=role_term)}'


# jooble.org was deliberately EXCLUDED from direct search, despite being the original
# site that started this whole feature -- a real live test (multiple attempts, 30s and
# 45s timeouts, both playwright:adaptive and playwright:chrome crawler types) found
# Apify's crawler infrastructure gets an explicit `Received blocked status code: 403`
# from jooble.org every single time, even after Apify's own built-in anti-blocking
# proxy rotation and "UNBLOCKER proxy group" retry. This is jooble.org actively
# blocking Apify's datacenter IPs specifically (the exact same real subdomain URL
# loads fine via a plain browser-like fetch) -- not fixable by adjusting the URL,
# timeout, or crawler engine. Left on the Google-only path, same reasoning as
# duunitori.fi (see its exclusion note above DIRECT_SEARCH_URL_BUILDERS).


# arc.dev's country pages are confirmed at /en-{iso2}/remote-jobs -- no city-level page
# exists (remote listings rarely name an exact city), so a city search just reuses its
# parent country's page.
def _direct_url_arc_dev(location, loc_type, country, role_term=_DIRECT_ROLE_TERM):
    iso2 = COUNTRY_ISO2.get(country)
    if not iso2:
        return None
    return f'https://arc.dev/en-{iso2}/remote-jobs'


# Domains needing the extra `country` argument (global sites, or a country-specific
# site whose city-vs-country URL structure isn't just "same domain, different path").
_DIRECT_URL_BUILDERS_WITH_COUNTRY = {
    'wearedevelopers.com': _direct_url_wearedevelopers_com,
    'arc.dev': _direct_url_arc_dev,
}


# Everything else: builder(location, loc_type) -> str | None, no country needed because
# the domain only ever applies to its own one COUNTRY_JOB_SITES country anyway.
DIRECT_SEARCH_URL_BUILDERS = {
    'finn.no': _direct_url_finn_no,
    'arbeidsplassen.nav.no': _direct_url_arbeidsplassen_nav_no,
    'jobindex.dk': _direct_url_jobindex_dk,
    'it-jobbank.dk': _direct_url_it_jobbank_dk,
    'jobly.fi': _direct_url_jobly_fi,
    'tyomarkkinatori.fi': _direct_url_tyomarkkinatori_fi,
    # duunitori.fi deliberately excluded -- a real test found Apify's crawler infra
    # (both playwright:adaptive AND cheerio/plain-HTTP modes) gets zero content back
    # from it entirely, including the start URL itself, while a plain WebFetch to the
    # exact same URL succeeds fine with real content. This points to the site blocking
    # Apify's own infrastructure specifically (e.g. datacenter IP blocking), not
    # anything fixable via a different URL or crawler setting -- stays on the
    # Google-only path, which already worked before this feature existed.
    'karriere.at': _direct_url_karriere_at,
    'stepstone.at': _direct_url_stepstone_at,
    'stepstone.de': _direct_url_stepstone_de,
    'xing.com': _direct_url_xing_com,
    'iamexpat.de': _direct_url_iamexpat_de,
    'iamexpat.nl': _direct_url_iamexpat_nl,
    'moovijob.com': _direct_url_moovijob_com,
    # jobs.ch and jobup.ch removed -- see the note above GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS.
    'swissdevjobs.ch': _direct_url_swissdevjobs_ch,
    'itjobs.pt': _direct_url_itjobs_pt,
    'tecnoempleo.com': _direct_url_tecnoempleo_com,
    'infojobs.net': _direct_url_infojobs_net,
    'apec.fr': _direct_url_apec_fr,
    'hellowork.com': _direct_url_hellowork_com,
    'reed.co.uk': _direct_url_reed_co_uk,
    'totaljobs.com': _direct_url_totaljobs_com,
    'cv-library.co.uk': _direct_url_cv_library_co_uk,
    'cwjobs.co.uk': _direct_url_cwjobs_co_uk,
    'dice.com': _direct_url_dice_com,
    'ziprecruiter.com': _direct_url_ziprecruiter_com,
    'jobbank.gc.ca': _direct_url_jobbank_gc_ca,
    'jora.com': _direct_url_jora_com,
}


def _direct_search_overrides_path():
    from app import storage
    return storage.DATA_DIR / 'direct_search_overrides.json'


# Memo for _load_direct_search_overrides, keyed on the overrides file's (mtime, size).
# This used to live as an attribute ON THE FUNCTION OBJECT
# (_load_direct_search_overrides._cache = ...). That works, but a function growing
# attributes at runtime is invisible to every tool and surprising to read. A plain
# module-level dict is the same cache, stated openly.
_DIRECT_SEARCH_OVERRIDES_CACHE: dict = {}

# Same shape, for the job-posting patterns discovered automatically.
_DISCOVERED_PATTERNS_CACHE: dict = {}


def _load_direct_search_overrides() -> dict:
    """{domain: {'template': '...{KEYWORD}...', 'added_at': iso}} -- domains Sina fixed
    live via the broken-URLs dialog: he pasted a real search-result URL, Claude
    resolved it into a reusable template (see _resolve_url_template_with_claude), and a
    real Apify test crawl confirmed it's reachable, before it ever got saved here.

    Memoized on the file's mtime+size. _build_direct_search_url falls through to this
    for every domain with no builder, once per (domain, location) pair -- measured at
    217 real open()+json.loads() calls of the same unchanging file for a single
    18-country search. The cache key means a live fix saved mid-run
    (_save_direct_search_override) is still picked up immediately."""
    from .jsonstore import load_cached_json
    return load_cached_json(_direct_search_overrides_path(),
                            _DIRECT_SEARCH_OVERRIDES_CACHE)


def _save_direct_search_override(domain: str, template: str) -> None:
    import json
    overrides = _load_direct_search_overrides()
    overrides[domain] = {'template': template, 'added_at': datetime.now(timezone.utc).isoformat()}
    try:
        path = _direct_search_overrides_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass  # best-effort -- a failed save just means this fix doesn't persist, not a crash


def _discovered_job_patterns_path():
    """Where automatically-discovered job-URL patterns are kept.

    Separate file from the direct-search overrides: those are SEARCH urls (how to ask a
    site for results), these are POSTING url shapes (how to recognise one result). They
    are discovered by different machinery and are useful independently.
    """
    from app import storage
    return storage.DATA_DIR / 'discovered_job_patterns.json'


def load_discovered_job_patterns() -> dict:
    """{domain: {'globs': [...], 'added_at': iso}} -- patterns the app worked out itself.

    Memoized on the file's mtime+size, same as the direct-search overrides, so a pattern
    discovered mid-run is picked up immediately by the rest of that run.
    """
    from .jsonstore import load_cached_json
    return load_cached_json(_discovered_job_patterns_path(),
                            _DISCOVERED_PATTERNS_CACHE, _drop_stale_patterns)


def _drop_stale_patterns(patterns: dict) -> dict:
    """Forget patterns approved by an older, looser verifier.

    Tightening the acceptance rules has to reach patterns already on disk, or the bad ones
    keep being used forever. Three real examples were saved before the article/category
    checks existed -- a hiring guide and two category pages -- and every later search would
    have collected from them.

    Dropping rather than re-verifying on the spot: re-verification needs network calls, and
    this runs on every load. A dropped domain is simply unknown again, so the next search
    re-learns it under the current rules, which is the correct outcome and costs nothing
    but a few HTTP requests once.
    """
    from .pattern_discovery import VERIFIER_VERSION
    kept = {}
    for domain, entry in (patterns or {}).items():
        if not isinstance(entry, dict):
            continue
        if (entry.get('verifier_version') or 0) < VERIFIER_VERSION:
            continue
        kept[domain] = entry
    return kept


def save_discovered_job_pattern(domain: str, globs: list) -> None:
    """Remember a verified pattern so no later search has to work it out again."""
    import json
    from datetime import datetime, timezone
    patterns = dict(load_discovered_job_patterns())
    from .pattern_discovery import VERIFIER_VERSION
    patterns[domain] = {'globs': list(globs),
                        'added_at': datetime.now(timezone.utc).isoformat(),
                        # Which acceptance rules approved this. A pattern saved under an
                        # older, looser verifier is re-checked rather than trusted.
                        'verifier_version': VERIFIER_VERSION}
    try:
        path = _discovered_job_patterns_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(patterns, indent=2, ensure_ascii=False), encoding='utf-8')
        _DISCOVERED_PATTERNS_CACHE.pop('value', None)
    except Exception:
        pass  # best-effort: a failed save costs a re-discovery, never a crash


def _build_direct_search_url(domain: str, location: str, loc_type: str, country: str | None,
                             role_term: str = _DIRECT_ROLE_TERM) -> str | None:
    """The site's own search URL for one role term.

    `role_term` defaults to the original single term, so every existing caller keeps the
    exact URL it had -- verified by building all 63 URLs before and after this parameter
    existed and comparing them.
    """
    if domain in _DIRECT_URL_BUILDERS_WITH_COUNTRY:
        return _DIRECT_URL_BUILDERS_WITH_COUNTRY[domain](location, loc_type, country,
                                                         role_term)
    builder = DIRECT_SEARCH_URL_BUILDERS.get(domain)
    if builder:
        return builder(location, loc_type, role_term)
    # Fallback: a Claude-resolved, Apify-verified template Sina saved live via the
    # broken-URLs dialog -- country-wide only (the template has no location slot, since
    # Claude was deliberately told not to guess one), but still real and automatic from
    # here on, instead of falling all the way back to Google-only coverage.
    override = _load_direct_search_overrides().get(domain)
    if override and override.get('template'):
        return override['template'].replace('{KEYWORD}', quote_plus(role_term))
    return None


# ---------------------------------------------------------------------------
# Sites Apify's crawler infrastructure cannot read -- bot-blocked, consent-gated, or
# JS-only search with no URL parameter. They were originally collected for a stage that
# opened a real, visible Chrome window so Sina could clear the block himself; the fetch
# ladder now does that part automatically (Chrome's TLS fingerprint, a crawler identity,
# then a headless browser that runs the page's JavaScript and clicks its consent button),
# so the stage runs unattended. See search/browser_sites.py.
#
# The tables themselves are the real work and survived that change intact: each entry is a
# verified search URL and, where one exists, a verified prefix for the site's individual
# job links.
#
# jooble.org was left out here entirely, and re-tried once via MANUAL_ASSIST_GLOBAL_SITES
# below (its country-subdomain trap seemed solvable once a human is actually watching
# every result) -- but real testing found a different, worse problem: jooble.org's own
# Cloudflare bot-check blocks Playwright's browser session itself, before any human
# could even see a captcha to solve. See the comment on its removed entry below for what
# was tried.

def _manual_assist_url_nationalevacaturebank(cities):
    # Confirmed real via a live test: the path lands on DPG Media's cookie-consent gate
    # first (same as the country-wide URL), but the gate's own callbackUrl parameter
    # shows it redirects right back to this exact /vacatures/amsterdam path once cleared
    # -- the headless browser's consent-dismissal clears that gate either way.
    if 'Amsterdam' in cities:
        return 'https://www.nationalevacaturebank.nl/vacatures/amsterdam'
    return f'https://www.nationalevacaturebank.nl/vacatures?{_qs(query=_DIRECT_ROLE_TERM)}'


def _manual_assist_url_karrierestart(cities):
    # /jobb/oslo confirmed real via a live test -- the page's own "Du har søkt:
    # Arbeidssted: Oslo" filter chip shows it's a genuine location filter, not a guess.
    # Its keyword search is still JS-only (see the unresolved-sites pass), so this only
    # reaches the right city; the role cannot be put in the URL for this site.
    if 'Oslo' in cities:
        return 'https://karrierestart.no/jobb/oslo'
    return 'https://www.karrierestart.no/jobb'


MANUAL_ASSIST_SITES = {
    'duunitori.fi': {
        'country': 'Finland',
        'url': lambda cities: f'https://duunitori.fi/tyopaikat?{_qs(haku=_DIRECT_ROLE_TERM)}',
        'job_link_glob': 'https://duunitori.fi/tyopaikat/tyo/',
    },
    'seek.com.au': {
        'country': 'Australia',
        'url': lambda cities: f'https://www.seek.com.au/{_DIRECT_ROLE_TERM.lower().replace(" ", "-")}-jobs',
        'job_link_glob': 'https://www.seek.com.au/job/',
    },
    'careerone.com.au': {
        'country': 'Australia',
        'url': lambda cities: f'https://www.careerone.com.au/jobs?{_qs(q=_DIRECT_ROLE_TERM)}',
        'job_link_glob': None,
    },
    'nationalevacaturebank.nl': {
        'country': 'Netherlands',
        'url': _manual_assist_url_nationalevacaturebank,
        'job_link_glob': 'https://www.nationalevacaturebank.nl/vacature/',
    },
    'werk.nl': {
        # No confirmed city-path/param found for Amsterdam (unlike the two above) --
        # not guessed blindly. Sina is present anyway and can type "Amsterdam" into
        # werk.nl's own location field himself once he's past the DigiD login wall.
        'country': 'Netherlands',
        'url': lambda cities: 'https://www.werk.nl/nl/vacatures',
        'job_link_glob': None,
    },
    'adem.public.lu': {
        'country': 'Luxembourg',
        'url': lambda cities: 'https://jobboard.adem.lu/login',
        'job_link_glob': None,
    },
    'vdab.be': {
        'country': 'Belgium',
        'url': lambda cities: f'https://www.vdab.be/vindeenjob/vacatures?{_qs(trefwoorden=_DIRECT_ROLE_TERM)}',
        'job_link_glob': 'https://www.vdab.be/vindeenjob/vacatures/',
    },
    'actiris.brussels': {
        'country': 'Belgium',
        'url': lambda cities: f'https://www.actiris.brussels/fr/citoyens/offres-d-emploi/?{_qs(keyword=_DIRECT_ROLE_TERM, localisation="Tout", page=1, keywordSearchType="Partout")}',
        'job_link_glob': 'https://www.actiris.brussels/fr/citoyens/detail-offre-d-emploi/',
    },
    'jobat.be': {
        'country': 'Belgium',
        'url': lambda cities: f'https://www.jobat.be/nl/jobs?{_qs(keywords=_DIRECT_ROLE_TERM)}',
        'job_link_glob': None,
    },
    'leforem.be': {
        'country': 'Belgium',
        'url': lambda cities: 'https://www.leforem.be/recherche-offres/resultat-recherche-offre',
        'job_link_glob': None,
    },
    'karrierestart.no': {
        'country': 'Norway',
        'url': _manual_assist_url_karrierestart,
        'job_link_glob': None,
    },
}


# Global, not tied to any one country -- these run on every search where the browser-site
# is enabled at all, regardless of which countries/cities are selected, since both are
# remote-work platforms with no country scoping of their own. Sina found both of these
# himself, in his own browser before logging in -- a real screenshot each time, after an
# earlier research pass had wrongly concluded neither had a public listing at all.
MANUAL_ASSIST_GLOBAL_SITES = {
    'work.turing.com': {
        # Confirmed real via a live test: ?search= genuinely filters (13 results for
        # "Data Scientist" vs. 257 unfiltered). No job_link_glob because role cards
        # aren't real <a href> links at all (0 matches in the raw HTML) -- they're
        # JS-only click targets, same shape as eluta.ca's href="#!" trap. Falls back to
        # capturing the filtered listing page itself as one row, same as every other
        # "no confirmed link pattern" site in this dict.
        'url': lambda cities: f'https://work.turing.com/jobs?{_qs(search=_DIRECT_ROLE_TERM)}',
        'job_link_glob': None,
    },
    'work.mercor.com': {
        # Also confirmed real via Sina's own browser (a "Data scientist" search showing
        # genuine project-based opportunities), but /explore's search box is entirely
        # client-side -- the URL stays exactly /explore regardless of query, confirmed
        # when Sina sent back the URL after searching. He types the search himself once
        # the browser opens, same as the JS-only country-scoped sites above.
        'url': lambda cities: 'https://work.mercor.com/explore',
        'job_link_glob': None,
    },
    'weworkremotely.com': {
        # Re-tested with headless=False (exactly what this feature always uses) instead
        # of the headless=True used in the original research pass -- the Cloudflare
        # bot-challenge that blocked the headless fetch never appeared for this initial
        # page load: real content loaded first try (786KB HTML, real title), with
        # genuine "Data Scientist" postings visible right on the listing page itself
        # (e.g. "Proxify AB - Senior Data Scientist", "Toptal - Data Scientist for Top
        # Cosmetic Firm"). job_link_glob is deliberately None even though the individual
        # job links are real and confirmed (/remote-jobs/{slug}) -- a real test found
        # visiting them via further automated page.goto() calls (no human involved in
        # between) DOES hit the Cloudflare wall ("Just a moment..."), even though the
        # first, human-initiated page load didn't. Only the listing page itself is safe
        # to fetch automatically; the titles/descriptions on it are enough on their own,
        # same honest "capture the page" fallback as every other no-glob site here.
        'url': lambda cities: f'https://weworkremotely.com/remote-jobs/search?{_qs(term=_DIRECT_ROLE_TERM)}',
        'job_link_glob': None,
    },
    # jooble.org was tried here too (both the global domain and a country subdomain),
    # but removed again after a real test: it hits a Cloudflare "Performing security
    # verification" wall that never resolves, even after 12+ real seconds, even with a
    # fully visible (headless=False) browser, and even after masking the obvious
    # automation fingerprints (navigator.webdriver, --disable-blink-features=
    # AutomationControlled, a persistent real-Chrome-profile context instead of a fresh
    # one). Unlike weworkremotely.com's block (which was purely headless-detection and
    # went away with a visible browser), this one appears to key off something deeper in
    # Playwright's CDP connection itself -- Sina, sitting right there watching, would
    # never even get a captcha to click; the page just never leaves "verifying." Left
    # out entirely rather than ship a browser-site entry that quietly never works.
}


_MANUAL_ASSIST_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def _extract_manual_assist_job_links(html_content: str, page_url: str, glob_prefix: str, limit: int = 20) -> list[str]:
    from urllib.parse import urljoin
    seen = []
    for href in _MANUAL_ASSIST_HREF_RE.findall(html_content):
        absolute = urljoin(page_url, href)
        if absolute.startswith(glob_prefix) and absolute not in seen:
            seen.append(absolute)
        if len(seen) >= limit:
            break
    return seen


# How much of a manually-opened page's raw body text is kept as a listing's
# description -- named (matching this file's own convention elsewhere, e.g.
# MAX_TRANSLATE_CHARS) rather than left as a bare repeated literal.
_MANUAL_ASSIST_DESCRIPTION_MAX_CHARS = 6000
