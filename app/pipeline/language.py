"""Detecting which language a listing is written in.

Translation used to live here too. It was removed once the vocabularies covered thirteen
languages: translating a Dutch advert into English so an English word list could read it was
paying DeepL to undo work the Dutch word list already did. Detection stayed, because the
vocabularies need to know which one to load.
"""
from __future__ import annotations

import hashlib
import re
import threading
from lingua import Language, LanguageDetectorBuilder

# is_category_uncertain asks the category rules themselves whether they found anything.
# Imported at module level rather than inside the function: rules.py does not import this
# module back, so there is no cycle to avoid.
from .rules import category_from_words



# Detection is lingua's, not langdetect's. Measured on 400 real listings from a real
# search, labelled by unmistakable function words ("und/der/die" vs "the/and/with"):
#
#                       full description        first 180 characters
#     langdetect        399/400   13.7s         379/400  -- 21 wrong
#     lingua            399/400    3.1s         396/400  --  4 wrong
#
# The short-text column is the reason to switch, not the clock. This detector's verdict
# DELETES listings: a listing wrongly called non-English is "translated", marked
# was_translated, and then dropped by lacks_english_mention for not containing the word
# "English" -- the exact failure documented under _MIN_LANGDETECT_CHARS below. langdetect
# is wrong that way five times as often, and short descriptions are common here because
# four direct-API sources return almost no text at all.
#
# The speed is a genuine bonus rather than the point: the language step is 303s of a real
# Filter run over 2,542 listings, and roughly 87s of that was langdetect. Re-detecting the
# same 2,542 listings with lingua takes 33.7s. (The 400-listing sample above suggested 4.4x;
# the real corpus gives 2.6x, because its descriptions are longer. The measured number on
# the real thing is the one that counts.)
#
# Restricted to the languages this app can actually meet -- the countries it searches, plus
# English. An open-ended detector has to weigh Tagalog and Yoruba against German on a
# fragment of a job advert, and every extra candidate is another way to be wrong about text
# that was only ever going to be one of these.
_DETECTOR_LANGUAGES = (
    Language.ENGLISH, Language.GERMAN, Language.FRENCH, Language.SPANISH, Language.ITALIAN,
    Language.DUTCH, Language.PORTUGUESE, Language.SWEDISH, Language.DANISH, Language.BOKMAL,
    Language.FINNISH, Language.POLISH,
)

_DETECTOR = None
_DETECTOR_LOCK = threading.Lock()


def _detector():
    """The detector, built once, on first use rather than at import.

    Both halves of that matter and both were measured. Preloading the models costs ~4s and
    makes each detection roughly 1.6x faster (800 real listings: 10.4s preloaded against
    16.0s lazy), which is clearly worth paying once inside a 303s Filter step -- but paying
    it at IMPORT put those same 4 seconds on the launch of a desktop app that may never run
    a Filter at all. Building here moves the cost to the first listing that needs it.

    Locked because detect_language is called from translate_many's 30-worker pool: without
    it the first Filter run would build up to 30 detectors at once, each loading its own
    copy of the models.
    """
    global _DETECTOR
    if _DETECTOR is None:
        with _DETECTOR_LOCK:
            if _DETECTOR is None:
                _DETECTOR = (LanguageDetectorBuilder
                             .from_languages(*_DETECTOR_LANGUAGES)
                             .with_preloaded_language_models()
                             .build())
    return _DETECTOR


def _detect(text: str) -> str:
    """The ISO-639-1 code lingua settles on, or 'unknown'. Never raises.

    Norwegian comes back as BOKMAL, whose ISO-639-1 code is 'nb'; the rest of the app only
    ever compares against 'en', so the distinction costs nothing here.
    """
    try:
        language = _detector().detect_language_of(text)
    except Exception:
        return 'unknown'
    if language is None:
        return 'unknown'
    code = getattr(language, 'iso_code_639_1', None)
    return code.name.lower() if code is not None else 'unknown'


