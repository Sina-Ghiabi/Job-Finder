"""Country / city reference tables and the lookups over them."""
from __future__ import annotations


COUNTRIES = [
    'Italy', 'Denmark', 'Finland', 'Norway', 'Sweden', 'Austria', 'Belgium', 'France', 'Germany',
    'Netherlands', 'Luxembourg', 'Switzerland', 'Portugal', 'Spain', 'United Kingdom',
    'United States', 'Canada', 'Australia',
]


# Searched by every enabled platform, same as COUNTRIES, but at city granularity
# instead of country -- see run_search. Shown in the wizard nested under their parent
# country (COUNTRY_CITIES below): checking the country searches the whole country;
# checking a city underneath it searches just that city. The two are independent
# checkboxes, not a parent/child propagation -- checking both is valid (redundant, not
# wrong) and just means both a country-wide and a city-specific search run.
# Milan and Turin are cities like any other here: Remote means Remote everywhere, and no city
# is exempt from the Work Location rule.
#
# They were missing, and nothing else made up for it: COUNTRY_JOB_SITES had no entry for
# Italy either, so a search of Italy ran one direct site task (arc.dev) and no site: query
# for a single Italian board. The country he can most easily work in was the least
# searched in the app.
CITIES = ['Amsterdam', 'Berlin', 'Vienna', 'Oslo', 'Copenhagen', 'Milan', 'Turin']


CITY_COUNTRY = {
    'Amsterdam': 'Netherlands',
    'Berlin': 'Germany',
    'Vienna': 'Austria',
    'Oslo': 'Norway',
    'Copenhagen': 'Denmark',
    'Milan': 'Italy',
    'Turin': 'Italy',
}


# Reverse of CITY_COUNTRY, grouped by country in COUNTRIES order -- countries not in
# here (most of them) simply have no cities to expand in the wizard.
COUNTRY_CITIES = {
    country: [city for city, c in CITY_COUNTRY.items() if c == country]
    for country in COUNTRIES
    if any(c == country for c in CITY_COUNTRY.values())
}


COUNTRY_ISO2 = {
    'Italy': 'it', 'Denmark': 'dk', 'Finland': 'fi', 'Norway': 'no', 'Sweden': 'se', 'Austria': 'at',
    'Belgium': 'be', 'France': 'fr', 'Germany': 'de', 'Netherlands': 'nl', 'Luxembourg': 'lu',
    'Switzerland': 'ch', 'Portugal': 'pt', 'Spain': 'es', 'United Kingdom': 'uk', 'United States': 'us',
    'Canada': 'ca', 'Australia': 'au',
}


