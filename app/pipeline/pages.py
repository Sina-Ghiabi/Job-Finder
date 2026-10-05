# -*- coding: utf-8 -*-
"""Telling a page of jobs from a job.

A search collects pages, and some of what it collects are not vacancies at all: a board's
category page, a saved search, a "1.500+ offen" index. Measured on the real Austrian corpus,
73 of the 557 listings that reach Claude are pages like that. They are also among the most
expensive, because a page of forty jobs is longer than one job -- 6,885 characters at the
median against 3,775 for a real posting.

Sending them costs money and gains nothing: Claude reads a list of other people's jobs and
is asked whether the user should apply to it.

WHY THE URL DECIDES AND THE TITLE ONLY VOTES

The obvious rule -- does the title say "jobs" -- is wrong, and wrong in the direction that
costs real work. Of 73 listings a title-and-URL rule flagged, 27 were genuine single
vacancies:

    arc.dev/remote-jobs/data-cleaning                    a category page
    arc.dev/remote-jobs/details/experienced-backend-dev  one job, same prefix
    europa.eu/eures/portal/jv-se/jv-details/MTczMzcy…    one job, titled "Student Job (f/m/x)"

A board says what a page IS in the shape of its address. A details segment, a long numeric
id, a hash -- those name one posting, and no wording in the title can outweigh them.
"""
from __future__ import annotations

import re


# The address of ONE posting. Any of these outranks every listing-page signal below, because
# a board that has given a page its own id is pointing at a single thing.
#
#   /details/ or /jv-details/   said outright (arc.dev, EURES)
#   a run of 5+ digits anywhere in a path segment -- an id, wherever the board puts it:
#       karriere.at/jobs/10028125                       the whole segment
#       wearedevelopers.com/jobs/ext/2698650-aws-sol…   in front of the slug
#       nl.indeed.com/job/back-end-developer-a64bd8c…   behind it, as hex
#       remoteok.com/remote-jobs/…-benzinga-1137224     behind it, as digits
#   a trailing token of 8+ characters carrying a digit -- a generated hash:
#       arc.dev/remote-jobs/details/…-pgs0dchx5x
#
# Digits are what separate an id from a word, and that is the whole trick. "software",
# "maria-enzersdorf" and "data-cleaning" are category pages and carry none; every posting id
# in the corpus carries some. An earlier version looked for an 8-character trailing token
# without requiring a digit, and "engineer" qualified.
_SINGLE_POSTING_URL = re.compile(
    r'/details?/|/jv-details/'
    r'|/[^/?#]*\d{5,}[^/?#]*(?:[/?#]|$)'
    r'|[-/][a-z0-9]*\d[a-z0-9]*(?:[/?#]|$)(?<=[a-z0-9]{8})', re.I)

# A page that lists vacancies. Read from the path, where a board describes what it is
# serving rather than what it is about.
#
# The last three alternatives were added after a real Austrian run leaked 14 index pages
# into Claude:
#   stepstone.at/jobs/devops-engineer/in-salzburg     role, then place -- a filtered list
#   weworkremotely.com/jobs-in-remote-location-austria
#   pnet.co.za/cmp/en/ista-personnel-solutions-73462/jobs   a company's own job list
# A curated article that lists COMPANIES, not a vacancy and not even a page of vacancies.
# wellfound.com publishes dozens and the crawler followed twelve of them into a real Oslo
# run: "19 Hot Crypto Startups Hiring Remotely in 2022", "YC Startups That Are Aggressively
# Hiring", "20 Companies Building Our Remote First Future". Their addresses are
# title-shaped, so every rule below read them as one posting.
_COLLECTION_URL = re.compile(r'/job-collections?/|/collections?/|/job-lists?/', re.I)

_LISTING_URL = re.compile(
    r'/search\b|/jobs?/?$|/jobs?\?|/jobs?/[a-z][a-z0-9-]*/?$|/remote-jobs/?$'
    r'|/remote-jobs/[a-z][a-z0-9-]*/?$|/stellenangebote/?$|/vacatures/?$|/offres/?$'
    r'|/browse\b|/categor|/tag/|/suche\b|/jobs/ls/'
    r'|/jobs?-in-|/jobs?/[a-z0-9%.-]+/in-[a-z0-9%.-]+/?$', re.I)