# Nothing here translates anything any more, and nothing has for some time. The 13
# language vocabularies replaced it: a rule reads a Dutch advert in Dutch instead of
# paying to turn it into English first. What stood in this gap -- the DeepL keys, the
# translation model, the worker count tuned on 40 Dutch listings, the spent-key set --
# was scaffolding for a stage that no longer exists, and every one of those names was
# read by nothing. Detection stays, below: knowing a listing is Dutch is what chooses
# the Dutch vocabulary.


_ANTHROPIC_API_KEY: list = [None]






# be unreliable on short text -- e.g. 'AI'/'AI' detects as Hungarian, 'Data'/'Data' as
# Indonesian, 'Remote'/'Remote' as Romanian. This matters for a real reason beyond just
# a wrong language LABEL: a listing wrongly detected as non-English gets "translated"
# (a near no-op, since it's already English) and marked was_translated=True, which then
# feeds directly into lacks_english_mention() below -- and a real English job posting
# almost never contains the literal word "English" in its own text (it doesn't need
# to), so it gets wrongly DROPPED. Sina flagged this exact scenario as suspicious; this
# confirmed it. Below this length, detection is too unreliable to trust either way, so
# text this short is treated as 'unknown' (same as already-empty text) -- which,
# equally importantly, is NOT the same as 'en': translate_many/maybe_translate already
# only skip translation for 'en' OR 'unknown' together, so a short listing just never
# gets misclassified into the wrong bucket in the first place, whichever language it
# actually turns out to be.
_MIN_LANGDETECT_CHARS = 40


# Where a cached langdetect verdict and the text it was computed from are stashed on a
# job dict. Same idea as the Claude screening cache: Filter is re-run by hand often, and
# re-deriving an answer that cannot have changed is pure waste.
_LANG_CACHE_KEY = '_lang_detected'


_LANG_CACHE_TEXT_KEY = '_lang_detected_for'


def detect_language(row) -> str:
    """Uses the FULL title+description (not just a short prefix) so a listing that's mostly
    German with a handful of English tech terms ("Data Engineering", "Python", ...) doesn't
    get misdetected as English and skip translation.

    That full-text scan is also, by a wide margin, the most expensive thing in a Filter
    run: profiling 800 listings put ~19 s of a ~28 s run inside langdetect's n-gram
    extraction alone, more than every other step combined. lingua cut that by roughly 4x
    (measured: 13.7s -> 3.1s over 400 listings) but it is still the step to watch. It is not safe to make it
    cheaper by shortening the text -- capping the window below ~3,000 characters is
    exactly the misdetection bug documented above _MIN_LANGDETECT_CHARS, and a cap high
    enough to be safe (10,000) touches no real listing on disk, so it buys nothing.

    What IS safe is not repeating the work. lingua is deterministic -- the same text always
    yields the same verdict. So the
    verdict is memoised on the row alongside a fingerprint of the exact text it was
    derived from, and reused only when that fingerprint still matches. Keying on the text
    rather than a flag is what makes it correct -- translation REPLACES the description,
    and a deep-crawl can fill one in later, and both of those must re-detect rather than
    serve a stale answer. A hash rather than the text itself because this is persisted
    into jobs.json: storing the description a second time would roughly double the file,
    while hashing 22,000 characters costs ~10 us against an 8 ms detection.

    The write-back is guarded to real dicts: detect_language also gets called with pandas
    rows during raw Search display, and those must never be mutated here. A non-dict just
    takes the uncached path, exactly as before.
    """
    text = f"{row.get('title') or ''} {row.get('description') or ''}".strip()
    if len(text) < _MIN_LANGDETECT_CHARS:
        return 'unknown'
    fingerprint = hashlib.sha1(text.encode('utf-8', 'replace')).hexdigest()
    cached = row.get(_LANG_CACHE_KEY)
    if cached and row.get(_LANG_CACHE_TEXT_KEY) == fingerprint:
        return cached
    result = _detect(text)
    if isinstance(row, dict):
        row[_LANG_CACHE_KEY] = result
        row[_LANG_CACHE_TEXT_KEY] = fingerprint
    return result