# Best-known major local job boards per country, excluding LinkedIn/Indeed/Glassdoor
# (already excluded everywhere else above) -- curated from a round of web research per
# country, not independently domain-verified the way the glassdoor.ca leak was. A wrong
# or dead domain here just means that one `site:` clause returns nothing, harmless. Not
# every one of the 18 COUNTRIES has an entry; a country with none just skips straight to
# the open-web stage (see build_google_job_queries).
#
# Several entries below deliberately repeat across multiple countries, same reasoning as
# app.welcometothejungle.com (see its own note below): each is one real site whose
# actual coverage spans more than one country, so it's listed under every country it
# genuinely covers rather than forced into either a single country or
# GOOGLE_GLOBAL_EXTRA_SITES (which would run it even against countries it has no
# presence in):
# - europa.eu: hosts EURES, the EU's own official job-mobility portal -- covers every
#   EU/EEA country plus Switzerland (14 of our 18: all except United Kingdom, which left
#   EURES after Brexit, and United States/Canada/Australia, which were never EU/EEA).
#   Deliberately listed as the bare `europa.eu` domain, not `eures.europa.eu` -- real
#   research found EURES's own informational site lives at eures.europa.eu, but its
#   actual job vacancy search and detail pages are hosted on the separate `europa.eu`
#   domain (under /eures/portal/jv-se/**), so a `site:eures.europa.eu` clause would never
#   have matched a real job posting at all.
# - wearedevelopers.com: a large European developer-jobs platform, strongest in
#   Germany/Austria/Switzerland/UK specifically (per real research, not just guessed).
# - iamexpat.nl / iamexpat.de: same publisher, but genuinely two separate per-country
#   domains (Netherlands and Germany respectively), not one shared domain -- listed
#   individually under each country like any other single-country entry.
#
# app.welcometothejungle.com (formerly Otta) deliberately repeats across France,
# Germany, Netherlands, Spain, United Kingdom, United States, and Canada -- unlike every
# other entry here, it isn't one country's own board, but real investigation (its own
# official supported-locations list, cross-checked against real indexed job postings)
# confirmed it only has genuine listings for exactly these 7 countries, not the other 11
# or any of the 5 cities -- so it's listed under each of those 7 rather than treated as
# a GOOGLE_GLOBAL_EXTRA_SITES entry (which runs for every location, including places
# this site has no real presence).
COUNTRY_JOB_SITES = {
    # europa.eu (EURES) and arbetsformedlingen.se (Sweden) both removed from every
    # entry here -- Sina asked for this after a real cost audit found both already have
    # a free, direct JSON-API integration (_fetch_eures/_fetch_arbetsformedlingen_se,
    # see _run_direct_api_searches) that returns the SAME listings with the SAME (or
    # better -- both APIs include the full job description text) quality, at zero
    # Apify cost. Keeping them here too meant paying for a real Google known-sites
    # query + Deep-Crawl-eligible page fetches for results the free API already had,
    # just to have Filter's own dedup throw the paid-for duplicate away. Italy's and
    # Sweden's entries are gone entirely now that their only members were removed (both
    # still get a real Startup-sites stage from COUNTRY_STARTUP_SITES, unaffected).
    'Denmark': ['jobindex.dk', 'jobnet.dk', 'it-jobbank.dk'],
    # te-palvelut.fi removed -- its search backend (paikat.te-palvelut.fi) no longer
    # resolves via DNS at all (confirmed dead). Its real successor, tyomarkkinatori.fi,
    # is below with a confirmed working URL Sina found by hand.
    'Finland': ['duunitori.fi', 'jobly.fi', 'tyomarkkinatori.fi'],
    'Norway': ['finn.no', 'arbeidsplassen.nav.no', 'karrierestart.no'],
    'Austria': ['karriere.at', 'stepstone.at', 'wearedevelopers.com'],
    'Belgium': ['vdab.be', 'jobat.be', 'leforem.be', 'actiris.brussels'],
    'France': ['francetravail.fr', 'apec.fr', 'hellowork.com', 'cadremploi.fr', 'app.welcometothejungle.com'],
    'Germany': ['arbeitsagentur.de', 'stepstone.de', 'xing.com', 'app.welcometothejungle.com', 'wearedevelopers.com', 'iamexpat.de'],
    'Netherlands': ['werk.nl', 'nationalevacaturebank.nl', 'app.welcometothejungle.com', 'iamexpat.nl'],
    'Luxembourg': ['moovijob.com', 'adem.public.lu'],
    # jobs.ch and jobup.ch removed too, same reasoning as europa.eu/arbetsformedlingen.se
    # above -- both already have a free JobCloud API (_fetch_jobcloud). Unlike the
    # other removals, that free API's own description is thinner (title only, no full
    # JD -- see _fetch_jobcloud's own docstring), a real, accepted trade-off Sina
    # confirmed he's fine with. swissdevjobs.ch was NOT part of this removal (not
    # raised/agreed on) -- still searched via Google as before.
    'Switzerland': ['swissdevjobs.ch', 'wearedevelopers.com'],
    'Portugal': ['net-empregos.com', 'sapoemprego.pt', 'itjobs.pt'],
    'Spain': ['infojobs.net', 'empleate.gob.es', 'tecnoempleo.com', 'app.welcometothejungle.com'],
    'United Kingdom': ['reed.co.uk', 'totaljobs.com', 'cv-library.co.uk', 'cwjobs.co.uk', 'app.welcometothejungle.com', 'wearedevelopers.com'],
    'United States': ['dice.com', 'ziprecruiter.com', 'app.welcometothejungle.com', 'builtin.com'],
    'Canada': ['jobbank.gc.ca', 'eluta.ca', 'app.welcometothejungle.com'],
    'Australia': ['seek.com.au', 'jora.com', 'careerone.com.au'],
}


_WEAREDEVELOPERS_COUNTRY_SLUGS = {
    # Switzerland is deliberately absent: wearedevelopers.com has no Swiss page. Confirmed
    # by asking for every plausible spelling -- /jobs/l/switzerland, /ch and /schweiz all
    # answer 404, while germany, austria, united-kingdom and netherlands answer 200. The
    # entry was here anyway, so every Swiss search built a URL that could only fail, and
    # the health check reported it as a broken site on every run.
    'Germany': 'germany', 'Austria': 'austria', 'United Kingdom': 'united-kingdom',
}


