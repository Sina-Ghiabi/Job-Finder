# -*- coding: utf-8 -*-
"""Saying which sites went quiet.

A site that returns nothing looks exactly like a site that has no matching jobs. The
difference matters -- one is a layout change to fix, the other is just a quiet week --
so every domain a search touched and got nothing from is named at the end of the run.
"""

from __future__ import annotations

from urllib.parse import urlsplit
from ..geo import (CITY_COUNTRY, COUNTRY_JOB_SITES)
from .sites import (GOOGLE_GLOBAL_EXTRA_SITES, GLOBAL_STARTUP_SITES, COUNTRY_STARTUP_SITES)

def _warn_zero_result_google_sites(rows: list[dict], countries: list[str], cities: list[str],
                                    progress_cb=None,
                                    extra_broken_domains: tuple[str, ...] | list[str] = (),
                                    problems: list | None = None) -> list:
    """The user asked for this as a blanket safety net covering EVERY site RoleHound searches
    via Google (COUNTRY_JOB_SITES and GOOGLE_GLOBAL_EXTRA_SITES alike, confirmed
    deep-crawl pattern or not) -- not just the ones with no confirmed
    GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS entry (that's the separate, narrower check
    inside _deepen_google_results). A domain can go quiet for lots of reasons that have
    nothing to do with a missing deep-crawl pattern -- a typo'd/dead/renamed domain,
    Google not indexing it well, a robots block -- and this run simply never saw a
    single result from it.

    `extra_broken_domains` is _deepen_google_results' own list (domains with no
    confirmed job-URL pattern) -- merged in here so the user gets ONE combined report for
    every domain that needs attention this run, regardless of which of the two checks
    found it, instead of two separate warnings.

    Returns the problems as a list of dicts and, if `problems` is given, appends them to
    it. This used to end in a dialog asking the user to go and find the correct URL himself;
    pattern discovery does that automatically now, so what remains is telling him which
    sites stayed quiet and why."""
    no_pattern_domains = set(extra_broken_domains)
    broken_domains: set = set()

    # Every row, from every stage -- not just the ones Google produced.
    #
    # This used to read `[r for r in rows if r.get('platform') == 'google']`, and that one
    # filter made the report lie. A site reached by the browser-site stage carries its own
    # domain as its platform, not 'google', so it was invisible here and got reported as
    # having "returned zero results" in the same run that it delivered listings. On a real
    # Netherlands search that misreported werk.nl, weworkremotely.com, work.turing.com and
    # work.mercor.com -- four sites the user was told he had lost and had not.
    found_domains = {
        urlsplit(r['url']).netloc.lower() for r in rows if r.get('url')
    }

    def _was_found(domain: str) -> bool:
        return any(fd == domain or fd.endswith('.' + domain) for fd in found_domains)

    if countries or cities:
        expected_domains = set(GOOGLE_GLOBAL_EXTRA_SITES) | set(GLOBAL_STARTUP_SITES)
        for country in countries:
            expected_domains.update(COUNTRY_JOB_SITES.get(country) or [])
            expected_domains.update(COUNTRY_STARTUP_SITES.get(country) or [])
        for city in cities:
            expected_domains.update(COUNTRY_JOB_SITES.get(CITY_COUNTRY.get(city) or '') or [])
            expected_domains.update(COUNTRY_STARTUP_SITES.get(CITY_COUNTRY.get(city) or '') or [])

        broken_domains.update(domain for domain in expected_domains if not _was_found(domain))

    # A site that produced listings but has no individual-posting pattern is NOT the same
    # thing as a site that produced nothing, and merging them cost the user real trust: told
    # that seventeen sites had gone quiet, he had actually lost nine -- startup.jobs had
    # delivered 52 listings, magnet.me 6, jobfluent.com 5, nationalevacaturebank.nl 3.
    # Both still deserve a line, because a site whose postings cannot be opened
    # individually is genuinely worth fixing; it just is not a loss.
    # Both lists are drawn from the SAME universe and split by one question: did this
    # domain produce anything at all? A domain that reached here for having no posting
    # pattern is quiet if it also produced nothing, and listings-only if it did -- reading
    # only `broken_domains` for the quiet half silently dropped every domain that arrived
    # via extra_broken_domains, which is most of them.
    all_reported = no_pattern_domains | broken_domains
    quiet_domains = sorted(d for d in all_reported if not _was_found(d))
    listing_only_domains = sorted(d for d in all_reported if _was_found(d))

    if not (quiet_domains or listing_only_domains):
        return []

    if progress_cb:
        if quiet_domains:
            progress_cb(
                f"GLOG:platform:Google|error|{len(quiet_domains)} known job site(s) "
                "produced NOTHING this run (blocked, poorly indexed by Google, "
                "temporarily down, or the domain may be wrong/outdated).",
                0, 1,
            )
        if listing_only_domains:
            progress_cb(
                f"GLOG:platform:Google|warning|{len(listing_only_domains)} site(s) did "
                "return listings, but only their search page -- no confirmed pattern for "
                "individual postings there yet, so their jobs come in as one page rather "
                "than one row each.",
                0, 1,
            )

    found = [{
        'name': domain,
        'reason': 'This site produced no results at all this run, from any route -- not '
                  'Google, not its own search page, not the browser. The domain may have '
                  'changed, gone down, or stopped being indexed.',
        'fixable': False,
        'kind': 'url',
        'url': 'https://%s/' % domain,
    } for domain in quiet_domains]
    found += [{
        'name': domain,
        'reason': 'This site DID return listings this run, but no pattern for its '
                  'individual job pages could be worked out, so what came back is its '
                  'search page rather than one row per posting. Nothing was lost; the '
                  'jobs are just less usable than they could be.',
        'fixable': False,
        'kind': 'url',
        'url': 'https://%s/' % domain,
    } for domain in listing_only_domains]
    if problems is not None:
        problems.extend(found)
    return found
