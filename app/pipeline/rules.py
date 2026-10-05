"""The content rules that decide whether one listing survives the Filter."""
from __future__ import annotations

import re
import pandas as pd

from .text import (is_true_flag, text_of)
from . import country_rules
from .search_title import is_any_workplace, is_not_remote
from .sources_norm import (WORKPLACE_HYBRID, WORKPLACE_ONSITE, WORKPLACE_REMOTE,
                           clean_workplace)


# Sina's order. Checked in this sequence, so a listing that is both a thesis project and
# an internship is filed as a thesis, and this is also the order the Jobs table sorts in.
CATEGORY_ORDER = ['Thesis', 'PhD', 'Internship', 'Part-Time', 'Full-Time']


# ---------------------------------------------------------------- what kind of role ----
#
# THIS REPLACED A BARE SUBSTRING SEARCH, AND HERE IS WHY
#
# The old rule was four words -- 'part-time', 'part time', 'internship', 'thesis' -- looked
# for anywhere in the title or the description. Sina found what that costs: a Glovo advert
# demanding "2-5 years of professional experience outside of an academic and internship
# setting" was filed as an Internship. The sentence whose whole point is that this is NOT an
# internship was the sentence that labelled it one.
#
# Counted on his own Bank of 19,383 listings, 291 of the 1,129 filed as Internship said
# nothing of the sort in their title, and 240 of those had matched on the bare word alone --
# "Postdoc Position", "AI Techlead", "Machine Learning Engineer", all internships because a
# company blurb mentioned "many internship opportunities".
#
# It mattered more from the day the Filter window's category choice started using this. Until
# then the Type column was informational -- the docstring below still said "Nothing is
# filtered out based on this anymore" -- so being wrong was invisible.
#
# THE SHAPE OF THE FIX
#
# The TITLE is the authority. A job advert that is an internship, a thesis placement, a
# doctoral post or a part-time role says so in its title; 838 of the 1,129 already did. The
# description is read only for a phrase that asserts THIS ROLE is one, never for the bare
# word. Every pattern below was measured against the real Bank before it was kept, and three
# drafts were thrown away for relabelling thousands of rows wrongly -- the notes on each say
# which.
#
# The title patterns are multilingual on purpose. The old English-only list missed 693 real
# internships: Traineeship, Stagiair, Werkstudent, Praktikum.

# What a doctoral or postdoctoral post calls itself. Sina asked for these to be their own
# kind: "کار Full time با کار phd و تحقیقاتی کاملا فرق دارد و باید تفکیک باشند". It is not a
# Thesis -- that is a final-year or master placement -- and it is not an ordinary Full-Time
# job either. Before this they were scattered across four categories: 124 filed Full-Time,
# 62 Thesis, 24 Part-Time and 12 Internship.
#
# Title only. These posts always name themselves there, and the words appear constantly in
# ordinary job bodies ("you will work with our PhDs", "a PhD is a plus") -- the same trap the
# bare word "internship" fell into.
_PHD_TITLE = re.compile(
    r'(\bph\.?\s?d\b|\bphd\b|\bpost[- ]?doc\w*\b|\bdoctoral\b|\bdoctorate\b'
    r'|\bpromovendus\b|\bpromovenda\b|\bpromotieonderzoek\b|\bdoktorand\w*\b'
    r'|\beng\.?d\b|\bdoctorando\b|\bdottorand\w*\b)', re.I)

# Word boundaries carry real weight here: \bintern\b must not match "international" or
# "internal", which is most of why the bare substring was wrong to begin with.
#
# The bare "intern" needs more than a word boundary, though, and a measurement found out
# why: in Dutch and German, "intern" on its own is the adjective INTERNAL. "Je komt te
# werken in een intern dataplatformteam" is an internal platform team, and it filed a Data
# Engineer post as an internship. English uses the noun at the end of a title or against
# punctuation -- "Data Science Intern", "Intern - Analytics", "AI Research Intern (2027)" --
# while the Dutch adjective sits in front of the noun it describes. So the bare word is
# accepted only where English puts it.
_INTERNSHIP_TITLE = re.compile(
    r'(\binternships?\b|\binterns\b'
    r'|\bintern(?=\s*(?:$|[,\-–—()/|:]|\d))'
    r'|\b(?:praktikum|praktikant\w*|praktyki|stagiair\w*|werkstudent\w*'
    r'|working student|traineeship|tirocinio|becario|becaria|est[aá]gio|pr[aá]ctica[s]?'
    r'|summer analyst)\b)', re.I)

# Phrases that say THIS role is an internship, rather than merely using the word.
_INTERNSHIP_IN_BODY = re.compile(
    r'(this internship'
    r'|the internship (?:will|is|starts|begins|lasts|runs|takes place|offers)'
    r'|internship (?:position|placement|programme|program|contract|agreement|allowance|'
    r'period|duration|report|thesis)'
    r'|\bas an intern\b'
    r'|during (?:your|the) internship'
    r'|(?:offer|offering|offers|have|seeking|looking for) an internship'
    r'|is an internship'
    r'|internship \(m'
    r'|\d+[- ](?:month|week)s? internship'
    r'|internship of \d'
    r'|internship for (?:a period|\d)'
    r')', re.I)

# The sentence whose whole point is that this is NOT an internship. Glovo's advert is the
# case that started all of this.
_NOT_AN_INTERNSHIP = re.compile(
    r'(outside of[^.]{0,60}internship'
    r'|not an internship'
    r'|beyond[^.]{0,40}internship'
    r'|excluding[^.]{0,40}internship'
    r'|internship[s]? (?:do|does) not count'
    r'|no internship'
    r')', re.I)

_THESIS_TITLE = re.compile(r'\b(thesis|scriptie|abschlussarbeit|masterarbeit|bachelorarbeit'
                           r'|afstudeer\w*)\b', re.I)
_THESIS_IN_BODY = re.compile(
    r'(this thesis|your thesis|thesis (?:project|position|placement|topic|work|student)'
    r'|write (?:your|a) (?:master|bachelor)?\s*thesis'
    r'|(?:master|bachelor)\'?s? thesis (?:project|position|placement|topic|at|with|in our)'
    r'|final thesis)', re.I)

_PART_TIME_TITLE = re.compile(r'(part[- ]time|teilzeit|deeltijd|temps partiel)', re.I)

# Part-Time, read from the body as well as the title -- and the history here matters, because
# the narrow version cost Sina his entire result.
#
# Three attempts failed first, and each is still a real trap:
#
#   * "X hours a week" relabelled 1,999 rows, "Senior DevOps Engineer" among them, because
#     "40 hours a week" matched;
#   * capping it under 33 hours still caught "Je bent minimaal 32 uur per week beschikbaar"
#     -- a MINIMUM, on a full-time job -- and the decimal half of "39.25 uur per week";
#   * accepting "in Teilzeit" from the body took 302 German adverts saying "Diese Stelle ist
#     in Vollzeit sowie in Teilzeit zu besetzen", a full-time job that MAY be done part-time.
#
# So I narrowed it to the title and two English sentences. THAT WAS MEASURED ON THE WRONG
# POPULATION. Across all 12,778 German listings the body mentions were indeed dominated by the
# both-options phrasing -- but of the 742 that match everything else Sina asked for, 94 mention
# part-time and only 17 are that phrasing. The other 77 say it plainly, and every one was being
# filed as Full-Time:
#
#     "Beschäftigungsart Teilzeit"                          Werkstudent Data Science
#     "Vertragsart: Teilzeit"                               REWE digital
#     "This is a part-time (Werkstudent) role"              Pergolux
#     "happy to discuss a part-time arrangement"            European Central Bank
#     "bis zu 20 Stunden pro Woche"                         Rohde & Schwarz
#
# He searched Junior + Remote + Part-Time in Germany, expected at least ten, and got none.
# This rule is why. It now reads the body, and the both-options phrasing is excluded by name
# rather than by refusing to read at all.
_PART_TIME_IN_BODY = re.compile(
    r'(this is a part[- ]time'
    r'|this (?:position|role|job|vacancy) is part[- ]time'
    # How a German advert states the contract, which is where these actually live.
    r'|besch[äa]ftigungsart\W{0,12}teilzeit'
    r'|vertragsart\W{0,12}teilzeit'
    r'|arbeitszeit\W{0,12}teilzeit'
    r'|anstellungsart\W{0,12}teilzeit'
    r'|\bin\s+teilzeit\b'
    r'|\bteilzeit\b\W{0,4}(?:befristet|unbefristet|m[öo]glich)'
    r'|part[- ]time\s+\(werkstudent'
    r'|part[- ]time\s+(?:arrangement|contract|basis|role|position|position\b)'
    r'|part[- ]time\s+options?\b'
    # A working week short enough that it cannot be full time. Bounded at 32 because a German
    # or Dutch full week is 35-40, and written so the number has to be the hours -- the earlier
    # failures came from matching a minimum, or the decimals of 39.25.
    r'|\b(?:[89]|1[0-9]|2[0-9]|3[0-2])\s*(?:std\.?|stunden|hours|hrs|uur|uren)\s*'
    r'(?:/|pro|per|a|in der)\s*(?:woche|week|weekly)'
    r')', re.I)

# A full-time job that MAY also be done part-time. Not what Sina means, and it is 211 of the
# 1,994 German listings that mention Teilzeit at all -- common enough to need naming, rare
# enough that refusing to read the body because of it was the wrong trade.
_PART_TIME_IS_OPTIONAL = re.compile(
    r'(voll-?\s?zeit\W{0,14}(?:sowie|oder|und|bzw|/|,)\W{0,14}teil-?\s?zeit'
    r'|teil-?\s?zeit\W{0,14}(?:sowie|oder|und|bzw|/)\W{0,14}voll-?\s?zeit'
    r'|in\s+voll-?\s+und\s+teilzeit'
    r'|full[- ]?time\W{0,10}(?:or|and|/|,)\W{0,10}part[- ]?time'
    r'|part[- ]?time\W{0,10}(?:or|and|/)\W{0,10}full[- ]?time)', re.I)

# Checked in this order. PhD comes before Thesis because a "PhD Candidate" advert says
# "thesis" all through its body and is still a doctoral post, not a thesis placement.
_CATEGORY_RULES = (
    ('PhD', _PHD_TITLE, None, None),
    ('Thesis', _THESIS_TITLE, _THESIS_IN_BODY, None),
    ('Internship', _INTERNSHIP_TITLE, _INTERNSHIP_IN_BODY, _NOT_AN_INTERNSHIP),
    ('Part-Time', _PART_TIME_TITLE, _PART_TIME_IN_BODY, _PART_TIME_IS_OPTIONAL),
)


