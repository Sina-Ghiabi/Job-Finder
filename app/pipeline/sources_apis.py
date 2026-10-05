"""Direct API fetchers -- one per job board with a usable public API."""
from __future__ import annotations

from datetime import datetime, timezone
import requests
from apify_client import ApifyClient

from .text import (dig)
from .geo import (COUNTRY_ISO2)
from .rules import (_REMOTEOK_API_URL)


# ---------------------------------------------------------------------------
# Direct JSON API integrations -- for the handful of sites whose real, confirmed
# location mechanism is a REST API returning JSON, not an HTML page the
# website-content-crawler could extract <a href> links from (see the long comment
# above DIRECT_SEARCH_URL_BUILDERS for the full research). These bypass Apify
# entirely -- a plain `requests` HTTP call, parsed directly -- which is both cheaper
# and gives richer, already-structured data than scraping ever would.
# ---------------------------------------------------------------------------

# Sweden's official open JobSearch API (Arbetsförmedlingen's own open-data initiative,
# jobtechdev.se) -- genuinely public, no registration or API key needed.
_ARBETSFORMEDLINGEN_API_URL = 'https://jobsearch.api.jobtechdev.se/search'


# Germany's real Arbeitsagentur job-search REST API. `jobboerse-jobsuche` is not a
# secret -- it's the public client key the official Arbeitsagentur app itself uses,
# long since reverse-engineered and documented in the open-source community wrapper
# project (bundesAPI/jobsuche-api) that a real live test against this exact endpoint
# confirmed still works.
_ARBEITSAGENTUR_API_URL = 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs'


_ARBEITSAGENTUR_API_KEY = 'jobboerse-jobsuche'


# Every fetcher below used to make exactly one request and take one page. That is
# invisible from the inside -- the list comes back full, nothing errors -- and it was
# measured against what each API reports it actually has:
#
#     arbeitsagentur.de       370 jobs, we took 100      (73% never seen)
#     europa.eu (EURES)    20,647 jobs, we took  50      (99.8% never seen)
#     jobs.ch                 163 jobs, we took  20      (88% never seen)
#     arbetsformedlingen.se    29 jobs, we took  29      (complete, by luck of size)
#
# These APIs are free, so the only real cost of reading further is downstream: every extra
# row is translated and screened by Claude in the Filter, which is not free. Hence a cap
# rather than "read everything" -- generous enough to be complete for a normal query, low
# enough that one pathological result set cannot run up a bill.
#
# The page parameter for each source was PROVEN, not guessed: page one and page two were
# fetched and compared. That mattered -- jobs.ch accepts `offset` and silently ignores it,
# so a guessed loop there would have returned page one forever while the counts looked
# right.
DIRECT_API_MAX_PAGES = 20
DIRECT_API_MAX_ROWS = 1000


def _paginate_rows(fetch_page, max_rows: int = DIRECT_API_MAX_ROWS,
                   max_pages: int = DIRECT_API_MAX_PAGES) -> list[dict]:
    """Call fetch_page(page_number) from page 1 until the source runs out.

    Stops on the first empty page, on a page that returns nothing new (an API that ignores
    its own page parameter answers page one forever -- that must end the loop, not spin),
    or when either cap is reached.
    """
    rows: list[dict] = []
    seen: set = set()
    for page in range(1, max_pages + 1):
        try:
            page_rows = fetch_page(page) or []
        except Exception:
            # One bad page keeps whatever the earlier ones returned rather than losing the
            # source entirely -- the same principle every other stage here follows.
            #
            # But a failure on page ONE is not one bad page: it is the source failing, and
            # swallowing it turns a dead source into "no results today". EURES answered 990
            # rows in the morning and HTTP 403 in the afternoon, and the app reported neither
            # -- just an empty list, identical to a search that genuinely matched nothing.
            # That is O-7's fault in its worst direction: not a working source called broken,
            # but a broken source called quiet.
            #
            # Nothing has been collected yet, so there is nothing to protect. The caller and
            # the Log get the real error.
            if not rows:
                raise
            break
        if not page_rows:
            break
        fresh = 0
        for row in page_rows:
            key = row.get('url') or (row.get('title'), row.get('company'))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            fresh += 1
            if len(rows) >= max_rows:
                return rows
        if fresh == 0:
            break
    return rows


