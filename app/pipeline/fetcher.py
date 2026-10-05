"""Open a page that does not want to be opened.

Eight job sites defeated plain `requests`, and measuring each one showed that "blocked"
was never a single condition. They failed for four different reasons, each with its own
answer:

  * startup.jobs, en.devjobs.de returned 403 to requests and 200 to the identical request
    sent with Chrome's real TLS fingerprint. The block never looked at the page or the
    headers -- Python's TLS handshake is recognisable on sight, and that alone was the
    whole barrier.
  * datacareer.de refuses every browser-shaped user agent, ours included, and answers
    `curl/8.4.0` and Googlebot with the full 19,344-character listing. It is not defending
    against crawlers; it is defending against things pretending to be browsers.
  * englishjobs.de and jobfluent.com arrive fine but render their list in JavaScript, so
    the HTML that comes back is a shell.
  * germantechjobs.de is not blocked at all. It redirects to a JobCopilot signup page,
    because the job board behind it no longer exists. No technique reaches a site that
    is gone, and pretending otherwise would waste a browser launch on every run forever.

So this is a ladder, cheapest rung first, and a page is fetched by climbing until one
works. Most sites are answered on rung one in a few hundred milliseconds; a site needs
the browser only if all three cheap rungs failed, and then only once, because the rung
that worked is written down per domain and used directly from then on.

What counts as success is deliberately stricter than HTTP 200: a consent wall, a
Cloudflare interstitial and an nginx error page are all 200 with a body. `_is_usable`
judges the page, and the caller can demand more -- discovery asks for links, since a
shell that parses cleanly but holds nothing is a failure for its purposes even though
the request succeeded.
"""
from __future__ import annotations

import re
import threading
import time
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from .text import looks_like_error_page, text_of

# Bumped when a rung is added or its behaviour changes, so that domains recorded as
# needing an expensive rung -- or as unreachable -- are re-tried under the new ladder
# instead of being trusted forever. Same contract as the pattern verifier's version.
FETCHER_VERSION = 2

FETCH_TIMEOUT_SECONDS = 25
BROWSER_TIMEOUT_MS = 50000

# Rung 5's budget. It is generous on purpose: this rung is only ever reached after four
# cheaper ones have failed, it runs a real browser on Apify's side, and the measured times
# for pages it successfully opened ran from 9s (reed.co.uk) to 60s (glassdoor.com).
APIFY_FETCH_TIMEOUT_SECONDS = 180

# Rung 1 and 2 present themselves as a normal browser, which is what almost every site
# expects to see.
BROWSER_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')

# Rung 3 stops pretending. Sites that block browser-shaped agents are usually serving a
# search engine on purpose -- their own robots.txt invites it -- and identifying honestly
# as a crawler is what they are set up to answer.
CRAWLER_UA = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'

BASE_HEADERS = {'Accept-Language': 'en-US,en;q=0.9,de;q=0.8'}

STRATEGIES = ('plain', 'chrome_tls', 'crawler', 'browser', 'apify')

# Rung 5. Apify's own free SuperScraper endpoint: a real browser on THEIR machines, behind
# THEIR proxy pool. This is not the same thing as the Apify proxy, which was tried earlier
# and refuses every request made from this desktop on the free plan -- the difference is
# that the fetch happens inside Apify's network, which is where that proxy is meant to be
# used from.
#
# Measured against the twelve hosts the local ladder genuinely cannot open (403 or 429 with
# a challenge page, not a 404 on an expired posting): it opened EIGHT of them, with real
# content, including several this app searches directly --
#
#     glassdoor.com 981 KB   cv-library.co.uk 699 KB   stepstone.at 510 KB
#     cwjobs.co.uk  457 KB   reed.co.uk       406 KB   totaljobs.com 295 KB
#     moovijob.com  273 KB   tecnoempleo.com   76 KB
#
# Four are still shut: stepstone.de (an HTTP/2 protocol error on Apify's side, though
# stepstone.de is separately reached through an Apify actor that returned 260 rows in a
# real search), seek.com.au and duunitori.fi (403 even on residential IPs), and jobly.fi.
#
# One warning worth keeping, because it cost a completely wrong measurement: the free
# plan's standby actor drops concurrent connections. Probing six of these at once returned
# "Connection aborted" for all six -- including two that a one-at-a-time probe had just
# opened. Requests through this rung are therefore serialised, exactly like the browser.
_APIFY_SCRAPER_ENDPOINT = 'https://super-scraper-api.apify.actor/'
_APIFY_TOKEN: list = [None]
_APIFY_LOCK = threading.Lock()