# The third kind of page that is not a vacancy, and the one nothing looked for: a board's own
# editorial. Not a vacancy, and not a page OF vacancies either, so neither _LISTING_URL nor
# _COUNTS_VACANCIES has anything to fire on -- and their addresses are title-shaped, so every
# rule above reads them as one posting.
#
# The user found them at the far end of the Germany run, in the nine listings Claude had marked
# "apply": "How to become a Data Scientist in Germany" (a careers article), "Data Scientist
# (m/f/d): Salary, tasks & jobs" (Hays' reference page for the role) and "The Helmholtz
# Information & Data Science Framework" (an organisation describing itself). Claude keeps
# them honestly enough -- they are about data science, they list the skills, and rule 5 asks
# about a page "listing many jobs", which none of them is.
#
# 33 of the 8,133 rows in the Bank, every one read by eye before this shipped: German wage
# tax, work permits, co-working spaces, a driving licence, a B1 exam diary, "Be or Become a
# 'Marketing and Sales' employee".
_EDITORIAL_URL = re.compile(
    r'/career[-_]advice/|/careers?[-_]advice/|/career[-_]tips?/|/karriere[-_]tipps?/'
    r'|/job[-_]profiles?/|/berufsbild(er)?/'
    r'|/blog/|/magazin(e)?/|/ratgeber/|/guide[s]?[-_/]|/lexikon/|/glossar'
    r'|/salary[-_]guide|/gehaltsreport|/discover[-_]'
    r'|/how[-_]to[-_]|/what[-_]is[-_]', re.I)

# ...unless the address also names a vacancy, which means it is one filed inside such a
# section. This guard is not optional. Without it the first draft took four real postings,
# and they were the best kind in the whole corpus -- an employer's own site, no agency in
# between -- because German employers file openings under "Über uns / Karriere":
#
#   wwf.de/ueber-uns/stellenangebote/stellenangebot/stelle/data-integration-bi-specialist
#   s-kreditpartner.de/ueber-uns/karriere/stellenangebote/werkstudent-data-science-…
#   lzpd.polizei.nrw/artikel/ml-data-scientist-wmd
#
# `/about-us/`, `/ueber-uns/`, `/artikel/`, `/news/` and `/presse/` were in that first draft
# and are deliberately absent now: a section that holds real openings cannot be read as
# editorial, however often it also holds articles.
#
# The job word must be a whole path segment. `/jobs?[/-]` read Hays' "/job-profiles/" as the
# word "job" and rescued the very page that started this.
_VACANCY_IN_URL = re.compile(
    r'stellenangebot|stellenanzeige|/stelle/|/jobs?/|/vacature|/vacancy|/vacancies'
    r'|/offre/|/empleo/|/emprego/|/karriere/|/career[s]?/[a-z0-9-]*\d', re.I)

# A title that explains a job rather than offering one. Same standing as _COUNTS_VACANCIES:
# a second opinion, for the boards that publish editorial on an address giving nothing away.
# "Be or Become a …" is jobinamsterdam.com's own series, eight of them in the Bank.
_EXPLAINS_A_JOB = re.compile(
    r'^\s*(?:how\s+to\b|what\s+(?:is|does|are)\b|wie\s+(?:wird|werde)\b|was\s+(?:ist|macht)\b)'
    r'|\bcareer\s+(?:advice|path|guide)\b|\bjob\s+profile\b|\bberufsbild\b'
    r'|\bguide\s+to\b|\bultimate\s+guide\b|\beverything\s+you\s+need\s+to\s+know\b'
    r'|\bbe\s+or\s+become\s+a\b', re.I)


def is_editorial_page(row: dict) -> bool:
    """Is this a board writing ABOUT work rather than offering any?

    Address first, title second, and a vacancy named anywhere in the address wins over both.
    """
    url = str(row.get('url') or '')
    if _VACANCY_IN_URL.search(url):
        return False
    return bool(_EDITORIAL_URL.search(url)
                or _EXPLAINS_A_JOB.search(str(row.get('title') or '')))