def _fetch_arbetsformedlingen_se(role_term: str) -> list[dict]:
    """Sweden, country-wide only (no defined Swedish city in CITIES). Returns rows
    already close to full richness -- this API includes the full job description text,
    not just a summary."""
    def page_rows(page: int) -> list[dict]:
        # Proven by probe: this API paginates on "offset", not "page".
        resp = requests.get(_ARBETSFORMEDLINGEN_API_URL,
                            params={'q': role_term, 'limit': 100,
                                    'offset': (page - 1) * 100},
                            timeout=30)
        resp.raise_for_status()
        return _arbetsformedlingen_rows(resp.json().get('hits') or [])

    return _paginate_rows(page_rows)


def _arbetsformedlingen_rows(hits: list) -> list[dict]:
    rows = []
    for hit in hits:
        employer = hit.get('employer') or {}
        address = hit.get('workplace_address') or {}
        description = dig(hit, 'description.text') or ''
        rows.append({
            'title': hit.get('headline'),
            'company': employer.get('name'),
            'location': address.get('municipality'),
            'country': 'Sweden',
            'posted_date': hit.get('publication_date'),
            'url': hit.get('webpage_url'),
            'description': description,
            'platform': 'arbetsformedlingen.se',
            'google_stage': 'known',
        })
    return rows


def _fetch_arbeitsagentur_de(role_term: str, city: str | None) -> list[dict]:
    """Germany, country-wide or Berlin-scoped (the only German city in CITIES). This
    API's search results don't include the full job description text (only
    structured summary fields) -- rows here have a thinner `description` than most
    other sources, synthesized from the available fields, which is still enough for
    the keyword/Claude filters downstream but won't read like a full JD."""
    def page_rows(page: int) -> list[dict]:
        # Proven by probe: "page" works; "seite" and "offset" are accepted and ignored.
        params = {'was': role_term, 'size': 100, 'page': page}
        if city:
            params['wo'] = city
            params['umkreis'] = 25
        resp = requests.get(
            _ARBEITSAGENTUR_API_URL, params=params,
            headers={'X-API-Key': _ARBEITSAGENTUR_API_KEY}, timeout=30,
        )
        resp.raise_for_status()
        return _arbeitsagentur_rows(resp.json().get('ergebnisliste') or [])

    return _paginate_rows(page_rows)


def _arbeitsagentur_rows(items: list) -> list[dict]:
    rows = []
    for item in items:
        ort = dig(item, 'stellenlokationen.0.adresse.ort')
        referenznummer = item.get('referenznummer')
        if not referenznummer:
            continue
        title = item.get('stellenangebotsTitel') or item.get('hauptberuf') or ''
        company = item.get('firma') or ''
        description = f"{title} at {company}" + (f" in {ort}" if ort else '')
        rows.append({
            'title': title,
            'company': company,
            'location': ort,
            'country': 'Germany',
            'posted_date': item.get('datumErsteVeroeffentlichung'),
            'url': f'https://www.arbeitsagentur.de/jobsuche/jobdetail/{referenznummer}',
            'description': description,
            'platform': 'arbeitsagentur.de',
            'google_stage': 'known',
            # This API returns no real JD text, so the description above is
            # synthesized and can never contain a remote keyword -- see
            # passes_work_location_rule's thin_description branch.
            'thin_description': True,
        })
    return rows


def _jooble_usage_path():
    from app import storage
    return storage.DATA_DIR / 'jooble_usage.json'


def _read_jooble_usage() -> dict:
    path = _jooble_usage_path()
    if not path.exists():
        return {}
    try:
        import json
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _record_jooble_usage(domain_key: str) -> int:
    """Increments and persists the used-request count for one Jooble domain (e.g. 'de'),
    returning the new total used. Best-effort -- a failure to write the counter file
    should never block the actual search."""
    import json
    usage = _read_jooble_usage()
    used = usage.get(domain_key, 0) + 1
    usage[domain_key] = used
    try:
        path = _jooble_usage_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(usage, indent=2), encoding='utf-8')
    except Exception:
        pass
    return used


