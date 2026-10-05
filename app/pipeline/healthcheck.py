"""Everything that can be verified without spending a penny, on demand.

The test suite proves the code is right. It cannot prove the fifty websites this app reads
are still the sites it was written against -- a job board can change its HTML, move its
domain, add a bot wall or shut down entirely, and every test stays green while the search
quietly returns less. That is the failure mode this app actually has, and no amount of
testing addresses it.

So this is the other half: a check Sina can run whenever he likes, before committing money
to a search, that asks reality instead of asking the code. It costs nothing -- no Apify
actor, no Jooble request (that key has a 500-LIFETIME cap and a health check must never be
what drains it) -- and covers:

    the data files          jobs.json and friends are readable and the right shape
    the fetch ladder        every rung's library is actually present in this build
    Apify                   the token works and the Google actor is reachable (a .get())
    the direct APIs         one minimal real call each, except Jooble (config only)
    the direct-search URLs  every site RoleHound searches by URL still opens
    the browser-only sites  every site that needs the ladder still opens
    the job-URL patterns    each saved pattern still matches real links on its own site

Problems come back in exactly the shape the pre-flight check produces, so they reach the
same window, with the same plain-language fix advice written by Claude.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from . import fetcher
from .errors import SearchCancelled
from .google import all_job_url_patterns
from .pattern_discovery import _glob_match
from .preflight import _preflight_check_api_sources, _preflight_check_google
from .sources_urls import MANUAL_ASSIST_GLOBAL_SITES, MANUAL_ASSIST_SITES

# Sites are checked concurrently. Eight matches the pre-flight checks and enrichment: fast
# enough that a full sweep is a minute rather than ten, low enough that no single site sees
# anything resembling a burst.
HEALTH_MAX_WORKERS = 8

# A pattern is confirmed by finding real links on the site that still match it. One is
# enough to prove the shape is alive; demanding more would fail a quiet day rather than a
# broken pattern.
HEALTH_MIN_PATTERN_MATCHES = 1


def _problem(name, reason, url=None, kind='url'):
    return {'name': name, 'reason': reason, 'fixable': False, 'kind': kind, 'url': url}


# --------------------------------------------------------------------------------------
# the individual checks
# --------------------------------------------------------------------------------------
def _check_storage() -> list[dict]:
    """The data files. A damaged one reads as empty, which looks like an empty app."""
    from app import storage
    storage.take_load_problems()          # discard anything already reported elsewhere
    storage.load_settings()
    storage.load_jobs()
    storage.load_applications()
    return [_problem('Saved data', text, kind='data')
            for text in storage.take_load_problems()]


def _check_ladder() -> list[dict]:
    """The fetch ladder's rungs. A missing library is the one failure that would otherwise
    be completely silent: every blocked site fails, and nothing says why."""
    problems = []
    for module, rungs, cost in (
        ('curl_cffi', 'the browser-fingerprint and search-engine routes',
         'Sites that answer 403 to a plain request can no longer be opened.'),
        ('playwright.sync_api', 'the full-browser route',
         'Sites that build their job list in JavaScript can no longer be read.'),
    ):
        try:
            import importlib
            importlib.import_module(module)
        except Exception as e:
            problems.append(_problem(
                'Fetch ladder — %s' % module,
                '%s could not be loaded (%s), so %s are unavailable. %s This is a RoleHound '
                'packaging problem, not a website problem.' % (module, e, rungs, cost),
                kind='app'))
    return problems


# A site is checked the way the SEARCH reaches it, which is not the same for every site.
#
# The browser-only sites really are opened by this machine's fetch ladder, so a failure
# here is a failure there. The direct-site searches are not: they go through Apify's
# crawler, on Apify's own infrastructure and IPs. Testing those with the local ladder
# answers a question nobody asked -- stepstone.at and stepstone.de both refuse this machine
# on all four rungs while the search reaches them perfectly well through Apify, and
# reporting that as broken would be the third kind of false alarm this check has produced.
#
# So for an Apify-reached site only transport-independent failures count: a domain that
# does not resolve, or a URL that is gone, is gone for Apify too. A 403 is not.
VIA_LADDER = 'ladder'
VIA_APIFY = 'apify'

_GONE_STATUSES = (404, 410)

class _Unverified:
    """Distinct from both a pass and a failure: the check could not be carried out.

    A real object rather than a magic string, so a caller comparing against it cannot
    silently pass a plain 'unverified' through and have it treated as a problem dict.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return 'UNVERIFIED'


UNVERIFIED = _Unverified()


