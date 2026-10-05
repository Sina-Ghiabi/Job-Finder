"""Normalizing each platform's raw rows into the common listing shape."""
from __future__ import annotations

import re

from urllib.parse import urlencode

from .text import (dig, first_present, strip_html)
from .geo import (CITY_COUNTRY)


# LinkedIn's own "posted within" URL filter (f_TPR), used only for the remote-filtered
# URL search below -- None means no time filter is applied.
LINKEDIN_TPR_MAP = {
    'past24Hours': 'r86400',
    'pastWeek': 'r604800',
    'pastMonth': 'r2592000',
    'anyTime': None,
}


def normalize_linkedin(item):
    return {
        'title': item.get('title'),
        'company': item.get('companyName'),
        'location': item.get('location'),
        'posted_date': item.get('postedAt'),
        'url': item.get('link'),
        'description': item.get('descriptionText') or strip_html(item.get('descriptionHtml')),
        'employment_type': item.get('employmentType'),
        'seniority_level': item.get('seniorityLevel'),
    }


# What the new LinkedIn actor calls each posted-time window. Ours are the names the wizard has
# always used (text.LINKEDIN_DATE_OPTIONS); the actor wants day / week / month, and nothing at
# all for "any time". Measured, not assumed: day returned 5 rows every one of them 0 days old,
# week's oldest was 6 days, month's was 27.
LINKEDIN_DATE_TO_WINDOW = {
    'past24Hours': 'day',
    'pastWeek': 'week',
    'pastMonth': 'month',
    'anyTime': '',
}

# The workplace type exactly as LinkedIn labels it, spelled the one way this app uses it. The
# actor writes "On-site", and a hand-edited or older row could say "onsite" or "On site"; a
# rule that compared against the raw string would miss every spelling but one.
WORKPLACE_REMOTE, WORKPLACE_HYBRID, WORKPLACE_ONSITE = 'Remote', 'Hybrid', 'On-site'
_WORKPLACE_SPELLINGS = {
    'remote': WORKPLACE_REMOTE, 'fully remote': WORKPLACE_REMOTE,
    'hybrid': WORKPLACE_HYBRID,
    'on-site': WORKPLACE_ONSITE, 'onsite': WORKPLACE_ONSITE, 'on site': WORKPLACE_ONSITE,
    'on_site': WORKPLACE_ONSITE,
}


def clean_workplace(value) -> str:
    """'Remote', 'Hybrid' or 'On-site' -- or '' when the row carries no (known) tag.

    '' is a real answer and not a failure: every row from Google, Indeed, Glassdoor and the
    direct APIs has no tag, and so does every LinkedIn row banked before 4 October 2026. The
    Work Location rule reads '' as "no evidence either way" and falls back to the text.
    """
    if value is None or isinstance(value, bool):
        return ''
    text = str(value).strip().lower()
    return _WORKPLACE_SPELLINGS.get(text, '')


# What a posting's `job_insights` list can hold besides the workplace type. The actor returns
# it as "['Hybrid', 'Full-time']" (a string) on some rows and a real list on others.
_EMPLOYMENT_WORDS = {
    'full-time': 'Full-time', 'part-time': 'Part-time', 'contract': 'Contract',
    'temporary': 'Temporary', 'internship': 'Internship', 'volunteer': 'Volunteer',
    'other': 'Other',
}


def _employment_from_insights(value) -> str:
    if isinstance(value, str):
        pieces = re.findall(r"[A-Za-z][A-Za-z\- ]+", value)
    elif isinstance(value, (list, tuple)):
        pieces = [str(v) for v in value]
    else:
        return ''
    for piece in pieces:
        found = _EMPLOYMENT_WORDS.get(piece.strip().lower())
        if found:
            return found
    return ''