# A title that COUNTS VACANCIES, and the one title signal strong enough to outrank the URL.
#
# The module docstring's rule -- the URL decides, the title votes -- was measured against a
# loose title rule, "does the title say jobs", which flagged 27 genuine vacancies out of 73.
# This is a different question and it does not have that failure mode: a real vacancy never
# says how many vacancies there are. Nothing in either corpus does.
#
# Every one of these is a real leaked title from the Austrian DevOps run, where the URL
# heuristic claimed them as single postings and this is what they actually were:
#   158 Jobs Hainburg an der Donau                    karriere.at/jobs/hainburg-an-der-donau
#   Your search returned 22 jobs                      a company page's own list
#   Mehr als 1.000 Jobs Kematen an der Krems
#   9 results for Platform Engineer jobs in Work From Home within a 30 km radius
#   Devops Engineer Jobs und Stellenangebote in Salzburg
# `positions` was in this list for one measurement and came straight back out: a real
# Wellfound advert is titled "UI/UX Designer India ~ Intern 3 Months + Full time 3
# Positions", where the number counts the openings in ONE posting. `jobs`, `Stellen`,
# `Treffer` and `Ergebnisse` never do that.
# The list was English and German, which is what the runs had been in. The Amsterdam run
# showed the cost: "31 data scientist vacatures in Amsterdam", "68 wo data scientist
# vacatures bekijken", "83 parttime data scientist vacatures" all read as single postings,
# and on a Not Remote search they would have gone to Claude as adverts. The word for a
# vacancy in each language this app searches is now here -- every one of them counts
# vacancies exactly the way "jobs" does, and none of them is what a real advert says about
# its own openings (which is why `positions` is still deliberately absent).
#
# The count and the word are not always adjacent, and that is the shape the Dutch boards
# use: "31 data scientist vacatures in Amsterdam", "68 wo data scientist vacatures
# bekijken". Up to four words are allowed between them -- enough for a role name, not
# enough to reach across a sentence. A real advert does not put a number in front of its
# title AND a word for "vacancies" after it.
_COUNTS_VACANCIES = re.compile(
    r'\b\d[\d.,]*\s*\+?\s*(?:[\w&/,-]+\s+){0,4}(?:jobs?|stellen|stellenangebote|vacancies'
    r'|offene?n?|treffer|ergebnisse?|vacature[sn]?|banen'
    r'|offres?|emplois?|offerte|annunci'
    r'|ofertas?|empleos?|vagas?|empregos?'
    r'|lediga jobb|annonser|stillinger|työpaikkaa|ofert[ay])\b'
    r'|\byour search returned\b|\bmehr als\s+[\d.,]+\s+(?:jobs?|stellen)'
    r'|\baktuell\s+[\d.,]+\+?\s*offen|\b\d+\s+results?\s+for\b'
    r'|\bjobs?\s+und\s+stellenangebote\b'
    # "77 Head of Key Account Management Jobs" -- a count, a category, and the word last.
    r'|^\s*\d[\d.,]*\s+[\w\s&/,-]{0,48}\b(?:jobs|stellen)\s*$', re.I)

# What an index page calls itself. Only ever a second opinion -- see the module docstring.
_LISTING_TITLE = re.compile(
    r'\b\d+\s+(?:open\s+|offene?n?\s+|fully\s+remote\s+)?(?:jobs|positions|stellen|vacancies)'
    r'|\baktuell\s+[\d.]+\+?\s*offen|\|\s*\d+\s+open'
    r'|^find the best\b|\bjob search\b|\ball jobs\b|\bjobs?\s+in\s+\w+\s*\|'
    r'|\bjobs?\s+(?:in|at|for)\s+[A-Z]', re.I)


# A last path segment that reads as a job title rather than a category. Boards without
# numeric ids still name the posting in the address, and the difference is length:
#
#   /careers/jobs/supply-chain-business-excellence-manager   a vacancy at AOP Health
#   /remote-jobs/airbnb-senior-data-scientist                a vacancy at WeWorkRemotely
#   /jobs/software        /jobs/devops        /remote-jobs/data-cleaning      categories
#
# Four or more hyphenated words is the line: the two false positives carry five and six,
# while "software", "devops" and "data-cleaning" carry one or two.
#
# Length alone is not enough, though, and one URL proved it immediately --
# "data-engineer-jobs-in-austria" is five words and a category page. What separates them is
# the word "jobs" itself: a board names a category after the thing it lists, and a posting
# is named after the role. So a long slug that says "jobs" is still a category.
_TITLE_SHAPED_SEGMENT = re.compile(r'/[a-z0-9]+(?:-[a-z0-9]+){3,}/?(?:[?#]|$)', re.I)
_SLUG_SAYS_LIST = re.compile(
    r'\b(?:jobs?|stellen|stellenangebote|vacatures|vacancies|offres|empleos|karriere)\b',
    re.I)