# THE LOCAL-LANGUAGE INTERNSHIP AND THESIS WORDS (Document T-20).
#
# The Type column's patterns above are English-first and deliberately narrow, and a bare "stage"
# is the reason: in English it is a stage ("Late Stage", "Stage Manager"), and in Dutch, French
# and Italian it is an internship. So Dutch "Stage Data & AI" was filed Full-Time -- 33 of the
# 4,325 Bank rows, and 62 of the 279 an Any search returned -- while the Internship module, which
# reads the same title, correctly called it an internship.
#
# The fix is to let the words the SEARCH sends for each language name the Type too, which makes
# "what was searched for" and "what the column calls it" one list instead of two. Four things keep
# it from being the fourth draft that gets thrown away:
#
#   * it speaks LAST. Only when no rule above fired, so every row already typed is untouched.
#   * TITLE only, and WHOLE words only. "Stagecoördinator" is a coordinator, not an internship,
#     and a prefix match would have filed it as one.
#   * only the languages of the listing's COUNTRY (country_rules.languages_for with no detected
#     language). A United States or United Kingdom row loads English alone, so "Stage Manager"
#     there is untouched. The detected language is deliberately not used: a Dutch advert with an
#     English description detects as English and would lose its Dutch words.
#   * the words below are NOT used, each for a stated reason.
_TYPE_WORDS_NOT_USED = {
    'trainee': 'a paid graduate programme, not an internship; the existing rule keeps "traineeship"',
    'traineeship': 'already matched by _INTERNSHIP_TITLE',
    'traineeprogram': 'a graduate programme', 'traineeohjelma': 'a graduate programme',
    'apprentissage': 'French for "learning" -- "Ingénieur Apprentissage Automatique" is Machine '
                     'Learning, and this would have filed it as an internship',
    'apprenti': 'an apprentice, and the stem of the word above',
    'apprendista': 'an apprentice, not an internship', 'apprendistato': 'an apprenticeship contract',
    'mémoire': 'also "memory"; the full phrases ("Mémoire de Master") are used',
    'alternance': 'a work-study contract; left out until read on real French rows',
    'alternant': 'a work-study contract; left out until read on real French rows',
}
_GATED_PATTERNS: dict = {}


def _gated_patterns(languages):
    """(thesis pattern, internship pattern) for a tuple of language codes, compiled once each."""
    cached = _GATED_PATTERNS.get(languages)
    if cached is not None:
        return cached
    # Imported here, not at the top: the search package imports this module.
    from .search.queries import _LANGUAGE_INTERNSHIP_WORDS, _LANGUAGE_THESIS_WORDS

    def compile_for(table):
        words = []
        for code in languages:
            for word in table.get(code, ()):
                bare = word.strip().strip('"').strip()
                if bare.lower() not in _TYPE_WORDS_NOT_USED:
                    words.append(bare)
        if not words:
            return None
        parts = sorted({re.escape(w).replace(r'\ ', r'\s+') for w in words}, key=len, reverse=True)
        return re.compile(r'(?<![\w])(?:%s)(?![\w])' % '|'.join(parts), re.I)

    cached = (compile_for(_LANGUAGE_THESIS_WORDS), compile_for(_LANGUAGE_INTERNSHIP_WORDS))
    _GATED_PATTERNS[languages] = cached
    return cached


def _gated_kind_from_title(row) -> str:
    """'Thesis', 'Internship', or '' -- from the title, in the languages of the listing's country."""
    title = str(row.get('title') or '')
    if not title:
        return ''
    languages = tuple(country_rules.languages_for(row.get('country'), row.get('location'), None))
    thesis, internship = _gated_patterns(languages)
    # Thesis first, as in _CATEGORY_RULES: "Afstudeerstage" and "Stage de fin d'études" are a
    # graduation placement, which the column has always called a thesis.
    if thesis and thesis.search(title):
        return 'Thesis'
    if internship and internship.search(title):
        return 'Internship'
    return ''


def category_from_words(row) -> str:
    """The kind of role the listing's own words say it is, or '' if they do not say.

    Separate from categorize() because two callers need the difference between "this says
    Full-Time" and "this says nothing, so call it Full-Time" -- see is_category_uncertain.
    """
    title = str(row.get('title') or '')
    body = str(row.get('description') or '')
    for name, in_title, in_body, against in _CATEGORY_RULES:
        if in_title.search(title):
            # "(MSc/PhD) AI Research Intern" is an internship open to doctoral students,
            # not a doctoral post. A title saying both says which with its second word.
            if name == 'PhD' and _INTERNSHIP_TITLE.search(title):
                continue
            return name
        if in_body is None:
            continue
        if against is not None and against.search(body):
            continue
        if in_body.search(body):
            return name
    # Nothing above spoke. The words of the listing's own languages get one more chance, in the
    # TITLE only -- see _gated_kind_from_title.
    return _gated_kind_from_title(row)


# Where the pre-translation text is kept. Translation overwrites title/description, and
# what it overwrites is sometimes the only evidence a listing is remote at all -- see
# maybe_translate for the 53 Dutch listings this cost.
ORIGINAL_TITLE_KEY = '_original_title'
ORIGINAL_DESCRIPTION_KEY = '_original_description'


def rule_text(row) -> str:
    """Everything a content rule should read: the listing as it arrived AND as translated.

    Only used by the rules that RESCUE a listing. The asymmetry is deliberate and is the
    same one that governs the keyword lists themselves: more text can only help a rule
    that is looking for a reason to KEEP something, while for a rule that deletes, more
    text is more chances to fire wrongly.
    """
    parts = [row.get('title'), row.get('description'), row.get('location'),
             row.get(ORIGINAL_TITLE_KEY), row.get(ORIGINAL_DESCRIPTION_KEY)]
    return ' '.join(str(p) for p in parts if p).lower()


ON_SITE_OR_HYBRID_KEYWORDS = [
    'on-site', 'onsite', 'on site',
    'in-office', 'in office',
    'in-person', 'office-based', 'office based',
    # QUALIFIED forms of "hybrid" only. The bare word used to be here and it was the single
    # most expensive entry in this list: on the German corpus it alone dropped 117 listings
    # that said nothing else about attendance. It fires on cloud architecture --
    # "container-orchestrierung (eks, kubernetes/kubeflow) oder einem hybrid-ansatz" is a
    # deployment topology, not a desk -- and it fires inside benefit lists, where "hybrides
    # Arbeiten möglich" beside flexible hours and a pension is an OFFER of flexibility
    # rather than a requirement to attend.
    #
    # No trailing boundary is applied to this list (see the pattern below), so 'hybrid work'
    # still catches "hybrid working" and 'hybrid model' catches "hybrid models".
    'hybrid work', 'hybrid model', 'hybrid role', 'hybrid setup',
    'hybrid arrangement', 'hybrid position', 'hybrid schedule', 'hybrid office',
    # ...and the compounds, because German does not leave a space. "hybrides
    # Arbeitsmodell" is as clear a statement of attendance as "hybrid working" and would
    # otherwise have been lost with the bare word: 'hybrid model' cannot match inside
    # "Arbeitsmodell". Dutch, the Nordic languages and French build the same way.
    'hybrides arbeit', 'hybride arbeit', 'hybridarbeit', 'hybrides modell',
    'hybridmodell', 'hybrid-modell', 'hybride werk', 'hybride model',
    'hybridarbete', 'hybridarbeid', 'hybridarbejde', 'hybridityö',
    'travail hybride', 'mode hybride', 'lavoro ibrido', 'trabajo híbrido',
]

# Matched only where a word starts. 'hybrid' was being found inside the run-together
# facet text some boards emit ("...work model hybrid...", "timehybridmid2"), which dropped
# 6 listings in a real 2,901-listing corpus that say nothing about a hybrid arrangement.
#
# The boundary is applied HERE and deliberately not to REMOTE_CONFIRMATION_KEYWORDS below,
# because the two lists fail in opposite directions: a stray match in this list DELETES a
# job Sina would have wanted, while a stray match in the remote list merely keeps one he
# can ignore -- and Claude re-checks the survivors anyway. Tighten the list that deletes;
# leave the list that rescues as loose as it is. The same asymmetry decided the leading-only
# boundary: every real phrase here starts at a word start, so nothing is lost at the front,
# and leaving the tail open keeps "on site" matching "on sites", "hybrid" matching "hybride".
_ON_SITE_OR_HYBRID_PATTERN = re.compile(
    r'\b(?:%s)' % '|'.join(re.escape(kw) for kw in
                           sorted(ON_SITE_OR_HYBRID_KEYWORDS, key=len, reverse=True)))


REMOTE_CONFIRMATION_KEYWORDS = [
    'remote', 'wfh', 'work from home', '100% remote', 'remote-first', 'remote only',
    # German, and the English phrasings the original six never covered. This list knew no
    # German at all, and most of what a German search returns is German: "Homeoffice
    # möglich" is THE standard way a German employer says a role can be done from home,
    # and it was worth nothing here. Measured on 80 real listings judged against Sina's
    # actual constraint, adding these took the rule from keeping 4 of 21 usable jobs to
    # keeping 10 -- and to 18 alongside the change in passes_work_location_rule below.
    'homeoffice', 'home office', 'home-office', 'mobiles arbeiten', 'mobile arbeit',
    'telearbeit', 'von zu hause', 'ortsunabhängig', 'remote-freundlich',
    'work from anywhere', 'fully remote', 'work remotely',

    # Found by asking the opposite question of the corpus: of the listings this rule
    # deleted, which contain a remote-sounding phrase the list does not know? Seven did,
    # and every one is genuine -- "40 days per year for telecommuting", "teams that are
    # home-based", "möjlighet till att arbeta hemifrån", "a 100% distributed setting --
    # Speechify has no office", "thuiswerkvergoeding", "smart working",
    # "work-from-home equipment".
    'telecommut', 'work-from-home', 'home-based', 'home based', 'smart working',
    'fully distributed', '100% distributed', 'fully-distributed', 'no office',

    # The English that translation actually produces, which is not the English a person
    # would write. "thuiswerk" comes back as "home work allowances for internet and a good
    # workplace"; "gedeeltelijk thuis" as "partial home work". The list knew "home office"
    # and "work from home" and neither of those is what came out.
    'home work', 'home working', 'working from home', 'work at home', 'from home',
    'place-independent', 'location-independent', 'independent of location',

    # The same search rejected these, and they are worth recording so nobody adds them
    # later: "hybrides Arbeiten" (26 listings) means part-time in the office, which is the
    # opposite; "deutschlandweit"/"europaweit" (17) describe where the COMPANY operates;
    # "workation" (14) is a few weeks abroad per year, not a remote role; "flexibles
    # Arbeiten" (12) is usually flexible HOURS; and "distributed team" (10) describes the
    # colleagues, not where this job is done.

    # The rest of Europe, by the standard term each country's postings use. None of these
    # appear in the current corpus, which is Germany-heavy -- but the app searches all
    # eighteen countries, and without them a Spanish or Polish remote posting that never
    # says the English word "remote" is invisible. Translation runs before this rule and
    # usually converts them, but not always: a listing detected as English (a common
    # outcome for a bilingual tech advert) is never translated at all, which is exactly
    # why the German entries above rescue 528 listings on their own.
    'teletrabajo', 'trabajo remoto', 'télétravail', 'travail à distance',
    'thuiswerk', 'op afstand', 'lavoro agile', 'trabalho remoto',
    'arbeta hemifrån', 'distansarbete', 'hjemmekontor', 'fjernarbejde', 'etätyö',
    'praca zdalna', 'zdalnie',
]


