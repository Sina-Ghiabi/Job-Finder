"""Working out, automatically, which links on a job board are individual job postings.

The deep crawl can only reach the jobs on a listing page if it knows which of that page's
links ARE jobs. That knowledge lives in GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS, and a domain
with no entry is a dead end: the listing page is kept as one row while every posting
behind it is lost. In one real search, 31 domains were in that state.

HOW THIS WORKS, AND WHY
-----------------------
This is the method that actually worked when a person did it by hand, in this order:

  1. find the CONTAINER holding the job cards. A job board renders its postings as a
     repeated block -- `<div class="jobs-list-items">`, `<ul class="job-list">`, a run of
     `<article>` elements. This is the strongest signal on the page and needs no model:
     it is just "which element repeats, each repetition holding a link whose text reads
     like a job title".
  2. take the links from INSIDE that container only. This is what separated the four real
     postings on berlinstartupjobs.com from the ~130 navigation, category and company
     links around them.
  3. OPEN one and confirm it really is a single posting.
  4. confirm the resulting glob does NOT also match the links that were not job cards.

Steps 3 and 4 are what an earlier attempt lacked. That attempt took the most common path
segment among job-ish links and proposed `/jobs/**`. Every domain it "verified" looked
fine until the URLs were actually opened:

    builtin.com/jobs/eu/germany/berlin/data-analytics/search/data-science  <- a search page
    arbeitnow.com/jobs/companies                                          <- a company index
    spaceindividuals.com/jobs/australia                                   <- a country page

All three match `/jobs/**`. Accepting them would have aimed a PAID crawler at search
pages -- worse than no pattern at all, since it spends credit to collect nothing.

Claude is used only where the structure alone is ambiguous, and only to READ link text (a
posting's link text is a job title; a category's is a topic). Its answer goes through the
same verification and is never trusted on its own.
"""
from __future__ import annotations

# The glob engine lives next door: pure prefix arithmetic over URLs, with no
# idea what a job posting is (see app/pipeline/globs.py).
from .globs import (_candidate_globs, _glob_for, _glob_match)

import collections
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from . import fetcher
from .claude_screen import CLAUDE_MODEL
from .text import text_of

# Bumped whenever the acceptance rules below change. A saved pattern records the version
# that approved it, so tightening the rules re-checks everything approved under a looser
# one instead of trusting it forever. Version 2 added the article/category title checks,
# after three saved patterns turned out to be a hiring guide and two category pages.
#
# Version 3 adds the Claude confirmation on the sampled page, after a real run saved five
# patterns whose pages are not jobs at all -- a recruitment agency's sector page, a
# marketing article, a documentation page, a company culture page, and a site's own search
# page -- and one "pattern" that was a single complete URL with no wildcard in it. Every
# one of those is now dropped from disk and re-learned under the stricter check.
# Version 4 covers the half of that last case the wildcard guard missed. jobs.sap.com came
# back with /job/<83-character job title>/** -- a wildcard on the end, so it passed, and a
# single posting pinned as the prefix, so it matches one job forever. A prefix segment now
# has to look like a folder rather than a slug.
VERIFIER_VERSION = 4