# A path that ENDS at /jobs is a list, whatever came before it. This costs nothing and
# fixes a real leak: pnet.co.za/cmp/en/ista-personnel-solutions-73462/jobs carries a
# five-digit id and so read as a posting, but the id belongs to the COMPANY and the page is
# that company's own list of vacancies -- title "Your search returned 12 jobs".
#
# ...unless the query string names one posting, which is how the Ashby, Greenhouse and Lever
# boards address a single vacancy. Measured: superhuman.com/company/careers/jobs?ashby_jid=
# bc3c8fd3-470d-4a97-8602-dcafd1e72219 is one real job titled "Corporate Security Engineer",
# and the first version of this rule threw it away.
_ENDS_AT_A_LIST = re.compile(r'/(?:jobs?|stellenangebote|vacatures|offres)/?(?:[?#]|$)', re.I)
# A path segment that is nothing but digits is an id, and an id is one posting. This is
# what keeps careers.lla.com/jobs/77601/job -- a real vacancy whose path ends at /job -- out
# of the rule above, while pnet.co.za/cmp/en/ista-personnel-solutions-73462/jobs stays in:
# that 73462 is glued to a company name, not a segment of its own.
_NUMERIC_SEGMENT = re.compile(r'/\d{4,}(?:[/?#]|$)')
# NAMED parameters only. A second alternative matched any parameter whose value was 16+ hex
# characters, on the reasoning that a hash that long is an id -- and it immediately claimed
# an index page as a posting:
#
#   meetfrank.com/?category=FULLY_REMOTE&…&speciality=5995b157871fb3a5190aa2ff
#   titled "13 Fully Remote Data & Analytics Jobs in Austria"
#
# That is a filter parameter carrying a MongoDB ObjectId, and it is shaped exactly like a
# posting id. The parameter's NAME is the only thing that separates them.
_QUERY_NAMES_ONE = re.compile(
    r'[?&](?:[a-z_]*(?:jid|job_?id|gh_jid|lever|posting|vacancy|offer|req)[a-z_]*)=[^&#]{4,}',
    re.I)


def is_single_posting_url(url) -> bool:
    """Does this address point at one vacancy?"""
    text = str(url or '')
    # A collection is an article about several companies, whatever its slug looks like.
    if _COLLECTION_URL.search(text):
        return False
    if _QUERY_NAMES_ONE.search(text) or _NUMERIC_SEGMENT.search(text):
        return True
    if _ENDS_AT_A_LIST.search(text):
        return False
    if _SINGLE_POSTING_URL.search(text):
        return True
    title_like = _TITLE_SHAPED_SEGMENT.search(text)
    if not title_like:
        return False
    # "jobs" anywhere in the path, not just inside the matched segment. karriere.at puts the
    # word one segment up -- /jobs/sankt-ruprecht-an-der-raab -- and reading only the last
    # segment made a town's job list look like a posting called "Sankt Ruprecht an der Raab".
    # weworkremotely.com/remote-jobs/airbnb-senior-data-scientist is the case this must not
    # break, and does not: what separates them is that its slug names a company and a role
    # while karriere.at's names a place, so the trailing segment still has to carry a word
    # the listing vocabulary does not claim.
    return bool(title_like and not _SLUG_SAYS_LIST.search(title_like.group(0)))


