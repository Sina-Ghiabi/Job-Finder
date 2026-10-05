# -*- coding: utf-8 -*-
"""Working out how a site nobody has seen before builds its job links.

Google keeps surfacing sites the app has no pattern for. Rather than skip them, this
opens a real posting, derives the URL shape that would have found it, verifies the
shape against the page, and saves it -- so the cost of learning a site is paid once.
"""

from __future__ import annotations

import fnmatch
from ..text import (text_of)
from ..fetcher import (recall_strategy)
from ..sources_urls import (save_discovered_job_pattern)
from ..apify import (WEBSITE_CONTENT_CRAWLER_ACTOR, _DEEP_CRAWL_MEMORY_MBYTES, crawl_urls_in_batches)
from .sites import (_PATTERN_CRAWL_BATCH_SIZE, _MAX_PATTERN_DISCOVERIES_PER_RUN)
from .deepen import (_absorb_deep_crawl_items, _crawl_domain,
                     _deep_crawl_run_input, _known_pattern_domain)

def _domains_worth_learning(rows):
    """The Google domains this run met that Job Finder cannot read yet, one page each.

    One page per domain is enough -- the pattern is a property of the site, not of the
    posting -- and a domain whose pattern is already known is skipped, so a run only ever
    pays attention to what it does not have.
    """
    page_for_domain = {}
    for row in rows:
        if row.get('platform') != 'google':
            continue
        url = row.get('url')
        if not url:
            continue
        domain = _crawl_domain(url)
        if not domain or domain in page_for_domain:
            continue
        if _known_pattern_domain(domain):
            continue
        page_for_domain[domain] = url
    return page_for_domain


def _learn_one_domain(domain, listing_url, client, progress_cb):
    """Work out one site's job-link pattern, and say which way it failed if it did.

    Three outcomes, and telling them apart is the point: the pattern was found and saved;
    discovery crashed (which used to be swallowed, so a crash looked exactly like an
    unreadable site and could repeat every run with nothing in the Log); or the page could
    not be read at all. Returns the globs found, or an empty list.
    """
    # Imported here, not at module level: pattern_discovery imports back into this package.
    from ..pattern_discovery import discover_job_url_patterns_smart

    try:
        globs = discover_job_url_patterns_smart(listing_url, client=client,
                                                progress_cb=progress_cb)
    except Exception as e:
        if progress_cb:
            progress_cb('GLOG:pattern|error|%s: working out its job links failed (%s).'
                        % (domain, e), 0, 1)
        return []

    if globs:
        save_discovered_job_pattern(domain, globs)
        if progress_cb:
            progress_cb('PATTERN_SITE_RESULT:%s|%d' % (domain, len(globs)), 0, 1)
        return globs

    # Say WHICH of the two failures it was, because they mean different things and the
    # fetch ladder already knows: it records per domain which rung worked, and an empty
    # record means every rung failed -- including the headless browser. This used to
    # re-fetch the page to find out; the answer is already on disk.
    if progress_cb:
        if not recall_strategy(domain):
            why = ('nothing could open it -- a plain request, a Chrome TLS fingerprint, '
                   'a search-engine identity and a real headless browser were all refused')
        else:
            why = ('it opens, but nothing on the page is recognisable as a job listing '
                   '(opened via the %s route)' % recall_strategy(domain))
        progress_cb('GLOG:pattern|error|%s: %s. Its listing page is kept either way.'
                    % (domain, why), 0, 1)
    return []