NO_REMOTE_PHRASES = [
    'no remote', 'not remote', 'remote not available',
    'remote work not permitted', 'remote work not available', 'without remote', 'remote is not',
    'on-site only', 'onsite only', 'must be on-site', 'must work on-site', 'fully on-site',
    'in-office only', 'in-person only', 'office-based only',
]


# The "Location:" label rule that used to live here is gone. It deleted any listing whose
# text named a location other than Italy/Milan/Turin, on the theory that a line reading
# "Location: Berlin" means "remote, but you must live in Berlin". Sina's call, and he is
# right: a company stating where IT is based is not stating where the WORKER must be, and
# a remote listing almost always names the company's own city somewhere. The rule was
# deleting real remote jobs over a sentence that said nothing about the applicant.


UNPAID_KEYWORDS = [
    'unpaid',
    'no salary', 'no pay', 'without pay',
    'volunteer', 'voluntary',
    'no compensation',
    'non-paid', 'nonpaid',
    'no stipend',
    'pro bono',
    'self-funded', 'self funded',
    'expenses only',
    'unwaged', 'no wage', 'unsalaried', 'gratis',
    'without remuneration',
    'for college credit only', 'credit only',
    'compensation: none',
]

# The list above is the vocabulary. What follows is the part that was missing: a
# requirement that the words describe THE POSITION.
#
# Matching them anywhere in the text deleted 222 of 2,542 real listings, and reading every
# one of those verdicts, essentially all were wrong:
#
#     volunteer  190x  a category link in a job board's own filter menu
#                      ("...Part-time Full-time Self-employed Student Seasonal Temp
#                        Volunteer Career level..."), or a benefit -- "2 paid volunteering
#                      days a year", "one day each year to volunteer at a charity"
#     unpaid      15x  "the option of unpaid leave", offered as a PERK
#     voluntary    9x  "zero voluntary employee churn", "voluntary work" in a list of
#                      life events a flexible employer accommodates
#     gratis       3x  German for "free", as in free drinks
#
# A company that offers unpaid leave is not offering an unpaid job. So the words split into
# two groups by how much context they need.

# Group one: phrases that cannot mean anything else wherever they appear.
_UNPAID_UNAMBIGUOUS = [
    'no pay', 'without pay', 'no compensation', 'non-paid', 'nonpaid', 'no stipend',
    'pro bono', 'expenses only', 'unwaged', 'no wage', 'unsalaried',
    'without remuneration', 'for college credit only', 'credit only',
    'compensation: none', 'this is an unpaid', 'this role is unpaid',
    'this position is unpaid', 'the position is unpaid', 'unpaid position',
    'unpaid role', 'unpaid internship', 'unpaid placement', 'unpaid work experience',
    'unbezahltes praktikum', 'unbezahlte stelle', 'ehrenamtliche stelle',
]

# Group two: words that mean an unpaid job only when attached to the role itself.
#
# "opportunity" is deliberately NOT in this list, and it was in the first version. Four
# real listings say "Volunteer opportunities" in their benefits -- the chance to do charity
# work on company time -- and that is a perk, not an unpaid job. The one genuine listing
# that says "This is an UNPAID volunteer opportunity" is caught by "this is an unpaid"
# above, so nothing real is lost by leaving the word out.
_UNPAID_ROLE_WORDS = (r'internship|internships|position|positions|role|roles|placement|'
                      r'traineeship|work experience|vacancy|post')

# 'self-funded' belongs here rather than above, and that is a real finding rather than
# caution: three listings said "profitable and self-funded" and "we've remained
# self-funded", which describes the COMPANY'S financing and is arguably a good sign. The
# phrase this rule was written for is "self-funded programme" -- a bootcamp the candidate
# pays for.
_UNPAID_SELF_FUNDED_TARGETS = (r'programme|program|course|courses|training|bootcamp|'
                               r'traineeship|internship|placement|study|studies')

_UNPAID_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(k) for k in _UNPAID_UNAMBIGUOUS) + r')'
    r'|\b(?:unpaid|voluntary|volunteer)\s+(?:' + _UNPAID_ROLE_WORDS + r')\b'
    r'|\b(?:this|the)\s+(?:' + _UNPAID_ROLE_WORDS + r')\s+(?:is|are)\s+'
    r'(?:unpaid|voluntary|unremunerated)\b'
    r'|\bself[- ]funded\s+(?:' + _UNPAID_SELF_FUNDED_TARGETS + r')\b',
    re.I)

# "No salary info" is XING's label for a listing whose salary field is empty, and
# "no salary range provided" is the same thing on other boards. It says the board does not
# know the pay, not that there is none -- the opposite of what this rule is looking for.
_UNPAID_NO_SALARY = re.compile(
    r'\bno salary\b(?!\s*(?:info|information|listed|provided|specified|given|range|data|'
    r'details|disclosed|indicated))', re.I)


SENIOR_KEYWORDS = [
    'senior', 'sr.', 'principal', 'manager', 'director', 'head of', 'chief', 'vp', 'vice president',
    'president', 'team lead', 'supervisor', 'department head', 'leadership',
]

# Matched at a word start, and -- separately -- only where the word can be about THIS role.
#
# This rule deleted 1,563 of 2,542 real listings, more than every other rule in the app,
# and 797 of those were deleted by a word that appeared ONLY in the description. Reading
# them, hardly any described the advertised role:
#
#     vp        inside "VPN" -- "firewalls, vpn, iam", "dhcp, dns oder vpn". The same
#               fault as 'itar' inside "Mitarbeiter", which cost 34% of the same corpus.
#     director  inside "Active Directory"
#     manager   "you will work closely with the engineering manager", "asset managers"
#               (the CLIENTS), "campaign manager on tiktok" (a product)
#     senior    "Senior executive (CEO, CFO, President)" -- a job board's filter menu; and
#               "Similar jobs: Senior Data Engineer" -- somebody else's vacancy entirely
#     principal "principal investigator", named as a career step AFTER this one
#
# A role's level is stated in its title, in the platform's own seniority field, or as a
# years-of-experience requirement -- and the last two already have their own handling.
#
# Two of these words are the start of an ordinary word that has nothing to do with
# seniority, so a leading boundary alone is not enough for them and each gets a guard on
# its tail. 'vp' opens "VPN", which appears in the skills list of plenty of infrastructure
# roles; 'director' opens "Directory", as in "Active Directory". Both were found in real
# listings. The guards are deliberately narrow: "Directors" still matches, because a plural
# of the job title is still the job title.
_SENIOR_KEYWORD_TAIL_GUARDS = {
    'vp': r'(?![a-z])',
    'director': r'(?!y\b|ies\b)',
}


def _senior_keyword_alternatives():
    for keyword in sorted(SENIOR_KEYWORDS, key=len, reverse=True):
        yield re.escape(keyword) + _SENIOR_KEYWORD_TAIL_GUARDS.get(keyword, '')


_SENIOR_TITLE_PATTERN = re.compile(
    r'\b(?:%s)' % '|'.join(_senior_keyword_alternatives()), re.I)

# The description still counts, but only where the phrasing makes the word the role's own
# title: "As a Senior Data Scientist you will...", "We are looking for a Senior Engineer",
# "Als Senior Data Scientist wirkst du...". Without this, a generic title over a senior
# body ("7P331 - AI Engineer" ... "als Senior AI Engineer berätst du unsere Kunden") would
# be missed, which is a real listing in the same corpus.
#
# "as well as leadership skills" and "such as Principal Investigator" are excluded by name:
# both appeared, and both are a requirement or an example rather than the job on offer.
_SENIOR_ROLE_DEFINING_PATTERN = re.compile(
    r'(?:(?<!well )(?<!such )\bas\s+(?:an?\s+)?'
    r"|\bwe(?:'re| are)\s+(?:looking|searching|hiring)\s+for\s+(?:an?\s+)?"
    r'|\bwir\s+suchen\s+(?:eine[nr]?\s+)?'
    r'|\bthis\s+is\s+(?:an?\s+)?'
    r'|\bthe\s+role\s+is\s+(?:that\s+of\s+)?(?:an?\s+)?'
    r'|(?<!sowie )\bals\s+(?:eine[nr]?\s+)?'
    r'|\bstellenbezeichnung\s*:?\s*)'
    r'(?:(?!well\b|such\b)[a-zäöüß/&+.\-]+\s+){0,2}?'
    r'(?:%s)\b' % '|'.join(_senior_keyword_alternatives()), re.I)

# The same thing said the other way round -- "Senior Data Scientist wanted", "Senior Data
# Engineer (m/w/d) gesucht". The level comes first and the verb that makes it this role's
# title comes after, so the prefix pattern above cannot see it.
_SENIOR_WANTED_PATTERN = re.compile(
    r'\b(?:%s)[^.!?\n]{0,50}?\b(?:wanted|sought|gesucht|gesuchte[nr]?)\b'
    % '|'.join(_senior_keyword_alternatives()), re.I)


SENIOR_LEVEL_FIELD_VALUES = {'director', 'executive', 'mid-senior level'}


# matches "5+ years", "+5 years", "5 + years" etc. for 3 through 10+ years of experience
SENIOR_EXPERIENCE_PATTERN = re.compile(
    r'\b(3|4|5|6|7|8|9|10)\s*\+\s*years?\b|\+\s*(3|4|5|6|7|8|9|10)\s*years?\b'
)


# Matches an experience RANGE whose lower bound is already 3+ -- "3-4 years", "5/7
# years", "10-15 years", "5 to 7 years". Two real gaps this closes (both confirmed with
# the live function): the upper bound used to be capped at 10 too, so a genuinely senior
# "10-15 years" matched nothing at all and slipped through; and only -, / and | counted
# as separators, so the very common written form "5 to 7 years" slipped through as well.
SENIOR_EXPERIENCE_RANGE_PATTERN = re.compile(
    r'\b([3-9]|1[0-9]|20)\s*(?:[-/|]|\bto\b)\s*(\d{1,2})\s*years?\b'
)


# Read beside a matched range, in is_too_senior. An age range is not an experience demand --
# "graduates aged 18 to 28 years" is the opposite of a senior requirement -- and the words
# cover the languages this app searches, because the posting is read before translation.
_AGE_RANGE_WORDS = re.compile(
    r'\b(ages?|aged|years old|between the ages|alter|jahre alt|altersgruppe|leeftijd|'
    r'jaar oud|[aâ]ge|ans d[\'e]|anni di et[aà]|edad|idade|alder|[åa]lder|ik[aä])\b', re.I)

_EXPERIENCE_WORDS = re.compile(
    r'\b(experience[ds]?|ervaring|erfahrung\w*|berufserfahrung|esperienza|exp[eé]rience|'
    r'erfaring|erfarenhet|kokemus|experi[eê]ncia|experiencia|track record|seniority)\b', re.I)