def _fetch_jooble(domain_code: str, country: str, role_term: str, api_key: str,
                   location: str | None = None, on_request_sent=None) -> list[dict]:
    """Any Jooble country domain the user has his own real API key for (see
    JOOBLE_API_COUNTRIES). Confirmed real response fields (checked against a live
    de.jooble.org call): title, location, snippet (a truncated description, not the
    full JD), salary, source (the original site Jooble aggregated it from), type, link
    (a real {domain}.jooble.org/jdp/... detail page), company, updated, id."""
    body = {'keywords': role_term}
    if location:
        body['location'] = location
    resp = requests.post(
        f'https://{domain_code}.jooble.org/api/{api_key}', json=body,
        headers={'Content-Type': 'application/json'}, timeout=30,
    )
    # Fired the moment the request has demonstrably REACHED Jooble (any HTTP status),
    # before raise_for_status/parsing can throw. Real bug fixed here: the caller used to
    # record usage only after this whole function returned successfully, so a 5xx, a
    # rate-limit response or a malformed body -- all of which Jooble has already counted
    # against the key -- left the local tally one short, permanently. Against a hard,
    # non-renewable 500-request lifetime cap, drifting OPTIMISTIC is the dangerous
    # direction: the app keeps believing it has budget after Jooble has stopped serving.
    if on_request_sent:
        on_request_sent()
    resp.raise_for_status()
    jobs = resp.json().get('jobs') or []
    rows = []
    for job in jobs:
        rows.append({
            'title': job.get('title'),
            'company': job.get('company'),
            'location': job.get('location'),
            'country': country,
            'posted_date': job.get('updated'),
            'url': job.get('link'),
            'description': job.get('snippet') or job.get('title') or '',
            'platform': f'{domain_code}.jooble.org',
            'google_stage': 'known',
            # A truncated search snippet, not a real JD -- see passes_work_location_rule.
            'thin_description': True,
        })
    return rows


# The user's own real Reed.co.uk Jobseeker API key, requested from reed.co.uk/developers/
# jobseeker and confirmed working with a real call: real "Data Scientist" postings in
# London etc., each with the *full* job description text (richer than Jooble's
# snippet-only response) -- title, employer, location, salary range, dates,
# description, and a real reed.co.uk/jobs/... URL, all present. UK-only (reed.co.uk has
# no other country); United Kingdom has no defined city in CITIES, so country-wide only.
_REED_API_URL = 'https://www.reed.co.uk/api/1.0/search'


def _fetch_reed_uk(role_term: str, api_key: str) -> list[dict]:
    """Reed's auth convention: HTTP Basic Auth with the API key as the username and an
    empty password -- confirmed via a real call, not a guess."""
    def page_rows(page: int) -> list[dict]:
        # UNVERIFIED, unlike the other four: no Reed key is configured here, so page one
        # and page two could not be compared the way they were for the others. These are
        # Reed's documented parameters, and the guard in _paginate_rows makes a wrong
        # guess harmless -- a page that returns nothing new ends the loop rather than
        # repeating page one forever. Worth re-probing the day a key is added.
        resp = requests.get(_REED_API_URL,
                            params={'keywords': role_term, 'resultsToTake': 100,
                                    'resultsToSkip': (page - 1) * 100},
                            auth=(api_key, ''), timeout=30)
        resp.raise_for_status()
        return _reed_rows(resp.json().get('results') or [])

    return _paginate_rows(page_rows)


def _reed_rows(results: list) -> list[dict]:
    rows = []
    for job in results:
        job_id = job.get('jobId')
        if not job_id:
            continue
        rows.append({
            'title': job.get('jobTitle'),
            'company': job.get('employerName'),
            'location': job.get('locationName'),
            'country': 'United Kingdom',
            'posted_date': job.get('date'),
            'url': job.get('jobUrl') or f'https://www.reed.co.uk/jobs/{job_id}',
            'description': job.get('jobDescription') or job.get('jobTitle') or '',
            'platform': 'reed.co.uk',
            'google_stage': 'known',
        })
    return rows


