# -*- coding: utf-8 -*-
"""The instructions Claude screens against, and the shape of its answer.

Kept apart from the code that sends them because this is the file that actually gets
edited. Every wording change this session -- and there were six -- meant finding one
string inside six hundred lines of request plumbing.

The prompt is also kept byte-identical to Job-Filter-Claude-Apify.md in the project
root, which is the copy the user reads and edits. If either changes, the other must.
"""
from __future__ import annotations

import hashlib
import json
import re

from ..drop_note import listing_text_without_note
from ..search_title import ROW_KEY as TITLE_ROW_KEY, clean_title


CLAUDE_MODEL = 'claude-haiku-4-5-20251001'


# The full contents of this prompt are authored by the user himself (see
# Job-Filter-Claude-Apify.md in the project root -- keep that file and this constant in
# sync if either is edited). It replaces an earlier, much shorter 5-rule paraphrase that
# Claude was found to judge inconsistently; this version gives Claude the exact same
# keyword dictionaries the app's own filters use, plus 4 additional rules the keyword
# filters don't cover at all (fake job/paid training, citizenship/residency, domain fit,
# degree completion), plus the user's real profile so it can also score a match percentage.
CLAUDE_SCREEN_SYSTEM_PROMPT = """# Job screening for the user

Read the whole posting and decide. If it conflicts with anything below, **DROP**. Otherwise
**KEEP**.

## Who it is for

The user. **Everything about him comes from his résumé**, given in full after these
instructions under "His résumé". Where he lives, which languages he speaks and how well, his
citizenship and residence status, where he studies, his experience and his skills — read
them there, and nowhere else.

If a rule needs a fact his résumé does not give, do not guess it, and do not DROP for it.

## What he is looking for

**A remote job he can do from his desk at home, in the city his résumé says he lives in** —
from any country, for any company. That is the point of this search.

**In the work named on the Field line of the posting**, at any level of seniority. Read
what level the posting is pitched at and report it in `seniority`; do not weigh it
against him. An internship, a junior opening, a mid-level role, a senior one and a lead
one are all kept, each labelled as what it is.

## DROP if any of these is true

1. **He would have to be present somewhere — the role is not remote.**

   Work through these in order and stop at the first that applies. Say which one in
   `location_basis`, and make the verdict agree with it.

   1a. The posting says **this role** can be done remotely → KEEP, whatever the work.
   1b. The posting **requires him to be present somewhere** → DROP. Office days per week, an
       attendance policy, "based in", relocation, hybrid as the working model — or a remote
       role restricted to a country he is not in ("remote within the US", "remote from
       India", "must reside in the Netherlands", "within commuting distance of Amsterdam").
       **"Based in", "located in", "must reside in" or "present in" followed by a REGION that
       contains where his résumé says he lives is satisfied by him, not violated — KEEP.**
       "Europe", "the EU", "EMEA", "Southern Europe", "a European country" and "European time
       zones" contain every European country, so for a candidate who lives in one of them
       they ask nothing he does not already do. Only a named country that is not his, or a
       list of countries that leaves his out, is a restriction; "specific countries" with none
       named is not evidence of anything. Check his country in the résumé before you write
       that a region excludes him.
   1c. **Home office appears only in a list of benefits** — "we offer home office, flexible
       hours, meal vouchers" → a perk for staff who already live there, not a remote role.
       DROP, and say so.
   1d. Otherwise → **DROP**. A posting that never says the work can be done away from
       an office has not said it can. Say so in `location_basis` and quote the
       posting's own words for where the work happens — its location line, its office,
       the city in its title — as `drop_evidence`.

   The only test is whether the posting requires him to **be present** somewhere. A remote
   role at a Dutch, German or American company passes it — where the company is does not
   matter. A role that says on-site, hybrid, or names days in an office fails it, whatever
   country that office is in.

   Three things are NOT a reason to drop under this rule:

   - **The Location and Company lines in the block above.** They say where the employer is,
     not where he must sit. "Netherlands" on its own is never a reason.
   - **A remote statement about the COMPANY rather than this role.** "We are a remote-
     first company" in a page footer, or a remote badge in the board's own filter menu,
     is not this posting saying this job is remote. Read what it says about the work.
   - **Anything you would describe as "implied".** If the word you reach for is "implied",
     "presumably" or "typically", you are inferring a requirement the posting does not make.
     That is 1d.

   If your reason for a DROP would be the country on its own, or something the posting
   only implies about being required somewhere, the answer is KEEP. The absence of a
   remote statement is not an inference — it is 1d, and 1d is a DROP.
2. **It requires a language he does not speak INSTEAD of English** — a language his résumé
   does not list, or one wanted fluent where his résumé gives a basic level, with English
   never named beside it.

   **A posting that wants English together with another language is a KEEP.** "Fluency in
   Dutch and English", "Deutsch und Englisch", "Nederlands en Engels", "English and at
   least one more language" — all KEEP. The posting has said the work can be done in a
   language he has, and whether the second one is a wall is a judgement about his own CV
   that he makes himself, looking at the advert. Taking it here takes it away from him.
   A bonus or nice-to-have is fine too, as it always was.

   So the only DROP under this rule is a posting that demands a language he lacks and never
   offers English anywhere near the demand.
3. **It is unpaid** — voluntary, expenses-only, for credit, or self-funded.
4. **Seniority is never a reason to drop.** How senior the posting is pitched — the
   years it asks for, and whether it calls itself Junior, Mid, Senior, Lead or
   Principal — is REPORTED, not filtered. Put it in `seniority` and keep the listing.
   A role wanting eight years is kept and labelled Senior; one wanting none is kept and
   labelled Junior. The user picks the levels he wants in the table afterwards, so taking
   that decision here would take it away from him.

5. **It is not a real vacancy** — a search-results or index page listing many jobs, a paid
   course sold as a job, a scheme charging a fee, one role posted across dozens of cities,
   or a page written ABOUT the work rather than offering any: a careers article, a guide, a
   role profile explaining what the job involves and what it pays, an organisation
   describing itself. A vacancy names one employer with one opening and says how to apply
   for it; if no single employer is hiring anyone here, it is not a vacancy.
6. **It requires a citizenship, residency or clearance his résumé shows he does not have.**
   One his résumé shows he has is fine.
7. **It is not the work named on the Field line.** That line is the job title the user is
   searching for. The same job under any other name an employer gives it counts. A
   different job that only mentions it, or works alongside it, does not.
8. **It requires enrolment at a university in a country other than the one his résumé says
   he studies in**, or at a named university he does not attend.

## Never DROP for

- **A degree requirement of any kind** — Bachelor's, Master's, PhD, doctorate, a completed
  degree, a named field of study. Switched off entirely, under every rule above. (A posting
  that *is itself* a PhD position is a different matter: that is a four-year research post,
  so it goes under rule 4.)
- **A city, country or address on its own.** That says where the company is, not where he
  must sit.
- **Silence about pay or experience.** No mention of either is not a statement.
  A posting that never mentions money is not unpaid — rule 3 needs words the posting does
  not have. One that never names a language demands none. One you would call "vague about
  seniority" has stated no experience requirement, so rule 4 has nothing to measure. If the
  reason you are about to write contains "not stated", "not mentioned", "unclear", "vague"
  or "implied" about PAY or EXPERIENCE, you are describing silence, and the answer is
  KEEP. Silence about where the work happens is rule 1d, and that is a DROP.
- **The job board's own furniture** — filter menus, "similar jobs", cookie notices,
  employee-count badges, the site name in the page title.

## Two traps

- **A perk is not a working arrangement.** "Work from anywhere for one month a year", a
  home-office allowance, flexible hours — none of these makes a role remote. Look at what
  the posting says about doing *this job*, not at its benefits list.
- **Quote before you drop.** For every DROP there must be words in the posting you could
  point at, and you copy them into **drop_evidence** before you give the verdict. They are
  checked against the posting: a DROP whose words are not in it is read as a KEEP. If your
  reason comes from the city, the industry or the feel of the role rather than a sentence,
  the answer is KEEP.

## Also return

- **employer** — the company doing the hiring, only if the posting names it, spelled as it
  spells it. Quote the exact words that name them; the quote is checked. Not the job board,
  not a recruiter, not a client mentioned in passing. Leave it empty rather than guess —
  most postings here never name anyone.
"""

