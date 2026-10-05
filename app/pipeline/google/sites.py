# -*- coding: utf-8 -*-
"""Which sites a Google search covers, and how a posting's URL looks on each.

Every list here was arrived at by running real searches and reading what came back, so each
carries the reasoning that put it there. They sit in their own module because they are read
by all four halves of the Google search and by the direct-site search besides -- a constant
that three callers share does not belong inside any one of them.
"""
from __future__ import annotations

import re

from ..search_title import DEFAULT_SEARCH_TITLE, quoted, title_forms


# `import *` skips anything starting with an underscore, and several of these do.
# Naming them all here is what keeps `from .google import _GOOGLE_QUERY_LOCATION_PATTERN`
# working for the callers that were importing it before the split.
__all__ = [
    'GOOGLE_SEARCH_ACTOR',
    'GOOGLE_QUERY_ROLE_TERMS',
    'GOOGLE_EXCLUDED_JOB_BOARDS',
    'GOOGLE_EXCLUDED_TLD_HINTS',
    'GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS',
    'GOOGLE_GLOBAL_EXTRA_SITES',
    'GOOGLE_GLOBAL_SITES_PER_GROUP',
    'GLOBAL_STARTUP_SITES',
    'COUNTRY_STARTUP_SITES',
    '_GOOGLE_QUERY_LOCATION_PATTERN',
    'GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT',
    '_PATTERN_CRAWL_BATCH_SIZE',
    '_DEEP_CRAWL_BATCH_SIZE',
    '_MAX_PATTERN_DISCOVERIES_PER_RUN',
]



GOOGLE_SEARCH_ACTOR = 'apify/google-search-scraper'


# Curated, Google-friendly role terms -- actual job-title phrases search far better on
# Google full-text search than the broad OR-list used for the structured platform APIs
# (KEYWORDS above); a bare "AI" or "Big Data" term alone is far too noisy for Google.
# Deliberately trimmed from an earlier 8-term list (which also had "ML Engineer",
# "NLP Engineer", "Computer Vision Engineer"), and later again from 5 to these 4
# (dropping "Data Analyst") -- freeing up word budget in the ~32-word query limit for more entries in
# GOOGLE_EXCLUDED_TLD_HINTS below (more real domain exclusions = less wasted cost on
# LinkedIn/Indeed/Glassdoor pages Google shouldn't be scraping in the first place). The
# trade-off: a listing titled exactly "NLP Engineer" or "Data Analyst" with none of
# these 4 phrases anywhere else on the page could be missed -- accepted deliberately for the cost win.
# The default title's forms. A real search passes the title Sina typed instead.
GOOGLE_QUERY_ROLE_TERMS = quoted(title_forms(DEFAULT_SEARCH_TITLE))


# LinkedIn, Indeed, and Glassdoor are already searched directly (and better) by their own
# dedicated actors above, for both countries and cities -- so Google is explicitly told to
# never return results from those three domains at all, to avoid ever reprocessing the same
# listings through a worse (unstructured, no full-JD-guaranteed) path. Google is only meant
# to surface company career pages and other job boards those three don't cover.
#
# This list is deliberately just the brand keyword, not a full domain -- checked as a
# plain substring against the URL (see the app-side filter in run_search and
# _is_excluded_job_board below), not as an exact ".com" suffix match. This was found
# to matter for real: a live test turned up a result from glassdoor.ca (the Canadian
# domain) that an earlier ".com"-only substring check let straight through. Indeed and
# Glassdoor both have dozens of country-specific domains/subdomains (indeed.co.uk,
# indeed.de, glassdoor.ca, ...) that can't realistically be enumerated in the query
# itself (see GOOGLE_EXCLUDED_TLD_HINTS below), so brand-substring matching here is
# what actually guarantees these three are never processed, regardless of TLD.
GOOGLE_EXCLUDED_JOB_BOARDS = ['linkedin', 'indeed', 'glassdoor']


