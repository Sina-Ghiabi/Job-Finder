# -*- coding: utf-8 -*-
"""Suite 9 -- the guard that can overturn Claude, tested without spending anything.

WHY THIS SUITE EXISTS

Claude does not have the last word on a removal. Every DROP has to quote the words in the
posting that force it, and screen.py checks that quote twice: `_evidence_is_real` asks whether
the words are really in the listing, and `_evidence_fits_rule` asks whether words like those
could carry the rule they are offered for. A quote failing either check is treated as no quote
at all, and **the DROP becomes a KEEP**.

That is the right direction to fail in -- The user sees one listing too many rather than one too
few -- but it makes the guard the last thing standing between a correct removal and a listing
in his results, and it is a pair of regular expressions. A pattern can be blind to a wording
without being blind to the rule.

It was. Counterfactual testing of the prompts found rule 4 not firing on

    "at least eight years of experience, who has led a data science team of five or more"

Claude answered DROP, rule 4, three times out of three. The guard overturned all three: the
years were spelled out so there was no digit, "experience" is not "experienced", and "led" is
not "lead". The same sentence with "8" was dropped correctly, and that is what named the cause.
Every senior role whose advert spells its number out was reaching him as a junior opening.

Trying the same technique offline then found two more, in languages the app reads every day:
Dutch `onbezoldigde functie` and Italian `non retribuito` for rule 3, and German
`Sprachkenntnisse` for rule 2 -- German never writes the bare noun "Sprache" in a job advert.

WHY OFFLINE

The guard is a pure function of the quoted words. Every wording a posting might use can be
tried against it for nothing, as many times as we like -- so this is the half of the prompt
audit that can be run to exhaustion, and the half that runs on a machine with no API credit.
The other half, asking the model whether it applies the rules at all, lives in suite 6.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, summary                       # noqa: E402

from app.pipeline.claude_screen.screen import (_evidence_fits_rule,  # noqa: E402
                                               _evidence_is_real)


# ---------------------------------------------------------------------------------------
# Could these words carry that rule?
# ---------------------------------------------------------------------------------------
#
# (rule, the sentence, must the guard accept it)
#
# The "must not" rows matter as much as the others: a guard that accepts every sentence is
# not a guard, and widening these patterns to fix a blindness is exactly how one stops being
# one. Each rejected sentence is something a posting really says and really cannot carry
# that rule.
#
# Accented and unaccented spellings both appear because the scrapers return both, depending
# on the site's own encoding.
FITS = [
    # -- rule 2, a language requirement ---------------------------------------------------
    (2, 'Verhandlungssicheres Deutsch in Wort und Schrift wird erwartet.', True),
    (2, 'Sehr gute Sprachkenntnisse werden vorausgesetzt.', True),
    (2, 'Ein Sprachniveau von mindestens B2 ist erforderlich.', True),
    (2, 'Uitstekende beheersing van de Nederlandse taal is vereist.', True),
    (2, 'Je beheerst beide talen in woord en geschrift.', True),
    (2, 'La maitrise du francais est indispensable.', True),
    (2, 'Ottima conoscenza della lingua italiana.', True),
    (2, 'Flytende norsk er et krav.', True),
    (2, 'Du behersker dansk i skrift og tale.', True),
    (2, 'Se requiere un nivel alto de espanol.', True),
    (2, 'Je talenkennis is uitstekend.', True),
    (2, 'Goede communicatieve vaardigheden in woord en geschrift.', False),
    (2, 'You will work with a friendly team in a modern office.', False),
    # "talen" is Dutch for languages and "talent" is in half the adverts on the board. The
    # pattern that reads the first must not read the second, in either language.
    (2, 'We are looking for talent to join our growing team.', False),
    (2, 'Ons talent acquisition team neemt contact met je op.', False),

    # -- rule 3, unpaid -------------------------------------------------------------------
    (3, 'This is a voluntary role; no salary, expenses only.', True),
    (3, 'Dit is een onbezoldigde functie; er is geen salaris.', True),
    (3, 'Es handelt sich um eine ehrenamtliche Taetigkeit ohne Verguetung.', True),
    (3, 'Das Praktikum ist unbezahlt.', True),
    (3, 'Stage non remunere de six mois.', True),
    (3, 'Tirocinio curriculare non retribuito.', True),
    (3, 'The placement is for study credits only.', True),
    (3, 'We offer a competitive salary and a yearly bonus.', False),
    (3, 'You will be part of a team that values learning.', False),

    # -- rule 4, too senior ---------------------------------------------------------------
    # The first row is the sentence that found the bug. It must stay first, and it must stay
    # spelled out.
    (4, 'We are hiring a data scientist with at least eight years of experience, who has '
        'led a data science team of five or more.', True),
    (4, 'We are hiring a data scientist with at least 8 years of experience.', True),
    (4, 'Mindestens fuenf Jahre Berufserfahrung werden vorausgesetzt.', True),
    (4, 'Je hebt minimaal vijf jaar ervaring in een vergelijkbare rol.', True),
    (4, 'Au moins cinq ans d experience sont requis.', True),
    (4, 'Almeno cinque anni di esperienza nel ruolo.', True),
    (4, 'Se requieren al menos cinco anos de experiencia.', True),
    (4, 'Minst fem ar i en liknande roll.', True),
    (4, 'We are looking for a Senior Data Scientist to lead our team.', True),
    (4, 'You will own the roadmap for a team of engineers.', False),
    (4, 'We offer fruit, a gym membership and a friendly atmosphere.', False),
]

section('Could the quoted words carry the rule they are offered for?')
for _rule, _sentence, _expected in FITS:
    _got = _evidence_fits_rule(_rule, _sentence)
    check('rule %d %s: %s' % (_rule, 'sees' if _expected else 'rejects', _sentence[:58]),
          _got == _expected, 'guard said %s' % _got)

# A rule the guard has no pattern for must pass everything through: the check is a filter on
# the three rules measured being stretched, not a whitelist. Rule 1 and rule 7 removals are
# held to `_evidence_is_real` alone, and narrowing that silently would cost real removals.
section('Rules with no pattern of their own are not filtered')
for _rule in (1, 5, 6, 7, 8, None, 'four'):
    check('rule %r lets any real quote through' % _rule,
          _evidence_fits_rule(_rule, 'any words at all, in any language'))


# ---------------------------------------------------------------------------------------
# Are the quoted words really in the posting?
# ---------------------------------------------------------------------------------------
section('Is the quote really in the posting?')

JOB = {
    'title': 'Data Scientist',
    'company': 'Vondelpark Analytics BV',
    'description': 'We are hiring a data scientist with at least eight years of experience. '
                   'You are required in our Amsterdam office three days a week.',
}

check('a quote copied exactly is accepted',
      _evidence_is_real('required in our Amsterdam office three days a week', JOB))
check('punctuation and casing do not reject a genuine quote',
      _evidence_is_real('Required in our Amsterdam Office, three days a week!', JOB))
check('collapsed whitespace does not reject a genuine quote',
      _evidence_is_real('required   in our\nAmsterdam office', JOB))
check('the title is part of the posting',
      _evidence_is_real('Data Scientist', JOB))
check('the company name is part of the posting',
      _evidence_is_real('Vondelpark Analytics', JOB))
check('an invented sentence is rejected',
      not _evidence_is_real('you must hold an EU passport', JOB))
check('a quote too short to mean anything is rejected',
      not _evidence_is_real('the', JOB))
check('an empty quote is rejected', not _evidence_is_real('', JOB))
check('a missing quote is rejected', not _evidence_is_real(None, JOB))

# The note the app appends to a listing after a removal repeats the previous quote verbatim.
# Left in the haystack, the guard would confirm a re-quote of our own note as if the employer
# had written it -- the guard checking its own homework.
section('The note we append is not part of the posting')
from app.pipeline.drop_note import set_drop_note                  # noqa: E402

_noted = dict(JOB)
set_drop_note(_noted, 'Rule 3 - unpaid volunteer position',
              'this is a voluntary role with no salary')
check('a quote that exists only in our own note is rejected',
      not _evidence_is_real('this is a voluntary role with no salary', _noted))
check('a quote from the posting itself still passes with a note attached',
      _evidence_is_real('required in our Amsterdam office', _noted))


sys.exit(summary('Suite 9 -- the quote guard'))