# The whole description goes to Claude. This used to stop at 6,000 characters to hold down
# the bill when every listing was its own request, and it cut 33 of 93 real listings short --
# one of them losing the words "from home" and "commuting distance", so the verdict was
# reached on text Claude was never shown. Since listings now share a request the saving was
# never worth that: the longest description in the corpus is 9,802 characters, and sending
# every listing whole costs about a cent more per run.
#
# The cap is kept only as a guard against a scraper returning a whole site in one field.
_CLAUDE_SCREEN_DESCRIPTION_MAX_CHARS = 60000


def _claude_screen_prompt(job: dict) -> str:
    """Combines every field of the listing -- not just the description -- into one
    block, so Claude judges the whole listing as a unit (title, company, location,
    platform-reported employment type/seniority level, and description all together),
    the same way the keyword filters above already do."""
    return (
        # The job title the user typed, which rule 7 judges the field against. On this line rather
        # than written into the rules, so the rules stay the same text for every title -- and
        # because this block is what the cache key hashes, a verdict reached for one title can
        # never be reused for another.
        f"Field: {clean_title(job.get(TITLE_ROW_KEY))}\n"
        f"Title: {job.get('title') or ''}\n"
        f"Company: {job.get('company') or ''}\n"
        # Still "Location:", and deliberately, while the Thesis and Internship modules
        # relabel this line. That relabel exists to stop Claude inventing a place for a
        # posting that names none -- a failure those two modules really have, because their
        # keyword stage lets silence through on purpose. This module's keyword stage drops
        # silence before Claude ever sees it, so the failure cannot arise here.
        #
        # And the relabel is not free. Measured on 20 real survivors, twice: with it, "Data
        # Scientist Space Jobs in Netherlands" stops being caught by rule 5 as a listings
        # page. De-emphasising the country apparently takes away part of what made that
        # title read as an index rather than a vacancy. One correct drop lost, nothing
        # gained -- so this line stays as it is.
        f"Location: {job.get('location') or ''} ({job.get('country') or ''})\n"
        f"Platform: {job.get('platform') or ''}\n"
        f"Employment type (as reported by the platform): {job.get('employment_type') or ''}\n"
        f"Seniority level (as reported by the platform): {job.get('seniority_level') or ''}\n"
        # NOT "the only text that can support a DROP", which this said for one measured
        # round. That wording cost a correct verdict: "Data Scientist Space Jobs in
        # Netherlands" is a listing page and rule 5 caught it from the TITLE, and telling
        # Claude only the description counts made it a KEEP.
        f"Description:\n"
        # Without the note we appended last run. It must not reach Claude as if the posting
        # said it, and this one call also protects the screening cache: _claude_screen_cache_key
        # hashes this very text, so a note left in would change the hash of every flagged
        # listing and re-screen -- and re-bill -- all of them on the next Filter run.
        f"{listing_text_without_note(job.get('description'))[:_CLAUDE_SCREEN_DESCRIPTION_MAX_CHARS]}"
    )


