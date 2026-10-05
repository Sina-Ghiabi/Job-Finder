# -*- coding: utf-8 -*-
"""The Thesis module's own rules. Imports nothing from the Job or Internship modules.

One of three parallel modules, per the user's design. When Filter runs, all three read the same
listings at the same time and none of them can affect another -- each is handed its own copy
of the rows, so even the mutation the salaried module does during translation is invisible
here.

SINA'S RULES FOR A THESIS, IN ORDER

  1. It has to be a thesis, and that is read from the TITLE. An advert offering one says so
     there; one that merely mentions the word is a salaried job talking about something
     else.
  2. A PhD is out. [owner's note: a thesis written for a PhD is of no use and must be dropped] -- a doctorate is a four-year research post, not something he writes during his
     M.Sc.
  3. Milan or Turin: anything goes -- on-site, hybrid, remote. Anywhere else: remote only.
  4. Unpaid is out.
  5. A language besides English is out.

AND THE RULE THAT IS NOT THE SALARIED ONE

Silence is not a rejection here. Measured over both real corpora, 38% of thesis and
internship adverts never mention remote work at all -- nobody writes "on-site" on a thesis
advert because everyone knows a thesis happens at the institute. The salaried Work Location
rule reads that silence as an office and drops it, which is right for a Dutch job advert and
wrong for this. Two in five were being deleted for being ordinary.
"""
from __future__ import annotations

import re

# This module's OWN copy of the title check. The user's rule: the three modules share nothing,
# not even a question they happen to ask identically. See field_words.py.
from .field_words import ALSO_ROW_KEY, row_is_in_field
from . import words
from ..search_title import (LEVEL_ROW_KEY, ROW_KEY as TITLE_ROW_KEY, WORK_MODE_ROW_KEY,
                            clean_title, clean_work_mode, is_any_workplace, is_not_remote)



# Where the untranslated text is kept. The salaried module writes these keys during
# translation; reading them is reading the listing, not sharing a rule. This module names
# them itself so it keeps working whatever that module renames.
ORIGINAL_TITLE_KEY = '_original_title'
ORIGINAL_DESCRIPTION_KEY = '_original_description'

# An aggregate or index page, not a vacancy. "Red Bull Internship Jobs | aktuell 5 offen |
# karriere.at" is a search-results page a crawler picked up, and it reached the survivors on
# a real Austrian run.
_INDEX_PAGE_PATTERN = re.compile(
    r'\|\s*aktuell\s+\d+|\b\d+\s+(?:offene?n?\s+)?(?:jobs?|stellen|vacatures|offerte)\b'
    r'|\bjobs?\s*\|\s*|\ball\s+(?:jobs|vacancies)\b|\bjob\s+search\b|\bsuchergebnisse\b',
    re.IGNORECASE)


def title_text(row) -> str:
    """The title, as the board wrote it and as translated, lowercased and padded.

    The trailing space matters: a title ENDING in a vocabulary word has no space after it,
    and several patterns need one to avoid firing inside a longer word.
    """
    parts = [row.get('title'), row.get(ORIGINAL_TITLE_KEY)]
    return ' '.join(str(part) for part in parts if part).lower() + ' '


def full_text(row) -> str:
    """Everything worth reading: the listing as it arrived AND as translated.

    Both, because the evidence can be in either -- a Dutch advert saying "thuiswerken" loses
    that word the moment it is translated, and an English phrase on the same page is only
    there after.
    """
    parts = [row.get('title'), row.get('description'), row.get('location'),
             row.get(ORIGINAL_TITLE_KEY), row.get(ORIGINAL_DESCRIPTION_KEY)]
    return ' '.join(str(part) for part in parts if part).lower()


def _hit(section: str, row, text: str) -> str:
    """The vocabulary term from `section` found in `text`, or ''."""
    found = words.pattern_for(section, row.get('country'), row.get('location')).search(text)
    return found.group(0) if found else ''


def is_thesis(row) -> bool:
    """True when the TITLE offers a thesis.

    Read from the title alone, and that is what makes it reliable. Every false positive
    measured over 5,468 real listings came from a body -- "Internationale Projektarbeit
    möglich" is a perk, "Positionsebene Berufseinstieg" is a metadata field.
    """
    return bool(_hit('thesis', row, title_text(row)))


def is_phd(row) -> bool:
    """True when the title says this thesis is a doctorate.

    Read from the title for a reason: a Master's thesis advert whose body says "you will
    work alongside our PhD students" is still a Master's thesis. And because the listing is
    already known to be a thesis by the time this is asked, the word does not have to prove
    anything -- on a thesis advert "PhD" names whose thesis it is.
    """
    return bool(_hit('phd', row, title_text(row)))