# Path segments that are never a posting. Not exhaustive and does not need to be, since
# every candidate is opened and checked anyway; this only avoids wasting requests.
_NON_JOB_SEGMENTS = {
    'about', 'blog', 'news', 'guide', 'guides', 'privacy', 'terms', 'imprint', 'impressum',
    'cookie', 'cookies', 'contact', 'faq', 'help', 'login', 'signup', 'register', 'search',
    'suche', 'companies', 'company', 'employers', 'arbeitgeber', 'skill-areas', 'categories',
    'category', 'tags', 'tag', 'newsletter', 'press', 'legal', 'pricing', 'post-a-job',
    'submit-a-job', 'sitemap', 'rss', 'feed', 'account', 'profile', 'dashboard', 'tools',
    # Legal and policy pages. Added after a real run learned
    # navartisglobal.com/legal_documents/** and collected "Privacy Policy" (14,049 chars)
    # and "Modern Slavery Policy" as job postings: they are long, and words like
    # "requirements" and "apply" appear in any terms document, so every body-based check
    # passed them.
    #
    # A PATH check is used rather than demanding a job-role word in the title, which was
    # measured and rejected: of 1,122 real collected titles, 122 (10.9%) contain no role
    # word my vocabulary knew -- "Data Engineers" (plural), "Mathematiker*in / Physiker*in",
    # "Weiterbildungsassistent", "Thesis - Optimization of Graph Neural Networks" -- and
    # every one of those is a real job. Requiring a role word would have lost them, which
    # is the one failure mode worth avoiding above all others.
    'legal', 'legal_documents', 'legal-documents', 'privacy', 'privacy-policy', 'terms',
    'conditions', 'gdpr', 'dsgvo', 'datenschutz', 'agb', 'compliance', 'policies',
    'modern-slavery', 'accessibility', 'disclaimer',
    # Advice and reference sections. Added after startup.jobs' sitemap produced
    # /students/** as a job pattern: nineteen pages of career advice -- "Writing an
    # Effective Resume", "Your First Startup Interview", "A Guide to Networking" -- each
    # around 4,700 characters of job vocabulary, which every body check passed and only one
    # of the five title rules caught.
    'students', 'resources', 'advice', 'career-advice', 'learn', 'learning', 'glossary',
    'interview-questions', 'salaries', 'collections', 'markets', 'trends', 'statistics',
    'insights', 'reviews', 'templates', 'toolkit',
}

# Words that, as the LAST path segment, name the page rather than a job. Checked separately
# from _NON_JOB_SEGMENTS because position changes the meaning entirely: "companies" as the
# leaf of /companies/acme is a company page, and as the middle of
# /jobs/companies/acme/data-scientist it is just a folder holding a real posting.
_NON_JOB_LEAF_SEGMENTS = {
    'salaries', 'salary', 'trends', 'statistics', 'stats', 'reviews', 'insights',
    'guide', 'guides', 'about', 'contact', 'faq', 'help', 'blog', 'news', 'press',
    'privacy', 'terms', 'imprint', 'impressum', 'datenschutz', 'sitemap', 'login',
    'signup', 'register', 'pricing', 'companies', 'employers', 'arbeitgeber',
}

# "27 Data Scientist Jobs in Berlin" is a listing page's title, not a posting's.
_RESULT_COUNT_TITLE = re.compile(
    r'\b\d+\s+(jobs?|stellen|stellenangebote|results?|vacancies|positions?)\b', re.I)

# A real posting almost always contains at least one of these.
_POSTING_MARKERS = re.compile(
    r'\b(apply|responsibilities|requirements|qualifications|your profile|we offer|'
    r'bewerben|aufgaben|anforderungen|profil|wir bieten|dein profil)\b', re.I)

# A hiring guide, an interview-question article or a salary report is long, uses job
# vocabulary, and is not a job. Judged on the title, which is where an article announces
# itself.
_ARTICLE_TITLE = re.compile(
    r'\b(interview questions?|hiring guides?|how to|guide to|checklist|tips|'
    r'what is|comparison|templates?|best practices|ultimate guide|salary report|'
    r'career advice|cv tips|resume tips|'
    # Added from real pages that reached the verifier: startup.jobs' student section
    # publishes "Writing an Effective Resume", "Your First Startup Interview", "Glossary of
    # Startup Terms" and "Salary Compensation", none of which the rules above matched.
    # "networking" was tried here and removed: measured against 2,682 real collected
    # titles it rejected "Golang System Developer / Networking Engineer at Altinity",
    # which is a real job. One lost listing is too many, and the article it was meant to
    # catch -- "A Guide to Networking" -- is already caught by "guide to".
    r'writing (an?|your)|your first|glossary|'
    r'salary (compensation|guide|range|expectations)|'
    r'resume|curriculum vitae|cover letter|job search|career path)\b', re.I)

