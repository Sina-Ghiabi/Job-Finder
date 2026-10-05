"""What a search ASKS: the words, the phrases and the passes -- never how it runs.

Split out of runner.py, which had grown to hold three unrelated jobs in one file: the
vocabulary here, the actor calls that spend money, and the orchestration that sequences them.
This half is pure: every function takes a title or a language and returns strings. Nothing in
it touches the network, the clock or the disk, which is why it can be read and changed
without any fear of what a search might do differently afterwards.

The measurements behind each list are kept with the list they justify.
"""
from __future__ import annotations

from ..geo import CITY_COUNTRY
from ..search_title import (DEFAULT_SEARCH_TITLE, field_form, quoted, role_form,
                            title_forms)


def job_keywords(title, also=None) -> str:
    """The broad job query: every form of the title, as exact phrases.

    'Data Engineering' -> '"Data Engineering" OR "Data Engineer"'

    `also` is the other names employers give the same work (see title_equivalents), each one
    added with its own twin form. The user asked for exactly this order -- [owner's note: first the raw results; then for Data Science also Data Scientist; for ML Engineer also ML Engineering] -- so the raw names come first and the twins
    after, which is the order `search_phrases` builds.

    Without `also` this is the query it has always been.
    """
    if not also:
        return ' OR '.join(quoted(title_forms(title)))
    from ..title_equivalents import filter_titles
    return ' OR '.join(quoted(_capped(filter_titles(title, also))))


# How many phrases one query may carry. A job board takes a query as a URL parameter and a
# long one is silently truncated or refused, which would cost the whole search rather than
# the last few titles -- so the phrases are capped here, where the reason is visible, rather
# than discovered as an empty result set. The equivalents are already capped at twelve, and
# each contributes two forms, so this only ever bites on the Level query below.
_MAX_QUERY_PHRASES = 40


def _capped(phrases: list) -> list:
    """The first _MAX_QUERY_PHRASES, in order, so what is dropped is the least important."""
    return list(phrases)[:_MAX_QUERY_PHRASES]


# How an English advert says a role is for a beginner. Attached to the ROLE form -- "Junior
# Data Engineer", never "Junior Data Engineering" -- which is why role_form exists.
_ENTRY_PREFIXES = ('Junior', 'Entry Level', 'Graduate', 'Associate')
_ENTRY_SUFFIXES = ('Trainee', 'Intern')


def entry_keywords(title, also=None) -> str:
    """The entry-level job query: the role form with each English beginner word.

    A SECOND job query, not a replacement, for the reason the precise internship query
    exists: the broad query fills LinkedIn's thousand places with senior roles and the junior
    ones never fit inside it. On the Austrian DevOps run this query alone added 245 listings
    the broad one never returned.

    `also` puts those same beginner words on every equivalent title -- "Junior ML Engineer",
    "Graduate AI Engineer", "Applied Scientist Intern". See level_keywords.
    """
    if not also:
        role = role_form(title)
        phrases = (['"%s %s"' % (word, role) for word in _ENTRY_PREFIXES]
                   + ['"%s %s"' % (role, word) for word in _ENTRY_SUFFIXES])
        return ' OR '.join(phrases)
    from ..title_equivalents import search_phrases
    ring3 = [phrase for phrase in
             search_phrases(title, also, (_ENTRY_PREFIXES, _ENTRY_SUFFIXES))
             if any(phrase.startswith(word + ' ') for word in _ENTRY_PREFIXES)
             or any(phrase.endswith(' ' + word) for word in _ENTRY_SUFFIXES)]
    return ' OR '.join(quoted(_capped(ring3)))


# ...and for the other job Levels. Junior's is entry_keywords above, exactly as it has always
# been -- The user called Junior complete. Each other Level asks the same question in its own
# words, as its own search vocabulary (the filters' profiles keep theirs; the two never
# share). Senior is Senior only, by the user's rule -- not Lead, Staff or Principal.
#
# Mid has almost no word of its own in a title: measured, 1% of titles carry one, and 57-63%
# carry no level word at all. So the Mid precise query is small, and most Mid roles come
# from the broad title query, with the Mid profile's filter deciding the level.
_LEVEL_PREFIXES = {
    'entry': ('Entry Level', 'Graduate', 'New Grad'),
    'junior': _ENTRY_PREFIXES,
    'mid': ('Mid-Level', 'Mid Level', 'Intermediate'),
    'senior': ('Senior', 'Sr.'),
}
_LEVEL_SUFFIXES = {
    'entry': ('Trainee',),
    'junior': _ENTRY_SUFFIXES,
    'mid': (),
    'senior': (),
}


def level_keywords(title, level, also=None) -> str:
    """The precise job query for a Level: the role form with that Level's English words.

    'junior' -- and anything that is not one of the four job Levels -- is entry_keywords,
    unchanged.

    `also` carries the Level's words onto every equivalent title too, which is the third ring
    The user asked for: [owner's note: for AI Engineer also search Junior AI Engineer and Junior AI Engineering]. This ring only matters for the SEARCH -- a job board matches the exact phrase, so
    "Junior AI Engineer" really does return listings "AI Engineer" does not, measured at 245
    of them on one real run. The filter needs none of it: its match is word by word, so
    "AI Engineer" already keeps a listing titled "Junior AI Engineer".
    """
    level = str(level or '').lower()
    if level not in _LEVEL_PREFIXES or level == 'junior':
        return entry_keywords(title, also)
    prefixes, suffixes = _LEVEL_PREFIXES[level], _LEVEL_SUFFIXES[level]
    if not also:
        role = role_form(title)
        phrases = (['"%s %s"' % (word, role) for word in prefixes]
                   + ['"%s %s"' % (role, word) for word in suffixes])
        return ' OR '.join(phrases)
    from ..title_equivalents import search_phrases
    ring3 = [phrase for phrase in search_phrases(title, also, (prefixes, suffixes))
             if any(phrase.startswith(word + ' ') for word in prefixes)
             or any(phrase.endswith(' ' + word) for word in suffixes)]
    return ' OR '.join(quoted(_capped(ring3)))