def _detect_language_pair(row) -> tuple:
    """(verdict, fingerprint) for one row -- exactly what detect_language computes, but
    RETURNED instead of memoised, so a DataFrame can store it in real columns.

    Search already paid for this work and threw it away: is_category_uncertain calls
    detect_language on every listing whose Type badge it can't pin down without
    translation, which measured at 4,434 ms over 552 of 800 listings -- and because a
    DataFrame row is a pandas Series, not a dict, detect_language's write-back guard
    (correctly) refuses to memoise onto it. Filter then repeated all of it from scratch.

    Storing the answer in two real columns instead means it rides through
    `df.to_dict('records')` into the job dicts and on into jobs.json, so Filter's language
    step opens an already-warm cache. Detecting every row here rather than only the
    uncertain ones is a deliberate trade: it does not increase total work (800 detections
    once, instead of 552 at Search plus 800 at Filter), and it moves what remains off the
    Filter button -- which the user sits and waits on -- and under Search, which is
    network-bound and minutes long anyway.

    The text expression is character-for-character identical to detect_language's, which
    is what guarantees the same verdict and a matching fingerprint. Where it can't match
    -- a field that is NaN in the DataFrame but None in the dict -- the fingerprints
    simply differ, Filter re-detects, and the result is still correct.
    """
    text = f"{row.get('title') or ''} {row.get('description') or ''}".strip()
    if len(text) < _MIN_LANGDETECT_CHARS:
        return ('unknown', '')
    fingerprint = hashlib.sha1(text.encode('utf-8', 'replace')).hexdigest()
    return (_detect(text), fingerprint)


# Every language of the countries this app searches, plus the ways a posting asks for one
# without naming it. The owner has English, and basic Italian, and nothing else.
#
# Each name is followed by `\w*` because this is read in the posting's OWN language now, and
# most of these languages build compounds: "Deutschkenntnisse", "Englischkenntnisse",
# "norskkunnskaper", "deutschsprachig", "suomen kielen". A word boundary after "deutsch"
# finds none of them -- which is exactly how a rule that catches "Fluent German and English"
# missed 1,765 of the 1,778 German listings that state the requirement in German.
#
# `deutsch(?!land)` is the one exclusion that has to be there: "in Deutschland",
# "deutschlandweit" and "Deutschlands" appear in most German postings and name the country,
# not the language.
_OTHER_LANGUAGES = (
    r'german\w*|deutsch(?!land)\w*|french|français\w*|francais\w*|spanish|español\w*|'
    r'espanol\w*|castellano|dutch|nederlands\w*|vlaams|flemish|swedish|svenska|svensk\w*|'
    r'danish|dansk\w*|norwegian|norsk\w*|finnish|suomi|suomen|finn\w*|polish|polski\w*|'
    r'polskiego|portuguese|português\w*|portugues\w*|czech|čeština|cestina|greek|'
    r'ελληνικά|romanian|română|romana|hungarian|magyar\w*|turkish|türkçe|arabic|'
    r'russian|mandarin|chinese|japanese|korean|hebrew|'
    # Italian is deliberately absent, and adding it while extending this list for the other
    # languages was a regression caught by a probe: the owner has basic Italian and lives in
    # Italy, so treating it as a language he lacks deletes the listings closest to him.
    r'lëtzebuergesch|luxembourgish|(?:the\s+)?local\s+language|(?:de\s+)?lokale\s+taal|'
    r'a\s+second\s+language|another\s+language|(?:the\s+)?national\s+language')

# "English", as each of those languages spells it. A posting that pairs the local language
# with English writes BOTH in its own language -- "Deutsch und Englisch", "Nederlands en
# Engels", "français et anglais" -- and the rule only ever looked for the English spelling,
# whose letters are not even a substring of "Englisch".
_ENGLISH = (r'english|englisch\w*|engels\w*|anglais\w*|inglese|inglés|ingles|inglês|'
            r'engelsk\w*|engelska|englanti\w*|englannin|angielski\w*|angličtina|'
            r'anglictina|angol\w*|engleză|engleza|αγγλικά')