# "Data Engineer Jobs", "Construction Jobs" -- a PLURAL job noun as the head of the title
# is an index of many postings. A single posting says it in the singular: "Job Vacancy:",
# "job in Berlin", "Data Scientist (w/m/d)".
_PLURAL_JOB_HEAD = re.compile(
    r'\b[\w/&-]+\s+(jobs|vacancies|stellenangebote|stellen|positions|openings|careers)\b',
    re.I)

# Only the part before the site-name suffix is judged. Real postings routinely carry a
# suffix that contains a plural -- berlinstartupjobs ends every posting title with
# "| IT / Software Development Jobs" -- and judging the whole title rejects them.
_TITLE_SEPARATORS = re.compile(r'\s*[|·—–]\s*|\s+//\s+')


def _leading_title(title: str) -> str:
    """The title up to its first separator -- the part that describes the PAGE, before
    the site name and section trail."""
    return _TITLE_SEPARATORS.split(text_of(title), 1)[0].strip()


_MIN_POSTING_CHARS = 800

# A posting links to few pages of its own shape; an index page links to many. Counted as
# distinct PAGES: a posting's own share links (?share=linkedin, ?share=facebook, ...) are
# the same page, and a real posting is also allowed to show a handful of related jobs.
_MAX_SIBLING_LINKS = 15

# Link text this short or this generic is navigation, not a job title.
_MIN_JOB_TITLE_WORDS = 2
_GENERIC_LINK_TEXT = re.compile(
    r'^(read more|more|apply|view|details|jobs?|home|next|previous|\d+)$', re.I)


def _fetch(url: str, needs_links: bool = False):
    """(status_code, soup) or (None, None). Never raises.

    Delegates to the fetch ladder rather than calling requests directly. Plain requests
    is still the first thing tried and answers nearly every site; the difference is what
    happens when it does not. Four of the sites that used to end here as a bare 403 --
    startup.jobs among them, the most frequent unknown domain in real searches -- open on
    a later rung, and the rung that worked is remembered per domain so the cost is paid
    once rather than on every page of that site.

    `needs_links` is for the listing page, where a 200 holding no links is a JavaScript
    shell and climbing one more rung is exactly the right response.
    """
    result = fetcher.fetch(url, needs_links=needs_links)
    if result.status is None:
        return None, None
    return result.status, BeautifulSoup(result.html, 'html.parser')


