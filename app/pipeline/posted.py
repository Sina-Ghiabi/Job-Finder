# -*- coding: utf-8 -*-
"""When a listing was posted, and whether that is recent enough to keep.

The user's observation, and the data bore it out immediately: the three paid actors take a date
range, but nothing else in the search does. Google results never see it, and neither do the
two sources that between them supply most of a German search -- EURES and arbeitsagentur.de
are direct APIs, not actors, and they hand back whatever they have.

Measured on the real German corpus, 4,647 listings after duplicates:

    europa.eu (EURES)     median 21 days old, 90% within 128,  oldest   953
    arbeitsagentur.de     median 25 days old, 90% within 154,  oldest 1,990
    linkedin              median 14 days old                   oldest   350

Nineteen hundred and ninety days is five and a half years. With the search set to "past
week", 83.8% of the dated listings were older than that.

TWO RULES, AND THE SECOND IS THE IMPORTANT ONE

A listing older than the chosen range is dropped. A listing with **no date at all** is
kept -- 1,567 of those 4,647, of which 1,145 are Google results and 336 come from
workatastartup.com. Not knowing when something was posted is not evidence that it is old,
and this app's standing rule is that what cannot be established is never grounds for
deleting. They go on to every other filter exactly as before.

WHAT IS READ, AND WHAT IS DELIBERATELY NOT

A date field, and nothing else. Every value in 11,186 real listings across three countries
was ISO or a unix stamp, written by the source itself; there is no interpretation in reading
one, only arithmetic.

Reading the advert's own text was built and then deliberately removed. It needed a
dictionary of 510 phrases across fourteen languages to tell "Veröffentlichungsdatum:
19.08.2026" from "Eintrittsdatum: 01.10.2026", because an advert carries start dates,
application deadlines, expiry dates, dates of birth, CSS library version stamps, and above
all salaries -- "45.000,00" is date-shaped. It worked: 36 of 36 hand-built cases, and all 42
dates it found in the German corpus were genuine. It was removed anyway, on the user's decision
and on the measurement: those 42 came out of 1,790 undated listings, and only two of them
were old enough to drop. Two listings do not pay for the one ambiguity that remained -- a
Hays page carries three "Online since" dates, one for its job and two for the vacancies
advertised beside it, and nothing in the text says which belongs to which.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


# Where sources put the date. Read in order and the first usable one wins; a source that
# sends two never disagrees with itself, and one that sends none falls through to None.
POSTED_DATE_FIELDS = (
    'posted_date',      # what sources_norm writes, and what nearly everything uses
    'postedDate',       # some actors, before normalisation
    'datePosted',       # schema.org JobPosting, straight from a page's JSON-LD
    'publishedAt',      # Remotive and several API sources
    'created_at',       # RemoteOK
    'listedAt',         # LinkedIn's raw field
    'date',             # the plainest name, used by a few boards
    'posted',
)

# Six shapes turned up in 11,186 real listings across three countries:
#
#   5,133   2026-07-20T20:26:09.305000+00:00   ISO, microseconds, offset      (EURES)
#   2,045   2026-09-05                         a plain date                   (LinkedIn, BA)
#     572   2026-09-02T05:00:00.000Z           ISO, milliseconds, Z           (several)
#      48   2026-09-08T21:47:54                 ISO, no zone                   (Remotive)
#      41   1788857704                          unix seconds, as a string      (arbeitnow)
#      15   2026-08-17T16:00:06+00:00           ISO, seconds, offset           (RemoteOK)
#
# The list below is far longer than that, deliberately. The user's instruction: every date
# format in the world, not only the ones already seen. A source added next month writes
# whatever its country writes, and a format that is missing here does not fail loudly -- the
# listing simply reads as undated and slips past the date filter in silence. Each extra
# entry costs one failed strptime and buys a whole source.
#
# Ordered most-specific first, because strptime is happy to accept a short pattern against a
# longer string's prefix: '%Y-%m-%d' would swallow '2026-09-05 14:30' and throw the time
# away. Four-digit years before two-digit ones for the same reason.
_WRITTEN_DATE_FORMATS: tuple = (
    # --- ISO and near-ISO, with a time -------------------------------------------------
    '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
    '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M',
    '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M',          # German, Austrian, Swiss, Polish
    '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',          # French, Italian, Spanish, UK
    '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M',          # US
    '%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M',          # Dutch
    '%Y%m%d%H%M%S', '%Y%m%dT%H%M%S',                # compact, no separators

    # --- purely numeric: every order, every separator, both year widths ----------------
    # Generated below rather than typed out, so no combination is missed by hand. The three
    # orders are year-month-day (ISO and east Asia), day-month-year (most of Europe, South
    # America, India, Australia) and month-day-year (North America); the separators are the
    # four the world writes -- '-', '/', '.', ' ' -- and both four- and two-digit years.
    #
    # Order matters and is not alphabetical: a four-digit year is tried before a two-digit
    # one so "05.09.26" is not read as the year 5, and day-first before month-first because
    # every country this app searches except the US writes the day first. An ambiguous
    # "05/09/2026" therefore reads as 5 September, which is right for Germany, Austria,
    # France, Italy, Spain, the Netherlands and the UK, and wrong only for the US.
    '%Y%m%d',

    # --- written months, English -------------------------------------------------------
    '%b %d, %Y',       # Sep 5, 2026
    '%b %d %Y',        # Sep 5 2026
    '%B %d, %Y',       # September 5, 2026
    '%B %d %Y',
    '%d %b %Y',        # 5 Sep 2026
    '%d %B %Y',        # 5 September 2026
    '%d-%b-%Y',        # 5-Sep-2026
    '%d.%b.%Y',
    '%b %d, %y', '%d %b %y',
    '%d %B, %Y', '%B %d, %Y %H:%M', '%b %d, %Y %H:%M',

    # --- written months with a weekday in front ----------------------------------------
    '%a, %d %b %Y', '%a %d %b %Y',                  # Mon, 5 Sep 2026
    '%A, %d %B %Y', '%A %d %B %Y',                  # Monday, 5 September 2026
    '%a, %d %b %Y %H:%M:%S',                        # RFC 822 / HTTP, without the zone
    '%A, %B %d, %Y', '%a, %b %d, %Y',               # Monday, September 5, 2026

    # --- year and month only, for boards that publish no day ---------------------------
    '%Y-%m', '%m/%Y', '%m.%Y', '%m-%Y', '%B %Y', '%b %Y',
)

# Every numeric order against every separator, both year widths. Written as a loop because a
# hand-typed list of 24 is a list with a gap in it, and a missing combination does not fail
# loudly -- the listing just reads as undated and slips past the date filter unnoticed.
_NUMERIC_DATE_FORMATS = tuple(
    sep.join(parts)
    for year in ('%Y', '%y')                       # four digits first: "05.09.26" is 2026
    for parts in (('%d', '%m', year),              # day first -- most of the world
                  ('%m', '%d', year),              # month first -- North America
                  (year, '%m', '%d'))              # year first -- ISO, east Asia
    if parts[-1] == year or parts[0] == year
    for sep in ('-', '/', '.', ' ')
)

# ...and the same again carrying a time, since boards append one as often as not.
_NUMERIC_DATETIME_FORMATS = tuple(
    '%s %s' % (fmt, clock)
    for fmt in _NUMERIC_DATE_FORMATS
    for clock in ('%H:%M:%S', '%H:%M')
)

# Times before dates: a pattern without %H happily matches the date half of a string that
# has a time, and throws the time away. Harmless for a day count, but it would also let
# '%d.%m.%Y' claim '05.09.2026 14:30' before '%Y-%m-%d %H:%M' ever sees it.
_DATE_ONLY_FORMATS: tuple = (_NUMERIC_DATETIME_FORMATS + _WRITTEN_DATE_FORMATS
                             + _NUMERIC_DATE_FORMATS)

# Month names in the languages this app searches, so a date written out in German or Finnish
# is read rather than shrugged at. strptime's %b and %B follow the process locale, which is
# English here and cannot be changed per-call safely, so the names are translated to English
# before strptime ever sees them.
_MONTH_NAMES = {
    # German
    'januar': 'January', 'februar': 'February', 'marz': 'March', 'märz': 'March',
    'april': 'April', 'mai': 'May', 'juni': 'June', 'juli': 'July', 'august': 'August',
    'september': 'September', 'oktober': 'October', 'november': 'November',
    'dezember': 'December', 'jan': 'Jan', 'feb': 'Feb', 'mrz': 'Mar', 'okt': 'Oct',
    'dez': 'Dec',
    # Dutch
    'januari': 'January', 'februari': 'February', 'maart': 'March', 'mei': 'May',
    'augustus': 'August', 'oktober ': 'October ',
    # French
    'janvier': 'January', 'fevrier': 'February', 'février': 'February', 'mars': 'March',
    'avril': 'April', 'juin': 'June', 'juillet': 'July', 'aout': 'August',
    'août': 'August', 'septembre': 'September', 'octobre': 'October',
    'novembre': 'November', 'decembre': 'December', 'décembre': 'December',
    # Italian
    'gennaio': 'January', 'febbraio': 'February', 'marzo': 'March', 'aprile': 'April',
    'maggio': 'May', 'giugno': 'June', 'luglio': 'July', 'agosto': 'August',
    'settembre': 'September', 'ottobre': 'October', 'dicembre': 'December',
    # Spanish and Portuguese
    'enero': 'January', 'febrero': 'February', 'abril': 'April', 'mayo': 'May',
    'junio': 'June', 'julio': 'July', 'septiembre': 'September', 'octubre': 'October',
    'noviembre': 'November', 'diciembre': 'December',
    'janeiro': 'January', 'fevereiro': 'February', 'marco': 'March', 'março': 'March',
    'maio': 'May', 'junho': 'June', 'julho': 'July', 'setembro': 'September',
    'outubro': 'October', 'novembro': 'November', 'dezembro': 'December',
    # Swedish, Norwegian, Danish
    'januari ': 'January ', 'mars ': 'March ', 'maj': 'May', 'juli ': 'July ',
    'oktober': 'October', 'desember': 'December',
    # Finnish
    'tammikuu': 'January', 'helmikuu': 'February', 'maaliskuu': 'March',
    'huhtikuu': 'April', 'toukokuu': 'May', 'kesakuu': 'June', 'kesäkuu': 'June',
    'heinakuu': 'July', 'heinäkuu': 'July', 'elokuu': 'August', 'syyskuu': 'September',
    'lokakuu': 'October', 'marraskuu': 'November', 'joulukuu': 'December',
    # Polish
    'styczen': 'January', 'styczeń': 'January', 'luty': 'February',
    'marzec': 'March', 'kwiecien': 'April', 'kwiecień': 'April', 'czerwiec': 'June',
    'lipiec': 'July', 'sierpien': 'August', 'sierpień': 'August',
    'wrzesien': 'September', 'wrzesień': 'September', 'pazdziernik': 'October',
    'październik': 'October', 'listopad': 'November', 'grudzien': 'December',
    'grudzień': 'December',
    # Polish declines the month in a date -- "5 września 2026" is the genitive of
    # "wrzesień", and the stem changes rather than just taking an ending, so the case
    # forms have to be listed. The other Slavic and Finnic languages inflect by suffix
    # alone, which the stem match in _with_english_months already handles.
    'stycznia': 'January', 'lutego': 'February', 'marca': 'March', 'kwietnia': 'April',
    'maja': 'May', 'czerwca': 'June', 'lipca': 'July', 'sierpnia': 'August',
    'wrzesnia': 'September', 'września': 'September', 'pazdziernika': 'October',
    'października': 'October', 'listopada': 'November', 'grudnia': 'December',
}

# Longest first. "september" must be tried before "sep", or the short name matches and
# leaves "tember" for strptime to choke on.
_MONTH_NAMES_BY_LENGTH = sorted(_MONTH_NAMES, key=len, reverse=True)

# "3 days ago", "vor 3 Tagen", "il y a 3 jours" -- boards that print an age rather than a
# date. Every language this app searches, because a German board writes German.
_RELATIVE_PATTERN = re.compile(
    r'(\d+)\s*\+?\s*'
    r'(minute|minuten|minuut|minuti|minutos|minuter|minutter|minuuttia|'
    r'hour|stunde|stunden|uur|heure|ora|ore|hora|horas|timme|timmer|time|tunti|godzin|'
    r'day|days|tag|tage|tagen|dag|dagen|dage|dagar|jour|jours|giorno|giorni|dia|dias|'
    r'paiva|paivaa|paivää|päivää|dni|dzien|'
    r'week|weeks|woche|wochen|semaine|settimana|settimane|semana|semanas|vecka|veckor|'
    r'uge|uger|uke|uker|viikko|viikkoa|tydzien|tygodni|'
    r'month|months|monat|monate|monaten|maand|maanden|mois|mese|mesi|mes|meses|'
    r'manad|maned|kuukausi|kuukautta|miesiac|miesiecy)',
    re.IGNORECASE)

_RELATIVE_DAYS = {
    'minute': 0, 'hour': 0, 'day': 1, 'week': 7, 'month': 30,
}

# "today", "just posted", "heute", "vandaag" -- an age of zero, written in words.
_TODAY_WORDS = re.compile(
    r'\b(today|just posted|new|heute|soeben|vandaag|nieuw|aujourd|oggi|hoy|hoje|'
    r'idag|i dag|tanaan|tänään|dzisiaj)\b', re.IGNORECASE)
_YESTERDAY_WORDS = re.compile(
    r'\b(yesterday|gestern|gisteren|hier|ieri|ayer|ontem|igar|i g[åa]r|eilen|wczoraj)\b',
    re.IGNORECASE)


# Words a board wraps around a date: "Posted on", "Veröffentlicht am", "Publicado el".
# Removed before parsing so the date underneath can be read.
_TRIM_AROUND_DATE = re.compile(
    r'\b(?:posted|published|listed|updated|created|added|on|at|since|'
    r'ver[oö]ffentlicht|eingestellt|aktualisiert|am|vom|seit|'
    r'geplaatst|gepubliceerd|op|sinds|'
    r'publi[ée]|mis en ligne|le|depuis|'
    r'pubblicato|il|dal|'
    r'publicado|el|desde|'
    r'publicerad|den|publisert|offentliggjort|julkaistu|'
    r'opublikowano|dnia)\b[:\s]*', re.IGNORECASE)

# "1st", "2nd", "3rd", "5th" -- English ordinals.
_ORDINAL_SUFFIX = re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)\b', re.IGNORECASE)

# The full stop German, Austrian, Czech and Finnish put after a day number when a month name
# follows: "5. Dezember 2026". Only removed before a letter, so "05.09.2026" keeps its dots.
_DAY_FULL_STOP = re.compile(r'\b(\d{1,2})\.\s*(?=[A-Za-zÀ-ÿ])')

# The words Spanish, Portuguese, French and the Nordic languages put between the parts of a
# written date: "5 de septiembre de 2026", "5. desember 2026", "den 5 september 2026".
_JOINING_WORDS = re.compile(r'\s+(?:de|del|di|du|av|den|der|des)\s+', re.IGNORECASE)

# A date embedded in a sentence. Only reached when the whole string did not parse, so these
# never get the chance to mis-read a clean field. Longest shapes first: a full written date
# before a bare numeric one, so "5 September 2026" is not clipped to "5".
_DATE_INSIDE_TEXT = (
    # 5 September 2026 · September 5, 2026 · 5-Sep-2026
    re.compile(r'\d{1,2}[\s.\-/]*[A-Za-z]{3,12}[\s.\-/,]+\d{2,4}'),
    re.compile(r'[A-Za-z]{3,12}[\s.\-/]+\d{1,2}[\s.,\-/]+\d{2,4}'),
    # 2026-09-05 · 2026/09/05 · 2026.09.05
    re.compile(r'\d{4}[-/.]\d{1,2}[-/.]\d{1,2}'),
    # 05.09.2026 · 05/09/2026 · 05-09-2026 · and the two-digit-year versions
    re.compile(r'\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}'),
)



def _with_english_months(text: str) -> str:
    """A date with its month name translated to English, so strptime can read it.

    strptime resolves %b and %B through the process locale. Changing that per call is not
    safe in a threaded search, and it would only ever be right for one language at a time
    anyway -- a single German search returns Dutch, French and English adverts too.

    Longest name first, so "september" is not matched by "sep" and left with a stray
    "tember" behind it. And the match runs against the START of a word only, because several
    languages inflect the month rather than leaving it bare: Finnish writes "syyskuuta" for
    "of September", Polish "września". Matching the stem catches every case ending without
    needing a table of them.
    """
    lowered = text.lower()
    for foreign in _MONTH_NAMES_BY_LENGTH:
        at = lowered.find(foreign)
        if at < 0:
            continue
        # A month name must start a word -- otherwise "mai" fires inside "email".
        if at and (lowered[at - 1].isalpha() or lowered[at - 1].isdigit()):
            continue
        # ...and whatever follows is a case ending, which strptime never needs to see.
        end = at + len(foreign)
        while end < len(lowered) and lowered[end].isalpha():
            end += 1
        return text[:at] + _MONTH_NAMES[foreign] + text[end:]
    return text


def _unit_days(word: str) -> int:
    """How many days one of the words in _RELATIVE_PATTERN stands for."""
    lowered = word.lower()
    for stem, days in _RELATIVE_DAYS.items():
        if lowered.startswith(stem[:3]):
            return days
    # Every remaining stem, by its first letters -- German 'wochen', Finnish 'viikkoa',
    # Polish 'miesiecy' and the rest.
    for stem, days in (('woch', 7), ('sem', 7), ('veck', 7), ('uge', 7), ('uke', 7),
                       ('viik', 7), ('tyd', 7), ('tyg', 7),
                       ('monat', 30), ('maand', 30), ('mois', 30), ('mes', 30),
                       ('man', 30), ('kuu', 30), ('mies', 30),
                       ('tag', 1), ('dag', 1), ('jour', 1), ('gior', 1), ('dia', 1),
                       ('paiv', 1), ('päiv', 1), ('dni', 1), ('dzie', 1),
                       ('stund', 0), ('uur', 0), ('heure', 0), ('ora', 0), ('hora', 0),
                       ('timm', 0), ('time', 0), ('tunti', 0), ('godz', 0),
                       ('minut', 0), ('minuu', 0)):
        if lowered.startswith(stem):
            return days
    return 1


def parse_posted_date(value, now=None, _extracting=False, allow_relative=True):
    """A posting date from any shape a source sends, or None when there is none.

    None means "this listing does not say", never "this listing is old". Everything that
    reads this treats the two completely differently -- see `is_recent_enough`.

    `_extracting` is internal: it marks the one recursive call made when a date is being
    pulled out of a longer sentence, and stops that call pulling again.

    `allow_relative` is off when the value came out of body text rather than a date field.
    "3 days ago" in a field is an age; the same words in an advert are as likely to be a
    search filter, a contract length or a notice period.
    """
    text = str(value or '').strip()
    if not text or text.lower() in ('nan', 'none', 'null', '-'):
        return None
    now = now or datetime.now(timezone.utc)

    # Unix seconds or milliseconds, as a number or a string of one.
    if re.fullmatch(r'\d{9,13}', text):
        seconds = int(text[:10])
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    # ISO 8601, in all its variants: with a zone, with Z, with micro- or milliseconds, with
    # a space instead of the T. Tried longest-first so a full timestamp is not truncated to
    # its date when it did not need to be.
    cleaned = text.replace('Z', '+00:00').replace(' ', 'T', 1)
    for candidate in (cleaned, cleaned[:26], cleaned[:19], cleaned[:10]):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    # Written-out dates, in the orders and languages different countries write them. The
    # month name is translated first because strptime reads %B in the process locale, which
    # is English here -- "5. September 2026" parses either way, "5. Dezember 2026" does not.
    candidate_text = _with_english_months(text)
    for fmt in _DATE_ONLY_FORMATS:
        try:
            return datetime.strptime(candidate_text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # The same again with the decoration removed. Four kinds, all real:
    #
    #   "Posted on 5 Sep 2026"        a label in front
    #   "5th September 2026"          an English ordinal
    #   "5. Dezember 2026"            the full stop Germanic languages put after a day
    #   "5 de septiembre de 2026"     the joining words Spanish and Portuguese use
    stripped = _TRIM_AROUND_DATE.sub(' ', candidate_text)
    stripped = _ORDINAL_SUFFIX.sub(r'\1', stripped)
    stripped = _DAY_FULL_STOP.sub(r'\1 ', stripped)
    stripped = _JOINING_WORDS.sub(' ', stripped)
    stripped = re.sub(r'\s+', ' ', stripped).strip(' ,;:.')
    if stripped and stripped != candidate_text:
        for fmt in _DATE_ONLY_FORMATS:
            try:
                return datetime.strptime(stripped, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue

    # An age rather than a date.
    if allow_relative:
        if _TODAY_WORDS.search(text):
            return now
        if _YESTERDAY_WORDS.search(text):
            return now - timedelta(days=1)
        relative = _RELATIVE_PATTERN.search(text)
        if relative:
            amount = int(relative.group(1))
            return now - timedelta(days=amount * _unit_days(relative.group(2)))

    # Last resort: a date sitting inside a longer sentence. Everything above required the
    # whole string to be the date, which is right for a dedicated field and wrong for the
    # line some boards put it on -- "Stellenangebot vom 05.09.2026, Vollzeit". Only tried
    # once nothing else matched, so a clean value is never routed through the guesswork.
    #
    # `_extracting` stops the recursion: a pattern can match the entire string it was given,
    # and re-entering with the same text would then recurse until the stack ran out -- which
    # it did, 985 frames deep, the first time this was written without the guard.
    if not _extracting:
        for pattern in _DATE_INSIDE_TEXT:
            found = pattern.search(candidate_text)
            if not found:
                continue
            inner = parse_posted_date(found.group(0), now=now, _extracting=True)
            if inner is not None:
                return inner
    return None


def posted_date_of(row, now=None):
    """The posting date of one listing, from whichever date field carries it.

    A date field only, and never the advert's own text. The text was tried -- a dictionary
    of 510 labels in fourteen languages, so that "Veröffentlichungsdatum: 19.08.2026" could
    be told apart from "Eintrittsdatum: 01.10.2026" -- and it was removed again. Measured on
    the German corpus it dated 42 of the 1,790 listings that have no date field, and of those
    42 only two were old enough to be dropped. Two listings is not worth the one risk it
    carried: a Hays page carried three "Online since" dates, one for the job and two for the
    vacancies advertised beside it, and nothing in the text says which is which.

    A date field has no such ambiguity. A source that fills one fills it with the posting
    date, and in 11,186 real listings every value was ISO or a unix stamp.
    """
    for field in POSTED_DATE_FIELDS:
        when = parse_posted_date(row.get(field), now=now)
        if when is not None:
            return when
    return None


def age_in_days(row, now=None):
    """How old a listing is, or None when it does not say."""
    now = now or datetime.now(timezone.utc)
    when = posted_date_of(row, now=now)
    if when is None:
        return None
    return max(0, (now - when).days)


def is_recent_enough(row, max_age_days, now=None) -> bool:
    """Was this posted within the chosen range?

    True for a listing with no date, and that is the rule that matters. 1,567 of 4,647
    German listings carry no date -- 1,145 of them Google results -- and not knowing when
    something was posted is not evidence that it is old. They carry on to every other
    filter, and Claude reads them like anything else.
    """
    if not max_age_days:
        return True
    age = age_in_days(row, now=now)
    return age is None or age <= max_age_days


# How many days each actor's own date value stands for. Read straight from what the three
# actors accept, so this table and the request they receive can never disagree.
_LINKEDIN_DAYS = {'past24Hours': 1, 'pastWeek': 7, 'pastMonth': 30, 'anyTime': 0}


def max_age_from_date_settings(date_settings) -> int:
    """The widest range any platform was asked for, in days. 0 means no limit.

    The user's reasoning: the three paid actors filter by date themselves, and nothing else in
    the search does -- Google results, EURES and arbeitsagentur.de all arrive with whatever
    age they happen to have. Measured on the German corpus, that meant adverts up to 1,990
    days old, five and a half years.

    The WIDEST of the three is the cut-off, not the narrowest. Narrowest would throw away
    listings a platform was legitimately asked for: with LinkedIn on a month and Indeed on
    its 14-day maximum, cutting at 14 would delete three weeks of LinkedIn results that were
    correctly returned. Widest only removes what no platform was asked for at all.
    """
    settings = date_settings or {}
    days = [
        _LINKEDIN_DAYS.get(str(settings.get('linkedin') or ''), 0),
        int(settings['indeed']) if str(settings.get('indeed') or '').isdigit() else 0,
        int(settings['glassdoor']) if str(settings.get('glassdoor') or '').isdigit() else 0,
    ]
    # A zero anywhere means that platform was asked for everything, and a listing it
    # returned cannot be too old by definition. "Any time" switches the filter off.
    if any(value == 0 for value in days):
        return 0
    return max(days)


def remove_stale(rows: list, max_age_days, now=None) -> tuple:
    """Drop listings posted longer ago than the chosen range. Returns (kept, removed)."""
    if not max_age_days:
        return list(rows), []
    kept: list = []
    removed: list = []
    for row in rows:
        (kept if is_recent_enough(row, max_age_days, now=now) else removed).append(row)
    return kept, removed