_MATCH_LINE_PATTERN = re.compile(r'match\s*:?\s*(\d{1,3})', re.IGNORECASE)


_KEEP_DROP_LINE_PATTERN = re.compile(r'^\s*(KEEP\b|DROP\s*:.*)$', re.IGNORECASE | re.MULTILINE)


# Claude's answer is constrained to this schema by the API itself: the grammar is compiled
# from it and the decoder cannot emit anything else. That removes the whole class of bug the
# two constants above exist to survive -- there is no prose to run out of room in, and no
# sentence for a regex to mistake for a verdict.
#
# `checked` is first, and that ordering is the entire design, not a detail. JSON fields are
# generated in the schema's order, so a verdict field placed first would have to be named
# before the model has written anything -- and measured over 60 real listings from the
# population the app actually screens, that is exactly what goes wrong: a bare
# verdict/rule/reason/match schema agreed with the current answer on 58 of 60 and DROPPED 2
# jobs the current answer keeps. With `checked` in front to hold the pass over the nine
# rules, agreement was 60 of 60 and nothing was lost. So the schema buys format safety
# without paying for it in recall -- but only in this order.
#
# `minimum`/`maximum` are deliberately absent: the API rejects them on integer fields
# ("For 'integer' type, properties maximum, minimum are not supported"), so `match` is
# clamped in code below instead.
_SCREEN_OUTPUT_SCHEMA: dict = {
    'type': 'object',
    'properties': {
        'checked': {
            'type': 'string',
            'description': 'Your brief pass through questions 1-8, in order, before '
                           'deciding. One short clause per question that mattered.',
        },
        # Rule 1 asks for a ladder to be worked in order; this is where the rung that
        # decided it is recorded. It sits before the verdict for the same reason `checked`
        # does -- the question has to be settled in words before a verdict is committed to --
        # and it makes the Log say which rung fired rather than only that rule 1 did.
        'location_basis': {
            'type': 'string',
            'enum': ['1a says this role is remote',
                     '1b requires him to be present somewhere',
                     '1c home office listed only as a benefit',
                     '1d nothing requires his presence'],
            'description': 'Which rung of rule 1 decided it.',
        },
        # The posting's own words for the thing a DROP claims -- asked for BEFORE the verdict,
        # like `checked` and `location_basis`, so the words have to be found before a verdict
        # can lean on them. Measured on 117 real DROPs: 11 of them claimed something the
        # posting never said ("unpaid" where pay is never mentioned, "on-site" where only a
        # city is named, "2+ years implied"). Asking for the quote in the prompt was not
        # enough; the quote is now checked against the posting, and a DROP that cannot show
        # one becomes a KEEP. See _evidence_supports_drop in screen.py.
        'drop_evidence': {
            'type': 'string',
            'description': 'The exact words from the posting, copied verbatim, that force '
                           'the DROP you are about to give -- the sentence naming the years, '
                           'the language, the office days, the fee. Empty for a KEEP. If you '
                           'cannot copy such words out of the posting, there is no DROP to '
                           'give.',
        },
        # ASKED BEFORE THE VERDICT, like `checked` and `location_basis`, and for the same
        # reason: a question has to be settled in words before a verdict is committed to.
        #
        # This is rule 4's replacement. Rule 4 used to DROP for seniority -- 19 of 90 flags
        # on the real Netherlands run -- and the user's instruction was to classify instead:
        # [owner's note: it should not filter, it should categorise]. So the level is reported here, the
        # listing is kept whatever it says, and he picks the levels he wants in the Jobs
        # table.
        #
        # The same six words rules.seniority_of returns, so the column reads one vocabulary
        # whether the value came from Claude or from the keyword classifier.
        'seniority': {
            'type': 'string',
            'enum': ['Intern', 'Junior', 'Mid', 'Senior', 'Lead', 'Unspecified'],
            'description': 'What level the posting is pitched at, from what it says: the '
                           'years it asks for and what it calls the role. Intern for a '
                           'placement or thesis post, Junior for a graduate or '
                           'career-starter role or up to about 2 years, Mid for roughly 3 '
                           'to 5, Senior for 5 or more or a role titled Senior, Lead for a '
                           'lead, staff, principal, head-of or team-owning role. '
                           'Unspecified when the posting says nothing about level -- that '
                           'is a real answer, not a guess to be filled in.',
        },
        'verdict': {'type': 'string', 'enum': ['KEEP', 'DROP']},
        'rule': {'type': 'integer',
                 'description': 'Which question (1-8) forced a DROP, or 0 for a KEEP. '
                                'Never 4: seniority is reported in `seniority`, not '
                                'dropped for.'},
        'reason': {'type': 'string',
                   'description': 'Ten words or fewer, naming the question. Empty for a KEEP.'},
        'employer_evidence': {
            'type': 'string',
            'description': 'The exact words from the posting that name the employer, '
                           'copied verbatim. Empty if the posting never names one.',
        },
        'employer': {
            'type': 'string',
            'description': "The employer's name only, as the posting spells it. Empty when "
                           'employer_evidence is empty.',
        },
    },
    # No `match` any more. Scoring a listing against the user is the second part's job now, read
    # against his uploaded résumé (claude_screen/worth.py), and this part only decides
    # KEEP or DROP. The field was last in the order, after the verdict, so taking it out
    # cannot move a verdict -- see the note above on why order matters.
    'required': ['checked', 'location_basis', 'seniority', 'drop_evidence', 'verdict',
                 'rule', 'reason', 'employer_evidence', 'employer'],
    'additionalProperties': False,
}