# EURES (europa.eu) has a real, fully public REST API -- no key, no signup, no login at
# all -- confirmed with a real call: {"numberRecords": N, "jvs": [{"title",
# "description" (full text), "id", "creationDate" (epoch millis), "locationMap"
# ({"DE": [...]}-style, keyed by ISO2), "employer": {"name", ...}, ...]}. Covers all 14
# EU/EEA+Switzerland countries this app already lists europa.eu for
# (_EURES_COUNTRIES), and its job-detail URL (europa.eu/eures/portal/jv-se/jv-details/
# {id}) matches the already-confirmed GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS entry exactly.
# One call covers every selected EURES country at once (locationCodes takes a list) --
# each row's real country is read back from its own locationMap key rather than assumed,
# since a single call can mix results from several countries together.
_EURES_API_URL = 'https://europa.eu/eures/api/jv-searchengine/public/jv-search/search'


def _fetch_eures(role_term: str, iso2_codes: list[str]) -> list[dict]:
    iso2_to_country = {v: k for k, v in COUNTRY_ISO2.items()}
    def page_rows(page: int) -> list[dict]:
        # Proven by probe: "page" works -- page two returns a completely different set.
        # This is the source that was losing the most by far: 20,647 available, 50 read.
        # BEST_MATCH, not MOST_RECENT. This was the whole problem with reading EURES
        # deeply, and it is a sort order rather than a filter. Measured on 300 real rows:
        # sorted by date, relevance collapses with depth -- 46% role-related on page one,
        # 6% by page fifteen, where it is returning nursing vacancies for a Data Scientist
        # query. Sorted by best match it holds 98-100% all the way to page twenty.
        #
        # A keyword filter was tried first and measured against the same 300 rows: a
        # query word in the title kept 22 and threw away 107 real jobs (Software Developer
        # C++, Fachinformatiker, Unreal Engine Entwickler); title-or-description lost 66
        # and still admitted 58 pieces of noise. Same answer as the role-word rule earlier
        # in this project -- filtering on words loses real listings. Sorting does not.
        body = {
            'resultsPerPage': 50, 'page': page, 'sortSearch': 'BEST_MATCH',  # 100 returns 400 -- 50 is the real max
            'keywords': [{'keyword': role_term, 'specificSearchCode': 'EVERYWHERE'}],
            'publicationPeriod': None, 'occupationUris': [], 'skillUris': [],
            'requiredExperienceCodes': [], 'positionScheduleCodes': [], 'sectorCodes': [],
            'educationAndQualificationLevelCodes': [], 'positionOfferingCodes': [],
            'locationCodes': iso2_codes, 'euresFlagCodes': [], 'otherBenefitsCodes': [],
            'requiredLanguages': [], 'minNumberPost': None, 'sessionId': 'jobdesk-search',
            'requestLanguage': 'en',
        }
        resp = requests.post(_EURES_API_URL, json=body,
                             headers={'Content-Type': 'application/json'}, timeout=30)
        resp.raise_for_status()
        return _eures_rows(resp.json().get('jvs') or [], iso2_to_country)

    return _paginate_rows(page_rows)


def _eures_rows(jvs: list, iso2_to_country: dict) -> list[dict]:
    rows = []
    for jv in jvs:
        job_id = jv.get('id')
        if not job_id:
            continue
        loc_map = jv.get('locationMap') or {}
        country_code = next(iter(loc_map), '')
        country = iso2_to_country.get(country_code.lower())
        if not country:
            continue
        employer = jv.get('employer') or {}
        creation_ms = jv.get('creationDate')
        posted_date = (
            datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc).isoformat()
            if creation_ms else None
        )
        rows.append({
            'title': jv.get('title'),
            'company': employer.get('name'),
            'location': None,
            'country': country,
            'posted_date': posted_date,
            'url': f'https://europa.eu/eures/portal/jv-se/jv-details/{job_id}',
            'description': jv.get('description') or jv.get('title') or '',
            'platform': 'europa.eu (EURES)',
            'google_stage': 'known',
        })
    return rows