# One retry, then a longer one, for a dropped connection only -- see _rung_apify.
_APIFY_ATTEMPTS = 3
_APIFY_RETRY_SECONDS = 4


def set_apify_token(token) -> None:
    """Hands the ladder its fifth rung. Called once per run, before any fetching.

    Without a token this rung is simply skipped, so nothing else in the app has to know
    whether it is available -- an unconfigured RoleHound behaves exactly as it did before.
    """
    _APIFY_TOKEN[0] = (token or '').strip() or None

# Playwright's sync API is not safe to drive from two threads at once, and enrichment runs
# eight workers. The three cheap rungs are fully parallel; only the browser serialises.
_BROWSER_LOCK = threading.Lock()

# One curl_cffi session per thread, never one shared between them.
#
# A three-hour German search died with a segmentation fault -- no Python traceback, the
# process killed outright, every listing collected up to that point gone with it. It
# happened part-way through a stage fetching 722 pages eight threads at a time, which is
# what these two rungs are doing whenever the enrichment or expansion pools are running.
#
# `curl_requests.get(...)` builds a throwaway session per call over a CFFI binding to
# libcurl. Sessions are meant to be per-thread and reused; hundreds of them being created
# and destroyed concurrently is the documented way to get exactly this crash, and a crash
# inside a C library cannot be caught, retried or logged by anything in Python.
#
# This is the strongest candidate rather than a proven cause -- a segfault leaves nothing
# behind to read, and the crash is probabilistic, so "it did not happen again" would prove
# little either way. The fix is standard practice for this library and costs nothing: a
# thread-local session is reused instead of rebuilt, which is also faster.
_CURL_SESSIONS = threading.local()


def _curl_session(curl_requests):
    """This thread's curl_cffi session, made once and kept."""
    session = getattr(_CURL_SESSIONS, 'session', None)
    if session is None:
        session = curl_requests.Session()
        _CURL_SESSIONS.session = session
    return session


class FetchResult:
    """What came back, and which rung produced it.

    `ok` and `accepted` are deliberately different questions. `ok` means a page arrived.
    `accepted` means it also satisfied what the caller asked for -- so a JavaScript shell
    fetched with `needs_links=True` is `ok` and not `accepted`. The best failed attempt is
    still returned rather than nothing, since a partial page beats no page for a caller
    that can use it, but nothing should mistake it for a success.
    """

    __slots__ = ('status', 'html', 'strategy', 'accepted')

    def __init__(self, status, html: str = '', strategy: str = '', accepted: bool = False):
        self.status = status
        self.html = html or ''
        self.strategy = strategy
        self.accepted = accepted

    @property
    def ok(self) -> bool:
        return self.status == 200 and bool(self.html)

    def soup(self):
        return BeautifulSoup(self.html, 'html.parser') if self.html else None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return 'FetchResult(status=%r, strategy=%r, accepted=%r, %d chars)' % (
            self.status, self.strategy, self.accepted, len(self.html))


_TITLE_TAG = re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S)

# Above this much raw HTML the readable body is certainly past looks_like_error_page's
# 1200-character body threshold, so only the title can decide and the parse is wasted work.
# This runs on every fetch of every row, so the parse is worth skipping where it cannot
# change the answer.
_SURELY_LONG_HTML = 40000