# How a posting says it wants a language really well, in each of those languages. Paired with
# a language name this is a requirement on its own -- "Sehr gute Deutschkenntnisse" names no
# English at all, and is still a wall. Every one of these is a LEVEL word: none of them can be
# read as offering the language rather than demanding it, which is what keeps this from
# firing on "wir bieten Deutschkurse".
_LANGUAGE_LEVEL = (
    r'sehr\s+gute\w*|gute\w*|fließend\w*|fliessend\w*|verhandlungssicher\w*|exzellente\w*|'
    r'ausgezeichnete\w*|perfekte\w*|muttersprach\w*|sicher\w*\s+im|beherrsch\w*|'
    r'sprachniveau|kenntnisse\s+in|uitstekende|goede|vloeiend\w*|beheersing|'
    r'maîtrise|maitrise|courant\w*|bilingue|excellente\s+connaissance|langue\s+maternelle|'
    r'ottima\s+conoscenza|buona\s+conoscenza|fluente|madrelingua|'
    r'nativo|nativa|fluido|dominio|se\s+requiere|'
    r'flydende|flytende|gode|goda|flytande|sujuva|hyvä|erinomain\w*|'
    r'fluent\w*|fluency|proficien\w*|native|mother\s+tongue|excellent\s+command|'
    r'good\s+command|working\s+knowledge|business\s+level|solid\s+knowledge')

# "or" is deliberately NOT a conjunction here. "C1+ level in either English or Spanish",
# "professional working proficiency in English or Russian" and "if the documents are not in
# German or English" all mean English on its own is enough -- the opposite of what this rule
# is looking for. Including it deleted three real listings that ask for nothing Sina lacks.
_LANGUAGE_CONJUNCTION = r'(?:and|&|\+|/|plus|as well as|sowie|und)'

# A bounded gap on BOTH sides of the conjunction, because real postings put the level in
# between: "German (native or C2) and English", "Fluency in German (C1 level) and English",
# "English and at least basic skills in German", "C1 level in English and B2 level in
# German". No sentence end may fall inside it, so it cannot reach into an unrelated clause.
_LANGUAGE_GAP = r'(?:[^.;!?\n]{0,28}?)'

# This replaces two bare substrings -- "english and" / "and english" anywhere in the text.
# On 2,542 real listings those deleted 95, and reading what actually followed the phrase,
# many were nothing to do with language at all: "...and English benefits & perks", "fluent
# English and strong communication skills", "German and English language courses" (a free
# language course, offered as a BENEFIT), "English and enthusiasm for collaborating".
#
# The question this rule exists to answer is only answered when a language is NAMED, so the
# replacement requires one. Measured against the same corpus: 9 listings stop being deleted
# wrongly, and 19 real second-language demands that the substring test MISSED are now
# caught -- among them "Fluency in German & English required", "Deutsch C1, Englisch
# mindestens B1-B2", and "Fluent in English & good German".
#
# AND SINCE 4 OCTOBER THIS PATTERN NO LONGER DELETES ANYTHING. It is kept, and kept tested,
# because it is still the most precise description in the project of what "the posting pairs
# English with another language" looks like -- see _names_english_beside below, which is now
# what the rule uses, and requires_language_besides_english's docstring for why the pairing
# became a KEEP.
_SECOND_LANGUAGE_PATTERN = re.compile(
    r'\b(?:%s)\b%s\s*%s%s\s*\b(?:%s)\b'
    r'|\b(?:%s)\b%s\s*%s%s\s*\b(?:%s)\b'
    # "fluent in English and at least one more language" asks for a second language without
    # naming it, which is just as much of a blocker.
    r'|\benglish\b[^.;!?\n]{0,20}?\b(?:and|plus|&)\s+(?:at\s+least\s+)?'
    r'(?:one|a|another|a\s+second)\s+(?:more\s+|additional\s+|further\s+|other\s+)?language\b'
    % (_OTHER_LANGUAGES, _LANGUAGE_GAP, _LANGUAGE_CONJUNCTION, _LANGUAGE_GAP, _ENGLISH,
       _ENGLISH, _LANGUAGE_GAP, _LANGUAGE_CONJUNCTION, _LANGUAGE_GAP, _OTHER_LANGUAGES),
    re.I)