# What the default searches for. Kept as names because the Log, the tests and older callers
# refer to "the job query"; they now mean the query for the title in the box.
KEYWORDS = job_keywords(DEFAULT_SEARCH_TITLE)
ENTRY_KEYWORDS = entry_keywords(DEFAULT_SEARCH_TITLE)


# =========================================================================================
# THREE SEARCHES, RUN ONE AFTER ANOTHER
# =========================================================================================
#
# Until now there was one search, and its keywords are the ones above: job titles. The
# Thesis and Internship modules then sifted whatever that search happened to return. Audited
# against the German corpus, that meant **9 thesis titles in 4,812 listings** -- and the
# thesis module recognised all 9, so nothing was wrong with the module. Nothing had ever
# asked for a thesis. Not one of the words `Masterarbeit`, `Abschlussarbeit`, `thesis`,
# `Praktikum` or `Werkstudent` appears anywhere in a query this app sends.
#
# So: three searches, in the user's order -- Job finished and closed, then Internship, then
# Thesis -- all landing in one pool that the existing filters separate exactly as they do
# today.
#
# Why three separate searches rather than one wider one, which was the obvious idea:
# **Indeed and Glassdoor cap a single call at 1,000 results.** OR-ing thesis words into the
# job query would make all three kinds share those 1,000 places, so adding theses would cost
# jobs. Three calls means three ceilings. The split raises Job's own recall rather than
# spending it.
#
# THE SHAPE OF EACH QUERY, which was measured rather than assumed. Asking Indeed for
# `Praktikum OR Werkstudent OR Internship` returns any internship at all -- "Praktikum
# Nachhaltigkeit", "Praktikum Producing" -- because nothing in this app checks that a
# listing is about data or AI; the search keywords are the only field filter there is.
# Putting the two groups side by side, which both actors read as AND, fixes it:
#
#     (Praktikum OR Werkstudent) ("Data Science" OR "Machine Learning")
#       -> "Praktikum R&D Laser Application - Data Fusion"
#       -> "PRAKTIKANT / WERKSTUDENT AI, DATA ENGINEERING UND SCIENCE (M/W/D)"
#       -> "Internship and Masterthesis (m/f/d) in the Area of Large Language Models"
#
# Verified live against both actors before this was written.
# THE ROLE GROUP IS IN EVERY LANGUAGE, and that is not decoration. A first version of this
# carried English only, and measuring it against Indeed for Germany showed what that costs:
# of 200 internship results, 23 were named in German with English-only role words and **47**
# with the German ones added. Both runs hit the cap, so the real gap is wider still. These
# appear only with the German terms:
#
#     Werkstudent Künstliche Intelligenz – KI im Arbeitsalltag (m/w/d)
#     Praktikum - Künstliche Intelligenz (KI) in der Technischen Entwicklung
#
# A German employer writes "Künstliche Intelligenz", a Finn writes "Tekoäly", and neither
# says "Artificial Intelligence" anywhere on the page.
#
# THAT HALF IS NOW THE TITLE, FOR ALL THREE PASSES. The role group above was a hand-written
# data-science list in thirteen languages, kept for Thesis alone while Job and Internship moved
# to the title. The user then put Thesis on the title too ("Masterarbeit Data Engineering"), so
# the list is gone from here and kept out of the public repository. The kind words below
# -- Praktikum, Masterarbeit, Tesi di Laurea -- are the half that is translated, and they stay.

# The word a posting uses to say it is an internship, in the languages this app searches.
# German first and at length because German draws the sharpest distinctions -- Praktikum is
# a placement, Werkstudent is term-time work alongside a degree, and both are things the user
# would take.
_INTERNSHIP_GROUP = (
    '(Praktikum OR Praktikant OR Praktikantin OR Werkstudent OR Werkstudentin '
    'OR Pflichtpraktikum OR Internship OR Intern OR "Working Student" OR Trainee '
    'OR Stage OR Stagiair OR Stagiaire OR Tirocinio OR Stagista OR Practicas OR Becario '
    'OR Estagio OR Praktik OR Praktikplats OR Harjoittelu OR Praktyki '
    'OR "Industrial Placement" OR "Work Placement" OR "Placement Year" OR "Summer Internship" '
    'OR "Student Worker" OR Co-op OR Traineeship)')

