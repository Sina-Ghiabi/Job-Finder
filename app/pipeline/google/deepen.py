# -*- coding: utf-8 -*-
"""Following a Google result into the postings behind it.

A hit is usually a board's results page, not a job. This takes the URL patterns
already confirmed for that domain and crawls the individual postings, folding what
comes back into the rows the search has collected so far.
"""

from __future__ import annotations

from urllib.parse import urlsplit
from apify_client import ApifyClient
from ..text import (looks_like_error_page, dig)
from ..sources_norm import (strip_site_name_from_title)
from ..sources_urls import (load_discovered_job_patterns)
from ..apify import (WEBSITE_CONTENT_CRAWLER_ACTOR, _DEEP_CRAWL_MEMORY_MBYTES, crawl_urls_in_batches)
from .sites import (GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS, GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT, _DEEP_CRAWL_BATCH_SIZE)
from .queries import _is_excluded_job_board

def _crawl_domain(u):
    """The netloc of a URL, lowercased. Was nested inside _deepen_google_results; three
    of the functions below need it now."""
    return urlsplit(u or '').netloc.lower()


def all_job_url_patterns() -> dict:
    """The built-in patterns plus every one the app has discovered for itself.

    Discovered entries are merged in rather than replacing anything: a hand-written
    pattern for a domain always wins, since it was written deliberately.
    """
    merged = dict(GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS)
    for domain, entry in (load_discovered_job_patterns() or {}).items():
        if domain in merged:
            continue
        globs = (entry or {}).get('globs') or []
        if globs:
            merged[domain] = list(globs)
    return merged


def _known_pattern_domain(netloc: str) -> str | None:
    """The job-URL-pattern key this netloc belongs to, if any.

    Keys are bare registrable-ish domains (e.g. 'finn.no', 'arbeidsplassen.nav.no') --
    match a netloc like 'www.finn.no' against 'finn.no' by checking suffix, not exact
    equality. Consults discovered patterns too, so a site learned in an earlier search is
    treated exactly like one that shipped with the app.
    """
    for known_domain in all_job_url_patterns():
        if netloc == known_domain or netloc.endswith('.' + known_domain):
            return known_domain
    return None


def _deep_crawl_plan(rows: list[dict]):
    """Work out what the deep crawl should visit.

    Returns (known_rows, start_urls, include_globs, warned_domains). Pure -- no network,
    no actor -- so what gets crawled can be checked on its own.
    """
    known_rows = [
        r for r in rows
        # 'startup' included alongside 'known'/'global' so a future
        # GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS entry for a COUNTRY_STARTUP_SITES/
        # GLOBAL_STARTUP_SITES domain is picked up automatically, instead of silently
        # never being deep-crawled the way it would be if this stage were left out.
        if r.get('platform') == 'google' and r.get('google_stage') in ('known', 'global', 'startup')
    ]
    # Deliberately NOT `if not known_rows: return` any more. That short-circuit predated
    # open-stage crawling and skipped everything below when the only google results came
    # from the open web -- including the start_urls block, which is exactly where an
    # open-stage row with a learned pattern now belongs.

    # Sina asked for this directly: when a known-sites-stage result lands on a domain
    # with no confirmed job-URL pattern yet (GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS), tell
    # him how to help fix it -- rather than silently doing nothing for that domain like
    # before. Collected here (not logged individually) and merged by the caller with
    # _warn_zero_result_google_sites' own broken-domain list, so Sina gets ONE combined
    # short log line and ONE combined dialog for every domain that needs a hand this
    # run, regardless of which of the two checks found it.
    warned_domains = set()
    for r in known_rows:
        url = r.get('url')
        if not url:
            continue
        domain = _crawl_domain(url)
        if _known_pattern_domain(domain) or domain in warned_domains:
            continue
        warned_domains.add(domain)

    # Only worth calling the crawler at all if at least one result is on a domain we
    # actually have a confirmed job-URL pattern for.
    #
    # Drawn from EVERY google row, not just known_rows. The stage filter above is right for
    # deciding which domains to warn about, and wrong here: pattern discovery examines all
    # four stages, so a site first seen on the open web can end up with a verified, saved
    # pattern -- and this used to skip it forever. The run that learned it crawled it once
    # (crawl_newly_learned_sites), and every run after that quietly ignored it, so the
    # permanent thing that was learned was used exactly once. jobfluent.com and
    # arbeitnow.com are both in that position.
    #
    # Cost is unaffected: the _known_pattern_domain filter is what bounds this, and an
    # open-stage row only survives it if its domain already has a confirmed pattern.
    start_urls = [
        r['url'] for r in rows
        if r.get('platform') == 'google' and r.get('url')
        and _known_pattern_domain(_crawl_domain(r['url']))
    ]
    start_urls = list(dict.fromkeys(start_urls))
    if not start_urls:
        return known_rows, [], [], sorted(warned_domains)

    include_globs = sorted({
        pattern
        for u in start_urls
        for pattern in all_job_url_patterns().get(_known_pattern_domain(_crawl_domain(u)) or '', [])
    })
    return known_rows, start_urls, include_globs, sorted(warned_domains)