def is_bachelor_only(row) -> bool:
    """True when this thesis is for a bachelor student and not also for a master's one.

    The user's rule: [owner's note: bring only Master Thesis listings]. He is an M.Sc. student with
    his B.Sc. already finished, so a thesis written for someone
    currently enrolled in a bachelor's programme is not one he can take. The Infineon
    "Bachelor Thesis - Artificial Intelligence in Microcontroller" reached a real final list
    at 72%, and its requirements say "Education: Pursuing a Bachelor's degree (at least in
    the 5th semester)".

    The "and not also" half is the part that matters. Plenty of adverts are open to either --
    "Bachelor or Master thesis", "Bachelor-/Masterarbeit" -- and those are his to take. So a
    bachelor word only disqualifies a listing that carries no master word alongside it.

    Read from the title and the body both, because the level is as often in the requirements
    as in the heading: the Infineon advert says "Bachelor Thesis" in its title, but an advert
    titled only "Abschlussarbeit" says which it is further down.
    """
    text = full_text(row)
    return bool(_hit('bachelor', row, text)) and not _hit('master', row, text)


def passes_location_rule(row) -> bool:
    """Where a thesis may be. The user's rule, and not the salaried one.

    Milan or Turin -> anything. Anywhere else -> it has to be remote, OR it has to say
    nothing at all. Silence survives here; see the module docstring for the 38%.

    For a Not Remote search the same words are read and the other answer kept: a denial of
    remote work or an on-site/hybrid term keeps it, a remote term with neither drops it, and
    silence still survives. The Milan/Turin exception is a Remote-search question and does
    not apply.
    """
    text = full_text(row)
    if is_any_workplace(row):
        return True
    if is_not_remote(row):
        if _hit('not_remote', row, text) or _hit('on_site', row, text):
            return True
        return not _hit('remote', row, text)
    if _hit('not_remote', row, text):
        return False
    if _hit('remote', row, text):
        return True
    if _hit('on_site', row, text):
        return False
    return True          # says nothing about where -- kept


def survives(row) -> tuple:
    """(survives, reason) for one listing, in the user's order. Cheapest and surest first."""
    if not is_thesis(row):
        return False, 'not a thesis'
    if _INDEX_PAGE_PATTERN.search(str(row.get('title') or '')):
        return False, 'a listings page, not a vacancy'
    # Does it name the job in the Search box? For a thesis the title OR the description may,
    # because a thesis title names a topic rather than a job -- the title alone kept none of
    # 334 real German theses for "Data Science". See field_words.py for the measurement.
    if not row_is_in_field(row):
        return False, 'never names %s' % clean_title(row.get(TITLE_ROW_KEY))
    if is_phd(row):
        return False, 'a PhD, not a thesis'
    # The user wants master's theses only. Checked right after the PhD rule, since the two are
    # the same question asked from either side: this thesis has to be at his level.
    if is_bachelor_only(row):
        return False, 'a bachelor thesis, not a master one'
    if not passes_location_rule(row):
        # Mode-aware, for the same reason as the Internship module: in a Not Remote search
        # this removes remote work, and saying "cannot be done from Turin" there reports the
        # opposite of what the rule did.
        return False, ('remote work, which a Not Remote search excludes'
                       if is_not_remote(row) else 'cannot be done from Turin')
    text = full_text(row)
    if _hit('unpaid', row, text):
        return False, 'unpaid'
    if _hit('other_language_required', row, text):
        return False, 'needs a language besides English'
    # Last, because it reads the whole posting and every cheaper rule has had its turn.
    if silent_about_english(row):
        return False, 'written in another language, never mentions English'
    return True, ''


# ---------------------------------------------------------------------------------------
# Is this readable at all?
# ---------------------------------------------------------------------------------------

# The user's rule, and his reasoning: a Dutch employer who writes two thousand characters of
# Dutch and never once mentions English almost certainly wants Dutch. The Job module has
# carried it for a long time; these two did not, and a real run ended with a Randstad
# traineeship written entirely in Dutch on the list.
#
# High-frequency English words, counted as a share of all words. Measured over the real
# Netherlands and Austria corpora, on the {N} recognised listings with a usable description:
#
#     English postings      min 12.4%, median 17.2%, max 23.5%
#     everything else       median 0.3%, three-quarters under 0.5%, max 14.3%
#
# 8% sits in the empty middle. At that cut not one of the 128 English postings is mistaken
# for foreign -- which is the direction that matters, since that mistake DELETES something
# The user can read -- and 4 of 118 foreign ones read as English, which merely keeps them.
_ENGLISH_MARKERS = ('the', 'and', 'you', 'with', 'for', 'our', 'are', 'your', 'will',
                    'this', 'that', 'have', 'from', 'work', 'team', 'experience')