def normalize_linkedin_pro(item):
    """One row from apimaestro/linkedin-jobs-scraper-api, in the shape the rest of the app reads.

    `workplace_type` is the point of this actor: LinkedIn's own Hybrid / On-site / Remote tag,
    which no other source carries and which the Work Location rule treats as the most reliable
    thing it can be told. `seniority_level` is None on purpose -- this actor does not return it
    and an invented value would be worse than none; seniority_of falls back to the title.
    """
    posted = str(item.get('posted_at') or '')
    return {
        'title': item.get('job_title'),
        'company': item.get('company'),
        'location': item.get('location'),
        # 'YYYY-MM-DD HH:MM:SS' -> the date, which is what the old actor gave and what the
        # table and the date filter read.
        'posted_date': posted[:10] or None,
        'url': item.get('job_url'),
        'description': item.get('description'),
        'employment_type': _employment_from_insights(item.get('job_insights')) or None,
        'seniority_level': None,
        'workplace_type': clean_workplace(item.get('work_type')) or None,
    }


def build_linkedin_remote_search_url(keywords, location, date_option_value):
    """Builds a LinkedIn jobs-search URL with f_WT=2 (Remote only) baked in, so the
    actor's own AI-search filters out non-remote listings before they're even fetched."""
    params = {'keywords': keywords, 'location': location, 'f_WT': '2'}
    tpr = LINKEDIN_TPR_MAP.get(date_option_value)
    if tpr:
        params['f_TPR'] = tpr
    return 'https://www.linkedin.com/jobs/search/?' + urlencode(params)


def normalize_indeed(item):
    loc = first_present(
        item,
        'location.streetAddress',
        'location.city',
        'location.raw',
        default=', '.join(filter(None, [dig(item, 'location.city'), dig(item, 'location.countryName')])) or None,
    )
    return {
        'title': item.get('title'),
        'company': dig(item, 'employer.name'),
        'location': loc,
        'posted_date': item.get('datePublished') or item.get('dateOnIndeed'),
        'url': item.get('jobUrl') or item.get('url'),
        'description': dig(item, 'description.text') or strip_html(dig(item, 'description.html')),
    }


def normalize_glassdoor(item):
    title = first_present(item, 'title', 'jobTitle')
    company = first_present(item, 'companyName', 'employer.name', 'company')
    # Glassdoor returns `location` as an OBJECT -- {'countryId': 180, 'id': 2918317,
    # 'name': 'Oslo', 'type': 'C'} -- and reading the key itself put that whole structure
    # into the Location column, the Excel export and the text every rule reads. Measured on
    # a real Oslo run: all 38 Glassdoor rows carried it. The name inside it is the city, so
    # the dotted path is asked for first and the object itself is the last resort.
    location = first_present(item, 'location.name', 'location.raw', 'location.city', 'location')
    if isinstance(location, dict):
        location = (location.get('name') or location.get('city')
                    or location.get('raw') or None)
    posted = first_present(item, 'postedAt', 'datePosted', 'posted_date')
    url = first_present(item, 'link', 'url', 'jobUrl')
    desc = first_present(item, 'descriptionText', 'description', 'description.text')
    if isinstance(desc, str):
        desc = strip_html(desc)
    return {
        'title': title, 'company': company, 'location': location,
        'posted_date': posted, 'url': url, 'description': desc,
    }


# A page's <title> ends with the site's own name far more often than not, and Google and the
# crawler both take the title from there. Measured on the real Oslo run: of 1,018 listings,
# 224 ended in "| Wellfound", 170 in "| FINN.no" and 10 in "| arbeidsplassen.no". That name
# is not part of the job: it shows in the table, goes into the Excel, is read by the
# duplicate check, and reaches Claude on the Title line.
#
# Only the site's OWN name is removed, matched against the address the listing came from --
# never a general "strip everything after the last dash", which would eat "Data Engineer -
# Microsoft Fabric".
_TITLE_TAIL = re.compile(r'\s*[|–—·\-]\s*([^|–—\-]{2,40})\s*$')


def _site_names(url: str) -> set:
    """What this site might call itself at the end of a page title."""
    host = str(url or '').split('//')[-1].split('/')[0].split(':')[0].lower()
    if not host:
        return set()
    labels = [label for label in host.split('.') if label]
    if labels and labels[0] == 'www':
        labels = labels[1:]
    names = {'.'.join(labels)}
    if labels:
        names.add(labels[0])                                  # wellfound
        if len(labels) >= 2:
            names.add('.'.join(labels[-2:]))                  # nav.no
            names.add(labels[0] + '.' + labels[-1])            # arbeidsplassen.no
    return {name for name in names if len(name) >= 3}