# A hash of the system prompt's own text -- NOT a hand-maintained version number, so
# any future edit to a rule in CLAUDE_SCREEN_SYSTEM_PROMPT automatically changes this
# and correctly invalidates every cached screening decision below (see
# _claude_screen_cache_key), with no risk of the user forgetting to bump a manual counter.
#
# The answer schema is hashed in alongside it for the same reason and it is not cosmetic:
# the schema changes the decisions, not just their shape. Measured over 60 real listings, a
# schema without a leading `checked` field dropped 2 jobs the prose format kept. A decision
# cached under one answer format must therefore not be reused under another.
_CLAUDE_SCREEN_PROMPT_VERSION = hashlib.sha256(
    (CLAUDE_SCREEN_SYSTEM_PROMPT + '\n'
     + json.dumps(_SCREEN_OUTPUT_SCHEMA, sort_keys=True)).encode('utf-8')).hexdigest()[:12]


def system_prompt_for(job: dict) -> str:
    """The prompt for the Level, and the Remote or Not Remote choice, this row is filtered at.

    Junior's are CLAUDE_SCREEN_SYSTEM_PROMPT above and CLAUDE_SCREEN_SYSTEM_PROMPT_NOT_REMOTE
    in prompt_not_remote.py; Entry, Mid and Senior each keep their own two in
    app/pipeline/profiles. Imported late because the profiles package imports this module.
    """
    from ..profiles import job_profile
    from ..search_title import LEVEL_ROW_KEY, is_any_workplace, is_not_remote
    job = job or {}
    return job_profile(job.get(LEVEL_ROW_KEY)).prompt_for(is_not_remote(job), is_any_workplace(job))