_ENGLISH_MARKER_PATTERN = re.compile(r'\b(?:%s)\b' % '|'.join(_ENGLISH_MARKERS))
_ENGLISH_MARKER_MINIMUM = 8.0
_ENGLISH_MINIMUM_WORDS = 40


def _original_text(row) -> str:
    """The posting as the board wrote it, before any translation.

    This rule has to read the original and nothing else. A translation turns "Engels" into
    "English", which would make every listing look as though it had mentioned English --
    the rule would then never fire at all.
    """
    parts = [row.get(ORIGINAL_TITLE_KEY) or row.get('title'),
             row.get(ORIGINAL_DESCRIPTION_KEY) or row.get('description')]
    return ' '.join(str(part) for part in parts if part).lower()


def looks_english(text: str) -> bool:
    """Is this posting written in English?

    Deliberately not a language detector. These modules decide vocabulary from the country
    and never load one, and a detector would be a second opinion that could disagree with
    the first. Counting function words answers the only question being asked here, and the
    measurement above shows the two populations do not overlap.

    A very short text is called English, because it is not evidence of anything: four
    sources return a title and nothing else by design, and calling those foreign would
    delete every listing they produce.
    """
    words = text.split()
    if len(words) < _ENGLISH_MINIMUM_WORDS:
        return True
    return len(_ENGLISH_MARKER_PATTERN.findall(text)) / len(words) * 100 >=         _ENGLISH_MARKER_MINIMUM


def silent_about_english(row) -> bool:
    """True when a posting is in another language AND never names English, in any spelling.

    Both halves matter. The listing's OWN word counts -- of the 553 non-English Netherlands
    listings the Job module measured, 47 said "Engels" and only 3 said "English", so looking
    for the English word alone would have thrown away 47 real ones.
    """
    text = _original_text(row)
    if looks_english(text):
        return False
    return not _hit('english_mention', row, text)


# ---------------------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------------------

# How alike two adverts have to be before this module calls them one posting. Its own
# numbers -- the Job module has its own, and the two are free to drift apart.
#
# The second threshold depends on how much the title says, and that is measured rather than
# guessed. Across both real corpora there are 146 pairs of recognised listings whose titles
# match, and the 17 that are NOT the same posting separate from the 2 that are almost
# perfectly by title length rather than by body similarity:
#
#   1-4 title words   28.6% - 74.4% body   "Afstudeeropdracht", "Werkstudent Data & AI",
#                                          "Traineeship Data&it" -- generic Dutch and German
#                                          titles that several employers all use, and every
#                                          one of these pairs is two different placements.
#   9 title words     76.7%, 76.8%         "Bachelor Thesis - Artificial Intelligence in
#                                          Microcontroller (f/m/div)" from LinkedIn and
#                                          again from EURES, which pads what it republishes.
#                                          One posting, twice.
#
# So a long, specific title is itself strong evidence and the body only has to agree
# loosely; a short generic one proves nothing and the body has to carry the whole claim.
# Nothing at all falls between 76.8% and 88%, so neither cut sits near a real pair.
_TITLE_MATCH = 90
_SPECIFIC_TITLE_WORDS = 6
_BODY_MATCH_SPECIFIC_TITLE = 75
_BODY_MATCH_GENERIC_TITLE = 85

# Republishers that overwrite the employer's name with a placeholder. A copy that still
# knows who is hiring is the better one to keep.
_PLACEHOLDER_COMPANIES = frozenset({'siehe beschreibung', 'see description', 'n/a', 'na',
                                    'unknown', 'confidential', '-'})


# A locale segment in a URL path, or a language query parameter. One posting published in
# two languages is one posting, and the boards say so in the address:
#
#   everox.homerun.co/student-worker-ai-automation-workflows/en_GB/?source=Indeed
#   everox.homerun.co/student-worker-ai-automation-workflows/nl/?source=Indeed
#
# Nothing else could catch a pair like that. The URLs differ, the titles differ once each is
# written in its own language, and the bodies share almost no tokens -- so both the title
# check and the body check below say "different posting".
# Named languages only, never "any two letters". An earlier draft stripped every
# two-letter path segment, which would have merged two different postings whose addresses
# happened to differ in one -- an id, a version, a market code. These are the codes the app
# actually searches in, with an optional region suffix (en_GB, de-AT, pt_BR).
_LOCALE_CODES = ('en', 'de', 'nl', 'fr', 'it', 'es', 'pt', 'sv', 'no', 'nb', 'da', 'fi',
                 'lb', 'pl')
