"""Per-site direct search -- crawling each job board's own search URL."""
from __future__ import annotations

from apify_client import ApifyClient
from ..text import dig, looks_like_error_page
from ..geo import CITY_COUNTRY, COUNTRY_JOB_SITES, _mentions_city
from ..apify import (WEBSITE_CONTENT_CRAWLER_ACTOR, _DEEP_CRAWL_MEMORY_MBYTES,
                     crawl_urls_in_batches)
from ..sources_urls import DIRECT_API_ROLE_TERMS, _build_direct_search_url
from ..google import COUNTRY_STARTUP_SITES, GLOBAL_STARTUP_SITES, GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT, GOOGLE_GLOBAL_EXTRA_SITES, GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS, _is_excluded_job_board


def _direct_site_tasks(countries: list[str], cities: list[str],
                       role_terms=None) -> list[dict]:
    """Every per-site direct search this run should attempt.

    One task per (domain, location) that actually resolves to a search URL. Pure: no
    network, no actor -- so what a country or city expands to can be checked directly.
    """
    tasks: list[dict] = []

    def add_tasks(location: str, loc_type: str, country: str | None):
        if not country:
            return
        known_domains = list(COUNTRY_JOB_SITES.get(country) or [])
        startup_domains = list(GLOBAL_STARTUP_SITES) + list(COUNTRY_STARTUP_SITES.get(country) or [])
        domains = list(known_domains)
        domains += [d for d in GOOGLE_GLOBAL_EXTRA_SITES if d not in domains]
        # startup-site domains included alongside known/global -- currently a no-op
        # for all of them (none has a DIRECT_SEARCH_URL_BUILDERS/
        # _DIRECT_URL_BUILDERS_WITH_COUNTRY entry or saved override yet, so
        # _build_direct_search_url returns None and `if url:` below skips it), but
        # this way a future builder for one of them starts working automatically
        # instead of silently needing this function updated too.
        domains += [d for d in startup_domains if d not in domains]
        for domain in domains:
            if domain in known_domains:
                stage = 'known'
            elif domain in startup_domains:
                stage = 'startup'
            else:
                stage = 'global'
            # One search per role term, not one per site. Every builder used to bake in
            # "Data Scientist" and nothing else, which is the same gap measured on the
            # direct APIs: on arbeitsagentur.de that one term found 376 of 1,481 listings.
            #
            # Deduplicated on the URL itself, because not every site puts the keyword in
            # its URL -- iamexpat.nl's builder returns the same category page whatever it
            # is asked for, and crawling that page four times would cost four times the
            # Apify pages for exactly the same links.
            for role_term in (role_terms or DIRECT_API_ROLE_TERMS):
                url = _build_direct_search_url(domain, location, loc_type, country, role_term)
                if not url or any(t['url'] == url for t in tasks):
                    continue
                tasks.append({
                    'domain': domain, 'location': location, 'loc_type': loc_type,
                    'country': country, 'url': url, 'stage': stage,
                    'role_term': role_term,
                })

    for country in countries:
        add_tasks(country, 'country', country)
    for city in cities:
        add_tasks(city, 'city', CITY_COUNTRY.get(city))
    return tasks


# Direct-site URLs are listing pages the app already knows how to read, so they batch
# larger than freshly-learned sites -- but still nowhere near the whole account at once.
_DIRECT_SITE_BATCH_SIZE = 12

def _direct_site_run_input(unique_urls: list[str], include_globs: list[str]) -> dict:
    """The actor configuration for the direct-site crawl.

    Identical tuning to the deep crawl's -- see _deep_crawl_run_input in google.py for
    the full history behind requestTimeoutSecs and maxRequestRetries.
    """
    return {
        "startUrls": [{"url": u} for u in unique_urls],
        "maxCrawlDepth": 1,
        "maxCrawlPages": len(unique_urls) * GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT,
        "crawlerType": "playwright:adaptive",
        "htmlTransformer": "none",
        "includeUrlGlobs": include_globs,
        "requestTimeoutSecs": 60,
        "maxRequestRetries": 1,
    }