# A language named with the level it is wanted at, which needs no English beside it to be a
# wall: "Sehr gute Deutschkenntnisse in Wort und Schrift", "Verhandlungssichere
# Deutschkenntnisse", "Uitstekende beheersing van de Nederlandse taal", "Ottima conoscenza
# della lingua italiana". The pair pattern above cannot see any of these, because none of
# them mentions English at all.
#
# Both orders, because languages differ: German puts the level first ("gute Deutsch-"),
# Italian and Spanish put it before the noun but after the verb ("conoscenza della lingua
# italiana"), and English does both ("fluent German" / "German fluency"). The gap between
# them is short and cannot cross a sentence end, so a level word in one bullet never reaches
# a language name in the next.
_LANGUAGE_LEVEL_GAP = r'(?:[^.;!?\n]{0,20}?)'
_LEVELLED_LANGUAGE_PATTERN = re.compile(
    r'\b(?:%s)%s\s*\b(?:%s)\b'
    r'|\b(?:%s)\b%s\s*\b(?:%s)\b'
    % (_LANGUAGE_LEVEL, _LANGUAGE_LEVEL_GAP, _OTHER_LANGUAGES,
       _OTHER_LANGUAGES, _LANGUAGE_LEVEL_GAP, _LANGUAGE_LEVEL), re.I)

# The same requirement stated numerically: "Deutsch C1, Englisch mindestens B1-B2",
# "Deutschkenntnisse auf Niveau C1", "norsk på nivå B2".
_CEFR_PATTERN = re.compile(
    r'\b(?:%s)%s\s*(?:sprachkenntnisse\s*|kenntnisse\s*|niveau\s*|nivå\s*|nivel\s*|'
    r'livello\s*|niveau\s+|level\s*)?[abc][12]\b'
    % (_OTHER_LANGUAGES, _LANGUAGE_LEVEL_GAP), re.I)

# A second language offered as a bonus is not a barrier: "Clear communication in English
# (German is a HUGE plus)" explicitly does not require German.
#
# The qualifier has to be ATTACHED to the language, which in practice means a copula or a
# bracket binds them. Without that, "Excellent written and spoken German skills and English
# skills Desirable: Initial experience..." reads as if German were the desirable one, when
# "Desirable:" is simply the next section's heading -- and that posting does require German.
# The German idioms need no copula because they are qualifiers in themselves:
# "Deutschkenntnisse von Vorteil" cannot be read any other way.
_LANGUAGE_NICE_TO_HAVE = re.compile(
    r'(?:\bis\b|\bare\b|\bwould\s+be\b|\bwäre\b|\bwaere\b|\bsind\b|\bist\b|[(\[])'
    r'[^.;!?\n]{0,18}?\b(?:a\s+)?(?:huge\s+|big\s+|nice\s+|real\s+|added\s+)?'
    r'(?:plus|bonus|advantage|asset|beneficial|welcome|desirable|preferred|'
    r'nice\s+to\s+have|great\s+to\s+have|good\s+to\s+have)\b'
    r'|\b(?:von\s+vorteil|wünschenswert|wuenschenswert|von\s+nutzen|'
    # The same idiom in the other languages this now reads, since the rule no longer sees a
    # translated posting. Each one, like the German ones, is a qualifier in itself and needs
    # no copula: "Nederlands is een pré", "l'italiano è un plus".
    r'ist\s+ein\s+plus|sind\s+ein\s+plus|een\s+pré|een\s+pre|is\s+een\s+plus|'
    r'strekt\s+tot\s+aanbeveling|est\s+un\s+plus|serait\s+un\s+plus|apprécié|apprecie|'
    r'è\s+un\s+plus|gradita|preferenziale|es\s+un\s+plus|valorable|se\s+valorará|'
    r'en\s+fordel|et\s+pluss|meriterande|eduksi|katsotaan\s+eduksi|'
    r'nice\s+to\s+have|optional)\b'
    # "We offer German and English language COURSES free of charge" is a perk, and reads
    # structurally identical to "German and English language SKILLS required" -- the noun
    # after the pair is the only thing that separates them.
    r'|^\s*(?:language\s+)?(?:courses?|classes|lessons?|tuition|training|kurse?|'
    r'sprachkurse?|unterricht)\b'
    # "proficiency in Dutch, or the willingness to learn it" is an invitation, not a wall,
    # and so is "Deutschkenntnisse oder die Bereitschaft, Deutsch zu lernen". Found in the
    # random sample of what this rule removes, on a Postdoc posting that says exactly that.
    r'|\b(?:or\s+)?(?:the\s+)?willing(?:ness)?\s+to\s+learn\b'
    r'|\bbereitschaft[^.;!?\n]{0,30}?zu\s+(?:er)?lernen\b'
    r'|\bbereit[^.;!?\n]{0,20}?zu\s+(?:er)?lernen\b', re.I)