def learn_missing_job_patterns(rows, anthropic_api_key=None, progress_cb=None,
                               should_cancel=None) -> dict:
    """Work out the job-URL pattern for every Google domain Job Finder cannot read yet.

    Takes the FULL row set, not the deep crawl's subset. An earlier version was called
    from inside _deepen_google_results and so inherited its filter -- only rows tagged
    google_stage known/global/startup -- which excluded the open-web stage entirely. That
    is deliberate for the paid CRAWL, and meaningless for discovery, which is free: it
    meant one domain was examined out of nineteen, so nothing was ever learned.

    For each domain the page to examine is one already collected from that site. Whatever
    is learned is saved permanently, so the cost is paid once per site, ever -- every
    later search treats it exactly like a built-in pattern.

    Returns {domain: (listing_url, globs)} for the sites learned THIS run, so the caller
    can go back and collect their postings immediately. Saving a pattern and not acting on
    it leaves the jobs behind the page it came from -- which is exactly what the first
    real run did, learning three sites and collecting nothing from any of them.
    """
    # One page per domain that has no pattern yet -- across EVERY google row, whatever
    # stage produced it.
    page_for_domain = _domains_worth_learning(rows)

    targets = list(page_for_domain.items())[:_MAX_PATTERN_DISCOVERIES_PER_RUN]
    if not targets:
        return {}

    client = None
    if anthropic_api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_api_key)
        except Exception as e:
            # Silently losing this dropped discovery to its structural heuristics alone,
            # with nothing to explain why a site that Claude could have read was skipped.
            client = None
            if progress_cb:
                progress_cb('GLOG:pattern|error|Claude could not be reached for pattern '
                            'discovery (%s) — sites are still analysed structurally, but '
                            'the ones needing a second opinion will be missed.' % e, 0, 1)

    if progress_cb:
        progress_cb('PATTERN_DISCOVERY_START', 0, 1)
        progress_cb(
            'GLOG:pattern|info|%d site(s) returned a page full of jobs that Job Finder '
            "could not read yet — working out how each one builds its job links…"
            % len(targets), 0, 1)

    learned_sites = {}
    needs_a_browser = []
    for domain, listing_url in targets:
        if should_cancel and should_cancel():
            break
        globs = _learn_one_domain(domain, listing_url, client, progress_cb)
        if globs:
            learned_sites[domain] = (listing_url, globs)
        else:
            needs_a_browser.append(domain)

    if progress_cb:
        progress_cb(
            'GLOG:pattern|success|Learned how %d of %d new site(s) build their job links. '
            'These are remembered for every future search.' % (len(learned_sites), len(targets)),
            0, 1)
        if needs_a_browser:
            progress_cb(
                'GLOG:pattern|error|%d site(s) could not be read at all: %s'
                % (len(needs_a_browser), ', '.join(sorted(needs_a_browser)[:6])), 0, 1)
        progress_cb('PATTERN_DISCOVERY_END', 0, 1)
    return learned_sites


def crawl_newly_learned_sites(rows, client, learned_sites, progress_cb=None,
                              should_cancel=None) -> int:
    """Go straight back to the sites just learned and collect their postings.

    Without this, learning is inert for the run that did it: the first real Germany search
    learned three sites and collected nothing from any of them, because the deep crawl had
    already finished. agentic-engineering-jobs.com kept its single /jobs/germany listing
    row while its postings stayed unreachable.

    Deliberately small: the start URLs are only the listing pages of the sites just
    learned, with only their own freshly-verified globs, so the cost scales with what was
    actually learned rather than with the size of the run.
    """
    if not learned_sites:
        return 0
    start_urls = [listing for listing, _globs in learned_sites.values() if listing]
    include_globs = sorted({g for _listing, globs in learned_sites.values() for g in globs})
    if not start_urls or not include_globs:
        return 0

    if progress_cb:
        progress_cb('PATTERN_CRAWL_START', 0, 1)
        progress_cb(
            'GLOG:pattern|info|Going back to %d newly-understood site(s) to collect the '
            'jobs behind their listing pages, %d at a time. A batch Apify is too busy for '
            'is waited on and tried again, then split, so none are lost.'
            % (len(start_urls), _PATTERN_CRAWL_BATCH_SIZE), 0, 1)

    crawled, unreachable, spent = crawl_urls_in_batches(
        client, WEBSITE_CONTENT_CRAWLER_ACTOR, start_urls,
        lambda batch: _deep_crawl_run_input(batch, include_globs),
        _PATTERN_CRAWL_BATCH_SIZE, should_cancel=should_cancel, progress_cb=progress_cb,
        label='pattern', memory_mbytes=_DEEP_CRAWL_MEMORY_MBYTES)
    usage = ('%.4f' % spent) if spent else None

    if unreachable and progress_cb:
        progress_cb('GLOG:pattern|warning|%d listing page(s) could not be crawled even one '
                    'at a time: %s' % (len(unreachable), ', '.join(unreachable)[:120]), 0, 1)
    if not crawled:
        if progress_cb:
            progress_cb('PATTERN_CRAWL_END', 0, 1)
            progress_cb('GLOG:pattern|error|Nothing could be collected from the '
                        'newly-understood sites. Their patterns are still saved for the '
                        'next search.', 0, 1)
        return 0

    # The listing rows themselves are the parents these postings inherit location from.
    parents = [r for r in rows
               if any(fnmatch.fnmatch(text_of(r.get('url')), g) or
                      text_of(r.get('url')) in start_urls for g in include_globs)]
    if not parents:
        parents = [r for r in rows if text_of(r.get('url')) in start_urls]
    _rescraped, added, _excluded, domain_counts = _absorb_deep_crawl_items(
        crawled, rows, parents or rows)

    if progress_cb:
        for domain, count in sorted(domain_counts.items()):
            progress_cb('PATTERN_CRAWL_SITE_RESULT:%s|%d' % (domain, count), 0, 1)
        progress_cb(
            'GLOG:pattern|success|Collected %d job(s) from the newly-understood site(s)%s.'
            % (added, (' ($%s)' % usage) if usage else ''), 0, 1)
        progress_cb('PATTERN_CRAWL_END', 0, 1)
    return added