# Best-effort query-level exclusions -- this reduces cost by stopping Google from
# returning (and websiteContentScraper from billing for) these domains in the first
# place, but can NOT be relied on alone for correctness: Google's `site:` operator
# requires one exact domain per entry, and there are more country-specific domains than
# could ever fit in the ~32-word query limit. The GOOGLE_EXCLUDED_JOB_BOARDS substring
# filter above is what actually guarantees correctness; this list is just cost
# reduction, covering the domains most likely to actually appear for the countries/
# cities this app searches (trimming GOOGLE_QUERY_ROLE_TERMS above to 4 terms freed up
# enough budget to list this many).
GOOGLE_EXCLUDED_TLD_HINTS = [
    'linkedin.com',
    'indeed.com', 'indeed.co.uk', 'indeed.ca', 'indeed.com.au', 'indeed.ie',
    'glassdoor.com', 'glassdoor.ca', 'glassdoor.co.uk', 'glassdoor.de', 'glassdoor.com.au', 'glassdoor.ie',
]


# For each known job site, the URL glob pattern its individual job-posting pages
# actually follow -- discovered one-by-one via real, live tests (fetching a real search
# results page for each domain, with `htmlTransformer: 'none'`, and inspecting its raw
# HTML for the real <a href> links, since the default "readable content" extraction was
# found to sometimes pick the wrong part of the page entirely -- e.g. finn.no's category
# filter sidebar instead of its job listings). Used by _deepen_google_results below to
# tell the deep-crawl actor which same-domain links are worth following into. A domain
# with no entry here just means that stage's result won't be deep-crawled -- some sites
# (werk.nl, arbetsformedlingen.se, jobnet.dk, duunitori.fi, vdab.be, jobat.be,
# ziprecruiter.com, karrierestart.no, ...) were tested and found to not expose real job
# links in their initial page load at all (cookie walls, bot detection, or job cards
# that never resolve to a plain crawlable href even after full rendering) -- for those,
# this feature simply doesn't add anything, same as before it existed.
GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS = {
    'finn.no': ['https://www.finn.no/job/ad/**'],
    'arbeidsplassen.nav.no': ['https://arbeidsplassen.nav.no/stillinger/stilling/**'],
    'jobindex.dk': ['https://www.jobindex.dk/vis-job/**'],
    'arbeitsagentur.de': ['https://www.arbeitsagentur.de/jobsuche/jobdetail/**'],
    'karriere.at': ['https://www.karriere.at/jobs/**'],
    'hellowork.com': ['https://www.hellowork.com/fr-fr/emplois/**'],
    'infojobs.net': ['https://www.infojobs.net/**/of-i**'],
    'reed.co.uk': ['https://www.reed.co.uk/jobs/**'],
    'jobbank.gc.ca': ['https://www.jobbank.gc.ca/jobsearch/jobposting/**'],
    # Found by asking why seven Dutch-search sites produced nothing at all. Six of them
    # render their listings in JavaScript or offer only category links, and there is no
    # pattern to be had. This one was different: its /jobs page opens through the Apify
    # rung with 709 KB and 48 links, and the app's own pattern discovery learned
    # "/job/**" from it unprompted. Without an entry here its postings were never
    # deepened into individual rows.
    'us.foundersbase.com': ['https://us.foundersbase.com/job/**'],
    # seek.com.au deliberately has no entry here -- see the comment above
    # DIRECT_SEARCH_URL_BUILDERS for why (confirmed 403 bot-blocking that turned a
    # real test into a 26+ minute retry storm).
    'dice.com': ['https://www.dice.com/job-detail/**'],
    'net-empregos.com': ['https://www.net-empregos.com/[0-9]**'],
    'stepstone.de': ['https://www.stepstone.de/stellenangebote--**'],
    'stepstone.at': ['https://www.stepstone.at/stellenangebote--**'],
    'xing.com': ['https://www.xing.com/jobs/*'],
    'totaljobs.com': ['https://www.totaljobs.com/job/**'],
    'cv-library.co.uk': ['https://www.cv-library.co.uk/job/**'],
    'jora.com': ['https://au.jora.com/job/**'],
    'francetravail.fr': ['https://candidat.francetravail.fr/offres/recherche/detail/**'],
    'apec.fr': ['https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/**'],
    'vdab.be': ['https://www.vdab.be/vindeenjob/vacatures/**'],
    'actiris.brussels': ['https://www.actiris.brussels/fr/citoyens/detail-offre-d-emploi/**'],
    'moovijob.com': ['https://en.moovijob.com/job-offers/**'],
    'tecnoempleo.com': ['https://www.tecnoempleo.com/*/*/rf-**'],
    'cwjobs.co.uk': ['https://www.cwjobs.co.uk/job/**'],
    'app.welcometothejungle.com': ['https://app.welcometothejungle.com/jobs/**'],
    'workatastartup.com': ['https://www.workatastartup.com/jobs/**'],
    # jobs.ch, jobup.ch, arbetsformedlingen.se, europa.eu (EURES), remotive.com, and
    # remoteok.com all deliberately have no entry here (or anywhere else in this dict)
    # any more -- each already has a free, direct JSON-API integration returning the
    # same listings at zero Apify cost (see _run_direct_api_searches), so a real cost
    # audit removed them from COUNTRY_JOB_SITES/GOOGLE_GLOBAL_EXTRA_SITES entirely,
    # which makes their own deep-crawl pattern here unreachable anyway. See the
    # comments above COUNTRY_JOB_SITES and GOOGLE_GLOBAL_EXTRA_SITES for the full
    # reasoning (including the one exception, arbeitsagentur.de, kept as-is since its
    # free API's description is thinner than what Google+Deep-Crawl can find).
    # arc.dev also serves localized variants (e.g. /en-id/remote-jobs/details/**) --
    # both patterns are needed to catch the non-localized and localized postings alike.
    'arc.dev': ['https://arc.dev/remote-jobs/details/**', 'https://arc.dev/*/remote-jobs/details/**'],
    'aijobs.ai': ['https://aijobs.ai/job/**'],
    # Confirmed via a real Playwright fetch of each site's own listing page (not
    # guessed): aijobs.net's postings are /job/{slug}-{id}/ (note: singular "job",
    # unlike aijobs.ai's above), wellfound.com's are /jobs/{id}-{slug}. wellfound.com's
    # own support docs warn against hand-constructing its *search* URLs -- irrelevant
    # here, since this dict only recognizes real links Google already indexed, never
    # builds a search URL itself.
    'aijobs.net': ['https://aijobs.net/job/**'],
    'wellfound.com': ['https://wellfound.com/jobs/**'],
    # weworkremotely.com and ziprecruiter.com deliberately have no entry here -- this
    # dict only feeds Apify's cloud-hosted crawler (_deepen_google_results below), which
    # is headless/datacenter-IP based and got served a Cloudflare bot-challenge for
    # both, confirming that path specifically is blocked (not just "unconfirmed
    # pattern"). weworkremotely.com's block turned out to be headless-detection
    # specifically, not automation in general -- see MANUAL_ASSIST_GLOBAL_SITES below,
    # where the exact same domain works fine through the browser-site path since that
    # one always runs a real, visible (headless=False) browser.
    # work.turing.com and work.mercor.com deliberately have no entry here either -- not
    # because they lack a public listing (an earlier pass wrongly concluded that; Sina
    # actually opened both in his own browser, before logging in, and found real search
    # boxes with real results -- see MANUAL_ASSIST_GLOBAL_SITES below, since Google's
    # own indexed pages here are auto-generated JS cards with no real <a href> to a
    # specific role at all, so this dict (which needs a real link pattern) can't help
    # either way).
    'itjobs.pt': ['https://www.itjobs.pt/oferta/**'],
    # swissdevjobs.ch is bilingual -- postings exist under both the plain and /de/ paths.
    'swissdevjobs.ch': ['https://swissdevjobs.ch/jobs/**', 'https://swissdevjobs.ch/de/jobs/**'],
    # jobly.fi is bilingual too -- Finnish postings under /tyopaikka/, English under /en/job/.
    'jobly.fi': ['https://www.jobly.fi/tyopaikka/**', 'https://www.jobly.fi/en/job/**'],
    'tyomarkkinatori.fi': ['https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat/**'],
    'it-jobbank.dk': ['https://www.it-jobbank.dk/jobannonce/**'],
    'builtin.com': ['https://builtin.com/job/**'],
    'wearedevelopers.com': ['https://www.wearedevelopers.com/jobs/ext/**'],
    'iamexpat.de': ['https://www.iamexpat.de/career/jobs-germany/**'],
    # berlinstartupjobs.com puts each posting at /<category>/<slug>, where the category
    # is one of its own job categories. Discovered by opening a real listing page and
    # reading its `.jobs-list-items` block, then VERIFIED by opening one of the links:
    # https://berlinstartupjobs.com/engineering/senior-backend-developer-golang-m-f-d-datatroniq/
    # returns "Job Vacancy: Senior Backend Developer - Go & Kubernetes // DATATRONiQ",
    # 7,317 characters, and is not a search page.
    #
    # The categories are listed explicitly rather than using a bare /*/* glob, because
    # /skill-areas/<x> and /companies/<x> have the same shape and are NOT job postings --
    # crawling those would spend Apify credit on category and company pages.
    'berlinstartupjobs.com': [
        'https://berlinstartupjobs.com/engineering/**',
        'https://berlinstartupjobs.com/marketing/**',
        'https://berlinstartupjobs.com/design-ux/**',
        'https://berlinstartupjobs.com/operations/**',
        'https://berlinstartupjobs.com/sales/**',
        'https://berlinstartupjobs.com/product-management/**',
        'https://berlinstartupjobs.com/hr-recruiting/**',
        'https://berlinstartupjobs.com/finance/**',
        'https://berlinstartupjobs.com/internships/**',
        'https://berlinstartupjobs.com/contracting-positions/**',
    ],
    'iamexpat.nl': ['https://www.iamexpat.nl/career/jobs-netherlands/**'],
    # careerone.com.au deliberately has no entry here either -- see the comment above
    # DIRECT_SEARCH_URL_BUILDERS for why (confirmed 403 bot-blocking on every
    # individual job page, same failure as seek.com.au).
    # duunitori.fi and jooble.org deliberately have no entry here either, despite a
    # confirmed real job-URL pattern existing for both (/tyopaikat/tyo/** and
    # *.jooble.org/desc/** respectively) -- real live tests found Apify's crawler
    # infrastructure gets fully blocked by both sites regardless of purpose (confirmed
    # for jooble.org via an explicit "blocked status code: 403" even after Apify's own
    # anti-blocking proxy rotation; duunitori.fi returned zero content under both
    # playwright and cheerio crawler modes). Leaving these patterns in place would only
    # make _deepen_google_results waste time/cost repeatedly failing the same way
    # whenever either domain shows up in a regular Google search result. jooble.org is
    # now also removed from GOOGLE_GLOBAL_EXTRA_SITES entirely (see that list's
    # comment) -- this entry stays only for the rare case a jooble.org URL surfaces
    # from an unrelated Google query.
    # ziprecruiter.com deliberately has no entry here -- still no confirmed individual
    # job-URL pattern; its direct search URL
    # still gets scraped for whatever content is on the listing page itself, just
    # without deep-crawling into individual postings.
}