# Two URL rules were tried here and BOTH were reverted, because measuring them against
# 31,351 real rows showed each one costing genuine vacancies to catch index pages the title
# rule above already catches for free.
#
# The first asked whether the trailing segment looks like a PLACE, by the joining words a
# German town carries -- "-an-der-", "-am-", "-in-". Those letters appear mid-phrase in
# English and it immediately lost:
#     /remote-jobs/toptal-ai-ml-engineer-for-AN-ai-driven-e-commerce-platform
#     /job/senior-forward-deployed-ai-engineer-remote-eligible-IN-germany
#
# The second inverted it: keep the row when the slug names a role. Job titles are far too
# varied for a word list, and it lost a dozen more at once --
#     /remote-jobs/huntress-evergreen-sales-development-representative
#     /remote-jobs/vercel-member-of-the-technical-staff-internal-agent
#     /remote-jobs/toggl-senior-full-stack
#     /de/jobs/director-operations-w-m-d
#
# weworkremotely.com/remote-jobs/<slug> and karriere.at/jobs/<place> are the same shape, and
# no amount of vocabulary separates them from the address alone. What DOES separate them is
# that the index page counts its vacancies in the title and the vacancy never does, which is
# exactly what _COUNTS_VACANCIES reads. The URL is the wrong place to solve this.


# =========================================================================================
# A VACANCY THAT IS GONE
# =========================================================================================
#
# Some of what a search collects is a posting that has already been taken down -- the board
# still serves the address, but the page now says so. Nothing in this app noticed: a page
# reading "Job Not Found. This job listing has been removed" has a title, a URL and enough
# text to pass every other check, so it reached Claude and could be shown to the user as a job
# to apply for.
#
# Measured across 26,216 unique listings on disk: 23 say they are gone. Every phrase below
# is one that actually occurred, and the longest of the 23 -- where a false positive would
# hide, because a long page has room to say "no longer" about something else -- were read
# one by one and every one is a dead vacancy:
#
#   11,441 ch  "Apply Shortlist This vacancy has expired This doesn't mean the journey ends"
#    5,611 ch  "Data Scientist bei Hutchison Drei Austria GmbH ist auf karriere.at leider
#               nicht mehr verfügbar"
#    3,825 ch  "Data Scientist / AI Engineer This job has expired Date Posted: 4 September"
#    2,039 ch  "This job is no longer available. We are looking for an experienced PL/SQL"
#
# Read from the OPENING of the page only. A board puts the notice where a visitor sees it
# first; an advert that mentions something being unavailable does so in its body, about
# something else.
_GONE_NOTICE = re.compile(
    r'\bjob not found\b'
    r'|\bthis job (?:listing |posting |ad )?(?:has been|was) (?:removed|deleted|closed|filled)'
    r'|\b(?:job|position|posting|vacancy|listing) is no longer available\b'
    r'|\bthis (?:job|position|vacancy) has (?:expired|been filled|closed)\b'
    r'|\b(?:stelle|stellenanzeige|anzeige|position) ist nicht mehr (?:verf[üu]gbar|aktiv|online)'
    r'|\bist (?:auf \S+ )?leider nicht mehr verf[üu]gbar'
    r'|\b(?:stelle|position) wurde (?:bereits )?besetzt'
    r'|\bvacature is niet meer beschikbaar\b', re.I)
_GONE_NOTICE_WITHIN = 600


# A page that answers with the board's own index of other vacancies instead of the posting.
# aijobs.net is the one that exposed it, and reading the page settled what it means: every
# old /job/… address there now redirects to foorilla.com/hiring/, a general list. The
# vacancy is gone; the address simply does not say so in words.
#
# The signature is the index's own shape -- "[SE][Full Time] USD 145K-166K Remote job [R]"
# repeated down the page. Measured over 21,679 real listings from four runs: 8 pages read
# like this, every one of them aijobs.net, each carrying 264 to 271 of these tags where
# nothing else reaches eight.
#
# It matters beyond tidiness: one of the two in the Oslo run was kept as REMOTE work, and
# the word "Remote" came from somebody else's vacancy further down that list.
_BOARD_INDEX_TAG = re.compile(
    r'\[(?:SE|MI|EN|EX|R|RF|H|Full Time|Part Time|Internship|Contract|Freelance)\]')
_BOARD_INDEX_PHRASE = re.compile(
    r'[\d.,]+\s+new jobs found|export as csv|distribution by experience', re.I)
_MIN_BOARD_INDEX_TAGS = 8


def is_board_index_text(description) -> bool:
    """True when this text is a job board's own index of other vacancies, not a posting."""
    text = ' '.join(str(description or '').split())
    if not text:
        return False
    return (len(_BOARD_INDEX_TAG.findall(text)) >= _MIN_BOARD_INDEX_TAGS
            or bool(_BOARD_INDEX_PHRASE.search(text[:2000])))