# Matches a bare minimum ask with no "+" and no range -- "8 years of experience", "6
# years experience", "7 years of relevant experience". Another real gap: neither pattern
# above caught these at all, so "8 years of experience required" passed the filter
# entirely. The lookbehind keeps it safe from ranges: without it, the "3" in a
# junior-friendly "1-3 years of experience" would match on its own and wrongly drop the
# listing.
#
# The gap between "years" and "experience" uses [^\s.;:!?()] rather than \S -- a real
# false-positive fix. With \S the gap crossed sentence boundaries, so two unrelated
# clauses paired up and DELETED junior-friendly listings:
#   "Our team grew 8 years running. No prior experience needed."  -> wrongly dropped
#   "You will gain 3 years worth of experience in one."           -> wrongly dropped
# Both were verified against the live function. Excluding sentence punctuation from the
# gap keeps the match inside one clause, which is the only place a real requirement is
# ever written.
SENIOR_MIN_YEARS_PATTERN = re.compile(
    r'(?<![-/|\d])\b([3-9]|1[0-9]|20)\s*\+?\s*years?'
    r"(?:\s+(?:of|in|'?s|professional|relevant|hands-on|industry|practical|commercial|work|working))*"
    r'\s+experience\b'
)


# A bare "N years ... experience" is not automatically a requirement -- "you will gain 3
# years worth of experience" says the opposite. The match above only counts as a
# seniority signal when the surrounding text actually frames it as one, or when nothing
# nearby explicitly waives it.
_SENIOR_REQUIREMENT_WORDS = (
    'required', 'require', 'requires', 'requirement', 'minimum', 'min.', 'at least',
    'must have', 'need', 'needs', 'looking for', 'seeking', 'proven', 'demonstrated',
    'experience:', 'expected', 'ideally', 'preferably', 'preferred', 'qualification',
)


_SENIOR_REQUIREMENT_WAIVERS = (
    'no prior experience', 'no experience', 'without experience', 'gain', 'you will gain',
    'not required', 'no previous experience',
)


FAKE_KEYWORDS = [
    'earn $', 'make money fast', 'no experience needed', 'guaranteed income',
    'click here to apply', 'send your bank details', 'wire transfer',
    'whatsapp only', 'telegram only', 'investment opportunity', 'pyramid',
    'mlm', 'pay to apply', 'registration fee', 'processing fee required',
    'work from home, no interview',
]


SUSPICIOUS_COMPANY_NAMES = {'', 'confidential', 'private company', 'n/a', 'company name', 'undisclosed'}


# remoteok.com also has a free public JSON API, no key/signup needed -- confirmed via a
# real call: a plain list of ~100 recent postings (no keyword search parameter, unlike
# remotive.com), so filtering by role term happens locally here rather than server-side.
# Global (remote-only listings), same as remotive.com above.
_REMOTEOK_API_URL = 'https://remoteok.com/api'


def _normalize_text(text) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ''
    return re.sub(r'\s+', ' ', str(text).strip().lower())


def is_likely_fake(row):
    reasons = []
    company = _normalize_text(row.get('company'))
    description = _normalize_text(row.get('description'))
    title = _normalize_text(row.get('title'))
    url = row.get('url')
    url_missing = url is None or (isinstance(url, float) and pd.isna(url)) or str(url).strip() == ''

    if company in SUSPICIOUS_COMPANY_NAMES:
        reasons.append('missing/suspicious company name')
    # A thin_description source (arbeitsagentur.de, Jooble, JobCloud, swissdevjobs --
    # see passes_work_location_rule) returns no JD body by design, so a short description is
    # EXPECTED there, not a fake-listing signal. Real bug this fixes: such a row is
    # under 50 chars by definition, so any one of them whose source ALSO returned no
    # company name scored 2 signals and was deleted here in step 2 -- before the
    # thin-description exemption in step 4 ever got a chance to keep it. Live for
    # arbeitsagentur.de, whose `firma` field really can come back empty.
    if not is_true_flag(row.get('thin_description')) and (not description or len(description) < 50):
        reasons.append('missing or too-short description')
    if url_missing:
        reasons.append('missing listing URL')

    combined = f'{title} {description}'
    for kw in FAKE_KEYWORDS:
        if kw in combined:
            reasons.append(f'suspicious phrase: "{kw}"')

    return len(reasons) >= 2


# The "it never mentioned English" rule that used to live here is gone, along with the two
# constants that only served it. Sina removed it for the same reason he removed the
# location-label rule and the must-prove-it-is-remote requirement: it deleted a listing for
# being SILENT rather than for saying anything. A posting written in Dutch that never
# happens to use the word "English" has not told anyone that English is unusable there --
# and the listings it deleted were exactly the ones Claude was best placed to judge.

# requires_language_besides_english (in language.py) is untouched and is the rule that
# still does this job properly: it fires on a posting that ASKS for another language.


# Built once per (country, location) pair and reused: a listing-by-listing rebuild of
# these alternations was measured at most of the rule's cost, and a real search hands the
# same handful of country/location pairs over and over.
_COUNTRY_PATTERN_CACHE: dict = {}


DETECTED_LANGUAGE_KEY = 'detected_language'
NEEDS_TRANSLATION_KEY = 'needs_translation'


def classify_language(row) -> str:
    """Work out what language this listing is written in, and record it on the row.

    Two flags are written, and they are what the rest of the Filter reads:

        detected_language   the language code, or 'unknown'
        needs_translation   False when the posting is already English

    Both are set before any translation happens, which is the point: the country object
    then checks the posting against its OWN language's vocabulary, and the translator only
    ever sees the listings that actually need it.

    Detection itself is lingua's, memoised on the row against a fingerprint of the exact
    text it was derived from -- so this costs nothing when it has already been asked, and
    correctly re-detects after a translation or a deep-crawl has changed the text.
    """
    from .language import detect_language          # imported here: language.py imports rules
    code = detect_language(row)
    if isinstance(row, dict):
        row[DETECTED_LANGUAGE_KEY] = code
        row[NEEDS_TRANSLATION_KEY] = code not in ('en', 'unknown')
    return code


def _row_language(row) -> str:
    """The listing's own language -- the one it was WRITTEN in, not the one it now reads in.

    The distinction is the whole point. Once a Dutch posting has been translated, its
    description is English, so detecting again answers "English" and loads the English
    vocabulary alone -- and the Dutch evidence sitting in _original_description is never
    searched for. A posting saying "thuiswerkvergoedingen" then looks like it never
    mentioned remote work at all, and is deleted for silence.

    Normally the answer is already on the row: the country step records it before the
    translator runs. This only has to work out for itself when something called a rule
    without that step, and then it reads the ORIGINAL text if one was kept.
    """
    if not isinstance(row, dict):
        return classify_language(row)
    code = row.get(DETECTED_LANGUAGE_KEY)
    if code:
        return code
    original = row.get(ORIGINAL_DESCRIPTION_KEY) or row.get(ORIGINAL_TITLE_KEY)
    if original:
        from .language import detect_language
        return detect_language({'title': row.get(ORIGINAL_TITLE_KEY) or row.get('title'),
                                'description': original})
    return classify_language(row)


def _country_pattern(section, country, location, detected=None, vocabulary=None):
    """The compiled matcher for one vocabulary section, for one listing's languages.

    Leading word boundary, no trailing one -- so "itar" can never fire inside "Mitarbeiter",
    while a Finnish stem still matches its inflections and "on site" still matches "on
    sites". Short entries are the exception and get a trailing boundary too: measured on
    real listings, a bare "coo" was matching inside "cookies" and deleting 33 postings for
    having a cookie banner.

    `vocabulary` is the profile whose words are read. None is the Junior profile -- this
    module's own country_rules -- which is every call this app made before the Entry, Mid
    and Senior profiles existed, so all of those behave exactly as they did. Each profile
    keeps its own complete word lists (Sina: "حتی اگر Redundancy باشه"); this matching
    engine is the one thing they share, and it has no words of its own.
    """
    vocab = vocabulary if vocabulary is not None else country_rules
    key = (vocab.__name__, section, str(country or ''), str(location or ''),
           str(detected or ''))
    pattern = _COUNTRY_PATTERN_CACHE.get(key)
    if pattern is None:
        terms = vocab.terms_for(section, country, location, detected)
        if terms:
            parts = []
            for term in sorted(terms, key=len, reverse=True):
                parts.append(re.escape(term) + (r'\b' if len(term) <= 3 else ''))
            pattern = re.compile(r'\b(?:%s)' % '|'.join(parts))
        else:
            pattern = re.compile(r'(?!)')
        _COUNTRY_PATTERN_CACHE[key] = pattern
    return pattern


# Where each section's words have to appear to mean anything.
#
# Seniority is the section this exists for. Matched against the whole posting it deleted
# 594 of 1,160 real listings, and reading the verdicts, nearly all were wrong: "partner"
# fired on a PhD posting that mentioned project partners, "manager" on an entry-level
# engineering role that mentioned the hiring manager, "hoofd" inside the Dutch word for
# head OFFICE, "coo" inside "cookies". A seniority word states the seniority of the job
# only when it is in the job title; anywhere else it is describing somebody else.
_SECTION_SCOPE = {
    'senior': 'title',
}


def _section_text(section, row, vocabulary=None) -> str:
    # A profile declares which of ITS sections are title-only; the Junior profile's answer
    # is _SECTION_SCOPE above.
    scope = getattr(vocabulary, 'SECTION_SCOPE', None) if vocabulary is not None else None
    if (scope if scope is not None else _SECTION_SCOPE).get(section) == 'title':
        parts = [row.get('title'), row.get(ORIGINAL_TITLE_KEY)]
        return ' '.join(str(part) for part in parts if part).lower()
    return rule_text(row)


def country_rule_hit(section, row, vocabulary=None):
    """The matched term from `section` in this listing's own languages, or ''.

    Reads the listing as the board wrote it AND as translated -- so every rule is asked
    twice: once in the posting's own language, once in English. Sina's requirement, and it
    is what makes the per-country vocabulary worth having: a Finnish posting is judged on
    its own words before translation could mangle them, and on the English ones afterwards.

    `vocabulary` picks the profile whose words are read; None is the Junior profile.
    """
    match = _country_pattern(section, row.get('country'), row.get('location'),
                             _row_language(row), vocabulary
                             ).search(_section_text(section, row, vocabulary))
    return match.group(0) if match else ''


COUNTRY_LANGUAGE_SECTION = 'other_language_required'


def country_language_rule_hit(row, vocabulary=None):
    """The second-language hit from the country vocabulary, unless English is named beside it.

    THE SECOND PLACE THE LANGUAGE QUESTION IS ANSWERED, AND IT NEARLY MISSED T-12.

    `language.requires_language_besides_english` reads the posting with regexes and knows
    about levels, conjunctions and qualifiers. This section is a flat list of phrases per
    country -- 'fluent dutch', 'deutschkenntnisse', 'vloeiend nederlands' -- and it is not
    redundant: it catches shapes the regexes have no level word for ('german required',
    'deutsch zwingend', 'nederlands vereist', 'nederlandstalig').

    But it had no idea English existed. When Sina asked for the pairing to be kept
    ("اگر به صورت ترکیبی میگفت انگلیسی و یه زبان دیگه باید این رو هم قبول بکنه") and the
    regex rule was changed to keep it, THIS list went on deleting it: "Fluent Dutch and
    English required" contains 'fluent dutch', and nothing here looked at the rest of the
    sentence. The first real Filter run after the change kept only 10 pairings out of the
    385 the regex rule had stopped deleting, which is what exposed it.

    So it cancels exactly the way the regex rule cancels, through the same function and the
    same window -- one question, one answer. Every hit is walked rather than just the first,
    because a posting can name Dutch twice and only pair English with one of them.
    """
    from .language import names_english_beside
    text = _section_text(COUNTRY_LANGUAGE_SECTION, row, vocabulary)
    pattern = _country_pattern(COUNTRY_LANGUAGE_SECTION, row.get('country'),
                               row.get('location'), _row_language(row), vocabulary)
    for match in pattern.finditer(text):
        if not names_english_beside(text, match.start(), match.end()):
            return match.group(0)
    return ''