# Sina-supplied sites that aren't tied to any one country -- searched for *every*
# selected location (country or city), same as the country-specific known-sites list,
# just without a country lookup. work.turing.com and work.mercor.com are
# remote-work-focused platforms; remoteok.com, weworkremotely.com, wellfound.com
# (formerly AngelList Talent) are major remote-first job boards; aijobs.net is
# AI/ML/Data-specific -- these last 4 were added after Sina asked whether any major
# remote/AI-focused boards were still missing, since none of the country-specific or
# original global sites were remote-first the way this app's own Remote-only rule
# requires. ziprecruiter.com was tried here too but is actually US/Canada/UK-focused,
# not genuinely global, so it went back to being a United States entry in
# COUNTRY_JOB_SITES instead (must stay out of this list, or a US known-sites-stage query
# would wrongly self-classify as the global stage in _google_query_stage's substring
# check -- see that function's docstring). workatastartup.com (Y Combinator's own board,
# YC-backed startups only), remotive.com (hand-curated remote board with a dedicated
# engineering/data/AI vertical), arc.dev (remote-first, stack-based matching for
# engineers), and aijobs.ai (AI/ML/data-specific, distinct site from aijobs.net) were
# added after a broader "what other genuinely good sites are missing" research pass --
# each confirmed real/active and non-redundant with what was already here.
#
# jooble.org (and its country subdomains) was REMOVED from this list once its own real
# REST API was wired in (see JOOBLE_API_COUNTRIES / _fetch_jooble below) -- Google's
# `site:jooble.org` results could never be deep-crawled anyway (confirmed 403
# datacenter-IP block, see the comment above GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS), so
# keeping it here only produced a "no confirmed job-link pattern" warning every run for
# a mechanism that was dead on arrival and is now fully superseded by the API.
#
# remotive.com and remoteok.com REMOVED for the same reason, after a later cost audit:
# both already have a free direct JSON-API integration (_fetch_remotive/_fetch_remoteok,
# see _run_direct_api_searches) returning the exact same listings, full description
# text included, at zero Apify cost -- keeping them in the paid Google global-sites
# query + Deep-Crawl-eligible set only paid for a duplicate Filter would dedup away
# anyway. weworkremotely.com deliberately stays -- it has no free API of its own.
GOOGLE_GLOBAL_EXTRA_SITES = [
    'work.turing.com', 'work.mercor.com',
    'weworkremotely.com', 'aijobs.net', 'wellfound.com',
    'workatastartup.com', 'arc.dev', 'aijobs.ai',
]