def prompt_version_for(job: dict) -> str:
    """The version hash of that prompt -- each one's edits change only its own cached verdicts."""
    from ..profiles import job_profile
    from ..search_title import LEVEL_ROW_KEY, is_any_workplace, is_not_remote
    job = job or {}
    return job_profile(job.get(LEVEL_ROW_KEY)).version_for(is_not_remote(job), is_any_workplace(job))


def resume_section(text) -> str:
    """The résumé as the second block of the system prompt -- "His résumé", which the rules
    above point to for every fact about the user.

    Its own block, after the rules, so the rules stay the same text for every résumé and the
    two can be cached together: every listing in a Filter run is judged against the same
    résumé, so it is paid for in full once and read from the cache after that.
    """
    return ('# His résumé\n\n'
            'the user uploaded this himself. It is the only source of facts about him.\n\n'
            '<resume>\n%s\n</resume>\n' % str(text or '').strip())


def system_blocks_for(job: dict, resume_text: str) -> list:
    """The whole system prompt for one request: the Level's rules, then the résumé.

    The cache mark sits on the résumé block, the last one, so both are cached together.
    """
    return [{'type': 'text', 'text': system_prompt_for(job)},
            {'type': 'text', 'text': resume_section(resume_text),
             'cache_control': {'type': 'ephemeral'}}]


def system_text_for(job: dict, resume_text: str) -> str:
    """The same system prompt as one plain string, with no cache mark -- for the batch path.

    Batched requests run in parallel, so each one writes the cache rather than reading what
    another wrote; measured, marking them cost more than it saved (Suite 4 holds the batch to
    a plain string). The sequential path, where each call follows the last, keeps the mark.
    """
    return system_prompt_for(job) + '\n\n' + resume_section(resume_text)


def current_resume_text() -> str:
    """The résumé uploaded in Search, as read when it was accepted. '' when there is none."""
    from app.resume import load_resume_text
    return load_resume_text()


def _claude_screen_cache_key(job: dict) -> str:
    """A hash of everything that actually influences Claude's screening decision for
    this listing -- the exact per-listing prompt text (title/company/location/
    platform/employment_type/seniority_level/description) plus the current system-
    prompt version. Stored on the job dict as job['claude_screen_cache_key'] right
    after a real screen (see reapply_filters' Claude Review step), so a later Filter
    re-run can tell -- cheaply and correctly, without guessing -- whether this exact
    listing needs to be sent to Claude again: unchanged content AND an unchanged
    prompt/ruleset hash identically, so the real (billed) API call is skipped and the
    previously-stored decision is reused as-is. Any change to either (a re-fetched
    listing with different text, or the user editing a rule in
    CLAUDE_SCREEN_SYSTEM_PROMPT) changes the hash and correctly forces a fresh screen.

    The résumé is hashed in too: every fact about the user comes from it, so a verdict reached
    against one résumé is never reused for another."""
    from app.resume import fingerprint
    raw = (prompt_version_for(job) + '\n' + fingerprint(current_resume_text()) + '\n'
           + _claude_screen_prompt(job))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# A name that is really a job board, an aggregator, or a placeholder. Claude is told not to
# return these; this is the check that they never reach a sponsor register lookup anyway.
_NOT_AN_EMPLOYER = re.compile(
    r'^(?:unknown|none|n/?a|not\s+(?:stated|specified|named|given|mentioned)|'
    r'confidential|undisclosed|anonymous|the\s+company|our\s+client|a\s+client|'
    r'client|employer|company|recruiter|recruitment\s+agency|'
    r'eures|indeed|linkedin|glassdoor|welcome\s+to\s+the\s+jungle|wellfound|monster|'
    r'startup\.jobs|magnet\.me|jobbird|nationale\s*vacaturebank|werk\.nl|jooble|'
    r'talent\.com|arbeitnow|remotive|remote\s*ok|we\s+work\s+remotely|otta|hackajob)'
    r'\.?$', re.I)


FILTER_CLAUDE_STEP_CHECKLIST = [
    'Can the work be done from where he lives?',
    'Needs a language his résumé lacks?',
    'Is the job paid?',
    'The right level?',
    'Is this a real job?',
    'Citizenship or residency required?',
    'Is it the job title searched for?',
    'University in a particular country?',
    'Who is the employer?',
]