# The softener that sits INSIDE the phrase rather than after it: "Englisch und idealerweise
# Deutsch" -- English required, German ideally. _LANGUAGE_NICE_TO_HAVE looks at the clause
# that FOLLOWS a match and therefore cannot see this one at all, because the word doing the
# softening is in the middle of the matched span.
#
# Found by reading a random thirty of the 2,934 listings this rule removes. Two of the thirty
# were wrong, and this was one of them.
_LANGUAGE_IDEALLY = re.compile(
    r'\b(?:ideally|idealerweise|idealer\s*weise|vorzugsweise|preferably|preferred|'
    r'bij\s+voorkeur|liefst|de\s+préférence|de\s+preference|idéalement|idealement|'
    r'idealmente|preferiblemente|helst|fortrinnsvis|mieluiten|mielellään)\b', re.I)

# "Professional working proficiency in English OR Russian" offers a choice, and English wins
# it. The pair pattern has always known this -- "or" is deliberately not one of its
# conjunctions -- but the levelled pattern had to be told separately, because it matches a
# level word next to a language name and never looks at what joins them. Caught by the test
# that has guarded this since the "or" conjunction was first removed.
_LANGUAGE_EITHER_OR = re.compile(
    r'\b(?:%s)\b[^.;!?\n]{0,28}?\b(?:or|oder|of|ou|o|eller|tai|veya|lub)\b'
    r'|\b(?:or|oder|of|ou|o|eller|tai|veya|lub)\b[^.;!?\n]{0,28}?\b(?:%s)\b'
    % (_ENGLISH, _ENGLISH), re.I)

# The qualifier only counts inside the SAME clause -- see the comment above.
_LANGUAGE_CLAUSE_END = re.compile(r'[.;!?\n]|<br\s*/?>|</li>|</p>|[•▪]|\s\*\s')
_LANGUAGE_QUALIFIER_WINDOW = 60
def _clause_after(text: str, start: int, span: int = 90) -> str:
    """The words just after a match, where "German ... is a plus" puts the qualifier."""
    return text[start:start + span]

# "English", on its own, in any of the spellings _ENGLISH knows. Used only to RESCUE a
# listing, never to delete one -- which is what licenses the window below to be generous
# where every pattern above it is deliberately tight.
_ENGLISH_PATTERN = re.compile(r'\b(?:%s)\b' % _ENGLISH, re.I)

# How far from the language demand the word "English" may sit and still count as being said
# in the same breath. 160 characters each side, which is wide enough for the three shapes a
# real posting uses -- the pair in one sentence ("Fluency in German & English required"), the
# level sentence followed by the English one ("Sehr gute Deutschkenntnisse. Englisch für die
# interne Kommunikation."), and a bulleted language list, where the two names are in
# NEIGHBOURING bullets and no single clause holds both:
#
#     • Nederlands: vloeiend
#     • Engels: goede beheersing
#
# Deliberately not clause-scoped, then. Clause scope is correct for _LANGUAGE_NICE_TO_HAVE,
# because reaching into the next sentence there would invent a qualifier the posting never
# attached and DELETE nothing wrongly -- it would keep wrongly. Here the error runs the other
# way: a window too narrow deletes a listing Sina asked to see. So the window is wide, and
# the cost of its width is some postings that name English somewhere unrelated surviving to
# Claude. That is the direction he has chosen every time it has come up.
_ENGLISH_BESIDE_WINDOW = 160
def names_english_beside(text: str, start: int, end: int) -> bool:
    """True when the posting names English next to the span between `start` and `end`.

    Public, and taking positions rather than a match object, because the country vocabulary
    in rules.py answers this same question with its own keyword lists and has to cancel the
    same way. One window, one spelling list, two callers -- rule 5 of the nine: a rule in two
    places is two rules.
    """
    return bool(_ENGLISH_PATTERN.search(
        text[max(0, start - _ENGLISH_BESIDE_WINDOW):end + _ENGLISH_BESIDE_WINDOW]))


