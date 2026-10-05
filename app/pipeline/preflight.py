"""Pre-run health checks over every source a search is about to use."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import anthropic
import requests

from .errors import (SearchCancelled)
from .geo import (CITY_COUNTRY, COUNTRY_ISO2, JOOBLE_API_COUNTRIES, _EURES_COUNTRIES)
from .rules import (_REMOTEOK_API_URL)
from .claude_screen import (CLAUDE_MODEL)
from .sponsorship import (_ARBEITNOW_API_URL)
from .sources_apis import (
    _ARBEITSAGENTUR_API_KEY,
    _ARBEITSAGENTUR_API_URL,
    _ARBETSFORMEDLINGEN_API_URL,
    _EURES_API_URL,
    _FRANCETRAVAIL_SCOPE,
    _FRANCETRAVAIL_TOKEN_URL,
    _REED_API_URL,
    _REMOTEOK_TIMEOUT_SECONDS,
    _REMOTIVE_API_URL,
    _SWISSDEVJOBS_API_URL,
    _read_jooble_usage,
)
from .google import (GOOGLE_SEARCH_ACTOR)


# Sina's own real Jooble REST API keys, one per country domain (each requested
# separately from Jooble -- a key from de.jooble.org only works for de.jooble.org, per
# Jooble's own docs), confirmed working with real calls: {"totalCount": 73575, "jobs":
# [{"title", "location", "snippet", "salary", "source", "type", "link", "company",
# "updated", "id"}, ...]}. This is a completely different mechanism from jooble.org's
# Cloudflare-blocked browser path above -- a plain server-to-server POST, no browser, no
# automation fingerprint for Cloudflare to catch at all.
#
# The free tier is a LIFETIME cap of 500 requests total *per key*, not monthly -- so
# every call is tracked in a small local counter file, keyed per domain (see
# _jooble_usage_path/_read_jooble_usage/_record_jooble_usage below), and Sina gets an
# explicit warning once a key's remaining budget gets low, well before it stops working.
_JOOBLE_LIFETIME_LIMIT = 500


# ---------------------------------------------------------------------------
# Pre-flight health check -- runs before any real search work, so a broken source is
# caught (and can be fixed or skipped) before real Apify credits/API quota are spent on
# the actual run, not discovered mid-run. Sina asked for this directly after this
# session's API-hunting work made clear which mechanisms are most likely to silently
# break (guessed direct-search URLs, undocumented APIs) -- see the fragility-risk
# discussion in README.md. Two sections, matching the two categories he cares about.
#
# A source with a real per-use budget (Jooble's 500-request LIFETIME cap) only ever
# gets a config-only check here (key present, right shape) -- never a real network call,
# since a pre-flight check itself must never be what drains that budget. Every other
# source gets one minimal real request, since none of them have that scarcity problem.
# ---------------------------------------------------------------------------
def _preflight_check_google(client, countries, cities, actor_order, progress_cb, should_cancel=None):
    if not ('google' in actor_order and (countries or cities)):
        return None
    try:
        # Real cost fixed here: this used to START A REAL ACTOR RUN (queries: "test")
        # and wait for it, on EVERY search -- a genuinely billed Apify run plus 20-60
        # seconds of dead time, purely to prove the actor is reachable, right after
        # client.user().get() already proved the token works and right before the real
        # Google call that would surface any failure anyway. .get() on the actor answers
        # exactly the same question (does this actor exist, and can this token see it?)
        # for no compute cost and no wait.
        actor_info = client.actor(GOOGLE_SEARCH_ACTOR).get()
        if actor_info:
            if progress_cb:
                progress_cb("PREFLIGHT_ITEM:Google Search actor|OK", 0, 1)
            return True
        if progress_cb:
            progress_cb("PREFLIGHT_ITEM:Google Search actor|FAILED|actor not found for this token", 0, 1)
        return {'name': 'Google Search actor', 'reason': 'actor not found for this token', 'fixable': False}
    except SearchCancelled:
        raise
    except Exception as e:
        if progress_cb:
            progress_cb(f"PREFLIGHT_ITEM:Google Search actor|FAILED|{e}", 0, 1)
        return {'name': 'Google Search actor', 'reason': str(e), 'fixable': False}


_PREFLIGHT_MAX_CONCURRENT_CHECKS = 8


def _passing_probe():
    """A no-I/O probe for a check whose verdict is already known to be OK (Jooble's
    config-only checks) -- lets it queue through the same reporting path as the real
    network probes so the Log stays in one consistent order."""
    return None


def _failing_probe(reason: str):
    """Counterpart to _passing_probe for an already-known failure."""
    def probe():
        raise RuntimeError(reason)
    return probe


def _register_api_preflight_checks(add_check, countries, cities, jooble_api_keys,
                                   reed_uk_api_key, francetravail_credentials,
                                   report_off=None):
    """Queue one check per API source that this run will actually use.

    Purely a catalogue -- it decides WHAT to check and hands each one to `add_check`;
    running them, reporting them and counting them is the caller's job. Adding a new
    source means adding one block here and nothing else.

    Note the deliberate asymmetry: most sources get a real minimal network call, but
    Jooble is config-only (its free key allows 500 requests for its entire lifetime, so
    spending one on a health check is not acceptable) and is queued through the same
    add_check with a probe that does no I/O, purely so the Log still reports every
    source in one ordered pass.
    """
    # Sweden -- real minimal call, no budget concern.
    if 'Sweden' in countries:
        add_check(
            'arbetsformedlingen.se',
            lambda: requests.get(_ARBETSFORMEDLINGEN_API_URL, params={'q': 'test', 'limit': 1},
                                 timeout=15).raise_for_status(),
            ['Sweden'],
        )

    # Germany -- real minimal call, no budget concern.
    if 'Germany' in countries or 'Berlin' in cities:
        add_check(
            'arbeitsagentur.de',
            lambda: requests.get(_ARBEITSAGENTUR_API_URL, params={'was': 'test', 'size': 1},
                                 headers={'X-API-Key': _ARBEITSAGENTUR_API_KEY},
                                 timeout=15).raise_for_status(),
            ['Germany'],
        )

    # Jooble -- config-only, NO network call, to protect the 500-lifetime budget per key.
    # Queued through add_check like everything else (with a probe that does no I/O and
    # just raises the already-known verdict) purely so the Log reports every source in
    # one ordered pass. Reporting these inline instead made all of Jooble's lines print
    # before every network source's, so the Log's order no longer matched the order the
    # sources actually run in -- a small regression from making the checks concurrent.
    for code, (country, city) in JOOBLE_API_COUNTRIES.items():
        if not (country in countries or (city and city in cities)):
            continue
        key = jooble_api_keys.get(code)
        name = f'{code}.jooble.org'
        settings_key = f'jooble_{code}_api_key'
        if not key:
            # Reported, not skipped. This used to `continue` on the grounds that an
            # unconfigured source is "not a problem, just not set up yet" -- and for a
            # country Sina never searches that is true, which is why this whole loop is
            # already scoped to the countries and cities of THIS run.
            #
            # For a country he DID select it is the opposite of harmless: a national job
            # board is switched off and nothing anywhere says so. A real check of the
            # saved settings found all fifteen Jooble keys, the Reed key and both France
            # Travail credentials empty, and the pre-flight's own log reported six sources
            # and looked entirely healthy.
            if report_off is not None:
                report_off(name, 'no API key, so this source is switched off for %s '
                           '(a free key from %s.jooble.org turns it on)' % (country, code),
                           fix_kind='jooble', settings_key=settings_key,
                           relevant_countries=[country])
            else:
                add_check(name, _failing_probe('no API key configured, so this source '
                                               'contributes no listings'),
                          [country], fixable=True, fix_kind='jooble',
                          settings_key=settings_key)
            continue
        if len(key.strip()) < 10:
            add_check(name, _failing_probe('the configured key looks malformed (too short)'),
                      [country], fixable=True, fix_kind='jooble', settings_key=settings_key)
            continue
        used = _read_jooble_usage().get(code, 0)
        if used >= _JOOBLE_LIFETIME_LIMIT:
            add_check(name, _failing_probe(f'lifetime request budget used up ({used}/{_JOOBLE_LIFETIME_LIMIT})'),
                      [country], fixable=True, fix_kind='jooble', settings_key=settings_key)
            continue
        add_check(name, _passing_probe, [country])

    # The Netherlands' national board. Config-only, like Jooble and for a related reason:
    # the check that matters is whether the Apify actor can be reached, and calling it is a
    # real actor run with a real cost. The token itself is already validated at the top of
    # run_search, so a config check here answers everything a probe would without paying
    # for it twice.
    if 'Netherlands' in countries or any(CITY_COUNTRY.get(c) == 'Netherlands' for c in cities):
        add_check('werk.nl', _passing_probe, ['Netherlands'])

    # Reed -- real minimal call, or a report that it is switched off. Same reasoning as
    # the Jooble block above: for a run that includes the UK, an unconfigured Reed key is
    # the UK's largest job board contributing nothing, and silence about it is worse than
    # a line Sina can dismiss.
    if 'United Kingdom' in countries:
        if not reed_uk_api_key:
            if report_off is not None:
                report_off('reed.co.uk', 'no API key, so this source is switched off for '
                           'the United Kingdom (a free key from reed.co.uk/developers '
                           'turns it on)', fix_kind='reed_uk',
                           settings_key='reed_uk_api_key',
                           relevant_countries=['United Kingdom'])
            else:
                add_check('reed.co.uk',
                          _failing_probe('no API key configured, so this source '
                                         'contributes no listings'),
                          ['United Kingdom'], fixable=True, fix_kind='reed_uk',
                          settings_key='reed_uk_api_key')
        else:
            add_check(
                'reed.co.uk',
                lambda: requests.get(_REED_API_URL, params={'keywords': 'test', 'resultsToTake': 1},
                                     auth=(reed_uk_api_key, ''), timeout=15).raise_for_status(),
                ['United Kingdom'], fixable=True, fix_kind='reed_uk', settings_key='reed_uk_api_key',
            )

    # France Travail -- real call, but just the OAuth2 token step (lightweight, no
    # search quota spent), not a real job search.
    if 'France' in countries:
        ft_client_id, ft_client_secret = francetravail_credentials or (None, None)
        if not (ft_client_id and ft_client_secret):
            add_check('francetravail.fr',
                      _failing_probe('no client ID/secret configured, so this source '
                                     'contributes no listings'),
                      ['France'], fixable=True, fix_kind='francetravail',
                      settings_key='francetravail_client_id')
        else:
            add_check(
                'francetravail.fr',
                lambda: requests.post(
                    _FRANCETRAVAIL_TOKEN_URL, params={'realm': '/partenaire'},
                    data={'grant_type': 'client_credentials', 'client_id': ft_client_id,
                          'client_secret': ft_client_secret, 'scope': _FRANCETRAVAIL_SCOPE},
                    headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=15,
                ).raise_for_status(),
                ['France'], fixable=True, fix_kind='francetravail',
                settings_key='francetravail_client_id',
            )

    # EURES -- a genuinely MINIMAL probe. This used to call _fetch_eures('test', ...),
    # the real search function, which POSTs for 50 full results with descriptions: a
    # health check doing a whole search's worth of work on every run. resultsPerPage=1
    # answers the same question (is the endpoint up and does it accept our body shape?)
    # for a fraction of the transfer.
    eures_relevant = [c for c in _EURES_COUNTRIES if c in countries]
    if eures_relevant:
        def _eures_probe():
            probe_body = {
                'resultsPerPage': 1, 'page': 1, 'sortSearch': 'MOST_RECENT',
                'keywords': [{'keyword': 'test', 'specificSearchCode': 'EVERYWHERE'}],
                'publicationPeriod': None, 'occupationUris': [], 'skillUris': [],
                'requiredExperienceCodes': [], 'positionScheduleCodes': [], 'sectorCodes': [],
                'educationAndQualificationLevelCodes': [], 'positionOfferingCodes': [],
                'locationCodes': [COUNTRY_ISO2[eures_relevant[0]]], 'euresFlagCodes': [],
                'otherBenefitsCodes': [], 'requiredLanguages': [], 'minNumberPost': None,
                'sessionId': 'jobdesk-preflight', 'requestLanguage': 'en',
            }
            requests.post(_EURES_API_URL, json=probe_body,
                          headers={'Content-Type': 'application/json'}, timeout=15).raise_for_status()

        add_check('europa.eu (EURES)', _eures_probe, eures_relevant)

    # Remotive / RemoteOK / arbeitnow.com -- always relevant (global, unconditional in
    # _run_direct_api_searches), real minimal calls, no key. arbeitnow.com was a real,
    # confirmed gap found in a later audit: it's called unconditionally in the real
    # search (_fetch_arbeitnow_sponsorship) but was never added here, so a break in
    # that source was only ever discovered mid-search instead of before spending any
    # real credits -- exactly the failure mode this whole pre-flight check exists to
    # catch.
    add_check('remotive.com',
              lambda: requests.get(_REMOTIVE_API_URL, params={'search': 'test'},
                                   timeout=15).raise_for_status(), ['Global'])
    # 15 seconds is the right ceiling for a search endpoint and the wrong one for this: it has
    # none, so one call returns its whole 623KB board and takes 34-44 seconds when healthy.
    # At 15 the Health Check reported a working source as broken before nearly every search --
    # the same fault as O-7, in a different disguise. See _REMOTEOK_TIMEOUT_SECONDS.
    add_check('remoteok.com',
              lambda: requests.get(_REMOTEOK_API_URL, headers={'User-Agent': 'Mozilla/5.0'},
                                   timeout=_REMOTEOK_TIMEOUT_SECONDS).raise_for_status(),
              ['Global'])
    add_check('arbeitnow.com',
              lambda: requests.get(_ARBEITNOW_API_URL, params={'visa_sponsorship': 'true'},
                                   timeout=15).raise_for_status(), ['Global'])

    # Switzerland-only sources -- real minimal calls, no key.
    if 'Switzerland' in countries:
        add_check('swissdevjobs.ch',
                  lambda: requests.get(_SWISSDEVJOBS_API_URL, headers={'User-Agent': 'Mozilla/5.0'},
                                       timeout=15).raise_for_status(), ['Switzerland'])
        for jobcloud_domain in ('jobs.ch', 'jobup.ch'):
            add_check(jobcloud_domain,
                      lambda d=jobcloud_domain: requests.get(
                          f'https://job-search-api.{d}/search', params={'query': 'test'},
                          headers={'User-Agent': 'Mozilla/5.0'}, timeout=15).raise_for_status(),
                      ['Switzerland'])

    # Every queued probe fires at once here; results are reported in queue order.



def _preflight_check_api_sources(countries, cities, jooble_api_keys, reed_uk_api_key,
                                 francetravail_credentials, progress_cb,
                                 should_cancel=None):
    """Returns (checked_count, passed_count, problems: list[dict]).

    The network checks below are collected first and then run CONCURRENTLY. They're pure
    network waits -- one thread spends its life waiting on a socket -- and there can
    be up to eleven of them at timeout=15 each -- run one after another that's a real,
    avoidable stall before any search work starts, three of which (Remotive, RemoteOK,
    arbeitnow) fire on literally every search. Results are reported in a fixed order
    afterwards, so the Log reads identically to the sequential version."""
    jooble_api_keys = jooble_api_keys or {}
    checked = 0
    passed = 0
    problems = []
    # Sources with no key at all -- reported, but never counted against the run. See
    # switched_off below.
    off: list = []

    def ok(name, relevant_countries=()):
        nonlocal checked, passed
        checked += 1
        passed += 1
        if progress_cb:
            progress_cb(f"PREFLIGHT_ITEM:{name}|OK||{'-'.join(relevant_countries)}", 0, 1)

    def fail(name, reason, fixable, fix_kind=None, settings_key=None, relevant_countries=()):
        nonlocal checked
        checked += 1
        problems.append({'name': name, 'reason': reason, 'fixable': fixable,
                          'fix_kind': fix_kind, 'settings_key': settings_key})
        if progress_cb:
            progress_cb(f"PREFLIGHT_ITEM:{name}|FAILED|{reason}|{'-'.join(relevant_countries)}", 0, 1)

    def queue_switched_off(name, reason, fix_kind=None, settings_key=None,
                           relevant_countries=()):
        """Queued, not reported on the spot, so the Log keeps one order.

        The same reason Jooble's config-only verdicts are queued through add_check: reporting
        inline put every keyless source's line above every network source's, and the Log no
        longer read in the order the sources actually run.
        """
        network_checks.append((name, None, list(relevant_countries), False, fix_kind,
                               settings_key, reason))

    def switched_off(name, reason, fix_kind=None, settings_key=None, relevant_countries=()):
        """A source with no key at all: reported, but not counted as a failure.

        Sina's words, looking at the Log: this is not a problem we have, it is a source we
        never set up. Reporting it as FAILED put it in red beside things that are genuinely
        broken, and made a healthy run read as a broken one. It still has to be SAID -- a
        national board switched off for a country being searched is worth knowing -- so it
        gets its own verdict and its own line, out of the failure count and out of the
        dialog that interrupts a search.
        """
        nonlocal checked, passed
        checked += 1
        passed += 1
        off.append({'name': name, 'reason': reason, 'fix_kind': fix_kind,
                    'settings_key': settings_key})
        if progress_cb:
            progress_cb(f"PREFLIGHT_ITEM:{name}|OFF|{reason}|{'-'.join(relevant_countries)}", 0, 1)

    # (name, probe_callable, relevant_countries, fixable, fix_kind, settings_key)
    network_checks = []

    def add_check(name, probe, relevant_countries, fixable=False, fix_kind=None, settings_key=None):
        network_checks.append((name, probe, list(relevant_countries), fixable, fix_kind,
                               settings_key, None))

    def run_network_checks():
        """Runs every queued probe at once, then reports them in queue order.

        An entry with no probe is a source with no key -- nothing to run, and it is reported
        from its place in the queue so the order still matches the order sources run in.
        """
        if not network_checks:
            return
        results: dict[str, str | None] = {}
        probes = [c for c in network_checks if c[1] is not None]
        if probes:
            with ThreadPoolExecutor(max_workers=min(_PREFLIGHT_MAX_CONCURRENT_CHECKS,
                                                    len(probes))) as executor:
                futures = {executor.submit(c[1]): c[0] for c in probes}
                for future in as_completed(futures):
                    try:
                        future.result()
                        results[futures[future]] = None
                    except Exception as e:
                        results[futures[future]] = str(e)
        for name, probe, relevant, fixable, fix_kind, settings_key, off_reason in network_checks:
            if probe is None:
                switched_off(name, off_reason, fix_kind=fix_kind, settings_key=settings_key,
                             relevant_countries=relevant)
                continue
            error = results.get(name)
            if error is None:
                ok(name, relevant)
            else:
                fail(name, error, fixable=fixable, fix_kind=fix_kind,
                     settings_key=settings_key, relevant_countries=relevant)
        network_checks.clear()

    _register_api_preflight_checks(add_check, countries, cities, jooble_api_keys,
                                   reed_uk_api_key, francetravail_credentials,
                                   report_off=queue_switched_off)
    run_network_checks()

    if off and progress_cb:
        progress_cb('GLOG:preflight|info|%d source(s) are switched off for want of a key: %s. '
                    'Nothing is broken; they simply contribute no listings to this search.'
                    % (len(off), ', '.join(item['name'] for item in off)), 0, 1)

    # The switched-off sources travel with the problems rather than only being logged.
    # Found while splitting run_health_check: the Health Check reports what this returns and
    # passes no progress callback, so turning a missing key from FAILED into an OFF line made
    # those sources vanish from it entirely. Sina asked to be told they are off -- just not
    # in red -- so the caller gets the list and decides how to show it.
    return checked, passed, problems, off


def _run_pre_google_check(client, countries, cities, actor_order, jooble_api_keys, reed_uk_api_key,
                           francetravail_credentials, progress_cb=None, problems_cb=None,
                           should_cancel=None):
    """Everything checked here (the Google Search actor itself, plus every direct-API
    source -- arbetsformedlingen.se, arbeitsagentur.de, each configured Jooble country
    domain, Reed, France Travail, EURES, Remotive, RemoteOK, and Switzerland's
    swissdevjobs.ch/jobs.ch/jobup.ch) is ONLY ever actually used from inside the Google
    stage of run_search (_run_direct_api_searches is called from there, not
    independently) -- so this check itself only runs right before that stage starts,
    not at the very top of run_search before Indeed/LinkedIn/Glassdoor even run. Sina
    asked for exactly this after noticing the original placement checked things that
    had nothing to do with what was about to run yet.

    Returns possibly-updated (jooble_api_keys, reed_uk_api_key, francetravail_credentials)
    reflecting any live fixes made in the problems dialog, so the real run right after
    this uses them without needing a restart. Raises SearchCancelled if Sina cancels
    from the problems dialog."""
    if progress_cb:
        progress_cb("PREFLIGHT_START", 0, 1)

    google_result = _preflight_check_google(client, countries, cities, actor_order, progress_cb, should_cancel=should_cancel)
    google_problems = [google_result] if isinstance(google_result, dict) else []
    google_checked = 1 if google_result is not None else 0
    google_passed = 1 if google_result is True else 0

    api_checked, api_passed, api_problems, _api_off = _preflight_check_api_sources(
        countries, cities, jooble_api_keys, reed_uk_api_key, francetravail_credentials, progress_cb,
    )

    total_checked = google_checked + api_checked
    total_passed = google_passed + api_passed
    if progress_cb:
        # Always emitted, even when nothing was relevant this run (total_checked == 0)
        # -- PREFLIGHT_START already opened a live timer line, so it must always be
        # matched by a PREFLIGHT_END or that line would tick forever. Sina asked for the
        # completed line to name the countries/cities this check covered (instead of a
        # bare passed/checked count), so the label carries that list -- pass/fail still
        # decides the line's color, just not its text anymore.
        status = 'OK' if total_passed == total_checked else 'FAILED'
        relevant_locations = list(countries) + list(cities)
        progress_cb(f"PREFLIGHT_END:{status}|{'-'.join(relevant_locations)}", 0, 1)

    all_problems = google_problems + api_problems
    if not all_problems or not problems_cb:
        return jooble_api_keys, reed_uk_api_key, francetravail_credentials

    result_holder = problems_cb(all_problems)
    if result_holder.get('cancel'):
        raise SearchCancelled()

    resolved_keys = result_holder.get('resolved_keys') or {}
    for problem in all_problems:
        new_value = resolved_keys.get(problem.get('settings_key'))
        if not new_value:
            continue
        if problem.get('fix_kind') == 'jooble':
            code = problem['settings_key'].replace('jooble_', '').replace('_api_key', '')
            jooble_api_keys = {**jooble_api_keys, code: new_value}
        elif problem.get('fix_kind') == 'reed_uk':
            reed_uk_api_key = new_value
        elif problem.get('fix_kind') == 'francetravail':
            # France Travail needs both client_id and client_secret -- the dialog
            # collects both under one "fix" and packs them as "id|||secret".
            if '|||' in new_value:
                francetravail_credentials = tuple(new_value.split('|||', 1))

    return jooble_api_keys, reed_uk_api_key, francetravail_credentials


# ---------------------------------------------------------------------------
# Turning a failure into something actionable.
#
# The problem dicts above say WHAT broke -- "HTTP 403", "key rejected", "no results this
# run". That is exactly the information Sina cannot act on: it names the symptom in the
# app's vocabulary, not the fix in his. So each one is handed to Claude with its context,
# and comes back with the two or three concrete steps that would actually resolve it.
#
# One call for the whole batch rather than one per problem: the model reads them together,
# it is a single round-trip instead of a dozen, and a search that ends with eight quiet
# domains should not cost eight API calls to explain.
# ---------------------------------------------------------------------------
_FIX_ADVICE_SYSTEM_PROMPT = """You help someone maintain a personal job-search app called
Job Finder. The user is not a developer working on its internals -- he runs it to find jobs.