def _deep_crawl_run_input(start_urls: list[str], include_globs: list[str]) -> dict:
    """The actor configuration for the deep crawl.

    Split out because every value in here is a tuned constant with a real test behind it
    (see the timeout note), and those decisions are much easier to find and revisit when
    they are not buried in the middle of a 235-line function.
    """
    return {
        "startUrls": [{"url": u} for u in start_urls],
        "maxCrawlDepth": 1,
        "maxCrawlPages": len(start_urls) * GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT,
        "crawlerType": "playwright:adaptive",
        "htmlTransformer": "none",
        "includeUrlGlobs": include_globs,
        # A real live test found duunitori.fi caused this actor to hang for 10+ minutes
        # on a single start URL. maxRequestRetries is capped at 1 (down from the
        # actor's own default of 3) so one troubled site can only ever add
        # requestTimeoutSecs x 2 to the whole batched run, not an unbounded hang --
        # every other start URL bundled into the same call would otherwise wait on it
        # too. requestTimeoutSecs itself went through two real-tested revisions:
        # first dropped to 30s (from the actor's default 60s) purely to bound
        # duunitori.fi's hang -- but a later batch of 9 domains found a real, working
        # site (stepstone.de/.at) averaging ~40-42s per page under concurrent load
        # (despite loading in seconds when crawled alone), which 30s wrongly flagged as
        # unreachable. Restored to 60s (the actor's own original default) once isolated
        # re-tests confirmed duunitori.fi fails identically regardless of this value
        # (also tried 45s, cheerio, and playwright:chrome -- none worked, confirming
        # it's a hard site-side block, not a timing issue) -- so there was no
        # reliability reason to keep it below the default, and legitimate slow sites
        # like StepStone need the room.
        "requestTimeoutSecs": 60,
        "maxRequestRetries": 1,
    }