def silent_about_english(row, vocabulary=None) -> bool:
    """True when a non-English posting never once names English, in any spelling.

    Sina's rule, and it runs BEFORE translation, which is the whole point: a Dutch employer
    who writes 2,000 characters of Dutch and never mentions English almost certainly wants
    Dutch. Deleting it here costs nothing, where deleting it after translation would mean
    paying to translate it first -- on the real Netherlands data this is 503 listings and
    92% of the entire DeepL bill.

    Two things make it safe rather than a blunt "is it foreign" test:

      * The listing's OWN word for English counts. Of the 553 non-English Netherlands
        listings, 47 said "Engels" and only 3 said "English" -- looking for the English
        word alone would have deleted 47 real ones.
      * The match is on the ORIGINAL text, not a translation, because a translation turns
        "Engels" into "English" and makes every listing look like it mentioned it.

    A listing already in English is never touched: it is written in the language Sina reads.

    And a source that returns no description is exempt, for the same reason it is exempt
    from the Work Location rule: there is no text for the word to appear in, and none to
    detect a language from either. A real arbeitsagentur.de row arrives with the whole
    description "Data Scientist at Jenoptik AG" -- twenty-nine characters of English, which
    the language detector reads as Danish, after which this rule deletes it for never
    mentioning English. Four sources are like this by design (arbeitsagentur.de, Jooble,
    jobs.ch, SwissDevJobs) and this is exactly the shape that once made all four produce
    nothing but deletions.
    """
    if is_true_flag(row.get('thin_description')):
        return False
    if not is_true_flag(row.get(NEEDS_TRANSLATION_KEY)):
        return False
    parts = [row.get(ORIGINAL_TITLE_KEY) or row.get('title'),
             row.get(ORIGINAL_DESCRIPTION_KEY) or row.get('description')]
    text = ' '.join(str(part) for part in parts if part).lower()
    return not _country_pattern('english_mention', row.get('country'),
                                row.get('location'), _row_language(row),
                                vocabulary).search(text)


def passes_work_location_rule(row, vocabulary=None):
    """The Work Location rule -- one rule, in the listing's own language and in English.

    Named Work Location, not "the Remote rule", because Claude's own screening prompt has a
    Rule 2 called the Remote rule and the two were being confused in the Log and in
    conversation. This is the cheap keyword rule that runs early; Claude's is the judgement
    that runs last on what survives. Same subject, different stage.

    It replaced two separate rules that used to run at different points in the Filter, one
    before translation and one after. They are merged here, as Sina asked, and it reads
    rule_text -- the listing as the board wrote it AND as translated -- so both are asked
    at once, in whichever of the two the evidence happens to be.

    Three questions, in this order:

      1. Milan or Turin anywhere in the listing -> keep, unconditionally.
      2. An on-site/hybrid term, with no remote term anywhere -> drop.
         The "with no remote term" half is not a softening. Measured on 2,848 real
         listings, 1,549 mentioned remote work and 1,204 of those were being dropped --
         562 purely because the word "hybrid" appeared somewhere on the page, almost
         always in the board's own filter menu ("Workplace: Full Remote | Hybrid |
         On-site"), which is the site's control panel, not a statement about the role.
      3. A phrase that explicitly denies remote work ("kein Homeoffice", "ei etätyötä",
         "solo in sede") -> drop, whatever else the page says.

    And a fourth: the posting has to say, somewhere, that the work can be done away from an
    office. Silence drops it.

    That requirement was removed once and then restored, and the reason for restoring it is
    worth keeping. Removed, it let through 128 listings that said nothing whatsoever about
    working arrangements -- Dutch office jobs that simply never raise the subject. Claude
    then deleted them anyway, writing "on-site role in Amsterdam" for each, which the text
    never said. So the listings died regardless; the only difference was that they were
    translated and screened first, at real cost, and that the stated reason was invented.
    Sina's call is that silence in a Dutch job advert means an office job, and that he would
    rather not read 128 of them.

    The exemption is the part that matters: a source that returns no description at all has
    not been silent, it had nothing to say. arbeitsagentur.de, Jooble, jobs.ch and
    SwissDevJobs are like that by design, and this exact requirement is what previously made
    all four produce deletions and nothing else.

    NOT REMOTE. When the row is being filtered for Not Remote (search_title.WORK_MODE_ROW_KEY),
    the same words are read and the other answer kept -- see passes_not_remote_rule. Remote is
    everything above, unchanged.
    """
    if is_any_workplace(row):
        return True
    if is_not_remote(row):
        return passes_not_remote_rule(row, vocabulary)
    # LINKEDIN'S OWN TAG, read before any wording. A row from apimaestro/linkedin-jobs-scraper
    # -api carries `workplace_type` -- the Hybrid / On-site / Remote chip Sina sees on the page
    # and no other source can give us -- and it is the most reliable thing this rule is ever
    # told. It exists because three adverts in a row that he opened were tagged Hybrid and had
    # been kept: VisionBI (two days at the client's site, and "of gewoon remote" at the end of
    # the sentence), KLM (working from home only "als je functie dit toelaat") and IDPP, whose
    # text literally says "Working Model: Remote" while the tag says Hybrid. The last one no
    # rule that reads wording can ever catch.
    #
    # Placed after the Milan/Turin exemption, which is absolute, and before everything else.
    tag = clean_workplace(row.get('workplace_type'))
    if tag in (WORKPLACE_HYBRID, WORKPLACE_ONSITE):
        return False
    if tag == WORKPLACE_REMOTE:
        # The tag is the poster's own statement, so the word "remote" is no longer required
        # and a stray "located in" cannot overrule it. What still can is a phrase that denies
        # remote work outright, or a stated number of office days -- an advert tagged Remote
        # that also says "three days a week in our office" is contradicting its own tag, and
        # the cautious reading is the one that keeps the home office honest.
        if country_rule_hit('not_remote', row, vocabulary):
            return False
        return not says_office_attendance_is_required(rule_text(row))
    if (not country_rule_hit('remote', row, vocabulary)
            and country_rule_hit('on_site', row, vocabulary)):
        return False
    if country_rule_hit('not_remote', row, vocabulary):
        return False
    # The posting commits the role to office time, whatever else it says. This sits after the
    # checks above and before the thin-description exemption on purpose: it must be able to
    # overrule a stray "remote" in a sentence that is itself describing a hybrid arrangement,
    # which is the gap Sina found, and it must NOT fire on a source that returned no text.
    if says_office_attendance_is_required(rule_text(row)):
        return False
    if is_true_flag(row.get('thin_description')):
        # Not silence -- these four sources (arbeitsagentur.de, Jooble, jobs.ch,
        # SwissDevJobs) return no description text at all, by design, so the word could
        # never appear however remote the job is. Dropping them here is what made all four
        # produce nothing but deletions before. They go to Claude with what little they have.
        return True
    hit = country_rule_hit('remote', row, vocabulary)
    if not hit:
        return False
    # A remote word that only says the role MIGHT be remote is not the posting saying it is.
    # KLM's advert reached him because of one: "Als je functie dit toelaat: thuiswerken en tot
    # 8 weken werken vanuit het buitenland" -- if your role allows it, working from home --
    # sits in the benefits list, twice, and was the whole of its claim. Overruled by an
    # unambiguous full-remote statement elsewhere in the text, which is what the same escape
    # hatch does for every other rule here. Measured: 7 listings on the Bank, all of them read.
    text = rule_text(row)
    if not _ALSO_FULLY_REMOTE.search(text) and _remote_only_when_hedged(text, hit):
        return False
    return True


# "If your role allows it", "where possible", "in overleg": the posting leaves remote work to
# be agreed, which makes it a perk and not a property of the job.
_HEDGED_REMOTE = re.compile(
    r'\b(?:als|indien|if|wenn)\b[^.;!?\n]{0,44}?'
    r'\b(?:toelaat|toestaat|allows?|allowed|mogelijk|possible|erlaubt|zul[äa]sst)\b'
    r'|\bwaar\s+mogelijk\b|\bwhere\s+possible\b|\bindien\s+mogelijk\b'
    r'|\bif\s+your\s+(?:function|role|position|job)\b'
    r'|\bin\s+overleg\b|\bby\s+arrangement\b|\bon\s+request\b|\bop\s+aanvraag\b',
    re.I)


def _remote_only_when_hedged(text, hit) -> bool:
    """True when EVERY occurrence of the remote term sits inside a hedge.

    One unhedged occurrence is enough to say the role is remote, so this is all-or-nothing:
    a posting that says "remote" plainly once and "als je functie dit toelaat: thuiswerken"
    once is not hedged.
    """
    spots = list(re.finditer(re.escape(hit), text, re.I))
    if not spots:
        return False
    for spot in spots:
        if not _HEDGED_REMOTE.search(text[max(0, spot.start() - 90):spot.end() + 40]):
            return False
    return True


# What a posting says when the role really does need you in an office, as opposed to when the
# word "hybrid" merely appears on the page.
#
# That distinction is the whole of this. Rule 2 above drops an on-site term only when no
# remote term appears anywhere, and that softening was measured and is right: of 2,848 real
# listings, 562 were being dropped purely because "hybrid" sat in the board's own filter menu
# ("Workplace: Full Remote | Hybrid | On-site"), which is the site's control panel, not a
# statement about the job. More carry it about *architecture* -- "hybriden Architekturen
# (On-Premise und Cloud)" -- which is the F-2 trap in another language.
#
# But the softening left a real gap, and Sina found two listings in it:
#
#   "BERLIN, DÜSSELDORF, HAMBURG, KÖLN, HYBRID, MÜNCHEN … Hybrides Arbeiten: Ein
#    individueller Mix aus remote working, Zeit im Office oder beim Kunden vor Ort"
#   "Location: Hybrid in Chelsea District, NY OR Century City, Los Angeles"
#
# Both say plainly that the role is hybrid, and both survived because the word "remote"
# appears inside the very sentence that says so.
#
# So the question asked here is not "is the word there" but "does the posting COMMIT to office
# time": a number of office days, a hybrid bound to a named place, or a mix that names the
# office as part of the arrangement. Measured on the Bank: 484 of the 4,093 listings that pass
# the Remote rule, 11.8%, and a random sample of them read by eye.
_OFFICE_WORD = (r'(?<!home[-\s])(?<!home)office|(?<!home[-\s])b[üu]ro|kantoor|bureau|'
                r'ufficio|oficina|kontor|toimisto|on[-\s]?site|vor\s+ort|in\s+sede|presencial|'
                # A CLIENT'S site is an address he would have to travel to just as an office
                # is. VisionBI's advert -- "gemiddeld twee dagen op de klant locatie" -- survived
                # for exactly this reason: _DAYS_IN_OFFICE wanted a number of days beside an
                # office word and "klant locatie" was not one, in any language. Measured on
                # the Bank: 10 listings newly dropped, all ten genuinely hybrid ("hybride
                # werken: op ons hoofdkantoor in de meern, bij de klant of vanuit huis"), and
                # none newly kept.
                r'klant\s?locatie\w*|bij\s+de\s+klant|client\s+sites?|client\s+locations?|'
                r'customer\s+sites?|customer\s+locations?|at\s+the\s+client|'
                r'client\s+premises|beim\s+kunden|kundenstandort\w*|chez\s+le\s+client|'
                r'presso\s+il\s+cliente|sede\s+del\s+cliente|hos\s+kunden?')