# ...and the word it uses to offer a thesis. Master-level only is enforced later, by the
# Thesis module's own rules -- the search casts wider than the filter on purpose, because a
# posting that says only "Abschlussarbeit" does not say which degree until you read it.
_THESIS_GROUP = (
    '(Masterarbeit OR Master-Thesis OR Masterthesis OR "Master Thesis" OR Abschlussarbeit '
    'OR Diplomarbeit OR Studienarbeit OR Forschungsarbeit OR Thesis OR "Final Project" '
    'OR Afstudeeropdracht OR Afstudeerstage OR "Memoire de fin" OR "Tesi di Laurea" '
    'OR "Trabajo Fin de Master" OR "Examensarbete" OR "Masteroppgave" OR "Speciale" '
    'OR "Diplomityo" OR "Praca magisterska" OR "Master\'s Thesis" OR "MSc Thesis" '
    'OR "Master Thesis Project" OR "Thesis Project" OR "Degree Project" '
    'OR "Final Year Project" OR "Graduation Project" OR "Research Thesis" OR Dissertation '
    'OR "Mémoire de Master" OR "Tesi di Laurea Magistrale" OR Afstudeerproject)')

def _role_forms(title, also=None) -> list:
    """Every form of the title to ask for: as typed, its twin, and -- when `also` is given --
    every other name for the same work with its twin (see title_equivalents), capped."""
    if not also:
        return title_forms(title)
    from ..title_equivalents import filter_titles
    return _capped(filter_titles(title, also))


def internship_role_group(title, also=None) -> str:
    """The role half of the internship query: every form of the title, grouped.

    No "Junior" and no "Entry Level" here. An internship is entry-level by definition, and
    adding the word would only shrink what comes back.
    """
    return '(%s)' % ' OR '.join(quoted(_role_forms(title, also)))


def internship_keywords(title, also=None) -> str:
    """The broad internship query: the internship words beside the title, read as AND."""
    return '%s %s' % (_INTERNSHIP_GROUP, internship_role_group(title, also))


def thesis_keywords(title, also=None) -> str:
    """The broad thesis query: the thesis words beside the title, read as AND.

    Every form of the title, as for internships: an advert may say "Masterarbeit Data
    Engineering" or "Thesis: Data Engineer Tooling".
    """
    return '%s (%s)' % (_THESIS_GROUP, ' OR '.join(quoted(_role_forms(title, also))))


INTERNSHIP_KEYWORDS = internship_keywords(DEFAULT_SEARCH_TITLE)
THESIS_KEYWORDS = thesis_keywords(DEFAULT_SEARCH_TITLE)


# =========================================================================================
# THE SAME QUESTION ASKED TWICE: LOOSELY, AND EXACTLY
# =========================================================================================
#
# The query above puts a kind group beside a role group, which the actors read as AND. On a
# small result set that works perfectly -- the first twenty come back clean. At a thousand
# it does not, and the measurement is stark: of 1,000 internships Indeed returned for it,
# **699 were internships and only 273 were in the user's field.** Marketing, HR, shop
# photography, toolmaking. An actor that runs out of exact matches widens the question
# rather than returning fewer rows, and nothing downstream asks whether a listing is about
# data at all.
#
# So the same question is also asked exactly, as quoted phrases that weld a kind word to a
# role word. There is nothing in "Werkstudent Data Science" for an actor to loosen.
#
# MEASURED ON ALL THREE ACTORS, Germany, the same day:
#
#                 items   relevant   cost      against the broad query
#     Indeed         48      46      $0.001    +1%
#     Glassdoor      91      88      $0.001    +0%
#     LinkedIn    1,000     701      $1.948    +97%
#
# Two different answers, and worth keeping apart rather than averaging. Indeed and Glassdoor
# honour a quoted phrase: a handful of rows, 96% of them exactly right, for a tenth of a
# cent. LinkedIn ignores the quotes and fills its 1,000 either way -- but fills them BETTER,
# 701 relevant against 273. So on LinkedIn the precise query replaces the broad one at the
# same price; on the other two it is added for nothing.
#
# And they genuinely find different postings. Of the relevant listings each returned, 29 were
# found only by the precise query and 210 only by the broad one. The 29 are the most on-target
# titles in the whole run -- "Werkstudent Data Engineer", "Werkstudent Data Science",
# "Werkstudent KI-basierte Bordnetzentwicklung" -- and the broad query misses them because
# they do not fit inside its thousand.
# Built from the title rather than written out per field. The internship word stays in the
# local language -- a German advert says "Werkstudent", never "working student" -- and the
# title stays in English, because a job title in this field is not translated by anybody.
#
# Real examples of exactly this shape, found in the corpus without ever being asked for:
#     Praktikant:in (all genders) AI DevOps ab Oktober 2026
#     Werkstudent:in - Cloud & DevOps Engineer (Azure)
#     Werkstudent im Bereich IT und DevOps (m/w/d)
#
# English has its own shapes -- the internship word comes AFTER the title as often as before,
# "Data Engineering Intern" as often as "Working Student Data Engineer" -- so it gets both.
_ENGLISH_INTERNSHIP_BEFORE = ('Working Student', 'Internship')
_ENGLISH_INTERNSHIP_AFTER = ('Intern', 'Internship', 'Trainee')


def precise_internship_phrases(title, also=None) -> dict:
    """Every exact internship phrase for this title, by language code.

    Each language's own internship words are welded to each form of the title. A word that
    is itself two words ("Contrat de Professionnalisation") is left out: welded to a title
    it becomes a phrase no advert actually contains, and an exact phrase that matches
    nothing is a query slot spent for nothing.
    """
    forms = _role_forms(title, also)
    phrases = {'en': ['"%s %s"' % (word, form)
                      for form in forms for word in _ENGLISH_INTERNSHIP_BEFORE]
               + ['"%s %s"' % (form, word)
                  for form in forms for word in _ENGLISH_INTERNSHIP_AFTER]}
    for code, words in _LANGUAGE_INTERNSHIP_WORDS.items():
        single = [w for w in words if ' ' not in w.strip('"')]
        phrases[code] = ['"%s %s"' % (word.strip('"'), form)
                         for word in single for form in forms]
    return phrases