def is_gone(row) -> bool:
    """Does this address still serve this vacancy?

    Two ways it does not. The page says so in words -- "This job has expired", "leider nicht
    mehr verfügbar" -- or it answers with the board's own list of other jobs, which is what a
    board does when the posting is no longer there and it would rather show you something.
    """
    opening = ' '.join(str(row.get('description') or '').split())[:_GONE_NOTICE_WITHIN]
    if _GONE_NOTICE.search(opening):
        return True
    return is_board_index_text(row.get('description'))


def remove_dead_postings(rows: list) -> tuple:
    """Drop the postings that say they are gone. Returns (kept, removed)."""
    kept: list = []
    removed: list = []
    for row in rows:
        (removed if is_gone(row) else kept).append(row)
    return kept, removed


def is_listing_page(row) -> bool:
    """True when this row is a page of vacancies rather than a vacancy.

    The single-posting check runs first and wins outright. Everything after it is evidence
    that a page lists jobs: the path says so, or the title counts them ("12 open jobs",
    "aktuell 1.500+ offen").
    """
    url = str(row.get('url') or '')
    title = str(row.get('title') or '')
    # Counting vacancies outranks everything, including the single-posting address. See
    # _COUNTS_VACANCIES for why this one title signal is allowed to win where the loose
    # "says jobs" rule is not.
    if _COUNTS_VACANCIES.search(title):
        return True
    if _COLLECTION_URL.search(url):
        return True
    if is_single_posting_url(url):
        return False
    if _LISTING_URL.search(url):
        return True
    return bool(_LISTING_TITLE.search(title))


# Written onto an index page once its contents have actually been taken out of it. Only a
# page carrying this may be discarded -- see remove_listing_pages.
EMPTIED_KEY = '_listing_page_emptied'

# Set when a page held postings but every one was already in the search -- the later pages of
# a paginated listing, in other words. Kept apart from EMPTIED_KEY because the two lead to
# different words in the Log and one of them is an instruction to go and fix a site. A real
# German run told the user that 53 XING pages "gave up nothing"; 162 XING postings were in that
# run's results and 96 came out of those very pages.
_ALREADY_HAD_KEY = '_listing_page_already_had'


def remove_listing_pages(rows: list) -> tuple:
    """Drop the index pages whose contents were already taken. Returns (kept, removed).

    An index page is only worth discarding once it has given up the vacancies inside it.
    Measured over all 197 index pages in the Austrian corpus: every one fetched
    successfully, 165 gave up 2,185 postings between them, and **32 gave up nothing** --
    not through any network failure, but because no link on them matched a known posting
    shape. navartisglobal.com is the plainest case: 84 links on the page, not one
    recognisable.

    For a while those 32 were kept, on the reasoning that discarding them would take
    whatever they listed with them. The user asked the question that undoes it: what good is a
    kept page that gave up nothing? Measured on the second German run, none at all. Of the
    88 that could not be emptied, 76 were dropped by the ordinary filters anyway, and every
    one of the 12 that reached Claude was an index page -- "Data Science Jobs in Germany -
    2026", "AI Jobs in Berlin", "Analytics Engineer Jobs in Germany" -- 61,845 characters
    of nothing.

    The reasoning was wrong in a specific way. Keeping a page only saves the vacancies
    inside it if keeping it is a route to them, and when the page could not be emptied it
    is not: those jobs were never collected and no later step collects them. Nothing is
    lost by discarding the page that was not already lost.

    What the rule was really protecting is A-4 -- a genuine vacancy misread as an index,
    where keeping it saves a real job. That is now handled where it belongs, in
    `is_single_posting_url`, and handled exactly: both of the real vacancies A-4 named,
    `aop-health.com/.../careers/jobs/supply-chain-business-excellence-manager` and
    `weworkremotely.com/remote-jobs/airbnb-senior-data-scientist`, are recognised as single
    postings and never reach this function as candidates.

    So every index page goes, emptied or not -- and the ones that gave nothing up are
    returned separately, because a site whose postings cannot be recognised is a real gap
    worth naming in the Log rather than a row worth keeping.

    Deliberately its own function in its own module rather than another clause inside the
    filter chain: it answers a question about what a URL IS, not about whether the user would
    want the job, and those are different subjects that fail in different ways.
    """
    kept: list = []
    removed: list = []
    for row in rows:
        (removed if is_listing_page(row) else kept).append(row)
    return kept, removed


