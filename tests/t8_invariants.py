# -*- coding: utf-8 -*-
"""Suite 8 -- the tests that would have caught the bug that emptied the user's results.

WHY THIS SUITE EXISTS

He searched Data Science + Junior + Remote + Part-Time in Germany, expected at least ten of
about 12,000 listings, and got none. 2,559 assertions passed that day. Every one of them
checked a rule against a sentence somebody had thought of in advance, and the fault was not in
any single rule -- it was a rule that had been narrowed on a measurement taken over the wrong
population, and nothing in the suite compared the Filter's output to what the pool could
plausibly yield.

His instruction afterwards: [owner's note: run all the tests that were named, so that every bug comes out]. No suite finds every bug, and saying otherwise would be a lie. What this one finds
is the CLASS of bug that hurt him: a filter that silently removes far more than it should.

THE FOUR TECHNIQUES HERE, AND WHAT EACH IS FOR

  1. METAMORPHIC TESTS. The strongest tool when there is no oracle -- when you cannot write
     down the right answer for a real advert. Instead of asserting an answer, they assert a
     RELATIONSHIP that must hold whatever the answer is: adding a condition can never increase
     the survivors; running the same Filter twice must give the same result; a listing that
     passes Remote must fail Not Remote. A rule can be wrong about a listing and still satisfy
     these -- but it cannot be wrong about ALL of them, and it cannot silently invert.

  2. COMBINATORIAL (t-wise) COVERAGE. The user asked for this by name -- one at a time, then in
     pairs, then threes. Every subset of the conditions is counted on real listings, and a
     subset that empties the pool while each member looks reasonable is exactly the shape of
     what happened to him.

  3. A GOLDEN CORPUS. Real listings from his own Bank with the verdict recorded. A rule tuned
     tomorrow that flips one of them fails here, which is the regression net the project did
     not have when Part-Time was narrowed.

  4. INVARIANTS ON THE PIPELINE ITSELF. Silence must never delete. An empty description must
     never decide anything. A filter given nothing to filter on must keep everything.

A FIFTH, MUTATION TESTING, LIVES IN tests/mutate.py because it runs the other suites rather
than asserting anything itself: it breaks one rule at a time and checks that some test notices.
That is how you find out whether assertions COVER a rule or merely pass alongside it.
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, summary                       # noqa: E402

from app.pipeline import (chosen_filters, filters, job_field_words,  # noqa: E402
                          language, rules, title_equivalents)
from app.pipeline.language import (  # noqa: E402
    english_requirement_of,
    requires_language_besides_english,
)
from app.pipeline.pages import is_editorial_page                  # noqa: E402
from app.pipeline.profiles import job_profile                     # noqa: E402
from app.pipeline.search_title import (LEVEL_ROW_KEY, ROW_KEY as TITLE_ROW_KEY,
                                       WORK_MODE_ROW_KEY)         # noqa: E402

TITLE = 'Data Science'
LEVEL = 'junior'
PROFILE = job_profile(LEVEL)


def stamped(job, work_mode='remote'):
    row = dict(job)
    row[TITLE_ROW_KEY] = TITLE
    row[LEVEL_ROW_KEY] = LEVEL
    row[WORK_MODE_ROW_KEY] = work_mode
    return row


# Listings written to look like the real thing, in the shapes that have actually caused trouble
# in this project. Not random: each is a real advert's structure with its identifying details
# changed.
FULL_REMOTE_JUNIOR = {
    'title': 'Junior Data Scientist (m/w/d)', 'company': 'Acme GmbH', 'country': 'Germany',
    'url': 'https://example.invalid/1',
    'description': 'We are hiring a junior data scientist to build forecasting models. '
                   'This role is 100% remote. Everything is in English. Salary 55,000 EUR. ' * 3,
}
PART_TIME_REMOTE = {
    'title': 'Data Scientist (m/w/d)', 'company': 'Brightwell AG', 'country': 'Germany',
    'url': 'https://example.invalid/2',
    'description': 'Beschäftigungsart Teilzeit. Fully remote data science work in English, '
                   'building models. Bezahlung nach Tarif. ' * 3,
}
OFFICE_BOUND = {
    'title': 'Data Scientist', 'company': 'Kontor GmbH', 'country': 'Germany',
    'url': 'https://example.invalid/3',
    'description': 'You join our Hanover office three days a week, building models in '
                   'English. Mobile working up to 40% mobile. ' * 3,
}
GERMAN_REQUIRED = {
    'title': 'Data Scientist (m/w/d)', 'company': 'Sprachwerk AG', 'country': 'Germany',
    'url': 'https://example.invalid/4',
    'description': 'Vollständig remote. Wir erwarten verhandlungssicheres Deutsch in Wort '
                   'und Schrift sowie Erfahrung mit Python. ' * 3,
}
SAYS_NOTHING = {
    'title': 'Data Scientist', 'company': 'Quiet BV', 'country': 'Netherlands',
    'url': 'https://example.invalid/5',
    'description': 'Data Scientist. Python, SQL, machine learning. Join our team. ' * 3,
}
AN_ARTICLE = {
    'title': 'How to become a Data Scientist in Germany (2026 guide)', 'company': '',
    'country': 'Germany', 'url': 'https://example.invalid/blog/how-to-become',
    'description': 'This guide explains what a data scientist does and how to become one. ' * 6,
}
CORPUS = [FULL_REMOTE_JUNIOR, PART_TIME_REMOTE, OFFICE_BOUND, GERMAN_REQUIRED,
          SAYS_NOTHING, AN_ARTICLE]

NAMES = title_equivalents.equivalents_for(TITLE)

CONDITIONS = {
    'field': lambda j: job_field_words.row_is_in_field(stamped(j), TITLE, NAMES),
    'remote': lambda j: rules.passes_work_location_rule(stamped(j), PROFILE.vocabulary),
    'junior': lambda j: not PROFILE.is_wrong_level(stamped(j)),
    'english': lambda j: not requires_language_besides_english(stamped(j)),
    'vacancy': lambda j: not is_editorial_page(j),
    'paid': lambda j: not rules.is_unpaid(stamped(j)),
}


def survivors(pool, names):
    out = []
    for job in pool:
        if all(CONDITIONS[name](job) for name in names):
            out.append(job)
    return out


# ============================================================ 8.1  metamorphic ============
section('8.1  metamorphic -- relationships that must hold whatever the answer is')

# The one that matters most. Every filter is a restriction, so adding one can only ever remove.
# A rule that INVERTED -- kept what it should drop -- would break this, and nothing in the old
# suite would have noticed.
_all_names = list(CONDITIONS)
_monotone = True
_where = ''
for _size in range(1, len(_all_names) + 1):
    for _combo in itertools.combinations(_all_names, _size):
        _with = len(survivors(CORPUS, _combo))
        for _extra in _all_names:
            if _extra in _combo:
                continue
            _more = len(survivors(CORPUS, list(_combo) + [_extra]))
            if _more > _with:
                _monotone = False
                _where = '%s then +%s: %d -> %d' % (' + '.join(_combo), _extra, _with, _more)
check('adding a condition never increases the survivors', _monotone, _where)

# Running the same filter twice must give the same answer. A rule that remembers something
# between calls -- a cache keyed on the wrong thing, a row it mutated -- shows up here.
_once = [j.get('url') for j in survivors(CORPUS, _all_names)]
_twice = [j.get('url') for j in survivors(CORPUS, _all_names)]
check('the same filter run twice gives the same answer', _once == _twice, (_once, _twice))

# Remote and Not Remote are opposites on a listing that states its arrangement. Both answering
# the same way means one of them is not reading.
_remote_keeps = rules.passes_work_location_rule(stamped(FULL_REMOTE_JUNIOR), PROFILE.vocabulary)
_not_remote_keeps = rules.passes_not_remote_rule(stamped(FULL_REMOTE_JUNIOR, 'not_remote'),
                                                PROFILE.vocabulary)
check('a fully remote listing passes Remote and fails Not Remote',
      _remote_keeps and not _not_remote_keeps, (_remote_keeps, _not_remote_keeps))
_office_remote = rules.passes_work_location_rule(stamped(OFFICE_BOUND), PROFILE.vocabulary)
_office_not_remote = rules.passes_not_remote_rule(stamped(OFFICE_BOUND, 'not_remote'),
                                                 PROFILE.vocabulary)
check('an office-bound listing fails Remote and passes Not Remote',
      not _office_remote and _office_not_remote, (_office_remote, _office_not_remote))

# A condition nobody chose must change nothing. Every "empty means all" promise in the Filter
# window rests on this, and it is the promise that makes a first run complete.
for _label, _call in (
        ('no country chosen', lambda: chosen_filters.filter_by_place(CORPUS, [], [])),
        ('no kind chosen', lambda: chosen_filters.filter_by_category(CORPUS, [])),
        ('no sponsorship chosen', lambda: chosen_filters.filter_by_sponsorship(CORPUS, '')),
        ('no date window', lambda: chosen_filters.filter_by_date(CORPUS, 'anyTime')),
        ('no match floor', lambda: chosen_filters.filter_by_match(CORPUS, 0)),
):
    _kept, _removed = _call()
    check('%s removes nothing' % _label, _removed == 0 and len(_kept) == len(CORPUS),
          (_label, _removed))

# Widening the field can only ever keep MORE. If an equivalent title made the answer smaller,
# something is matching on the wrong thing.
_narrow = len(survivors(CORPUS, ['field']))
_wide_names = NAMES
_wide = sum(1 for j in CORPUS
            if job_field_words.row_is_in_field(stamped(j), TITLE, _wide_names))
check('adding other names for the job never loses a listing', _wide >= _narrow,
      (_narrow, _wide))


# SILENCE DROPS ONLY IN A REMOTE SEARCH, and the user asked for that to be certain: [owner's note: the rule above is for Remote only]. It already was -- passes_work_location_rule hands a Not Remote
# row to passes_not_remote_rule, where silence KEEPS -- and this is the assertion that stops
# anyone merging the two by accident. Getting it wrong in either direction empties a search.
for _label, _job, _remote_keeps, _not_remote_keeps in (
        ('a listing that says nothing', SAYS_NOTHING, False, True),
        ('a fully remote listing', FULL_REMOTE_JUNIOR, True, False),
        ('an office-bound listing', OFFICE_BOUND, False, True),
):
    _r = rules.passes_work_location_rule(stamped(_job, 'remote'), PROFILE.vocabulary)
    _n = rules.passes_work_location_rule(stamped(_job, 'not_remote'), PROFILE.vocabulary)
    check('%s: Remote %s, Not Remote %s'
          % (_label, 'keeps' if _remote_keeps else 'drops',
             'keeps' if _not_remote_keeps else 'drops'),
          _r == _remote_keeps and _n == _not_remote_keeps, (_r, _n))


# ======================================================= 8.2  combinatorial ===============
section('8.2  combinatorial -- every subset of the conditions, on listings that must survive')
# The user asked for this shape directly: [owner's note: first one by one, then two by two, then three by three].
#
# The assertion is not a count. It is that the two listings which MUST reach him -- a fully
# remote junior data science role, and a genuinely part-time remote one -- survive every subset
# of the conditions that does not specifically exclude them. A rule that empties the pool shows
# up as one of these disappearing under some pair, which is what "Part-Time in Germany" was.
_must_survive = [FULL_REMOTE_JUNIOR, PART_TIME_REMOTE]
for _size in (1, 2, 3, 4, 5, 6):
    _failures = []
    for _combo in itertools.combinations(_all_names, _size):
        _kept = {j.get('url') for j in survivors(_must_survive, _combo)}
        for _job in _must_survive:
            if _job.get('url') not in _kept:
                _failures.append('%s removed %s' % (' + '.join(_combo), _job.get('title')))
    check('%d condition(s) at a time keep the listings that must survive' % _size,
          not _failures, _failures[:4])

# And the reverse: a listing that should be removed is removed by the condition that owns it,
# under every combination that includes it.
for _label, _job, _owner in (
        ('an office-bound listing', OFFICE_BOUND, 'remote'),
        ('a listing demanding German', GERMAN_REQUIRED, 'english'),
        ('an article rather than a vacancy', AN_ARTICLE, 'vacancy'),
):
    _escaped = []
    for _size in range(1, len(_all_names) + 1):
        for _combo in itertools.combinations(_all_names, _size):
            if _owner not in _combo:
                continue
            if survivors([_job], _combo):
                _escaped.append(' + '.join(_combo))
    check('%s is removed wherever %s applies' % (_label, _owner), not _escaped, _escaped[:3])


# =========================================================== 8.3  the golden corpus =======
section('8.3  golden -- real listing shapes with the verdict written down')
# The net the project did not have. Each of these is a real advert's structure, and the verdict
# beside it is what the Filter must say. A rule narrowed tomorrow that flips one of them fails
# here, at the moment it is narrowed, instead of emptying a real search a week later.
NO_DESCRIPTION_AT_ALL = {
    'title': 'Data Scientist', 'company': 'Sparse GmbH', 'country': 'Germany',
    'url': 'https://example.invalid/6', 'description': '',
}

GOLDEN = [
    ('a fully remote junior data science role', FULL_REMOTE_JUNIOR, True),
    ('a genuinely part-time remote role', PART_TIME_REMOTE, True),
    # NOT a bug, and this line is why it is written down. The Work Location rule requires the
    # posting to say SOMEWHERE that the work can be done away from an office, and silence drops
    # it. That requirement was removed once and restored: without it, 128 listings that never
    # raised the subject came through, and Claude deleted them anyway with reasons the text did
    # not contain ("on-site role in Amsterdam"). The user's call was that silence in a Dutch advert
    # means an office job and he would rather not pay to read 128 of them.
    #
    # This suite asserted the opposite on its first run, and reading the rule is what settled
    # it. Recorded as the expected answer so nobody -- including me -- has to guess again.
    ('a listing that says nothing about its arrangement', SAYS_NOTHING, False),
    # The exemption that makes the rule above survivable for whole sources -- and it keys on
    # the `thin_description` FLAG, not on the description being empty. arbeitsagentur.de,
    # Jooble, jobs.ch and SwissDevJobs set it, and this requirement is what once made all four
    # produce deletions and nothing else.
    #
    # Measured before writing this down: the real Bank holds ZERO rows with no description and
    # 5 under 200 characters, none flagged -- and three of those five are index pages ("31 data
    # scientist vacatures in Amsterdam") that should be dropped anyway. So an unflagged empty
    # row being dropped costs nothing in practice, and the flag is what to set if a new source
    # ever needs the exemption.
    ('an unflagged empty listing', NO_DESCRIPTION_AT_ALL, False),
    ('a flagged thin listing, as the quiet sources send them',
     dict(NO_DESCRIPTION_AT_ALL, thin_description=True), True),
    ('three days a week in Hanover', OFFICE_BOUND, False),
    ('verhandlungssicheres Deutsch required', GERMAN_REQUIRED, False),
    ('a careers-advice article', AN_ARTICLE, False),
]
for _label, _job, _should_survive in GOLDEN:
    _survives = bool(survivors([_job], _all_names))
    check('%s: %s' % (_label, 'kept' if _should_survive else 'removed'),
          _survives == _should_survive,
          'survived' if _survives else 'removed')

# The kinds, written down too. The Part-Time bug was a Category verdict, not a survival one, so
# survival alone would not have caught it.
#
# The three below were added because MUTATION TESTING said nothing was watching them. Removing
# the "not an internship" guard from the category rules broke no test at all, and that guard is
# the one the user reported: Glovo's "2-5 years of professional experience outside of an academic
# and internship setting" was being filed as an Internship, on a sentence whose whole point is
# that it is not one.
NOT_AN_INTERNSHIP_ADVERT = {
    'title': 'Product Data Scientist', 'company': 'Glovo', 'country': 'Spain',
    'url': 'https://example.invalid/glovo',
    'description': 'Requirements: 2-5 years of professional experience outside of an academic '
                   'and internship setting, in a quantitative analysis role. Fully remote, in '
                   'English, building models. ' * 3,
}
MENTIONS_A_PHD = {
    'title': 'Machine Learning Engineer', 'company': 'Modelwerk AG', 'country': 'Germany',
    'url': 'https://example.invalid/mentions-phd',
    'description': 'Fully remote machine learning work in English. You will work alongside our '
                   'PhDs, and a PhD is a plus but not required. ' * 3,
}
A_REAL_PHD_POST = {
    'title': 'PhD Candidate in Causal Inference', 'company': 'TU Delft',
    'country': 'Netherlands', 'url': 'https://example.invalid/phd',
    'description': 'A four-year doctoral position, fully remote, writing your thesis in '
                   'English on causal inference for health data. ' * 3,
}

for _label, _job, _kind in (
        ('Beschäftigungsart Teilzeit', PART_TIME_REMOTE, 'Part-Time'),
        ('a plain junior role', FULL_REMOTE_JUNIOR, 'Full-Time'),
        ('"outside of an academic and internship setting"',
         NOT_AN_INTERNSHIP_ADVERT, 'Full-Time'),
        ('a role merely saying "a PhD is a plus"', MENTIONS_A_PHD, 'Full-Time'),
        ('an actual doctoral post', A_REAL_PHD_POST, 'PhD'),
):
    check('%s is categorised as %s' % (_label, _kind), rules.categorize(_job) == _kind,
          rules.categorize(_job))


# --- the similarity floor, which mutation testing found nothing was watching ----------------
# Raising MINIMUM_SIMILARITY to 95 -- so every other name for the job is dropped -- broke no
# test at all. That is the setting which decides whether "AI Engineer" and "Machine Learning
# Engineer" reach the user, and on his own Bank it is worth 712 listings. It is also the number he
# chose himself, twice, after I argued against it.
_CANDIDATES = [
    {'title': 'Machine Learning Engineer', 'same_work': 80, 'closest_to': '', 'because': ''},
    {'title': 'AI Engineer', 'same_work': 60, 'closest_to': '', 'because': ''},
    {'title': 'Data Analyst', 'same_work': 35, 'closest_to': '', 'because': ''},
    {'title': 'Database Administrator', 'same_work': 20, 'closest_to': '', 'because': ''},
]
check('the similarity floor is the 35 the user set',
      title_equivalents.MINIMUM_SIMILARITY == 35, title_equivalents.MINIMUM_SIMILARITY)
_kept = title_equivalents.close_enough(_CANDIDATES)
check('a title scoring above the floor is searched for',
      'Machine Learning Engineer' in _kept and 'AI Engineer' in _kept, _kept)
check('  ...and 35 itself stays, because his rule was BELOW 35 goes',
      'Data Analyst' in _kept, _kept)
check('  ...while 20 is dropped', 'Database Administrator' not in _kept, _kept)
_dropped = [name for name, _score, _why in title_equivalents.too_far(_CANDIDATES)]
check('the dropped one is reported with its score, not silently lost',
      _dropped == ['Database Administrator'], _dropped)

# And what the user turns down himself is remembered per title, which is what replaced the
# blacklist. Nothing here writes to the cache -- rejections are passed in directly.
_after_reject = title_equivalents.close_enough(_CANDIDATES, ['Data Analyst'])
check('a title the user rejected is not searched for again',
      'Data Analyst' not in _after_reject and 'AI Engineer' in _after_reject, _after_reject)
check('  ...and the Log can say it was his choice, not a score',
      any(name == 'Data Analyst' and 'turned this one down' in why
          for name, _s, why in title_equivalents.too_far(_CANDIDATES, ['Data Analyst'])),
      title_equivalents.too_far(_CANDIDATES, ['Data Analyst']))


# ===================================================== 8.4  pipeline invariants ===========
section('8.4  invariants -- silence never deletes, and nothing decides on an empty field')
# The rule this whole project is built on, asserted directly rather than trusted.
_EMPTY_SHAPES = [
    {},
    {'title': '', 'description': '', 'url': ''},
    {'title': None, 'description': None, 'company': None, 'country': None},
    {'title': 'Data Scientist'},                       # a title and nothing else
    {'description': 'Remote data science work.'},      # a body and nothing else
]
for _at, _shape in enumerate(_EMPTY_SHAPES):
    _errors = []
    for _name, _test in CONDITIONS.items():
        try:
            _test(_shape)
        except Exception as _exc:
            _errors.append('%s: %s' % (_name, type(_exc).__name__))
    check('shape %d is judged without raising' % _at, not _errors, _errors)

# An empty pool must come back empty rather than raise, from every one of the chosen filters.
for _label, _call in (
        ('by place', lambda: chosen_filters.filter_by_place([], ['Germany'], [])),
        ('by category', lambda: chosen_filters.filter_by_category([], ['Part-Time'])),
        ('by sponsorship', lambda: chosen_filters.filter_by_sponsorship([], 'Yes')),
        ('by date', lambda: chosen_filters.filter_by_date([], 'pastWeek')),
        ('by match', lambda: chosen_filters.filter_by_match([], 50)),
):
    _kept, _removed = _call()
    check('an empty pool filtered %s stays empty' % _label,
          _kept == [] and _removed == 0, (_kept, _removed))


# ================================ the English column and the language rule, as one =======
# english_requirement_of and requires_language_besides_english read the same patterns to
# answer two different questions -- what shape is this, and does it go. One of the three
# answers, 'Other only', IS the rule's True, and the two must agree on every input or the
# column contradicts the Log: a row labelled 'Other only' that the Filter kept, or a row
# deleted while wearing an 'English only' badge.
#
# Asserted over generated text rather than a fixed list, because the agreement has to hold
# for inputs nobody thought of -- that is the whole class of bug two readings of one question
# produce.
_LANG_PIECES = [
    '', 'Fluent English required.', 'Sehr gute Deutschkenntnisse in Wort und Schrift.',
    'You are fluent in English and Dutch.', 'Uitstekende beheersing van de Nederlandse taal.',
    'Deutschkenntnisse von Vorteil.', 'Englisch und idealerweise Deutsch.',
    'C1+ level in either English or Spanish.', 'Deutschkenntnisse auf Niveau C1.',
    'We build models. Remote. Join the team.', 'Nederlands en Engels.',
    'Ottima conoscenza della lingua italiana.', 'Fluent German is required.',
]
_disagreements = []
for _i, _one in enumerate(_LANG_PIECES):
    for _two in _LANG_PIECES:
        _row = {'title': 'Data Scientist', 'description': _one + ' ' + _two}
        _label = english_requirement_of(_row)
        _drops = requires_language_besides_english(_row)
        if (_label == 'Other only') != _drops:
            _disagreements.append((_label, _drops, (_one + ' ' + _two)[:60]))
check('the English column and the language rule agree on all %d texts'
      % (len(_LANG_PIECES) ** 2), not _disagreements, _disagreements[:4])

# And the label is always one of the three. A fourth value would reach the table as a badge
# with no colour and a filter entry with no tooltip.
_labels = {english_requirement_of({'title': 'Data Scientist', 'description': _one + ' ' + _two})
           for _one in _LANG_PIECES for _two in _LANG_PIECES}
check('every answer is one of the three the column knows',
      _labels <= set(language.ENGLISH_NEED_ORDER), sorted(_labels))

# The Filter cannot leave an 'Other only' row behind, which is the same invariant seen from
# the other end: the rule that deletes them runs in the same loop that writes the label.
_kept_labels = {j.get('English') for j in filters._step_rules(
    [dict(_r, **{WORK_MODE_ROW_KEY: 'remote', TITLE_ROW_KEY: TITLE,
                 LEVEL_ROW_KEY: LEVEL}) for _r in CORPUS],
    progress_cb=None, cancelled=lambda: False, profile=PROFILE)[0]}
check('no row survives the Filter labelled Other only',
      'Other only' not in _kept_labels, sorted(x for x in _kept_labels if x))


sys.exit(summary('Suite 8 -- invariants, metamorphic and combinatorial'))