def _names_english_beside(text: str, hit) -> bool:
    """The same question, for a regex match -- which is how this module always asks it."""
    return names_english_beside(text, hit.start(), hit.end())

def requires_language_besides_english(row):
    """Drops a listing that wants a language Sina does not have INSTEAD of English.

    Reads the posting in whatever language it was written in. That is a correction, not a
    design: this rule was written when every listing was translated to English before the
    keyword stage, so it only ever looked for English words. Translation was then removed to
    stop paying DeepL, every other rule was given multilingual vocabulary, and this one was
    left behind -- with its own docstring still promising the text would arrive in English.

    What that cost, measured on the 5,442 real German listings of the Germany run: of the
    1,778 that state a German requirement in German, it caught **13**. The other 1,765 went
    through to Claude, which is both a bill and a gap -- the two REPLY listings Sina found
    asked for "Kommunikationsstärke in Deutsch und Englisch" and reached him anyway.

    THE PAIRING IS NOW A KEEP, WHICH REVERSES WHAT THIS RULE WAS BUILT TO DO

    Sina set out the four shapes a posting can have and what he wants of each, and he had
    the first three right about the code as it stood:

        says nothing about language   non-English posting  dropped (silent_about_english)
                                      English posting      kept -- it is already readable
        wants another language only  "Sehr gute Deutschkenntnisse"      dropped
        wants English AND another    "Deutsch und Englisch"             dropped
        wants English only           "Fluent English required"          kept

    Then: "اگر به صورت ترکیبی میگفت انگلیسی و یه زبان دیگه باید این رو هم قبول بکنه". The
    third row flips. A posting that asks for English alongside Dutch has said the work can
    be done in a language he has, and whether the second one is a wall is a judgement about
    his own CV that he would rather make himself, looking at the advert.

    So only one shape is left as a reason to delete: **a language he lacks, with English
    never named beside it**. That is the whole change, and it is why _SECOND_LANGUAGE_PATTERN
    -- the pair -- is no longer in the loop below at all.

    Dropping the pair pattern was not enough on its own, and this is the trap: the levelled
    pattern catches the pair too. "You are fluent in English and Dutch" puts "fluent" within
    twenty characters of "Dutch", so _LEVELLED_LANGUAGE_PATTERN fires on it with no help from
    the pair pattern, and "Sehr gute Deutsch und Englisch Kenntnisse" likewise. Removing the
    pair pattern alone would have changed nothing for either. The pairing has to be checked
    for POSITIVELY and allowed to cancel the hit, which is _names_english_beside.

    It also closes a gap that was there the whole time. The pair pattern's conjunctions are
    `and & + / plus sowie und` -- so "Nederlands en Engels" never matched, because the Dutch
    "en" is not among them, nor is French "et" or Italian "e". The rule the pairing cancels
    does not need a conjunction list at all, so every language's "and" is covered for free.

    Two shapes are looked for now, both of them "a language, wanted at a level":

        level     "Sehr gute Deutschkenntnisse"      _LEVELLED_LANGUAGE_PATTERN
        numeric   "Deutschkenntnisse auf Niveau C1"  _CEFR_PATTERN

    Either can be cancelled three ways: the posting names English beside it, it softens the
    demand inside the phrase ("Englisch und idealerweise Deutsch"), or it calls the language
    a bonus in the clause that follows ("German is a plus", "or the willingness to learn").
    """
    text = f"{row.get('title') or ''} {row.get('description') or ''}"
    for pattern in (_LEVELLED_LANGUAGE_PATTERN, _CEFR_PATTERN):
        for hit in pattern.finditer(text):
            # Sina's reversal, and it is checked first because it is the broadest of the
            # three: English named beside the demand means he has been offered a language he
            # reads, and the listing is his to judge.
            if _names_english_beside(text, hit):
                continue
            # Two places a posting can take the demand back: inside the phrase itself
            # ("Englisch und idealerweise Deutsch") and in the clause after it ("German is a
            # plus", "or the willingness to learn"). Both have to be read, because neither
            # can see what the other sees.
            if (_LANGUAGE_IDEALLY.search(hit.group(0))
                    or _LANGUAGE_EITHER_OR.search(hit.group(0))):
                continue
            if not _LANGUAGE_NICE_TO_HAVE.search(_clause_after(text, hit.end())):
                return True
    return False


