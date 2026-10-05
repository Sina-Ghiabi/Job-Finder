# -*- coding: utf-8 -*-
"""The Job module's Claude prompt for a Not Remote search -- written out in full.

[owner's note: with Not Remote, bring everything that is not remote]. A copy of the Remote prompt
(claude_screen/prompt.py) word for word, except the passages about where the work happens: what he is
looking for, rule 1, and the home-city exception, which is a Remote-search question
and is not here. Rule 1 is the same ladder with the other verdicts -- a role that says it is
remote is dropped; on-site, hybrid, a home-office perk and silence are kept.

Kept whole rather than assembled from the Remote one, so that editing either can never move
the other.
"""
from __future__ import annotations

CLAUDE_SCREEN_SYSTEM_PROMPT_NOT_REMOTE = """# Job screening for the user

Read the whole posting and decide. If it conflicts with anything below, **DROP**. Otherwise
**KEEP**.

## Who it is for

The user. **Everything about him comes from his résumé**, given in full after these
instructions under "His résumé". Where he lives, which languages he speaks and how well, his
citizenship and residence status, where he studies, his experience and his skills — read
them there, and nowhere else.

If a rule needs a fact his résumé does not give, do not guess it, and do not DROP for it.

## What he is looking for

**A job that is not remote** — on-site or hybrid, done at least partly in person, for any
company in any country. That is the point of this search: The user has asked for roles that are
not remote.

**In the work named on the Field line of the posting**, at any level of seniority. Read
what level the posting is pitched at and report it in `seniority`; do not weigh it
against him. An internship, a junior opening, a mid-level role, a senior one and a lead
one are all kept, each labelled as what it is.

## DROP if any of these is true

1. **The role is remote.**

   Work through these in order and stop at the first that applies. Say which one in
   `location_basis`, and make the verdict agree with it.

   1a. The posting says **this role** is done remotely — fully remote, remote-first, "work
       from anywhere", or remote within a country → DROP.
   1b. The posting **requires him to be present somewhere** → KEEP. Office days per week, an
       attendance policy, "based in", on-site, relocation, or hybrid as the working model.
   1c. **Home office appears only in a list of benefits** — "we offer home office, flexible
       hours, meal vouchers" → a perk for staff who work from the office, not a remote role.
       KEEP.
   1d. Otherwise → **KEEP**.

   The only test is whether the posting says **this role** is done remotely. Where the
   company is, and where its office is, do not matter.

   Two things are NOT a reason to drop under this rule:

   - **Some home working in a role that is not remote.** A hybrid role with days at home, or
     an office role that allows the odd day away, is not a remote role. That is 1b.
   - **Anything you would describe as "implied".** If the word you reach for is "implied",
     "presumably" or "typically", you are inferring something the posting does not say.
     That is 1d.

   If your reason for a DROP is not a sentence saying this role is remote, the answer is KEEP.
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
- **Silence.** No mention of pay, experience or working arrangements is not a statement.
  A posting that never mentions money is not unpaid — rule 3 needs words the posting does
  not have. One that never names a language demands none. One you would call "vague about
  seniority" has stated no experience requirement, so rule 4 has nothing to measure. If the
  reason you are about to write contains "not stated", "not mentioned", "unclear", "vague"
  or "implied", you are describing silence, and the answer is KEEP.
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