_WEAREDEVELOPERS_CITY_SLUGS = {'Berlin': 'berlin', 'Vienna': 'vienna'}


# Local-language spellings for the 5 CITIES, so _mentions_city doesn't wrongly reject a
# genuinely correct job page just because its own text is in the local language (a real
# Copenhagen posting on a Danish site is far more likely to say "København" than the
# English "Copenhagen"; same idea for Vienna/"Wien").
_CITY_LOCAL_SPELLINGS = {
    'Vienna': ['Vienna', 'Wien'],
    'Copenhagen': ['Copenhagen', 'København', 'Kobenhavn', 'Koebenhavn'],
    # An Italian advert almost never writes "Milan" or "Turin" -- it writes Milano and
    # Torino. Without these, _mentions_city would reject every genuine Italian listing for
    # not naming the city it is actually in, which is the exact opposite of its purpose.
        'Milan': ['Milan', 'Milano'],
    'Turin': ['Turin', 'Torino'],
}


def _mentions_city(city: str, text: str) -> bool:
    text_lower = (text or '').lower()
    return any(spelling.lower() in text_lower for spelling in _CITY_LOCAL_SPELLINGS.get(city, [city]))


# Each entry: country domain code -> (COUNTRY_JOB_SITES country name, matching CITIES
# city or None). Sina supplies the actual key per domain via settings.json
# (jooble_{code}_api_key) -- a domain with no key configured is just skipped.
JOOBLE_API_COUNTRIES = {
    'de': ('Germany', 'Berlin'),
    'nl': ('Netherlands', 'Amsterdam'),
    'at': ('Austria', 'Vienna'),
    'no': ('Norway', 'Oslo'),
    'fr': ('France', None),
    'dk': ('Denmark', 'Copenhagen'),
    'se': ('Sweden', None),
    # Only one city can be named per Jooble domain, and Milan is the larger tech market of
    # the two -- Turin is still covered by the country-wide call this same entry makes.
    'it': ('Italy', 'Milan'),
    'ch': ('Switzerland', None),
    'fi': ('Finland', None),
    'be': ('Belgium', None),
    'es': ('Spain', None),
    'uk': ('United Kingdom', None),
    'au': ('Australia', None),
    'ca': ('Canada', None),
    'pt': ('Portugal', None),
}


_EURES_COUNTRIES = [
    'Italy', 'Denmark', 'Finland', 'Norway', 'Sweden', 'Austria', 'Belgium', 'France',
    'Germany', 'Netherlands', 'Luxembourg', 'Switzerland', 'Portugal', 'Spain',
]


# Small heuristic country lookup for arbeitnow's free-text `location` field (no ISO
# country code in the response) -- covers what real testing actually showed in the
# `visa_sponsorship=true` results. A location that matches none of these is left with
# country=None and dropped rather than guessed, since a wrong country here would put a
# real sponsorship-tagged job in front of the wrong search entirely.
_ARBEITNOW_LOCATION_COUNTRY_HINTS = {
    'united kingdom': 'United Kingdom', 'uk': 'United Kingdom', 'england': 'United Kingdom',
    'london': 'United Kingdom', 'edinburgh': 'United Kingdom', 'oxford': 'United Kingdom',
    'cambridge': 'United Kingdom', 'manchester': 'United Kingdom', 'bristol': 'United Kingdom',
    'germany': 'Germany', 'berlin': 'Germany', 'munich': 'Germany', 'frankfurt': 'Germany',
    'hamburg': 'Germany', 'cologne': 'Germany', 'bochum': 'Germany',
    'australia': 'Australia', 'sydney': 'Australia', 'melbourne': 'Australia',
    'netherlands': 'Netherlands', 'amsterdam': 'Netherlands',
    'austria': 'Austria', 'vienna': 'Austria',
    'switzerland': 'Switzerland', 'zurich': 'Switzerland', 'geneva': 'Switzerland',
    'france': 'France', 'paris': 'France',
    'spain': 'Spain', 'madrid': 'Spain', 'barcelona': 'Spain',
    'canada': 'Canada', 'toronto': 'Canada', 'vancouver': 'Canada',
    'united states': 'United States', 'usa': 'United States', 'new york': 'United States',
}


def _arbeitnow_location_to_country(location: str) -> str | None:
    location_lower = (location or '').lower()
    for hint, country in _ARBEITNOW_LOCATION_COUNTRY_HINTS.items():
        if hint in location_lower:
            return country
    return None