# The word a board puts between the job and its own name -- "Data Engineer | Jobs |
# Wellfound". Removed only AFTER the site's name has been, so "Data Engineer - Jobs" from a
# site that never named itself is left exactly as the employer wrote it.
_GENERIC_TAILS = frozenset({'jobs', 'job', 'careers', 'career', 'vacancies', 'stillinger',
                            'stillingsannonse', 'jobb', 'ledigestillinger'})


_TITLE_HEAD = re.compile(r'^([^|–—]{2,40}?)\s*[|–—]\s*')


def strip_site_name_from_title(title, url) -> str:
    """The page title without the site's own name. Unchanged when it has none.

    Both ends: thehub.io writes "The Hub | Internship Data Engineer | SurplusMap", where the
    site's name leads and the employer's follows the job.
    """
    text = ' '.join(str(title or '').split())
    names = _site_names(url)
    if not text or not names:
        return text
    head = _TITLE_HEAD.match(text)
    if head and head.group(1).strip().lower().replace(' ', '').rstrip('.') in names:
        shorter = text[head.end():].strip()
        if len(shorter) >= 3:
            text = shorter
    stripped_site = False
    # At most two, for "Data Engineer | Jobs | Wellfound".
    for _round in range(2):
        found = _TITLE_TAIL.search(text)
        if not found:
            break
        tail = found.group(1).strip().lower().replace(' ', '').rstrip('.')
        if tail in names:
            pass
        elif stripped_site and tail in _GENERIC_TAILS:
            pass
        else:
            break
        shorter = text[:found.start()].strip()
        if len(shorter) < 3:          # the title was only the site's name -- leave it alone
            break
        text = shorter
        stripped_site = True
    return text


# A job board's own way of writing where a job is, inside the page title:
#     "Senior Data Scientist - Casablanca at Artefact • Casablanca"
#     "Data Scientist at Riskified • Lisbon"
# wellfound and a few others put the place after a bullet, and Google hands the title over
# with no location field at all.
#
# Every segment after the first bullet is read, not just the last one. Reading only the
# last was a real mistake, caught before it shipped by printing all 130 relabels: "Software
# Architect at openigloo • Berlin • Hyderabad" became India, and a job naming both New York
# and a Swiss city became Switzerland. Two countries is not certainty.
_TITLE_PLACES = re.compile(r'[•|]\s*([^•|]{2,40})')

# Said in the title, and meaning "no particular place".
_NO_PLACE = re.compile(r'\b(remote|anywhere|worldwide|global|hybrid|europe|emea|eu)\b', re.I)

# Cities outside the eighteen countries this app searches, which it therefore has no table
# for -- and which turn up anyway, because a job board indexed by Google lists the world.
# Only names with one obvious home: "Cambridge" and "Birmingham" are deliberately absent,
# and so is anywhere the app already knows.
_WORLD_CITIES = {
    'New York': 'United States', 'New York City': 'United States',
    'San Francisco': 'United States', 'Los Angeles': 'United States',
    'Seattle': 'United States', 'Boston': 'United States', 'Chicago': 'United States',
    'Austin': 'United States', 'Denver': 'United States', 'Atlanta': 'United States',
    'Toronto': 'Canada', 'Vancouver': 'Canada', 'Montreal': 'Canada',
    'Casablanca': 'Morocco', 'Rabat': 'Morocco', 'Cairo': 'Egypt',
    'Tel Aviv': 'Israel', 'Dubai': 'United Arab Emirates', 'Abu Dhabi': 'United Arab Emirates',
    'Singapore': 'Singapore', 'Hong Kong': 'Hong Kong', 'Tokyo': 'Japan',
    'Bangalore': 'India', 'Bengaluru': 'India', 'Mumbai': 'India', 'Hyderabad': 'India',
    'Pune': 'India', 'Delhi': 'India', 'Chennai': 'India',
    'Sydney': 'Australia', 'Melbourne': 'Australia', 'Auckland': 'New Zealand',
    'São Paulo': 'Brazil', 'Sao Paulo': 'Brazil', 'Buenos Aires': 'Argentina',
    'Mexico City': 'Mexico', 'Bogotá': 'Colombia', 'Santiago': 'Chile',
    'Johannesburg': 'South Africa', 'Cape Town': 'South Africa', 'Nairobi': 'Kenya',
    'Lagos': 'Nigeria', 'Istanbul': 'Turkey', 'Kyiv': 'Ukraine', 'Kiev': 'Ukraine',
    'Bucharest': 'Romania', 'Sofia': 'Bulgaria', 'Budapest': 'Hungary',
    'Athens': 'Greece', 'Zagreb': 'Croatia', 'Belgrade': 'Serbia',
    'Riga': 'Latvia', 'Vilnius': 'Lithuania', 'Tallinn': 'Estonia',
}