# ---------------------------------------------------------------------------------------
# Opening them up
# ---------------------------------------------------------------------------------------

# Eight at a time, the same ceiling enrichment uses: enough to hide the latency, low enough
# not to look like an attack to any one site.
EXPAND_MAX_WORKERS = 8

# A description shorter than this is not a posting -- an error page, a consent wall, a shell
# -- and admitting it would put a row into the search that says nothing.
EXPAND_MIN_DESCRIPTION_CHARS = 200

# How many postings one index page may contribute. A category page can link to hundreds, and
# a search that quietly turned into a crawl of karriere.at would be a different program.
EXPAND_MAX_PER_PAGE = 60


def _normalised(url) -> str:
    return str(url or '').split('#')[0].rstrip('/').lower()


def postings_inside(html: str, page_url: str, known: set) -> list:
    """The single-posting URLs on an index page that the search does not already have.

    One level, and only one. A category page links to other category pages, and following
    those is how a job search becomes a site crawl -- so a link is taken only when its own
    shape says it is a posting, never because it is another index.
    """
    from bs4 import BeautifulSoup

    from .fetcher import same_domain_links

    out, seen = [], set()
    for link in same_domain_links(BeautifulSoup(html, 'html.parser'), page_url):
        key = _normalised(link)
        if key in known or key in seen or not is_single_posting_url(link):
            continue
        seen.add(key)
        out.append(link)
        if len(out) >= EXPAND_MAX_PER_PAGE:
            break
    return out


def _collect_links_inside(indexes, known, progress_cb, should_cancel):
    """Open each listing page and gather the postings linked inside it.

    One fetch per page, in parallel. Returns the (link, parent row) pairs worth fetching --
    only links this search has not already seen, so a page that merely repeats what the
    search found costs nothing more than the one fetch that proved it.
    """
    import concurrent.futures

    from .fetcher import fetch

    wanted: list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=EXPAND_MAX_WORKERS) as pool:
        futures = {pool.submit(fetch, str(row.get('url')), needs_links=True): row
                   for row in indexes}
        for future in concurrent.futures.as_completed(futures):
            row = futures[future]
            if should_cancel and should_cancel():
                for pending in futures:
                    pending.cancel()
                break
            try:
                html = future.result().html
            except Exception:                                   # noqa: BLE001
                continue
            if not html:
                continue
            found = postings_inside(html, str(row.get('url')), known)
            if not found:
                # Nothing NEW came out -- which is two very different things, and telling
                # them apart matters more than it looks.
                #
                # A real German run reported "53 pages from www.xing.com gave up nothing",
                # and that reads as "XING is broken, go and fix it". XING was not broken:
                # 162 of its postings are in that run's results and 96 of them came out of
                # these very pages. The later pages repeated the earlier ones, and
                # postings_inside deliberately skips a link the search already has.
                #
                # So: ask again ignoring what is already known. If the page does hold
                # postings we simply had them all, that is a page working perfectly, and
                # saying otherwise sends the user to fix a site that is fine.
                anything = postings_inside(html, str(row.get('url')), set())
                if anything:
                    row[_ALREADY_HAD_KEY] = True
                # Either way the page keeps its contents as far as this app can tell, so
                # it is NOT marked emptied and remove_listing_pages leaves it alone.
                continue
            row[EMPTIED_KEY] = True
            for link in found:
                known.add(_normalised(link))
                wanted.append((link, row))

    emptied = sum(1 for row in indexes if row.get(EMPTIED_KEY))
    already = sum(1 for row in indexes if row.get(_ALREADY_HAD_KEY))
    unreadable = len(indexes) - emptied - already
    if progress_cb and already:
        # Not a warning: this is a page that worked. Every posting on it was already in
        # the search, which is what the later pages of a paginated listing look like.
        progress_cb('GLOG:expand|info|%d page(s) held only postings the search already '
                    'had — nothing missed there.' % already, 0, 1)
    if progress_cb and unreadable:
        # THIS is the one worth acting on, and it is worth separating from the line above:
        # a page whose postings cannot be recognised at all is a gap in the URL patterns,
        # and the two used to be reported as one number. On a real German run that number
        # was 81 and it named www.xing.com 53 times -- a site whose postings were being
        # read perfectly well.
        progress_cb('GLOG:expand|warning|%d of %d page(s) list jobs but nothing on them '
                    'could be recognised as a posting — those sites need a URL pattern '
                    'before their jobs can be collected.'
                    % (unreadable, len(indexes)), 0, 1)

    if not wanted:
        if progress_cb:
            progress_cb('GLOG:expand|info|No new postings were reachable inside them.', 0, 1)
        return []

    if progress_cb:
        progress_cb('GLOG:expand|info|%d posting(s) found inside. Fetching each one.'
                    % len(wanted), 0, len(wanted))
    return wanted