def _is_usable(html: str) -> bool:
    """A 200 that is actually the page, not a wall wearing its status code.

    aijobs.ai once stored an HTTP 429 notice as a job description -- title "429", 607
    characters of real text -- because the status line said 200 and the body parsed. The
    same check that caught it is reused here, one rung earlier.
    """
    if not html:
        return False
    match = _TITLE_TAG.search(html)
    title = text_of(re.sub(r'<[^>]+>', ' ', match.group(1))) if match else ''
    if len(html) > _SURELY_LONG_HTML:
        return not looks_like_error_page(title, 'x' * (_SURELY_LONG_HTML // 4))
    body = ' '.join(BeautifulSoup(html, 'html.parser').get_text(' ').split())
    return not looks_like_error_page(title, body)


def same_domain_links(soup, base_url: str) -> list[str]:
    """Links on the page that stay on the site. Used to tell a rendered page from a shell."""
    host = urlsplit(base_url).netloc.lower()
    seen, out = set(), []
    for anchor in (soup.find_all('a', href=True) if soup else []):
        full = urljoin(base_url, anchor['href']).split('#')[0]
        if urlsplit(full).netloc.lower() == host and full not in seen:
            seen.add(full)
            out.append(full)
    return out


# --------------------------------------------------------------------------------------
# the rungs
# --------------------------------------------------------------------------------------
def _rung_plain(url: str) -> FetchResult:
    """What the app has always done. Fastest, and right for the large majority of sites."""
    headers = dict(BASE_HEADERS, **{'User-Agent': BROWSER_UA})
    try:
        response = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS, headers=headers)
        return FetchResult(response.status_code, response.text, 'plain')
    except Exception:
        return FetchResult(None, '', 'plain')


# A rung that is missing its library is a capability the app has silently lost: every site
# that needs it fails, and nothing anywhere says why. Recorded once and reported through
# the first progress_cb that comes along, rather than per request -- the point is to say it
# at all, not to say it four hundred times.
_MISSING_CAPABILITIES: list[str] = []


def _record_missing_capability(message: str) -> None:
    if message not in _MISSING_CAPABILITIES:
        _MISSING_CAPABILITIES.append(message)


def take_missing_capabilities() -> list[str]:
    """Rungs that could not load, and clears the list."""
    missing = list(_MISSING_CAPABILITIES)
    _MISSING_CAPABILITIES.clear()
    return missing


_CAPABILITIES_REPORTED = {'done': False}


def _report_missing_capabilities(progress_cb) -> None:
    """Say once, up front, if a rung is unavailable in this build.

    Checked directly rather than waiting for a rung to be reached and fail: a site that
    needs rung 2 might be the only one all run, and the reason it failed would then be
    reported only after it had already been given up on -- or, if that fetch had no
    progress callback, not at all.
    """
    if _CAPABILITIES_REPORTED['done']:
        return
    _CAPABILITIES_REPORTED['done'] = True
    try:
        import importlib
        importlib.import_module('curl_cffi.requests')
    except Exception as e:
        _record_missing_capability(
            'The curl_cffi library could not be loaded (%s), so two of the four ways of '
            'opening a blocked site are unavailable. Sites that answer 403 to a plain '
            'request will now fail. This is a RoleHound packaging problem, not a website '
            'problem.' % e)
    try:
        importlib.import_module('playwright.sync_api')
    except Exception as e:
        _record_missing_capability(
            'Playwright could not be loaded (%s), so the last resort -- a real headless '
            'browser -- is unavailable. Sites that build their job list in JavaScript '
            'cannot be read. This is a RoleHound packaging problem, not a website problem.'
            % e)
    for missing in take_missing_capabilities():
        progress_cb('GLOG:fetch|error|%s' % missing, 0, 1)


def _curl_get(url: str, user_agent: str, strategy: str) -> FetchResult:
    """The same request, but over a TLS handshake indistinguishable from Chrome's.

    curl_cffi is optional on purpose: if it is missing the ladder simply loses two rungs
    and the app still runs, rather than failing to import. That is the right behaviour and
    a dangerous one to leave quiet -- those two rungs are what open every site that answers
    403 to a plain request, so losing them turns "this site blocks us" into the permanent
    answer for sites that were working the day before.
    """
    try:
        from curl_cffi import requests as curl_requests
    except Exception as e:
        _record_missing_capability(
            'The curl_cffi library could not be loaded (%s), so two of the four ways of '
            'opening a blocked site are unavailable. Sites that answer 403 to a plain '
            'request will now fail. This is a RoleHound packaging problem, not a website '
            'problem.' % e)
        return FetchResult(None, '', strategy)
    headers = dict(BASE_HEADERS, **{'User-Agent': user_agent})
    try:
        response = _curl_session(curl_requests).get(
            url, impersonate='chrome', headers=headers, timeout=FETCH_TIMEOUT_SECONDS)
        return FetchResult(response.status_code, response.text, strategy)
    except Exception:
        return FetchResult(None, '', strategy)


def _rung_chrome_tls(url: str) -> FetchResult:
    return _curl_get(url, BROWSER_UA, 'chrome_tls')


def _rung_crawler(url: str) -> FetchResult:
    return _curl_get(url, CRAWLER_UA, 'crawler')


# Patches applied before any of the page's own scripts run. A headless Chrome otherwise
# announces itself through navigator.webdriver, an empty plugin list and a missing
# chrome.runtime, and those three are exactly what a bot wall reads.
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins',
    {get: () => [1,2,3,4,5].map(i => ({name: 'Plugin ' + i}))});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en','de']});
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}};
const _query = window.navigator.permissions.query;
window.navigator.permissions.query = (p) => (
    p.name === 'notifications'
      ? Promise.resolve({state: Notification.permission})
      : _query(p));