def _readable_text(soup) -> str:
    clone = BeautifulSoup(str(soup), 'html.parser')
    for tag in clone(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
        tag.decompose()
    return ' '.join(clone.get_text(' ').split())


def _same_domain_links(soup, base_url: str) -> list[str]:
    host = urlsplit(base_url).netloc.lower()
    out = []
    for anchor in soup.find_all('a', href=True):
        full = urljoin(base_url, anchor['href']).split('#')[0]
        if urlsplit(full).netloc.lower() == host:
            out.append(full)
    return list(dict.fromkeys(out))


def _normalize_page(url: str) -> str:
    """The page a URL points at, ignoring query string and trailing slash.

    `/engineering/senior-data-scientist/` and `/engineering/senior-data-scientist/?share=li`
    are one page, and counting them as two made a real posting look like an index.
    """
    parts = urlsplit(url)
    return '%s://%s%s' % (parts.scheme, parts.netloc.lower(), parts.path.rstrip('/'))


def _looks_like_job_title(text: str) -> bool:
    """Does this link's text read like a job title rather than navigation?"""
    words = text.split()
    if len(words) < _MIN_JOB_TITLE_WORDS:
        return False
    if _GENERIC_LINK_TEXT.match(text.strip()):
        return False
    # "Marketing & Communications (15)" is a category with a count, not a posting.
    if re.search(r'\(\d+\)\s*$', text):
        return False
    return True


def find_job_card_groups(soup, base_url: str) -> list[list[str]]:
    """Every plausible group of job-card links on the page, best candidate first.

    This is step 1, and it is the whole trick: rather than reasoning about the ~130 links
    on a listing page, find the elements whose repetition IS the job list and take only
    the links inside them.

    Returns a LIST of groups rather than one. An earlier version kept only the largest,
    and on berlinstartupjobs.com the `li` fallback matched the navigation menu -- 16 guide
    articles, beating the 4 real postings -- so the real jobs were discarded before they
    could be checked. Groups are ordered by selector specificity, and the caller verifies
    each until one passes.
    """
    host = urlsplit(base_url).netloc.lower()
    groups: list[list[str]] = []

    # Most specific first. A job board almost always marks its list with one of these;
    # the <article>/<li> fallbacks catch the ones that do not, at the cost of also
    # catching menus -- which is why every group is verified rather than trusted.
    selectors = ['[class*=job-list]', '[class*=jobs-list]', '[class*=joblist]',
                 '[class*=job-card]', '[class*=job_item]', '[class*=vacancy]',
                 '[class*=stellenangebot]', 'article', 'li']
    for selector in selectors:
        try:
            elements = soup.select(selector)
        except Exception:
            continue
        # Deliberately no minimum on the ELEMENT count. Repetition can live inside one
        # container (`<div class="jobs-list-items">` holding twenty links) just as
        # readily as across many (`<article>` per job). Requiring three elements missed
        # the single-container case entirely -- which is the commonest shape there is.
        # The link-count gate below is what actually establishes repetition.
        links = []
        for element in elements:
            for anchor in element.find_all('a', href=True):
                full = urljoin(base_url, anchor['href']).split('#')[0]
                if urlsplit(full).netloc.lower() != host:
                    continue
                label = ' '.join(anchor.get_text(' ').split())
                if not _looks_like_job_title(label):
                    continue
                segments = [s for s in urlsplit(full).path.split('/') if s]
                if len(segments) < 2 or segments[0].lower() in _NON_JOB_SEGMENTS:
                    continue
                links.append(full)
        links = list(dict.fromkeys(links))
        if len(links) < 3:
            continue
        # Split by URL shape: one selector can pick up several distinct sections, and
        # each shape is its own candidate rather than being averaged together.
        by_shape = collections.defaultdict(list)
        for url in links:
            shape = _glob_for(url)
            if shape:
                by_shape[shape].append(url)
        for shape, urls in sorted(by_shape.items(), key=lambda kv: -len(kv[1])):
            if len(urls) >= 2 and urls not in groups:
                groups.append(urls)
    return groups
def _looks_like_single_posting(url: str, soup, status, shape: str | None = None) -> bool:
    """Step 3: is the page at `url` one job posting, or another index page?

    `shape` is the glob currently being verified. It matters for the sibling count below:
    the question is "does this page link to many pages OF THE KIND WE ARE PROPOSING", and
    answering it with a coarser shape than the one under test gets it wrong. Measured on
    arbeitnow.com, a real posting links to 103 pages under /jobs/** -- its related-jobs
    rail -- and to 8 under /jobs/companies/*/*, the glob actually being verified. Judged by
    the first number every posting on the site looks like an index; by the second, correct.
    """
    if status != 200 or soup is None:
        return False
    # A URL's last segment names what the page IS. startup.jobs publishes
    # /roles/<role>/salaries, /trends and /statistics alongside its category pages: several
    # thousand characters, job vocabulary throughout, and a title -- "Startup Onboarding
    # Manager Salary (2026)" -- that no title rule caught. Every body-based check passed
    # them, and 60 of them were learned as job patterns in one run.
    segments = [s for s in urlsplit(url).path.split('/') if s]
    if segments and segments[-1].lower() in _NON_JOB_LEAF_SEGMENTS:
        return False
    title = text_of(soup.title.string if soup.title else '')
    if _RESULT_COUNT_TITLE.search(title):
        return False
    # An article and a category page both read like a posting by body alone -- see this
    # module's header for the three real pages that got through. The title is what gives
    # them away.
    lead = _leading_title(title)
    if _ARTICLE_TITLE.search(lead):
        return False
    if _PLURAL_JOB_HEAD.search(lead):
        return False
    body = _readable_text(soup)
    if len(body) < _MIN_POSTING_CHARS:
        return False
    if not _POSTING_MARKERS.search(body):
        return False
    shape = shape or _glob_for(url)
    if shape:
        here = _normalize_page(url)
        siblings = {_normalize_page(u) for u in _same_domain_links(soup, url)
                    if _glob_match(u, shape)}
        siblings.discard(here)
        if len(siblings) > _MAX_SIBLING_LINKS:
            return False
    return True


# A page can pass every structural rule and still not be a job. In one real run five did,
# and each was saved as a permanent pattern: a recruitment agency's sector page
# ("Specialist Artificial Intelligence Recruitment Agency"), a marketing article ("SumUp
# Kompass"), a documentation page ("Getting Started"), a company culture page, and a site's
# own search page. All long, all full of job vocabulary, none caught by any title rule.
#
# Tightening the rules is not the answer and has been measured twice: requiring a role word
# in the title would have dropped 122 of 1,122 real jobs, and requiring a query word in a
# EURES title dropped 107 of 129. Words cannot separate these; meaning can. Asked about
# these exact eleven pages -- the five impostors and six real postings -- Claude agreed
# with a human reading on all eleven.
#
# So the structural checks still do the work of narrowing, and this is the last word before
# a pattern is saved forever. One Haiku call per candidate, once per domain in its
# lifetime. Without a Claude key it simply does not run and the structural verdict stands,
# which is exactly the behaviour that existed before.
_POSTING_JUDGE_SYSTEM_PROMPT = """You are shown one web page from a job site: its URL, its
title, and the start of its text.

Answer whether it is ONE INDIVIDUAL JOB POSTING -- a specific open role at a specific
employer that a person could apply to.

These are NOT individual job postings, however much job vocabulary they contain:
  - a recruitment agency's service or sector page ("Specialist X Recruitment Agency")
  - a list, index or search-results page of many jobs
  - a company culture, about, benefits or careers-overview page
  - documentation, a blog post, a guide, a news article, marketing copy
  - a login, signup or account page

A posting IS one even if it is short, in German, for several openings of the same role,
an internship, a working-student role, or a thesis position.

Reply with exactly one line:
VERDICT: JOB
or
VERDICT: NOT A JOB
"""

_POSTING_JUDGE_MAX_CHARS = 2500


def _claude_confirms_posting(client, url: str, soup) -> bool | None:
    """True/False if Claude judged the page, None if it could not be asked.

    None is deliberately distinct from False: no key, or a failed call, must leave the
    structural verdict standing rather than silently rejecting every site.
    """
    if client is None:
        return None
    title = text_of(soup.title.string if soup.title else '')
    body = _readable_text(soup)[:_POSTING_JUDGE_MAX_CHARS]
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=20, temperature=0,
            system=_POSTING_JUDGE_SYSTEM_PROMPT,
            messages=[{'role': 'user',
                       'content': 'URL: %s\nTITLE: %s\n\nTEXT:\n%s' % (url, title, body)}])
        answer = ' '.join(block.text for block in response.content
                          if getattr(block, 'type', None) == 'text').upper()
    except Exception:
        return None
    if 'NOT A JOB' in answer:
        return False
    if 'VERDICT: JOB' in answer:
        return True
    return None