# Thesis the same way, and for the same reason. English says it both ways round -- "Master
# Thesis Data Engineering" and "Data Engineering Master Thesis" -- so it gets both; every
# other language puts its thesis word first.
_ENGLISH_THESIS_BEFORE = ('Master Thesis', 'Thesis')
_ENGLISH_THESIS_AFTER = ('Thesis', 'Master Thesis')


def precise_thesis_phrases(title, also=None) -> dict:
    """Every exact thesis phrase for this title, by language code.

    Each language's own single-word thesis words -- Masterarbeit, Examensarbete, Tesi --
    welded to each form of the title. Two-word ones ("Tesi di Laurea") are left out, for the
    reason given on precise_internship_phrases.
    """
    forms = _role_forms(title, also)
    phrases = {'en': ['"%s %s"' % (word, form)
                      for word in _ENGLISH_THESIS_BEFORE for form in forms]
               + ['"%s %s"' % (form, word)
                  for word in _ENGLISH_THESIS_AFTER for form in forms]}
    for code, words in _LANGUAGE_THESIS_WORDS.items():
        single = [w for w in words if ' ' not in w.strip('"')]
        phrases[code] = ['"%s %s"' % (word.strip('"'), form)
                         for word in single for form in forms]
    return phrases

# Nowhere, in the end -- and the empty tuple is the finding rather than an oversight.
#
# LinkedIn ignores quoted phrases and fills its 1,000 rows whatever it is asked, so a second
# call there is a second $2 for the same ceiling. That looked like a clear case for replacing
# the broad query rather than adding to it, and it was written that way. Then it was
# measured, on Germany, the same day:
#
#     precise   1,000 returned, 707 relevant, $1.93
#     broad     1,000 returned, 582 relevant, $2.00
#
#     only precise 235      only broad 110      both 472
#
# A third of what each returns, the other never sees. The 110 the broad query alone finds are
# real and wanted -- "Deutsche Bank Internship in Group Strategic Analytics 2027", "Analytics
# & Insights Internship", "Internship / Thesis - Sensory Analytics" -- and dropping the broad
# query to save $2 would have cost every one of them.
#
# The user's rule settled it before the number arrived: if the two find the same jobs, keep one;
# if they find different jobs and both work, keep both. They find different jobs.
_PRECISE_REPLACES_BROAD: tuple = ()


# =========================================================================================
# ONCE IN ENGLISH, ONCE IN THE COUNTRY'S OWN LANGUAGE
# =========================================================================================
#
# The user's instruction after seeing I-3: [owner's note: search once in the country's own language and once in English]. Two searches per kind rather than one query carrying both, and the reason is
# the same one that made three passes right in the first place -- the 1,000-result ceiling is
# **per call**. A single query OR-ing English and German words makes the two share those
# 1,000 places; two calls give each its own.
#
# It also sharpens what is asked. German words sent to a Swedish search are noise that costs
# result slots, and the local query for Sweden should say "Maskininlärning", not
# "Künstliche Intelligenz". So the words are chosen per country, from the country's own
# languages -- which is why this is a table per language rather than one long OR-list.
#
# A country whose language is English (Ireland, the UK) has no local pass: it would be the
# same search run twice. COUNTRY_LANGUAGES already lists every country's languages with
# English last, so the local pass is simply "every language except en".
#
# This table is the SEARCH's own vocabulary and shares nothing with the filters' 13 language
# dictionaries, deliberately: those decide whether a listing survives, this decides what is
# asked for, and the two failing together would be much harder to see than either failing
# alone.
# --- the title, per language --------------------------------------------------------
#
# The same in every language, and that is the finding rather than a shortcut: a job title in
# this field is not translated by anybody (see "THE FIELD" at the top of this file). So there
# is no table here any more -- the local pass sends the title's own forms, and what makes it
# a different question from the English pass is the local word for a beginner or for an
# internship beside it.


# --- how each language says "beginner" -------------------------------------------------
#
# This is the half that IS translated, and the corpus proves it pays: a real German advert
# reads "JUNIOR CLOUD ENGINEER (M/W/D) — ABSOLVENT:INNEN WILLKOMMEN!". `Absolvent` and
# `Berufseinsteiger` are words no English query will ever match, on postings that are exactly
# what the user can be hired into.
#
# `Junior` itself is in every list on purpose: it is a loanword everywhere and an advert that
# uses it in an otherwise-German title would be missed by a list of German words only.
_LANGUAGE_ENTRY_WORDS = {
    'de': ['Junior', 'Berufseinsteiger', 'Absolvent', 'Absolventin', 'Einsteiger',
           'Nachwuchs', 'Trainee', 'Einstiegsposition'],
    'nl': ['Junior', 'Starter', 'Startersfunctie', 'Afgestudeerde', 'Trainee'],
    'fr': ['Junior', 'Débutant', '"Jeune Diplômé"', '"Premier Emploi"', 'Alternance'],
    'it': ['Junior', 'Neolaureato', 'Neolaureata', '"Prima Esperienza"', 'Apprendistato'],
    'es': ['Junior', '"Recién Titulado"', '"Recién Graduado"', '"Primer Empleo"', 'Becario'],
    'pt': ['Junior', 'Júnior', '"Recém-Licenciado"', '"Primeiro Emprego"'],
    'sv': ['Junior', 'Nyexaminerad', 'Nyutexaminerad', 'Traineeprogram'],
    'no': ['Junior', 'Nyutdannet', 'Trainee'],
    'da': ['Junior', 'Nyuddannet', 'Graduate', 'Trainee'],
    'fi': ['Junior', 'Vastavalmistunut', 'Harjoittelija', 'Trainee'],
    'pl': ['Junior', 'Absolwent', '"Młodszy Specjalista"', 'Stażysta'],
    'lb': ['Junior', 'Absolvent', 'Debutant'],
}