# GOOGLE_GLOBAL_EXTRA_SITES no longer has to fit in one query line -- Sina asked for a
# way to keep adding global sites without ever running into Google's ~32-word query
# limit again. Split into groups of this size, each becoming its own query line per
# location (build_google_job_queries), so the total number of global sites is only
# bounded by how many extra lines we're willing to add, not by one line's word budget.
#
# Raised from 6 to 8 after a real cost audit found this could cut one whole query line
# (and its scraped/billed pages) per location for free: GOOGLE_GLOBAL_EXTRA_SITES had
# just shrunk to exactly 8 domains (remotive.com/remoteok.com removed -- see that
# list's own comment) and was still being split into 2 groups purely because of the
# old 6-per-group cap, not because 8 didn't fit. Verified with a real word-count check
# for every group size up to 12 domains, worst-case location ("United Kingdom", 2
# words, stacked with the longest role-term clause used so far): 8 domains = 30 words
# (safe), 9 domains = 32 words (right at the limit), 10+ exceeds it. 8 is therefore the
# exact right value -- not padded higher, so a real future 9th global site still
# correctly splits into its own new line automatically instead of risking the query
# limit, exactly what this whole per-group design exists to guarantee.
GOOGLE_GLOBAL_SITES_PER_GROUP = 8