const _getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return _getParameter.call(this, p);
};
"""

# The label on the button that clears a consent wall, in the languages these sites use.
# Matched on the whole label so that "Accept" is dismissed and "Accept job offer" is not.
_CONSENT_LABEL = re.compile(
    r'^(accept|accept all|accept all cookies|allow all|agree|i agree|got it|ok|okay|'
    r'continue|alle akzeptieren|akzeptieren|alle cookies akzeptieren|zustimmen|'
    r'einverstanden|verstanden|aceptar|aceptar todo|accepter|tout accepter)$', re.I)


def _dismiss_consent(page) -> bool:
    for element in page.query_selector_all('button, a[role=button], div[role=button]'):
        try:
            label = ' '.join((element.inner_text() or '').split())
        except Exception:
            continue
        if label and _CONSENT_LABEL.match(label):
            try:
                element.click(timeout=3000)
                page.wait_for_timeout(2000)
                return True
            except Exception:
                pass
    return False


def _rung_browser(url: str) -> FetchResult:
    """A real browser: runs the page's JavaScript, clears its consent wall, scrolls it.

    The last rung and the slowest -- a launch plus render is seconds, not milliseconds --
    so it is reached only when the three cheap rungs have all failed, and the result is
    remembered per domain so it is reached at most once per site.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _record_missing_capability(
            'Playwright could not be loaded (%s), so the last resort -- a real headless '
            'browser -- is unavailable. Sites that build their job list in JavaScript '
            'cannot be read. This is a RoleHound packaging problem, not a website problem.'
            % e)
        return FetchResult(None, '', 'browser')

    with _BROWSER_LOCK:
        try:
            with sync_playwright() as playwright:
                browser = None
                for channel in ('chrome', 'msedge', None):
                    try:
                        browser = (playwright.chromium.launch(channel=channel, headless=True)
                                   if channel else
                                   playwright.chromium.launch(headless=True))
                        break
                    except Exception:
                        continue
                if browser is None:
                    return FetchResult(None, '', 'browser')
                try:
                    context = browser.new_context(
                        user_agent=BROWSER_UA,
                        viewport={'width': 1440, 'height': 900},
                        locale='en-US', timezone_id='Europe/Berlin',
                        extra_http_headers=dict(BASE_HEADERS))
                    context.add_init_script(_STEALTH_JS)
                    page = context.new_page()
                    response = page.goto(url, timeout=BROWSER_TIMEOUT_MS,
                                         wait_until='domcontentloaded')
                    page.wait_for_timeout(2500)
                    _dismiss_consent(page)
                    # A lazily-loaded list only renders what has been scrolled into view.
                    for _ in range(3):
                        page.mouse.wheel(0, 4000)
                        page.wait_for_timeout(1000)
                    try:
                        page.wait_for_load_state('networkidle', timeout=6000)
                    except Exception:
                        pass
                    html = page.content()
                    status = response.status if response is not None else 200
                    return FetchResult(status, html, 'browser')
                finally:
                    browser.close()
        except Exception:
            return FetchResult(None, '', 'browser')