def _verify_and_build(candidates: list[str], soup, listing_url: str,
                      progress_cb=None, all_links: list[str] | None = None,
                      client=None) -> list[str]:
    """Steps 3 and 4: open a sample, then check the glob excludes the non-job links.

    `all_links` is the pool the glob must not over-reach into. It defaults to the links on
    the listing page, which is the right pool when the candidates came from that page. The
    sitemap route passes its own pool instead, because there is no page there to read.
    """
    if len(candidates) < 2:
        return []

    def covers_at_least_two(glob):
        """Short-circuits. The sitemap route can pass tens of thousands of candidates, and
        counting every match of every proposal there is minutes of pointless work."""
        found = 0
        for url in candidates:
            if _glob_match(url, glob):
                found += 1
                if found >= 2:
                    return True
        return False

    # Several shapes are offered per group, general first, because one shape cannot express
    # every site's layout -- see _candidate_globs. A glob is only worth proposing if it
    # covers at least two of the cards; one is a coincidence, not a pattern.
    proposed = [glob for glob in _candidate_globs(candidates) if covers_at_least_two(glob)]
    if not proposed:
        return []

    if all_links is None:
        all_links = _same_domain_links(soup, listing_url)
    candidate_set = set(candidates)
    not_candidates = [u for u in set(all_links) if u not in candidate_set]

    verified = []
    for glob in proposed:
        # Step 4: the glob must not sweep in links that were not job cards. This is
        # exactly what separates /engineering/** (jobs) from /jobs/** (jobs AND searches),
        # and it is what rejects the over-general glob when a more precise one is also on
        # offer: /jobs/** sweeps in 58 of arbeitnow.com's city index pages, while
        # /jobs/companies/*/* sweeps in none.
        collateral = 0
        for url in not_candidates:
            if _glob_match(url, glob):
                collateral += 1
                if collateral > 2:
                    break          # over budget already; no need to count the rest
        if collateral > 2:
            continue
        # Step 3: open a real one.
        samples = []
        for url in candidates:
            if _glob_match(url, glob):
                samples.append(url)
                if len(samples) >= 2:
                    break
        for sample in samples:
            status, sample_soup = _fetch(sample)
            if not _looks_like_single_posting(sample, sample_soup, status, shape=glob):
                continue
            # Structurally a posting. Now the question the structure cannot answer.
            judged = _claude_confirms_posting(client, sample, sample_soup)
            if judged is False:
                if progress_cb:
                    progress_cb(
                        'GLOG:pattern|info|%s: %s looked like a posting but is not one '
                        '-- pattern not saved.'
                        % (urlsplit(listing_url).netloc, glob), 0, 1)
                continue
            verified.append(glob)
            if progress_cb:
                how = ('verified by opening a real posting and confirming it is one'
                       if judged else 'verified by opening a real posting')
                progress_cb(
                    'GLOG:pattern|success|Worked out how %s builds its job links (%s) '
                    '-- %s.' % (urlsplit(listing_url).netloc, glob, how), 0, 1)
            break
    return verified