# The lookbehinds are not decoration. "up to 2 days of home office per week" is working FROM
# home -- the opposite of what this rule looks for -- and without them the word "office"
# inside it turned a remote-friendly benefit into an office requirement.
# The number of days is spelled out as often as it is written in figures, and in the posting's
# own language: "twee dagen per week op kantoor", "zwei Tage im Büro". The pattern knew
# only the English words, so every Dutch and German advert that spelled it out was invisible
# to it -- including VisionBI's, "gemiddeld twee dagen op de klant locatie". Measured on the
# Bank: 11 listings newly dropped, every one of them literally "twee dagen per week op
# kantoor / bij de klant" or the same in another language, and none newly kept.
_NUMBER_WORD = (r'one|two|three|four|[1-4]|twee|drie|vier|zwei|drei|deux|trois|quatre|'
                r'due|tre|quattro|dos|tres|cuatro')
_DAYS_IN_OFFICE = re.compile(
    r'\b(?:%s)\s+(?:recommended\s+|required\s+|fixed\s+|vaste\s+|feste\s+)?'
    r'(?:days?|tage?|dagen|dagar|giorni|d[ií]as|jours)\b[^.;!?\n]{0,30}?\b(?:%s)\b'
    r'|\b(?:%s)\b[^.;!?\n]{0,24}?\b(?:%s)\s+'
    r'(?:days?|tage?|dagen|giorni|d[ií]as|jours)\b'
    % (_NUMBER_WORD, _OFFICE_WORD, _OFFICE_WORD, _NUMBER_WORD), re.I)

_HYBRID_AT_A_PLACE = re.compile(r'\bhybrid\w*\s+(?:in|at|en|à|a)\s+[A-ZÄÖÜ][\w.\-]+', re.I)

# A share of the week in an office is a commitment whether or not the word "hybrid" is
# anywhere near it: "Work 40% at the office, 40% from home", "ongeveer 50% aanwezigheid op
# kantoor". Added after a probe taken verbatim from a real listing turned out to be caught by
# none of the other three -- the test was right and the patterns were one short.
_PERCENT_IN_OFFICE = re.compile(
    r'\b[1-9][0-9]?\s*%%[^.;!?\n]{0,24}?\b(?:%s)\b' % _OFFICE_WORD, re.I)

_MIX_NAMING_THE_OFFICE = re.compile(
    r'\bhybrid\w*\b[^.;!?\n]{0,90}?\b(?:%s)\b'
    r'|\b(?:%s)\b[^.;!?\n]{0,90}?\bhybrid\w*\b' % (_OFFICE_WORD, _OFFICE_WORD), re.I)

# A company that calls itself office-first has said where the work happens, in two words.
# Found on 30 Bank listings, every one of them phrased like Adyen's: "This role is based out
# of our Amsterdam office. We are an office-first company and value in-person collaboration".
# The opposite claim, "remote-first", is already in the escape hatch below.
_OFFICE_FIRST = re.compile(r'\boffice[-\s]?first\b|\bb[üu]ro[-\s]?first\b', re.I)

# A small number of days AT HOME is a statement about the other days of the week. Every
# pattern above reads stated OFFICE days, and adverts say it the other way round at least as
# often: "the freedom to work from home two days a week", "Hybride werken met minimaal 2
# dagen per week thuiswerken", "eligible for remote work for up to 2 days per week". 96 Bank
# listings, and one of them is the advert Sina reported.
#
# Capped at three days on purpose: four or five days at home is a remote job with an
# occasional desk, not a commitment to an office.
_LIMITED_HOME_DAYS = re.compile(
    r'\b(?:work(?:ing)?\s+from\s+home|home[-\s]?office|homeoffice|thuiswerk\w*|'
    r'telewerk\w*|remote)\b[^.;!?\n]{0,28}?'
    r'\b(?:one|two|three|[1-3])\s+(?:days?|tage?n?|dagen)\b'
    r'|\b(?:one|two|three|[1-3])\s+(?:days?|tage?n?|dagen)\b[^.;!?\n]{0,28}?'
    r'\b(?:work(?:ing)?\s+from\s+home|home[-\s]?office|homeoffice|thuiswerk\w*|'
    r'telewerk\w*)\b', re.I)

# A share of the week spent AWAY from the office is a statement about the rest of it. The twin
# of _LIMITED_HOME_DAYS, for percentages instead of days, and it exists because Sina reported
# HDI's "Data Scientist: Advanced Analytics & AI Engineer" arriving as Full Remote on this:
#
#     "Mobile working: Whether from home or on the go - our mobile working model
#      (up to 60% mobile) offers you more freedom and independence."
#
# 60% mobile is 40% in Hanover or Cologne. Not one of the six patterns above fired:
# _PERCENT_IN_OFFICE wants a percentage beside an OFFICE word, and this advert states the share
# that is not. The same blind spot the days patterns had, in the other unit.
#
# ANYTHING BELOW 100% IS NOT REMOTE, AND THAT IS THE WHOLE RULE
#
# Caught on 364 Bank listings, spread by how much of the week they call remote:
#
#     1-39%   120        "20% mobile"
#     40-59%  147        "bis zu 50 % mobiles Arbeiten"
#     60-69%   63        "60% remote"  <- HDI, the listing Sina reported
#     70-79%   10
#     80-89%    7        "80% Remote", "85% remote"
#     90-99%   17        "zu etwa 95 % remote möglich"
#
# I set the bound at 70 first, on the argument that a 95%-remote post with "Gelegentlich finden
# Workshops" is work he can do from home. He overruled it in one line -- "آقا Remote باشه دیگه
# / یعنی چی 70 درصد" -- and he is right, for a reason the percentage hides: the 5% is spent at
# an address. HDI's is Hanover or Cologne. A job that needs him in a German office one week in
# twenty is not a job he can hold from where he lives, and calling it 95% remote does not
# change that.
#
# So every stated share below 100 is an office commitment. All 364.
#
# 100 itself is outside the range, and the guards for it are load-bearing: "100% remote", "bis
# zu 100 % mobiles Arbeiten" and "100% home office" are fully remote, and catching them here
# would invert the rule this pattern belongs to. The negative lookahead on the second branch is
# what stops "10" being read out of "100".
_PERCENT_AT_HOME = re.compile(
    r'\b(?:[1-9]|[1-9][0-9])\s*%%?\s*(?:[^.;!?\n]{0,18}?)\b'
    r'(?:remote|mobil\w*|home[-\s]?office|homeoffice|work\w*\s+from\s+home|telework\w*|'
    r'thuiswerk\w*|t[eé]l[eé]travail)\b'
    r'|\b(?:remote|mobiles?\s+arbeiten|mobil\w*|home[-\s]?office|homeoffice|'
    r'work\w*\s+from\s+home|telework\w*|thuiswerk\w*)\b[^.;!?\n]{0,22}?'
    r'\b(?:[1-9]|[1-9][0-9])\s*%%?(?!\s*\d)', re.I)

# A workation allowance -- a few weeks a year from wherever you like -- is a perk on an
# office job, not a remote job. This exists because of the listing Sina reported: Glovo's
# advert says "office-first culture" and "work from home two days a week", and it reached him
# anyway, because "the opportunity to work from anywhere for up to three weeks a year" fired
# the escape hatch below and skipped every check in this rule. The bound is what gives it
# away: real remote work is not measured in weeks per year.
_WORKATION = re.compile(
    r'\b(?:work|arbeiten|werken)\s+(?:from\s+)?(?:anywhere|abroad|from\s+abroad|remotely)\b'
    r'[^.;!?\n]{0,40}?\b(?:up\s+to\s+)?'
    # Spelled out as often as in figures -- "up to three weeks a year" -- and a digits-only
    # pattern read straight past the advert that prompted this.
    r'(?:\d+|one|two|three|four|five|six|eight|ten|twelve|a\s+few|several)\s*'
    r'(?:weeks?|days?|months?|wochen|tage|dagen|maanden|monate)\b'
    r'[^.;!?\n]{0,20}?\b(?:a|per|pro|im)\s+(?:year|jahr|jaar)\b', re.I)

# The escape hatch, and it matters as much as the patterns. A posting that offers a fully
# remote option alongside a hybrid one is still a remote job: "Standort in Dresden (hybrid)
# oder remote deutschlandweit".
_ALSO_FULLY_REMOTE = re.compile(
    r'\b(?:100\s*%|fully|completely|komplett|vollst[äa]ndig|volledig)\s*remote\b'
    r'|\boder\s+remote\b|\bor\s+(?:fully\s+)?remote\b'
    r'|\bremote\s+(?:deutschlandweit|weltweit|worldwide|anywhere|from\s+anywhere)\b'
    r'|\bwork\s+from\s+anywhere\b|\bremote[-\s]?first\b', re.I)

# Hybrid cloud, not a hybrid desk.
_HYBRID_IS_TECHNICAL = re.compile(
    r'\bhybrid\w*\s+(?:cloud|architect\w*|system\w*|infrastruktur\w*|infrastructure|'
    r'setup|environment|landschaft\w*|szenarien)'
    r'|\bhybriden?\s+(?:architektur\w*|systemlandschaft\w*|umgebung\w*)', re.I)

# "vor 1 Tag" is how old a NEIGHBOURING job card is, not how many days in the office. Four of
# the first sample's catches were this: a German board's sidebar, read as an office rota.
_DAYS_ARE_AN_AGE = re.compile(
    r'vor\s+\d+\s+Tag|\d+\s+(?:days?|tagen?)\s+ago|hace\s+\d+', re.I)


def says_office_attendance_is_required(text) -> bool:
    """Does this posting commit the role to time in an office?

    Deliberately silent unless it does. Everything this returns True for is removed from a
    Remote search, so the cost of a false positive is a job Sina never sees.
    """
    body = ' '.join(str(text or '').split())
    if not body:
        return False

    # EVERY place the escape hatch fires is examined, not just the first, and a workation
    # perk does not count as one. Reading only the first match is what let Glovo's
    # office-first advert through: "work from anywhere for up to three weeks a year" was the
    # leftmost match, and the rule returned before looking at anything else. Checking them
    # all also means a listing that really does say "100% remote" somewhere still escapes,
    # however many workation perks it lists first.
    for hatch in _ALSO_FULLY_REMOTE.finditer(body):
        nearby = body[max(0, hatch.start() - 40):hatch.end() + 90]
        if not _WORKATION.search(nearby):
            return False

    for pattern in (_DAYS_IN_OFFICE, _PERCENT_IN_OFFICE, _HYBRID_AT_A_PLACE,
                    _MIX_NAMING_THE_OFFICE, _OFFICE_FIRST, _LIMITED_HOME_DAYS,
                    _PERCENT_AT_HOME):
        found = pattern.search(body)
        if not found:
            continue
        around = body[max(0, found.start() - 60):found.end() + 60]
        if _HYBRID_IS_TECHNICAL.search(around) or _DAYS_ARE_AN_AGE.search(around):
            continue
        return True
    return False