# --- and each other job Level, the same way ------------------------------------------------
#
# Junior's table is _LANGUAGE_ENTRY_WORDS above, untouched. The others follow its pattern:
# the local word for that Level, and the English loanword too wherever an advert in that
# language uses it -- "Senior" is written in German, Italian and Dutch titles exactly as in
# English, the way "Junior" is.
#
# Entry is Junior's list without "Junior" itself: the Entry profile's filter drops a posting
# titled Junior, so asking for them would spend result slots on listings it removes.
_LANGUAGE_LEVEL_WORDS = {
    'junior': _LANGUAGE_ENTRY_WORDS,
    'entry': {code: [word for word in words if word not in ('Junior', 'Júnior')]
              for code, words in _LANGUAGE_ENTRY_WORDS.items()},
    # The words a posting in each language uses for someone between junior and senior. Only
    # four languages have one in common use; elsewhere the English loanword is what appears.
    'mid': {
        'de': ['Mid-Level'],
        'nl': ['Medior', 'Mid-Level'],
        'fr': ['Confirmé', 'Confirmée', 'Mid-Level'],
        'it': ['Middle', 'Mid-Level'],
        'es': ['"Semi Senior"', 'Semisenior', 'Mid-Level'],
        'pt': ['Pleno', 'Mid-Level'],
        'sv': ['Mid-Level'],
        'no': ['Mid-Level'],
        'da': ['Mid-Level'],
        'fi': ['Mid-Level'],
        'pl': ['Regular', 'Mid-Level'],
        'lb': ['Mid-Level'],
    },
    'senior': {
        'de': ['Senior'],
        'nl': ['Senior'],
        'fr': ['Senior', 'Sénior'],
        'it': ['Senior'],
        'es': ['Senior', 'Sénior'],
        'pt': ['Senior', 'Sênior'],
        'sv': ['Senior'],
        'no': ['Senior'],
        'da': ['Senior'],
        'fi': ['Senior'],
        'pl': ['Senior', 'Starszy'],
        'lb': ['Senior'],
    },
}

# EVERY WORD A POSTING USES FOR AN INTERNSHIP OR A THESIS, PER LANGUAGE.
#
# [owner's note: the dictionaries must use every equivalent word for Internship in each chosen country, and the same for Thesis]. Each list below is the language's own words, completed
# against what the Filter's two modules recognise (thesis/words.py, internship/words.py) -- the
# rule being that a word the search sends must be one the module keeps, or it is fetched and then
# thrown away. tests/t7 asserts that for every word here, for every country that speaks it.
#
# NOT here, on purpose: 'Beca' ("because" is a prefix match for the recogniser and a grant is not
# an internship), 'LIA' ("liability"), a bare 'Placement' ("Job Placement Specialist"), and
# Bachelor words -- the Thesis module is Master-level only and would drop every one.
_LANGUAGE_INTERNSHIP_WORDS = {
    'de': ['Praktikum', 'Praktikant', 'Praktikantin', 'Werkstudent', 'Werkstudentin',
           'Pflichtpraktikum', 'Praxissemester', 'Abschlusspraktikum', 'Ferialpraktikum',
           'Praxisphase', '"Freiwilliges Praktikum"', 'Trainee'],
    'nl': ['Stage', 'Stagiair', 'Stagiaire', 'Stageplaats', 'Stageplek', 'Stageopdracht',
           'Meewerkstage', 'Werkstudent', 'Studentmedewerker', 'Afstudeerstage', 'Traineeship',
           'Trainee'],
    'fr': ['Stage', 'Stagiaire', '"Contrat de Professionnalisation"', 'Alternance', 'Alternant',
           'Apprentissage', 'Apprenti', '"Contrat d\'Apprentissage"', '"Stage de Césure"'],
    'it': ['Tirocinio', 'Tirocinante', 'Stagista', 'Stage', 'Apprendistato', 'Apprendista',
           'Praticante'],
    'es': ['Prácticas', 'Practicante', 'Becario', 'Becaria', '"Prácticas Profesionales"'],
    'pt': ['Estágio', 'Estagiário', 'Estagiária', 'Trainee'],
    'sv': ['Praktik', 'Praktikplats', 'Praktikantplats', 'Praktikant', 'Trainee',
           'Traineeprogram'],
    'no': ['Praktikant', 'Praktikplass', 'Praksisplass', 'Internship', 'Trainee',
           'Traineeprogram', 'Studentjobb'],
    'da': ['Praktik', 'Praktikant', 'Praktikplads', 'Praktikophold', 'Praktikforløb',
           'Studiejob', 'Studenterjob', 'Studentermedhjælper', 'Trainee'],
    'fi': ['Harjoittelu', 'Harjoittelija', 'Työharjoittelu', 'Harjoittelupaikka',
           'Kesäharjoittelu', 'Trainee', 'Traineeohjelma'],
    'pl': ['Praktyki', 'Praktykant', 'Staż', 'Stażysta', '"Praktyki Studenckie"'],
    'lb': ['Stage', 'Stagiaire', 'Praktikum'],
}