# Dedicated startup/scaleup job boards -- a separate, additive Google stage Sina asked
# for after a real research pass (see the "Startup Websites Search" section): sites
# that specifically curate jobs at startups/scaleups, rather than the general-purpose
# boards in COUNTRY_JOB_SITES.
#
# GLOBAL_STARTUP_SITES: real, multi-country startup job boards (not tied to one
# country's local ecosystem) -- searched for every location, same idea as
# GOOGLE_GLOBAL_EXTRA_SITES. startup.jobs and topstartups.io were confirmed real and
# active during the Netherlands research pass but aren't Dutch-specific at all (they
# just happen to have a Netherlands filter page, same as any other country) -- moved
# here instead of duplicating them into every country's own list.
#
# COUNTRY_STARTUP_SITES: real, country-specific startup ecosystems' own job boards.
# Researched and confirmed country-by-country (Netherlands, then Germany so far) -- a
# country with no entry here just skips its OWN local sites (GLOBAL_STARTUP_SITES still
# always runs for it), same as COUNTRY_JOB_SITES' own per-country gap handling, so more
# countries can be added later without needing any other code changes.
#
# wellfound.com (Wellfound/AngelList Talent) and dutchtechjobs.com were deliberately
# left OUT of the Netherlands entry: wellfound.com is already in
# GOOGLE_GLOBAL_EXTRA_SITES (adding it here too would double-search it and break
# _google_query_stage's stage classification, which assumes GOOGLE_GLOBAL_EXTRA_SITES
# and this list are disjoint); dutchtechjobs.com was confirmed dead/expired-domain-for
# -sale in that same research pass, despite still being listed on Startup Amsterdam's
# own official page. handpickedberlin.com was tried for Germany but returned HTTP 403
# to a real fetch attempt (likely blocking automated access outright) -- left out since
# it couldn't be confirmed live/crawlable, unlike the two Germany sites below.
GLOBAL_STARTUP_SITES = ['startup.jobs', 'topstartups.io']