def country_from_listing_location(location, title, searched=None):
    """The country a listing itself names, when it is plainly not the one searched.

    Google results are stamped with the country whose query produced them, because Google
    returns no location field of its own. That is right nearly always and wrong when a
    German search surfaces a listing that says Casablanca: measured on the real Germany run,
    38 listings were filed under Germany while naming another city and no German one.

    Returns that other country, or None to leave the stamp alone. Deliberately silent
    unless certain, because the country is read by more than one rule -- it picks the
    language vocabulary too -- and a wrong label is better than an empty one:

      - only a place this app already knows, from CITY_COUNTRY or the major-city table
      - never when the text also names the searched country or one of its cities
      - never when the place is "Remote", "Europe" or another non-place
      - never when two different countries are named: that is not certainty, it is a guess

    Relabels only. Nothing here removes a listing; what to do with a foreign one is the
    Not Remote place rule's decision, and Claude's.
    """
    from .search.queries import _CITY_COUNTRY_FALLBACK

    text = str(location or '').strip()
    if not text:
        found = _TITLE_PLACES.findall(' '.join(str(title or '').split()))
        text = ' | '.join(part.strip() for part in found)
    if not text or _NO_PLACE.search(text):
        return None

    known = dict(_WORLD_CITIES)
    known.update(_CITY_COUNTRY_FALLBACK)
    known.update(CITY_COUNTRY)
    countries = set()
    for place, country in known.items():
        if re.search(r'\b%s\b' % re.escape(place), text, re.I):
            countries.add(country)
    # The searched country said by name rather than by one of its cities.
    if searched and re.search(r'\b%s\b' % re.escape(str(searched)), text, re.I):
        return None
    if len(countries) != 1:
        return None
    country = countries.pop()
    return None if searched and country == searched else country


def normalize_google_search_result(item: dict, loc_type: str | None, loc_value: str | None) -> dict:
    """`item` is one entry of a page's `organicResults` from the Google Search actor.
    Unlike the three dedicated job actors, Google doesn't return structured job fields
    (company, exact posted date) -- location/country are filled in from whichever
    city/country the originating query was actually built for (since we embedded it in
    the query ourselves; see _location_from_search_term), and description prefers the
    full scraped page text (the `websiteContentScraper` add-on's `websiteContent.text`)
    over Google's own short result snippet, falling back to the snippet if that page
    couldn't be scraped."""
    website_content = item.get('websiteContent') or {}
    description = website_content.get('text') or item.get('description') or ''
    if loc_type == 'city':
        location, country = loc_value, CITY_COUNTRY.get(loc_value or '')
    elif loc_type == 'country':
        location, country = None, loc_value
    else:
        location, country = None, None
    title = strip_site_name_from_title(item.get('title'), item.get('url'))
    # ...unless the listing itself plainly names somewhere else. See
    # country_from_listing_location for why this stays quiet unless it is certain.
    elsewhere = country_from_listing_location(location, title, searched=country)
    if elsewhere:
        country = elsewhere
    return {
        'title': title,
        'company': None,
        'location': location,
        'country': country,
        'posted_date': None,
        'url': item.get('url'),
        'description': description,
    }