def passes_not_remote_rule(row, vocabulary=None):
    """The Work Location rule for a Not Remote search: the same words, the other answer.

    Sina's rule: "اگر Not Remote رو زدیم هر چی به غیر از این رو بیاره". Remote keeps a posting
    that says the work can be done away from an office; this drops exactly that posting and
    keeps everything else.

    It mirrors the Remote rule's caution rather than inverting it blindly. The Remote rule
    drops an on-site term only when no remote term appears anywhere, because a board's own
    filter menu ("Full Remote | Hybrid | On-site") puts both words on nearly every page. So
    this drops a remote term only when no on-site or hybrid term appears anywhere -- a page
    carrying both is left for Claude to read, in both searches.

      1. A phrase that denies remote work ("kein Homeoffice", "solo in sede") -> keep.
      2. An on-site or hybrid term anywhere -> keep.
      3. No description at all -> keep; there was nothing to read, and Claude decides.
      4. A remote term, with none of the above -> drop.
      5. Silence -> keep. A posting that never mentions remote work is not a remote role.

    The Milan and Turin exception does not apply here. It exists because Sina can reach any
    arrangement in the city he lives in, which is a Remote-search question; a Not Remote
    search keeps every role that is not remote, in those two cities and everywhere else.
    """
    # LinkedIn's tag decides it when there is one, in the other direction: Remote is exactly
    # what a Not Remote search does not want, and Hybrid or On-site is exactly what it does.
    tag = clean_workplace(row.get('workplace_type'))
    if tag == WORKPLACE_REMOTE:
        return False
    if tag in (WORKPLACE_HYBRID, WORKPLACE_ONSITE):
        return True
    if country_rule_hit('not_remote', row, vocabulary):
        return True
    if country_rule_hit('on_site', row, vocabulary):
        return True
    if is_true_flag(row.get('thin_description')):
        return True
    return not country_rule_hit('remote', row, vocabulary)


def is_unpaid(row):
    """Drops listings that are unpaid/volunteer/self-funded rather than a real job.

    Measured on the same 2,542 real listings that exposed the old version: this deletes 4,
    where the old one deleted 222. All four were read and all four are right -- "This is an
    UNPAID volunteer opportunity", "an unpaid internship structure", "an equity-only role,
    no salary at this stage", and "a full-time, non-paid, remote internship role". Nothing
    the old rule caught correctly is missed, and 218 real listings stop being thrown away.
    """
    text = f"{row.get('title') or ''} {row.get('description') or ''}"
    return bool(_UNPAID_PATTERN.search(text) or _UNPAID_NO_SALARY.search(text))


def is_too_senior(row):
    """Drops listings aimed at senior/leadership hires, based on title/description
    keywords, LinkedIn's own seniorityLevel field, and "N+ years" / "N-M years" asks."""
    seniority_level = str(row.get('seniority_level') or '').strip().lower()
    if seniority_level in SENIOR_LEVEL_FIELD_VALUES:
        return True

    # The title states the level; the description only counts where it names this role's
    # own title. See _SENIOR_TITLE_PATTERN for the 797 listings the old "anywhere in the
    # text" test was deleting. Measured on the same 2,542: 1,563 deletions become 908, with
    # 655 listings recovered and NOT ONE newly deleted, and 849 listings survive every
    # keyword rule where 430 did before.
    title = str(row.get('title') or '')
    if _SENIOR_TITLE_PATTERN.search(title):
        return True
    description = str(row.get('description') or '')
    if (_SENIOR_ROLE_DEFINING_PATTERN.search(description)
            or _SENIOR_WANTED_PATTERN.search(description)):
        return True

    combined_text = f"{row.get('title') or ''} {row.get('description') or ''}".lower()

    # All three experience patterns below require the literal substring "year" (they end
    # in `years?`), so if it isn't present none of them can possibly match. Checking that
    # first is provably equivalent and far cheaper: measured over 800 real-length
    # postings, the three regex scans cost ~1,080 ms while this substring test costs
    # ~10 ms, and a great many listings never mention years of experience at all.
    if 'year' not in combined_text:
        return False

    if SENIOR_EXPERIENCE_PATTERN.search(combined_text):
        return True

    for span in SENIOR_EXPERIENCE_RANGE_PATTERN.finditer(combined_text):
        low, high = int(span.group(1)), int(span.group(2))
        if high < low:
            continue
        # A range of years is not always a range of experience. Measured over all five real
        # corpora: 272 matches, 208 of them beside an experience word, 5 beside an age word
        # ("highly motivated graduates aged 18 to 28 years" -- a VIE graduate programme,
        # dropped as too senior), and no experience range anywhere starts at 12 or more. So
        # two guards, both narrow: an age word nearby disqualifies the range outright, and a
        # lower bound of 12+ has to be vouched for by an experience word.
        around = combined_text[max(0, span.start() - 90):span.end() + 90]
        if _AGE_RANGE_WORDS.search(around):
            continue
        if low >= 12 and not _EXPERIENCE_WORDS.search(around):
            continue
        return True

    match = SENIOR_MIN_YEARS_PATTERN.search(combined_text)
    if match:
        # Only treat a bare "N years ... experience" as senior when the sentence it sits
        # in actually frames it as a requirement, and doesn't explicitly waive one. See
        # _SENIOR_REQUIREMENT_WORDS/_WAIVERS for the real false positives this closes.
        start = combined_text.rfind('.', 0, match.start()) + 1
        end = combined_text.find('.', match.end())
        sentence = combined_text[start:end if end != -1 else len(combined_text)]
        if not any(waiver in sentence for waiver in _SENIOR_REQUIREMENT_WAIVERS):
            if any(word in sentence for word in _SENIOR_REQUIREMENT_WORDS):
                return True

    return False


# THIS TABLE WAS ENGLISH ONLY, AND THE DUTCH SOURCES SEND DUTCH.
#
# Whatever is not here used to be returned UNCHANGED -- `_EMPLOYMENT_TYPE_LABELS.get(value,
# value)` -- so a raw source word became a category of its own. Measured on the 4,325-row
# Netherlands Bank: 72 rows filed as **Tijdelijk** and 39 as **Vast**, which are simply Dutch
# for temporary and permanent. werk.nl, Jooble NL and EURES all send them.
#
# What that cost: 'Vast' means a permanent full-time job, and those 39 could not be found by
# ticking Full-Time, because their Type was the word "Vast". They also fell outside
# CATEGORY_ORDER, so they sorted nowhere, and outside CATEGORY_BADGE_COLORS, so the Jobs
# table painted them with the fallback grey.
_EMPLOYMENT_TYPE_LABELS = {
    'full-time': 'Full-Time',
    'part-time': 'Part-Time',
    'contract': 'Contract',
    'temporary': 'Temporary',
    'internship': 'Internship',
    'volunteer': 'Volunteer',
    'other': 'Other',
    # Dutch -- werk.nl, Jooble NL, EURES.
    'vast': 'Full-Time',
    'vaste baan': 'Full-Time',
    'voltijd': 'Full-Time',
    'fulltime': 'Full-Time',
    'deeltijd': 'Part-Time',
    'parttime': 'Part-Time',
    'bijbaan': 'Part-Time',
    'tijdelijk': 'Temporary',
    'uitzendwerk': 'Temporary',
    'detachering': 'Contract',
    'freelance': 'Contract',
    'zzp': 'Contract',
    'stage': 'Internship',
    'stageplaats': 'Internship',
    'werkstudent': 'Internship',
    'afstudeerstage': 'Thesis',
    'afstudeeropdracht': 'Thesis',
    # German -- arbeitsagentur.de, Jooble DE.
    'vollzeit': 'Full-Time',
    'festanstellung': 'Full-Time',
    'unbefristet': 'Full-Time',
    'teilzeit': 'Part-Time',
    'befristet': 'Temporary',
    'zeitarbeit': 'Temporary',
    'praktikum': 'Internship',
    'werkstudium': 'Internship',
    'abschlussarbeit': 'Thesis',
    'freiberuflich': 'Contract',
    # French, Italian, Spanish, Portuguese, Nordic -- EURES reaches all of these.
    'temps plein': 'Full-Time', 'cdi': 'Full-Time',
    'temps partiel': 'Part-Time', 'cdd': 'Temporary', 'stage ': 'Internship',
    'tempo pieno': 'Full-Time', 'indeterminato': 'Full-Time',
    'tempo parziale': 'Part-Time', 'determinato': 'Temporary',
    'tirocinio': 'Internship',
    'jornada completa': 'Full-Time', 'indefinido': 'Full-Time',
    'jornada parcial': 'Part-Time', 'practicas': 'Internship',
    'tempo integral': 'Full-Time', 'meio periodo': 'Part-Time',
    'heltid': 'Full-Time', 'deltid': 'Part-Time', 'vikariat': 'Temporary',
    'kokoaika': 'Full-Time', 'osa-aika': 'Part-Time',
}


def categorize(row):
    """What kind of role this is: the Type column, and what the Filter window's Type choice
    filters on.

    It stopped being purely informational the day that choice was wired up, which is when
    its mistakes started reaching Sina. The rules it uses, and the three drafts thrown away
    for relabelling thousands of real listings wrongly, are documented at the top of this
    module.

    'Full-Time' is the answer when the listing says nothing. It is a real answer, not a
    missing one -- it is what the Type column prints, and the Filter agrees with the column
    rather than contradicting it.
    """
    said = category_from_words(row)
    if said:
        return said

    employment_type = str(row.get('employment_type') or '').strip()
    if employment_type and employment_type.lower() != 'nan':
        # An unrecognised value becomes 'Other', never itself. Returning the raw word is
        # what put "Vast" and "Tijdelijk" in the Type column: 111 listings filed under a
        # category the Filter window cannot offer, CATEGORY_ORDER cannot sort and
        # CATEGORY_BADGE_COLORS has no colour for. 'Other' is at least a word the app
        # knows, and the raw value stays on the row as `employment_type` for anyone who
        # wants to see what the board actually said.
        return _EMPLOYMENT_TYPE_LABELS.get(employment_type.lower(), 'Other')

    return 'Full-Time'