def _rung_apify(url: str) -> FetchResult:
    """Fetch through Apify's SuperScraper. Never raises; a missing token is a plain miss.

    The plain call is tried first and the residential-proxy one only if it fails, because
    the plain one opened all eight of the sites this rung actually rescues -- premium was
    measured to add nothing on any of them, so paying for it up front would be spending
    Sina's Apify credit on nothing.
    """
    token = _APIFY_TOKEN[0]
    if not token:
        return FetchResult(None, '', 'apify')
    for extra in ({}, {'premium_proxy': 'true'}):
        params = {'url': url, 'token': token}
        params.update(extra)
        for attempt in range(_APIFY_ATTEMPTS):
            try:
                with _APIFY_LOCK:
                    response = requests.get(_APIFY_SCRAPER_ENDPOINT, params=params,
                                            timeout=APIFY_FETCH_TIMEOUT_SECONDS)
            except Exception:
                # Almost always the free plan's standby actor dropping the connection
                # rather than anything about the site -- totaljobs.com opened on its own
                # and failed on the request that followed a 22-second glassdoor fetch.
                # Worth waiting out, because the alternative is recording a reachable
                # domain as permanently shut.
                if attempt < _APIFY_ATTEMPTS - 1:
                    time.sleep(_APIFY_RETRY_SECONDS * (attempt + 1))
                continue
            if response.status_code == 200 and response.text:
                return FetchResult(200, response.text, 'apify')
            break       # a real answer, just not a usable one: try the next setting
    return FetchResult(None, '', 'apify')


_RUNGS = {
    'plain': _rung_plain,
    'chrome_tls': _rung_chrome_tls,
    'crawler': _rung_crawler,
    'browser': _rung_browser,
    'apify': _rung_apify,
}


# --------------------------------------------------------------------------------------
# the ladder
# --------------------------------------------------------------------------------------
def fetch(url: str, *, needs_links: bool = False, allow_browser: bool = True,
          progress_cb=None) -> FetchResult:
    """Climb the ladder until the page comes back usable. Never raises.

    `needs_links` makes a link-less page a failure rather than a success, which is what
    discovery needs: englishjobs.de answers rung one with a 200 whose body is a shell, and
    accepting that would stop the climb one rung short of the browser that renders it.
    """
    domain = urlsplit(url).netloc.lower()
    order = _strategy_order(domain, allow_browser)
    last = FetchResult(None, '', '')

    if progress_cb is not None:
        _report_missing_capabilities(progress_cb)

    def better(candidate: FetchResult, incumbent: FetchResult) -> bool:
        """Which failed attempt describes the site more truthfully?

        This used to keep whichever rung ran LAST, so the reported reason depended on the
        order the rungs happened to be tried in. nationalevacaturebank.nl answers 200 to a
        Chrome fingerprint and 403 to a crawler identity, and was reported as "refused the
        request (HTTP 403)" on one run and "loaded but held no links" on the next -- two
        different diagnoses of one site, only the second of which is true.
        """
        if candidate.status is None:
            return False
        if incumbent.status is None:
            return True
        if (candidate.status == 200) != (incumbent.status == 200):
            return candidate.status == 200
        return len(candidate.html) > len(incumbent.html)

    for name in order:
        result = _RUNGS[name](url)
        if not result.ok or not _is_usable(result.html):
            if better(result, last):
                last = result
            continue
        if needs_links and not same_domain_links(result.soup(), url):
            if better(result, last):
                last = result
            continue
        result.accepted = True
        if name != 'plain':
            remember_strategy(domain, name)
            if progress_cb is not None:
                progress_cb('GLOG:fetch|info|%s needed the %s route -- opened it'
                            % (domain, _RUNG_LABELS.get(name, name)), 0, 1)
        elif domain in load_domain_strategies():
            # It used to need a harder rung, or nothing reached it at all. It does now, so
            # clear the record instead of leaving a stale one to skew every later fetch.
            remember_strategy(domain, 'plain')
        return result

    remember_strategy(domain, '')  # nothing worked; do not pay for the climb again
    return last


_RUNG_LABELS = {
    'chrome_tls': 'browser-fingerprint',
    'crawler': 'search-engine',
    'browser': 'full browser',
    'apify': 'Apify unblocker',
}