def _discover_from_sitemap(listing_url: str, progress_cb=None, client=None) -> list[str]:
    """Work the pattern out from the site's sitemap instead of its listing page.

    For a site whose pages are shut but whose sitemap is open. datacareer.de is the case
    that motivated this: every listing URL answers 403 to a browser-shaped request, while
    /sitemap.xml serves 5,381 URLs including 128 postings under /job/. The sitemap exists
    to be read by search engines, so it is frequently the one door left unlocked.

    It is also the better source where both work, being complete rather than page one.
    Candidates are still opened and verified exactly as page-derived ones are -- a URL
    appearing in a sitemap says the site advertises it, not that it is a job.
    """
    urls = fetcher.sitemap_urls(listing_url)
    if not urls:
        return []
    host = urlsplit(listing_url).netloc.lower()
    urls = [u for u in urls if urlsplit(u).netloc.lower() == host]

    groups: dict[str, list[str]] = collections.defaultdict(list)
    for url in urls:
        segments = [s for s in urlsplit(url).path.split('/') if s]
        if len(segments) < 2 or segments[0].lower() in _NON_JOB_SEGMENTS:
            continue
        groups[segments[0].lower()].append(url)

    # A posting group is large and named like postings. Try job-named segments first, then
    # the rest by size -- a site may name the segment something unexpected, and the
    # verifier is what actually decides.
    def rank(item):
        segment, members = item
        named = bool(re.match(r'^(job|jobs|stelle|stellen|stellenangebot|position|'
                              r'vacancy|vacancies|career|careers|offer|offers|role|roles)$',
                              segment))
        return (not named, -len(members))

    for segment, members in sorted(groups.items(), key=rank)[:6]:
        if len(members) < 3:
            continue
        # Every member is a candidate, not just a sample of them. Passing members[:12] made
        # the other 13 of jobfluent.com's 25 postings count as collateral against their own
        # glob, which rejected the site outright. _verify_and_build only ever OPENS two of
        # them, so the full list costs nothing.
        verified = _verify_and_build(members, None, listing_url, progress_cb,
                                     all_links=urls, client=client)
        if verified:
            if progress_cb:
                progress_cb('GLOG:pattern|info|%s would not open its listing pages, so its '
                            'sitemap was read instead -- %d posting URLs found.'
                            % (host, len(members)), 0, 1)
            return verified
    return []