# The English column's three answers, in the order Sina reads them: "English only" first,
# because that is the group he asked to see first.
ENGLISH_NEED_ORDER = ['English only', 'English + Other', 'Other only']


def english_requirement_of(row) -> str:
    """Which of the three language shapes this posting is -- the English column.

    Sina asked for the pairing to stop being deleted and then asked to be able to pick it
    out in the table: "میتونی یک ستون ها اضافه کنی که بشه انتخاب کرد فقط English و
    English + Other Language ... مثل فایل Excel". So the same reading that decides whether
    to delete also writes down WHAT it found, and the column is a classification like
    Seniority and Type -- it deletes nothing.

        'English only'     nothing asks for a second language. This is also the answer for a
                           posting that never mentions language at all, which is most of
                           them: an advert in English that makes no language demand has not
                           made one, and grouping it with the demands would be a guess.
        'English + Other'  English is named beside a language he lacks -- the shape he asked
                           to have back.
        'Other only'       a language he lacks, English nowhere beside it. These are what
                           requires_language_besides_english still deletes, so they appear
                           in the raw Bank and in the search table and never survive the
                           Filter. The column still has the label, because a value the table
                           cannot show is how a column starts lying.

    The last of those is kept in exact agreement with the rule by construction: the same
    patterns, the same three cancellations, the same "beside it" window. An invariant test
    asserts the two can never disagree, because two readings of one question drift.
    """
    text = f"{row.get('title') or ''} {row.get('description') or ''}"
    paired = False
    for pattern in (_LEVELLED_LANGUAGE_PATTERN, _CEFR_PATTERN, _SECOND_LANGUAGE_PATTERN):
        for hit in pattern.finditer(text):
            # Softened three ways, exactly as the rule softens it: "Englisch und idealerweise
            # Deutsch", "English or Russian", "German is a plus". A softened demand is not a
            # demand, so it is not a pairing either -- it is 'English only'.
            if (_LANGUAGE_IDEALLY.search(hit.group(0))
                    or _LANGUAGE_EITHER_OR.search(hit.group(0))
                    or _LANGUAGE_NICE_TO_HAVE.search(_clause_after(text, hit.end()))):
                continue
            if _names_english_beside(text, hit):
                paired = True
            else:
                # The rule returns True here and the Filter deletes the row, so this answer
                # has to come out the same way round or the column would contradict the Log.
                return 'Other only'
    return 'English + Other' if paired else 'English only'


def is_category_uncertain(row) -> bool:
    """True when categorize() had to fall back to the generic 'Full-Time' default because
    the listing is in a non-English language and neither its own words nor a structured
    employment_type field could confirm what it actually is. Used only during raw Search
    display, to push these listings to the end of the list: their real Type badge is only
    known once Filter translates them and recategorizes with English text.

    This asks category_from_words rather than matching keywords itself, and that matters --
    the question is exactly "did the category rules find anything", and two places answering
    it separately is how they drift apart. The rules now read German, Dutch, Polish, Italian
    and Spanish titles directly, so far fewer listings reach this at all: a "Praktikum" is
    recognised where it used to fall through to Full-Time.
    """
    if category_from_words(row):
        return False
    employment_type = str(row.get('employment_type') or '').strip()
    if employment_type and employment_type.lower() != 'nan':
        return False
    return detect_language(row) not in ('en', 'unknown')