def _strategy_order(domain: str, allow_browser: bool) -> list[str]:
    """Which rungs to try, in order, given what this domain did last time.

    allow_browser=False gates the Apify rung too. Its callers are robots.txt and sitemap
    fetches, where dozens of URLs are tried speculatively and most are expected to miss;
    spending up to three minutes of Apify's browser on each guess would turn a cheap
    lookahead into the slowest thing in the run.
    """
    rungs = [s for s in STRATEGIES if allow_browser or s not in ('browser', 'apify')]
    entry = load_domain_strategies().get(domain)
    if entry is None:
        return rungs

    known = entry.get('strategy') or ''
    if known and known in rungs:
        # Try what worked last time first, then the rest as a fallback in case the site
        # changed. A site that got easier should not be stuck on the expensive rung.
        return [known] + [s for s in rungs if s != known]

    # Recorded as unreachable by every rung. Still try the cheap ones -- a site can come
    # back, and three fast requests are affordable -- but not the browser: that is seconds
    # of launch for a domain already proven to defeat it, and jobtensor.com alone cost 16
    # of them. If the site does recover, a cheap rung will find it and clear this record.
    #
    # Apify is kept in this list even though it is the most expensive rung of all, and that
    # is deliberate rather than an oversight. A domain lands here precisely because nothing
    # local reached it, which is the exact case rung 5 exists for -- dropping it here would
    # mean the one route that can open glassdoor.com is skipped for glassdoor.com. The
    # cost is bounded because a success is remembered and goes straight to this rung next
    # time, and a failure is a single request rather than a browser launch.
    return [s for s in rungs if s != 'browser']


# --------------------------------------------------------------------------------------
# per-domain memory
# --------------------------------------------------------------------------------------
_STRATEGY_CACHE: dict = {}


def _strategy_path():
    from app import storage
    return storage.DATA_DIR / 'domain_fetch_strategy.json'


def load_domain_strategies() -> dict:
    """{domain: {'strategy': name, 'fetcher_version': n, 'at': iso}}.

    Memoized on the file's mtime+size so a strategy learned mid-run is used by the rest of
    that run -- the same contract the discovered job patterns use.
    """
    from .jsonstore import load_cached_json

    def drop_stale(value):
        # A strategy learned by an older fetcher may no longer describe what this one does,
        # so it is forgotten rather than trusted.
        return {domain: entry for domain, entry in value.items()
                if isinstance(entry, dict)
                and (entry.get('fetcher_version') or 0) >= FETCHER_VERSION}

    value = load_cached_json(_strategy_path(), _STRATEGY_CACHE, drop_stale)
    return value


def recall_strategy(domain: str) -> str:
    entry = load_domain_strategies().get(domain) or {}
    return entry.get('strategy') or ''


# Enrichment fetches eight rows at once, and any of them can learn a strategy. Without
# this, two workers finishing together would each read the file, add their own domain, and
# write -- and the second write would silently drop the first one's entry.
_MEMO_LOCK = threading.Lock()


def remember_strategy(domain: str, strategy: str) -> None:
    """Write down the rung that worked, so the climb happens once per site, not per page.

    An empty strategy records that the whole ladder failed. That is worth storing too: a
    site that is gone -- germantechjobs.de redirects to a signup page now -- would
    otherwise cost a browser launch on every future run to learn the same thing again.
    """
    import json
    from datetime import datetime, timezone
    with _MEMO_LOCK:
        strategies = dict(load_domain_strategies())
        if strategies.get(domain, {}).get('strategy') == strategy:
            return  # unchanged; skip the write and keep the memo valid
        strategies[domain] = {'strategy': strategy,
                              'fetcher_version': FETCHER_VERSION,
                              'at': datetime.now(timezone.utc).isoformat()}
        try:
            path = _strategy_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(strategies, indent=2, ensure_ascii=False),
                            encoding='utf-8')
            _STRATEGY_CACHE.pop('value', None)
        except Exception:
            pass  # best-effort: a failed save costs a re-climb, never a crash


# --------------------------------------------------------------------------------------
# sitemaps
# --------------------------------------------------------------------------------------
_SITEMAP_CANDIDATES = ('/sitemap.xml', '/sitemap_index.xml', '/sitemap/sitemap.xml',
                       '/jobs-sitemap.xml', '/job-sitemap.xml')