# How many category pages to open when a listing page turns out to hold only categories,
# and how many of its groups to consider. Small on purpose: this is the last resort, it
# costs a page fetch plus up to two sample fetches each, and a site that needs more than
# two tries is not one where the shape is obvious enough to trust anyway.
_MAX_DEEPER_PAGES = 2


def _discover_one_level_deeper(listing_url: str, soup, progress_cb=None,
                               client=None) -> list[str]:
    """Follow a category link and look for the postings there.

    Some search pages list no postings at all -- only the categories that contain them.
    startup.jobs is the clearest case: /?q=data+scientist returns 49 links, every one of
    them /roles/<category>, and opening one shows a title of "QA Engineer Jobs in September
    2026". The verifier is right to reject those as index pages, and right to reject a
    /roles/** glob that cannot tell a category from a posting. But the postings are real
    and one click away, which is exactly what a person would do next.

    Strictly one level. The pages found here are verified by the same rules as any other,
    so following a link cannot lower the bar for what counts as a job.
    """
    host = urlsplit(listing_url).netloc
    tried = 0
    for candidates in find_job_card_groups(soup, listing_url):
        for candidate in candidates:
            if tried >= _MAX_DEEPER_PAGES:
                return []
            segments = [s for s in urlsplit(candidate).path.split('/') if s]
            if any(s.lower() in _NON_JOB_SEGMENTS for s in segments):
                continue
            status, deeper_soup = _fetch(candidate, needs_links=True)
            if status != 200 or deeper_soup is None:
                continue
            tried += 1
            for deeper_candidates in find_job_card_groups(deeper_soup, candidate):
                verified = _verify_and_build(deeper_candidates, deeper_soup, candidate,
                                             progress_cb, client=client)
                if verified:
                    if progress_cb:
                        progress_cb(
                            'GLOG:pattern|info|%s lists categories rather than jobs, so one '
                            'was opened -- the postings are inside.' % host, 0, 1)
                    return verified
    return []


def discover_job_url_patterns(listing_url: str, progress_cb=None, client=None) -> list[str]:
    """Structural discovery: find the job-card container, verify, return the globs.

    Free -- plain HTTP up the fetch ladder, a handful of requests. Returns [] when nothing
    can be established, which is the correct outcome for a site that is genuinely gone. A
    guess would be worse than nothing: the crawler that consumes it costs money.

    Three routes, in cost order:
      1. the listing page itself -- one request, and it is what the search actually found
      2. its sitemap -- for sites that serve crawlers and refuse everyone else, and which
         is more complete besides, listing every posting rather than page one
      3. one category page in -- for sites whose search results are categories, not jobs
    """
    status, soup = _fetch(listing_url, needs_links=True)
    if status == 200 and soup is not None:
        # Every candidate group, in order, until one verifies. The wrong groups (a
        # navigation menu, a guide section) fail on the checks in _verify_and_build.
        for candidates in find_job_card_groups(soup, listing_url):
            verified = _verify_and_build(candidates, soup, listing_url, progress_cb,
                                         client=client)
            if verified:
                return verified

    from_sitemap = _discover_from_sitemap(listing_url, progress_cb, client=client)
    if from_sitemap:
        return from_sitemap

    if status == 200 and soup is not None:
        return _discover_one_level_deeper(listing_url, soup, progress_cb, client=client)
    return []