def _absorb_deep_crawl_items(crawled, rows: list[dict], known_rows: list[dict]):
    """Fold what the crawl returned back into `rows`.

    Returns (rescraped, added, excluded, domain_added_counts). Mutates `rows`: existing
    rows get a longer description where the crawl found one, genuinely new pages are
    appended. Pure apart from that -- no network -- so the merge rules can be tested on
    their own, which is where the referrer bug below was hiding.
    """
    # A newly-discovered linked page inherits the location/country of whichever
    # original Google result it was found under (matched by which domain started it).
    domain_to_row: dict[str, dict] = {}
    for r in known_rows:
        domain_to_row.setdefault(_crawl_domain(r.get('url')), r)
    url_to_row = {r['url']: r for r in known_rows if r.get('url')}

    rescraped = 0
    added = 0
    excluded = 0
    seen_urls = {r.get('url') for r in rows if r.get('url')}
    new_rows = []
    # Per-site breakdown for the log -- same idea as Known Websites: no live "Running"
    # state is possible (one combined crawler call covers every known-site domain at
    # once), so this counts each domain's own new-page total only once the whole call
    # is done, keyed by the KNOWN site the new page was reached from (not the domain of
    # the new page itself, which is the same domain here since crawling stays same-site).
    domain_added_counts: dict[str, int] = {}
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
            excluded += 1
            continue
        if url in url_to_row:
            row = url_to_row[url]
            if len(text) > len(row.get('description') or ''):
                row['description'] = text
                rescraped += 1
        else:
            if url in seen_urls:
                continue
            # The referrer is the EXACT original result this page was linked from, so
            # it's tried first. Real bug fixed here: this used to try the domain map
            # first and only fall back to the referrer, but domain_to_row is built with
            # setdefault -- it holds whichever result for that domain happened to come
            # FIRST -- and three domains are deliberately listed under several countries
            # (app.welcometothejungle.com under 7, wearedevelopers.com under 4), plus any
            # domain searched for both a country and its city. Since deep-crawling stays
            # same-domain, the domain lookup always succeeded and the accurate referrer
            # was never consulted, so e.g. a French Welcome-to-the-Jungle posting could be
            # stored as country='Canada' -- which then also drives the wrong Sponsorship
            # Visa badge.
            parent_row = url_to_row.get(dig(item, 'crawl.referrerUrl')) or domain_to_row.get(_crawl_domain(url))
            if not parent_row:
                continue
            new_rows.append({
                # A crawled page's title is its <title> tag, which usually ends in the site's
                # own name ("Data Engineer | FINN.no"). That is not part of the job.
                'title': strip_site_name_from_title(
                    dig(item, 'metadata.title') or item.get('title'), url),
                'company': None,
                'location': parent_row.get('location'),
                'country': parent_row.get('country'),
                'posted_date': None,
                'url': url,
                'description': text,
                'platform': 'google',
                'google_stage': parent_row.get('google_stage', 'known'),
            })
            seen_urls.add(url)
            added += 1
            bare = _known_pattern_domain(_crawl_domain(url))
            if bare:
                domain_added_counts[bare] = domain_added_counts.get(bare, 0) + 1

    rows.extend(new_rows)
    return rescraped, added, excluded, domain_added_counts