_LANGUAGE_THESIS_WORDS = {
    'de': ['Masterarbeit', 'Abschlussarbeit', 'Diplomarbeit', 'Studienarbeit',
           'Forschungsarbeit', 'Masterthesis', 'Thesis'],
    'nl': ['Afstudeeropdracht', 'Afstudeerscriptie', 'Masterscriptie', 'Scriptie',
           'Afstudeerproject', 'Afstudeerplek', 'Afstudeeronderzoek', 'Afstudeerstage',
           'Thesis'],
    'fr': ['"Mémoire de Fin d\'Études"', 'Mémoire', '"Mémoire de Master"',
           '"Projet de Fin d\'Études"', 'PFE', '"Stage de Fin d\'Études"', '"Stage de Master"'],
    'it': ['"Tesi di Laurea"', '"Tesi di Laurea Magistrale"', 'Tesi', '"Tesi Magistrale"',
           '"Tesi Sperimentale"', 'Tesista', '"Progetto di Tesi"', '"Tirocinio di Tesi"'],
    'es': ['"Trabajo Fin de Máster"', '"Trabajo de Fin de Máster"', 'TFM',
           '"Trabajo de Fin de Grado"', 'Tesis', 'Tesina', '"Proyecto Fin de Carrera"',
           '"Proyecto de Fin de Máster"'],
    'pt': ['"Dissertação de Mestrado"', 'Dissertação', '"Tese de Mestrado"', 'Tese',
           '"Projeto de Fim de Curso"', '"Trabalho Final de Mestrado"'],
    'sv': ['Examensarbete', 'Exjobb', 'Examensjobb', 'Masteruppsats', 'Magisteruppsats',
           '"Examensarbete Master"'],
    'no': ['Masteroppgave', 'Masteravhandling', 'Masterprosjekt', 'Hovedoppgave'],
    'da': ['Speciale', 'Kandidatspeciale', 'Specialeprojekt', 'Masterprojekt',
           'Afgangsprojekt'],
    'fi': ['Diplomityö', 'Pro-Gradu', 'Gradu', 'Opinnäytetyö', 'Lopputyö'],
    'pl': ['"Praca Magisterska"', '"Praca Dyplomowa"'],
    'lb': ['Masterarbeit', 'Ofschlossaarbecht', '"Mémoire de Master"'],
}

_KIND_WORDS = {'internship': _LANGUAGE_INTERNSHIP_WORDS, 'thesis': _LANGUAGE_THESIS_WORDS}


# =========================================================================================
# THE MAJOR CITY OF EACH COUNTRY -- a lookup, not a search plan
# =========================================================================================
#
# This table used to drive an extra LinkedIn query per selected country. LinkedIn caps one
# search at 1,000 jobs, and a Berlin-only run measured 120 jobs of which 48 were not in the
# 1,000 the Germany-wide run had already paid for -- so the app asked for each country's
# strongest city as well.
#
# The user ended that, and his reason outranks the measurement: [owner's note: only the places that were chosen are wanted, and no other city may be added on the app's own judgement]. A search asks for the places he picked and nothing else. If he wants Berlin he
# picks Berlin -- and then Berlin is searched once, not twice.
#
# The table stays because it still answers a different question: which country a city
# belongs to. CITY_COUNTRY only knows the cities offered in the wizard, and a row whose
# country cannot be resolved loses its country field and its local-language pass.
#
# The ranking inside it is the user's: the best cities of each country by income and by where
# data and AI work actually is -- not by population. Duisburg is bigger than Karlsruhe and
# has a fraction of the work he looks for.
MAJOR_CITIES = {
    # Seven, on the user's instruction: the deepest market of the eighteen.
    # Munich (highest incomes, Google/Apple/BMW/Siemens), Berlin (Europe's largest startup
    # scene and the most English-speaking workplaces), Frankfurt (European finance, DE-CIX),
    # Hamburg (Airbus, media, logistics), Stuttgart (Mercedes/Porsche/Bosch, industrial
    # data), then the Rhine pair -- Cologne and Düsseldorf are one labour market between
    # them and both are large enough to hold their own ceiling.
    # Berlin first, ahead of Munich, and only because it is the one with a measurement:
    # a Berlin-only search returned 120 jobs of which 48 were not in the 1,000 the
    # country-wide search had already produced. Munich is the stronger market on every
    # other reading -- higher incomes, Google/Apple/BMW/Siemens -- and when
    # LINKEDIN_MAX_SPLIT_CITIES is raised above one it is the very next city asked. With
    # only one slot, a measured 40% beats a reasoned first place.
    'Germany': ['Berlin', 'Munich', 'Frankfurt', 'Hamburg', 'Stuttgart', 'Cologne',
                'Düsseldorf'],
    'Italy': ['Milan', 'Rome', 'Turin', 'Bologna', 'Padua'],
    'Denmark': ['Copenhagen', 'Aarhus', 'Odense', 'Aalborg', 'Lyngby'],
    'Finland': ['Helsinki', 'Espoo', 'Tampere', 'Oulu', 'Turku'],
    'Norway': ['Oslo', 'Bergen', 'Trondheim', 'Stavanger', 'Tromsø'],
    'Sweden': ['Stockholm', 'Gothenburg', 'Malmö', 'Uppsala', 'Linköping'],
    'Austria': ['Vienna', 'Graz', 'Linz', 'Salzburg', 'Innsbruck'],
    'Belgium': ['Brussels', 'Antwerp', 'Ghent', 'Leuven', 'Liège'],
    'France': ['Paris', 'Lyon', 'Toulouse', 'Grenoble', 'Nantes'],
    'Netherlands': ['Amsterdam', 'Rotterdam', 'Utrecht', 'Eindhoven', 'The Hague'],
    # A country small enough that the capital is most of the market; the others are the
    # cross-border commuter towns where the jobs are actually advertised.
    'Luxembourg': ['Luxembourg City', 'Esch-sur-Alzette', 'Belval', 'Kirchberg',
                   'Differdange'],
    'Switzerland': ['Zurich', 'Geneva', 'Basel', 'Lausanne', 'Zug'],
    'Portugal': ['Lisbon', 'Porto', 'Braga', 'Coimbra', 'Aveiro'],
    'Spain': ['Madrid', 'Barcelona', 'Valencia', 'Bilbao', 'Málaga'],
    'United Kingdom': ['London', 'Cambridge', 'Manchester', 'Edinburgh', 'Bristol'],
    'United States': ['San Francisco', 'New York', 'Seattle', 'Boston', 'Austin'],
    'Canada': ['Toronto', 'Vancouver', 'Montreal', 'Ottawa', 'Waterloo'],
    'Australia': ['Sydney', 'Melbourne', 'Brisbane', 'Canberra', 'Perth'],
}