# ---------------------------------------------------------------------------------
# Claude, for pages where the structure alone is ambiguous
# ---------------------------------------------------------------------------------
# Used only to READ link text -- deciding that "Senior Data Scientist - Python, ML" is a
# posting and "Marketing & Communications (15)" is a category. Claude is asked to LIST the
# posting paths it can see, not to author a glob: a first version asked for glob syntax
# and got back a regex (`/*/[a-z0-9-]+/`) the matcher could not use, so it silently fell
# back to the heuristic. Listing URLs is what it is good at; deriving a safe glob from
# them is what this module is good at.

_JOB_PATTERN_SYSTEM_PROMPT = """You are given the links found on a job board's search-results page.

Identify which of them are INDIVIDUAL JOB POSTINGS.

You will see links as `path | link text`. Use both. On a job board:
  - an individual posting's link text is a JOB TITLE ("Senior Data Scientist, Berlin")
  - a category link's text is a topic, often with a count ("Marketing & Communications (15)")
  - a company link's text is a company name ("DATATRONiQ")
  - navigation text is generic ("About", "Post a job", "Browse all 134 jobs")

List ONLY the paths that are individual job postings, one per line, exactly like this:

JOB: /engineering/senior-data-scientist-acme/
JOB: /engineering/cloud-devops-engineer-acme/

Copy the paths exactly as given. Do not invent paths. Do not write a pattern, a regex or
a glob -- just list the actual posting paths you can see.

If none of the links are individual postings -- the page may show only categories, or load
its listings with JavaScript -- reply with exactly:

JOB: NONE
"""

_JOB_PATTERN_ANSWER = re.compile(r'^JOB:\s*(\S+)\s*$', re.M)

_MAX_LINKS_IN_PROMPT = 120


def resolve_job_pattern_with_claude(client, listing_url: str, progress_cb=None) -> list[str]:
    """Ask Claude which links are postings, then verify exactly as the structural path does."""
    status, soup = _fetch(listing_url)
    if status != 200 or soup is None:
        return []

    host = urlsplit(listing_url).netloc
    seen = set()
    samples = []
    for anchor in soup.find_all('a', href=True):
        full = urljoin(listing_url, anchor['href']).split('#')[0]
        if urlsplit(full).netloc.lower() != host.lower() or full in seen:
            continue
        seen.add(full)
        label = ' '.join(anchor.get_text(' ').split())[:70]
        samples.append('%s | %s' % (urlsplit(full).path, label))
        if len(samples) >= _MAX_LINKS_IN_PROMPT:
            break
    if len(samples) < 5:
        return []

    page_title = text_of(soup.title.string if soup.title else '')
    prompt = 'Site: %s\nPage title: %s\n\nLinks found on this page:\n%s' % (
        host, page_title[:120], '\n'.join(samples))
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=600, temperature=0,
            system=_JOB_PATTERN_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}],
        )
        answer = '\n'.join(block.text for block in response.content
                           if getattr(block, 'type', None) == 'text')
    except Exception:
        return []

    scheme = urlsplit(listing_url).scheme
    on_page = set(_same_domain_links(soup, listing_url))
    named = []
    for raw in _JOB_PATTERN_ANSWER.findall(answer):
        cleaned = raw.strip().strip('`*_ ').rstrip('.')
        if not cleaned or cleaned.upper() == 'NONE':
            continue
        full = cleaned if cleaned.startswith('http') else '%s://%s%s' % (scheme, host, cleaned)
        # Only paths that were really on the page: a hallucinated one cannot become a
        # pattern.
        if full in on_page:
            named.append(full)

    return _verify_and_build(list(dict.fromkeys(named)), soup, listing_url, progress_cb,
                             client=client)


def discover_job_url_patterns_smart(listing_url: str, client=None, progress_cb=None) -> list[str]:
    """Structure first (free), Claude second (only when structure finds nothing).

    Both paths end in the same verification, so neither can return a pattern that has not
    been proved by opening a real posting.
    """
    found = discover_job_url_patterns(listing_url, progress_cb=progress_cb, client=client)
    if found:
        return found
    if client is not None:
        return resolve_job_pattern_with_claude(client, listing_url, progress_cb=progress_cb)
    return []