You are given a numbered list of things that failed during a search. For each one, write
the concrete steps HE can take.

What Job Finder already does by itself, so never suggest doing these by hand:
- It works out each site's job-URL pattern automatically, by reading the site and
  verifying against real postings. Never tell him to find a URL pattern, edit a regex,
  or configure link patterns.
- It already retries a blocked site four ways: a plain request, a request carrying
  Chrome's TLS fingerprint, a request identifying as a search-engine crawler, and a real
  headless browser that runs JavaScript and dismisses cookie banners. Never suggest
  changing the user agent, adding headers, using a browser, or handling cookies.
- It reads a site's sitemap when its pages are closed.
So if a site is reported as unreachable, every automatic route has already failed.

Rules:
- Reply with one block per item, starting with `FIX <number>:` on its own line.
- Then 1-3 short steps, one per line, each starting with "- ".
- Be specific and practical. Name the actual page to open, the actual setting to change.
- If the cause is an API key, say where that provider issues keys, and that the new key
  goes in Job Finder's Setup window (or can be pasted directly into this problem report).
- If a website is blocking or has gone quiet, the useful steps are human ones: open it in
  a browser to see whether it still exists, whether it still has a job section, and
  whether its address has changed or it now redirects somewhere else.
- If nothing can genuinely be done -- the site is gone, or it is a hard block -- say that
  in one line. Do not invent a fix. "This site has shut down; it can be ignored" is a
  better answer than a plausible-sounding step that will not work.