# The user's own real France Travail (formerly Pôle emploi) API credentials, requested from
# francetravail.io/data/api/offres-emploi -- OAuth2 client_credentials, confirmed
# working with a real call only after the user additionally *subscribed* his application to
# the "Offres d'emploi v2" product in the francetravail.io catalog (creating the
# application and getting client_id/secret wasn't enough on its own -- the token
# endpoint returned "invalid_scope" until that separate subscription step was done).
# Response includes the full French-language job description, real location
# (lieuTravail.libelle), company (entreprise.nom), and a real
# candidat.francetravail.fr/offres/recherche/detail/{id} URL matching the
# already-confirmed GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS entry for francetravail.fr.
_FRANCETRAVAIL_TOKEN_URL = 'https://entreprise.francetravail.fr/connexion/oauth2/access_token'


_FRANCETRAVAIL_API_URL = 'https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search'


_FRANCETRAVAIL_SCOPE = 'api_offresdemploiv2 o2dsoffre'


def _fetch_francetravail(role_term: str, client_id: str, client_secret: str) -> list[dict]:
    token_resp = requests.post(
        _FRANCETRAVAIL_TOKEN_URL, params={'realm': '/partenaire'},
        data={
            'grant_type': 'client_credentials', 'client_id': client_id,
            'client_secret': client_secret, 'scope': _FRANCETRAVAIL_SCOPE,
        },
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=30,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()['access_token']

    resp = requests.get(
        _FRANCETRAVAIL_API_URL, params={'motsCles': role_term},
        headers={'Authorization': f'Bearer {access_token}'}, timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get('resultats') or []
    rows = []
    for job in results:
        job_id = job.get('id')
        if not job_id:
            continue
        lieu = job.get('lieuTravail') or {}
        entreprise = job.get('entreprise') or {}
        origine = job.get('origineOffre') or {}
        rows.append({
            'title': job.get('intitule'),
            'company': entreprise.get('nom'),
            'location': lieu.get('libelle'),
            'country': 'France',
            'posted_date': job.get('dateCreation'),
            'url': origine.get('urlOrigine') or f'https://candidat.francetravail.fr/offres/recherche/detail/{job_id}',
            'description': job.get('description') or job.get('intitule') or '',
            'platform': 'francetravail.fr',
            'google_stage': 'known',
        })
    return rows


# remotive.com's public JSON API needs no key or signup at all -- confirmed via a real
# call: {"job-count": N, "jobs": [{"id", "url", "title", "company_name", "category",
# "tags", "job_type", "publication_date", "candidate_required_location", "salary",
# "description"}, ...]}. Global (like GOOGLE_GLOBAL_EXTRA_SITES, not tied to one
# country), so it runs on every search where the app can reach it, independent of which
# countries/cities are selected. Documented rate limit: max ~2 requests/minute, and
# Remotive's own guidance suggests capping real-world use to a handful of calls a day --
# fine here since it's called once per search, not per country/city.
_REMOTIVE_API_URL = 'https://remotive.com/api/remote-jobs'


def _fetch_remotive(role_term: str) -> list[dict]:
    resp = requests.get(_REMOTIVE_API_URL, params={'search': role_term}, timeout=30)
    resp.raise_for_status()
    jobs = resp.json().get('jobs') or []
    rows = []
    for job in jobs:
        rows.append({
            'title': job.get('title'),
            'company': job.get('company_name'),
            'location': job.get('candidate_required_location'),
            # Remote-only listings, no single fixed country -- same 'Global' convention
            # as MANUAL_ASSIST_GLOBAL_SITES's work.turing.com/work.mercor.com rows.
            'country': job.get('candidate_required_location') or 'Global',
            'posted_date': job.get('publication_date'),
            'url': job.get('url'),
            'description': job.get('description') or job.get('title') or '',
            'platform': 'remotive.com',
            'google_stage': 'global',
        })
    return rows


# remoteok.com has no search endpoint: one call returns its entire board -- 623KB, every
# listing, and the filtering happens here. That is why it is slow, and 30 seconds was never
# enough for it. Measured five times in a row on a healthy connection:
#
#     34.7s  34.0s  38.0s  43.5s   all HTTP 200, all 623,084 bytes
#     0.3s   HTTP 502                 it also serves the occasional bad gateway
#
# So the old ceiling did not make the source fast, it made it invisible: every real search
# dropped remoteok silently, and the live suite failed on it at random. 75 seconds clears the
# slowest measured call with room, and the 502 is a fast failure that no timeout can help.
_REMOTEOK_TIMEOUT_SECONDS = 75


def _fetch_remoteok(role_term: str) -> list[dict]:
    resp = requests.get(_REMOTEOK_API_URL, headers={'User-Agent': 'Mozilla/5.0'},
                        timeout=_REMOTEOK_TIMEOUT_SECONDS)
    resp.raise_for_status()
    items = resp.json() or []
    term_lower = role_term.lower()
    rows = []
    for job in items:
        if not isinstance(job, dict) or not job.get('id'):
            continue  # first item is a legal-notice object, not a real job
        haystack = f"{job.get('position', '')} {job.get('description', '')} {' '.join(job.get('tags') or [])}".lower()
        if term_lower not in haystack:
            continue
        rows.append({
            'title': job.get('position'),
            'company': job.get('company'),
            'location': job.get('location'),
            'country': job.get('location') or 'Global',
            'posted_date': job.get('date'),
            'url': job.get('url'),
            'description': job.get('description') or job.get('position') or '',
            'platform': 'remoteok.com',
            'google_stage': 'global',
        })
    return rows


# swissdevjobs.ch has a real, working (if undocumented) no-key read API --
# /api/jobsLight -- confirmed via a real call: 170 active postings with rich structured
# fields (salary range, exact city, tech stack). No keyword search parameter either, so
# filtered locally, same as remoteok.com. This bypasses a real, confirmed problem with
# the direct-search crawl path for this domain: swissdevjobs.ch's guessed country-wide
# search URL returns a genuine 403 (see DIRECT_SEARCH_URL_BUILDERS), so this API is the
# only way this domain gets real country-wide (not just per-city) coverage at all.
_SWISSDEVJOBS_API_URL = 'https://swissdevjobs.ch/api/jobsLight'


def _fetch_swissdevjobs(role_term: str) -> list[dict]:
    """swissdevjobs.ch -- CONFIRMED DEAD as of this writing.

    Its API endpoint still answers HTTP 200, but with an HTML sign-up page: the whole site
    now redirects to devitjobs.jobcopilot.com/signup?utm_source=sdj_old, so it was
    acquired or shut down and folded into JobCopilot. Left in place rather than deleted
    because a source coming back is not unheard of, and one cheap request per search is a
    small price for finding out -- but it now fails with a sentence that says what
    happened, instead of a raw JSONDecodeError that reads like a bug in RoleHound.
    """
    resp = requests.get(_SWISSDEVJOBS_API_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    resp.raise_for_status()
    content_type = (resp.headers.get('content-type') or '').lower()
    if 'json' not in content_type:
        raise RuntimeError(
            'swissdevjobs.ch no longer serves its jobs API -- it now returns an HTML page '
            'and redirects to jobcopilot.com, so the site appears to have shut down or '
            'been acquired. Nothing to fix on this end.')
    items = resp.json() or []
    term_lower = role_term.lower()
    rows = []
    for job in items:
        job_url = job.get('jobUrl')
        if not job_url:
            continue
        haystack = f"{job.get('name', '')} {job.get('techCategory', '')} {job.get('metaCategory', '')} {' '.join(job.get('technologies') or [])}".lower()
        if term_lower not in haystack:
            continue
        rows.append({
            'title': job.get('name'),
            'company': job.get('company'),
            'location': job.get('actualCity') or job.get('cityCategory'),
            'country': 'Switzerland',
            'posted_date': job.get('activeFrom'),
            'url': f'https://swissdevjobs.ch/jobs/{job_url}',
            'description': job.get('name') or '',
            'platform': 'swissdevjobs.ch',
            'google_stage': 'known',
            # jobsLight returns the role name only, no JD body -- see passes_work_location_rule.
            'thin_description': True,
        })
    return rows


# jobs.ch and jobup.ch (the JobCloud platform, same backend for both) also have a real,
# working (undocumented) search API with actual server-side keyword filtering --
# job-search-api.<domain>/search?query=... -- confirmed via real calls for both. Their
# list results don't include the full description (only title/company/place/dates), so
# rows here are thinner than most, same trade-off as arbeitsagentur.de -- still enough
# for downstream keyword/Claude filters.
def _fetch_jobcloud(domain: str, role_term: str) -> list[dict]:
    def page_rows(page: int) -> list[dict]:
        # Proven by probe: "page" works. "offset" and "from" are ACCEPTED AND IGNORED --
        # both return page one every time, so guessing either would have produced a loop
        # that looked like it was paginating and was not.
        resp = requests.get(
            f'https://job-search-api.{domain}/search',
            params={'query': role_term, 'page': page},
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=30,
        )
        resp.raise_for_status()
        return _jobcloud_rows(domain, resp.json().get('documents') or [])

    return _paginate_rows(page_rows)


def _jobcloud_rows(domain: str, documents: list) -> list[dict]:
    detail_path = 'en/vacancies/detail' if domain == 'jobs.ch' else 'en/jobs/detail'
    rows = []
    for job in documents:
        job_id = job.get('id')
        if not job_id:
            continue
        company = job.get('company') or {}
        rows.append({
            'title': job.get('title'),
            'company': company.get('name'),
            'location': job.get('place'),
            'country': 'Switzerland',
            'posted_date': job.get('publicationDate'),
            'url': f'https://www.{domain}/{detail_path}/{job_id}/',
            'description': job.get('title') or '',
            'platform': domain,
            'google_stage': 'known',
            # The JobCloud API carries the title only, no JD -- see passes_work_location_rule.
            'thin_description': True,
        })
    return rows


# ---------------------------------------------------------------------------
# werk.nl -- the Netherlands' national board, reached through an Apify actor.
#
# Every other country with a real national source has it wired in directly:
# arbeitsagentur.de for Germany, arbetsformedlingen.se for Sweden. The Netherlands had
# nothing. Its only Netherlands-specific source was nl.jooble.org, which needs a key
# The user has not configured, so a Dutch search ran on EURES and three global boards and no
# national board at all.
#
# werk.nl is the UWV's own board -- Dutch employers are legally required to report
# vacancies to it -- and carries 250,000+ live listings, which makes it the single
# largest Dutch source there is. It has no public API: the search page renders in
# JavaScript (a real fetch through the ladder returned 17 links, one of them a job), and
# a hunt through the rendered page for an internal JSON endpoint found only
# /api/user/status and /api/search/suggest. It also blocks non-Dutch traffic at the
# network edge, which no amount of local cleverness gets past.
#
# So this goes through Apify, whose actor runs inside their network. Confirmed with a
# real run before it was written: 15 Dutch vacancies in 11 seconds, each carrying a
# title, a real location, a contract type, a full description and an apply URL.
_WERK_NL_ACTOR = 'blackfalcondata/werk-scraper'
_WERK_NL_TIMEOUT_SECONDS = 420

# The actor returns one record per vacancy with several description shapes; this is the
# order to prefer them in -- plain text first, since everything downstream reads text.
_WERK_NL_DESCRIPTION_FIELDS = ('descriptionText', 'description', 'descriptionMarkdown')


def _fetch_werk_nl(client: ApifyClient, role_term: str, city: str | None = None,
                   max_results: int = 200, days_old: int = 30) -> list[dict]:
    """The Netherlands, country-wide or city-scoped. Never raises for a bad response.

    `includeDetails` is on because the description is what every downstream rule reads:
    without it the rows would arrive as thin as arbeitsagentur.de's and would have to be
    enriched one page at a time afterwards.
    """
    run_input = {
        'query': role_term,
        'maxResults': max_results,
        'includeDetails': True,
        'daysOld': days_old,
        'descriptionMaxLength': 6000,
    }
    if city:
        run_input['location'] = city

    run = client.actor(_WERK_NL_ACTOR).call(run_input=run_input,
                                            timeout_secs=_WERK_NL_TIMEOUT_SECONDS)
    dataset_id = (run or {}).get('defaultDatasetId')
    if not dataset_id:
        return []
    return _werk_nl_rows(list(client.dataset(dataset_id).iterate_items()), city)


def _werk_nl_rows(items: list, city: str | None = None) -> list[dict]:
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get('url') or item.get('applyUrl') or item.get('detailUrl')
        title = item.get('title') or item.get('functionName') or ''
        if not (url and title):
            continue
        description = ''
        for field in _WERK_NL_DESCRIPTION_FIELDS:
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                description = ' '.join(value.split())
                break
        rows.append({
            'title': title,
            'company': item.get('companyName') or item.get('employer') or '',
            # werk.nl shouts its locations ("AMSTERDAM"), which reads badly in the table
            # and matches nothing that compares against a city name.
            'location': (item.get('location') or item.get('city') or city or '').title(),
            'country': 'Netherlands',
            'posted_date': item.get('datePosted') or item.get('publishedAt')
            or item.get('startDate'),
            'url': url,
            'description': description or f"{title} at {item.get('companyName') or ''}",
            'platform': 'werk.nl',
            'google_stage': 'known',
            'employment_type': item.get('contractType') or '',
            # Only when the actor really gave nothing: with includeDetails on it almost
            # always does, and claiming thin_description when the text is real would
            # wrongly exempt the row from the Remote rule's positive check.
            'thin_description': not description,
        })
    return rows


# ---------------------------------------------------------------------------
# workatastartup.com -- Y Combinator's own board, also through an Apify actor.
#
# It is already in GOOGLE_GLOBAL_EXTRA_SITES, and on a real Netherlands search it produced
# exactly nothing. Asking why: the page opens fine (180 KB through the browser rung) and
# offers 79 same-domain links, but every one of them is a category -- /jobs/l/software-
# engineer and the like -- so there is no individual-posting pattern to learn and nothing
# for the crawler to deepen into.
#
# It is worth the trouble rather than writing off: YC companies are unusually
# remote-friendly and hire at exactly the level the user is looking at. Confirmed with real
# runs before this was written -- 15 postings back, each with a real
# workatastartup.com/jobs/NNNNN URL, a company, a location and a description.
#
# One thing the probing showed that the code below depends on: the actor's filters are
# narrow. `query="Data Scientist"` with `remoteOnly` returned zero, `query="data"` returned
# five, no filter at all returned everything. So the query is sent unquoted and the app's
# own rules do the filtering, which is what they are for.
_WORKATASTARTUP_ACTOR = 'parsebird/yc-jobs-scraper'
_WORKATASTARTUP_TIMEOUT_SECONDS = 300


def _fetch_workatastartup(client: ApifyClient, role_term: str,
                          max_results: int = 100) -> list[dict]:
    """Y Combinator's job board. Never raises for a bad response."""
    run = client.actor(_WORKATASTARTUP_ACTOR).call(
        run_input={'searchQuery': role_term, 'maxResults': max_results},
        timeout_secs=_WORKATASTARTUP_TIMEOUT_SECONDS)
    dataset_id = (run or {}).get('defaultDatasetId')
    if not dataset_id:
        return []
    return _workatastartup_rows(list(client.dataset(dataset_id).iterate_items()))


def _workatastartup_rows(items: list) -> list[dict]:
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get('url') or item.get('applyUrl')
        title = item.get('title') or ''
        if not (url and title):
            continue
        description = ''
        for field in ('descriptionText', 'description', 'companyTagline'):
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                description = ' '.join(value.split())
                break
        rows.append({
            'title': title,
            'company': item.get('companyName') or '',
            'location': item.get('location') or item.get('companyLocation') or '',
            # Genuinely global: YC companies hire from everywhere, and the country is
            # whatever the listing itself says rather than the search's country.
            'country': None,
            'posted_date': item.get('createdAt') or item.get('postedAt'),
            'url': url,
            'description': description or f"{title} at {item.get('companyName') or ''}",
            'platform': 'workatastartup.com',
            'google_stage': 'global',
            'thin_description': not description,
        })
    return rows


def _fetch_apify_credit_label(client: ApifyClient) -> str:
    """Real, current-cycle remaining credit from Apify's own usage API -- never
    estimated. Falls back to the plain 'Apify Token' label (no $ figure) if the numbers
    aren't available for some reason; the token itself being valid is checked
    separately, this is best-effort display only."""
    try:
        limits = client.user().limits()
        max_usd = (limits.get('limits') or {}).get('maxMonthlyUsageUsd')
        used_usd = (limits.get('current') or {}).get('monthlyUsageUsd')
        if max_usd is not None and used_usd is not None:
            remaining = max(0.0, max_usd - used_usd)
            return f"Apify Token - ${remaining:.2f} credit"
    except Exception:
        pass
    return "Apify Token"