_URL_LOCALE_SEGMENT = re.compile(
    r'/(?:%s)(?:[-_][a-z]{2})?(?=/|$)'
    r'|[?&](?:lang|language|locale|hl)=(?:%s)(?:[-_][a-z]{2})?'
    % ('|'.join(_LOCALE_CODES), '|'.join(_LOCALE_CODES)), re.IGNORECASE)


def _url_identity(row) -> str:
    """A URL reduced to the posting it points at, ignoring language and tracking.

    Returns '' when there is no usable address, and an empty identity never matches
    anything -- two listings with no URL are not evidence of one posting.
    """
    url = str(row.get('url') or '').strip().lower()
    if not url:
        return ''
    url = url.split('#', 1)[0]
    path = url.split('?', 1)[0]
    # The query is dropped entirely: `?source=Indeed` says which board sent us, which is
    # exactly the thing that differs between two copies of one advert.
    path = _URL_LOCALE_SEGMENT.sub('', path)
    return path.rstrip('/')


def _dedup_key(row) -> str:
    """A title reduced to the words that identify the posting.

    Company names are deliberately not part of this. One advert reaches a search through
    several boards and they disagree about the name -- "Infineon Technologies" on LinkedIn
    and "siehe Beschreibung" on EURES are the same employer, and grouping on the name would
    have called those two theses two different postings.
    """
    return ' '.join(sorted(re.findall(r'[a-z0-9]+', str(row.get('title') or '').lower())))


def _quality(row) -> tuple:
    """How good a copy this is. Highest wins, so the survivor is the employer's own posting
    rather than a republisher's excerpt."""
    company = str(row.get('company') or '').strip().lower()
    return (bool(company) and company not in _PLACEHOLDER_COMPANIES,
            len(str(row.get('description') or '')))


def remove_duplicates(rows: list) -> tuple:
    """Drop repeat copies of the same advert. Returns (kept, removed).

    Same URL is one copy. Otherwise: near-identical title words AND a near-identical body.
    Both halves are needed. The title alone is not enough -- "Afstudeeropdracht" appears
    twice in the real Netherlands data and they are two genuinely different projects that
    happen to share the most generic thesis title in Dutch. The body alone is not enough
    either, since boilerplate about the company is often identical across its whole careers
    page.
    """
    from rapidfuzz import fuzz            # a library, like re -- not a shared RoleHound rule

    keep = [True] * len(rows)
    # Best copy first here too, so when two addresses are the same posting the one that
    # survives is the one that names the employer.
    seen_urls: set = set()
    for i in sorted(range(len(rows)), key=lambda i: _quality(rows[i]), reverse=True):
        identity = _url_identity(rows[i])
        if not identity:
            continue
        if identity in seen_urls:
            keep[i] = False
        else:
            seen_urls.add(identity)

    titles = [_dedup_key(row) for row in rows]
    bodies = [' '.join(str(row.get('description') or '').split()).lower() for row in rows]
    # Best copy first, so it is the one that survives every comparison it wins.
    order = sorted(range(len(rows)), key=lambda i: _quality(rows[i]), reverse=True)

    for i in order:
        # A title that reduces to nothing carries no evidence, and two empty strings score a
        # perfect match -- which would merge every untitled listing into one.
        if not keep[i] or not titles[i] or not bodies[i]:
            continue
        for j in order:
            if j == i or not keep[j] or not titles[j] or not bodies[j]:
                continue
            if fuzz.ratio(titles[i], titles[j]) < _TITLE_MATCH:
                continue
            specific = min(titles[i].count(' '), titles[j].count(' ')) + 1
            cut = (_BODY_MATCH_SPECIFIC_TITLE if specific >= _SPECIFIC_TITLE_WORDS
                   else _BODY_MATCH_GENERIC_TITLE)
            if fuzz.token_set_ratio(bodies[i], bodies[j]) >= cut:
                keep[j] = False

    return [row for row, k in zip(rows, keep) if k], keep.count(False)


