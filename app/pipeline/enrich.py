"""Fetching the real job description for listings whose source only returned a stub.

Four sources (arbeitsagentur.de, jooble, jobcloud/jobs.ch, swissdevjobs.ch) have APIs that
return no description text at all -- they set `thin_description` and the description comes
out as literally "<title> at <company>", around 40 characters. Measured on a real corpus:
**113 of 185 listings (61%)** arrived that way, with a median description length of 76
characters.

That is not a cosmetic problem. Everything downstream reads the description:

  * the Remote rule waives its positive check for thin rows, so on-site jobs sail
    through -- verified on real listings: "Arbeitsort Jena" and "Arbeitsort Espelkamp",
    zero remote keywords, both kept purely because the text was unreadable;
  * `is_too_senior`, `has_sponsorship_restriction` and `is_unpaid` all scan the
    description and see almost nothing;
  * language detection needs 40 characters before it will even guess, so a German
    listing with a 37-character stub is never detected and never translated;
  * and Claude scores the listing against the resume on those same ~40 characters, which
    makes its match percentage close to meaningless for 61% of the list.

Every one of those rows already carries a working URL. Fetching it costs nothing but an
HTTP request -- no Apify credit, no actor -- and on a real sample took 1.1 seconds for 25
listings, turning an average of 45 characters into 1,585.

Deliberately a free HTTP fetch + BeautifulSoup rather than the Apify crawler: these are
ordinary server-rendered pages (verified: the description is present in the HTML, no
JavaScript needed), and routing them through a paid crawler would cost real money for
something a free GET already answers.

The fetch goes through the ladder in `fetcher`, so a posting on a site that refuses a
plain request is still read -- but with the browser rung switched off. Enrichment can face
hundreds of rows eight at a time, and a browser launch each would turn a one-second step
into a several-minute one for the rare page that needs it.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import time

from bs4 import BeautifulSoup

try:
    # Purpose-built main-content extraction: it knows what a menu, a cookie banner and a
    # footer look like, which a tag-stripping pass does not. Optional on purpose -- if the
    # package is ever missing from a build, readable_text simply falls back to the pass
    # this app always used rather than the whole search failing over a description.
    import trafilatura
except Exception:                                            # pragma: no cover
    trafilatura = None

from . import fetcher
from .errors import SearchCancelled
# What a page IS lives in pages.py; this module only decides whether to read it again.
from .pages import is_board_index_text
from .text import is_true_flag, looks_like_error_page, text_of

# A description shorter than this is a summary line or a stub, not the posting. Used to
# decide whether a structured source actually answered or whether the page is worth
# reading instead. Kept well under ENRICH_MIN_USEFUL_CHARS so that a genuinely short but
# real JSON-LD description is still preferred to guessing at the layout.
_MIN_STRUCTURED_DESCRIPTION_CHARS = 200

# How much of the plainly-extracted text a cleaner route has to retain before it is
# believed. Set from the measurement rather than by taste: across 24 real postings the
# cleaner routes kept 60-90% of the page text, and the single failure kept 24%. Anything
# above half is chrome being stripped; anything far below it is content going missing.
_KEEP_PLAIN_TEXT_BELOW_RATIO = 0.5

# One page per listing, fetched concurrently. Eight is the same ceiling the pre-flight
# checks use -- enough to hide the latency, low enough not to look like an attack to any
# single site.
ENRICH_MAX_WORKERS = 8

# A page that takes longer than this is not worth holding the whole search for; the
# listing simply keeps its stub and carries on.
ENRICH_TIMEOUT_SECONDS = 20

# Below this, whatever came back is not a real description -- an error page, a consent
# wall, an empty shell -- and replacing a stub with it would make things worse, not
# better. Real recovered descriptions in testing ran 3,000-6,000 characters.
ENRICH_MIN_USEFUL_CHARS = 300

# How long to wait before asking again for the pages that did not answer.
#
# WHY A SECOND PASS EXISTS AT ALL, and what it is not for. A real German search fetched 860
# pages in 65 seconds; 579 came back with a description and 281 did not. Running the very
# same URLs again afterwards, with the same code, recovered 196 of them. Nothing about those
# pages or that code had changed in between, so a share of every enrichment pass is lost to
# whatever the network was doing in that minute -- and each loss costs a listing its text for
# the rest of the search, which is how 217 arbeitsagentur.de adverts reached Claude as a
# 69-character stub.
#
# The obvious explanation was crowding: eight workers into one host, since 789 of those
# German listings came from arbeitsagentur.de alone. It is wrong, and the measurement says
# so plainly. The same 60 known-good pages, fetched at eight, four and two at a time:
#
#     8 at a time     5 seconds    60 of 60
#     4 at a time     6 seconds    60 of 60
#     2 at a time    11 seconds    60 of 60
#
# Not one failure at any speed, and throttling the host merely doubled the time. A per-host
# gate was written for this and then removed again: it cost real time and bought nothing.
#
# The failures are transient, so the answer is to ask again rather than to ask more politely.
# The pause is there because a retry that arrives immediately is part of the same burst.
# Against a search measured in hours it costs nothing, and it needs no Apify credit -- which
# is exactly the trade Sina has asked for every time: "زمان مهم نیست / نمیخوام آگهی از دستم
# بره".
#
# What the retries do NOT recover: pages that are genuinely gone. Of the 123 still empty
# after two passes, fetching each one alone and unhurried recovered exactly one.
#
# So: five attempts in all, spread across about ten minutes, and then the ones that never
# answered are dropped rather than sent onward as a bare job title. The gaps lengthen on
# purpose -- an immediate retry is part of the same burst that failed, and whatever was
# wrong with the network in one minute is usually still wrong in the next. Ten minutes is
# Sina's own figure, and the trade is his standing one: time is free, a lost listing is not.
ENRICH_RETRY_PAUSES = (20, 60, 120, 240, 180)

# Words a job posting has and a navigation menu does not, in the languages this app
# searches. A posting says what you will do, what it wants, or what it offers; a menu says
# "Hire developers · Hire designers · Sign in".
#
# The first version of this list was written from English and had sixteen English phrases
# against eight German, five Dutch, four French, three Italian, three Spanish -- and nothing
# whatsoever for Portuguese, Swedish, Norwegian, Danish, Finnish or Luxembourgish. A Danish
# advert therefore scored zero however real it was, and the guard below silently threw away
# the page that had just been fetched for it.
#
# It showed up in German first because German is where the corpus is. Of a hundred
# arbeitsagentur.de listings whose pages were fetched for real, eight came back with 1,768
# to 4,788 characters of plainly genuine advert -- "30 Tage Urlaub", "unbefristeten
# Arbeitsvertrag", "Zum nächstmöglichen Zeitpunkt suchen wir einen AI Consultant" -- and were
# rejected for carrying only one or two of the eight words this list knew.
#
# So the list is now per language and written from real adverts rather than from English.
# The German entries come from 546 real descriptions in the German corpus: `erfahrung`
# appears in 57% of them, `aufgaben` in 49%, `kenntnisse` in 47%, `studium` in 45%,
# `abgeschlossenes` in 40%.
#
# What is deliberately NOT here: words a job BOARD uses about jobs. "Vollzeit", "Teilzeit",
# "Gehalt" and "Arbeitszeit" all appear in the filter widget down the side of a search page,
# and adding them would make every index page look like a posting.
_POSTING_WORD_GROUPS = {
    'en': (r'responsibilit|requirement|qualificat|you will|we offer|we are looking|'
           r'experience (?:with|in)|your profile|benefits|salary|skills|degree|years of|'
           r'knowledge of|what you|about the role|apply now|join (?:our|us)|'
           r'the role|the team|you bring|ideally|fluent in|full[- ]time position|'
           r'permanent contract|holiday|annual leave|we are seeking|your tasks|'
           r'what we offer|your responsibilities|nice to have|must have'),
    'de': (r'aufgaben|aufgabengebiet|aufgabenbereich|t[äa]tigkeit|anforderungen|'
           r'anforderungsprofil|qualifikation|voraussetzung|wir bieten|wir suchen|'
           r'suchen wir|dein profil|ihr profil|dein aufgaben|erfahrung|kenntnisse|'
           r'abgeschlossenes|studium|ausbildung|berufserfahrung|f[äa]higkeiten|'
           r'mitbringen|idealerweise|w[üu]nschenswert|freuen uns|bewerbung|benefits|'
           r'verg[üu]tung|urlaubstage|tage urlaub|festanstellung|arbeitsvertrag|'
           r'unbefristet|weiterbildung|weiterentwicklung|arbeitsumfeld|einarbeitung|'
           r'zum n[äa]chstm[öo]glichen|teil unseres teams|eigenverantwortlich|'
           r'verantwortung|das erwartet|das bringst du|das bieten wir|deine aufgaben|'
           r'ihre aufgaben|homeoffice|home[- ]office'),
    'nl': (r'wat je|wij bieden|wij zoeken|jouw profiel|jouw taken|ervaring|'
           r'werkzaamheden|functie-eisen|functieomschrijving|vaardigheden|opleiding|'
           r'wat wij bieden|wij vragen|arbeidsvoorwaarden|vakantiedagen|'
           r'vast contract|doorgroeimogelijkheden|solliciteer|over de functie|'
           r'jij hebt|je krijgt|het team'),
    'fr': (r'vos missions|nous recherchons|votre profil|exp[ée]rience|comp[ée]tences|'
           r'profil recherch[ée]|vos t[âa]ches|nous offrons|nous vous proposons|'
           r'formation|dipl[ôo]me|avantages|r[ée]mun[ée]ration|cong[ée]s pay[ée]s|'
           r'contrat [àa] dur[ée]|poste [àa] pourvoir|rejoignez|votre mission|'
           r'ce que nous offrons|vous [êe]tes'),
    'it': (r'le tue mansioni|cerchiamo|requisiti|il tuo profilo|competenze|esperienza|'
           r'offriamo|mansioni|responsabilit[àa]|titolo di studio|laurea|'
           r'formazione|benefit|retribuzione|ferie|contratto a tempo|'
           r'cosa offriamo|ti occuperai|entrerai a far parte'),
    'es': (r'buscamos|tus funciones|requisitos|ofrecemos|tu perfil|experiencia|'
           r'conocimientos|competencias|titulaci[óo]n|formaci[óo]n|beneficios|'
           r'salario|vacaciones|contrato indefinido|qu[ée] ofrecemos|'
           r'te ofrecemos|tus responsabilidades|se requiere|imprescindible'),
    'pt': (r'procuramos|as tuas fun[çc][õo]es|requisitos|oferecemos|o teu perfil|'
           r'experi[êe]ncia|conhecimentos|compet[êe]ncias|forma[çc][ãa]o|licenciatura|'
           r'benef[íi]cios|sal[áa]rio|f[ée]rias|contrato sem termo|o que oferecemos|'
           r'as suas fun[çc][õo]es|responsabilidades'),
    'sv': (r'vi erbjuder|vi s[öo]ker|dina arbetsuppgifter|arbetsuppgifter|din profil|'
           r'erfarenhet|kunskaper|kvalifikationer|utbildning|f[öo]rm[åa]ner|'
           r'l[öo]n|semesterdagar|tillsvidareanst[äa]llning|om tj[äa]nsten|'
           r'vi ser g[äa]rna|du har|om oss|meriterande'),
    'no': (r'vi tilbyr|vi s[øo]ker|dine arbeidsoppgaver|arbeidsoppgaver|din profil|'
           r'erfaring|kunnskap|kvalifikasjoner|utdanning|goder|'
           r'l[øo]nn|feriedager|fast stilling|om stillingen|'
           r'du har|om oss|[øo]nskelig'),
    'da': (r'vi tilbyder|vi s[øo]ger|dine arbejdsopgaver|arbejdsopgaver|din profil|'
           r'erfaring|kendskab|kvalifikationer|uddannelse|personalegoder|'
           r'l[øo]n|feriedage|fast stilling|om stillingen|'
           r'du har|om os|det er en fordel'),
    'fi': (r'tarjoamme|etsimme|ty[öo]teht[äa]v[äa]t|teht[äa]v[äa]si|profiilisi|'
           r'kokemus|osaaminen|p[äa]tevyys|koulutus|edut|'
           r'palkka|lomap[äa]iv[äa]t|vakituinen|tietoa teht[äa]v[äa]st[äa]|'
           r'sinulla on|meist[äa]|katsotaan eduksi'),
    # Luxembourgish borrows from German and French; both are above, and these are its own.
    'lb': r'mir bidden|mir sichen|d[äa]ng aufgaben|erfarung|kenntnisser',
}

_POSTING_WORDS = re.compile(
    r'\b(?:%s)\w*' % '|'.join(_POSTING_WORD_GROUPS[lang]
                              for lang in sorted(_POSTING_WORD_GROUPS)), re.I)

# How many of them a real posting carries. Measured on the Austrian corpus: the 401 clean
# postings carry a median of 14, and the quarter that carry fewest still carry 5. The
# chrome-only descriptions carry 0 or 1 -- arc.dev's 505 characters of "For companies Hire
# developers Hire designers Hire marketers" score zero. Three is comfortably between them.
_MIN_POSTING_WORDS = 3


def carries_posting_words(description) -> bool:
    """Does this text read like a job posting at all?

    Purely the vocabulary question, with no allowance made for length. Used where the answer
    has to be trusted on its own: deciding whether a freshly fetched page may REPLACE a
    description that is already there.
    """
    text = ' '.join(str(description or '').split())
    return len(_POSTING_WORDS.findall(text)) >= _MIN_POSTING_WORDS


def looks_like_chrome_only(description) -> bool:
    """True when a description is long enough to pass for real but says nothing about a job.

    The gap this closes: `thin_description` is set by character count, so a page whose
    entire text is a navigation menu sails past it. Twenty-seven Austrian listings arrived
    that way -- every arc.dev posting carried exactly 505 characters, all of it the site's
    own menu, and not one word of the vacancy. They were then screened by Claude, which was
    asked to judge a job it had not been shown.

    Re-fetching them recovered a real posting for eight of the twelve tried, and all of
    those turned out to be remote roles -- exactly what Sina is looking for, invisible until
    the page was read properly.

    The length escape hatch is what separates this from carries_posting_words above, and it
    belongs here and not there. This function decides whether to spend a fetch, so a long
    page is left alone: the posting is somewhere inside it and re-reading is unlikely to
    help. The replacement guard cannot afford the same generosity -- a sign-in wall is
    easily longer than a job advert, and that is exactly how one was lost.
    """
    text = ' '.join(str(description or '').split())
    if not text:
        return True
    # Before the length escape hatch: a board's index is long BY NATURE, and being long is
    # exactly why it slipped through. See is_board_index_text.
    if is_board_index_text(text):
        return True
    if len(text) >= ENRICH_MIN_USEFUL_CHARS * 8:
        return False
    return not carries_posting_words(text)

# Sent because several of these sites return a consent/blocked page to an obviously
# scripted client. This is the same browser identity a person would arrive with.
ENRICH_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/122.0 Safari/537.36'),
    'Accept-Language': 'en-US,en;q=0.9,de;q=0.8',
}

# Stripped before the text is extracted: these carry site chrome (menus, cookie banners,
# footers) that is identical on every page and would otherwise dilute the description --
# and worse, could feed the content rules words the actual job posting never used.
_STRIP_TAGS = ('script', 'style', 'nav', 'footer', 'header', 'noscript', 'form', 'aside')


def _extract_page_text(html: str) -> str:
    """The readable text of a job page, with site chrome removed."""
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    return ' '.join(soup.get_text(' ').split())


def job_posting_json_ld(html: str) -> dict:
    """The site's own schema.org JobPosting object, if it publishes one.

    This is the best description a page can give, because the site wrote it as data rather
    than as a layout: `description`, `title`, `hiringOrganization`, `jobLocation`,
    `datePosted` and `employmentType` as named fields, with no menu, banner or footer mixed
    in. Google for Jobs requires the markup, so any board that wants its listings indexed
    has a reason to publish it correctly.

    Measured over one real posting from each of the 24 hosts a real search produced: 9 of
    them publish a JobPosting object, and among those 9 the fields are essentially always
    there -- title 9/9, hiringOrganization 9/9, description 9/9, datePosted 9/9,
    employmentType 9/9, jobLocation 8/9. arbeitsagentur.de is one of the nine, which is
    what makes this worth having: its API returns no job text at all, so its listings are
    flagged thin_description and exempted from the "must confirm remote" requirement --
    and its posting pages carry the full description in JSON-LD the whole time.

    Returns {} rather than raising for anything malformed. A site publishing broken JSON-LD
    must cost nothing beyond falling back to reading the page.
    """
    found: dict = {}
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all('script', attrs={'type': 'application/ld+json'}):
            raw = tag.string or tag.get_text() or ''
            try:
                data = json.loads(raw)
            except Exception:
                continue
            # A JobPosting can sit at the top level, inside an @graph, or inside a list --
            # all three appear in the wild, so the whole tree is walked rather than assumed.
            stack = [data]
            while stack:
                node = stack.pop()
                if isinstance(node, list):
                    stack.extend(node)
                elif isinstance(node, dict):
                    types = node.get('@type')
                    types = types if isinstance(types, list) else [types]
                    if 'JobPosting' in types and not found:
                        found = node
                    stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    except Exception:
        return {}
    return found


def _text_from_json_ld(posting: dict) -> str:
    """The description out of a JobPosting object, as plain text.

    The field is HTML by specification -- schema.org says so and every real example
    measured here honours it -- so it is parsed rather than used raw, or the listing's own
    markup would end up in front of the keyword rules and Claude.
    """
    description = posting.get('description')
    if not isinstance(description, str) or not description.strip():
        return ''
    try:
        return ' '.join(BeautifulSoup(description, 'html.parser').get_text(' ').split())
    except Exception:
        return ' '.join(description.split())


# Held while trafilatura (and so lxml) parses. See the comment at the call below: without it
# the process dies, not raises.
_EXTRACT_LOCK = threading.Lock()


def readable_text(html: str) -> str:
    """The job text of a page, by the most trustworthy route that works.

      1. the site's own JobPosting JSON-LD -- data, not layout
      2. trafilatura -- purpose-built main-content extraction
      3. strip the chrome tags and take what is left -- what this app always did

    Each rung is more of a guess than the one above it, so the order is not arbitrary.
    Measured on real posting pages, step 3 leaves navigation and cookie-banner text in the
    description (6 noise markers across 4 pages) where step 2 leaves almost none (1), and
    that noise is not cosmetic: run-together facet text like "timehybridmid2" is what made
    the on-site rule fire on listings that never mentioned a hybrid arrangement.

    A shorter result from a better route is normally the right answer -- that is chrome
    being removed, not content being lost. Measured over 24 real arbeitsagentur postings,
    JSON-LD returned a median 3,463 characters against the old route's 4,289 while carrying
    MORE job vocabulary (76 hits against 72): less text, more posting.

    But shorter is only right up to a point, and the fallback below is where that line is
    drawn. One page in those 24 gave trafilatura 257 characters where the old route found
    1,049 -- not chrome removal, a collapse -- and without this guard the chain would have
    handed back a quarter of a real description and called it an improvement. So a better
    route wins unless it returns less than `_KEEP_PLAIN_TEXT_BELOW_RATIO` of what simply
    reading the page produces, and that page's text is usable in its own right.
    """
    plain = _extract_page_text(html)

    def long_enough(candidate: str, may_exceed_plain: bool) -> bool:
        if len(candidate) < _MIN_STRUCTURED_DESCRIPTION_CHARS:
            return False
        if len(plain) < ENRICH_MIN_USEFUL_CHARS:
            return may_exceed_plain
        return len(candidate) >= len(plain) * _KEEP_PLAIN_TEXT_BELOW_RATIO

    # JSON-LD is trusted even when the page body reads as empty, because it is not read
    # off the layout at all -- it is what the site published ABOUT the job. A posting
    # rendered entirely in JavaScript has no body text to strip and still carries a
    # complete description here.
    structured = _text_from_json_ld(job_posting_json_ld(html))
    if long_enough(structured, may_exceed_plain=True):
        return structured

    if trafilatura is not None:
        try:
            # One thread at a time inside trafilatura, and this lock is the whole fix for a
            # crash that killed a search outright. The Amsterdam run died 56 minutes in, with
            # no Python error of any kind; Windows recorded why:
            #
            #   Faulting module: etree.cp38-win_amd64.pyd   (lxml)
            #   Exception code:  0xc0000005                 (access violation)
            #
            # trafilatura parses with lxml, whose C parser is not safe to drive from several
            # threads at once -- and this runs inside an 8-thread pool (enrich_thin_
            # descriptions) and again inside the crawl. A C-level fault cannot be caught by
            # anything in Python: the process is simply gone, which is why the checkpoint
            # exists at all, and why the earlier fault of this family (J) was mitigated
            # rather than cured.
            #
            # The cost is nothing that matters. Extraction is a few milliseconds of CPU per
            # page against a network fetch of a second or more, and every fetch still runs in
            # parallel -- only the parsing is queued.
            with _EXTRACT_LOCK:
                extracted = trafilatura.extract(html, include_comments=False,
                                                include_tables=True, favor_recall=True)
        except Exception:
            extracted = None
        if extracted:
            extracted = ' '.join(extracted.split())
            # ...but trafilatura is NOT given that licence, and the difference is the whole
            # reason these two are separated. It reads the same DOM the tag-strip reads, so
            # when stripping nav/header/footer leaves nothing, there was nothing but chrome
            # to find -- and with favor_recall on it will happily hand back the menu. A page
            # that is one long <nav> produced 0 characters the old way and 2,639 characters
            # of "Home Jobs About Contact" this way, which would have been written into a
            # listing as its job description.
            if long_enough(extracted, may_exceed_plain=False):
                return extracted

    return plain or structured


def fetch_listing_description(url: str) -> str:
    """The real description behind one listing URL, or '' if it could not be had.

    Never raises: a listing that cannot be enriched keeps its stub, which is exactly the
    behaviour before this step existed. A search must not fail because one job board was
    slow.
    """
    try:
        # The fetch ladder, not a bare GET: a posting on a site that answers 403 to a
        # browser-shaped request is exactly the case enrichment exists for, and the rung
        # that site needs was already worked out when its pattern was discovered, so this
        # costs one extra lookup rather than a re-climb.
        #
        # `allow_browser=False` on purpose. Enrichment runs eight rows at a time and can
        # face hundreds; a browser launch per row would turn a fast step into a slow one,
        # and a posting that needs a full browser to read is rare enough to leave as a stub.
        result = fetcher.fetch(url, allow_browser=False)
        if result.status != 200 or not result.html:
            return ''
        from bs4 import BeautifulSoup as _BS
        title = ''
        try:
            _soup = _BS(result.html, 'html.parser')
            title = _soup.title.string if _soup.title else ''
        except Exception:
            title = ''
        body = readable_text(result.html)
        # A throttled or blocked fetch still returns 200 with a real body. Replacing a
        # stub with that is strictly worse than keeping the stub.
        if looks_like_error_page(title, body):
            return ''
        return body
    except Exception:
        return ''


class _EnrichTally:
    """What one enrichment run has managed so far.

    fetch_round used to be nested inside enrich_thin_descriptions purely because it mutated
    two counters through `nonlocal`, which nothing outside a closure can reach -- so it could
    never be called, or tested, on its own. Holding the counters in one object is what lets
    the round move out: same numbers, same guards, now reachable.
    """

    __slots__ = ('improved', 'cancelled', 'by_platform')

    def __init__(self):
        self.improved = 0
        self.cancelled = False
        self.by_platform: dict = {}

    def recovered(self, platform: str) -> None:
        self.improved += 1
        self.by_platform[platform] = self.by_platform.get(platform, 0) + 1


def _fetch_round(rows_to_try, workers, tally, should_cancel):
    """One pass over a set of rows. Returns the ones still without a description."""
    remaining = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_listing_description, text_of(r.get('url'))): r
                   for r in rows_to_try}
        for future in concurrent.futures.as_completed(futures):
            row = futures[future]
            if should_cancel and should_cancel():
                # Cancel stops SUBMITTING more work; whatever already came back is
                # kept, same principle as every other stage.
                for pending in futures:
                    pending.cancel()
                tally.cancelled = True
                break
            try:
                text = future.result()
            except Exception:
                remaining.append(row)
                continue
            current = text_of(row.get('description'))
            # Longer is not the same as better, and that gap cost a real listing. A
            # LinkedIn posting of 4,344 characters vanished from a real run because the
            # refetch came back longer -- a sign-in wall is easily longer than a job ad --
            # and this guard, which only measured length, let it overwrite the posting.
            #
            # So a replacement has to be three things: long enough to be a description,
            # longer than what is already there, and recognisably a job posting rather
            # than a page of furniture. The third is the one that was missing.
            # ...and not the board's own index of other vacancies, which is long, full of
            # posting words, and about everybody's job but this one (see pages.is_gone).
            if (len(text) >= ENRICH_MIN_USEFUL_CHARS and len(text) > len(current)
                    and carries_posting_words(text)
                    and not is_board_index_text(text)):
                row['description'] = text
                row['thin_description'] = False
                tally.recovered(text_of(row.get('platform')) or 'unknown')
            else:
                remaining.append(row)
    return remaining




def enrich_thin_descriptions(rows: list[dict], progress_cb=None, should_cancel=None) -> int:
    """Replace stub descriptions with the real thing, in place. Returns how many improved.

    Only touches rows flagged `thin_description` that carry a URL, and only when the
    fetched text is both longer than what is already there and long enough to be a real
    description (ENRICH_MIN_USEFUL_CHARS). A row that fails any of those keeps exactly
    what it had.

    Clearing `thin_description` on success matters as much as the text itself: that flag
    is what makes the Remote rule waive its check and what tells the language step not to
    bother. Once the row has a real description, neither waiver should apply any more.
    """
    # Two ways a listing needs its page read. The flag is the original one -- a source that
    # returned no description at all. The second is a page whose text is long enough to look
    # real and is entirely the site's own menu; see looks_like_chrome_only for the arc.dev
    # listings that exposed it. Both end up in the same place, and the guard below is what
    # makes adding the second safe: a fetch only replaces what is there when it comes back
    # longer AND long enough, so a page that answers "Loading..." changes nothing.
    targets = [r for r in rows
               if text_of(r.get('url'))
               and (is_true_flag(r.get('thin_description'))
                    or looks_like_chrome_only(r.get('description')))]
    if not targets:
        return 0

    if progress_cb:
        progress_cb('ENRICH_START', 0, 1)
        progress_cb(
            f"GLOG:enrich|info|{len(targets)} listing(s) arrived with no real description — "
            "fetching each one's own page (free, no Apify credit)…",
            0, 1,
        )

    tally = _EnrichTally()

    missed = list(targets)
    try:
        missed = _fetch_round(missed, ENRICH_MAX_WORKERS, tally, should_cancel)

        # Then ask again, and again, over roughly ten minutes. A failure here is transient
        # far more often than it is final -- see ENRICH_RETRY_PAUSES for the measurement --
        # and the pauses lengthen because whatever was wrong with the network in one minute
        # is usually still wrong in the next.
        for attempt, pause in enumerate(ENRICH_RETRY_PAUSES, start=2):
            if not missed or tally.cancelled or (should_cancel and should_cancel()):
                break
            if progress_cb:
                progress_cb(
                    f"GLOG:enrich|info|{len(missed)} page(s) have not answered yet — "
                    f"waiting {pause}s, then asking again (attempt {attempt} of "
                    f"{len(ENRICH_RETRY_PAUSES) + 1}).", 0, 1)
            time.sleep(pause)
            before_retry = tally.improved
            missed = _fetch_round(missed, ENRICH_MAX_WORKERS, tally, should_cancel)
            if progress_cb and tally.improved > before_retry:
                progress_cb(
                    f"GLOG:enrich|success|Attempt {attempt} recovered "
                    f"{tally.improved - before_retry} more.", 0, 1)
    except SearchCancelled:
        raise

    # Whatever never answered is dropped, on Sina's instruction and on the evidence for it.
    #
    # This is the one place the app deletes a listing for a reason other than a rule about
    # the job, so it is worth being exact about what is thrown away. Every row here was
    # asked for by name, five times, across ten minutes, and never produced a line of text:
    # its description is still "<title> at <company>", about 69 characters. Nothing can read
    # that -- not the Remote rule, not seniority, not the language step, and not Claude,
    # which would be scoring a CV against a job title. And Sina cannot read it either.
    #
    # They are not merely slow. Of the 123 the German corpus was left with after two passes,
    # fetching each one alone and unhurried recovered exactly one: the rest are pages that
    # have been taken down or never had a description to give.
    #
    # A cancelled search drops nothing: the rows that went unfetched went unfetched because
    # the search stopped, which says nothing about the pages.
    # And only the ones that have nothing. "Did not answer" is not the same as "has no
    # text": a row already holding a real 5,000-character description is on this list too,
    # because the page that was fetched for it came back SHORTER and was rightly refused.
    # Dropping that would delete a perfectly good posting on the strength of a redundant
    # fetch, which is the opposite of the point.
    dropped: list = []
    if missed and not tally.cancelled and not (should_cancel and should_cancel()):
        dead = {id(row) for row in missed
                if not carries_posting_words(row.get('description'))}
        if dead:
            dropped = [row for row in rows if id(row) in dead]
            rows[:] = [row for row in rows if id(row) not in dead]

    if progress_cb:
        for platform, count in sorted(tally.by_platform.items()):
            progress_cb(f"ENRICH_SITE_RESULT:{platform}|{count}", 0, 1)
        progress_cb(
            f"GLOG:enrich|success|Recovered the real description for {tally.improved} of "
            f"{len(targets)} listing(s).",
            0, 1,
        )
        if dropped:
            progress_cb(
                f"GLOG:enrich|warning|{len(dropped)} listing(s) never answered after "
                f"{len(ENRICH_RETRY_PAUSES) + 1} attempts over "
                f"{sum(ENRICH_RETRY_PAUSES) // 60} minutes and had no description at all — "
                "removed, because nothing downstream can read a bare job title.", 0, 1)
        progress_cb('ENRICH_END', 0, 1)
    return tally.improved