def _check_one_url(name: str, url: str, via: str) -> dict | None:
    """One site, judged by how the search actually reaches it."""
    result = fetcher.fetch(url, needs_links=True, allow_browser=(via == VIA_LADDER))
    if result.accepted:
        return None

    if via == VIA_APIFY:
        if result.status is None:
            return _problem(name, 'The site did not respond at all — the address may be '
                                  'dead or the domain may have moved.', url=url)
        if result.status in _GONE_STATUSES:
            return _problem(name, 'Its search page is gone (HTTP %s) — the site has moved '
                                  'or renamed it, so the saved search URL now points at '
                                  'nothing.' % result.status, url=url)
        return None      # blocked or JS-only: Apify's crawler may still read it

    if result.status is None:
        reason = 'did not respond at all'
    elif result.status != 200:
        reason = 'refused the request (HTTP %s)' % result.status
    else:
        reason = ('loaded but contained no links — a consent wall, or a page that builds '
                  'its list in JavaScript that did not render')
    return _problem(name, 'Its search page %s. Every route was tried: a plain request, a '
                          'Chrome TLS fingerprint, a search-engine identity, and a real '
                          'headless browser.' % reason, url=url)


def _check_one_pattern(domain: str, globs: list, site_url: str) -> dict | _Unverified | None:
    """A saved job-URL pattern, against a page that would actually contain postings.

    A pattern that no longer matches anything is worse than no pattern: the crawler is
    still pointed at the site, still billed for it, and still collects nothing.

    `site_url` must be a SEARCH page, not the site's front door. The first real run of this
    check used the homepage and reported 26 of 29 patterns as broken -- every one a false
    alarm, because a homepage does not list job postings. Twenty-six false failures is
    worse than no check at all: it is exactly what teaches someone to ignore the red lines.
    """
    result = fetcher.fetch(site_url, needs_links=True)
    if not result.accepted:
        # Not "fine" -- unknown. Most direct-site domains are reached by Apify and refuse
        # this machine, so the pattern simply cannot be verified from here. Returning None
        # reported those as OK, which is a lie in the other direction.
        return UNVERIFIED
    links = fetcher.same_domain_links(result.soup(), site_url)
    matched = sum(1 for link in links for glob in globs if _glob_match(link, glob))
    if matched >= HEALTH_MIN_PATTERN_MATCHES:
        return None
    return _problem(
        '%s — job-link pattern' % domain,
        'Its saved job-link pattern (%s) no longer matches any link on the site, so the '
        'crawler would be paid to visit it and collect nothing. The site has most likely '
        'changed the shape of its posting URLs.' % '; '.join(globs)[:120],
        url=site_url)


# --------------------------------------------------------------------------------------
# the sweep
# --------------------------------------------------------------------------------------
def _site_search_url(site: dict, cities: list) -> str:
    """The search URL one browser-only site entry builds for these cities.

    A one-line helper purely so the call is made through a plain `dict` annotation: the
    two site tables have different inferred value types, so calling site['url'] inline
    made one of them an un-callable `object`.
    """
    return site['url'](cities)


def _url_targets(countries: list[str], cities: list[str]) -> list[tuple[str, str, str]]:
    """(label, url) for every site this app opens by URL, scoped to what a run would use.

    The direct-site half comes from _direct_site_tasks, the real search's own planner,
    rather than from a list built here. That matters twice over: it checks exactly what a
    search would open, and it cannot drift from it. Building the list independently got
    the scoping wrong immediately -- every builder returns a URL whatever country you hand
    it, so a first attempt produced "finn.no (Germany)" and "cv-library.co.uk (Germany)",
    checking Norwegian and British sites as if a German search would ever open them.
    """
    # Imported here rather than at module scope: `search` is the topmost layer and imports
    # from this one's neighbours, so taking it at import time would invert the package's
    # stated layering for the sake of one call.
    from .search.direct_site import _direct_site_tasks

    targets: list[tuple[str, str, str]] = [
        ('%s (%s)' % (task['domain'], task['location']), task['url'], VIA_APIFY)
        for task in _direct_site_tasks(countries, cities)]
    for domain, site in sorted(MANUAL_ASSIST_SITES.items()):
        if site['country'] in countries:
            targets.append(('%s (%s)' % (domain, site['country']),
                            _site_search_url(site, cities), VIA_LADDER))
    for domain, global_site in sorted(MANUAL_ASSIST_GLOBAL_SITES.items()):
        targets.append(('%s (Global)' % domain,
                        _site_search_url(global_site, cities), VIA_LADDER))
    # One URL per label; the same site reached twice is one check.
    seen, unique = set(), []
    for label, url, via in targets:
        if url not in seen:
            seen.add(url)
            unique.append((label, url, via))
    return unique