# Which country each of those cities belongs to. Needed because CITY_COUNTRY only knows the
# seven cities the user can pick from the wizard, and a row whose country cannot be resolved is
# a row that loses its country field AND its local-language pass -- the pass would find no
# languages for "" and skip itself silently, which is the worst kind of bug: a whole search
# that does nothing and says nothing.
_CITY_COUNTRY_FALLBACK = {city: country
                       for country, cities in MAJOR_CITIES.items()
                       for city in cities}


def country_of_location(loc_type: str, location: str) -> str | None:
    """The country a plan item belongs to, however the location got into the plan."""
    if loc_type == 'country':
        return location
    return CITY_COUNTRY.get(location) or _CITY_COUNTRY_FALLBACK.get(location)


def local_languages_for(country: str) -> list:
    """The country's own languages, English excluded -- what a local-language pass asks in."""
    from ..country_rules import COUNTRY_LANGUAGES
    return [code for code in COUNTRY_LANGUAGES.get(country, ()) if code != 'en']


def keywords_for(kind: str, country: str | None, language: str,
                 shape: str = 'broad', title=None, level=None, also=None) -> str | None:
    """One pass's query, or None when there is nothing to ask.

    `title` is the job title the user typed; every query is built from it, Thesis included, and a
    missing one falls back to DEFAULT_SEARCH_TITLE.

    `language` is 'en' for the English pass and 'local' for the country's own. A local pass
    returns None where the country speaks English, or where a language has no words for this
    kind -- and a pass with no query is skipped rather than sent empty.

    `shape` is 'broad' (the two groups side by side) or 'precise' (exact phrases). For
    internships and theses, precise welds an internship or thesis word to the title. For
    jobs, precise is the query for the Level.

    `level` is the job Level chosen in Search -- entry, junior, mid or senior. Anything else,
    nothing included, is Junior, which is what the job pass has always searched.

    `also` is the other names employers give this job (see title_equivalents). It widens every
    pass: the job shapes, and the internship and thesis queries, whose title group and exact
    phrases carry each other name as well.
    """
    level = str(level or '').lower()
    if level not in _LANGUAGE_LEVEL_WORDS:
        level = 'junior'
    if shape == 'precise':
        if kind == 'job':
            # The job pass's precise shape is the Level's own: a broad query fills
            # LinkedIn's thousand places with whatever is most common, and the roles at the
            # chosen Level never fit. English only -- the local pass carries the Level in the
            # country's own words, and that is the whole reason that pass exists, since the
            # title itself does not translate.
            return level_keywords(title, level, also) if language == 'en' else None
        codes = ['en'] if language == 'en' else local_languages_for(country or '')
        table = (precise_internship_phrases(title, also) if kind == 'internship'
                 else precise_thesis_phrases(title, also))
        phrases: list = []
        for code in codes:
            phrases.extend(table.get(code, ()))
        unique = list(dict.fromkeys(phrases))
        # Capped only when other names were added: a long query is silently truncated or refused.
        return ' OR '.join(_capped(unique) if also else unique) if unique else None

    if language == 'en':
        if kind == 'job':
            return job_keywords(title, also)
        return (internship_keywords(title, also) if kind == 'internship'
                else thesis_keywords(title, also))

    codes = local_languages_for(country or '')
    if not codes:
        return None
    kind_words: list = []
    entry_words: list = []
    for code in codes:
        if kind == 'job':
            entry_words.extend(_LANGUAGE_LEVEL_WORDS[level].get(code, ()))
        else:
            kind_words.extend(_KIND_WORDS[kind].get(code, ()))
    role_clause = '(%s)' % ' OR '.join(quoted(_role_forms(title, also)))
    if kind == 'job':
        # Not the English query translated -- it cannot be, since the title is not
        # translated by anybody, and sending it twice would be one wasted call per country.
        # So it asks the one thing English cannot: the title beside the local word for a
        # beginner. `("Data Engineer") (Junior OR Berufseinsteiger OR Absolvent ...)` finds
        # "JUNIOR CLOUD ENGINEER (M/W/D) - ABSOLVENT:INNEN WILLKOMMEN!", which no English
        # query will ever match.
        if not entry_words:
            return None
        return '%s (%s)' % (role_clause, ' OR '.join(dict.fromkeys(entry_words)))
    if not kind_words:
        return None
    return '(%s) %s' % (' OR '.join(dict.fromkeys(kind_words)), role_clause)