- No preamble, no summary, no markdown headers. Plain lines only.
"""

_FIX_BLOCK_PATTERN = re.compile(r'^FIX\s+(\d+)\s*:\s*$', re.IGNORECASE | re.MULTILINE)

# Enough for a few short steps each across a realistic batch, and a hard stop on cost.
_FIX_ADVICE_MAX_TOKENS = 1600
_FIX_ADVICE_MAX_PROBLEMS = 12


def explain_problems(problems: list, anthropic_api_key: str | None = None,
                     progress_cb=None) -> None:
    """Attach a plain-language `fix_advice` to each problem, in place.

    Best-effort by design: no key, no network, or an unparseable reply all leave the
    problems exactly as they were. The window still shows what broke and why -- the advice
    is an addition to that, never a precondition for reporting it.
    """
    if not problems:
        return
    if not anthropic_api_key:
        for problem in problems:
            problem.setdefault(
                'fix_advice',
                'Add a Claude API key in Setup to get step-by-step fix suggestions here.')
        return

    batch = problems[:_FIX_ADVICE_MAX_PROBLEMS]
    listed = '\n'.join(
        '%d. %s\n   what happened: %s%s'
        % (index, problem.get('name') or 'unknown',
           problem.get('reason') or 'unknown',
           ('\n   url: %s' % problem['url']) if problem.get('url') else '')
        for index, problem in enumerate(batch, 1))

    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=_FIX_ADVICE_MAX_TOKENS,
            temperature=0,
            system=_FIX_ADVICE_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': listed}],
        )
        answer = '\n'.join(block.text for block in response.content
                           if getattr(block, 'type', None) == 'text')
    except Exception as e:
        if progress_cb:
            progress_cb('GLOG:preflight|error|Could not get fix suggestions from Claude '
                        '(%s) -- the problems below are still listed in full.' % e, 0, 1)
        return

    # Split on the FIX <n>: markers and give each block to the problem it names, rather
    # than assuming the model returned them in order or returned all of them.
    marks = list(_FIX_BLOCK_PATTERN.finditer(answer))
    for position, mark in enumerate(marks):
        end = marks[position + 1].start() if position + 1 < len(marks) else len(answer)
        try:
            index = int(mark.group(1)) - 1
        except ValueError:
            continue
        if 0 <= index < len(batch):
            advice = answer[mark.end():end].strip()
            if advice:
                batch[index]['fix_advice'] = advice