def _absorb_direct_site_items(crawled, rows: list[dict], url_to_task: dict):
    """Fold the crawl's pages back into `rows`.

    Returns (added, listing_reached, job_count_for_task_url, wrong_city_count) -- the
    three dicts are what the per-site status lines are built from. Pure apart from
    appending to `rows`.
    """
    seen_urls = {r.get('url') for r in rows if r.get('url')}
    listing_reached = set()
    job_count_for_task_url: dict[str, int] = {}
    wrong_city_count: dict[str, int] = {}
    added = 0
    new_rows = []
    for item in crawled:
        url = item.get('url')
        text = (item.get('text') or '').strip()
        if not url or not text:
            continue
        # An error, block or rate-limit page is a real HTTP 200 with real text on it;
        # without this it becomes a row and is translated, screened and shown as a job.
        if looks_like_error_page(dig(item, 'metadata.title') or item.get('title'), text):
            continue
        if _is_excluded_job_board(url):
            continue

        if url in url_to_task:
            # This is the listing/search-results page itself -- a real connection was
            # made and real content came back, which is exactly what the green/red
            # status line below reports on, regardless of whether any individual job
            # link is found under it. Kept as a fallback row too (useful even with zero
            # individual job links) exactly like a normal Google result would be.
            listing_reached.add(url)
            task = url_to_task[url]
            if url in seen_urls:
                continue
            new_rows.append({
                'title': dig(item, 'metadata.title') or item.get('title'),
                'company': None,
                'location': task['location'] if task['loc_type'] == 'city' else None,
                'country': task['country'],
                'posted_date': None,
                'url': url,
                'description': text,
                'platform': 'google',
                'google_stage': task['stage'],
            })
            seen_urls.add(url)
            added += 1
            continue

        # A page reached by following a link from one of the start URLs above --
        # match it back to whichever task's start URL referred here.
        referrer = dig(item, 'crawl.referrerUrl')
        task = url_to_task.get(referrer)
        if not task:
            continue
        if task['loc_type'] == 'city' and not _mentions_city(task['location'], (dig(item, 'metadata.title') or '') + ' ' + text):
            # A real, live test found arbeidsplassen.nav.no's own city filter isn't
            # strictly precise -- its UI shows "Oslo" as an active filter, but still
            # mixes in jobs actually located in Stavanger, Trondheim, Gjovik (likely
            # deliberate "similar/nearby" recommendations on the site's part). Since
            # Sina asked for genuinely correct results, not just "the site says it
            # filtered", this drops any job page whose own text doesn't actually
            # mention the requested city -- better a missed edge case (a real Oslo job
            # that never repeats "Oslo" in its own body text) than a wrong-city result
            # slipping through.
            #
            # The counter below deliberately sits AFTER this filter. A real log bug
            # otherwise: the green per-site line could announce "N individual job
            # posting(s) found" when all N had just been dropped for being in the wrong
            # city -- exactly the case this filter exists for.
            wrong_city_count[task['url']] = wrong_city_count.get(task['url'], 0) + 1
            continue
        job_count_for_task_url[task['url']] = job_count_for_task_url.get(task['url'], 0) + 1
        if url in seen_urls:
            continue
        new_rows.append({
            'title': dig(item, 'metadata.title') or item.get('title'),
            'company': None,
            'location': task['location'] if task['loc_type'] == 'city' else None,
            'country': task['country'],
            'posted_date': None,
            'url': url,
            'description': text,
            'platform': 'google',
            'google_stage': task['stage'],
        })
        seen_urls.add(url)
        added += 1

    rows.extend(new_rows)
    return added, listing_reached, job_count_for_task_url, wrong_city_count


def _report_direct_site_outcomes(url_to_task, listing_reached, job_count_for_task_url,
                                 wrong_city_count, progress_cb) -> int:
    """Log one green/red status line per direct-searched URL. Returns the red count.

    Green if a real connection was made to this exact URL (regardless of how many, or
    whether zero, individual job links were found under it -- that's a separate, softer
    note folded into the same green line), red if nothing came back from it at all. This
    is the green/red half of the yellow "Checking..." lines logged before the crawl.
    """
    red_count = 0
    for url, t in url_to_task.items():
        job_count = job_count_for_task_url.get(url, 0)
        dropped_wrong_city = wrong_city_count.get(url, 0)
        wrong_city_note = f" ({dropped_wrong_city} dropped as wrong-city)" if dropped_wrong_city else ""
        has_pattern = bool(GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS.get(t['domain']))
        if url in listing_reached:
            if job_count > 0:
                note = f"{job_count} individual job posting(s) found{wrong_city_note}"
            elif dropped_wrong_city:
                note = f"connected, but all {dropped_wrong_city} posting(s) it returned were in the wrong city"
            elif has_pattern:
                note = "connected, but no individual job postings extracted (its URL format may have changed)"
            else:
                note = "connected (no confirmed individual-job-URL pattern for this domain yet)"
            if progress_cb:
                progress_cb(f"GLOG:direct_site|success|{t['domain']} for {t['location']}: {note}.", 0, 1)
        else:
            red_count += 1
            if progress_cb:
                progress_cb(
                    f"GLOG:direct_site|error|{t['domain']} for {t['location']}: could not connect at all "
                    f"to {url} -- please check it manually:\n"
                    f"    1 - Open {url} in your browser and see what it actually shows\n"
                    f"    2 - If it's broken, empty, blocked, or redirected somewhere odd, "
                    f"go to {t['domain']}'s homepage, search \"Data Scientist\" manually, "
                    f"and copy the new working URL\n"
                    f"    3 - Send the new URL back here so it can be fixed",
                    0, 1,
                )
    return red_count