# Google and the direct sources take a handful of plain phrases rather than one boolean
# query -- Google's queries also carry site: clauses and run into a ~32-word limit.
#
# The internship terms used to be the internship words ALONE: "Werkstudent", "Praktikum",
# "Internship", "Working Student", with no field at all. So Google's internship stage asked
# for every internship in every subject, and the field filter had to throw nearly all of it
# away afterwards. Each is now welded to the title.
_GOOGLE_INTERNSHIP_WORDS = ('Werkstudent', 'Praktikum', 'Internship', 'Working Student')


def google_job_terms(title) -> list:
    """What Google is asked for on the job pass: each form of the title."""
    return quoted(title_forms(title))


def google_internship_terms(title) -> list:
    """What Google is asked for on the internship pass: an internship word with the title."""
    role = role_form(title)
    return ['"%s %s"' % (word, role) for word in _GOOGLE_INTERNSHIP_WORDS]


def direct_job_terms(title) -> list:
    """What the direct APIs and sites are asked for on the job pass: each form, unquoted,
    because those sources take a plain phrase and several treat a quote as a character."""
    return list(title_forms(title))


def direct_internship_terms(title) -> list:
    """What the direct sources are asked for on the internship pass."""
    role = role_form(title)
    return ['Praktikum %s' % role, 'Werkstudent %s' % role, '%s Internship' % role,
            'Working Student %s' % role]


# The thesis terms used to be the thesis words alone -- "Masterarbeit", "Thesis" -- which
# asked Google for every thesis in every subject. Welded to the FIELD form of the title,
# because a thesis is about a subject: "Masterarbeit Data Engineering".
_GOOGLE_THESIS_WORDS = ('Masterarbeit', 'Master Thesis', 'Abschlussarbeit', 'Thesis')


def google_thesis_terms(title) -> list:
    """What Google is asked for on the thesis pass: a thesis word with the title's subject."""
    subject = field_form(title)
    return ['"%s %s"' % (word, subject) for word in _GOOGLE_THESIS_WORDS]


def direct_thesis_terms(title) -> list:
    """What the direct sources are asked for on the thesis pass. Four, like the other two
    passes -- these sources are called once per term."""
    subject = field_form(title)
    return ['Masterarbeit %s' % subject, 'Abschlussarbeit %s' % subject,
            'Master Thesis %s' % subject, 'Thesis %s' % subject]


GOOGLE_INTERNSHIP_TERMS = google_internship_terms(DEFAULT_SEARCH_TITLE)
GOOGLE_THESIS_TERMS = google_thesis_terms(DEFAULT_SEARCH_TITLE)


# The passes, in the order the user asked for them: each one finished and closed before the next
# begins. `key` is what the wizard's checkboxes send back.
#
# Every pass's terms are built from the title at the moment a search starts -- see
# terms_for_pass -- so what is stored here is only the default's.
SEARCH_PASSES = (
    {'key': 'job', 'label': 'Jobs', 'keywords': KEYWORDS,
     'google_terms': google_job_terms(DEFAULT_SEARCH_TITLE),
     'direct_terms': direct_job_terms(DEFAULT_SEARCH_TITLE)},
    {'key': 'internship', 'label': 'Internships', 'keywords': INTERNSHIP_KEYWORDS,
     'google_terms': GOOGLE_INTERNSHIP_TERMS,
     'direct_terms': direct_internship_terms(DEFAULT_SEARCH_TITLE)},
    {'key': 'thesis', 'label': 'Theses', 'keywords': THESIS_KEYWORDS,
     'google_terms': GOOGLE_THESIS_TERMS,
     'direct_terms': direct_thesis_terms(DEFAULT_SEARCH_TITLE)},
)

# What run_search does when nothing is asked for: the job pass, in English, once -- which is
# exactly what it did before any of this was written. Every existing caller and every test
# therefore behaves identically, and the new behaviour only ever arrives because the wizard
# asked for it by name.
#
# The languages are a separate default for the same reason. An earlier version derived them
# instead, and it quietly broke the guarantee: with nothing selected it ran the job pass
# twice, once in English and once in Italian, and six plan tests caught it. Deriving a
# default from another default is how a promise like "the Job path is untouched" stops being
# true without anyone editing the Job path.
def terms_for_pass(key: str, title) -> tuple:
    """(google_terms, direct_terms) for one pass and one title.

    All three are built from the title.
    """
    if key == 'job':
        return google_job_terms(title), direct_job_terms(title)
    if key == 'internship':
        return google_internship_terms(title), direct_internship_terms(title)
    if key == 'thesis':
        return google_thesis_terms(title), direct_thesis_terms(title)
    entry = next(p for p in SEARCH_PASSES if p['key'] == key)
    return entry['google_terms'], entry['direct_terms']