def find(rows: list, progress_cb=None, anthropic_api_key=None, should_cancel=None,
         search_title=None, search_work_mode=None, other_names=None) -> tuple:
    """The whole Thesis module. Returns (kept, removed_by_reason).

    `search_title` is the job title in the Search box, and `search_work_mode` its Remote or
    Not Remote choice. Each thesis found is judged against both -- the keyword rules here,
    and Claude, whose prompt and cache key read them off the row.

    Recognise, then de-duplicate, then judge by keyword, then -- if a key is configured --
    let Claude read what survived. That last stage is where the theses the user could not
    actually do get removed: the keyword rules deliberately keep a listing that says nothing
    about where the work happens, and only reading the work itself tells a photonics lab in
    Villach from a machine-learning model. See claude.py.

    De-duplicating before judging is not an optimisation. Judging first would spend every
    rule -- and a Claude call -- on four copies of one advert, and hand the user the same thesis
    four times.
    """
    if progress_cb:
        progress_cb('FILTER_STEP_START:thesis|Thesis', 0, 1)

    # Copies, carrying the title in the box NOW and this Level -- never written onto the rows
    # given. The résumé match reads both off the row.
    title = clean_title(search_title)
    # The other names employers give this job (title_equivalents), handed in by the caller so
    # this module asks nobody and shares nothing: the field rule matches any of them.
    stamp = {TITLE_ROW_KEY: title, LEVEL_ROW_KEY: 'thesis', ALSO_ROW_KEY: list(other_names or []),
             WORK_MODE_ROW_KEY: clean_work_mode(search_work_mode)}
    found = [dict(row, **stamp) for row in rows if is_thesis(row)]
    found, duplicates = remove_duplicates(found)

    # Nothing here writes to a row it was given. The survivors come back as copies carrying
    # the Type label, so a caller can run this module and the Internship module over one
    # list and neither can see what the other decided. The independence is the module's
    # property, not something the caller has to remember to arrange.
    reasons: dict = {}
    kept = []
    for row in found:
        ok, why = survives(row)
        if ok:
            kept.append(dict(row, Category='Thesis'))
        else:
            reasons[why] = reasons.get(why, 0) + 1

    if progress_cb:
        progress_cb('GLOG:filter_step:thesis|info|%d thesis listing(s) among %d, '
                    '%d of them duplicate copies.'
                    % (len(found) + duplicates, len(rows), duplicates), 0, 1)
        for why, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            progress_cb('FILTER_STEP_ITEM:thesis|%s (%d removed)' % (why, count), 0, 1)

    # Every fact about the user now comes from his résumé, so without one Claude would judge
    # against nobody. Skipped, and said so, rather than run blind.
    from . import claude as _claude
    if anthropic_api_key and kept and not _claude.resume_text():
        if progress_cb:
            progress_cb('WARNING: Claude was skipped for theses — no résumé has been '
                        'uploaded. Choose your résumé (PDF or Word) in Search and run Filter '
                        'again.', 0, 1)
        anthropic_api_key = None
    if anthropic_api_key and kept:
        kept, claude_reasons = _claude_pass(kept, anthropic_api_key, progress_cb,
                                            should_cancel)
        for why, count in claude_reasons.items():
            reasons[why] = reasons.get(why, 0) + count
            if progress_cb:
                progress_cb('FILTER_STEP_ITEM:thesis|Claude: %s (%d removed)' % (why, count),
                            0, 1)

    if progress_cb:
        progress_cb('FILTER_STEP_DONE:thesis|Thesis|%d kept' % len(kept), 0, 1)
    return kept, reasons


def _claude_pass(rows: list, api_key: str, progress_cb=None, should_cancel=None) -> tuple:
    """Claude reads every surviving thesis. Returns (kept, removed_by_reason).

    A listing Claude did not answer about is KEPT. That is the important half: a failed
    request, an unfinished answer or a cancelled batch must never be able to delete a real
    thesis, and there are only ever a handful of these -- The user reading one extra costs him a
    minute, losing one costs him the thesis.
    """
    import anthropic

    from . import claude as _claude

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as exc:                                  # noqa: BLE001
        if progress_cb:
            progress_cb('GLOG:filter_step:thesis|warning|Could not reach Claude for the '
                        'Thesis pass (%s) — keeping every listing.' % str(exc)[:80], 0, 1)
        return rows, {}

    answers = _claude.screen(client, rows, progress_cb, should_cancel)

    kept: list = []
    reasons: dict = {}
    for row in rows:
        answer = answers.get(id(row))
        if answer is None:
            kept.append(row)                 # unanswered -- kept, never guessed at
            continue
        drop, reason, _match, basis = answer
        # No score from this part any more, and no floor on one: how well a thesis matches
        # The user is read against his résumé in the second part, which also applies the floor
        # (claude_screen/worth.py).
        row[_claude.BASIS_KEY] = basis
        row[_claude.CACHE_KEY] = _claude.cache_key(row)
        if drop:
            why = reason or 'Claude dropped it'
            reasons[why] = reasons.get(why, 0) + 1
            continue
        row[_claude.VERDICT_KEY] = 'KEEP'
        kept.append(row)
    return kept, reasons