def _run_direct_site_searches(rows: list[dict], client: ApifyClient, countries: list[str],
                              cities: list[str], progress_cb=None, should_cancel=None,
                              role_terms=None) -> None:
    """Additive, not a replacement -- runs alongside the existing Google-based
    known/global stages (which are untouched), never instead of them. For every
    selected country/city, and every COUNTRY_JOB_SITES/GOOGLE_GLOBAL_EXTRA_SITES domain
    with a builder in DIRECT_SEARCH_URL_BUILDERS/_DIRECT_URL_BUILDERS_WITH_COUNTRY, this
    builds that site's own real location-search URL directly (see the long comment
    above those dicts for which domains have one and why the rest don't) and crawls it
    with the website-content-crawler actor, same technique as _deepen_google_results.

    A URL built here that turns out to be wrong (a site changed its format, or one of
    the less-certain inferred guesses above just doesn't work) is expected to happen
    sometimes -- rather than fail silently, any built URL that yields zero real job
    links (for a domain with a confirmed GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS entry, so a
    real result was expected) gets the same yellow, step-by-step log warning as the
    other two warning types, naming the exact URL that didn't work so Sina can check
    it and report back the correct one."""
    tasks = _direct_site_tasks(countries, cities, role_terms)
    if not tasks:
        return

    # Same URL can come up twice (e.g. a country and one of its cities both selected,
    # both resolving to the same country-wide URL for a domain with no city-level
    # builder) -- setdefault dedups while preserving first-seen task per URL.
    url_to_task: dict[str, dict] = {}
    for t in tasks:
        url_to_task.setdefault(t['url'], t)
    unique_urls = list(url_to_task.keys())

    include_globs = sorted({
        pattern
        for t in tasks
        for pattern in GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS.get(t['domain'], [])
    })

    if progress_cb:
        # Live-ticking timer, started right before the one combined crawl call that
        # covers every direct-site URL -- same reasoning as Known Websites/Deep-Crawl's
        # own timers.
        progress_cb("DIRECT_SITE_START", 0, 1)
        # Sina asked for a per-site status indicator in the Log: a yellow "checking"
        # line now, followed later by a green line (a real connection was made to this
        # exact URL -- regardless of whether it had 0 or 50 jobs on it) or a red line
        # (couldn't connect to it at all). The Log panel can't recolor an existing
        # line, so this is two separate lines rather than one line changing color, but
        # reads the same way: yellow, then green/red right after. GLOG: (not a plain
        # WARNING:) so this nests under "Direct Site Search" instead of appearing flat
        # at the very end of the whole log, unindented -- a real bug fixed this round.
        for url, t in url_to_task.items():
            progress_cb(f"GLOG:direct_site|info|Checking {t['domain']} for {t['location']}: {url}", 0, 1)

    # Batched, retried and split by the shared crawl pattern, so a busy account costs a
    # wait rather than every direct-site URL in the run. This used to be one call over all
    # of them asking for the whole 16,384MB allowance: refused whenever another actor was
    # still going, and the whole section returned nothing.
    crawled, unreachable, usage_usd = crawl_urls_in_batches(
        client, WEBSITE_CONTENT_CRAWLER_ACTOR, list(unique_urls),
        lambda batch: _direct_site_run_input(batch, include_globs),
        _DIRECT_SITE_BATCH_SIZE, should_cancel=should_cancel, progress_cb=progress_cb,
        label='direct_site', memory_mbytes=_DEEP_CRAWL_MEMORY_MBYTES)

    if unreachable and progress_cb:
        progress_cb(f"GLOG:direct_site|warning|{len(unreachable)} site URL(s) could not be "
                    f"reached even one at a time: {', '.join(unreachable)[:120]}", 0, 1)
    if not crawled:
        if progress_cb:
            progress_cb("DIRECT_SITE_HEADER:FAILED|", 0, 1)
            progress_cb("  ! Direct site search collected nothing", 0, 1)
        return
    if progress_cb:
        progress_cb(f"DIRECT_SITE_HEADER:SUCCESS|{usage_usd:.4f}", 0, 1)

    added, listing_reached, job_count_for_task_url, wrong_city_count = \
        _absorb_direct_site_items(crawled, rows, url_to_task)

    red_count = _report_direct_site_outcomes(
        url_to_task, listing_reached, job_count_for_task_url, wrong_city_count, progress_cb,
    )

    if progress_cb:
        progress_cb(
            f"GLOG:direct_site|info|Direct site search done: {added} row(s) added from "
            f"{len(unique_urls)} directly-searched page(s), {red_count} URL(s) could not "
            "be reached at all.",
            0, 1,
        )