COUNTRY_STARTUP_SITES = {
    'Netherlands': [
        'scaleupjobs.nl', 'jobfluent.com', 'jobs.siliconcanals.com',
        'startupmap.iamsterdam.com', 'magnet.me', 'us.foundersbase.com',
    ],
    'Germany': ['berlinstartupjobs.com', 'startuplist.de'],
    # la-french-tech.welcomekit.co is the official French government-backed "Mission
    # French Tech" job board (NEXT40/Green20 + broader French Tech startup roster) --
    # confirmed real and live via a real fetch, and a different domain from
    # app.welcometothejungle.com (already a France COUNTRY_JOB_SITES entry) despite
    # both being hosted on Welcome to the Jungle's platform, so no overlap.
    # licornesociety.com confirmed real and live via a real fetch too (859 open
    # positions at French/European startups at the time of checking).
    'France': ['la-french-tech.welcomekit.co', 'www.licornesociety.com'],
    # workinstartups.com and builtinlondon.uk were both tried for the UK and rejected:
    # workinstartups.com returned HTTP 403 to a real fetch attempt (same
    # can't-confirm-crawlable reason handpickedberlin.com was excluded for Germany --
    # Google's own index having it doesn't mean RoleHound's own crawler can actually
    # reach it later); builtinlondon.uk is real and very active but lists jobs at
    # large established companies (Mastercard, Wells Fargo, Cloudflare, ...) alongside
    # startups, not startups specifically -- including it would wrongly label a big
    # company's listing as "Startup" (this stage's Type badge shows "Startup" directly
    # from being found here, no verification at all -- see display_category()).
    # londonstartupjobs.co.uk confirmed real and live via a real fetch (currently
    # thinner than the other countries' sites -- only a handful of open roles at the
    # time of checking -- but genuinely startup-specific and a sister site to the
    # already-confirmed berlinstartupjobs.com from the same operator).
    'United Kingdom': ['londonstartupjobs.co.uk'],
    # thehub.io ("The Hub") confirmed real, live, and very active (216 filtered jobs
    # at the time of checking) via a real fetch -- and confirmed to explicitly cover
    # Denmark, Finland, Iceland, Norway, and Sweden itself (Iceland isn't in
    # COUNTRIES), so it's added to all 4 of those Nordic countries at once rather than
    # researched one at a time. sting.co (Stockholm Innovation & Growth's own startup
    # jobs page) was also tried for Sweden and rejected -- real site, but a real fetch
    # found "0 results" / "No items found" in its listings at the time of checking, so
    # it's not worth including even though the site itself is legitimate.
    # www.supjobs.com (formerly startupjobs.se/"SUPJOBS", operating since 2009)
    # confirmed real and live via a real fetch (81 pages of listings at the time of
    # checking) -- Sweden-specific, on top of the shared Nordic thehub.io above.
    'Sweden': ['thehub.io', 'www.supjobs.com'],
    'Denmark': ['thehub.io'],
    'Finland': ['thehub.io'],
    'Norway': ['thehub.io'],
    # startup.ch (the obvious first candidate for Switzerland) returned HTTP 403 to a
    # real fetch attempt -- excluded, same reasoning as the other 403 cases above.
    # startupticker.ch/en/jobs confirmed real and live via a real fetch (40 recently
    # published jobs, dated within days of checking, powered by Joinup -- Switzerland's
    # startup employment platform).
    'Switzerland': ['www.startupticker.ch'],
    # Austria got a second, deeper research pass after Sina flagged it as especially
    # important to him and the first pass (austrianstartups.com alone) as weak --
    # metajob.at/startup-wien confirmed real and live via a real fetch, with 225 real,
    # recently-dated startup postings in Vienna at the time of checking (companies
    # like Hirebuddy, Brewcycle, krankenversichern.at) -- a much stronger source than
    # austrianstartups.com alone. karriere.at also has a real startup-filtered section
    # (karriere.at/jobs/startup/wien) but karriere.at itself is already a
    # COUNTRY_JOB_SITES entry for Austria, and the same domain can't be searched in two
    # disjoint stages (see _google_query_stage's disjointness requirement), so it
    # wasn't duplicated here.
    #
    # austrianstartups.com/opportunities is Austria's own startup association's board
    # -- a real fetch couldn't read its content directly (it's a JS-rendered community
    # platform), but a real Google search confirmed individually-indexed opportunity
    # pages exist (e.g. austrianstartups.com/opportunities/302304), proving Google can
    # and does crawl real individual postings there even though this session's own
    # fetch tool couldn't render them -- a weaker verification bar than metajob.at's,
    # noted here for that reason. "Opportunities" covers jobs, co-founder searches, and
    # volunteering together (not jobs exclusively), broader than the other countries'
    # sites but still genuinely startup-ecosystem-specific -- kept alongside metajob.at
    # rather than replaced by it, since it's still a real, additional source.
    'Austria': ['metajob.at', 'austrianstartups.com'],
    # startupjobsitaly.com confirmed real and live via a real fetch: 205 real
    # positions ("#1 job board for Italy's startup & tech ecosystem"), recently
    # updated. xjobs.cdpventurecapital.it confirmed real and live via a real fetch
    # too -- run by CDP Venture Capital (Italy's National Innovation Fund) for its own
    # startup portfolio, hundreds of real listings.
    'Italy': ['startupjobsitaly.com', 'xjobs.cdpventurecapital.it'],
    # www.startuphub.ai/countries/spain/jobs confirmed real and live via a real fetch
    # (183 open roles explicitly branded "AI and tech startups"). spainjobs.io was
    # also tried and rejected -- real and very active, but lists jobs at large
    # established companies (Google, Microsoft, Affirm, ...) alongside startups, same
    # "not startup-specific enough" reason builtinlondon.uk and Agoria were rejected
    # for (this stage's Type badge shows 'Startup' directly just from being found
    # here, no verification at all -- see display_category()).
    'Spain': ['www.startuphub.ai'],
    # www.startupjobs.pt confirmed real and live via a real fetch (real listings from
    # Portuguese startups/scaleups like Feedzai, Coverflex, Imaginary Cloud). landing
    # .jobs was also tried and rejected -- based in Lisbon, but explicitly "Tech Jobs
    # in Europe" (not Portugal-specific) with big-corporate partners (Siemens,
    # Volkswagen), same not-startup-specific-enough reason spainjobs.io/
    # builtinlondon.uk/Agoria were rejected for.
    'Portugal': ['www.startupjobs.pt'],
    # jobs.a16z.com confirmed real, live, and enormous via a real fetch: "852
    # companies. 18,964 jobs" across Andreessen Horowitz's own VC-backed portfolio,
    # with postings timestamped within hours -- extremely active. crunchboard.com
    # (TechCrunch's own job board) and himalayas.app were also tried and rejected --
    # crunchboard.com returned HTTP 403 to a real fetch; himalayas.app is real and
    # huge (97k+ listings) but general remote work, not startup-specific (large
    # enterprises like Thomson Reuters, Humana, Santander showed up in real listings).
    # workatastartup.com (Y Combinator) and wellfound.com are already covered globally
    # (GOOGLE_GLOBAL_EXTRA_SITES); app.welcometothejungle.com/dice.com/ziprecruiter
    # .com/builtin.com are already United States' own COUNTRY_JOB_SITES entries, so
    # none of those were duplicated here.
    'United States': ['jobs.a16z.com'],
    # www.startupsnorth.ca confirmed real, live, and large via a real fetch: literally
    # "Canada's Startup Job Board", 2,344+ open positions at venture-backed companies
    # (Cohere, Waabi, Xanadu, ...), 465 added in the week of checking alone.
    # dmz.torontomu.ca/dmz-startup-job-board (Toronto Metropolitan University's startup
    # incubator) confirmed real too, though thinner (only 2 listings visible at the
    # time of checking) -- kept anyway since it's a genuine, additional real source.
    'Canada': ['www.startupsnorth.ca', 'dmz.torontomu.ca'],
    # Two real, live, large Australian/NZ VC-portfolio job boards, same idea as
    # jobs.a16z.com for the US -- both confirmed via real fetches:
    # jobs.blackbird.vc ("Blackbird Job Board", Getro-powered) -- 1,195 open jobs
    # across Blackbird Ventures' 100+ portfolio companies (Canva, Culture Amp,
    # SafetyCulture, ...). squarepeg.getro.com ("Square Peg Job Board") -- 1,673 open
    # jobs across Square Peg Capital's portfolio (Canva, Airwallex, Bugcrowd, ...).
    # startupgalaxy.com.au returned HTTP 403 to a real fetch -- excluded, same
    # can't-confirm-crawlable reasoning as the other 403 cases. StartupAUS (the obvious
    # first candidate, a national startup body) was confirmed disbanded in 2021.
    'Australia': ['jobs.blackbird.vc', 'squarepeg.getro.com'],
}