def _build_rows_from_links(wanted, progress_cb, should_cancel):
    """Fetch each posting found inside a listing page and turn it into a row.

    One fetch per posting, in parallel, and never the browser rung: this runs over hundreds
    of pages and a launch-and-render is measured in seconds. A page only a full browser can
    read stays unread, which is the cheaper loss.
    """
    import concurrent.futures

    from .enrich import readable_text
    from .errors import SearchCancelled
    from .fetcher import fetch

    def build(item):
        link, parent = item
        try:
            # allow_browser=False, for the same reason enrich.py gives: this loop runs
            # EXPAND_MAX_WORKERS threads over hundreds of pages, and the browser rung is a
            # launch-and-render measured in seconds. One page needing it is fine; fifty
            # would turn a three-minute stage into an hour. A page only a full browser can
            # read stays unread, which is the cheaper loss.
            html = fetch(link, allow_browser=False).html
        except Exception:                                       # noqa: BLE001
            return None
        if not html:
            return None
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        heading = soup.find('h1')
        title = (heading.get_text(' ').strip() if heading
                 else (soup.title.get_text().strip() if soup.title else ''))
        description = readable_text(html)
        if not title or len(description) < EXPAND_MIN_DESCRIPTION_CHARS:
            return None
        return {
            'title': ' '.join(title.split())[:180],
            'description': description,
            'company': '',
            'location': '',
            'country': parent.get('country') or '',
            'url': link,
            'platform': parent.get('platform') or 'google',
            'source': 'listing page: %s' % str(parent.get('title') or '')[:60],
        }

    built = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=EXPAND_MAX_WORKERS) as pool:
            futures = {pool.submit(build, item): item for item in wanted}
            for future in concurrent.futures.as_completed(futures):
                if should_cancel and should_cancel():
                    for pending in futures:
                        pending.cancel()
                    break
                try:
                    row = future.result()
                except Exception:                               # noqa: BLE001
                    continue
                if row:
                    built.append(row)
    except SearchCancelled:
        raise

    if progress_cb:
        progress_cb('GLOG:expand|success|%d listing(s) recovered from pages that would '
                    'otherwise have been thrown away.' % len(built), 0, 1)
    return built


def expand_listing_pages(rows: list, progress_cb=None, should_cancel=None) -> list:
    """Open every index page in `rows` and return the postings found inside.

    The user's instruction, and the reason it is worth the wall-clock: [owner's note: time does not matter, and no listing may be lost]. Measured on the real Austrian corpus, nine index pages held 43 job
    URLs the search had never seen, every one of them fetched cleanly, and two cleared the
    whole filter chain -- both remote roles at arc.dev that would otherwise have been thrown
    away with the page that listed them.

    Additive and safe to fail: anything that cannot be fetched is simply not returned, and
    the search carries on with what it had. The index pages themselves are NOT removed here
    -- that is remove_listing_pages' job, and keeping the two separate means expanding can
    be switched off without changing what gets filtered.
    """
    indexes = [row for row in rows if is_listing_page(row) and str(row.get('url') or '')]
    if not indexes:
        return []

    known = {_normalised(row.get('url')) for row in rows}

    if progress_cb:
        progress_cb('GLOG:expand|info|%d page(s) in this search list jobs rather than being '
                    'one. Opening each to collect the postings inside — this is free, and it '
                    'is where jobs were being lost.' % len(indexes), 0, 1)

    wanted = _collect_links_inside(indexes, known, progress_cb, should_cancel)
    if not wanted:
        return []
    return _build_rows_from_links(wanted, progress_cb, should_cancel)