# ------------------------------------------------------------------ what level it is ----
#
# WHY THIS EXISTS, AND WHY IT CLASSIFIES RATHER THAN FILTERS
#
# The Level used to be a filter and nothing else: `search_level` picked a profile, the
# profile's `is_wrong_level` deleted whatever did not match, and no row ever carried what
# level it actually was. Sina's decision, after seeing the numbers: "نباید Filter کنه باید
# اون هارو دسته بندی کنه ... اول بر اساس Seniority Groupby میکنی و بعد بر اساس Type و دیگه
# هیچی نباید حذف بشه" -- group by seniority, then by type, and delete nothing. He picks in
# the table, the way he picks the Type.
#
# So this is `categorize`'s twin: it reads the listing and returns a word, and the Jobs table
# prints it in a column with an Excel-style filter button over it.
#
# THREE SOURCES, IN THIS ORDER, AND THE ORDER IS THE DESIGN
#
#   1. The TITLE, whole words only. An employer who writes "Senior Data Scientist" has said
#      what the role is, and no amount of body text outranks that. Whole words because this
#      module has just been bitten by the substring version of exactly this mistake --
#      a city-name test once matched "turin" inside "manufacturing" and waved 386
#      listings past the Remote rule.
#   2. LINKEDIN'S OWN FIELD, `seniority_level`, which only LinkedIn sends. Measured on the
#      4,325-row Netherlands Bank: of the rows that reach Claude it is absent on most, and
#      where present it reads "Not Applicable" more often than anything else. So it is a
#      corroboration, not a primary source -- and its "Mid-Senior level" bucket deliberately
#      maps to Mid rather than Senior, because it covers both and guessing the harder of the
#      two would hide mid-level work behind a Senior label.
#   3. SILENCE -> 'Unspecified'. Not 'Mid', not 'Junior'. The Type column answers silence
#      with 'Full-Time' because that is the honest default for a contract; there is no
#      honest default for seniority, and inventing one would put a word in the column that
#      the posting never said. 'Unspecified' is a real answer and it is filterable.
_SENIORITY_TITLE_WORDS = (
    # Checked in this order, first match wins, so the more senior reading of a title that
    # carries two words ("Senior Data Engineer, Junior Team") is the one that survives.
    ('Lead', (r'lead', r'leading', r'principal', r'staff', r'head\s+of', r'director',
              r'vp', r'vice\s+president', r'chief', r'teamlead', r'team\s+lead',
              r'hoofd', r'leitend\w*', r'teamleider')),
    ('Senior', (r'senior', r'sr\.?', r'experienced', r'ervaren', r'erfahren\w*',
                r'medior[-\s]?senior')),
    ('Mid', (r'mid[-\s]?level', r'mid', r'intermediate', r'medior', r'regular')),
    ('Junior', (r'junior', r'jr\.?', r'entry[-\s]?level', r'graduate', r'new\s+grad',
                r'starter', r'startersfunctie', r'afgestudeerde', r'associate',
                r'trainee', r'einsteiger', r'berufseinsteiger')),
    ('Intern', (r'intern', r'internship', r'stagiair\w*', r'stage', r'werkstudent',
                r'praktikant\w*', r'afstudeerstage', r'afstudeeropdracht')),
)
_SENIORITY_TITLE_PATTERNS = [
    (name, re.compile(r'\b(?:%s)\b' % '|'.join(words), re.IGNORECASE))
    for name, words in _SENIORITY_TITLE_WORDS
]

# LinkedIn's own buckets, mapped to the words this column prints. 'Not Applicable' is not a
# level -- it is LinkedIn saying the employer left the field blank -- so it falls through to
# the silence answer rather than becoming a word of its own.
_LINKEDIN_SENIORITY = {
    'internship': 'Intern',
    'entry level': 'Junior',
    'associate': 'Junior',
    'mid-senior level': 'Mid',
    'director': 'Lead',
    'executive': 'Lead',
}

SENIORITY_ORDER = ['Intern', 'Junior', 'Mid', 'Senior', 'Lead', 'Unspecified']


def seniority_of(row) -> str:
    """What level this listing is, as a word for the Seniority column.

    Classifies, never filters. Silence is 'Unspecified', which is a real answer: see the
    note above for why there is no honest default here the way 'Full-Time' is one for Type.

    CLAUDE'S ANSWER WINS WHERE THERE IS ONE. It has read the whole posting and been asked
    this directly (the `seniority` field of the screening schema, which replaced rule 4);
    this function has read a title and a board's metadata field. Where Claude has not seen
    the row -- no key, a failed call, or the keyword stage dropped it first -- the title
    answers, which is why both exist.
    """
    # .get() straight off the row, never `row or {}`: this runs through df.apply in
    # run_search, where `row` is a pandas Series and `or` raises "truth value of a
    # Series is ambiguous". That exception was swallowed by the surrounding try and took
    # the whole column block with it -- sponsorship_visa stopped being written at all,
    # which is how suite 4 found this.
    if row is None:
        return 'Unspecified'
    said = str(row.get('claude_seniority') or '').strip()
    if said in SENIORITY_ORDER:
        return said
    title = str(row.get('title') or '')
    for name, pattern in _SENIORITY_TITLE_PATTERNS:
        if pattern.search(title):
            return name
    field = str(row.get('seniority_level')
                or row.get('seniorityLevel') or '').strip().lower()
    if field in _LINKEDIN_SENIORITY:
        return _LINKEDIN_SENIORITY[field]
    return 'Unspecified'


def display_category(job: dict) -> str:
    """The Type badge's actual display text -- job['Category'] with a ' Startup'
    suffix for listings found via the Startup Websites Search stage
    (google_stage == 'startup', see COUNTRY_STARTUP_SITES/build_google_job_queries).
    Deliberately kept separate from categorize()'s own return value (which stays a
    clean 'Full-Time'/'Part-Time'/etc. for CATEGORY_ORDER-based sorting and
    CATEGORY_BADGE_COLORS lookups) -- this is purely a display-time label, computed
    for free from a field that's already known (no Claude call needed), replacing the
    removed Company Popularity feature's per-company Claude web-search cost with a
    zero-cost signal Sina asked for instead."""
    # text_of, not a bare `or 'Other'`: a NaN Category is TRUTHY, so `or` passes the
    # float straight through and the caller hands it to QTableWidgetItem, which raises
    # OverflowError and takes the whole Jobs table down with it. Same NaN family that
    # is_true_flag guards for booleans.
    category = text_of(job.get('Category')) or 'Other'
    if job.get('google_stage') == 'startup':
        return f'{category} Startup'
    return category


# Dedup, Sina's design: clean the title down to its words, and if two titles are the same
# job, let the two DESCRIPTIONS decide. This replaced grouping by company name, which was
# useless on a real search -- 1,189 of 2,199 Netherlands listings arrive with no company at
# all (994 from EURES, which republishes without ever naming the employer), so for more
# than half of them the only duplicate check that ran was an exact URL match.
#
# The title threshold is 90%, not the 50-65% first tried, because both were measured on
# those 2,199 rows and the loose gate deletes real jobs. Employers reuse one boilerplate
# across every opening they post, so the descriptions come out 80-99% alike even when the
# jobs are unrelated: Lemon.io's "Senior React Full-stack Developer" and "Senior Data
# Engineer", Heineken's Global Commercial Strategy and Regional Talent internships,
# Eindhoven's PhD on protein design and PhD on nanoswitches, BJAK's four different AI
# product roles. At 50% seven real postings died; going from 50% to 90% costs only 67
# fewer removals out of 2,199 and loses none of them. Sina's rule stands -- if the titles
# are genuinely different, don't delete.
_DEDUP_TITLE_SIMILARITY_THRESHOLD = 0.90
_DEDUP_DESCRIPTION_SIMILARITY_THRESHOLD = 0.80

# Decoration a board bolts onto a title: "(32-40 uur)", "(m/w/d)", "| tot EUR 4.000",
# reference numbers. The company name is stripped too, but only when the SOURCE supplied
# one -- stripping the title-regex GUESS was measured to eat the title itself, turning
# "Data Scientist - Causal Inference and Experimentation" into plain "Data Scientist".
_DEDUP_BRACKETED = re.compile(r'[\(\[\{][^\)\]\}]*[\)\]\}]')
_DEDUP_GENDER_TAG = re.compile(r'\b[mvwfdxh]\s*[/|]\s*[mvwfdxh](?:\s*[/|]\s*[mvwfdxh])?\b')
_DEDUP_SALARY_TAIL = re.compile(
    r'\s*[|–-]\s*(?:tot|vanaf|up\s+to|from|circa|ca\.)\s+\S.*$')
# Everything that is not a letter goes in one pass -- digits, punctuation, symbols. The
# word boundary matters more than the exact character: "Data-analist" and "Data analist"
# are the same job, and "Data Analist (9212028)" and "Data Analist (9211223)" are too.
_DEDUP_NOT_LETTERS = re.compile(r'[^a-zÀ-ɏ]+')


def dedup_title_key(title, company='') -> str:
    """Reduce a title to the words that say WHICH job it is, for the dedup comparison.

    Only ever used to compare two titles with each other -- the listing's own title is
    never modified, so nothing downstream (Claude, the Jobs table, the export) sees this.
    """
    text = str(title or '').lower()
    name = ' '.join(str(company or '').split()).lower()
    if len(name) > 2:
        # "Data Engineer at Merapar", "Merapar - Data Engineer" -> "data engineer"
        text = re.sub(r'\s*(?:\b(?:at|bij|chez|presso)\b|@|[-–,|])?\s*%s\b\.?'
                      % re.escape(name), ' ', text)
    # A short tail after a pipe is the employer or the board, whoever they are. The company
    # strip above only runs when the SOURCE named one, and it often has not by this point --
    # the employer is read out of the posting later, by Claude. That cost a real duplicate:
    # SurplusMap's internship came back from finn.no as "Internship Data Engineer" and from
    # thehub.io as "Internship Data Engineer | SurplusMap", 99.4% the same text, and the two
    # titles scored 84 against a 90 cut, so both were shown. A long tail is left alone --
    # "Data Engineer | Build the data foundation for the future of care" is the job itself.
    if '|' in text:
        head, _sep, tail = text.rpartition('|')
        if head.strip() and len(tail.split()) <= 3:
            text = head
    text = _DEDUP_SALARY_TAIL.sub(' ', text)
    text = _DEDUP_GENDER_TAG.sub(' ', text)
    text = _DEDUP_BRACKETED.sub(' ', text)
    text = _DEDUP_NOT_LETTERS.sub(' ', text)
    return ' '.join(text.split())


def dedup_quality(job: dict) -> tuple:
    """How good a copy of a listing this is -- higher sorts first, and the best copy is the
    one dedup keeps.

    Which copy survives is not cosmetic: it is the one Claude reads and the one Sina
    clicks. A EURES republication is a truncated excerpt pointing at a EURES page; the
    employer's own posting has the whole description and a link that still works.
    """
    url = str(job.get('url') or '').lower()
    republisher = any(host in url for host in _DEDUP_REPUBLISHER_HOSTS)
    return (0 if republisher else 1,
            len(str(job.get('description') or '')),
            1 if str(job.get('company') or '').strip() else 0)


_DEDUP_REPUBLISHER_HOSTS = ('europa.eu', 'jooble.org', 'talent.com', 'glassdoor.')


def _remove_fake_listings_list(jobs: list[dict]) -> tuple[list[dict], int]:
    """List-based counterpart to the old DataFrame-based remove_fake_listings() --
    is_likely_fake() itself is unchanged and reused as-is (it already just calls
    .get() on whatever row it's given, dict or Series alike)."""
    kept = [job for job in jobs if not is_likely_fake(job)]
    return kept, len(jobs) - len(kept)