# build_google_job_queries always emits a line shaped exactly
# `{role_clause} jobs {location} {site_clause}` -- so the location sits between the
# literal word "jobs" and the start of the site clause, which is always either `(` (an
# inclusive site: group) or `-site:` (the open-web stage's exclusions). Matching only
# that slice is what makes attribution exact.
_GOOGLE_QUERY_LOCATION_PATTERN = re.compile(r'\bjobs\s+(.*?)\s+(?:\(|-site:)', re.IGNORECASE)


# How many total pages (each start URL + every same-domain link found on/from it, one
# level deep) the deeper-crawl pass below is allowed to fetch per known-sites result --
# generous, since a real job board's listing/search page can easily link to 10+ of its
# own job postings (Sina's own example).
GOOGLE_DEEP_CRAWL_PAGES_PER_RESULT = 15


# How many freshly-learned sites share one crawl run. Small on purpose: each run asks for
# 4096MB of the account's 16384MB allowance, so several can queue without any of them being
# refused, and a batch that fails takes only its own sites down with it.
_PATTERN_CRAWL_BATCH_SIZE = 3

# The same, for the main deep crawl over every known job board's result pages. Larger,
# because these are pages the app already understands rather than sites it has just met.
_DEEP_CRAWL_BATCH_SIZE = 12


# How many unknown domains one search will try to learn. Whatever Google finds, RoleHound
# is expected to go in and read -- so this is a stop against a pathological run, not a
# ration. Each domain costs a handful of HTTP requests and at most one small Claude
# call, and the result is saved forever: the cost is paid once per site, ever.
_MAX_PATTERN_DISCOVERIES_PER_RUN = 40


