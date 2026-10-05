"""Sites that need a real browser -- now opened by one, not by Sina.

These sites were collected because Apify's crawler could not read them: a consent wall, a
bot check, or a list rendered entirely in JavaScript. The original mechanism was honest
about that and asked for help -- it opened a visible Chrome window, waited for Sina to
clear whatever was in the way, and read the page he ended up on.

Everything that made the human necessary is now done by the fetch ladder. It sends a
request with Chrome's TLS fingerprint, identifies as a crawler where a site wants one,
and, failing both, drives a headless browser that runs the page's JavaScript and clicks
its consent button. That is the whole of what the human was there for.

So the sites stay and the interruption goes. The tables in sources_urls are real work --
verified search URLs and verified job-link prefixes for duunitori.fi, seek.com.au,
work.turing.com and the rest -- and deleting them along with the mechanism would have
quietly dropped every listing those sites carry.

What a site cannot do any more is ask for help. If the ladder cannot open it, that is
reported as a problem for the pre-flight window rather than a request that Sina go and
look at it himself.
"""
from __future__ import annotations

from .. import fetcher
from ..sources_urls import (
    MANUAL_ASSIST_GLOBAL_SITES,
    MANUAL_ASSIST_SITES,
    _MANUAL_ASSIST_DESCRIPTION_MAX_CHARS,
    _extract_manual_assist_job_links,
)

# A posting page is fetched without the browser rung: these are individual job pages on a
# site the ladder has already opened once, and the rung that worked for the listing is
# remembered per domain anyway. Paying for a browser launch per posting would turn a fast
# stage into a slow one for a page that almost never needs it.
BROWSER_SITE_MAX_POSTINGS = 20


def _page_text(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    return ' '.join(soup.get_text(' ').split())[:_MANUAL_ASSIST_DESCRIPTION_MAX_CHARS]


def _page_title(html: str, fallback: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    title = ' '.join((soup.title.string or '').split()) if soup.title else ''
    return title or fallback


def _search_one_site(domain, site, cities, rows, progress_cb, should_cancel) -> tuple[int, dict | None]:
    """Open one site through the ladder and collect what it yields.

    Returns (rows added, problem or None). The problem is what used to be a request for
    help: a dict the pre-flight window can show, naming the domain and why it stayed shut.
    """
    country = site['country']
    url = site['url'](cities)

    result = fetcher.fetch(url, needs_links=True, progress_cb=progress_cb)
    if not result.accepted:
        # Three different failures, and saying which one matters. The first real run of
        # this stage reported "nationalevacaturebank.nl: could not be opened -- HTTP 200",
        # which is nonsense: the page arrived, it simply held no links. That is a consent
        # wall or a JavaScript shell, not a block, and it is acted on differently.
        if result.status is None:
            short, long = 'no response at all', 'The site did not respond at all'
        elif result.status != 200:
            short = 'HTTP %s' % result.status
            long = 'The search page was refused (HTTP %s)' % result.status
        else:
            short = 'the page loaded but held no links'
            long = ('The search page loaded but contained no links at all — a consent wall '
                    'or a page that builds its list in JavaScript that did not render')
        if progress_cb:
            progress_cb('GLOG:browser_sites|error|%s (%s): could not be read -- %s.'
                        % (domain, country, short), 0, 1)
        return 0, {
            'name': '%s (%s)' % (domain, country),
            'reason': '%s. Every route was tried: a plain request, a Chrome TLS '
                      'fingerprint, a search-engine identity, and a real headless browser.'
                      % long,
            'fixable': False,
            'kind': 'url',
            'url': url,
        }

    job_links = []
    if site['job_link_glob']:
        job_links = _extract_manual_assist_job_links(
            result.html, url, site['job_link_glob'], limit=BROWSER_SITE_MAX_POSTINGS)

    added = 0
    if job_links:
        for job_url in job_links:
            if should_cancel and should_cancel():
                break
            posting = fetcher.fetch(job_url, allow_browser=False)
            if not posting.ok:
                continue
            rows.append({
                'title': _page_title(posting.html, domain),
                'company': None,
                'location': None,
                'country': country,
                'posted_date': None,
                'url': job_url,
                'description': _page_text(posting.html),
                # The real source, not 'google'. Tagging these 'google' also made them
                # count as evidence the domain was healthy in _warn_zero_result_google_sites,
                # suppressing the warning for a domain whose own site: query found nothing.
                'platform': domain,
                'google_stage': 'known',
            })
            added += 1
        if progress_cb:
            progress_cb('GLOG:browser_sites|success|%s (%s): %d job posting(s) found via %s.'
                        % (domain, country, added, result.strategy), 0, 1)
        return added, None

    # No confirmed job-link pattern for this domain, or none matched. Same honest fallback
    # as everywhere else: keep the listing page itself as one row rather than nothing.
    rows.append({
        'title': _page_title(result.html, domain),
        'company': None,
        'location': None,
        'country': country,
        'posted_date': None,
        'url': url,
        'description': _page_text(result.html),
        'platform': domain,
        'google_stage': 'known',
    })
    if progress_cb:
        progress_cb('GLOG:browser_sites|success|%s (%s): opened via %s, kept the listing page '
                    '(no confirmed individual-posting pattern for this site).'
                    % (domain, country, result.strategy), 0, 1)
    return 1, None


def _run_browser_site_search(rows: list[dict], countries: list[str], cities: list[str] | None = None,
                             progress_cb=None, should_cancel=None,
                             problems: list | None = None) -> None:
    """Additive, same principle as the other direct-search stages -- only ever adds rows.

    `problems` collects the sites that stayed shut, for the pre-flight window to report.
    """
    cities = cities or []
    relevant = [(domain, site) for domain, site in MANUAL_ASSIST_SITES.items()
                if site['country'] in countries]
    # Global sites run every time, independent of which countries are selected -- given a
    # 'country' label here (not on the dict itself) purely so the loop can tag rows.
    relevant += [(domain, {**site, 'country': 'Global'})
                 for domain, site in MANUAL_ASSIST_GLOBAL_SITES.items()]
    if not relevant:
        return

    if progress_cb:
        progress_cb('BROWSER_SITES_START', 0, 1)
        progress_cb('GLOG:browser_sites|info|Opening %d site(s) that need a real browser…'
                    % len(relevant), 0, 1)

    added = 0
    for domain, site in relevant:
        if should_cancel and should_cancel():
            break
        try:
            site_added, problem = _search_one_site(
                domain, site, cities, rows, progress_cb, should_cancel)
        except Exception as e:
            # Deliberately not rebuilding the URL here: the site's own url() callable is
            # one of the things that could have raised, and calling it again inside the
            # handler would turn a reported problem into a crashed stage.
            site_added, problem = 0, {
                'name': '%s (%s)' % (domain, site['country']),
                'reason': 'Failed while being read: %s' % e,
                'fixable': False, 'kind': 'url',
            }
            if progress_cb:
                progress_cb('GLOG:browser_sites|error|%s: %s' % (domain, e), 0, 1)
        added += site_added
        if problem is not None and problems is not None:
            problems.append(problem)

    if progress_cb:
        progress_cb('GLOG:browser_sites|info|Browser-site search done: %d row(s) added.'
                    % added, 0, 1)
        progress_cb('BROWSER_SITES_END', 0, 1)