# =========================================================================================
# MARKDOWN MIRRORS
# =========================================================================================
#
# wearedevelopers.com serves every page twice: once as HTML and once as Markdown at the same
# address with ".md" on the end -- its own words, "Every page supports .md or Accept:
# text/markdown". Google indexes both, and the crawler follows the link the HTML page makes
# to its own mirror. So one vacancy arrives as two rows:
#
#   /jobs/ext/2836673-devops-engineer        title "DevOps Engineer"
#   /jobs/ext/2836673-devops-engineer.md     title None
#
# Measured across every corpus on disk: 95 such rows, every one from wearedevelopers.com,
# not one with a title. The addresses differ, so duplicate removal never matched them. The
# title is empty, so the field filter kept them -- a missing title is never evidence -- and
# one reached Claude in the Austrian DevOps run and was KEPT, listed as "None".
#
# This does not delete anything. Sina's rule is that a raw search shows every listing as
# fetched and cleanup happens at Filter, so the row is CORRECTED instead: its address is put
# back to the one the HTML copy has, and its title and company are read out of the Markdown
# itself. Filter's own duplicate check then sees two rows at one address and keeps one.
#
# The Markdown copy is worth correcting rather than just discarding, because it is the
# cleaner of the two. The HTML copy's text opens "WeAreDevelopers WeAreDevelopers Sign in
# Search videos, moments, articles"; the Markdown copy opens "# Data Scientist - Company:
# Sportradar AG - Location: Wien, Austria (Remote available)".
_MARKDOWN_MIRROR_URL = re.compile(r'^(https?://[^?#]+?)\.md(?=[?#]|$)', re.I)
# The page text arrives in two shapes, and both are real. Most is whitespace-collapsed, so
# the Markdown's line breaks are gone and a heading reads "--- # Data Scientist - Company:
# Sportradar AG - Location: ...". Some keeps its line breaks and has no heading marker at
# all: "Agent guide: /agents.md. [blank line] Platform Engineer [blank line] Company: RED".
# The first version of this read only the first shape and recovered 59 titles of 79.
#
# So the preamble is cut away first, whatever it ends with, and the title is whatever comes
# before the first field label.
_MIRROR_PREAMBLE = re.compile(r'^.*?agents\.md\.\s*(?:---\s*)?(?:#\s+)?', re.S | re.I)
_MIRROR_TITLE = re.compile(r'^(.+?)\s*(?:-\s+)?(?:Company|Location|Contract):', re.S)
_MIRROR_COMPANY = re.compile(r'Company:\s+(.+?)\s*(?:-\s+|\n)\s*(?:Location|Contract|Skills):',
                             re.S)
# A mirror of a posting that is gone. Measured: 16 of the 95 mirror rows read "# Job Not
# Found This job listing has been removed or is no longer available". Giving those a title
# would make a vanished vacancy look like a live one, so they are left untitled and the
# dead-posting check downstream decides what they are.
_MIRROR_GONE = re.compile(r'^\s*Job Not Found\b', re.I)


def unmirror_markdown_row(row: dict) -> dict:
    """Put a Markdown-mirror row back on its real address, with its real title. In place.

    Only ever touches a row whose address ends in .md -- nothing else is changed -- and
    never overwrites a title or company the row already has.
    """
    url = str(row.get('url') or '')
    match = _MARKDOWN_MIRROR_URL.match(url)
    if not match:
        return row
    row['url'] = match.group(1) + url[match.end():]
    text = str(row.get('description') or '')
    body = _MIRROR_PREAMBLE.sub('', text, count=1)
    if _MIRROR_GONE.match(body):
        return row
    title = str(row.get('title') or '').strip()
    if not title or title == 'None':
        found = _MIRROR_TITLE.match(body)
        # A title is one line. Anything longer means the label was not where it should be
        # and the match ran on into the advert -- better no title than a paragraph.
        if found and len(found.group(1).strip()) <= 140 and '\n' not in found.group(1).strip():
            row['title'] = found.group(1).strip()
    if not str(row.get('company') or '').strip():
        found = _MIRROR_COMPANY.search(body)
        if found and len(found.group(1).strip()) <= 100:
            row['company'] = found.group(1).strip()
    return row