# What one city-sized search has actually cost, measured on the two real runs of the O
# campaign: Oslo 1,018 listings for $2.42, Amsterdam 2,616 for $3.07. Quoted as a range
# rather than an average because the number that matters to Sina is whether the next search
# fits in what is left, and the honest answer to that is the top of the range.
_APIFY_SEARCH_COST_LOW = 2.40
_APIFY_SEARCH_COST_HIGH = 3.10

# How many listings a Filter typically reaches Claude with, from the campaign's real runs:
# Oslo 16, Amsterdam 15 at Entry/Remote, 18 at Junior/Remote, 48-49 at Junior/Not Remote.
# Used only to turn the measured per-listing rate into a figure Sina can compare with the
# Apify line -- the rate itself is the measurement.
_TYPICAL_LISTINGS_TO_CLAUDE = 50

# What one Filter costs in Claude tokens, before this app has measured a run of its own.
# From the campaign's real batches: screening is batched (half price, and the instructions
# paid once per request of three listings rather than once per listing), while the résumé
# match runs one listing at a time over the survivors -- which is where most of it goes.
_CLAUDE_FILTER_COST_LOW = 0.10
_CLAUDE_FILTER_COST_HIGH = 0.30


def _report_budget(apify_token, progress_cb):
    """Two lines the Health Check could not answer before: what is left, and what a run costs.

    Apify says exactly what an account has used and what its cap is, so that one is a fact.
    Anthropic does not: an ordinary API key cannot ask for a balance -- that lives behind the
    organisation Admin API, which needs a different kind of key. What can be known exactly is
    what THIS app has spent, because every Claude response reports its own token usage, and
    since this campaign the app keeps that ledger (claude_screen/spend.py). So the Claude line
    reports spending rather than pretending to know a balance.
    """
    if not progress_cb:
        return

    if apify_token:
        try:
            from apify_client import ApifyClient
            limits = ApifyClient(apify_token).user().limits() or {}
            used = float((limits.get('current') or {}).get('monthlyUsageUsd') or 0.0)
            cap = (limits.get('limits') or {}).get('maxMonthlyUsageUsd')
            if cap:
                left = max(float(cap) - used, 0.0)
                searches = int(left // _APIFY_SEARCH_COST_HIGH)
                progress_cb('HEALTH_ITEM:Apify credit|OK|$%.2f of $%.2f left this month — '
                            'about %d more city search%s at $%.2f–$%.2f each'
                            % (left, float(cap), searches, '' if searches == 1 else 'es',
                               _APIFY_SEARCH_COST_LOW, _APIFY_SEARCH_COST_HIGH), 0, 1)
            else:
                progress_cb('HEALTH_ITEM:Apify credit|OK|$%.2f used this month; this account '
                            'states no monthly cap' % used, 0, 1)
        except Exception as e:
            progress_cb('HEALTH_ITEM:Apify credit|OK|could not be read (%s)' % str(e)[:60], 0, 1)

    try:
        from .claude_screen import spend as _spend
        totals = _spend.summary()
        # Sina's ask, in his words: not what one listing costs, but what a normal run of this
        # kind costs. So the estimate leads, and the spending behind it follows.
        if totals['per_listing_usd']:
            estimate = totals['per_listing_usd'] * _TYPICAL_LISTINGS_TO_CLAUDE
            line = ('one Filter costs about $%.2f — measured from this app\'s own runs '
                    '(%d listing(s) for $%.2f last time). $%.2f spent in total, $%.2f '
                    'this month'
                    % (estimate, totals['last_run_listings'], totals['last_run_usd'],
                       totals['total_usd'], totals['month_usd']))
        elif totals['total_usd']:
            line = ('one Filter costs about $%.2f–$%.2f; $%.2f spent by this app in total, '
                    '$%.2f this month'
                    % (_CLAUDE_FILTER_COST_LOW, _CLAUDE_FILTER_COST_HIGH,
                       totals['total_usd'], totals['month_usd']))
        else:
            line = ('one Filter costs about $%.2f–$%.2f. Nothing recorded yet — the ledger '
                    'starts at the next Filter and replaces that estimate with this app\'s '
                    'own figures. (Anthropic does not tell an API key what the account '
                    'balance is, so this counts what the app spends, from the tokens each '
                    'answer reports.)'
                    % (_CLAUDE_FILTER_COST_LOW, _CLAUDE_FILTER_COST_HIGH))
        progress_cb('HEALTH_ITEM:Claude spending|OK|%s' % line, 0, 1)
    except Exception as e:
        progress_cb('HEALTH_ITEM:Claude spending|OK|could not be read (%s)' % str(e)[:60], 0, 1)

    # And the line that answers the question as Sina asked it: not what one listing costs --
    # what a normal search of this kind costs, end to end.
    progress_cb('HEALTH_ITEM:What a normal search costs|OK|'
                'about $%.2f–$%.2f in total for one city — $%.2f–$%.2f of Apify for the '
                'search, plus about $%.2f–$%.2f of Claude when you press Filter'
                % (_APIFY_SEARCH_COST_LOW + _CLAUDE_FILTER_COST_LOW,
                   _APIFY_SEARCH_COST_HIGH + _CLAUDE_FILTER_COST_HIGH,
                   _APIFY_SEARCH_COST_LOW, _APIFY_SEARCH_COST_HIGH,
                   _CLAUDE_FILTER_COST_LOW, _CLAUDE_FILTER_COST_HIGH), 0, 1)


def _check_the_app_itself(report):
    """The two faults that are the app's own, before any source is asked.

    A damaged saved file and a broken fetch route both make every check after them look
    wrong for the wrong reason, so they are answered first and named plainly.
    """
    storage_problems = _check_storage()
    if storage_problems:
        for problem in storage_problems:
            report(problem['name'], problem)
    else:
        report('Saved data files', None)

    ladder_problems = _check_ladder()
    if ladder_problems:
        for problem in ladder_problems:
            report(problem['name'], problem)
    else:
        report('Fetch ladder (all four routes)', None)


def _check_apify_and_apis(apify_token, countries, cities, jooble_api_keys, reed_uk_api_key,
                          francetravail_credentials, report, progress_cb, should_cancel):
    """The paid actor and every direct API this run would use.

    Two separate questions, reported separately so a failure names which one broke: can the
    Apify token reach the Google actor, and does each direct API answer. A source with no
    key at all is neither -- it is switched off, and says so in amber rather than red.
    """
    if apify_token:
        try:
            from apify_client import ApifyClient
            client = ApifyClient(apify_token)
            client.user().get()
            google_result = _preflight_check_google(
                client, countries, cities, ['google'], None, should_cancel=should_cancel)
            report('Apify token and Google actor',
                   google_result if isinstance(google_result, dict) else None)
        except SearchCancelled:
            raise
        except Exception as e:
            report('Apify token and Google actor',
                   _problem('Apify token', 'The Apify token could not be used (%s). Every '
                                           'paid search depends on it.' % e, kind='api'))

    try:
        api_checked, _api_passed, api_problems, api_off = _preflight_check_api_sources(
            countries, cities, jooble_api_keys or {}, reed_uk_api_key,
            francetravail_credentials, None)
        # Switched off is not broken, and it is not silence either: a national board
        # contributing nothing to a country being searched is worth one amber line.
        for item in api_off:
            if progress_cb:
                progress_cb('HEALTH_ITEM:%s|OFF|%s' % (item['name'], item['reason']), 0, 1)
        if api_problems:
            for problem in api_problems:
                problem.setdefault('kind', 'api')
                report(problem['name'], problem)
        elif api_checked:
            report('Direct APIs (%d checked)' % api_checked, None)
    except SearchCancelled:
        raise
    except Exception as e:
        report('Direct APIs', _problem('Direct APIs',
                                       'The API checks could not be run (%s).' % e,
                                       kind='api'))


def _check_job_sites(countries, cities, report, progress_cb, should_cancel):
    """Open every job site this run would search, and say which ones answered.

    Free: none of it touches Apify. Returns the targets it checked and the set of sites that
    did not answer -- the pattern check below needs both, and needs to know which sites to
    leave alone.
    """
    targets = _url_targets(countries, cities)
    if progress_cb:
        progress_cb('GLOG:health|info|Checking %d job site(s) — no Apify credit is spent '
                    'on any of this.' % len(targets), 0, 1)
    unreachable: set = set()
    with ThreadPoolExecutor(max_workers=HEALTH_MAX_WORKERS) as executor:
        futures = {executor.submit(_check_one_url, label, url, via): label
                   for label, url, via in targets}
        for future in as_completed(futures):
            if should_cancel and should_cancel():
                for pending in futures:
                    pending.cancel()
                raise SearchCancelled()
            label = futures[future]
            url_problem: dict | None
            try:
                url_problem = future.result()
            except Exception as e:
                url_problem = _problem(label, 'The check itself failed: %s' % e)
            if url_problem is not None:
                unreachable.add(label.split(' (')[0])
            report(label, url_problem)

    return targets, unreachable


def _check_saved_patterns(targets, unreachable, report, progress_cb, should_cancel):
    """Check each saved job-link pattern against its own site's results page.

    Only patterns whose site can be pointed at a real SEARCH page: a pattern matches
    postings, and postings appear on search results, so checking a homepage proves nothing
    and fails everything. A domain with no search URL is left alone rather than reported --
    silence is correct there, a false red line is not.

    A site that just failed to open is not asked about its pattern either. The check would
    fetch the same URL, fail the same way, and -- since an unreachable site is not the
    pattern's fault -- report OK, so one domain appeared as both broken and fine in one run.

    Returns the domains whose pattern could not be verified from this machine.
    """
    search_url_for: dict[str, str] = {}
    for label, url, _via in targets:
        search_url_for.setdefault(label.split(' (')[0], url)
    patterns = all_job_url_patterns()
    pattern_targets = [(domain, globs, search_url_for[domain])
                       for domain, globs in sorted(patterns.items())
                       if globs and domain in search_url_for and domain not in unreachable]
    skipped = sum(1 for d, g in patterns.items() if g and d not in search_url_for)
    if skipped and progress_cb:
        progress_cb('GLOG:health|info|%d saved pattern(s) were not checked — those sites '
                    'are not searched for the selected countries, so there is no results '
                    'page to check them against.' % skipped, 0, 1)
    if progress_cb:
        progress_cb('GLOG:health|info|Checking %d saved job-link pattern(s) against their '
                    'own sites.' % len(pattern_targets), 0, 1)
    unverified_patterns: list = []
    with ThreadPoolExecutor(max_workers=HEALTH_MAX_WORKERS) as executor:
        pattern_futures: dict = {executor.submit(_check_one_pattern, d, g, u): d
                                 for d, g, u in pattern_targets}
        for future in as_completed(pattern_futures):
            if should_cancel and should_cancel():
                for pending in pattern_futures:
                    pending.cancel()
                raise SearchCancelled()
            domain = pattern_futures[future]
            outcome: dict | _Unverified | None
            try:
                outcome = future.result()
            except Exception as e:
                outcome = _problem(domain, 'The pattern check itself failed: %s' % e)
            if outcome is UNVERIFIED:
                unverified_patterns.append(domain)
                continue
            report('%s — job-link pattern' % domain, outcome)

    return unverified_patterns


def run_health_check(apify_token=None, countries=None, cities=None, jooble_api_keys=None,
                     reed_uk_api_key=None, francetravail_credentials=None,
                     progress_cb=None, should_cancel=None) -> list[dict]:
    """Check everything checkable for free. Returns the problems, in pre-flight shape.

    Never raises for a broken source -- that is the thing being reported, not an error in
    the checking. SearchCancelled still propagates so the button can be stopped.
    """
    countries = list(countries or [])
    cities = list(cities or [])
    problems: list[dict] = []
    checked = passed = 0

    def report(name, problem):
        nonlocal checked, passed
        checked += 1
        if problem is None:
            passed += 1
            if progress_cb:
                progress_cb('HEALTH_ITEM:%s|OK' % name, 0, 1)
        else:
            problems.append(problem)
            if progress_cb:
                progress_cb('HEALTH_ITEM:%s|FAILED|%s' % (name, problem['reason'][:110]), 0, 1)

    if progress_cb:
        progress_cb('HEALTH_START', 0, 1)

    _check_the_app_itself(report)
    _report_budget(apify_token, progress_cb)
    _check_apify_and_apis(apify_token, countries, cities, jooble_api_keys, reed_uk_api_key,
                          francetravail_credentials, report, progress_cb, should_cancel)

    targets, unreachable = _check_job_sites(countries, cities, report, progress_cb,
                                           should_cancel)
    unverified_patterns = _check_saved_patterns(targets, unreachable, report,
                                                progress_cb, should_cancel)

    if progress_cb:
        if unverified_patterns:
            progress_cb('GLOG:health|info|%d pattern(s) could not be verified from this '
                        'machine — those sites refuse a direct request and are reached '
                        'through Apify during a real search: %s'
                        % (len(unverified_patterns),
                           ', '.join(sorted(unverified_patterns)[:6])), 0, 1)
        status = 'OK' if not problems else 'FAILED'
        progress_cb('HEALTH_END:%s|%d of %d checks passed' % (status, passed, checked), 0, 1)
    return problems