_LOC = re.compile(r'<loc>\s*([^<\s]+)\s*</loc>')
_SITEMAPINDEX = re.compile(r'<\s*sitemapindex', re.I)
_JOB_SITEMAP_HINT = re.compile(r'job|stelle|position|vacan|anzeige|career', re.I)

# How many sub-sitemaps of an index to follow. A large site splits its index by content
# type, and the job-named ones are followed first; this bounds a pathological index without
# capping a normal one, since a site rarely splits its postings across more than a few.
SITEMAP_MAX_SUBMAPS = 12


# Sitemaps are not sorted with us in mind. datacareer.de lists 4,966 company pages before
# any of its 128 postings, so a 5,000-URL cap cut off every single job while looking like
# it had read the whole file. The cap exists only to stop a pathological sitemap from
# exhausting memory; at ~60 bytes a URL this is a couple of megabytes, and it has to be
# larger than any real sitemap's job section rather than tuned to a typical size.
SITEMAP_URL_LIMIT = 50000

# A wall-clock bound, because neither a URL count nor a sub-sitemap count bounds the WAIT.
# startup.jobs publishes 19 sub-sitemaps holding 50,000 URLs between them; reading them all
# is minutes, and this runs while Sina is watching a search. A budget stops on whatever it
# has, which is the right trade for a fallback route -- a partial sitemap still verifies
# correctly, it just has fewer candidates to offer.
SITEMAP_BUDGET_SECONDS = 25.0


def sitemap_urls(site_url: str, limit: int = SITEMAP_URL_LIMIT,
                 budget_seconds: float = SITEMAP_BUDGET_SECONDS) -> list[str]:
    """Every page URL the site advertises to search engines, or [].

    A site that wants its postings indexed publishes them here, and the sitemap is served
    for crawlers -- so it is often open when the pages themselves are not. datacareer.de
    is exactly that shape: 403 on every listing, and a sitemap naming 128 postings.

    It is also more complete than any listing page, which only ever shows page one.

    Bounded by `budget_seconds` as well as by `limit`: a site with a large sitemap index
    can otherwise take minutes, and this is a fallback running inside a live search.
    """
    import time
    deadline = time.time() + budget_seconds
    parts = urlsplit(site_url)
    root = '%s://%s' % (parts.scheme or 'https', parts.netloc)
    seen_maps, urls = set(), []

    declared = []
    robots = fetch(root + '/robots.txt', allow_browser=False)
    if robots.ok:
        declared = re.findall(r'(?im)^\s*sitemap:\s*(\S+)', robots.html)

    for candidate in list(declared) + [root + p for p in _SITEMAP_CANDIDATES]:
        if candidate in seen_maps:
            continue
        seen_maps.add(candidate)
        result = fetch(candidate, allow_browser=False)
        if not result.ok or '<' not in result.html:
            continue
        locations = _LOC.findall(result.html)
        if not locations:
            continue
        # A <sitemapindex> lists more sitemaps; a <urlset> lists pages. Read the document's
        # own declaration rather than guessing from a .xml suffix: startup.jobs serves an
        # index whose entries are /sitemaps/<name>/<n> with no extension at all, and
        # suffix-matching took all 19 of them for pages and found no jobs on the site.
        is_index = _SITEMAPINDEX.search(result.html) is not None
        if is_index:
            submaps = list(locations)
        else:
            submaps = [loc for loc in locations if loc.endswith('.xml')]
            urls += [loc for loc in locations if not loc.endswith('.xml')]
        # A sitemap index points at more sitemaps. Follow the ones that name jobs first,
        # since a large site's index also lists company and blog maps we do not need.
        ranked = sorted(submaps, key=lambda s: not _JOB_SITEMAP_HINT.search(s))
        for submap in ranked[:SITEMAP_MAX_SUBMAPS]:
            if submap in seen_maps or len(urls) >= limit or time.time() > deadline:
                continue
            seen_maps.add(submap)
            sub = fetch(submap, allow_browser=False)
            if sub.ok:
                urls += [loc for loc in _LOC.findall(sub.html) if not loc.endswith('.xml')]
        if urls:
            break
        if time.time() > deadline:
            break

    return urls[:limit]