def _deepen_google_results(rows: list[dict], client: ApifyClient, progress_cb=None,
                           should_cancel=None, anthropic_api_key=None) -> tuple[int, int, int, list[str]]:
    """Only applies to results from the **known-sites and global-sites stages**
    (build_google_job_queries' first two queries per location: one restricted via
    `site:` to that country's curated major job boards -- e.g. finn.no for Norway --
    and one restricted to the fixed global extra sites in GOOGLE_GLOBAL_EXTRA_SITES,
    e.g. ziprecruiter.com -- tagged `google_stage == 'known'` or `'global'` respectively
    when the result was first normalized in run_search. Those are real, structured job
    boards, so when one of their result pages is itself a listing/search page rather
    than a single job (e.g. finn.no's own search results page), it very likely links
    directly to its own individual job postings on the same domain.

    This deliberately does NOT apply to open-web-stage results. A real test tried
    exactly that first -- deep-crawling every Google result, any domain, no restriction
    -- against a generic aggregator site and it was a clear failure: out of 113 new
    pages found, over 100 were irrelevant navigation (other countries' listing pages on
    the same site, category pages, company profile pages, even a Discord invite and an
    ad-tracking link), and the handful of genuinely-individual job pages it did surface
    were all in completely unrelated cities (Palo Alto, Cleveland, Cincinnati -- found
    while searching for Oslo). Open-web aggregator pages don't reliably expose their own
    same-domain job links the way a real job board does, so that broad approach was
    dropped entirely rather than kept as a fallback.

    Only URLs on a domain with an entry in GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS are worth
    deep-crawling at all -- two things had to be true at once for this to work, both
    found the hard way via real tests:
    1. `htmlTransformer: 'none'`. The actor's default content extraction (Mozilla's
       Readability) was found to sometimes pick entirely the wrong part of the page as
       "main content" -- on finn.no's own search results page, it picked the category
       filter sidebar instead of the job listings, so the real job links were never even
       looked at. `'none'` keeps the raw HTML instead of guessing.
    2. An explicit, per-site `includeUrlGlobs` pattern telling the crawler exactly which
       links are individual job postings (e.g. finn.no -> `/job/ad/**`). Without this,
       same-domain link-following found *zero* new pages even on real job boards
       (verified on finn.no itself) -- apparently the actor's default enqueueing doesn't
       reliably pick up on which links matter without being told.
    A domain missing from GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS is skipped for this pass
    entirely (its result is left as Google originally scraped it) -- several major sites
    were tested and found to not expose real job links at all even with both fixes
    applied (cookie walls, bot detection, or genuinely dynamic job cards).

    Mutates `rows` in place: a result's description is updated in place if the same URL
    re-scraped with more content; every newly discovered same-domain sub-page becomes a
    new row (inheriting the parent result's location/country), except pages on
    LinkedIn/Indeed/Glassdoor (still always excluded) or with no text at all. Returns
    (rescraped_count, added_count, excluded_count, no_pattern_domains) -- the last one
    is every domain seen this run with no confirmed GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS
    entry, for the caller to merge into the same broken-URLs dialog as
    _warn_zero_result_google_sites' own list (see run_search)."""
    known_rows, start_urls, include_globs, warned_domains = _deep_crawl_plan(rows)

    if not known_rows:
        return 0, 0, 0, []
    if not start_urls:
        return 0, 0, 0, warned_domains

    if progress_cb:
        # Live-ticking timer, started right before the one combined crawl call that
        # covers every known-job-board result page -- same reasoning as Known
        # Websites' own timer: this can take a while, and Sina asked for every Google
        # stage to show a real Running indicator, not just a summary once it's done.
        progress_cb("DEEP_CRAWL_START", 0, 1)

    crawled, unreachable, deep_crawl_usage_usd = crawl_urls_in_batches(
        client, WEBSITE_CONTENT_CRAWLER_ACTOR, start_urls,
        lambda batch: _deep_crawl_run_input(batch, include_globs),
        _DEEP_CRAWL_BATCH_SIZE, should_cancel=should_cancel, progress_cb=progress_cb,
        label='google', memory_mbytes=_DEEP_CRAWL_MEMORY_MBYTES)

    if unreachable and progress_cb:
        progress_cb(f"  ! {len(unreachable)} page(s) could not be crawled even one at a "
                    f"time: {', '.join(unreachable)[:120]}", 0, 1)
    if not crawled:
        if progress_cb:
            progress_cb("DEEP_CRAWL_HEADER:FAILED|", 0, 1)
            progress_cb("  ! Google deeper crawl collected nothing", 0, 1)
        return 0, 0, 0, warned_domains

    rescraped, added, excluded, domain_added_counts = _absorb_deep_crawl_items(
        crawled, rows, known_rows,
    )

    if progress_cb:
        # Always stops the DEEP_CRAWL_START timer, even with zero new pages found, so
        # it never ticks forever -- per-site lines only added when there's something
        # to show.
        progress_cb(f"DEEP_CRAWL_HEADER:SUCCESS|{deep_crawl_usage_usd}", 0, 1)
        for domain, count in sorted(domain_added_counts.items()):
            progress_cb(f"DEEP_CRAWL_SITE_RESULT:{domain}|{count}", 0, 1)
    return rescraped, added, excluded, warned_domains
