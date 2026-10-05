# RoleHound

A personal, local job-search desktop application. It searches LinkedIn, Indeed and
Glassdoor through Apify, cleans the results down with a long chain of keyword rules,
optionally has Claude re-verify everything as a final safety pass, tracks which jobs
you've applied to, and remembers everything between runs. No server, no account, no
cloud database — everything lives on your machine as plain JSON files.

**This document exists so the project can be reconstructed from scratch if the code is
ever lost.** It documents not just what each feature does, but the exact keyword lists,
the exact order things run in, and *why* certain decisions were made — including things
that were tried and deliberately reverted.

Built with **PySide6** (Qt for Python), packaged as a single standalone **`RoleHound.exe`**
with PyInstaller.

---

## Table of contents

- **[Before you change anything](#before-you-change-anything)** — every mistake this project has already made, and what is done instead. Read this first.
- [Quick start](#quick-start)
- [The two-phase model: raw search, then Filter](#the-two-phase-model-raw-search-then-filter)
- [The Setup Wizard — every field](#the-setup-wizard--every-field)
- [Startup Websites Search & Company Popularity](#startup-websites-search--company-popularity)
- [Pre-flight health check — before every real search](#pre-flight-health-check--before-every-real-search)
- [How a search actually runs](#how-a-search-actually-runs)
- [The categorize/sort pipeline (what a raw Search actually still does)](#the-categorizesort-pipeline-what-a-raw-search-actually-still-does)
- [Phase 2 — what the Filter button does](#phase-2--what-the-filter-button-does-reapply_filters)
- [The content filters — exact rules, in exact order](#the-content-filters--exact-rules-in-exact-order)
- [The Claude final pass](#the-claude-final-pass)
- [The Job Search page](#the-job-search-page)
- [The My Applications page](#the-my-applications-page)
- [The Log panel](#the-log-panel)
- [Clear Search / Clear My Applications](#clear-search--clear-my-applications)
- [Excel export](#excel-export)
- [Sponsorship Visa column](#sponsorship-visa-column)
- [App icon](#app-icon)
- [Where everything is stored, and the exact file formats](#where-everything-is-stored-and-the-exact-file-formats)
- [Project file structure](#project-file-structure)
- [Running from source](#running-from-source)
- [Building the .exe](#building-the-exe)
- [Design decisions and things that were tried and reverted](#design-decisions-and-things-that-were-tried-and-reverted)
- [Full-codebase audit — 30 findings, all fixed](#full-codebase-audit--30-findings-all-fixed)
- [Audit round two — 16 findings, 4 of them caused by round one](#audit-round-two--16-findings-4-of-them-caused-by-round-one)
- [Audit round three — 13 findings, 0 critical](#audit-round-three--13-findings-0-critical)
- [The test suite (`tests/`)](#the-test-suite-tests)
- [Known limitations](#known-limitations)

---

## Before you change anything

**Read this section first. Every entry is something that was actually tried on this project
and turned out to be wrong.** Not theory, not style — each one cost real time, real money, or
real job listings, and each is written down so it is paid for once.

How to use it: find the area you are about to touch, read what has already been tried there,
and only then write code. If you are about to do something this section says was tried and
reverted, the burden is on you to say what is different this time.

Every entry has the same four parts:

| | |
|---|---|
| **Tried** | what was done |
| **What happened** | what it actually cost, in numbers where they exist |
| **Now** | what the code does instead |
| **Guarded by** | the test that fails if someone undoes it — or *nothing yet*, honestly |

---

### The nine rules that came from being wrong

These are the general lessons. Everything after them is the specific evidence.

#### 1. Count, then read

A number produced by a script is a claim about the data, not a fact about it. Every large
count in this project that was reported without reading its rows was wrong at least once.

- "580 listings have `'nan'` as their posted date" — an artefact of a scratch JSON round-trip.
  The Bank contained **zero**.
- "10 listings have epoch dates" — same artefact.
- "74 titles still carry the board's name" — whitespace-only differences.
- "286 listings were removed as duplicates with no twin" — 221 were genuine duplicates the
  audit tool could not pair up; only 4 were fakes.

All four were raised as faults and all four had to be retracted. The fix is not "be more
careful": it is to print the rows and read them before reporting the number.

#### 2. A green test suite is not evidence that the thing works

The two largest faults in this project were found by the user reading real output, not by 2,400
passing assertions:

- The **language filter caught 13 of 1,778** German requirements. Every test passed, because
  the tests were written in the same language the rule understood: English.
- **Three of the nine listings Claude marked "apply"** were not vacancies at all — a careers
  article, a salary reference page, an organisation's about page. Nothing looked for them
  because nothing knew that kind of page existed.

Tests prove the code does what it was written to do. They cannot tell you the thing it was
written to do was the wrong thing. Only real output can.

#### 3. A docstring's assumption goes stale silently

`requires_language_besides_english` said, in its own docstring: *"Reads the text after
translation, so a German posting has become English by the time it gets here."* That was true
when it was written. Translation was later removed to stop paying DeepL, every other rule was
given multilingual vocabulary, and this one was not — and the docstring kept promising the old
world to everyone who read it.

When you remove a stage, grep for every rule that depended on it. The comment that explains
why code is correct becomes the thing that hides that it no longer is.

#### 4. Silence is not a statement — except about the working arrangement

A posting that does not mention salary is not an unpaid posting. One that never names a
language demands none. One you would call "vague about seniority" has stated no experience
requirement, so there is nothing to measure. Claude broke this rule 17 times in 111 listings
before it was forced to quote the posting first.

**The working arrangement is now the one exception, and it is the user's own reversal.** His
words, 4 October 2026: *owner's note: no - silence is not to be kept any more* — a posting that never
says the work can be done away from an office has not said it can, and it is dropped.

That exception was already half-true and the halves disagreed, which is why this rule needed
rewriting rather than annotating:

- **`passes_work_location_rule` always dropped silence** in a Remote search. See `F-4`: 991
  listings, measured, deliberate.
- **Claude's rung 1d kept it** — "1d. Otherwise → **KEEP**." So the cheap rule deleted a
  silent posting and the expensive one would have kept it, and which answer the user got depended
  on which stage saw the row.

Now both drop it, from one source string applied to all four Remote prompts at once (see area
5). The Not Remote prompts are untouched: their rule 1 is the inverse, so "silence drops it"
would be nonsense there. **Pay and experience keep their protection** — rule 3 still needs
words saying the work is unpaid and rule 4 no longer drops at all, and widening the reversal
to pay would resurrect `O-3` exactly.

For everything other than the working arrangement the rule stands unchanged, and the reason
it is the user's stands too: he would rather see a job that turns out to be unsuitable than never
see one that was.

**The cure for silence is a better source, never a better guess** — and when no better source
is reachable, the cure is to accept the silence. See *"LinkedIn's workplace badge"* in area M
for the three times that was checked and the answer it gave.

How often does it actually matter? Measured on the 127 listings that reached Claude on the
Germany run: **117 say how the work is done, 10 do not**, and two of those ten were not
vacancies at all. Eight listings in 127.

#### 5. A rule that lives in ten places is ten rules

Claude's rule 5 exists in the Junior prompt (Remote and Not Remote), Entry, Mid and Senior
twice each, and the Internship module under its own number and wording. Editing one of them
made the Levels silently disagree — and this has now happened **twice**, once as O-5 and once
as O-17.

Both times the guard written after the first occurrence caught the second. When you change a
shared rule, change it from one source string by script, never by hand, and regenerate the
eight `.md` mirrors from the prompt itself.

#### 6. Both directions, on real data, before it ships

A rule that removes listings has two failure modes and only one is visible. Under-firing is
noise; over-firing loses a job and nobody ever knows.

Every filter change in this project is now measured on the real corpora — 8,133 rows in the
Bank, 5,442 of them German — and a random sample of what it *newly removes* is read by eye.
That sample has caught a real fault every single time it has been taken:

- the editorial rule's first draft took 4 real postings, all from employers' own sites
- the language rule's first draft misread *"idealerweise Deutsch"* and *"or the willingness to
  learn"* as requirements
- and it added Italian to the list of languages the user lacks, which would have emptied Italy

#### 7. Follow the data to the end, not to the test

Three faults in one evening came from reading where a value travels after the feature that
creates it:

- `set_drop_note` rstripped the posting, so the screening cache key changed and 3 of 14 real
  listings were re-screened and **re-billed** on every run
- Excel's 32,767-character cell limit cut exactly the note that explained a removal
- `add_application` copies `description` into the record, so a job the user kept by hand was
  filed with "WHY THIS WAS REMOVED" attached

None of these failed a test. All three were found by opening the next file the data reaches.

#### 8. Fail open, never silently

Every Claude call, every network fetch, every enrichment step keeps the listing when it fails.
A network hiccup must never look like a verdict. The one exception is a *parse* failure, which
is retried rather than read as a silent KEEP — because an unreadable answer is not an answer.

The corollary: an errored call is never cached. A transient failure frozen in as "no decision"
is worse than paying for the call again.

#### 9. A stage that can run for an hour must say where it is

The deep crawl opened 781 listing pages over **83 minutes without writing one line**. It was
working perfectly; there was no way to know that from outside, and the only other sign of life
— credit ticking down — stalls too while a batch waits. Silence that long is indistinguishable
from a hang, and the reasonable response to a hang is to kill the app and lose everything
already paid for.
---

---

### What changed on 3–4 October 2026, and where each piece is written up

The `T-` codes are this round's findings. Read the ones that touch what you are about to open;
each is written where its code lives, not here.

| what changed | code | area |
|---|---|---|
| `"turin"` matched inside `"manufacturing"` — 386 listings skipped the Remote rule | `T-1` | 2 |
| The Type column was printing raw Dutch (`Vast`, `Tijdelijk`) | `T-2` | 2 |
| Seniority is classified by `rules.seniority_of`, not filtered | `T-3` | 2 |
| Rule 4 reports seniority instead of dropping for it | `T-4` | 5 |
| Eight job prompts became two; the cache key no longer varies by Level | `T-5` | 5 |
| What each actor really honours — `f_WT`, `f_E`, `sortBy` are **ignored** | `T-6` | 6 |
| The five on/off switches, and `actor_filters.py` | `T-7` | 6 |
| What a real run costs, and where the 105 minutes went | `T-8` | 6 |
| The quote guard was overturning correct removals | `T-9` | 4 |
| The Seniority column, and `M-9` caught twice | `T-10` | 13 |
| A suite not in `run_all.py` does not exist | `T-11` | 15 |
| The pairing "English **and** Dutch" is a KEEP — 385 listings back | `T-12` | 3 |
| The `English?` column — the pairing, picked out in the table | `T-13` | 13 |
| The Level deleted in **two** places; removing one left the other running | `T-14` | 2 |
| Type stops filtering: it removed 295 of 321 survivors | `T-15` | 2 |
| **LinkedIn moved to a new actor that returns the Hybrid/Remote tag** — and the price I first quoted for it was wrong | `T-16` | 6 |
| The Search window's actor panel: one dropdown per parameter, no prose | `T-18` | 6 |
| **Search offers Type — Any / Thesis / Internship — and no seniority**; Remote-only no longer asked of Thesis/Internship; Glassdoor's Not Remote bug; the four vocabularies | `T-19` | 6 |
| The Type column reads the local-language words: Dutch `Stage …` is an Internship | `T-20` | 2 |
| **Remote / Not Remote under Type, Remote locked for Thesis and Internship; every dropdown is the actor's own parameter, sent as chosen** | `T-21` | 6 |
| Three text shapes the Work Location rule could not see: client sites, hedged remote, spelled-out numbers | `T-17` | 2 |

Four of these reverse something the Document previously stated, so read the old text too
rather than only the new: **rule 4 of the nine** (silence is no longer a statement *about
the working arrangement*), **`T-5`** (the cache key must now *not* change with the Level —
the assertion was inverted on purpose), **`T-16`**, which overturns the decision in area 16
to "stop looking" for LinkedIn's workplace tag, and **`T-12`**, which reverses the purpose of
`O-16` itself. `O-16` was the work of making the language rule catch *"Deutsch und
Englisch"*; `T-12` is the user deciding he wants those listings after all. The `O-16` write-up
stays as it is, because the machinery it built is what `T-12` reuses to tell the pairing
apart — it just hands the answer to a column instead of to the delete loop.

### Where to look, by the file you are about to open

Every finding below carries its campaign code (`O-16`, `N-2`…). The full write-up of each,
with the measurements, is in **`Test-Campaign-Bugs.md`** under the same code.

| about to edit | read | findings |
|---|---|---|
| `pipeline/pages.py` | [1 · Is this a vacancy?](#1--is-this-a-vacancy) | A-1 A-2 A-3 A-4 L-3 N-4 N-8 K-1 K-3 O-17 R-1 |
| `pipeline/rules.py`, `filters.py` | [2 · The keyword filters](#2--the-keyword-filters) | F-1 F-2 F-3 F-4 L-2 N-3 M-3 M-7 M-8 O-1 O-2 **T-1 T-2 T-3 T-14 T-15 T-17 T-20** |
| `ui/filter_dialog.py` | [2 · The keyword filters](#2--the-keyword-filters) | **T-14 T-15** — what the window stopped offering, and why |
| `pipeline/language.py` | [3 · Language](#3--language) | O-16 I-3 R-3 **T-12** |
| `pipeline/claude_screen/` | [4 · Claude](#4--claude) | G-1 O-3 O-5 O-15 D-1 M-2 M-4 L-8 S-1 R-5 |
| the prompts and the 8 `.md` mirrors | [5 · Prompts and Levels](#5--prompts-and-levels) | M-1 M-3 O-5 O-17 **T-4 T-5 T-16** (rule 1b) |
| `pipeline/search/`, the actors | [6 · The search](#6--the-search-the-money-path) | I-1 I-2 I-3 I-4 O-9 O-10 O-12 J-1 J-2 C-1 C-2 N-6 R-4 **T-6 T-7 T-8 T-16 T-18 T-19 T-21** |
| `pipeline/actor_filters.py`, `sources_enabled.py` | [6 · The search](#6--the-search-the-money-path) | **T-6 T-7** — what each actor really honours, and the five switches |
| the duplicate passes in `filters.py` | [7 · Duplicates](#7--duplicates) | L-4 L-5 N-5 O-6 |
| `pipeline/enrich.py`, `fetcher.py` | [8 · Getting the real text](#8--getting-the-real-text-of-a-posting) | B-1 B-2 N-7 K-2 K-4 |
| `sources_norm.py`, `sources_apis.py` | [9 · Sources and normalisation](#9--sources-and-normalisation) | N-1 N-2 O-14 M-6 R-2 |
| `storage.py`, the Bank | [10 · Storage](#10--storage-and-not-eating-your-own-data) | O-4 L-7 M-5 |
| the Log, `preflight.py`, `healthcheck.py` | [11 · Saying what is happening](#11--saying-what-is-happening) | O-7 O-8 O-13 M-10 C-1 |
| anything that spends money | [12 · Cost and caching](#12--cost-and-caching) | D-1 M-4 O-8 S-1 |
| `excel_export.py`, `ui/` | [13 · The UI and the export](#13--the-ui-and-the-export) | M-9 **T-10 T-13** |
| the build, the icon, git | [14 · Packaging](#14--packaging-the-exe-icons-git) | — |
| a signal we do not have | [16 · Looked for, not gettable](#16--signals-we-went-looking-for-and-could-not-get) | — |
| anything at all | [15 · How to work here](#15--how-to-work-on-this-codebase) | E-1 L-1 L-8 O-10 O-11 |

---

### 1 · Is this a vacancy?

There are **three** kinds of page that are not a vacancy, and each needed its own rule. If
you are adding a fourth, say which of these it is not.

| kind | example | caught by |
|---|---|---|
| an index of vacancies | `karriere.at/jobs/hainburg` · "158 Jobs Hainburg" | `_LISTING_URL`, `_COUNTS_VACANCIES` |
| an article listing *companies* | "20 Companies Building Our Remote First Future" | `_COLLECTION_URL` |
| a board's own editorial | `hays.de/en/job-profiles/data-scientist` | `is_editorial_page` |

**A-1 · A page of jobs screened as if it were a job.** 73 of the 557 Austrian listings that
reached Claude were category pages, saved searches and indexes — and the *most expensive*
listings in the corpus, 6,885 characters at the median against 3,775 for a real posting,
because a page of forty jobs is longer than one job. Fixing it cut Austria 557 → 499 and the
Netherlands 93 → 79, about **15% of the text that reaches Claude**.

**A-2 · The first version of that rule ate real vacancies.** Of 73 listings a title-and-URL
rule flagged, **27 were genuine**. Now: the URL decides and the title only votes. A board
says what a page *is* in the shape of its address — `/details/`, a 5+ digit id, a trailing
hash — and no wording in a title outranks that.

**A-3 · An index page dropped even when nothing could be taken out of it — FIXED, then
REVERSED.** For a while a page that could not be emptied was kept, so as not to lose what it
listed. The user asked what good a kept page that gave up nothing is. Measured: of 88 that could
not be emptied, 76 died to ordinary filters and **every one of the 12 that reached Claude was
an index page** — 61,845 characters of nothing. Now every index page goes, emptied or not.
The reasoning that was wrong: keeping a page only saves the vacancies inside it if keeping it
is a *route* to them, and when it cannot be emptied, it is not.

**A-4 · Two real vacancies flagged as index pages.** What A-3's rule was really protecting.
Handled where it belongs, in `_SLUG_SAYS_LIST` / `_TITLE_SHAPED_SEGMENT`, not by keeping
every unemptied page.

**L-3 · Index pages that count their vacancies were claimed as postings.** `_COUNTS_VACANCIES`
is the one title signal strong enough to outrank the URL, because **a real vacancy never says
how many vacancies there are.** `positions` is deliberately absent from that list: a real
Wellfound advert reads "UI/UX Designer India ~ Intern 3 Months + Full time 3 Positions",
where the number counts openings in *one* posting.

**N-8 · …in eleven languages.** The Amsterdam run read "31 data scientist vacatures in
Amsterdam", "68 wo data scientist vacatures bekijken" and "83 parttime data scientist
vacatures" as single adverts. The word for "vacancy" in every language the app searches is in
the pattern now — `vacatures`, `banen`, `offres`, `emplois`, `annunci`, `ofertas`, `vagas`,
`lediga jobb`, `stillinger`, `työpaikkaa`, `Treffer`, `Stellenangebote`.

**N-4 · A page gave the board's list of other vacancies instead of the posting.**
`is_board_index_text` reads the description, not the address — some boards serve a real URL
whose body is their own list.

**K-1 · "53 XING pages gave up nothing" — XING was working.** The report was measuring the
wrong thing. A site that answers and yields no *recognisable posting links* is not a site
that failed; `postings_inside` was the thing to fix, not XING.

**K-3 · Articles and company pages pass as job postings — MEASURED, NOT WORTH A FIX (then).**
Recorded as not worth fixing at the time. **O-17 later proved that wrong**: three of them
reached the nine listings Claude marked *apply*. If a finding says "not worth a fix", it means
*at the volume measured then* — re-measure before trusting it.

**O-17 · A board's own editorial reached the "apply" list.** A careers article, Hays' salary
reference page, an organisation's about page. Neither index rule fires on them (they list no
vacancies) and their addresses are title-shaped, so `_SINGLE_POSTING_URL` claimed them.
`is_editorial_page` reads the address first and the title second. 33 of the Bank's 8,133.

> **The trap, and it is the important part.** The first draft included `/about-us/`,
> `/ueber-uns/`, `/artikel/`, `/news/`, `/presse/` and took **four real postings** — the best
> kind in the corpus, an employer's own site with no agency in between, because German
> employers file openings under *Über uns / Karriere*. Those five path words are gone, and
> `_VACANCY_IN_URL` overrules everything: an address naming a vacancy **is** one, whatever
> section holds it. The job word must be a **whole path segment** — a looser `/jobs?[/-]` read
> Hays' `/job-profiles/` as the word "job" and rescued the very page that started this.

**R-1 · 17 listings disappeared after index-page expansion — RESOLVED.** Not lost: they were
duplicates of postings the expansion had already pulled out of the index.

---

### 2 · The keyword filters

**The order matters and it is not arbitrary.** The cheapest rule runs first, because
everything it removes is work the later rules do not have to do. `remove_off_field` is one
regex against a title, no network; the language rule reads the whole body; Claude costs money.

**L-2 · The field filter had never run.** `job_field_words.py` was written when the Pool was
built and then **never imported**. On the Austrian run, of 411 jobs reaching Claude, **86 were
Vertrieb, Verkauf, Copywriter, Customer Support, Maschinenbau and HR** — $0.28 of Claude per
country spent reading sales jobs. The lesson is not about that function: **a module can exist,
be correct, be tested and never be called.** Check the call site, not just the code.

**F-1 · "on-premise" is about servers, not desks.** It was in
`ON_SITE_OR_HYBRID_KEYWORDS` and it means the software runs on your own hardware.

**F-2 · "hybrid" fires on cloud architecture and on benefit lists.** "hybrid cloud",
"hybrid model of care", "hybrid benefits". The word needs its surrounding clause to agree.

**F-3 · "arbeitsort" and "einsatzort" are form fields.** They are the *label* on a German
posting's location field — present on almost every German advert, saying nothing about
whether the work is remote.

**F-4 · 991 listings dropped for saying nothing — RESOLVED, the rule is right.** In a Remote
search, a posting that never says it can be done remotely is dropped. That is the user's rule and
it is deliberate: `passes_work_location_rule` requires a positive statement. Do not "fix" this
into silence-passes without asking him.

**T-1 · `"turin"` was matching inside `"manufacturing"`, and 386 listings skipped the Remote
rule entirely.** The most expensive single line in the Filter, and it had no test.

`mentions_milan_or_turin` is the **first** question `passes_work_location_rule` asks, and a
yes means keep unconditionally — the Remote rule is skipped. It tested
`city in rule_text(row)`, a plain substring, and the city names are four and five letters:

```
turin  ⊂  manufacturing · structuring · nurturing
turin  ⊂  sturing   — ordinary business Dutch: "kpi-sturing", "aansturing",
                      "salessturing", "datagedreven sturing"
milan  ⊂  "our engineer Milan shows how smarter shipping systems…"   (a first name)
```

Measured on the real 4,325-row Netherlands Bank: **395 rows said yes, 9 were really about
Milan or Turin.** 386 false positives, 356 of them Dutch — every one exempt from the rule that
is the premise of the whole search. One reached Claude, which dropped it with *"hybrid work
required in eindhoven, not turin"*: Claude read it correctly, the keyword rule had waved it
through, and the right answer cost a paid second opinion.

**Now** · `\b(?:turin|torino|milan|milano)\b`. 395 → 9, zero false positives; listings
reaching Claude went 88 → 78. **28 assertions in suite 1, both directions** — a fix that
stopped matching Turin at all would pass a one-sided test and silently delete the Italian
listings the rule exists to save. The remaining false positive is the engineer named Milan,
left deliberately: one row in 4,325, and it fails in the safe direction.

> **The lesson is `L-2` in another shape.** There, a module existed, was correct, and was
> never imported. Here the rule existed, was imported, was called in the right place — and
> **nothing asserted anything about it.** Check that a rule has a test, not just a caller.

**T-2 · The Type column was printing Dutch.** `_EMPLOYMENT_TYPE_LABELS` held seven English
keys, and an unrecognised value was returned **unchanged** — `.get(value, value)`. So werk.nl,
Jooble NL and EURES filed **72 listings as `Tijdelijk` and 39 as `Vast`**, Dutch for temporary
and permanent.

Those 39 are permanent full-time jobs that ticking Full-Time could not find, because their
Type was the word "Vast". Both values also fell outside `CATEGORY_ORDER`, so they sorted
nowhere, and outside `CATEGORY_BADGE_COLORS`, so the table painted them fallback grey.

**Now** · Dutch, German, French, Italian, Spanish, Portuguese and Nordic terms are mapped, and
an unrecognised value becomes `'Other'` rather than itself. The raw word stays on the row as
`employment_type` for anyone who wants to see what the board actually said. Across the Bank:
`Tijdelijk 72 → 0`, `Vast 39 → 0`, `Full-Time 3,721 → 3,760`, `Temporary 22 → 94`.

**T-3 · Seniority is classified here now, not filtered.** `rules.seniority_of` is
`categorize`'s twin: it reads the title first (whole words — `T-1` is in this same module),
then LinkedIn's own `seniority_level`, and answers `'Unspecified'` for silence rather than
guessing. `SENIORITY_ORDER` is its vocabulary. Why it exists and what it replaced is in area 5
under `T-4`.

Two things about it that are load-bearing:

- **Claude's answer wins where there is one.** It has read the whole posting and been asked
  directly; this function has read a title. `job['claude_seniority']` is checked first.
- **It must take a pandas Series.** It ran through `df.apply` in `run_search` with
  `(row or {}).get(...)`, and `row or {}` raises *"truth value of a Series is ambiguous"*.
  **That exception was swallowed by the surrounding `try` and took the rest of the column
  block with it — `sponsorship_visa` stopped being written at all.** Suite 4 found it by
  reading a column that had silently vanished. `categorize` avoids this by calling `.get()`
  straight off the row; so does this.

**M-3 · A title-only check would have deleted every thesis — measured, not chosen.** The
obvious optimisation, killed by measuring it first.

**M-7 · "Graduates aged 18 to 28 years" read as an experience range.** A VIE graduate
programme — the opposite of a senior job — dropped for being open to young people. Measured
across all five corpora before touching it: **272 ranges matched, 208 beside an experience
word, 5 beside an age word, and not one experience range anywhere starting at 12 or more.**
That shape gave two narrow guards rather than the blunt "require an experience word", which
would have let real senior postings through ("Minimum of 4-6 years in a GTM Operations role"
never says the word): an age word within 90 characters disqualifies the range outright, in
every language the app reads (`aged`, `Alter`, `leeftijd`, `età`, `ålder`), and a lower bound
of 12 or more must be vouched for by an experience word.

**N-3 · "Lead Data Engineer" was the wrong level for nobody.** The level words had gaps.

**M-8 · Lead and Staff titles pass the keyword stage for Mid and Senior — BY DESIGN.** They
are legitimate at those levels; Claude decides.

**O-1 · A Not Remote search kept a job in another country.** `_step_place` reads
`geo.CITY_COUNTRY` for the cities actually chosen. A Not Remote search means the user must be able
to reach the office, so a posting in another country is not a candidate.

**O-2 · The Thesis and Internship modules reported the opposite of what they did.** A remote
posting removed in a Not Remote search was logged as "cannot be done from Turin". The Log line
is not decoration: it is the only thing that says *why* a listing went.

> **Title-vs-description priority was built and deliberately reverted.** Several conflicting
> iterations — title wins outright, then title-then-JD both must pass, then JD has priority —
> and none was better. Title and description are concatenated into one string and checked
> together, with no special-casing. **Do not assume title-priority logic is wanted; it was
> removed on purpose.**

> **`english and` / `and english` as bare substrings** deleted 95 of 2,542 real listings, many
> nothing to do with language: "...and English benefits & perks", "fluent English and strong
> communication skills", "German and English language **courses**" — a free perk. A language
> must be **named**. On the same corpus: 9 wrong deletions stopped, 19 real demands the
> substring had missed were caught.

#### `T-14` · the Level deleted in TWO places, and removing one left the other running

The worst kind of bug this project produces, and the clearest example of rule 5 of the nine:
**a rule that lives in two places is two rules.**

Seniority was supposed to stop deleting (`T-4`). `profile.is_wrong_level` came out of
`_step_rules`, rule 4 of the prompt was rewritten to report instead of drop, the Seniority
column and its filter button went in, and the Filter window lost the control. All of that was
done, and **the Level went on deleting.**

The second one was a single line in `COUNTRY_RULE_SECTIONS`:

```python
('Too senior', 'senior'),
```

`_step_rules` asked the question in English. `_step_country_rules` asked the *same* question
in the posting's own language, with each profile's own word list swapped in — which is why
the Log said *"Wrong level for Mid"* rather than *"Too senior"*, and why the two never looked
like the same rule when read.

**It was not found by reading the code. It was found by comparing outputs:**

```
same Bank, filtered at junior   151 kept, 49 of them Senior
same Bank, filtered at mid      101 kept,  0 of them Senior
```

Same pool, same rules, different Level — and the only thing that could produce that
difference was a Level rule still firing. With both gone, **all four Levels keep the same 162
rows**, which is now the assertion.

What stayed, deliberately: the vocabularies keep their `senior` sections (the Internship and
Thesis modules read them) and `is_too_senior` is still tested. Removing a working rule because
one caller stopped needing it is how a module becomes unreachable — that is `L-2`.

**The lesson for the next change of this shape**: after taking a rule out, do not re-read the
diff. Run the thing twice with the setting that rule depended on set differently, and compare
the *outputs*. A second copy cannot hide from that, and it hid from everything else.

#### `T-15` · Type stops filtering — it removed 295 of 321 survivors

`filter_by_category` ran inside `_step_chosen`, on the kinds ticked in the Filter window. On
the real Netherlands run, with Part-Time ticked:

```
321  listings had survived every other rule
-295 removed by the Type filter -- every Full-Time job, because Part-Time was ticked
= 26 left
```

> *owner's note: the Type filter may go, as the kinds of jobs to show are chosen in the table*

So the step is gone and the choice is the Type column's own filter button, where changing his
mind costs nothing instead of a whole Filter run. Same instruction, same reasoning and the
same order as `T-14`: **Seniority first, then Type, and nothing deleted for either.**

Three things about how it was removed:

- **`categories` is still accepted and still saved.** An older `settings.json` loads
  unchanged; the value is simply not read in that step any more. Nothing was migrated.
- **`filter_by_category` itself stays, with its tests.** It is correct, and it is still the
  only thing in the project that knows a PhD advert is not a thesis placement even though it
  says "thesis" all through its body. Its four assertions in `t4` used to go through
  `reapply_filters`; they call the function directly now, because the Filter no longer does —
  a correct rule with no caller **and** no test is how `T-1` survived for months.
- **The Filter window had to say so.** The *"Kind of role, and visa"* box is now just
  **Visa**; the Level box is labelled *"Level — chooses the vocabulary, not what survives"*
  with a grey note under it saying nothing is removed for its level any more. A window that
  still offers a control which no longer does anything is `O-2` in another costume. The empty
  `self.category_boxes` dict is kept so the dialog's return shape is unchanged for its
  callers and its tests.

#### `T-17` · three shapes the Work Location rule could not see

Found by taking the user's three Hybrid adverts apart word by word (`T-16`). The tag fixes LinkedIn;
Google, Indeed, Glassdoor and the direct APIs carry no tag, and KLM's advert came from Google. So
the text rule had to learn what it was missing — and **each change was measured on the real
4,325-row Bank before it was written**, because the rule has a measured softening of its own
(*562 listings dropped for a "hybrid" that sat in a job board's filter menu*) and a change that
re-opens that costs real jobs. All three came out the same way: **zero listings newly kept, and
every listing newly dropped read by eye and genuinely hybrid.**

| shape | the advert | what was wrong | newly dropped on the Bank |
|---|---|---|---|
| **client sites** | VisionBI: *"gemiddeld twee dagen op de klant locatie"* | `_DAYS_IN_OFFICE` wanted a number of days beside an *office* word, and a client's address is not one — in any language. `_OFFICE_WORD` now includes `klant locatie`, `bij de klant`, `client site/location`, `customer site/location`, `beim Kunden`, `Kundenstandort`, `chez le client`, `presso il cliente`, `hos kunden` | 10, e.g. *"hybride werken: op ons hoofdkantoor in de meern, bij de klant of vanuit huis"* |
| **hedged remote** | KLM: *"Als je functie dit toelaat: thuiswerken"* | "if your role allows it", in a benefits list, was the whole remote claim. `_HEDGED_REMOTE` (als/indien/if/wenn … toelaat/allows/mogelijk/possible; *waar mogelijk*; *where possible*; *in overleg*; *by arrangement*; *op aanvraag*) | 7 |
| **spelled-out numbers** | the same VisionBI advert | the pattern knew only `one/two/three/four`. *"twee dagen per week op kantoor"* was invisible, and so was every Dutch, German, French, Italian and Spanish advert that spelled the number. `_NUMBER_WORD` adds `twee drie vier · zwei drei · deux trois quatre · due tre quattro · dos tres cuatro` | 11 — **every one literally "twee dagen per week op kantoor / bij de klant"** |

Three things that must not be undone:

- **A hedged remote word is overruled by one plain statement.** `_remote_only_when_hedged` is
  all-or-nothing: a posting that says *"fully remote"* once and *"als je functie dit toelaat:
  thuiswerken"* once is not hedged, and `_ALSO_FULLY_REMOTE` overrules it anyway.
- **`up to two days of home office` is still dropped, and that is correct.** It is not an office
  day — it is a *limited number of home days*, which means the rest of the week is in the office
  (`_LIMITED_HOME_DAYS`, older than this entry). A test written the other way round failed, and
  the test was wrong, not the rule.
- **The broad version was measured and deliberately not applied.** Letting *any* on-site word
  overrule a stray "remote" unless the advert says fully remote would drop **519 of the 1,205**
  that pass today. Reading the 519, a large share are weak locational phrases — *located in* (25),
  *work location*, *je werkt op* (11), *office location* — that say where the company is, not that
  he must sit there, and applying it blind would build the opposite error: real remote jobs lost
  silently. It is a candidate for a narrower version (strong terms only), not a done change.

**Still invisible to every text rule: IDPP.** *"Working Model: Remote"* in the advert, Hybrid on
LinkedIn. Only the tag can catch it (`T-16`), and for a source with no tag nothing can.

#### The Log checklist was renamed twice in the same session, for the same reason

`FILTER_RULES_STEP_CHECKLIST` is what the Log prints as *"this rule genuinely ran against
every listing"*. It listed six rules; four run:

```
Work Location rule
Wants another language instead of English     <- was "Requires a language besides English"
Text-based sponsorship restriction
Unpaid
                                              <- "Too senior" was here (T-14)
                                              <- "Lacks English mention" was here (deleted earlier)
```

The language line was renamed because after `T-12` it removes far less than its old name
claimed — only a posting wanting another language *instead of* English. **A checklist line
that overstates what it deleted is the same fault as not saying why at all** (`O-2`).

`_rules_checklist(profile)` used to rename the last line per Level, so the Log read *"Wrong
level for Mid"*. It returns the list unchanged now. `profile` stays in the signature on
purpose: every caller passes it, the tests call it both ways, and if a Level rule ever comes
back it must be **added to the checklist deliberately** rather than appear by renaming.


### 3 · Language

Two separate jobs live in `language.py` and confusing them is the root of most of what went
wrong here: **detecting** what language a posting is written in, and **deciding** whether it
demands a language the user does not have.

#### Detection — why it is `lingua`, not `langdetect`

Measured on 400 real listings from a real search, labelled by unmistakable function words
(`und/der/die` against `the/and/with`):

```
                  full description        first 180 characters
langdetect        399/400   13.7s         379/400  -- 21 wrong
lingua            399/400    3.1s         396/400  --  4 wrong
```

**The short-text column is the reason to switch, not the clock.** This detector's verdict used
to *delete* listings: one wrongly called non-English was "translated", marked
`was_translated`, and then dropped by `lacks_english_mention` for not containing the word
"English". langdetect is wrong that way five times as often, and short descriptions are common
here because four direct-API sources return almost no text at all.

Speed was a bonus, not the point — and the honest number is the one from the real corpus, not
the sample: the 400-listing sample suggested 4.4×, the real 2,542-listing corpus gave 2.6×
(87s → 33.7s of a 303s language step), because real descriptions are longer.

The detector is **restricted to the languages this app can actually meet**. An open-ended
detector has to weigh Tagalog and Yoruba against German on a fragment of an advert, and every
extra candidate is another way to be wrong about text that was only ever going to be one of
a known handful.

#### `_MIN_LANGDETECT_CHARS` — why very short text is `unknown`, not `en`

On short text a detector is unreliable in a specific, repeatable way:

```
'AI'      -> Hungarian
'Data'    -> Indonesian
'Remote'  -> Romanian
```

The user flagged this as suspicious before it was confirmed. Below the threshold the text is
`unknown`, and that is deliberately **not** the same as `en`: translation skipped `en` *or*
`unknown` together, so a short listing never got misclassified into the wrong bucket at all.

#### The demand rule — `O-16`, the biggest single fault in the project

> **Tried** · an English-only vocabulary, because at the time every listing was translated to
> English before the keyword stage.
> **What happened** · translation was removed to stop paying DeepL. Every other rule was given
> multilingual vocabulary; this one was not, and **its own docstring kept promising the old
> world**. Of 1,778 German listings stating a German requirement in German, it caught **13**.
> **Now** · the posting is read in its own language, in three shapes, in ten languages.
> **Guarded by** · section 1.language — **7** walls, **9 pairings that must be kept**,
> 11 non-walls, 4 Italian probes. The 16 walls became 7 + 9 when `T-12` landed; the nine
> are kept as assertions rather than deleted, because they are the best collection in the
> project of what the pairing looks like in a real advert.

Three shapes, because a posting states the demand three different ways:

```
pair      "Deutsch und Englisch"          _SECOND_LANGUAGE_PATTERN     ← no longer deletes
level     "Sehr gute Deutschkenntnisse"   _LEVELLED_LANGUAGE_PATTERN   ← names no English
numeric   "Deutschkenntnisse Niveau C1"   _CEFR_PATTERN
```

The pair pattern stopped deleting on 4 October — see **`T-12`** below — and is still here,
still tested, because it is the most precise description in the project of what the pairing
*is*. Read `T-12` before touching any of the three.

The two gaps that made it fail were both about **how a language writes itself**:

```
looked for  english      the posting writes  Englisch           not even a substring
looked for  deutsch\b    the posting writes  Deutschkenntnisse  compounds have no boundary
```

Hence every name carries `\w*`. Hence also the one exclusion that has to be there:
**`deutsch(?!land)`** — "in Deutschland", "deutschlandweit" and "Deutschlandticket" appear in
most German postings and name the country.

The levelled pattern reads **both orders**, because languages differ: German puts the level
first (`gute Deutsch-`), Italian and Spanish put it after the verb (`conoscenza della lingua
italiana`), English does both (`fluent German` / `German fluency`). The gap between them is
short and cannot cross a sentence end, so a level word in one bullet never reaches a language
name in the next.

#### `T-12` · the pairing "English **and** Dutch" is a KEEP

The user set out the four shapes a posting can have and what he wanted of each, and he had the
first three right about the code as it stood:

| the posting | before 4 Oct | after |
|---|---|---|
| says nothing about language, and is **not** in English | dropped (`silent_about_english`) | unchanged |
| says nothing, and **is** in English | kept — already readable | unchanged |
| wants another language only — *"Sehr gute Deutschkenntnisse"* | dropped | unchanged |
| wants English **and** another — *"Deutsch und Englisch"* | dropped | **KEPT, and labelled** |
| wants English only | kept | unchanged |

> *owner's note: a posting asking for English together with another language must be accepted too*

A posting asking for English alongside Dutch has said the work can be done in a language he
has. Whether the second one is a wall is a judgement about his own CV, and he would rather
make it himself looking at the advert than have it made for him. Same reasoning as `T-4` for
seniority and the Type column before it: **classify, do not delete.**

**On the real 4,325-row Netherlands Bank: 776 deletions became 391. 385 listings came back,
and nothing new was deleted** — the before/after sets are nested, which is the check worth
making when a rule is loosened. End to end, the Filter went from **75 listings kept / 26
clean** to **166 kept / 57 clean**, for $0.7 of Claude. What came back, by its own words:

```
Health Technology Internship              Dutch and English
Postdoctoral researcher, Comp. ling.      Dutch and excellent command of academic English
Werkstudent AI Specialist                 Engels en Nederlands
Medior Data Platform Engineer             English and Dutch
Graduation: Automated sales lead …        Dutch / English
```

What still goes, and it is the only shape left that does:

```
Traineeship Data Analytics                Uitstekende beheersing van de Nederlandse
Young AI Professional / Traineeship       vloeiend Nederlands
Career Coach IT                           vloeiend Nederlands
Online Data Analyst Netherlands           Dutch proficiency
```

##### Removing the pair pattern from the loop was NOT enough, and this is the trap

The levelled pattern catches the pairing too. *"You are fluent in English and Dutch"* puts
`fluent` within twenty characters of `Dutch`, so `_LEVELLED_LANGUAGE_PATTERN` fires on it with
no help from the pair pattern at all; *"Sehr gute Deutsch und Englisch Kenntnisse"* likewise.
Deleting the pair pattern from the loop would have changed the verdict on **neither**.

So the pairing has to be looked for **positively** and allowed to cancel a hit:
`_names_english_beside(text, hit)`. Any of the two surviving patterns can now be cancelled
three ways — the posting names English beside the demand, it softens the demand inside the
phrase (`_LANGUAGE_IDEALLY`), or it calls the language a bonus in the clause after
(`_LANGUAGE_NICE_TO_HAVE`).

##### A gap that was there the whole time, closed for free

The pair pattern's conjunctions are `and & + / plus sowie und`. The Dutch **"en"** is not
among them, nor the French "et", nor the Italian "e" — so *"Nederlands en Engels"* and
*"Maîtrise du français et de l'anglais"* were never caught by the pattern that existed to
catch them. Nine of the sixteen walls in section `1.language` were the pairing, and two of
those nine only ever matched through the *levelled* pattern by accident.

`_names_english_beside` needs no conjunction list, so every language's "and" is covered.

##### The window is 160 characters each side, and it is wide on purpose

```
_ENGLISH_BESIDE_WINDOW = 160
```

Wide enough for the three shapes a real posting uses: the pair in one sentence, a level
sentence followed by an English one (*"Sehr gute Deutschkenntnisse. Englisch wird im Team
gesprochen."*), and a **bulleted language list**, where the two names sit in neighbouring
bullets and no single clause holds both:

```
• Nederlands: vloeiend
• Engels: goede beheersing
```

Deliberately *not* clause-scoped, which is the opposite of the decision made for
`_LANGUAGE_NICE_TO_HAVE` two paragraphs up — and the reason is the **direction of the error**.
A qualifier search that reaches too far invents a bonus the posting never offered and keeps a
listing wrongly. This search reaches too far and keeps a listing wrongly as well; reach too
*narrowly* and it deletes one the user asked to see. Only one of those costs him a job, so the
two windows are tuned in opposite directions. Both ends are pinned by assertions (40
characters away counts, 400 does not).

##### THE SECOND PLACE THE QUESTION IS ANSWERED, WHICH NEARLY SWALLOWED THE WHOLE CHANGE

`country_rules['other_language_required']` is a flat phrase list per country — `fluent
dutch`, `deutschkenntnisse`, `vloeiend nederlands`, `nederlands vereist` — read by
`_step_country_rules`, one step after the regex rule. **It had no idea English existed.**

So the regex rule stopped deleting the pairing and this list went straight on deleting it:
*"Fluent Dutch and English required"* contains `fluent dutch`, and nothing here looked at the
rest of the sentence. **Caught by measuring, not by reading** — the first real Filter run
after the change kept only **10** pairings of the 385 the regex rule had released, which is
far too few, and tracing one of them landed here.

`rules.country_language_rule_hit` is now that same list with the same cancel, through the
same `language.names_english_beside` and the same 160-character window: one question, one
answer, two callers (rule 5 of the nine). It walks **every** hit rather than the first,
because a posting can name two languages and pair English with only one of them. The entry
in `COUNTRY_RULE_SECTIONS` is a sentinel object, not a section name, like the `None` that
means `silent_about_english` beside it.

**The list stays**, and is not redundant with the regexes: it catches shapes that have no
level word for a regex to find — `german required`, `deutsch zwingend`, `nederlands vereist`,
`nederlandstalig`.

##### Where the 385 actually end up, which is worth knowing before being disappointed

```
385   the text pairs English with another language
-281  fail the Work Location rule -- Dutch office and hybrid jobs, correctly dropped
  -2  unpaid, or still an unpaired demand elsewhere in the text
=102  reach Claude
 -91  Claude drops or flags
= 11  in the final 166
```

**The Remote rule takes three quarters of them, and that is the right answer, not a leak.**
A Dutch employer who wants Dutch *and* English is usually an employer with an office in
Utrecht; the pairing was never the thing disqualifying them.

**Three of Claude's flags are rule 2, and they are correct**: *"Rule 2 — Dutch fluency
required without English pairing"*, *"English alone insufficient"*. Claude read the whole
posting and found the 160-character window had been generous — English appeared nearby but
not as an alternative to the Dutch. That is the window's documented failure direction working
as intended: it hands the listing to the careful reader instead of deleting it, and the
listing is **flagged, not removed**, so the user still sees it in the review dialog.

##### Rule 2 of the Claude prompt had to move with it, in twelve files

Keeping the listing at the keyword stage changes nothing if Claude deletes it one step later,
and rule 2 said exactly what the keyword rule used to. It is now:

> **It requires a language he does not speak INSTEAD of English** … A posting that wants
> English together with another language is a **KEEP** … Taking it here takes it away from him.

That paragraph is copied into **twelve** prompt documents — Junior Remote and Not Remote,
Entry/Mid/Senior ×2, and the four Internship and Thesis prompts, where it is numbered **5**
rather than 2 and says "a nice-to-have" rather than "nice-to-have". Changed by one script
that refused to write anything unless every file matched the expected count, per `O-5`/`O-17`
and rule 5 of the nine. **The first attempt matched 4 of the 12** — the profiles wrap the
line after *"or one"*, `claude_screen` wraps before it — and the guard is the only reason the
other eight were not silently left on the old rule. Then all eight `.md` mirrors regenerated
from `system_prompt_for`, never by hand (`M-1`).

**Every prompt edit invalidates the screening cache** (`_claude_screen_cache_key` hashes the
prompt text), so the next Filter re-asks Claude about every survivor and re-bills it. That is
the intended cost of changing a rule, not a bug to work around.

#### Four things that must not be undone

**`or` is not a conjunction here.** "C1+ in either English or Spanish", "professional working
proficiency in English or Russian", "if the documents are not in German or English" all mean
English alone is enough. Including `or` deleted three real listings. **This has bitten twice**:
the levelled pattern added later had to be told separately, and the test written the first
time is what caught it.

**A language must be NAMED.** The bare substrings `english and` / `and english` deleted 95 of
2,542 real listings, many nothing to do with language: "...and English benefits & perks",
"fluent English and strong communication skills", "German and English language **courses**" —
a free perk. Requiring a named language stopped 9 wrong deletions and caught 19 real demands
the substring had missed, among them "Fluency in German & English required" and "Deutsch C1,
Englisch mindestens B1-B2".

**`idealerweise` sits inside the phrase.** "Englisch und idealerweise Deutsch" is English
required, German *ideally*. `_LANGUAGE_NICE_TO_HAVE` reads the clause that *follows* a match
and cannot see it. `_LANGUAGE_IDEALLY` reads the matched span itself. Found by reading a
random thirty of the 2,934 listings this rule removes — **two of the thirty were wrong**, and
this was one.

**Italian is deliberately absent from the vocabulary.** The owner has only basic Italian and lives in Italy.
Adding it while extending the list for the other languages was a regression that would have
emptied Italy; a four-line probe caught it.

#### `I-3` · the role words were English only

The same mistake one step earlier, in the *search* rather than the filter. Measured against
Indeed for Germany, 200 internship results each:

| role words | results named in German |
|---|---|
| English only | 23 |
| plus the German ones | **47** |

Both runs hit the cap, so the real gap is wider. These appear only with the German terms:

```
Werkstudent Künstliche Intelligenz – KI im Arbeitsalltag (m/w/d)
Praktikum - Künstliche Intelligenz (KI) in der Technischen Entwicklung
```

A German employer writes *Künstliche Intelligenz*, a Finn writes *Tekoäly*, and neither says
"Artificial Intelligence" anywhere on the page. Since the query is the only thing that checks
a listing is about data at all, **a missing language is a whole country's postings never
seen.** The role group carries all twelve languages now.

#### `R-3` · DeepL has no API key — BY DESIGN

Worth remembering while reading German results: when translation still ran, their translations
came from Google Translate, the weaker of the two routes — measured at 12 of 122 listings
translated on one real run. Nothing is translated at all now; every rule reads the posting in
its own language, which is what replaced it.

---

### 4 · Claude

**Claude never deletes.** It flags with a reason, a review dialog asks for confirmation, and
any API error fails open. An early design had it silently remove what it flagged. This is
load-bearing; do not "simplify" it.

#### The answer format — and why the field order is the whole design

The answer is constrained by a JSON schema the API compiles into a grammar, so the decoder
cannot emit anything else. That removes a whole class of bug: there is no prose to run out of
room in, and no sentence for a regex to mistake for a verdict.

**`checked` comes first, and that ordering is not a detail.** JSON fields are generated in
schema order, so a verdict placed first would be named before the model has written anything.
Measured over 60 real listings from the population the app actually screens:

```
bare verdict/rule/reason/match schema   agreed 58 of 60, DROPPED 2 jobs the old answer keeps
`checked` first, holding the pass over the nine rules   60 of 60, nothing lost
```

The schema buys format safety without paying for it in recall — **but only in this order.**
The same logic governs `drop_evidence` and `location_basis`: both are asked for *before* the
verdict, so the words have to be found before a verdict can lean on them. And in
`worth.py`: reasoning, then the number, then the verdict, for exactly the same reason.

`minimum`/`maximum` are deliberately absent from the schema — the API rejects them on integer
fields — so `match` is clamped in code instead.

**The schema is hashed into the cache key alongside the prompt**, and that is not cosmetic:
the schema changes the *decisions*, not just their shape. A decision cached under one answer
format must not be reused under another.

#### `G-1` · the batch pass decided nothing at all

The group schema was missing `**_SCREEN_OUTPUT_SCHEMA['properties']`. So `properties` held
only `listing` while `required` named all eight real fields and `additionalProperties` was
False — the grammar permitted exactly one field, demanded eight, and emitted what it was
permitted:

```json
{"answers":[{"listing":1}]}
```

Thirteen output tokens, no verdict, no match. A missing verdict reads as "not a DROP", so
**every listing came back KEPT and unscored, and the batch pass — the one that runs on a real
search — decided nothing.** It looked like a working stage: no errors, an answer for every
listing, a plausible bill.

That is the shape of the worst bug in this project: *plausible output from a stage doing
nothing.* It is why `_read_structured_answer` now discards an answer whose listing number is
missing or out of range rather than applying it by position — **applying one listing's verdict
to another is the one failure here that would never show up in a log.**

#### `O-3` · dropping for what a posting does not say

> **Tried** · asking harder in the prompt not to drop on silence.
> **What happened** · 17 wrong drops in 111 became 11. Measured over 117 real DROPs, 11 could
> not point at anything: *"unpaid"* where pay is never mentioned, *"on-site"* where only a
> city is named, *"2+ years implied"*, *"no on-site requirement stated"*. Asking again did
> nothing.
> **Now** · `drop_evidence` is a required schema field, checked against the posting.
> `_evidence_is_real` compares letters and digits only, so punctuation and casing do not
> reject a genuine quote. A DROP that cannot show one becomes a KEEP — the safe direction.
> 17 → 2 of 94.

**The second guard is the subtle one.** Checking that the quoted words are in the posting
stops an *invented* sentence, not an *irrelevant* one: a DROP reading "Rule 3 — unpaid
volunteer position" on an internship that never mentions money passed by quoting some other
true sentence. `_EVIDENCE_MUST_CONTAIN` now requires a rule-3 quote to contain a word about
pay, a rule-2 quote a language, a rule-4 quote a number or a seniority word — in every
language the app reads. Only the three rules measured being stretched are listed; every other
rule passes on the quote being real, which is all `_evidence_is_real` can ask.

#### `T-9` · the guard was overturning correct removals, and it is a pair of regexes

**A quote failing either check is treated as no quote, and the DROP becomes a KEEP.** That is
the safe direction — one listing too many rather than one too few — but it makes the guard the
last thing standing between a correct removal and a listing in the user's results, and a pattern
can be blind to a *wording* without being blind to the *rule*.

It was. Counterfactual testing of the prompts found rule 4 not firing on

```
"at least eight years of experience, who has led a data science team of five or more"
```

**Claude answered DROP, rule 4, three times out of three. The guard overturned all three**: the
years were spelled out so there was no digit, `experience` is not `experienced`, and `led` is
not `lead`. The same sentence with `8` was dropped correctly, and that is what named the
cause. Every senior role whose advert spells its number out was reaching him as a junior
opening.

**Now** · rather than list the cardinals of eleven languages — where Norwegian *to* and Swedish
*sex* would match ordinary English words — **the span of time is matched**: `years`, `Jahre`,
`jaar`, `ans`, `anni`, `años`, `år`, `vuotta`. To say how much experience it wants, an advert
has to name a unit.

Trying the same technique offline then found two more in languages the app reads every day:
**Dutch `onbezoldigd` and Italian `non retribuito`** for rule 3, and German
**`Sprachkenntnisse`** for rule 2 — German never writes the bare noun *Sprache* in a job
advert. Dutch pluralises *taal* to *talen*, and a bare stem there would have swallowed
**`talent`**, a word in half the adverts on the board, so that one is spelled out.

> **Suite 9 exists for this and is offline on purpose.** The guard is a pure function of the
> quoted words, so every wording an advert might use can be tried for nothing, as many times
> as you like — the half of the prompt audit that can be run to exhaustion, and the half that
> runs on a machine with no API credit. The negative cases matter as much as the positive
> ones: widening a pattern to fix a blindness is exactly how one stops being a guard.

#### `S-1` · one listing per request. Never three.

Sharing a request is what makes this affordable at all — the prompt is identical for every
listing, so sent one at a time it is paid for 93 times over. But it is not free, and the price
is accuracy. Measured on the real 93-listing corpus, same prompt, all four sizes in one batch
so nothing else could differ:

```
group   kept   cost     agreement with one-at-a-time
    1      3   $0.169   (the reference)
    3      6   $0.113   96.7%
    5      5   $0.104   95.6%
   10      9   $0.093   93.4%
```

**Every one of the six disagreements at ten was a listing wrongly KEPT** — an Amsterdam role
whose only remote wording was a staff perk ("work from anywhere for one month a year"), and a
Dutch-language role in Bilthoven asking for two office days a week. Sent alone or in threes,
Claude drops both and says exactly why. Crowding the request does not make it reason worse
about the listing in front of it so much as **make it less willing to say no.**

#### Token budgets, retries, and why a truncated answer is worthless

The old prose answer was two short lines, so 100 tokens was right — measured over 240 real
listings, 239 finished using at most ~75.

**The 240th is why a second number exists.** Occasionally Claude obeyed "check all 9 rules as
a complete, sequential pipeline" literally, wrote the review out rule by rule, and ran out of
room before the verdict. Repeating that request unchanged is pointless — temperature is 0, so
the same request returns the same truncated answer — **which is exactly what the first version
of the retry did: three billed calls to fail three identical times.** The retry gives it
*room*, not another attempt.

Truncation has to invalidate the **whole** answer, not just an unparseable one. A half-written
review is prose about the rules, and prose contains sentences like "No DROP." and "RULE 2 —
REMOTE RULE"; one stray line beginning "DROP:" in the middle of that reasoning would be read
as the verdict and delete a job the user should have seen.

The budget is 500 now, not 100, because the schema-constrained answer carries its `checked`
pass: measured over 60 real listings it used 195 output tokens on average and 348 at worst.

**A complete answer that still says nothing is worth one more try too.** It used to be
accepted silently — the listing kept with no reason and no Match %, indistinguishable from a
real KEEP. Caught by the live suite failing once on "a MATCH percentage was parsed" and
passing on the next run.

#### Failing open, and what must never be cached

- **An errored screen is never cached.** A transient failure frozen in as "no decision" is
  worse than paying again. The cost of that correct choice is that an erroring listing keeps
  costing a call on every future run — a real live run showed one row of three failing
  reproducibly when screened as part of a burst — so a transient failure is retried *here*,
  before it becomes the caller's problem. Only transient ones: a bad key or a malformed
  request fails identically however many times it is sent.
- **Anything missing from a batch result is simply absent**, and the caller screens those
  listings one at a time. Nothing is silently marked KEEP.

#### `temperature` is a 400 on the current models

It was **removed from the API** on Sonnet 5, Opus 5 and the whole 4.6+ family. Sending it
fails every single call — found the hard way by a model comparison in which **60 of 60 Sonnet
requests failed** before the parameter was dropped. Haiku 4.5 still accepts it and determinism
is worth having on a classifier, so it is sent only where it is legal.

#### `O-15` · a removal left no trace on the listing

`drop_evidence` was validated and then thrown away — it appeared in **exactly one line of the
whole app**. Auditing the Germany run therefore needed a throwaway script, and two of
ninety-four drops could not be explained at all. `drop_note.py` writes it on the end of the
listing between `$$` markers. See [12 · Cost and caching](#12--cost-and-caching) for the three
faults that cost.

#### `D-1` · the cost estimate was wrong twice

And `worth.py` is why the second time: **part two costs money too.** Counted only in the
screening half, the Health Check reported a run at a fraction of its real cost — the first
measurement of a Berlin-sized filter showed $0.0183 for screening and *nothing at all* for the
résumé match, which had read eight more listings.

#### `R-5` · a vacancy with no title reaches Claude — BY DESIGN

Dropping it would be a guess about a posting whose text may be perfectly good.

#### `M-2` and the résumé

The second pass once judged every listing against a **stale, hard-coded paragraph** about the user
— "entry or junior level, in data, ML or AI" — written before the field became a title he
types, and never updated when it did. A Data Engineering search was still being judged against
data science. The résumé replaces it entirely, and its fingerprint is hashed into the cache key
so a verdict reached against one résumé is never reused for another.

**`L-8` · `worth.py` also lost a regex's word boundary silently** — `\b` in a non-raw string is
a backspace character. Every file was checked afterwards. Use raw strings.

**`M-4` · the résumé block brought cache marks into batched requests.** `cache_control` belongs
on the per-run system prompt, not inside a batch item.

**The résumé-match minimum is 35%, and the number has a history.** A cybersecurity delivery
architect passed every rule and scored 35 against a data-engineering profile, while every
genuine match in the same run scored 65 to 85. The user asked for everything under 35% to be cut,
so the line sits just above it. Below it a listing is *flagged*, not deleted — it still reaches
the review dialog and can be kept by hand.

---

### 5 · Prompts and Levels

**The prompt is the user's own text.** It replaced a shorter 5-rule paraphrase that Claude judged
inconsistently. This version gives Claude the same keyword dictionaries the app's own filters
use, plus four rules the keyword filters do not cover at all (fake job / paid training,
citizenship, domain fit, degree completion).

**The job prompt is now TWO documents, not eight.** It was one per Level per mode — Junior,
Entry, Mid and Senior, each Remote and Not Remote. It is now one Remote and one Not Remote,
byte-identical across all four Levels. The Internship and Thesis modules keep their own
numbering and wording, so the files on disk are still ten; what collapsed is the job pass.

Why it collapsed, and why that was almost free: this suite's own guard said *"the Levels
differ only in the level paragraph and rule 4"*. Those were the **only** two differences. When
rule 4 stopped filtering (`T-4` below) and the level paragraph was replaced with one that asks
for the level to be reported, the four texts became the same text.

**`T-5` · the cache key no longer changes with the Level, and that is correct.** The key is a
hash of the prompt text, and the prompt no longer mentions the Level — so a verdict reached at
Junior is the same verdict at Senior. The same listing used to be asked about **four times**,
once per Level; now once. The assertion that the key must *change* with the Level was inverted
to assert it must not, with the reasoning written beside it, so reintroducing per-Level wording
cannot pass quietly.

**`T-4` · rule 4 reports seniority instead of dropping for it.** The user's instruction, after
seeing what it cost: *owner's note: it must not filter but categorise: group by Seniority, then Type, and remove nothing*.

Measured on the real Netherlands run: **rule 4 fired on 19 of Claude's 90 flags** — nineteen
listings removed for their seniority, by a prompt, before he ever saw them.

Its four per-Level wordings (Entry dropped 2+ years, Junior 3+, Mid 6+ or under 2, Senior
anything under 5 or any lead title) are replaced by one shared text saying seniority is never
a reason to drop, pointing at a **new required `seniority` field** in the answer schema with
the same six words the Seniority column shows: `Intern · Junior · Mid · Senior · Lead ·
Unspecified`.

Three details that matter if this is ever touched again:

- **The numbering was not changed.** Rule 4 keeps its number even though it no longer drops,
  because the schema reports which rule fired **by number** and every recorded reason in the
  Bank points at the old numbering. Renumbering would quietly repoint all of them.
- **`seniority` is `required`**, so an answer cannot omit it, and it is asked **before** the
  verdict — the same ordering as `checked` and `location_basis`, for the same reason: the
  question has to be settled in words before a verdict is committed to.
- **It is written on the row even for a DROP.** A listing removed for being on-site is still a
  Senior listing, and the table shows the column for every row it has.

**Rung 1d now drops silence about the working arrangement.** Four passages moved together,
from one source string, in all four Remote prompts: the rung itself, the bullet calling an
absent statement a KEEP, the closing instruction that told it to answer KEEP on an absence,
and the blanket silence paragraph (narrowed to pay and experience). Each substitution had to
appear exactly once in each file or nothing was written. The Not Remote prompts are untouched.
See rule 4 of the nine for why this reversal is the user's and what it is NOT allowed to extend
to.

**This has caused the same fault twice.** `O-5`: a rule meant for every Level ("a minimum of
three years or fewer is his level") was put in the shared section, where it wrongly applied to
Entry — caught by reading the generated diff. `O-17`: rule 5 was widened in one file and the
Levels disagreed. Both times the same guard caught it:

```
FAIL  remote: the Levels differ only in the level paragraph and rule 4
FAIL  Job-Filter-Claude-Apify.md is the junior remote prompt, byte for byte
```

Those two guards still stand, in their post-`T-4` form: the first is now *"remote: every
Level gets byte-identical text"*, because the two passages it allowed to differ are gone.
The mirror assertion is unchanged and is the one that fires if a prompt is edited and the
`.md` beside it is not regenerated.

**Now** · change a shared rule from one source string, **by script**, in every file that
holds it — and make the script refuse to write unless each substitution matched **exactly
once** per file, which is what stops the O-5/O-17 class rather than care does. Then
regenerate the eight `Job-Filter-Claude-Apify*.md` mirrors **from the prompt itself**.

Since `T-4` the job pass is two documents rather than eight, so a shared rule now reaches
two constants instead of eight; the Internship and Thesis modules still have their own two
each, which is why the files on disk are still ten. They are
what the user reads to know what Claude is told, and a test compares them byte for byte. Never
edit a mirror by hand — `M-1` is exactly that drift having already happened once.

#### Three lines of the per-listing prompt that were measured and left alone

- **The `Field:` line carries the job title the user typed**, on its own line rather than written
  into the rules, so the rules stay the same text for every title — and because this block is
  what the cache key hashes, a verdict reached for one title can never be reused for another.
- **`Location:` stays `Location:`**, deliberately, while the Thesis and Internship modules
  relabel it. That relabel exists to stop Claude inventing a place for a posting that names
  none — a failure those modules really have, because their keyword stage lets silence through
  on purpose. This module's keyword stage drops silence first, so the failure cannot arise.
  And the relabel is not free: measured on 20 real survivors, twice, *"Data Scientist Space
  Jobs in Netherlands"* stopped being caught by rule 5 as a listings page. One correct drop
  lost, nothing gained.
- **The description is not "the only text that can support a DROP".** It said that for one
  measured round, and it cost a correct verdict: rule 5 caught that same Netherlands listing
  from the **title**, and telling Claude only the description counts made it a KEEP.

**The prompt version is a hash of the prompt's own text**, not a hand-maintained number, so any
future edit to a rule automatically invalidates every cached decision with no risk of the user
forgetting to bump a counter.

**The description cap is a guard, not an economy.** The longest description in the corpus is
9,802 characters and sending every listing whole costs about a cent more per run; the cap
exists only against a scraper returning a whole site in one field.

---

### 6 · The search (the money path)

This is where real credit is spent. Every number below was billed.

#### The user's rule outranks a measured gain

> **Tried** · asking each selected country's strongest city separately as well, because
> LinkedIn caps one query at **1,000 results** (its own documented ceiling, which the actor's
> `splitByLocation` field exists for). Measured for 24 cents: the same search restricted to
> Berlin returned 120 jobs, of which **48 were not in the 1,000** the country-wide run had
> produced. **40% new, from one city.**
> **What happened** · the answer: *owner's note: only the places that were chosen are wanted, and no other city may be added on the app's own judgement*, and
> *owner's note: if Berlin gives only 48 adverts, go with those 48; what use is a Milan advert?*
> **Now** · **a city the user did not choose is never added to the plan.** If he wants Berlin he
> picks Berlin, and Berlin is searched exactly once. The limit is a ceiling, not a target.
> **Guarded by** · `O-9`, and section 7 of the run_search suite

A real gain was given up here on purpose. That is the entry to re-read before "improving"
coverage.

#### `T-6` · what each actor actually honours — tested one parameter at a time

> **The `linkedin` rows below describe `curious_coder/linkedin-jobs-scraper`, which was
> REPLACED on 4 October 2026 — see `T-16`.** They are kept because they are why it was
> replaced: its remote filter, its experience filter and its sort were all dropped. The
> new actor's own measurements, made by the same method, are in `T-16`.

**Read this before adding anything to an actor's request.** A field existing in an actor's
published input schema says nothing about it being applied. Each row below was proved by
running the same query twice against the live actor with one parameter changed and comparing
the returned job ids: **an identical set means the parameter was dropped.**

| actor | parameter | verdict | evidence |
|---|---|---|---|
| linkedin | `f_WT=2` remote-only | **IGNORED** | same URL without it returned the identical 300 jobs, 100% overlap; the Work Location rule passed exactly 91 of 300 on both |
| linkedin | `f_E` experience level | **IGNORED** | adding it returned the same 300 jobs reordered |
| linkedin | `sortBy` | **IGNORED** | same |
| linkedin | `f_TPR` date window | honoured | 0 of 2,592 rows older than the window |
| linkedin | `autoConvertToAiSearch` | honoured | see below |
| glassdoor | `remoteWorkType` | **honoured** | without it 300 rows, 84% of titles in field; with it **15 rows, 100% in field** |
| glassdoor | `daysOld` | honoured | `daysOld=1` returned 17 rows, every one 0 days old |
| glassdoor | `minRating` | honoured | asking 4.0 took 300 rows to 222, and the 143 rated below 4 became **0** |
| glassdoor | `employerSizes` | honoured | asking 1–200 took 300 rows to 94 |
| glassdoor | `easyApply` | honoured | 300 → 224, **every one** Easy Apply (48 of 300 unfiltered) |
| glassdoor | `sortBy` | **IGNORED** | identical 300 jobs, same order |
| indeed | `datePosted` | honoured | 14 → 1 cut 300 rows to 32, all 32 a subset. **Its maximum is 14 days** |

**So nothing filters for remote work at LinkedIn's end, and that is the premise of the whole
search.** Every office job in the country is paid for and then removed by the Work Location
rule. `f_WT=2` is still in the URL because the URL is what the actor accepts and removing it
changes nothing, but no part of this app may claim it filters — two t7 assertions used to say
exactly that, passed, and were renamed.

**And the one real remote filter is on the cheap actor.** Measured per row from the billed
runs: **linkedin $0.002000, glassdoor $0.000270, indeed $0.000105.** LinkedIn is twenty times
Glassdoor and is the one whose remote filter does nothing.

**`autoConvertToAiSearch=False` is sent as a constant, not offered as a choice.** The actor
rewrites a boolean query into a semantic one unless told not to, and its own default is to do
it. Measured on one query, 300 rows, everything else held still: with the rewrite on, 17% of
titles contained a phrase the query asked for; off, **25%**. The two result sets shared only
59% of their jobs, so this is a different search rather than a reordering. The user's instruction
when the measurement came in: *owner's note: if it really works, enable it, and keep it out of the Search field*.

**The precise (level-prefixed) query earns its keep poorly.** Measured on the real Mid run:
the 40-phrase precise query returned 880 rows for $1.76, of which **784 were already in the
broad set and only 96 were new — and only 13 of those 96 carried a Level word at all.** The
broad query carries no Level words and is byte-identical for all four Levels, so one broad
search already covers every seniority; the filter's match is word by word, so "Data Engineer"
keeps "Junior Data Engineer" without being asked. Set against the campaign note that the
precise query once added 245 listings on an Austrian DevOps run — it is not worthless, it is
title- and country-dependent, and it should be measured again before being relied on.

#### `T-18` · the actor panel is a list of dropdowns, with no prose

> *owner's note: no explanations for the actors' parameters: list every parameter an actor accepts, each with a dropdown in front*

Each platform's box in the Search window is now one row per parameter: **the parameter's own name
on the left, a dropdown on the right, nothing else.** The intro paragraph, the per-field hint
lines and the per-actor footer note are gone from the window. They still exist as data
(`Field.hint`, `NOTES`) because they hold what was measured — that is what `T-6` and `T-16` are
for — and a test asserts none of it reaches the panel.

- **Every control is a `QComboBox`.** A tick was a checkbox and a number was a spin box. A tick is
  now **No / Yes**; a number is a list of limits (`Field.presets`, always starting with 0 for *No
  limit*, and never above what the actor accepts — Glassdoor and Indeed stop at 1,000).
  `Field.dropdown_options(current)` decides what to offer, so the window no longer chooses a
  widget per kind. The value **stored** is the one the actor is given, never the label.
- **A value saved under the old spin box is kept, not replaced.** A 400 that is not on the list is
  appended to it and shown selected: opening the window and saving must never quietly change what
  he had picked. A number reads back as an `int` and a tick as a real `bool`, both asserted.
- **Labels are the actors' own words**, read from their input schemas: LinkedIn *Sort Order*,
  *Easy Apply Only*, *Under 10 Applicants*, *Workplace Type*, *Results limit*; Glassdoor *Results
  limit*, *Remote only*, *Minimum rating*, *Company sizes*, *Easy Apply*; Indeed *Results limit*.
  LinkedIn's *Workplace Type* is the actor's own `remote` and *Results limit* its own `limit`,
  each sent as chosen — **this paragraph used to say the opposite** (an internal `allWorkplaces`
  switch, shown as "Follows the Work setting / Any"). That was changed by `T-21`.

**What is *not* in the panel, and why.** "Every parameter we can give" was read as *every one
measured to work* — which is the rule this table has always had (`T-6`). The posted-time window is
**not** repeated per actor (LinkedIn `date_posted`, Glassdoor `daysOld`, Indeed `datePosted`)
because the wizard's own "Posted within" control already sets all three, and two controls for one
value is how they disagree. `experienceLevel` is absent because it was measured dead (`T-16`).
If the user wants the dead and unmeasured parameters shown anyway, that is a one-line change per field
and a decision about whether the window may offer controls that do nothing.

**Level and Work, checked at the same time because he asked whether they still work.** Both do:

| control | what it still changes |
|---|---|
| **Work** — Remote / Not Remote | LinkedIn's `remote` field (sent only for Remote; no place is exempt since `T-23`), Glassdoor's `remoteWorkType`, the Work Location rule, and which way LinkedIn's tag is read (`T-16`) |
| **Type** — Thesis / Internship | which *search* runs: each is its own pass with its own words, and (since `T-19`) **no remote-only filter at the actor** |
| ~~**Level** — Entry / Junior / Mid / Senior~~ | **removed from Search by `T-19`.** It only ever changed a second, precise query: 1–3 rows per platform and none for Mid |

Verified by running `keywords_for` for each — the broad query is the same for all four job levels
and the precise one differs. Neither control was removed.

#### `T-19` · Search offers Type — Any / Thesis / Internship — and no seniority

> *owner's note: remove Seniority from Search; keep Type with Any, Thesis and Internship, each searching for its own kind and Any for everything*

**Why Seniority came out of Search — measured first.** The user asked how the Level field really works
and whether it does at all. Same 20-row test on Indeed, Glassdoor and LinkedIn with the app's own
queries (`keywords_for` → `_actor_request`), Netherlands, a month, Not Remote so that no remote
filter confounds it:

| | Indeed | Glassdoor | LinkedIn |
|---|---|---|---|
| **broad** query, Junior / Mid / Senior | the **same 20 rows** for all three | same | same |
| precise **Junior** | 1 row | 1 | 2 |
| precise **Mid** | **0** | **0** | — |
| precise **Senior** | 3 | 1 | 20 |

An actor is never given a seniority *parameter* — none has one, and LinkedIn's `experienceLevel`
was measured dead (`T-16`). Level only ever entered the **text of a second, precise query**
(`"Junior Data Scientist" OR "Entry Level …"`), which added one to three rows and none for Mid,
while the broad query — identical for every level — brought **15 to 40 percent senior titles
whatever was chosen**. Whether the precise query's few rows are also in a deep broad run was *not*
measured and is open (about $1.50 on LinkedIn, almost nothing on the other two).

**What Type does.** One control, stored under the old `search_level` key so every reader of it
keeps working: **`any`**, **`thesis`**, **`internship`**.

| Type | what runs |
|---|---|
| **Thesis** | only the thesis pass — its words, in English then in the country's own language |
| **Internship** | only the internship pass, the same way |
| **Any** | the job, internship and thesis passes, in that order; **no seniority word anywhere** |

- **Any is the other three, run in turn** — not a fourth kind of query. `_resolve_passes('any')`
  returns `job, internship, thesis` with a job level of the *word* `'any'`, and `_process_plan_item`
  skips the job pass's precise shape for it. That skip is not optional: `keywords_for` falls back to
  **Junior** when its level is `None`, so merely deleting the level would have left
  `"Junior Data Scientist"` in a search that was supposed to contain no seniority at all.
- **Old values open as Any.** `clean_search_type` maps `junior`, `mid`, `senior`, `entry`, `nothing`
  and anything unknown to `any`, so an old `settings.json` shows a real choice. They are **not**
  rewritten on read: `MainWindow` hands the raw value down and the suites check it does, so an
  un-saved old `junior` still behaves as it used to until the Search window is next accepted.
- `LEVELS` gained `'any'`; `JOB_LEVELS` did not. The four job levels stay valid values — the Filter's
  profiles are keyed by them — Search just no longer offers them.
- **The Filter window offers the same three** (it writes the same key and had its own Level radio
  list), with its explanatory note removed.
- **Claude's résumé-match is told `Level: Any`**, not `Junior`. The Filter stamps the row with what
  was *asked* (`'any'`), not the profile that judged it (every profile decides the same since `T-5`),
  and part two's prompt says *a Level of Any means he did not choose one*. Left as it was, Claude
  would have been told every Any posting was a Junior one. That edit changes
  `_APPLY_PROMPT_VERSION`, so the next Filter re-asks part two and re-bills it.

**The order is English first, then the country's own language** — `ALL_SEARCH_LANGUAGES = ('en',
'local')`, each with a broad and a precise query — for Thesis and Internship alike. Verified, and
asserted (`7.type`), not assumed.

##### The live check: does each Type really return anything?

A real `run_search` per Type, Netherlands, **Remote** (his own configuration), a month, 20 rows per
query, LinkedIn + Indeed + Glassdoor (no Google), cost guard first:

```
                    before the fix below        after
THESIS               40 rows  (Indeed only)     86 rows   Glassdoor 41 · Indeed 40 · LinkedIn  5
INTERNSHIP           46 rows  (Indeed only)    114 rows   Glassdoor 47 · Indeed 47 · LinkedIn 21
ANY                 163 rows                   279 rows   job 79 · internship 115 · thesis 86
Type column on Any  Thesis 15, Internship 15   Thesis 47, Internship 34, PhD 10, Full-Time 169, ...
Apify cost          $0.21                      $0.47
```

**"Thesis searches only for thesis" is true of what is *sent*, not of what comes back.** The first
run's 40 Thesis rows held about six real theses (`Master Thesis Internship`, `Afstudeerder`,
`Afstudeerstage`); the rest were `Senior River Systems Engineer`, `Staff Security Engineer`,
`Manager, Growth Lifecycle`. Indeed, when its exact matches run out, **widens the query and returns
whatever it has** — `queries.py` documents the same thing for 1,000-row runs. The Thesis and
Internship modules in the Filter are what narrow it, which is what they are for. Duplicates
(the same row from several queries) are also removed later, not here.

##### A real fault found by that check: Remote-only was asked of Thesis and Internship

With Remote selected, `_linkedin_request` sent `remote` and `_glassdoor_request` sent
`remoteWorkType` for **every** pass. A thesis or an internship is almost never remote, so the
**second and third platforms returned nothing**: asked directly, LinkedIn's English internship query
gave **0 rows three times in a row** with the filter on, and **9 rows, all internships**, with it
off. Only Indeed — the one platform with no remote filter — produced output.

The two kinds also **have their own modules with their own Remote rule, which lets silence through
on purpose.** A filter applied at the actor removes, before the module ever sees them, exactly what
the module would have kept. So `_KINDS_WITH_THEIR_OWN_REMOTE_RULE = ('thesis', 'internship')` and
`_process_plan_item` passes `not_remote or kind in …` to the request builders — the existing way of
saying "send no remote filter" — so **only the Job pass is asked for remote-only at the actor.**
That is the user's own rule applied to a case it had not reached: *the actor brings what he is looking
for and his own Filter decides.*

**Glassdoor had the same bug from the other side, and it was bigger.** `_glassdoor_request` leaves
`remoteWorkType` out for a Not Remote search, but the Search window's *Remote only* field — default
**Yes** — and `apply_to_request` (which adds a key whenever a field is on) **put it straight back.**
So with the window's settings passed, which the app always does, **a Not Remote search asked
Glassdoor for remote work only: the exact opposite of what was chosen, and silent** (the `O-12`
fault again, on a different actor). It also meant *No* in the window did nothing in a Remote search,
because a tick can only add a key — the "untick does nothing" problem listed as *not done* under
`T-16`, now closed. `_actor_request` removes it when the effective search is not remote-only **or**
the window says No; a request built with no settings keeps what the builder always sent.

##### The vocabularies — four lists, and the search had been sending words nothing recognised

> *owner's note: the dictionaries must use every equivalent word for Internship in each chosen country, and the same for Thesis*

There are **four** places that decide what an internship or a thesis *is*, and they had drifted —
rule 5 of the nine, a rule in several places is several rules:

| where | decides |
|---|---|
| `search/queries.py` `_LANGUAGE_INTERNSHIP_WORDS` / `_LANGUAGE_THESIS_WORDS`, and the two English groups | what the **search sends** |
| `thesis/words.py`, `internship/words.py` — each module keeps its own (the three modules share nothing, by design) | what the **Filter module keeps** |
| `rules.py` `_INTERNSHIP_TITLE`, `_THESIS_TITLE` | the **Type column** |
| `country_rules.py` sections `internship`, `thesis` | the Job module's vocabulary; **nothing reads these two sections for the Type or the modules** |

Run every word the search sends through the module that is supposed to keep it, per country, and
**5 were not recognised** — fetched, paid for, and thrown away. The sharpest: the Spanish
**`Trabajo Fin de Máster`** — the official name, with the accent — was unknown to the thesis module
although `trabajo fin de master` was known; and the Norwegian **`Praktikplass`** was sent by the
search and unknown to the internship module. After the work: **0 of 156.** Search words went from 46
to 86 (Internship) and from about 40 to 70 (Thesis).

- **Added, insert-only.** `extend_vocab` found each language's list and inserted just the missing
  words above its closing bracket — **49 lines added, 0 deleted**, existing comments untouched (an
  earlier version rewrote the list and would have destroyed the comments that record why words are
  there). Idempotent: a second run changes nothing.
- **Left out on purpose**, because the module patterns are prefix-only (`\b` before, nothing after):
  `beca` (matches *because*), `lia` (*liability*), a bare `placement` (*Job Placement Specialist*),
  and every **Bachelor** word — the Thesis module is Master-level and drops them. Asserted as *not*
  recognised.
- **`Examensjobb` moved** from the Swedish *internship* list to *thesis*, where it belongs.
- **Invariant `7.vocab`**: every word the search sends, for every country that speaks the language,
  is recognised by its module. A word added to one list and not the other now fails a test.

##### Not changed, and measured so the next decision is informed

**The Type column and Dutch `Stage …` — recorded here as a decision, then made: see `T-20`.**

**An Any search is judged by the Job Filter, not by the Thesis and Internship modules.** Type no
longer deletes, so a thesis or an internship from an Any search comes through as an ordinary row
with its Type badge. The modules' extra rules (university enrolment, thesis agreements, their own
prompts) apply when `Thesis` or `Internship` is chosen explicitly. That follows *classify, don't
delete*; it is also a real difference, stated here so it is not discovered later.

#### `T-20` · the Type column reads the local-language internship and thesis words

> *owner's note: yes, fix it* — the answer to `T-19`'s open item.

**The fault.** 33 of the 4,325 Bank rows, and 62 of the 279 an Any search returned, were Dutch
`Stage Data & AI`, `wo stage Data Science & Machine Learning`, `hbo/ad-stage E-learning` — filed
`Full-Time` (or `Temporary`) while the Internship module, reading the same title, called them
internships. The Type column's patterns (`rules._INTERNSHIP_TITLE`, `_THESIS_TITLE`) are
English-first and **deliberately narrow**, and a bare `stage` is why: in English it is a stage
(`Late Stage`, `Stage Manager`), in Dutch, French and Italian it is an internship. The column's own
history records three drafts thrown away for labelling thousands of real rows wrongly, so this was
**measured on the Bank and on the live results, and every row it would change was read, before a
line was written.**

**What changed.** `category_from_words` still tries every existing rule first. Only when none
fired does `_gated_kind_from_title` read the **title** with the words the *search sends* for the
languages of the listing's **country** — so "what was searched for" and "what the column calls it"
are one list (`search/queries.py`) instead of two, and a word added there now types the column
without a second edit. Four properties keep it from being the fourth draft that gets thrown away:

| property | why |
|---|---|
| **it speaks last** | only when no existing rule fired, so every row already typed is untouched — the change is strictly additive |
| **title only, whole words only** | `Stagecoördinator` is a coordinator, not an internship. The prototype was a whole-word match from the start; a prefix match would have filed it as one |
| **the languages of the *country*, not the detected language** | a United States or United Kingdom row loads English alone, so `Stage Manager` there is untouched. The detected language is deliberately **not** used: a Dutch advert with an English description detects as English and would have lost its Dutch words |
| **eleven words are deliberately not used** | `_TYPE_WORDS_NOT_USED`, each with its reason beside it |

**The eleven, because two of them would have been serious:**

- **`apprentissage`** — French for *learning*. `Ingénieur Apprentissage Automatique` is a Machine
  Learning Engineer, and for a Data Scientist search in France this would have filed the core of the
  results as internships. Its stem `apprenti` goes with it.
- **`trainee`**, `traineeship`, `traineeprogram`, `traineeohjelma` — a paid graduate programme, not
  an internship. The existing rule already keeps `traineeship`, and `Trainee BI Consultant` stays
  `Full-Time`.
- `mémoire` alone (it is also *memory*; `Mémoire de Master` and `Mémoire de Fin d'Études` are used),
  `apprendista` and `apprendistato` (apprenticeship contracts), and `alternance` / `alternant`
  (work-study contracts, left out **until read on real French rows** — none has been read yet).

**Measured, all of it:** the Bank — 16 rows change (15 `Full-Time` and one `Temporary`, every one a
Dutch `Stage …`), none wrongly. Live results — 62 / 21 / 40 rows across the three Type searches,
the same shape. `Stagecoördinator` and `Management Traineeship` did not move.

**Two things it does NOT do, and one cost it carries:**

- `Afstudeerstage` stays a **Thesis**, and `Tirocinio di Tesi` stays an **Internship**. Both are
  typed the other way round from what one might guess, by rules **older than this one**
  (`afstudeer\w*` and `tirocinio`), and a test names them so changing either is a decision.
- It does **not** use `country_rules['internship' / 'thesis']`. Those sections hold
  `neolaureato`, `jeune diplôme`, `recién titulado`, `nyuddannet`, `oppisopimus` and `elev` — new
  graduates and apprentices, not internships — and using them would have filed every graduate role
  as one. They are read by nothing for the Type or for the two modules.
- **Canada loads French, so a bare `Stage` there is read as an internship** — a Canadian `Stage Lead
  Machine Learning` would be mislabelled. That is the price of the rule being by country, it is
  asserted so changing it is deliberate, and it is the reason the guard exists rather than a hope
  it never comes up.

**The live check afterwards** (Any, Netherlands, ≤20 rows per query, no Google, Remote and Not Remote,
191 distinct listings): the Type column left **0** titles that name a thesis or an internship under
another label (Internship in an Any search went 34 → 96). Seven rows are labelled Thesis or
Internship with no such word in the title, and **all seven come from rules older than this one**:
LinkedIn's own `employmentType` (`Data Scientist (Europe, Asia)`), `werkstudent`, and `traineeship`
(`Management Traineeship Business & Tech` was an Internship before and still is — a paid graduate
programme, and a candidate for the next decision, not this one). The same run confirmed the Remote
flag per kind (`T-19`) and the Glassdoor fix: Glassdoor's Job pass returned **2 rows** in a Remote
search and **40** in Not Remote — which is what a Not Remote search was being denied before.

**Links, 11 of 20 — and why that is not 11 good and 9 dead.** LinkedIn 5 of 5 opened and matched.
Glassdoor 0 of 5: its pages refuse the fetcher, so they could **not be verified**, which is not the
same as being broken. Four Indeed results opened but their `<title>` does not carry the job title
(employer career sites built in JavaScript, e.g. Workday), which is the matcher being strict.
The earlier LinkedIn-only run opened 167 of 167.

Guarded by section `1.gated`: **31 titles in 12 countries** that must now be typed correctly, **13
that must stay `Full-Time`** (each a real near-miss), the rule speaking last (a Part-Time Stage is
still Part-Time, a PhD still a PhD), `is_category_uncertain` agreeing, and a sweep that **every word
the search sends that may name a Type, does.**

#### `T-21` · Remote / Not Remote under Type, locked for Thesis and Internship — and every dropdown is the actor's own parameter

> **Amended (T-21b) — Remote / Any in Search AND in Filter.** The row is exactly two options,
> **Remote** and **Any**; "Not Remote" is gone from both windows. Each choice fills the actor's own
> remote term: **LinkedIn** `remote` = `remote` / Any; **Glassdoor** `remoteWorkType` = Yes / No;
> **Indeed** `location` = `"remote"` / Any (the actor documents `location` as "City, state, zip
> code, or remote"; measured 10 rows each: Germany 10 of 10 Home Office/Remote, US 10 of 10 Remote,
> Netherlands 0 — Indeed.nl lists almost none, an honest empty answer). Any sends nothing remote, so
> the actors bring Remote and everything else. **The Italy exception was removed by `T-23`.** Thesis and Internship grey out Remote and choose Any. Saved as `search_workplace`
> (Search) and `search_work_mode` (= `remote` / `any`, also what the Filter radios save); settings
> saved earlier with `not_remote` open as Any.
>
> **Any is a real third Filter mode** (`search_title.is_any_workplace`): the Work Location keyword
> rule, and the thesis / internship location rules, keep every listing; Claude gets a prompt whose
> rule 1 ("The role is remote") and "what he is looking for" paragraph are replaced by "where the
> work is done is never a reason to drop" — and for Internship the working-student rule, which was
> rule 1a again. Those prompts are **derived** from the six Not Remote prompts by
> `pipeline/prompt_any.py` (refuses if a passage is not found exactly once) rather than typed as six
> more copies; every other rule is byte-identical, with its own cache version. Everything below that
> says "Not Remote" in the Search or Filter window describes the state before this amendment;
> `not_remote` remains an internal mode for old saved settings.

> *owner's note: add a Remote / Not Remote row under Type; when Thesis or Internship is chosen, Remote becomes unclickable*
>
> *owner's note: every choice made there goes directly into that actor's own parameter*

**The row.** Under **Type** the Search window has a row called **Remote / Not Remote** (it was
labelled *Work*). Choosing **Thesis** or **Internship** makes the **Remote** entry unclickable —
greyed, with a tooltip — and moves the choice to **Not Remote**. Going back to **Any** gives Remote
back and puts back whatever was chosen before. The Filter window's own Remote radio does the same.
Theses and internships are almost never remote, and measured, a remote-only request returned nothing
for either on two of three platforms (`T-19`); locking it is the same finding applied at the source.

**Every dropdown is the actor's own parameter, and its value goes into the request as chosen.** Two
of the dropdowns were not actor parameters at all, and the app also derived a remote filter behind
the window's back from the work mode. All three were indirections, and all three are gone:

| was | is |
|---|---|
| LinkedIn *Workplace Type* = `allWorkplaces`, an internal switch ("Follows the Work setting / Any") | the actor's own **`remote`**, with its real values: **Any · Remote · On-site · Hybrid** — sent exactly as chosen |
| LinkedIn *Results limit* = `maxResults`, which the actor has never heard of, plus a total cap in our pager | the actor's own **`limit`** (Max · 10 · 20 · 50 · 100). Under 100 it is **one call** — a page shorter than the page size is the last page, so the walk stops by itself. *Max* sends the actor's 100 and walks the pages |
| `_actor_request` threw the window's value away and rebuilt `remote` / `remoteWorkType` from the work mode | with the window's settings in hand the builder's derived value is **discarded** and the dropdown's value goes in through `apply_to_request` |

**The Remote / Not Remote choice SETS two dropdowns, and the panel shows what will be sent.**
Remote → LinkedIn `remote` = Remote and Glassdoor *Remote only* = Yes; Not Remote → Any and No.
Choosing Thesis or Internship does the same, because it locks Not Remote. He can change either
dropdown afterwards and that is sent as chosen — a Not Remote search with LinkedIn left on *Hybrid*
sends `hybrid`. Three rules keep that honest rather than surprising:

- **A value he saved himself is left alone on opening.** Only a dropdown that was never saved is
  derived from the mode, so opening the window on a saved Not Remote does not show a *Remote*
  dropdown that nothing ever set; a saved *Hybrid / No* opens as *Hybrid / No*.
- **Changing the mode overwrites those two dropdowns.** That is deliberate — the mode is the larger
  statement — and it means a manual *Hybrid* does not survive switching to Not Remote and back.
- **The mode stays saved as Not Remote after a Thesis or Internship.** The Remote you had before is
  restored while the window is open, not across sessions: a Thesis run saves `not_remote`, and the
  next Any search opens on Not Remote until you click Remote. The alternative — saving one value and
  deriving another at the point of use — is exactly the indirection this entry removes.

**Checked on the real actor, 20 rows each ($0.30):** `remote=hybrid` → **20 of 20 tagged Hybrid**;
`remote=remote` → **20 of 20 Remote**; `limit=20` → **exactly 20 rows in one call**. And one result to
keep honest: `remote=onsite` is accepted and sent as chosen, but LinkedIn applies it only about
**70% purely** — 14 On-site, 5 Hybrid, 1 Remote in the sample. Remote and Hybrid are exact; On-site
is a filter that leaks, so a row's own tag is still what to trust, and that is what the Work Location
rule reads.

**One exception remains (the Italy one that stood here was removed by `T-23`).**
`_actor_request` removes the workplace parameter for the **thesis and internship passes of an Any search** (`skip_remote`),
which would otherwise be remote-filtered and return nothing. In an Any search with *Remote* chosen the
job pass sends `remote=remote` and the other two do not, so that one dropdown is not sent verbatim to
every call it nominally covers. It is the one place "directly" is not literally true, and it is there
because the alternative is the 0-row result `T-19` measured.

#### `T-26` · Thesis and Internship know the other names for the job; the first name and the Persian quotations are gone

> [owner's note: add the equivalents to Thesis and Internship too]

- **Equivalents.** `title_equivalents` (asked of Claude once per title, cached on disk) used to widen only the
  Job module. Its list now reaches Thesis and Internship in two places. **The field rule:** `find()` takes
  `other_names` (handed in by `FilterWorker`, so the modules still ask nobody and share nothing), stamps them on
  every row as `_title_also`, and each module's own `field_words.py` matches the typed title *or any* of them,
  each with its twin form — "Tirocinio TESI Artificial Intelligence" is no longer off-field for "Data Science".
  **The search queries:** the broad query's title group and the exact "kind word + title" phrases carry every
  other name too (`_role_forms`), the typed title first; with equivalents the phrase list is capped at 40 so a
  query is never silently truncated. With no key or no answer the list is empty and nothing changes.
  What it does not do: it does not fix the AND of thesis words and title that returns almost nothing for a
  narrow title (`T-25`) — more alternatives inside the title group help, searching the thesis words alone
  would help more, and that remains the owner's decision.
- **Scrub.** The first name is written "the user" throughout (code, prompts, docs); the owner's Persian
  instructions are rewritten as short English `owner's note:` lines. Only the GitHub user name in URLs and in the
  license notice keeps the name, and the public README keeps one Persian sentence stating its purpose.

#### `T-24` · Going public: the name, the license, the cleaned repository, and a step-by-step guide

> *owner's note: the aim is a public release that everyone can use* · *owner's note: downloading and using is fine; changing and selling is not*

- **Name:** JobDesk became Job Finder and then **RoleHound** (window title, brand label, `RoleHound_Export.xlsx`,
  `RoleHound.spec`, `RoleHound.exe`, the Taskbar id). **The per-user data folder stays
  `%APPDATA%\JobDesk` on purpose** — renaming it would orphan every saved setting, the Bank and the résumé.
  Why RoleHound: "Job-Finder" alone was shared by 100+ GitHub repositories, while "RoleHound"
  had none (checked 5 October 2026 — GitHub only, not Google or any domain).
- **This file** was `README.md`; it is now `Document.md`. The new `README.md` is the short public page
  (purpose, what it uses, what to prepare, a step-by-step guide, the Google speed note).
- **License:** PolyForm Strict 1.0.0 (`LICENSE`) — use for yourself, no changes, no redistribution, no
  commercial use. Source-available, not Open Source. GitHub's Terms still let anyone fork a public repository;
  the license says they may not, it does not stop them.
- **Two repositories.** `RoleHound` (public) holds one clean commit made with a GitHub noreply address.
  `RoleHound-history` (private) keeps the full 72-commit history, which carries two personal e-mail
  addresses and an old personal profile in `archive/` (residence, nationality, university, language levels).
  Removing a file from the latest commit does not remove it from history, so the public repository was
  started afresh. The working folder is wired to `RoleHound-history`; a change reaches the public one only by
  being copied across clean.
- **What the review found and removed:** no API key, token or password was ever committed (all 72 commits
  scanned); the `archive/` folder (34 files) and personal sentences in comments and docs were removed. Still
  there, knowingly: the first name "The user" in prompts and comments, the GitHub user name, and quotations of
  the owner's Persian instructions.
- **Step-by-step guide:** in `README.md`. One correction it made: an earlier draft of the README said to upload
  the résumé in the Search window; it is uploaded in the **Filter** window (**Choose résumé…**), and the
  Anthropic key is optional — without it only the keyword rules run.

#### `T-25` · Open finding: a Thesis search for "Data Science" returns almost nothing

> *owner's note: a Thesis search returned Internship and Full-Time results, and very few of them*

Measured on 5 October 2026 with capped live runs (Italy, Past 2 weeks). The real search returned 4 rows, none
a thesis: the query asks for a thesis word **and** the title ("Data Science" / "Data Scientist"), the actors
read it as one text query, and almost no Italian thesis advert has both. The 31-term English `OR` list returned
0 rows on all three actors. A bare "Tesi" returned 113 rows, 36 of them theses (LinkedIn 13 of 13, Glassdoor 8
of 20, Indeed 1 of 20) — and the Thesis Filter then removed all 36 because their titles never name "Data
Science" (e.g. "Tirocinio TESI Artificial Intelligence_Bologna" is removed too: the field rule has no
synonyms). **Not changed.** Two decisions are the owner's: search the thesis words alone and let the Filter
judge the field, and widen the field rule with equivalents (AI, Machine Learning, Statistics).

#### `T-23` · Remote means Remote — no Milan, Turin or Italy exception

> *owner's note: Remote means Remote even in Turin or Milan; to see everything, search Any*

The home-city exception is gone, everywhere it lived. Remote is judged as Remote in Turin and Milan
like in any city; the way to see on-site work there is to search **Any**.

- **Keyword rules:** `mentions_milan_or_turin` and `MILAN_TURIN_NAMES` are deleted; the Work Location
  rule, and the Thesis and Internship location rules, no longer keep a listing for naming either city.
- **Request builders:** LinkedIn and Glassdoor send their remote filter in Italy as anywhere, Indeed
  sends `location=remote`; `_actor_request` keeps one exception only, the thesis / internship passes
  (`T-19`).
- **Claude (all six Remote prompts + the eight mirrors, regenerated):** the sentence "a role in that
  city … also works, on-site or not", rule 1's wording "other than the city he lives in" (now "present
  somewhere — the role is not remote"), the "Anything in the city he lives in … is a KEEP regardless of
  rule 1" line, the internship working-student exception, and the `in or near the city he lives in`
  answer in `location_basis` are removed. The region paragraph of rule 1b ("Europe contains where he
  lives") stays: it is about whether a remote role admits him, not about on-site work.
- **Tests:** the assertions that Milan/Turin/Italy stay exempt now assert the opposite (t1, t4, t7,
  t10). **What this costs:** a Remote search no longer shows an on-site Milan advert, and a Remote
  prompt's cached verdicts are re-asked once (new prompt version). Still Italy-specific, unrelated to
  this rule: the "Italy first" sort order in the table.

#### `T-22` · The column filters crashed the program, and now leave a crash log

> *owner's note: the program crashes and closes when the Excel-style table filter is used*

Windows logged two `Qt6Widgets.dll` access violations (same offset, `0xc0000005`) in one morning, both
while a column filter was used just after a Filter run. **Cause, found by reading and not reproduced
headless:** every tick fired `changed`, the Jobs page re-offered the same values, and `offer()` tore
down and rebuilt the whole panel — destroying the very checkbox whose click was being handled, with
the menu open and the mouse over it. **Fix** (`column_filter.py`): a tick, *Show all* and *Select none*
now update the open panel in place; `offer()` rebuilds only when the values really changed, never
while the menu is open (it waits for `aboutToHide`), and old widgets are `deleteLater`'d rather than
destroyed on the spot. **Honest limit:** the crash could not be provoked offscreen before or after, so
the fix rests on the analysis plus tests that the panel object stays the same. To be sure next time,
`main.py` now enables `faulthandler` and writes `%APPDATA%\JobDesk\crash.log`; if it happens again that
file names the line.

#### `T-7` · the five switches, and why there are five rather than nineteen

`app/pipeline/sources_enabled.py`. The four Apify platforms keep their drag-to-reorder
checklist (`actor_order`); everything else a search asks is **one** box, "The direct APIs".

This arrived by being narrowed twice, and the narrowing is the useful part. It began as a box
per stage and per source — nineteen. Then: switches for the actor-backed sources only. Then
The user's final shape: *owner's note: only for the Google, Indeed, Glassdoor and LinkedIn APIs*.

- **Deep Crawl got no switch of its own.** `run_google = 'google' in actor_order` gates the
  whole phase — the Google query, known and startup sites, Deep Crawl and URL-pattern
  discovery are all inside that one `if` — so unticking Google already stops it. A second
  control would have been two switches for one decision.
- **The per-source gates stay in `direct_api.py`.** `is_enabled()` answers True for any key
  the table does not carry, so they cost nothing now and exposing one later is a single line.

**`app/pipeline/actor_filters.py` is the same pattern for the filters**: one table, read both
by the Search window that draws the controls and by the request builders that send them. A
field cannot appear in the window without being sent, or be sent without appearing. Only the
`T-6` rows marked *honoured* are in it; `experienceLevel` and both `sortBy`s of the old
actors are absent because they were measured and ignored, and `distance`, `geoId`, `radius`
and `company_id` are absent because **they were never measured**. Untested is not the same as
broken, and neither belongs in a window.

Every entry in it is **the actor's own parameter**, and its value is sent as chosen (`T-21`). There
used to be two that were instructions to the app wearing an actor's name — LinkedIn's `maxResults`
and `allWorkplaces` — and that was the very thing this table was written to prevent: a control that
does something other than what it says. The pair that used to be the trap before them —
`limitPerSource` and `count` having to move together — went with the old actor.

#### `T-16` · LinkedIn moved to an actor that returns the Hybrid / Remote tag

**The failure that caused it.** Three adverts in a row that the user opened were tagged **Hybrid**
on LinkedIn and had been kept as Remote, and he said so in the plainest terms available: *owner's note: about 99 percent of what was returned was Hybrid - a very big failure*. I had told him
57 listings were "100% safe to apply". That was wrong. Measured afterwards on the 57: 23 said
fully remote, 17 came from remote-only boards with vague prose, **11 were genuinely doubtful**
(Charles Schwab: *"we believe in the importance of in-office collaboration"*; Catawiki: *"a hybrid
setup … with a minimum of two [days]"*), and 1 said nothing at all. Not 99%, but the claim
"100% safe" was mine and it was false — and **no rule that reads wording could have made it true**,
because the tag is not in the wording.

Three of the four adverts he sent, and why each got through:

| advert | tag on LinkedIn | what the Work Location rule saw |
|---|---|---|
| VisionBI | Hybrid | *"twee dagen op de klant locatie … of gewoon remote"* — the stray "remote" at the end of a hybrid sentence satisfied the rule, and `twee` / `klant locatie` were not in the office-days pattern |
| KLM | Hybrid | *"Als je functie dit toelaat: thuiswerken"* — "if your role allows it", in a benefits list, was the entire remote claim |
| IDPP | Hybrid | its text **literally says `Working Model: Remote`**. No rule on wording can ever catch this one; only the tag can |

**The tag cannot be read from LinkedIn's public page — checked, not assumed.** A fetch of the
IDPP advert with the app's fullest ladder gave 274,866 characters of HTML and the word `hybrid`
appeared **zero** times; `jobLocationType` and `TELECOMMUTE` appeared zero times. The chip is
rendered only for a logged-in session. So *"give Claude the link instead of the text"* (The user's
question) would show Claude the same page without the tag — or the login wall. It adds nothing.

**It also cannot come from `curious_coder/linkedin-jobs-scraper`.** 26 keys on a live run, none
for workplace type, and its Document says why: since August 2026 LinkedIn's AI search keeps only
four real URL filters (date, company, Easy Apply, under 10 applicants); `f_E`, `f_JT` and `f_WT`
are merely *"converted into natural language and appended to the keywords"* with *"no guarantee"*.
That is `T-6`'s measured ignore, explained by its own author. The Document lists `workplaceTypes`
and `workRemoteAllowed` as output fields; **no live row ever carried either**.

**What changed the answer: looking at other actors.** Area 16 below recorded the decision *"stop
looking"* after three routes failed — and all three were routes into the **same** actor. The store
has 97 LinkedIn-jobs actors. Their Documents and input schemas were scanned for workplace words,
then a dozen were run for 5 rows each. Two return the tag: `memo23/linkedin-jobs-scraper` (3 of
10 rows, marked `"inferred"` — not trusted) and **`apimaestro/linkedin-jobs-scraper-api`**, which
returns `work_type` on **every row** — 225 of 225 on real data.

**That is now the LinkedIn actor** (`apify.LINKEDIN_ACTOR`; the old one is kept as
`LINKEDIN_LEGACY_ACTOR` and nothing runs it). Measured, same method as `T-6` — one parameter
changed, job ids compared:

| parameter | verdict | evidence |
|---|---|---|
| `remote` | **honoured** | 100 of 100 rows tagged Remote; only 43 ids shared with the unfiltered run, so it searches *deeper* for remote jobs rather than trimming the same list |
| `date_posted` | honoured | `day`: 5 rows, every one 0 days old · `week`: oldest 6 days · `month`: oldest 27 |
| `sort=recent` | honoured | median age of the first 30 results 17 → 10 days; a different 36% of jobs |
| `easy_apply` | honoured | 100 rows → 38, **every one** Easy Apply |
| `under_10_applicants` | honoured, weakly | 100 → 18 rows; the applicant count is empty on those rows, so the effect shows in the number of results only |
| `experienceLevel` | **IGNORED** | all five levels returned the same **96 of 100** ids, 20 senior-titled and 0 junior-titled in each |
| boolean `OR` / quotes in `keywords` | **honoured** | 100 of 100 titles contained a phrase from a 3-phrase OR query; the same words joined by spaces gave 5 of 15 |

`experienceLevel` was measured and is **not offered**: Seniority is classified in the table and
no actor is asked about it (The user, when he saw it in the results: *owner's note: Seniority was never to be checked in the actor at all*).

**What the swap changes in the code**, in the order a row travels:

- `_linkedin_request` — plain fields (`keywords`, `location`, `limit`, `date_posted`, and
  `remote` for a Remote search), no search URL, no `autoConvertToAiSearch` (this actor does not
  rewrite the query). `LINKEDIN_DATE_TO_WINDOW` maps our `pastWeek` etc. to `day`/`week`/`month`.
- **`remote` is the window's *Workplace Type*, sent exactly as chosen** (`T-21` — this bullet used to
  describe a switch called `allWorkplaces` and a value derived from the work mode, both gone). The
  Remote / Not Remote row *sets* that dropdown (Remote → Remote, Not Remote → Any) and the field
  takes ONE value, so "everything but remote" cannot be asked. With no window at all the builder
  still sends `remote` for a Remote search, which is what every test written before the window had
  a say reads. (Italy was exempt here until `T-23`; it is not any more.) It is a
  *recall* setting and not a decision — nothing is deleted at the actor, every row carries its own
  tag, and the Filter decides, which is the user's rule: the actor brings what he is looking for and
  his own Filter does the rest.
- `_run_linkedin_pages` — the actor returns **at most 100 rows per call** (`limit` maximum), so one
  search is several calls with `page_number`. Measured depth on one query with `remote` on: page 1
  gave 100, page 2 gave 55, page 3 gave 0. A page shorter than 100 is the last page; ids are
  de-duplicated across pages; a Results limit under 100 is the actor's own `limit` and ends the walk
  after one call (`T-21`; the `maxResults` cap this used to name is gone). **The first page failing
  propagates like any single-call actor; a later page failing keeps the rows already paid for and
  says why in the Log**, because losing 100 paid rows to a hiccup on page 2 would be a bill with
  nothing to show and swallowing the reason would be `O-2`.
- `normalize_linkedin_pro` — `job_title`, `company`, `job_url`, `description`, `work_type` →
  `workplace_type`, the date without its time, and the employment type out of `job_insights`
  (**225 of 225 real rows parsed, zero empty**: 137 Full-time, 48 Part-time, 29 Contract, 8
  Internship, 2 Temporary, 1 Volunteer). `seniority_level` is `None` and stays so — this actor does
  not return one and an invented value would be worse than none; `seniority_of` reads the title.
- **`passes_work_location_rule` reads the tag first**, (the Milan/Turin exemption that preceded it was removed by `T-23`) and before
  every word in the advert. Hybrid or On-site → dropped. Remote → the word "remote" is no longer
  required and a stray *"located in"* cannot overrule it, but a phrase that denies remote work
  outright, or a stated number of office days, still can: an advert tagged Remote that says "three
  days a week in our office" is contradicting its own tag. **A Not Remote search reads it the
  other way round** (Remote → dropped, Hybrid/On-site → kept). A row with no tag — Google, Indeed,
  Glassdoor, the direct APIs, and every LinkedIn row banked before this change — falls through to
  the text rules unchanged.

**The measured comparison, same query (`Data Analyst`, Netherlands, one week):**

| | old actor | new actor |
|---|---|---|
| rows | 300 | 180 unfiltered · **45 with `remote`** |
| tagged | no tag | every row |
| price per row | **$0.002** | **$0.005** |
| cost of that run | $0.596 | $0.225 (45 rows) |
| description length, median | 4,495 | 3,715 |

Of the 300 the old actor returned, the new one also saw 46 and tagged them: **27 Hybrid, 16
On-site, 3 Remote — about 6% Remote.** And of the 11 the old text rule had called Remote *and*
the new actor could tag, **10 were Hybrid or On-site.** The sample is small and the direction is
what matters, but it agrees with what the user saw by clicking.

##### THE PRICE I FIRST QUOTED WAS WRONG, and it consumed his credit

I told the user the new actor was "~300 times cheaper per row, $0.002 for 45 rows". **It is 2.5 times
MORE expensive per row: $0.005 a job**, read from the actor's own pricing events
(`pricingPerEvent.apify-default-dataset-item.eventPriceUsd`). The figure came from a run's
`usageTotalUsd`, which comes back **empty or zero for a pay-per-event run at the moment it
finishes** — the earlier printouts all said `$0.0000` and I read that as the price. Then I ran
dozens of 100-row tests on his new key before checking the unit price, and **spent the whole $10
monthly cap — $11.27** — which is why the final live end-to-end run could not be done.

What is true: it is cheaper **per useful row**, not per row. The old actor's 300 rows were ~6%
Remote, so a Remote row cost about $0.03; the new one returns only Remote rows, so one costs
$0.005. Per search the ceiling is about 155 Remote rows, **~$0.78**, against $0.60 for 300 rows
that were mostly office jobs. Rules for the next person who prices an actor: **read
`pricingPerEvent` from `client.actor(id).get()`, never `usageTotalUsd` from a fresh run; and
before running a test more than once, multiply the unit price by the rows you are about to buy.**

##### The end-to-end run, done afterwards on a fresh key

A real LinkedIn-only search through the app's own `run_search`, then `reapply_filters` with Claude,
then every link opened. Netherlands, Mid, Remote, the 2-week window (LinkedIn `pastMonth`), **no
result cap**:

```
SEARCH    198 rows, 682 s, $1.00 (as the app logged it)     tag: Remote 198 of 198
          page 1 100 rows · page 2 100 rows · page 3 0 rows      (the broad query)
          the precise "Mid-Level …" query                    0 rows
FILTER    198 -> 167 kept, 11 removed, 151 flagged
CLAUDE    16 not flagged, all at or above the 35% floor
LINKS     167 of 167 open, and each is the live advert it claims to be:
          0 failed to fetch · 0 title mismatches · 0 closed · 0 login walls
```

The 16 are all `Remote`-tagged, all `English only`, Seniority `Unspecified`, Type 10 Full-Time /
3 Contract / 2 Part-Time / 1 Internship. **The query the app really builds is 34 and 89
characters, not forty phrases** — an earlier worry in this entry that a long boolean query might
be refused did not arise; both were accepted.

**Of the 151 flagged, about 100 are the résumé-fit pass** (*"Requires 4+ years; résumé shows 2"*) and
**51 are Rule 1 or 6** — Claude reading office or location requirements in the text. That split
matters: the Remote tag sorts out *workplace type*; it says nothing about whether the role asks
for presence in a particular country, which is what most Rule 1 flags on Remote-tagged rows are.

##### RULE 1b: a region that contains where he lives is not a restriction against him

**17 of the 49 Rule 1 flags were about Europe, the EU or a European time zone** —
*"Remote restricted to Europe; he is in Italy"* — and Italy is in Europe, the EU and EMEA. Claude
read the region as a restriction *against* him. Added to rule 1b in all four Remote prompts, by
one script that refused to write unless every file matched once (`O-5`/`O-17`), mirrors
regenerated by script (`M-1`). The Not Remote prompts have a different rule 1 and are untouched.

**Two wordings, measured by re-asking Claude about the same 17 plus 8 real presence requirements
as controls:**

| wording | Europe listings now KEPT | real-presence controls wrongly kept |
|---|---|---|
| a region containing his home "is not a restriction" | 6 of 17 | 1 of 8 |
| *"based in" / "located in" / "must reside in" + such a region "is satisfied, not violated"* | **7 of 17** | 1 of 8 |

**That is a partial fix and it is recorded as one.** Claude's own answer shows why the second
wording barely helped: *"Must work from EU region; he lives in <city>, <country>"* — it states the
fact and drops anyway, because 1b's first sentence says *"based in" → DROP* and it applies that
to the region before reaching the exemption. The remaining ten are mostly hard phrases read as
physical presence (*"physically located within Europe"*), and **some of them are correct drops**:
`UTC+0` is Britain and Portugal, not Italy, and *"requires travel within Europe monthly"* really
is a presence requirement. The one control that flipped (*"Remote-first stated but Amsterdam
location implies office presence required"*) was a flag on **inference** — which rule 1 forbids —
so that change is an improvement rather than a loss.

The model is the cheap one (`claude-haiku-4-5`). Further wording changes have diminishing returns
and each costs a measured round; the next real lever is a stronger model for the Rule 1 question
alone, which is the user's decision because it is a price. **These are flagged, not deleted** — the
review dialog still shows every one of them.

##### THE COST LINE IN THE LOG WAS WRONG TOO, for the same reason

The live run printed `$0` for every LinkedIn call while buying 12 rows at $0.005. Measured: at
the moment a pay-per-event run ends, `usageTotalUsd` is **0 and `chargedEventCounts` is also 0**;
a 10-row run read 0 for ten seconds and then $0.05. The app read the run once. It is the same
field read at the same wrong moment that first gave the user a wrong price.

`_settled_usage` now waits for it — polling every 3 s, for at most 45 s — **only** for a run that
carries `chargedEventCounts` at all (pay-per-event) **and** returned rows (a run that bought
nothing cost nothing). If it has not settled the answer is `None`, printed blank:
**unknown, never a false $0.00.** Cancelling during the wait returns at once with the rows
already fetched. The older per-compute actors are read once, exactly as before. It adds about
twelve seconds per LinkedIn call, which on the real run above is part of the 682 s.

##### Still not done — say so rather than imply it

- The Bank's 2,577 existing LinkedIn rows carry **no tag** and will not until re-searched.
- `experienceLevel`, `company_id`, `geoId` and `distance` are unmeasured or dead and are not offered.
- The `precise` (Mid-Level …) query returned 0 rows with the remote filter on, one week to a month.
  Whether that is the phrases being rare or the filter being strict has **not** been separated;
  it would take one unfiltered run of that query, about $0.50.
- ~~Glassdoor's `remoteWorkType` has the same untick problem~~ — **fixed in `T-19`, and now by design
  in `T-21`**: the window's value is the value sent.

#### `T-8` · what a real run costs and where the time goes

One uncapped Mid search of the Netherlands, 2-week window, 4 October 2026: **4,349 listings in
105 minutes for $8.65**, then the Filter in 4 minutes for $0.39 of Claude.

| source | listings | cost |
|---|---|---|
| linkedin | 2,577 | **$4.87** |
| google (+ Deep Crawl, startup sites, pattern discovery) | 476 | $1.08 |
| **europa.eu (EURES)** | **464** | **$0.00** |
| indeed | 442 | $0.00 |
| workatastartup.com | 188 | part of $0.82 |
| werk.nl | 125 | part of $0.82 |
| arbeitnow, remotive, weworkremotely, remoteok | 47 | $0.00 |
| **glassdoor** | **6** | $0.00 |

Four things worth keeping from that:

- **EURES gave 464 listings for nothing**, third-largest source in the run. Free, no key, and
  it was nearly switched off.
- **Glassdoor gave 6** because its real remote filter is now sent. That is the filter working,
  not the source failing — it used to give 300 of which most were office jobs.
- **Two "direct APIs" are not free**: `werk.nl` and `workatastartup.com` have no public API and
  need an Apify actor, and between them took **$0.82 and about ten minutes**. The other eleven
  really are free.
- **Deep Crawl was the slow stage and the second-best source**: ~25 minutes and $0.31 for
  **187 listings**, 161 of them from `wellfound.com` alone. It is also where the three
  best-matching listings of the entire run came from. Switching Google off saves ~50 minutes
  and $1.08 and costs 260 listings.

#### `O-12` · a Not Remote search asked LinkedIn for remote work only

`f_WT=2` is LinkedIn's own remote-only filter and it was on **every** search of every country
except Italy, whatever work mode was selected — silently, because the listings that came back
looked normal. The history explains it without excusing it: the app was remote-only when that
URL was written, Not Remote arrived later and was built into the Filter, and nobody went back
to the search. `search_work_mode` was not even a parameter of `run_search`.

It travels the whole way now: `SearchWorker → run_search → _process_plan_item → _actor_request
→ _linkedin_request`. **Indeed and Glassdoor take the flag and ignore it** — they do not filter
by working arrangement — and there is a test for that too, so nobody later "fixes" them into
silently narrowing a search.

| | changes the search? | applied where |
|---|---|---|
| Type (Any / Thesis / Internship) | **yes** — which pass runs. The old Level (Entry/Junior/Mid/Senior) was removed in `T-19`; the precise job query it drove added 1–3 rows | `_resolve_passes` |
| Remote / Not Remote | only LinkedIn, and only since O-12 | `_linkedin_request`, then the Filter (the mechanism changed with `T-16`: `remote` is now a real field, not `f_WT=2` in a URL) |
| Country / city | yes | the whole plan |

#### `countries or COUNTRIES` — the most expensive single character in the project

```python
countries = countries or COUNTRIES      # wrong
countries = COUNTRIES if countries is None else countries   # right
```

An **empty** list is a deliberate cities-only selection, which the wizard explicitly allows
(it validates "at least one country OR city"). `or` read it as "no preference, search
everything". Picking only Amsterdam therefore ran the full 18-country search on top of it:

```
57 paid platform actor calls instead of 3
74 Google query lines instead of 4
16 of Jooble's non-renewable 500 lifetime requests
```

`is None` distinguishes "the caller did not pass one" from "the caller passed an empty one".
`or` cannot.

#### The query shape, and the measurement that fixes it

**A job title in this field is never translated.** Across **17,544 real European titles**:
"DevOps" appeared 273 times and every local form tried appeared **zero** times; "Data
Engineer" appeared 821 times in German adverts against **one** "Dateningenieur". A German
employer writes the English title and German around it.

So the title goes out in English everywhere, and what the local passes add is the local word
for **a beginner** and for **an internship** — the half that really is translated (`I-2`: a
kind word alone returns the wrong field entirely; `I-3`: English-only role words found 23
German-named results against 47 with the German terms).

**Broad first, then precise.** Broad is the backbone — 273 of the 302 relevant listings
measured — and precise is the cheap top-up that catches the 29 most on-target titles the broad
query's thousand cannot hold. The job pass has a precise shape too now, and it is the
entry-level one: it used to be skipped, back when the job keywords were role titles and an
exact phrase could only narrow them. Since the move to DevOps and MLOps the broad query
returns the whole field, seniors included, and **the junior roles the user can actually be hired
into never survive LinkedIn's thousand.** `keywords_for` returns `None` for shapes with
nothing to ask, so a pass that gains nothing costs nothing.

**On platforms that ignore quoted phrases the precise query REPLACES the broad one** rather
than joining it — otherwise it is a second full-price call for the same 1,000 rows.

#### Concurrency is capped at 2, and the cap is an account limit

```
you will exceed the memory limit of 16384MB for all your Actor runs and builds
(currently used: 16384MB, requested: 8192MB)
```

Two actors of that size fit; a third does not. `SEARCH_MAX_CONCURRENT_PLATFORMS = 2` — raise
it only if the Apify plan's memory goes up. For the same reason `memory_mbytes` is passed
**only** for the main Google call, which runs alone after `executor.shutdown(wait=True)`;
unconditional, each of the two concurrent platforms would claim the full cap at once.

**The three passes — Job, then Internship, then Thesis — run sequentially**, which is the user's
instruction (*owner's note: finish the jobs first, then Internship, then Thesis*) and
also means that **if credit runs out part-way, the Job pass is already done.**

#### `J-2` and the cancel bug — a crash or a cancel must not lose what was paid for

**`J-2`:** a crash used to lose every listing collected so far. There is a checkpoint now.

**The cancel bug is subtler and worth reading twice.** The loop checked `should_cancel()` at
the *top* of each iteration and raised immediately — **before draining the future whose
completion triggered that iteration.** A cancel arriving after a platform had finished all its
work threw that platform's rows away: verified with a faithful simulation, **0 rows kept
though two platforms had finished.** Now every completed future is always drained first;
cancellation only stops platforms that have not started, and the raise happens once, after the
loop.

A related one: cancelling left `done` short of `total`, so the progress bar froze partway and
read as "the app hung" rather than "the search stopped". The locations that will now never run
are accounted for.

#### `item_limit` is not one number

`item_limit` defaults to the wizard's per-search cap, which is right for
Indeed/LinkedIn/Glassdoor where **one dataset item is one job**. For the Google actor **one
item is a whole page of results**: a real full search builds 90 query lines × 3 pages = 270
page items, so a limit of 100 silently discarded 170 — and because the queries are ordered
country by country, that meant **dropping the last locations entirely** rather than trimming
each evenly.

And when the wizard's cap is switched off the value is a large number, not infinity, because
every one of these fields must be a number the actor accepts. The user's instruction — *owner's note: there must be no limit on finding listings* — came from the German run, where LinkedIn and Glassdoor each
returned **exactly 100 listings, the saved cap to the item**: both had more to give and
neither said so.

#### `C-1` · a failure that would not say why

```
LOCATION_DONE:Indeed|Germany|FAILED|
```

The field after `FAILED` is the reason, and it is empty. Running the actor by hand answered it
immediately:

```
Input is not valid: Field input.datePosted must be equal to one of the allowed values:
"", "1", "3", "7", "14"
```

That message names the field, the value and the alternatives. It reached Apify's client and
then went nowhere. **Two hours of a German search ran without Indeed because a perfectly clear
explanation was dropped on its way to the Log.** The reason went out as an indented grey
`  ! …failed:` line among hundreds of progress ticks, which is why it may as well not have
existed. It is an `ERROR:` line now.

**`C-2` · Indeed itself — resolved, my error not the app's.** The date option values were
wrong in the caller, not broken in Indeed.

**`R-4` · Indeed and Glassdoor collapsed after the move to DevOps — NOT A FAULT.** The field
changed; those two boards simply carry less of it.

**`N-6` · Indeed and Glassdoor return very little for a city search — INVESTIGATED.** Known
and accepted; their country searches are where their value is.

#### The date range, and what it does not reach

The range chosen in Search reaches the three paid actors and nothing else. Google results never
see it, and neither do the two direct APIs that between them supply most of a German search:
EURES and arbeitsagentur.de hand back whatever they hold — in one real search, **an advert
1,990 days old. Five and a half years.**

So the range is applied here as well, to every source equally. Only a listing whose **own date
field** says it is too old is dropped; one that gives no date is kept, because *not knowing
when something was posted is not evidence that it is old*. Placed before expansion and
enrichment, so nothing is fetched for a listing about to be discarded.

#### Order of the late stages, and why each sits where it does

1. **Open the index pages** — before enrichment, so whatever comes out goes through every step
   below exactly as if the search had found it directly. Measured on a real Austrian search:
   **nine such pages held 43 postings the search had never seen.** Additive: a failure returns
   nothing and the search carries on.
2. **Enrich thin descriptions.**
3. **Drop taken-down postings** — *after* enrichment, and that order is the point: many rows
   only receive their page text during enrichment, and a "Job Not Found" notice cannot be read
   off a page that has not been fetched. Measured on 34,693 listings: **27 say they are gone,
   all 27 were read, and all 27 are.**
4. **Report late problems** — everything that failed, in one window at the end, with Claude's
   plain-language fix advice. Deliberately not mid-search: interrupting a running search to say
   a site was quiet is exactly the popup this replaced. And **only the sites nothing could be
   read from**: a page whose postings the search already had is not a site with a problem, and
   naming it sends the user to fix something that works.

#### Two things that must survive a bug

- **Post-processing must never lose the fetched rows.** Everything after the fetch is working
  on data that already cost credit; if categorising or sorting raises, the raw DataFrame is
  still returned.
- **A raw search shows everything it fetched.** Duplicate and fake removal deliberately do
  *not* happen during a search — they wait for Filter. Correcting a row (a Markdown mirror put
  back on its real address) is allowed; removing one is not.

#### `NaN` is truthy, and it silently disabled two rules

Only some row builders set the optional boolean columns, so pandas fills the rest with `NaN`
— **and `NaN` is truthy**, which silently disabled the Remote rule and the English rule for
every listing in the dataset. They are normalised at the DataFrame boundary so a real `False`
reaches `jobs.json`, which also keeps that file valid JSON for anything other than Python's
own parser. `is_true_flag` guards every read regardless.

#### `J-1` · a segmentation fault three hours into a run — FIXED, cause not proven

lxml killed the process 56 minutes into the Amsterdam run (`N-7`). The browser rung is behind
`_BROWSER_LOCK` now and the checkpoint means a crash no longer costs the run. **Cause not
proven** is recorded honestly: if it returns, that is the entry to start from.

#### `O-10` · the money path was one 465-line function

The user: *owner's note: split it into the smallest modules; this part should become one of the safest in the program*. **Tests first**, because refactoring the least-tested and most expensive path is
exactly where a refactor does damage — Suite 7, entirely offline, around the one function that
spends real credit — and only then was a line moved.

The helpers are module-level now, not nested. They were only nested because the progress
counter was a `nonlocal` int; making it an object let them become **individually testable**,
which is the whole point: a wrong actor call or a mis-sorted platform result can be reproduced
without standing up an entire search.

**The real cost is read from Apify, never estimated** — it is present once a run reaches a
terminal state, even a failed one, because Apify still bills for compute already spent.

**The pre-flight check moved.** It used to run before Indeed/LinkedIn/Glassdoor even started,
but everything it checks is only used later, inside the Google stage. It runs right before that
stage now, so nothing is checked before it is about to matter.

---

### 7 · Duplicates

Three passes, in this order, and each exists because the one before it could not see
something.

**1 · Exact URL, walked best-first — not first-arrived.** `L-5`. The title pass always walked
best copy first; the exact-address pass walked the list as it arrived. Harmless until `L-4`
put Markdown mirrors on their real address: wearedevelopers.com serves every vacancy twice
and **16 of 95 mirror copies carry no text at all** — arriving first, an empty mirror would
have deleted the full posting sharing its address. Both passes walk the same order now, and
test 4.4c puts the empty mirror first on purpose.

**2 · Title + description similarity.** Catches a republisher like EURES.

> **Tried** · grouping by company name in this pass.
> **What happened** · it only ever compared listings that *had* a company, and on a real
> search most do not — **1,189 of 2,199** Netherlands rows arrived with none, so their only
> duplicate check was an exact URL match.
> **Now** · the text is compared instead, which found **204 more duplicates** on those same
> rows, including copies where one source wrote "KPMG" and another "Klynveld Peat Marwick
> Goerdeler".

**3 · Same employer, same title, different host.** `O-6`. For the copies the text test cannot
see: QuantumBlack's Data Scientist was **3,802 characters on qarera and 1,929 on LinkedIn**,
so their descriptions never reach the threshold. The real Amsterdam result the user would have
opened held **8 duplicate pairs among its 48 listings** — QuantumBlack, Metyis, Robeco,
Philips, Genmab, each on two boards.

Three conditions, so a company advertising two real openings under one title is not merged:
the employer must be named on both and match, the titles must match once the board's tail is
off, and both must be in the same country when both say one. **Rows from the same host are
left to the passes above** — a board listing a job twice is a different problem, and its two
copies usually do have matching text.

**`N-5` · the short-tail case.** SurplusMap's internship came back from finn.no as "Internship
Data Engineer" and from thehub.io as "Internship Data Engineer | SurplusMap" — the same
posting, **99.4% the same text**. The duplicate check strips the employer's name from a title,
but only when the *source* named the employer, and at that point neither row had: the name is
read out of the posting later, by Claude. The two titles scored **84 against a 90 cut** and
both were shown. A short tail after a pipe is dropped from the comparison key now; a long one
("Data Engineer | Build the data foundation for the future of care") is the job itself and is
kept.

**Open, and accepted by the user.** One job posted as "Capgemini" on one site and "Capgemini
Engineering" on another still shows twice. The rule that would bridge them would also merge
"Siemens" with "Siemens Healthineers", and **losing a real opening costs more than showing a
duplicate row**. His decision: *owner's note: that does not matter, fine*.

---

### 8 · Getting the real text of a posting

#### `B-1` · a description that was only a navigation menu

Every arc.dev posting arrived with **exactly 505 characters**, all of it the site's own menu:

```
For companies  Hire developers  Hire designers  Hire marketers  Hire product managers …
```

Not one word of the vacancy. `thin_description` is set by **character count**, so 505
characters passed for a real description and the row went to Claude, **which was asked to
judge a job it had not been shown.**

`looks_like_chrome_only` treats a description carrying none of the words a posting has as
thin whatever its length, and re-fetches. It recovered a real posting for 8 of the 12 tried,
every one a remote role.

#### The word list that decides this was written from English, and that was the bug

The first version had **sixteen English phrases against eight German, five Dutch, four French,
three Italian, three Spanish — and nothing at all for Portuguese, Swedish, Norwegian, Danish,
Finnish or Luxembourgish.** A Danish advert scored zero however real it was, and the guard
silently threw away the page that had just been fetched for it.

It showed up in German first because German is where the corpus is. Of a hundred
arbeitsagentur.de listings whose pages were fetched for real, **eight came back with 1,768 to
4,788 characters of plainly genuine advert** — *"30 Tage Urlaub"*, *"unbefristeten
Arbeitsvertrag"*, *"Zum nächstmöglichen Zeitpunkt suchen wir einen AI Consultant"* — and were
rejected for carrying only one or two of the eight words the list knew.

The list is per language now and written **from real adverts rather than from English**. The
German entries come from 546 real descriptions in the German corpus: `erfahrung` appears in
57%, `aufgaben` in 49%, `kenntnisse` in 47%, `studium` in 45%, `abgeschlossenes` in 40%.

**What is deliberately NOT in it: words a job BOARD uses about jobs.** "Vollzeit", "Teilzeit",
"Gehalt" and "Arbeitszeit" all appear in the filter widget down the side of a search page, and
adding them would make **every index page look like a posting.**

**How many a real posting carries**, measured on the Austrian corpus: the 401 clean postings
carry a median of **14**, and the quarter that carry fewest still carry **5**. Chrome-only
descriptions carry 0 or 1 — arc.dev's 505 characters score **zero**. Three is comfortably
between them.

#### `B-2` · enrichment could replace a good description with a longer bad one

A cleaner route has to keep enough of the page to be believed. Set from measurement, not
taste: **across 24 real postings the cleaner routes kept 60–90% of the page text, and the
single failure kept 24%.** Anything above half is chrome being stripped; anything far below it
is content going missing.

`<nav>`, `<header>`, `<footer>` and friends are stripped *before* extraction — identical on
every page, they would dilute the description and, worse, **feed the content rules words the
posting never used.**

#### Why a second pass exists, and what it is not for

A real German search fetched **860 pages in 65 seconds; 579 came back with a description and
281 did not.** Running the very same URLs again afterwards, with the same code, recovered
**196 of them.** Nothing about those pages or that code had changed, so a share of every
enrichment pass is lost to whatever the network was doing in that minute — which is how **217
arbeitsagentur.de adverts reached Claude as a 69-character stub.**

> **Tried** · the obvious explanation, crowding: eight workers into one host, since 789 of
> those German listings came from arbeitsagentur.de alone.
> **What happened** · it is wrong, and the measurement says so plainly. The same 60
> known-good pages, fetched at eight, four and two at a time:
>
> ```
> 8 at a time     5 seconds    60 of 60
> 4 at a time     6 seconds    60 of 60
> 2 at a time    11 seconds    60 of 60
> ```
>
> **Not one failure at any speed**, and throttling the host merely doubled the time. A
> per-host gate was written for this and then **removed again**: it cost real time and bought
> nothing.
> **Now** · the failures are transient, so the answer is to **ask again rather than ask more
> politely**. Five attempts spread across about ten minutes, with lengthening gaps — an
> immediate retry is part of the same burst that failed.

**What the retries do not recover: pages that are genuinely gone.** Of the 123 still empty
after two passes, fetching each one alone and unhurried recovered **exactly one**. So the ones
that never answer are dropped rather than sent onward as a bare job title.

Ten minutes is the user's own figure, and the trade is his standing one: *owner's note: time does not matter, and no listing may be lost* — time is free, a lost listing is not.

#### `N-7` / `J-1` · lxml killed the process outright

The Amsterdam run died 56 minutes in with **no Python error of any kind**. Windows recorded
why:

```
Faulting module: etree.cp38-win_amd64.pyd   (lxml)
Exception code:  0xc0000005                 (access violation)
```

trafilatura parses with lxml, **whose C parser is not safe to drive from several threads at
once** — and it ran inside an 8-thread pool and again inside the crawl. A C-level fault cannot
be caught by anything in Python: the process is simply gone. That is why the checkpoint exists
at all, and why the earlier fault of this family was mitigated rather than cured.

`_BROWSER_LOCK` puts one thread at a time inside trafilatura. **The cost is nothing that
matters**: extraction is a few milliseconds of CPU per page against a network fetch of a second
or more, and every fetch still runs in parallel — only the parsing is queued.

#### Two more things about fetching

- **Enrichment uses the fetch ladder, not a bare GET.** A posting on a site that answers 403 to
  a browser-shaped request is exactly the case enrichment exists for, and the rung that site
  needs was already worked out when its pattern was discovered.
- **trafilatura is optional on purpose.** If the package is missing from a build, `readable_text`
  falls back to the plain tag-stripping pass this app always used, rather than the whole search
  failing over a description.

**`K-2` · "nothing could open it" for three sites that open fine — OPEN.** Still unexplained.
**`K-4` · four sites need an account**, and whether they are worth one is not yet known.

---

### 9 · Sources and normalisation

Every source hands back a different shape, and most of the faults in this area are a field
read literally that should have been read carefully.

#### `N-1` · Glassdoor's location arrived as a raw object

```
{'countryId': 180, 'id': 2918317, 'name': 'Oslo', 'type': 'C'}
```

Reading the key itself put that whole structure into the Location column, the Excel export,
and **the text every rule reads**. Measured on a real Oslo run: **all 38 Glassdoor rows**
carried it. The name inside it is the city, so the dotted path is asked for first and the
object is the last resort.

#### `N-2` · the board's own name was part of the job title

A page's `<title>` ends with the site's own name far more often than not, and both Google and
the crawler take the title from there. Measured on the real Oslo run, of 1,018 listings:

```
224  ended in "| Wellfound"
170  ended in "| FINN.no"
 10  ended in "| arbeidsplassen.no"
```

That name is not part of the job: it showed in the table, went into the Excel, was read by
the duplicate check, and reached Claude on the Title line.

**Only the site's OWN name is removed, matched against the address the listing came from** —
never a general "strip everything after the last dash", which would eat *"Data Engineer -
Microsoft Fabric"*. And the connector word ("Data Engineer **| Jobs |** Wellfound") is removed
only *after* the site's name has been, so "Data Engineer - Jobs" from a site that never named
itself is left exactly as the employer wrote it.

#### `L-4` · Markdown mirrors — one vacancy arriving as two rows

wearedevelopers.com serves every page twice, at the same address with `.md` on the end — its
own words: *"Every page supports .md or Accept: text/markdown"*. Google indexes both, and the
crawler follows the link the HTML page makes to its own mirror:

```
/jobs/ext/2836673-devops-engineer        title "DevOps Engineer"
/jobs/ext/2836673-devops-engineer.md     title None
```

Measured across every corpus on disk: **95 such rows, every one from wearedevelopers.com, not
one with a title.** The addresses differ, so duplicate removal never matched them. The title is
empty, so the field filter kept them — **a missing title is never evidence** — and one reached
Claude in the Austrian DevOps run and was KEPT, listed as "None".

**This does not delete anything.** The user's rule is that a raw search shows every listing as
fetched and cleanup happens at Filter, so the row is **corrected**: its address is put back to
the HTML copy's, and its title and company are read out of the Markdown itself. Filter's
duplicate check then sees two rows at one address and keeps one.

**The Markdown copy is the cleaner of the two**, which is why it is worth correcting rather
than discarding. The HTML copy's text opens *"WeAreDevelopers WeAreDevelopers Sign in Search
videos, moments, articles"*; the Markdown copy opens *"# Data Scientist - Company: Sportradar
AG - Location: Wien, Austria (Remote available)"*.

Two details that cost a measurement each:

- **The page text arrives in two shapes and both are real.** Most is whitespace-collapsed, so
  the Markdown's line breaks are gone and a heading reads `--- # Data Scientist - Company: …`.
  Some keeps its line breaks and has no heading marker at all: `Agent guide: /agents.md.
  [blank] Platform Engineer [blank] Company: RED`. **The first version read only the first
  shape and recovered 59 titles of 79.**
- **16 of the 95 mirrors read "# Job Not Found".** Giving those a title would make a vanished
  vacancy look like a live one, so they are left untitled and the dead-posting check decides.

#### `O-14` · 38 German listings were not in Germany

Google returns no location field, so a Google result is stamped with the country whose query
produced it — right for **5,495 of 5,662** listings and wrong for the ones a German query
surfaced from elsewhere: a Casablanca job, a Lisbon job, a New York job.

`country_from_listing_location` answers **only when certain**: the place must be one the app
knows, the text must not also name the searched country, the place must not be "Remote" or
"Europe", and **exactly one** country must be named. Anything less returns `None` and the stamp
stands, because the country picks the language vocabulary downstream — a wrong label costs more
than a vague one. It relabels; it never removes.

> **The first version was wrong and reading the output caught it.** It looked at only the last
> bullet segment, so *"Software Architect at openigloo • Berlin • Hyderabad"* became India and
> a job naming both New York and a Swiss city became Switzerland. Every segment is read now,
> and **two countries means no answer.** Verified by printing all 132 relabels across 8,133
> rows of four real corpora and reading each one.

`_WORLD_CITIES` holds cities outside the eighteen countries, which turn up because a board
indexed by Google lists the world. **Only names with one obvious home**: "Cambridge" and
"Birmingham" are deliberately absent, and so is anywhere the app already knows.

#### Dates — six shapes in 11,186 real listings

Read in order, first usable one wins; a source that sends two never disagrees with itself, and
one that sends none falls through to `None`. A listing with no date is **kept** — not knowing
when something was posted is not evidence that it is old.

#### Google is told never to return the three paid boards

LinkedIn, Indeed and Glassdoor are already searched directly and better by their own actors, so
Google is told to skip them — otherwise the same listings are reprocessed through a worse,
unstructured path.

**The exclusion list is the brand keyword, not a full domain, and that matters for real**: a
live test turned up a result from **glassdoor.ca** that an earlier `.com`-only substring check
let straight through. Indeed and Glassdoor have dozens of country domains that cannot be
enumerated in the query itself, so brand-substring matching app-side is what actually
guarantees it.

**The role terms for Google are curated job-title phrases, not the broad OR-list** the
structured APIs get — a bare "AI" or "Big Data" is far too noisy for full-text search. Trimmed
from 8 to 5 to 4 (dropping "Data Analyst") to free word budget in the ~32-word query limit for
more domain exclusions, **which is the better trade**: every excluded domain is cost not spent
scraping a page Google should not have returned. Accepted deliberately: a listing titled
exactly "NLP Engineer" with none of the four phrases elsewhere on the page can be missed.

#### The deep-crawl patterns were discovered, never guessed

For each known job site, the URL glob its individual posting pages follow — found by fetching a
real search page for each domain with `htmlTransformer: 'none'` and reading the raw `<a href>`
links, because **the default "readable content" extraction sometimes picks the wrong part of
the page entirely** (finn.no's category sidebar instead of its listings).

A domain with no entry simply is not deep-crawled. Several were tested and **found to expose no
real job links in their initial page load at all** — werk.nl, arbetsformedlingen.se, jobnet.dk,
duunitori.fi, vdab.be, jobat.be, ziprecruiter.com, karrierestart.no — through cookie walls, bot
detection, or job cards that never resolve to a crawlable href even after full rendering.

Deliberate absences, each with its reason:

- **seek.com.au** — confirmed 403 bot-blocking that turned a real test into a **26+ minute
  retry storm**.
- **weworkremotely.com, ziprecruiter.com** — the cloud crawler is headless and datacenter-IP
  based and got a Cloudflare challenge. **weworkremotely's block is headless-detection
  specifically, not automation in general**: the same domain works fine through the
  manual-assist path, which runs a real visible browser.
- **jobs.ch, jobup.ch, arbetsformedlingen.se, EURES, remotive.com, remoteok.com** — each has a
  free direct JSON API returning the same listings at **zero Apify cost**, so a cost audit
  removed them entirely. **The one exception is arbeitsagentur.de**, kept as-is because its
  free API's description is thinner than what Google plus deep-crawl finds.
- **arc.dev needs two patterns** — it serves localized variants (`/en-id/remote-jobs/details/**`)
  alongside the plain ones.

**`K-1` · "53 XING pages gave up nothing" — XING was working.** The report was measuring the
wrong thing: a site that answers and yields no *recognisable posting links* is not a site that
failed.

**One entry exists because of a question.** Six of seven silent Dutch sites render in
JavaScript or offer only category links and there is no pattern to be had — but the seventh
opened with 709 KB and 48 links, and **the app's own pattern discovery learned `/job/**` from
it unprompted.** Without an entry its postings were never deepened into rows.

#### `remoteok.com` · a timeout below the source's normal speed

The site has **no search endpoint**: one call returns its entire board. Measured five times on
a healthy connection:

```
34.7s   34.0s   38.0s   43.5s     all HTTP 200, all 623,084 bytes
 0.3s   HTTP 502                  it also serves the occasional bad gateway
```

The fetcher allowed 30 seconds and the Health Check 15. **Both were below the source's ordinary
speed**, so every real search dropped it silently and the Health Check called it broken before
nearly every run — `O-7` again in a different hat. One constant now, 75 seconds, used by both.
Both numbers looked perfectly reasonable, which is why nobody questioned them.

**`M-6` · HTML entities are not unescaped before the rules read a posting.** "technology &amp;
domain knowledge" — measured across five real corpora: **26,445 entities on 27–43% of
listings**, from the sources that hand over plain text rather than HTML. No keyword verdict
changed when they were unescaped (measured over all 24,295), so this is not a filtering fix; it
is what the user reads in the table and the export, and what Claude is given. **The Bank keeps the
untouched original.**

**`R-2` · Jooble has no API key — BY DESIGN.** Its free tier is capped at **500 calls for the
life of the account**, which is why it is not configured, and why the pre-flight check does a
config-only check for it while every other source gets a real request.

---

### 10 · Storage, and not eating your own data

#### `O-4` · the Filter used to eat the pool it filters

Not a wrong verdict — a design fault the user found **by describing the app back to me**. A search
banked its listings, the Filter judged them, `save_jobs` wrote the survivors over `jobs.json`,
**and the pool was gone**: trying another Level, or Not Remote, meant paying Apify for the same
search again.

Everything measured in the whole campaign was only possible because the Amsterdam pool had been
kept by hand, outside the app.

`bank.json` now holds what a search returned, **keyed by URL** so re-searching a city does not
bank a posting twice and the newest copy wins. **The Filter reads from the Bank and never
writes to it**, so any Level and either work mode can be tried as often as the user likes, for
about $0.03 instead of $3.

#### Surviving a crash mid-search

> A three-hour German search died with a segmentation fault part-way through fetching the
> postings it had just found. **Three hours of work and $6.40 of Apify credit, and every
> listing collected went with it** — because `run_search` held everything in memory and wrote
> nothing until it returned.

A crash inside a C library cannot be caught by anything in Python, so there is no way to
*handle* it; **the only defence is to have written the rows down already.** After each stage,
whatever has been collected goes to disk. If the process dies, the next start finds the file
and says so.

**Deliberately a separate file from `jobs.json`.** A half-finished search is not a result — it
has not been deduplicated, dated or filtered — and silently merging it into the real list would
make a crashed run **indistinguishable from a good one.**

#### A forgiving loader must still say something

The loaders return empty rather than crashing on a corrupt or half-synced file, which is right.
**What was missing is that they also said nothing.** `jobs.json` is not a cache; it is what a
paid search produced, and a file that silently reads as empty **looks exactly like "no
results"** from the outside. Read errors are collected into a plain list — storage is imported
by everything and takes no `progress_cb` — and the UI drains it and logs each in red.

**Catching `JSONDecodeError` alone is not enough.** A file can be perfectly valid JSON and
still be the wrong *shape* — `null`, `"hello"`, a list — and each used to be returned as-is, so
every caller doing `settings.get(...)` crashed. **This is not hypothetical: the app's folder
lives in OneDrive**, and a sync conflict or a half-finished write produces exactly these files.

#### Three more rules about data

- **`data/settings.json` holds API keys and is not tracked.** Neither is `data/resume/`,
  `data/bank.json` or `data/jobs.json`. Never commit any of them.
- **An application record is a curated dict, not a copy of the job.** A new field has to be
  listed explicitly in `add_application` or it is silently dropped.
- **`L-7` · a run script overwrote a 5,685-listing corpus.** Scratch scripts write to the
  scratchpad, never to the real data directory.
- **`M-5` · the résumé path was fixed at import time.** `resume.py` computed its folder from
  `storage.DATA_DIR` when imported — *before* the test harness moves storage somewhere
  temporary — so a test saving a résumé would have **replaced the one the user really uploaded**.
  Resolved on every call now, and Suite 4.40 checks it points inside the test folder.

---

### 11 · Saying what is happening

The Log is not decoration. Three separate faults in this project were invisible for hours
because a line said the wrong thing, said it in the wrong colour, or did not say it at all.

#### `O-7` · a source with no key was reported as broken

A deliberately unconfigured source showed as red **FAILED**, which trains you to ignore red
lines — the one thing the Log must never do. It is amber **"Switched off"** now, and the
pre-flight check returns the `off` list separately so the distinction survives the trip to the
UI.

**`remoteok`'s timeout was the same fault in a different hat**: a working source called broken
before nearly every search, because the ceiling was below its ordinary speed.

**`M-10` · a live test called a healthy source broken — RESOLVED, not a fault.** Same family:
the check was wrong, not the source.

#### `O-13` · 83 minutes of silence

The deep crawl opened **781 listing pages over 83 minutes without writing one line.** It was
working the whole time; there was no way to know that from outside, and the only other sign of
life — credit ticking down — stalls too while a batch waits for its run.

It reports after every batch now, **with the money spent in the line**, because that is the
number that decides whether to wait or stop:

```
Batch 3 of 8 done — 287 page(s) read so far, $1.14 spent on this stage.
```

#### `O-8` · the Health Check could not say what anything costs

And the user's correction on how to say it: *owner's note: state what a normal search of this kind costs* —
quote what a **normal search** costs, not a per-listing figure.

**An OK line can still carry something worth reading.** That detail used to be dropped on the
floor, which is why the budget lines arrived in the Log as two bare "OK"s.

#### `O-2` · the modules reported the opposite of what they did

A remote posting removed in a Not Remote search was logged as *"cannot be done from Turin"*. A
Log line that is wrong is worse than none: it sends you to look in the wrong place.

#### `C-1` · the reason existed and was thrown away

Covered in [area 6](#6--the-search-the-money-path) — the actor's own complaint names the field,
the value and the alternatives, and it went out as an indented grey line among hundreds of
progress ticks. Two hours of a German search ran without Indeed.

#### Details of the Log that came from the user asking

- **A live-ticking timer** on the combined Google call, which can take a minute or more. With
  only a summary line appearing once everything was done, **there was no way to tell the stage
  had started rather than the app being stuck.** The stop line always fires, even with zero
  results, so the timer never ticks forever.
- **Nested timers**: the Pre-API check ticks inside the outer Google header, so there is one
  continuous Google timer with a sub-timer underneath.
- **Startup boards get their own section**, visually separate from the general-purpose ones.
- **A check's suffix names what was checked, not how many passed** — the user's ask; pass/fail
  still decides the colour.
- **Any timer left running is stopped** when the phase ends abnormally.

#### One parsing detail worth keeping

A progress message is `name|status|reason|countries`, and **`reason` is a raw `str(e)` from a
failed probe — the only field that can contain a `|` of its own.** So it is `rsplit` for the
trailing field and `split` for the leading ones: a reason can never push its remainder into the
countries slot. Real requests/urllib3 messages do not currently contain one; **this makes it
structurally impossible rather than relying on that staying true.**

A failed probe's message can be **300+ characters** — a real DNS failure measured 310 — which
wraps across several visual lines. The dialog shows the whole thing; the Log line gets the
readable part.

---

### 12 · Cost and caching

#### What the cache key hashes, and why each part is there

```
the exact per-listing prompt text  (title, company, location, platform, type, level, description)
+ the prompt's own text, hashed    (so editing a rule invalidates every decision automatically)
+ the answer schema, hashed        (because the schema changes decisions, not just their shape)
+ the résumé's fingerprint         (so a verdict against one résumé is never reused for another)
```

**Anything that changes the text Claude is shown changes the key**, and a changed key means
every affected listing is screened again and paid for again.

#### The three faults the removal note caused, all found by following the data

> **1 · `rstrip()` broke the cache.** `set_drop_note` tidied the posting on the way past.
> `description` is hashed into the key, and **three of fourteen real German listings end in
> their own blank lines** (`"...Apply Now!\n\n"`), so the posting came back two characters
> shorter and three of fourteen missed the cache. No rstrip now, a fixed `\n\n` separator
> matched by the same string, and the round trip is exact to the character.
>
> Proven against the real ledger: pass one **$0.0252 in 5 calls**, pass two over the same
> listings **$0.0000 in 0 calls**.

> **2 · Excel's 32,767-character cell limit cut exactly the note.** The note goes on the *end*
> of the listing, which is right everywhere else and is precisely where Excel truncates. 4 of
> 8,133 real listings are longer — "Job searches for specialists" is 46,686 characters — so for
> those four **the reason a job was removed would be the one thing missing from the export.**
> `_description_for_export` moves it to the front of that one cell.

> **3 · `add_application` copies `description` into the record**, so a job the user kept by hand
> would be filed with "WHY THIS WAS REMOVED" attached. The note comes off in the same loop that
> records the override.

**None of these failed a test.** All three were found by opening the next file the data
reaches.

**The note is display text, never input.** It is stripped at the top of `reapply_filters`
before any rule reads a listing — that one line is what makes the feature safe. Left in,
"Rule 2 - Requires German C1" would be read next run as *the posting* demanding German.

#### `spend.summary()['total_usd']` is the lifetime total, not the run's cost

This was reported to the user as a run cost and was wrong: the Germany Claude run cost **$0.3465**,
not the $0.4097 quoted. The per-run figure is `current_run` / `last_run` in
`%APPDATA%\JobDesk\claude_spend.json`.

#### Prompt caching is what makes this affordable

The system prompt is thousands of tokens and **identical on every call** in the per-listing
loop; without `cache_control` it was billed in full for every single listing. Only the first
call per cache window pays full price. Every row in one Filter run carries the same Level and
is read against the same résumé, so the cache holds across the run.

#### The prices in the ledger

Batch is 0.5×, a cache write 1.25×, a cache read 0.1×. `record` never raises — a bookkeeping
error must not fail a search.

#### Two costs that were invisible until they were counted

- **Part two costs money too.** Counted only in the screening half, the Health Check reported a
  Berlin-sized filter at **$0.0183 and nothing at all** for the résumé match, which had read
  eight more listings.
- **A second Claude call for the employer name cost 23% more**, because 86% of listings arrive
  with no company and the pass therefore ran on nearly all of them. It rides along in the
  screening answer now.

#### Free is not free: `Jooble`'s 500

Its key is capped at **500 calls for the life of the account**. The pre-flight check does a
**config-only** check for Jooble — key present and correctly formatted, no network call — while
every other source gets a real minimal request. **Do not "make it consistent".** And the
`countries or COUNTRIES` bug spent 16 of them in one wrong run.

---

### 13 · The UI and the export

#### `M-9` · the Excel export wrote its rows one set of columns short

A new column has to be added in **five** places — `JOB_HEADERS`, the widths, the `ws.cell`
call, the `styled_columns` index sets *after* it, and the Applications sheet — and missing one
shifts every later cell silently.

> **`M-9` tried to happen twice while the Seniority column was added, and both near-misses
> are worth knowing.** In `jobs_page.py` two hard-coded `5`s were left over for Type —
> `setItem(row_idx, 5, badge)` and `setColumnWidth(5, 150)` — which the new column moved, so
> Seniority was about to be painted with Type's badge and given Type's width. And in the Excel
> job sheet every cell after Posted Date ended up one column out: the sheet printed `72%`
> under **Posted Date**, `Apply` under **Match %**, and the description under **Link**.
>
> Neither was caught by reading the diff. Both were caught by asserting each cell **by header
> name** — `cols = {n: i for i, n in enumerate(JOB_HEADERS, start=1)}` and then checking the
> value in `cols['Posted Date']`. Do that when touching either sheet; a test that indexes by
> number cannot see this class of bug at all, because the numbers are what moved.

#### `T-10` · the Seniority column — classified, never filtered

`Seniority` sits **before** `Type`, in both tables and both Excel sheets, because that is the
order the user groups by: *owner's note: group by Seniority first, then by Type*. Both have an
Excel-style `ColumnFilterButton` over them, and **neither is a filter in the Filter window any
more** — the choice lives in the table, where he can change it without re-running anything.

Where the value comes from, in order: `job['Seniority']`, written beside `Category` wherever
that is written; else `rules.seniority_of`, which prefers Claude's own `claude_seniority` and
falls back to the title. Reading it through `seniority_of` rather than off the row means a
listing banked before this column existed still shows a word instead of a blank.

Two deliberate choices in the cell itself:

- **A plain `QTableWidgetItem`, not a widget.** The render is already about ten objects per row
  and ~6 seconds for 2,500 rows; the per-row buttons are the only widgets that earn it.
- **`'Unspecified'` is the answer for silence, not a guess.** Type answers silence with
  `'Full-Time'` because that is the honest default for a contract. There is no honest default
  for seniority. On the real run **24 of the 26 clean listings were `Unspecified`** — which is
  information, not a gap: an advert that never claims to want five years has not closed the
  door.

Adding `'seniority'` to the application record broke the guard that says the by-hand dialog
must offer every field `add_application` reads. **That guard is why the dialog has a Seniority
control at all** — a record shape defined in two places drifts the first time one is changed,
and it earned its place again.

#### `T-13` · the `English?` column — the pairing, picked out in the table

The other half of `T-12`. Keeping the pairing is only useful if he can find it again:

> *owner's note: add columns to choose English only, or English plus another language; English first, in the same table, like Excel*

So the same reading that decides whether to delete also writes down **what it found**, and the
answer is a column with a `ColumnFilterButton` over it, like Seniority and Type. Tick
`English only` and nothing else shows. The values are offered most-common-first, so
`English only` sits at the top of the list by itself — it is the overwhelming majority.

`language.english_requirement_of` gives three answers, and `ENGLISH_NEED_ORDER` is the order
he reads them in:

| badge | what it means | colour |
|---|---|---|
| `English only` | nothing asks for a second language | green |
| `English + Other` | English named beside a language he lacks | amber |
| `Other only` | a language he lacks, English nowhere near | dark red |

**`English only` is also the answer for silence, and that is a decision, not a gap.** Most
adverts never mention language at all. Grouping those with the demands would be a guess, and
the tooltip says so in as many words rather than leaving him to infer it from the badge.

**`Other only` can only appear in a raw search.** Those are exactly the rows
`requires_language_besides_english` deletes, and the label is written in the same loop that
deletes them. The label is kept anyway, and the badge is coloured like what it is, because a
column with a value it can never display is how a column starts lying — and the raw search
table *does* show them, since a raw search keeps every listing exactly as fetched.

**The column and the rule cannot disagree**, by construction: same patterns, same three
cancellations, same window. `t8` asserts it over **169 generated texts** — every pair of
thirteen real phrasings — that `english_requirement_of(row) == 'Other only'` is true exactly
when `requires_language_besides_english(row)` is, plus that no fourth label can escape and
that no row survives the Filter wearing `Other only`. Two readings of one question drift; this
is what stops it.

##### `M-9`, for the third time

The column was inserted at **7**, which moved five constants in `jobs_page.py`
(`LANGUAGE_COLUMN` 7→8 through `REMOVE_COLUMN` 13→14 — and the Language column itself was
removed afterwards, see the column table in the Jobs page section) and, in the Excel job sheet, every cell
from Platform to Description one to the right — **the link moved for the second time**, 13→14,
having already moved 12→13 when Seniority was added. `styled_columns` is now `{4, 5, 6, 7, 14}`.

The five places, again: `JOB_HEADERS`, `JOB_COLUMN_WIDTHS`, the `ws.cell` calls, the
`styled_columns` set, and the Applications sheet. **The Applications sheet deliberately does
not get this column** — the user asked for Type there and nothing else, and `add_application`
never reads an `English` field, so adding it would widen the by-hand dialog's contract for no
one's benefit.

Caught by nothing except the assertions that read by header name — `_cols['English?'] == 7`
and `_cols['Link'] == 14` — which is the whole lesson of `M-9`: the numbers are what move.

#### Rendering cost, and two measurement artifacts worth knowing about

About **6 seconds for 2,500 rows**, which a search can now produce since the direct APIs were
paginated. Roughly ten objects go in per row — eight items plus two cell widgets and their
layout wrappers — and that is where the time goes.

> **Tried** · suspending painting around the fill.
> **What happened** · measured at **1.00×. No difference at all**, so it was removed rather
> than left in looking like an optimisation.
> **And two earlier readings were wrong**: they suggested a widget leak and a large speedup.
> Both were artifacts — **Qt defers widget deletion**, so counting or timing without first
> flushing `DeferredDelete` events sees the previous render still in memory. With the flush,
> the widget count is flat across renders and nothing leaks.
> **Now** · making this genuinely fast needs the per-row buttons to stop being real widgets,
> which is a redesign rather than a tweak.

#### Two real crashes in the UI layer

- **A second Search in the same session rewrote the first run's log lines in place** instead of
  appending, because it reused the log keys (`platform:Indeed`, `known_sites`, …).
  `LogPanel.reset_keys` exists for this.
- **`apify_token`, `limit_per_call` and `date_values` were read by direct index** while every
  other key used `.get()`. A `settings.json` written before one of them existed — or
  hand-edited, **which the Document actually tells you to do** to add Jooble/Reed keys — raised
  `KeyError` straight out of the click handler with **no dialog and no log line**. It points at
  the wizard now, which is the one place that can fix a missing token.

#### Things the user asked for that are load-bearing

- **The detected language is shown per listing**, not only in the Log's per-run summary. *"A
  listing that was judged in the wrong language is the kind of mistake that is invisible until
  you can see which language it was judged in."*
- **A `skip` from the résumé match deletes nothing** — it is flagged for the review dialog like
  any other verdict, because the cost of being wrong here is a job the user never sees.
- **Filter is cancellable now.** Its Claude Review step is one sequential API call per listing,
  so a big Filter used to be impossible to stop once started — the longest thing the app does.
- **The Log protocol is one table**, not a 286-line if/elif chain. Adding a message type is one
  line plus one method.
- **Every `GLOG:` one-shot line gets a unique key**, so it can never collide with and silently
  rewrite another.

> **The Status control was changed from an editable `QComboBox` back to a `QPushButton` +
> `QMenu`.** Centering the text via `setEditable(True)` plus a centered read-only `QLineEdit`
> looked right but **silently broke click-anywhere-to-open** — an editable combo only opens its
> popup from the small arrow. A button with a menu gets centered text for free and stays fully
> clickable.

> **The Excel export was changed from a folder picker to a Save-As dialog.**
> `getExistingDirectory` felt confusing — *"why does it insist on a folder, not a path?"*

---

### 14 · Packaging, the exe, icons, git

> **There were two `RoleHound.exe` files.** One in the project root, three weeks old, and one in
> `dist/`. The user was opening the root one — which is why a new icon and a night of fixes "had
> not changed anything". The root copy is deleted; **the exe is `dist/RoleHound.exe`.**

> **`Icon.png` and `Icon.ico` were two different images** — a brain and an unrelated document
> mark. Only `Icon.ico` is ever read (`RoleHound.spec` twice, `main.py` once), so editing the PNG
> changed nothing. They are generated from one source now.
>
> Windows will not take a PNG as an exe icon, and a single-size `.ico` is blurry in the
> taskbar: **seven sizes, 16 to 256.** A black icon vanishes on a dark taskbar, which is
> Windows 11's default — the mark sits on its own dark rounded square so it separates from
> whatever is behind it.

> **`RoleHound.spec` was not in the repository.** `*.spec` in `.gitignore` caught it, so **a
> fresh clone could not build the app at all** — the only build instruction was missing.
> `!RoleHound.spec` excepts the hand-written one; generated specs stay ignored.

> **`build/`, `dist/`, `RoleHound.exe`, `__pycache__`, `.venv` are gitignored on purpose** —
> GitHub refuses a single file over 100MB. That means they were **never pushed**, so deleting
> them is *not* recoverable from git; it is merely *reproducible*, which is a weaker promise.
> Say which one you mean.

> **`.venv` is 918MB and must not be deleted.** It is the only place PyInstaller and PySide6
> live. Without it neither the tests nor the build can run. `python` on this machine is **not**
> the project's Python: the system 3.8 has neither `lingua` nor PyInstaller.

> **Anything moved out of the repository loses its git history.** Before deleting a loose
> folder, prove its contents exist in some commit. `Vocabulary-Backup/before-title-filter/`
> held **seven files that matched no committed version of anything** — they would have been
> gone for good. Twenty-two of the other thirty were byte-identical to a committed version;
> only measuring told the two apart.

> **A `git show` comparison will report false differences on Windows.** Nine of thirty-two
> archived files "differed" from their pushed copies; all nine were **CRLF against LF**. Compare
> with line endings normalised before concluding anything is lost.

---

### 15 · How to work on this codebase

- **Write scripts with the Write tool, not shell heredocs.** PowerShell mangled backslashes and
  `\n` repeatedly; every time, the fix was to stop fighting the shell.
- **Scratch work goes in the scratchpad**, never in the project and never in the real data
  directory — `L-7` lost a 5,685-listing corpus that way.
- **`E-1` / `L-8` · a regex stored as a literal backspace.** `\b` in a non-raw string is a
  backspace character, and the pattern silently lost its word boundary. It happened **twice**,
  in two different files. Every file was checked afterwards. Use raw strings.
- **Read the generated diff.** `O-5`, the country-relabel fault and the Italian regression were
  all caught by printing the output of a change and reading it — none by reasoning about the
  code.
- **`O-10` · tests first when refactoring the expensive path.** Suite 7 was written around
  `run_search` *before* a line of it moved, because refactoring the least-tested and most
  costly path is exactly where a refactor does damage.
- **`O-11` · five more functions nobody could hold in their head**, split the same way. The
  point is not tidiness: a small function can be *tested individually*, so a fault is
  reproduced without standing up a whole search.
- **`tests/run_all.py` includes Suite 6, which spends real money** on real API calls, with a
  15-minute per-suite ceiling.
- **`T-11` · a suite that is not in `run_all.py`'s `SUITES` list does not exist.**
  `t8_invariants.py` — the metamorphic and combinatorial work written after the empty German
  search, the suite the user specifically asked for — was written, committed, and **never
  registered**. The campaign printed `ALL GREEN` for days without running a line of it. Found
  only by reading the runner while adding another suite.
  **When you add a suite, add the row, then check the printed total went up by the number of
  assertions you wrote.** The total is the only thing that proves the file was executed.
  The campaign is 10 suites and **3,167 assertions** as of 4 October 2026: t0 static, t1 rules,
  t2 sources, t3 storage, t4 pipeline, t5 UI/export, t7 run_search, t8 invariants, t9 the
  Claude quote guard (offline, see `T-9`), t10 the per-platform actor filters.
- **`| Select-Object` buffers too.** Same trap as `| tail` below, one layer up: a background
  PowerShell command piped into `Select-Object -Last N` writes **nothing** until it finishes,
  so the output file sits at zero bytes and looks hung. Redirect to a file inside the command
  and read the file.
- **Never let PowerShell touch a commit message.** `Set-Content -Encoding utf8` in PowerShell
  5.1 means *UTF-8 with BOM*, and the three bytes land in the commit **subject** — `git log
  --oneline` then shows an invisible `﻿` before the first word, forever. Worse, the same
  encoding bites in the other direction: `git log --format=%s | <python>` **adds** a BOM on the
  way through the pipe, so the obvious check reports the bug is still there after it is fixed.
  Write the message with the Write tool, pass `-F`, and verify with Bash or `od`, never through
  a PowerShell pipe.
- **Two copies of a test suite must never run at once.** They share `jobs.json` and the spend
  ledger's lock, and the second one waits forever on the first.
- **A slow suite is not always a hung one.** The Claude **Batches API** queues rather than
  answers, and `_BATCH_MAX_WAIT_SECONDS` is 24 hours because that is what Anthropic guarantees.
  Ask the API for the batch's status before concluding anything: on 23 September 2026 two
  batches sat `in_progress` for over 40 minutes while earlier ones had ended in seconds.
- **`| tail` hides progress.** A background command piped into `tail` writes nothing until it
  exits, so "zero bytes of output" means *not finished*, not *hung*. Write to a file and read
  the file.
- **A stuck process with 0 CPU and no TCP connections is not blocked on the network.** Check
  what it actually holds before theorising.

#### Three diagnoses in one evening that were wrong

Recorded because the pattern matters more than the cases: *"zero output means hung"*, *"it is
blocked on the network"*, *"two processes are fighting"* — all three were plausible, all three
were wrong, and the cause was found only by **asking the API what the batch was doing.** When a
theory is cheap to test, test it before acting on it.

---

---

### 16 · Signals we went looking for and could not get

#### LinkedIn's workplace badge (On-site / Hybrid / Remote)

LinkedIn's own job page shows a pill saying **On-site**, **Hybrid** or **Remote**. It is the
employer's own answer, chosen when the advert was posted, and it would settle every case the
keyword rules have to infer. The user saw it on a Boehringer Ingelheim advert the app had kept in
a Remote search and asked, reasonably, whether we could read it.

**We cannot.** Three routes, all checked against live data, twice — once weeks ago and again
on 23 September 2026, because a recorded finding is still only a claim about data:

| route | result |
|---|---|
| `curious_coder/linkedin-jobs-scraper` | returns 22 fields. `employmentType`, `seniorityLevel`, `jobFunction`, `industries` — **no workplace type** |
| the public job page, fetched with the app's own ladder | fetches fine, ~300KB. Its criteria list carries the **same four** fields and no workplace type |
| schema.org `JobPosting` JSON-LD in that page | 15 keys. No `jobLocationType`, no `TELECOMMUTE`, on any of three pages |

The pill is rendered only for a logged-in viewer. That is why the actor cannot see it either.

**A false positive was raised and retracted while checking this**, and it is worth recording
because it is rule 1 being broken by the person who had written rule 1 two hours earlier. A
first pass searched the page for the bare words and reported "the page says Remote". Reading
the markup around each hit:

```html
<li>Benefit from an on-site daycare in the building …      a crèche
<span class="sr-only">Senior Data Engineer … - Remote</span>   a DIFFERENT advert, in the sidebar
```

**Decision at the time: dropped, and this was the user's call.** His reasoning, and it was the
right one *for the evidence then*: the field would only ever reach us as inference from noisy
text, and that inference would feed a rule that *removes* listings. An unreliable signal driving
a removal is the one combination that loses real jobs silently.

> **OVERTURNED on 4 October 2026 (`T-16`) — read this before relying on the section above.**
> The three routes in the table were all routes into **one** actor or its page, and the
> conclusion that the field "cannot be gotten" was drawn from that. It can: the Apify store has
> 97 LinkedIn-jobs actors and `apimaestro/linkedin-jobs-scraper-api` returns `work_type` on
> every row (225 of 225 on real data), including the one advert whose own text said "Remote"
> and whose tag said Hybrid. It is **not** inference from noisy text — it is LinkedIn's own
> field — so the user's reasoning above is *satisfied*, not overruled: the signal is now reliable
> enough to drive a removal. The lesson: a negative result about a signal is a claim about the
> routes tried. Before writing "cannot get" here, try a different *source*, not just a
> different way into the same one.

The cost of not having it is measured, not assumed: **8 listings in 127** on the Germany run
say nothing at all about how the work is done. Claude marks those `check` rather than `apply`,
which is the honest outcome for a posting that genuinely does not say.

**If this is ever reopened**, the only thing worth trying is a different actor that runs with
a logged-in session. Do not re-check the three routes above; they have been checked twice.

---

---
---

## Quick start

1. Run `RoleHound.exe` (or `python main.py` from source).
2. On first launch the Job Search page is empty (nothing saved yet). Click **New Search**.
3. Fill in the [Setup Wizard](#the-setup-wizard--every-field) and click **Start Search**.
4. Watch the [Log panel](#the-log-panel) at the bottom — every step is reported live.
5. When it finishes, results appear in the table — **completely unfiltered**. Click
   **Filter** to actually apply all the cleanup rules (see
   [the two-phase model](#the-two-phase-model-raw-search-then-filter) below for why).

## The two-phase model: raw search, then Filter

This is the single most important thing to understand about how RoleHound works, and it
was a deliberate, explicit design change partway through development (see
[Design decisions](#design-decisions-and-things-that-were-tried-and-reverted)).

**Phase 1 — New Search (`pipeline.run_search`)**: fetches from Apify, tags each
listing's `Type` (Part-Time/Internship/Thesis/Full-Time/...), and sorts. It does
**not** dedupe, remove fakes, translate, or apply any of the opinion-based content
filters — every listing that was fetched is shown, completely as-is. (An earlier
version of this app *did* dedupe/remove-fakes/translate during Search itself — this was
deliberately moved out, see Phase 2 below and "Design decisions", so a raw Search
always shows literally everything Apify returned, untouched.)

**Phase 2 — Filter button (`pipeline.reapply_filters`)**: this is where ALL cleanup and
content filtering happens — company-name backfill, deduplication, fake-listing removal,
translation, the Remote/Seniority/Sponsorship/Unpaid/Language rules, the Claude review
pass, and Sponsorship Visa checking. Nothing from any of
this runs until you explicitly click **Filter** — see "Phase 2 — what the Filter button
does" further down for the full, current, exact 7-step breakdown. Since it's a single
function re-run from scratch on whatever's currently saved, it can be run repeatedly any
time a rule changes, cleaning up old saved data without a brand-new Apify search.

**The Bank (`storage.bank.json`)** is what makes that last sentence true. A search writes
everything it found into the Bank, and the Filter reads from there — not from `jobs.json`,
which holds what the *last* Filter kept. Before the Bank existed the first Filter overwrote
the pool with its own survivors, so trying another Level, or Remote instead of Not Remote,
meant paying Apify to search the same city again. Now the pool is written once per search
and only ever read: every Level and both work modes can be tried against it as often as you
like, for the price of the Claude calls alone. Re-searching a city adds only what is new
(the Bank is keyed by URL) and refreshes any posting whose description was just read.

Why split it this way: it lets you see exactly what Apify actually returned (useful for
debugging "why didn't X show up"), and it means changing a filter's keyword list only
requires clicking Filter again — never a fresh, slow, Apify-credit-costing search.

## The Setup Wizard — every field

Opened by the **New Search** button (`app/ui/setup_wizard.py`). Every field is
remembered in `settings.json` and pre-filled next time.

| Field | Purpose |
|---|---|
| **Apify API token** | Your Apify account token (`apify_api_...`). "Show token" checkbox toggles visibility. |
| **Anthropic API key** | Optional. `sk-ant-...`. Lets the **Filter** button ask Claude to double-check every survivor as a final pass (see below). Leave blank to skip this entirely. |
| **Résumé** | PDF or Word (`.docx`) only — judged by what is inside the file, not its name; anything else, an old `.doc` or a scanned PDF with no text is refused with the reason. Copied into the data folder (`resume/`, never committed) and its text read once; **Preview** shows exactly what Claude reads. Every fact about you in Claude's prompts comes from it, and part two scores each listing against it. Required when a Claude key is set. See `app/resume.py`. |
| **Job title** | One title, e.g. `Data Engineer`. Every query, every title check and Claude's Field line are built from it, with its twin form (`Data Engineer` ↔ `Data Engineering`). See `app/pipeline/search_title.py`. |
| **Type** | Exactly one: **Any**, Thesis or Internship (`T-19`). Any runs the job, internship and thesis passes and puts no seniority word in any query; Thesis and Internship run only theirs, in English first and then the country's own language. Stored as `search_level`; an old value (Junior…) opens as Any. The four job profiles in `app/pipeline/profiles/` still exist, keyed by the old levels, for the Filter. |
| **Work** | Remote — every rule as it always was. Not Remote — the same words read the other way: a role that says it is remote is dropped; on-site, hybrid and silent ones are kept. Each Level has a Not Remote prompt of its own (`prompt_not_remote.py`, and the `-Not-Remote.md` mirrors). |
| **Set a result limit per search** | If checked, caps results per actor call (spinner, 1–1000). If unchecked, defaults to 1000 (Apify's practical ceiling). |
| **How far back — LinkedIn / Indeed / Glassdoor** | Each platform has different underlying date filters: LinkedIn (Past 24 hours / Past week / Past month / Any time), Indeed (Last 1/3/7/14 days / Any time), Glassdoor (Last 1/3/7/14/30 days). |
| **Which platforms, and in what order?** | A drag-to-reorder, checkable list (Indeed, Glassdoor, LinkedIn by default, in that order). Uncheck to skip a platform entirely; drag to change the order actors are called in. |
| **Which countries** | Checklist of all 18 supported countries with Select all / Clear all. Only checked ones are searched. |

Clicking **Start Search** saves all of this to `settings.json` and immediately starts
Phase 1 (the raw, unfiltered fetch). Clicking **Save** instead (added next to Cancel/
Start Search) validates and saves the exact same settings to `settings.json` **without**
starting a search — useful for configuring things (e.g. picking countries/cities) ahead
of time, especially while low on Apify credits and not ready to spend any yet. Both
buttons share one validation/build method (`SetupWizard._build_result_settings`); which
one was clicked is tracked via `wizard.should_start_search`, checked by
`MainWindow.open_setup_wizard` after the dialog closes.

The wizard grew tall enough (token fields + date pickers + actor order + 18 countries)
that on shorter screens the Cancel/Save/Start Search buttons could be pushed off the
bottom of the dialog, unreachable. Fixed by putting everything **except** those buttons
inside a `QScrollArea`, while the button row lives outside it in the outer layout —
so the buttons are always pinned visible at the bottom and only the content above them
scrolls.

## Cancelling a search mid-run

A **"Cancel Search"** button appears next to the progress bar only while an actual
Search is running (not during Filter — `FilterWorker` has no cancel mechanism, so
`JobsPage.set_searching(is_searching, cancellable=...)` only shows the button when the
caller opts in; `start_search` passes `cancellable=True`, `handle_filter_existing`
doesn't). Clicking it calls `SearchWorker.request_cancel()`, which flips a flag checked
between actor calls (`should_cancel`).

**Important design point**: cancelling **shows whatever was already fetched**, exactly
like an unexpected mid-search error already did — it does not throw the results away.
Originally, `pipeline.SearchCancelled` was re-raised all the way out of `run_search`
when cancelled, meaning `SearchWorker` caught it and emitted a `cancelled` signal with
*no data at all*, discarding every listing fetched before the click. This was changed
so `run_search`'s outer `except SearchCancelled:` no longer re-raises — it now falls
through to the exact same partial-results post-processing (dedup/fake-removal/
categorize/sort) as the existing "unexpected error mid-search" path, just with a
different log message ("Search cancelled by you. Showing the N listing(s) found so
far."). Since `SearchCancelled` can no longer escape `run_search` at all, the
now-dead `SearchWorker.cancelled` signal and `MainWindow._on_search_cancelled` were
removed — a cancelled search now always finishes through the normal `finished_ok` path,
same as a completed one.

## City-level search

The three dedicated platform actors originally only supported **country-level**
location filters. Checking each actor's real input schema (via the Apify API, not
guessing) showed all three actually support a city directly:
- **LinkedIn** (`location` field): "City, region, or country as you would type it on
  LinkedIn" — e.g. `"Amsterdam, Netherlands"`.
- **Indeed**: has a `country` field (ISO2, required) **and a separate** `location`
  field ("City, state, zip code, or 'remote'") — city search sets both.
- **Glassdoor** (`location` field): "City, state, or country" directly.

So `CITIES = ['Amsterdam', 'Berlin', 'Vienna', 'Oslo', 'Copenhagen']` (`pipeline.py`)
are searched by **every enabled platform**, the same as `COUNTRIES` are — Indeed,
Glassdoor, and LinkedIn each loop over both `countries` and `cities` in `run_search`'s
`plan` (each entry is now `(platform, 'country'|'city', location)`, not just
`(platform, country)`). For a city, the resulting row's `country` field is still filled
in with the real country (via `CITY_COUNTRY`) for the Country column/Excel export/etc.
— only the actor's own search query targets the city specifically. LinkedIn's non-Italy
remote-only URL trick (`build_linkedin_remote_search_url`) is used for every city too,
same as any non-Italy country.

**Shown in the wizard as a tree** (`QTreeWidget`, `self.countries_tree`), one top-level
row per country, with the country's cities (if any) nested as checkable child rows
underneath it — built from `pipeline.COUNTRY_CITIES` (the reverse of `CITY_COUNTRY`,
grouped by country). Only 5 of the 18 countries currently have a city under them
(Netherlands→Amsterdam, Germany→Berlin, Austria→Vienna, Norway→Oslo,
Denmark→Copenhagen); the other 13 are plain leaf rows with no expand arrow.

**Country and city checkboxes are deliberately independent, not linked** — this was an
explicit requirement: checking a country searches the whole country; checking a city
underneath it searches *just* that city; checking both is valid (not mutually
exclusive) and simply runs both a country-wide and a city-specific search. There is
**no** auto-check-all-children-when-parent-checked and **no** tristate-parent-based-on-
children behavior, unlike a typical checkable tree — `_set_all_countries` (Select
all/Clear all) is the only thing that touches both levels at once, and even that just
sets every row (top-level and nested) to the same state independently, not through
propagation.

`_selected_countries()` reads only top-level item check states;
`_selected_cities()` walks every top-level item's children and collects the checked
ones — so a country's own checkbox never affects what counts as a "selected city" or
vice versa. Cities default to **none selected** (unlike countries, which default to
all) — city search is opt-in.

**Collapsed by default, click-to-expand**: a country with cities starts collapsed, not
showing its cities up front. Clicking anywhere on that country's row (not just the tiny
built-in expand arrow) toggles it open/closed, via `itemClicked` →
`_on_country_tree_item_clicked` (only acts on top-level items that actually have
children; clicking a city row, or a country with none, does nothing there). Collapsing
a country does **not** uncheck a city underneath it that was already checked — Qt tree
items keep their check state regardless of expand/collapse, verified with a scripted
test (check Oslo, collapse Norway, confirm Oslo is still checked and still returned by
`_selected_cities()`).

## The Google actor — and why it never touches LinkedIn/Indeed/Glassdoor results

A 4th, structurally different actor was added: **`apify/google-search-scraper`**
(a generic Google SERP scraper, not a job-board actor). It's **opt-in only** —
unchecked by default even for a fresh install, since it costs more per listing than the
other three — enabled by checking "Google (countries & cities) — extra cost per
listing" in the wizard's platform list. (**Real, stale-label bug fixed in a later
audit**: this checkbox used to say "Google (city search)", left over from before this
same session extended Google to also search full selected countries, not just cities —
misleadingly implying it only ever applied to cities.) Unlike the other three
platforms, it's called **once total per search**, not once per
country/city, since its `queries` input already covers every selected location in one
batch (`run_search`'s `plan` list explicitly skips `'google'` and handles it as a single
extra step after the main loop, via `run_google = 'google' in actor_order and
bool(cities or countries)`).

**Google now searches selected countries too, not just cities** — originally it only
ran for `cities`, but the user explicitly asked for country-level coverage as well, matching
how the other three platforms already work. For **every selected country and every
selected city**, `build_google_job_queries` builds queries in **this exact stage
order** (now 4 stages, not 3 — a Startup-sites stage was added this session, see
[Startup Websites Search & Company Popularity](#startup-websites-search--company-popularity)
below for its full detail):

1. **Known-sites stage** (1 query line) — the role terms + that location, restricted
   via `site:` OR-clauses to that country's curated list of major local job boards
   (`COUNTRY_JOB_SITES` — e.g. Norway → `finn.no`, `nav.no`, `karrierestart.no`;
   Germany → `arbeitsagentur.de`, `stepstone.de`, `xing.com`; 18 countries covered, each
   researched individually, excluding LinkedIn/Indeed/Glassdoor since those are the
   dedicated actors' job). Runs first, so the most reliable local sources are checked
   before anything else. A country with no `COUNTRY_JOB_SITES` entry just skips this
   stage.
2. **Startup-sites stage** (1 query line, only present for a country with a researched
   `COUNTRY_STARTUP_SITES` entry) — same role terms + location, restricted to that
   country's dedicated startup/scaleup job boards, plus the always-searched
   `GLOBAL_STARTUP_SITES`. Kept as its own stage (not merged into known-sites) so it
   gets its own "Startup Websites Search" section in the Log and its own `google_stage`
   tag, which the Type badge's "... Startup" suffix relies on directly — see
   [Startup Websites Search & Company Popularity](#startup-websites-search--company-popularity).
3. **Global-extra-sites stage** (1 query line *per group*) — same role terms +
   location, restricted via `site:` OR-clauses to a fixed list of sites the user supplied
   that aren't tied to any one country, so they're searched for *every* selected
   location the same way:
   `GOOGLE_GLOBAL_EXTRA_SITES = ['jooble.org', 'work.turing.com', 'work.mercor.com',
   'remoteok.com', 'weworkremotely.com', 'aijobs.net', 'wellfound.com',
   'workatastartup.com', 'remotive.com', 'arc.dev', 'aijobs.ai']`. `remoteok.com`,
   `weworkremotely.com`, `wellfound.com` (major remote-focused boards) and `aijobs.net`
   (AI/ML/Data-specific) were added first, after the user asked whether any major job boards
   were still missing — none of the sites covered so far were remote-first the way this
   app's own Remote-only rule requires. The last 4 (`workatastartup.com` — Y Combinator's
   own board, YC-backed startups only; `remotive.com` — hand-curated remote board with a
   dedicated engineering/data/AI vertical; `arc.dev` — remote-first, stack-based matching
   for engineers; `aijobs.ai` — AI/ML/data-specific, a distinct site from `aijobs.net`)
   were added after a broader research pass specifically looking for any other
   genuinely-good sites still missing, confirmed real/active and non-redundant with
   what was already there. Runs second — after a location's own local job boards,
   before the open web.
   (`ziprecruiter.com` was tried here too, but it turned out to be genuinely
   US/Canada/UK-focused rather than global, so it went back to being a plain
   `United States` entry in `COUNTRY_JOB_SITES` instead — it must stay out of
   `GOOGLE_GLOBAL_EXTRA_SITES`, since the US's own known-sites-stage query would then
   contain that domain too, and `_google_query_stage`'s substring check would wrongly
   classify it as the global stage.)
   **No longer capped by one line's word budget**: growing this list once pushed the
   worst case (a 2-word location like "United Kingdom") right up against Google's
   ~32-word query limit. Rather than keep trimming role terms to make room, the user asked
   for the list itself to be split: `_global_extra_sites_clauses()` breaks
   `GOOGLE_GLOBAL_EXTRA_SITES` into groups of `GOOGLE_GLOBAL_SITES_PER_GROUP` sites,
   and `add_location` emits **one query line per group** instead of one line for the
   whole list. **Currently 1 line for all 8 sites** — `GOOGLE_GLOBAL_SITES_PER_GROUP`
   was raised from 6 to 8 in a later cost-optimization round, once
   `GOOGLE_GLOBAL_EXTRA_SITES` itself shrank to exactly 8 domains (`remotive.com`/
   `remoteok.com` removed — see "Removed for cost" below): merging what used to be 2
   lines into 1 cuts one whole billed query-page-batch per location, for every real
   search, at **zero coverage loss** — same 8 domains, just one line instead of two.
   Verified with a real word-count check across all 18 countries and 5 cities:
   worst case (`"United Kingdom"`) is 30 words, safely under the ~32-word limit; a
   9th domain would land at exactly 32 (the wire), a 10th would exceed it — so 8 is
   the precise right group size, not padded higher, letting a genuine future 9th
   global site still correctly split into its own new line automatically instead of
   silently risking the query limit.
   `_google_query_stage`'s `'global'`-stage detection (any `GOOGLE_GLOBAL_EXTRA_SITES`
   domain appearing in the query text) already works unchanged across multiple lines,
   since each group's line still contains real entries from the list. This means the
   global-sites list can now grow indefinitely (each new group just adds one more query
   line, at the cost of one more Apify query, not by tightening every line's word
   budget) — worst case across every country/city is 27 words (the open-web stage,
   unaffected by any of this), with the widest known-sites-stage line (Germany, now 7
   domains) also at 27. Also freed up room in `GOOGLE_QUERY_ROLE_TERMS`: The user had
   earlier traded off `"Data Analyst"` (5 terms → 4: `Data Scientist`, `Data Engineer`,
   `Machine Learning Engineer`, `AI Engineer`) purely to survive the old single-line
   squeeze — that trim stayed (no reason to revert it), but a future 5th role term would
   no longer be blocked by the global-sites list specifically. Separately, the user also
   trimmed analytics/analyst-flavored terms out of `KEYWORDS` (the much longer,
   unrelated term list used by the LinkedIn/Indeed/Glassdoor actors) entirely — see "The
   search keywords (`KEYWORDS`)" below.
4. **Open-web stage** (1 query line) — same role terms + location, no site restriction
   beyond the usual LinkedIn/Indeed/Glassdoor exclusion (`GOOGLE_EXCLUDED_TLD_HINTS`) —
   catches a company's own career page or any other job board not in the known-sites,
   startup-sites, or global-extra-sites lists (The user's own reasoning: "a specific company
   from that country might have posted a job on its own website that matches our
   search").

A **city** always reuses its **parent country's** known-sites and startup-sites lists
(via `CITY_COUNTRY`) for stages 1 and 2, but with the city name as the actual search
location for all four stages — so selecting only Oslo (not Norway) still searches
Norway's known and startup job boards, just scoped to Oslo specifically, followed by the
global-extra-sites and open-web searches scoped to Oslo. Selecting both Norway and Oslo
runs every applicable query for both (country stages, city stages) — the two are
independent, as already covered above.

`_google_query_stage(term)` classifies which stage a result's originating query came
from — `'open'` if it contains `-site:` (the open-web stage's only distinguishing
marker), else `'global'` if it contains one of the `GOOGLE_GLOBAL_EXTRA_SITES` domains
verbatim, else `'startup'` if it contains one of `GLOBAL_STARTUP_SITES` or any
`COUNTRY_STARTUP_SITES` value, else `'known'`. This only works because
`COUNTRY_JOB_SITES`, `COUNTRY_STARTUP_SITES`, and `GOOGLE_GLOBAL_EXTRA_SITES` are all
kept pairwise disjoint (see the `ziprecruiter.com` note above, and the `wellfound.com`
note in [Startup Websites Search & Company Popularity](#startup-websites-search--company-popularity))
— if a country's known-sites clause and the global or startup clause ever shared a
domain again, a known-sites-stage query for that country would wrongly classify as
`'global'`/`'startup'` too, since the check is a plain substring match. This
disjointness now matters for more than just query counting: the Type badge (see above)
trusts `google_stage == 'startup'` to append `"Startup"` with **no** verification at
all, so a shared domain here would silently mislabel whatever company that domain's
listings belong to.

With every country's default of "all selected" plus a city checked, this scales up
fast: 18 countries + 5 cities = 23 locations × up to 4 query lines each (1 known-sites,
for a country/city with a `COUNTRY_JOB_SITES` entry + 1 startup-sites, for one with a
`COUNTRY_STARTUP_SITES` entry + 1 global-sites — merged into a single line at the
current 8-site `GOOGLE_GLOBAL_EXTRA_SITES` length, see "Later reduced to 1 line" above
+ 1 open-web) — verified to individually stay under the ~32-word limit, 30 words max
across every real country/city, see the word-budget note above. This grows by one more
global-sites line only once `GOOGLE_GLOBAL_EXTRA_SITES` grows past
`GOOGLE_GLOBAL_SITES_PER_GROUP` (8) sites, and independently by however many
`known`/`startup` sites a given country's own `COUNTRY_JOB_SITES`/
`COUNTRY_STARTUP_SITES` entry has grown to (still just 1 line per country per stage
regardless of count — see the word-budget note). This is a real cost consideration
The user was explicitly told about before building it, and confirmed he understood and
wanted anyway — since then, a real cost audit (see "Removed for cost" and the
`GOOGLE_GLOBAL_SITES_PER_GROUP` note above) has trimmed this down considerably: fewer
`COUNTRY_JOB_SITES` entries (5 domains removed to their free-API-only equivalents),
one fewer global-sites line per location, and the app-side LinkedIn/Indeed/Glassdoor
exclusion restored to its full guarantee (see "Real gap found and fixed" further
below).

Location attribution for results uses `_location_from_search_term` (replacing the
earlier city-only `_city_from_search_term`) — it checks the originating query's
`searchQuery.term` text for a known city name first, then a known country name, and
`normalize_google_search_result` fills in `location`/`country` accordingly: a
country-level result gets `location=None, country=<that country>`; a city-level result
gets `location=<city>, country=<its parent country>` (unchanged from before).

**Google is explicitly told to never return LinkedIn/Indeed/Glassdoor results at all.**
Since those three sites are already searched directly (and more reliably — structured
fields, guaranteed full JD) by their own dedicated actors above, for both countries and
cities, having Google also surface listings from those same three domains would only
mean reprocessing the same jobs through a worse, unstructured path. So:
- Every open-web-stage query built by `build_google_job_queries` includes 12 `-site:`
  exclusions (`GOOGLE_EXCLUDED_TLD_HINTS` — `linkedin.com`; `indeed.com`, `.co.uk`,
  `.ca`, `.com.au`, `.ie`; `glassdoor.com`, `.ca`, `.co.uk`, `.de`, `.com.au`, `.ie`) —
  30 words max per query, verified under the ~32-word limit. This is **best-effort cost
  reduction only**: it stops the most common domains for the countries/cities this app
  actually searches from ever being scraped/billed, but Indeed and Glassdoor both have
  more country-specific domains than could ever fit in one query — Google's `site:`
  operator needs one exact domain per entry. (The known-sites-stage queries don't need
  this at all — restricting to a specific whitelist of non-big-3 domains via `site:`
  inclusion already can't return a LinkedIn/Indeed/Glassdoor result.)
- **The actual guarantee is app-side, not query-side**: `run_search`'s Google-processing
  loop checks every result's URL with `_is_excluded_job_board`, which matches the bare
  brand keyword (`'linkedin'`, `'indeed'`, `'glassdoor'` — `GOOGLE_EXCLUDED_JOB_BOARDS`)
  as a substring, not an exact `.com` domain. **This was proven necessary, not just
  theoretical**: a real test search for Oslo returned a result from
  `glassdoor.ca` — the Canadian domain — which an earlier version of this filter (exact
  `.com`-domain matching) let straight through. With the substring-based check, that
  same URL is correctly caught regardless of TLD, subdomain, or country code. Any
  skipped count is logged (`"Skipped N result(s) from LinkedIn/Indeed/Glassdoor
  (already covered by their own actors)."`).
- Google is now only meant to surface company career pages and other job boards outside
  the big three.

**Real gap found and fixed (this app-side check was removed, then restored)**: at one
point this exact check was removed from the main loop entirely, with the reasoning
"just let every Google result through and let Filter's own dedup
(`_remove_duplicates_list`) collapse it against whatever the dedicated actor already
found" — simpler, and it does catch cases the query-level `-site:` exclusion alone
can't (any URL shape, not just a known TLD). But that reasoning had a real hole: a
Google-scraped LinkedIn/Indeed/Glassdoor row very often has no extractable `company`
at all (Google never returns one, and `_extract_company_from_text`'s deliberately
conservative regex frequently can't recover it from these sites' own title formats),
which disqualifies it from Filter's company+title fuzzy match entirely — leaving only
an exact-URL match as a safety net, not guaranteed if Google indexed a
differently-formatted URL (tracking params, a different path) than the dedicated
actor's own output. A real duplicate could silently survive Filter as an extra,
lower-quality row sitting alongside the dedicated actor's cleaner one. The user asked for
this fixed once the gap was explained — `_is_excluded_job_board` (already proven,
substring-based, catches any TLD/subdomain) is back in the main loop as the real
app-side guarantee it was always meant to be, verified with a real simulated-loop test
(a `glassdoor.ca` result, among others, correctly excluded while a legitimate
`finn.no` result in the same batch survives) and confirmed the restored
`"Skipped N result(s)..."` log line renders correctly, nested under the Google
section.

## Deep-crawling known job boards (`_deepen_google_results`)

A known-sites-stage (or, since the global-extra-sites stage was added, a
global-extra-sites-stage) result — e.g. finn.no's own search page, or
ziprecruiter.com's — is often itself a *listing* of several jobs, not one job's actual
page — Google's scrape of it only captures whatever text is on that listing page, not
the individual postings behind it. The user explicitly asked whether the individual links
on such a page could be opened too, so this was built, tested for real multiple times,
and iterated based on what actually worked.

**What was tried and found not to work, in order:**
1. Deep-crawling *every* Google result (any stage), any domain, no restriction — tested
   against a generic aggregator site (devjobsscanner.com) for real. Of 113 new pages
   found, over 100 were noise (other countries' listing pages on the same site, category
   pages, company profile pages, a Discord invite, an ad-tracking link); the handful of
   genuinely individual job pages found were in completely unrelated cities (Palo Alto,
   Cleveland, Cincinnati — while searching for Oslo). **Dropped entirely** — restricted
   to known-sites-stage and global-extra-sites-stage results only from here on (never
   the open-web stage).
2. Same-domain-only crawling (the actor's default, no extra config) on finn.no's own
   search results page — found **zero** new pages, even on a real, major job board.
3. Investigating why: fetched finn.no's raw HTML directly and found the actor's default
   content extraction (Mozilla's Readability) was picking the **category filter
   sidebar** as "main content" instead of the actual job listings — the real job links
   were never even being looked at.
4. Setting `htmlTransformer: 'none'` (keep raw HTML, skip Readability's guess) — found
   40 real job links (`finn.no/job/ad/{id}`) in the raw HTML, but same-domain
   auto-crawling *still* didn't follow them without also being told the exact pattern.
5. Adding an explicit `includeUrlGlobs: ['https://www.finn.no/job/ad/**']` on top of
   `htmlTransformer: 'none'` — **this worked**: 16 real individual job pages found, each
   7,000–22,000 characters of full JD text, verified by reading one in full (a real
   "Senior Data Plattform Utvikler" posting at TET Digital AS, Oslo).

**Final design**: `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` (`pipeline.py`) maps each known
job-board domain to the URL glob pattern its individual job postings actually follow —
discovered one domain at a time via real live tests (fetch a real search-results page
with `htmlTransformer: 'none'`, inspect the raw HTML for real `<a href>` links). Only
domains with a confirmed entry get deep-crawled at all; `_deepen_google_results` skips
the crawler call entirely if none of a run's known-sites-stage or global-extra-sites-
stage results are on a recognized domain (no wasted cost). Domains tested and confirmed
as of this writing:

| Domain | Pattern |
|---|---|
| finn.no (Norway) | `/job/ad/**` |
| arbeidsplassen.nav.no (Norway) | `/stillinger/stilling/**` |
| jobindex.dk (Denmark) | `/vis-job/**` |
| arbeitsagentur.de (Germany) | `/jobsuche/jobdetail/**` |
| stepstone.de (Germany) | `/stellenangebote--**` |
| karriere.at (Austria) | `/jobs/**` |
| stepstone.at (Austria) | `/stellenangebote--**` |
| hellowork.com (France) | `/fr-fr/emplois/**` |
| jobs.ch (Switzerland) | `/en/vacancies/detail/**` |
| infojobs.net (Spain) | `/**/of-i**` |
| reed.co.uk (UK) | `/jobs/**` |
| jobbank.gc.ca (Canada) | `/jobsearch/jobposting/**` |
| seek.com.au (Australia) | `/job/**` |
| dice.com (US) | `/job-detail/**` |
| net-empregos.com (Portugal) | `/[0-9]**` |
| xing.com (Germany) | `/jobs/*` |
| totaljobs.com (UK) | `/job/**` |
| cv-library.co.uk (UK) | `/job/**` |
| jora.com (Australia) | `/job/**` (on `au.jora.com`) |
| francetravail.fr (France) | `/offres/recherche/detail/**` (on `candidat.francetravail.fr`) |
| jobup.ch (Switzerland) | `/en/jobs/detail/**` |
| apec.fr (France) | `/candidat/recherche-emploi.html/emploi/detail-offre/**` |
| vdab.be (Belgium) | `/vindeenjob/vacatures/**` |
| arbetsformedlingen.se (Sweden) | `/platsbanken/annonser/**` |
| actiris.brussels (Belgium) | `/fr/citoyens/detail-offre-d-emploi/**` |
| moovijob.com (Luxembourg) | `/job-offers/**` (on `en.moovijob.com`) |
| tecnoempleo.com (Spain) | `/*/*/rf-**` |
| cwjobs.co.uk (United Kingdom) | `/job/**` |
| app.welcometothejungle.com (France, Germany, Netherlands, Spain, United Kingdom, United States, Canada) | `/jobs/**` |
| workatastartup.com (global) | `/jobs/**` |
| remotive.com (global) | `/remote/jobs/**` |
| arc.dev (global) | `/remote-jobs/details/**` (+ `/*/remote-jobs/details/**` for localized variants) |
| aijobs.ai (global) | `/job/**` |
| itjobs.pt (Portugal) | `/oferta/**` |
| swissdevjobs.ch (Switzerland) | `/jobs/**` + `/de/jobs/**` (bilingual) |
| jobly.fi (Finland) | `/tyopaikka/**` (Finnish) + `/en/job/**` (English) |
| it-jobbank.dk (Denmark) | `/jobannonce/**` |
| builtin.com (United States) | `/job/**` |
| europa.eu — EURES (14 EU/EEA+Switzerland countries) | `/eures/portal/jv-se/jv-details/**` |
| wearedevelopers.com (Germany, Austria, Switzerland, United Kingdom) | `/jobs/ext/**` |
| iamexpat.de (Germany) | `/career/jobs-germany/**` |
| iamexpat.nl (Netherlands) | `/career/jobs-netherlands/**` |

**39 of the 55 unique domains in `COUNTRY_JOB_SITES` confirmed** (77 total entries,
since `app.welcometothejungle.com`, `europa.eu`, and `wearedevelopers.com` each repeat
across several countries — see the notes above `COUNTRY_JOB_SITES` itself). The last 4
of the original 42 (`vdab.be`, `arbetsformedlingen.se`, `actiris.brussels`,
`moovijob.com`) were originally guessed wrong and marked failed, then fixed in a second
pass using real web search results to find each site's actual search URL format instead
of guessing blindly (`actiris.be` was also renamed to its real domain,
`actiris.brussels`, in `COUNTRY_JOB_SITES` itself). `tecnoempleo.com` and `cwjobs.co.uk`
were added later, after the user asked whether any good startup/tech-specific boards were
still missing for individual countries — both were researched and confirmed via real,
live job-posting URLs on the first attempt (Tecnoempleo: Spain-specific tech board;
CWJobs: UK-specific tech board, part of the StepStone/Totaljobs group).

**A further batch of domains was added after a broad "what good sites are still
missing" research pass**, covering per-country gaps and multi-country sources
(`itjobs.pt`, `swissdevjobs.ch`, `jobly.fi`, `it-jobbank.dk`, `builtin.com`,
`europa.eu`/EURES, `wearedevelopers.com`, `iamexpat.de`, `iamexpat.nl`), and a **second
research pass confirmed real job-URL patterns for every one of them** on the first
attempt — all included in the table above. One of them needed a real domain correction
along the way, not just a URL pattern:
- **EURES**: initially added as `eures.europa.eu` (its own informational/CMS site,
  confirmed active), but real research found its actual job vacancy search and detail
  pages are hosted on the *separate* `europa.eu` domain under `/eures/portal/jv-se/**` —
  a `site:eures.europa.eu` clause would never have matched a real job posting at all.
  Corrected to `europa.eu` in `COUNTRY_JOB_SITES` before this was ever shipped.

Also deliberately **not** added, from the earlier gap-analysis research: `DataTeams.ai`
(redundant with `aijobs.net`/`aijobs.ai`, which were already added to
`GOOGLE_GLOBAL_EXTRA_SITES`), `AAAI Career Center` (too academic/research-focused for
this app's industry-role focus), `Yourfirm.at` (general-business rather than
tech-specific, weak fit), `Adzuna` (a real, good aggregator, but its actual domains are
per-country TLDs like `adzuna.co.uk` vs `adzuna.de` vs `adzuna.com` — the same multi-TLD
problem `GOOGLE_EXCLUDED_TLD_HINTS` exists to solve for Indeed/Glassdoor exclusion,
needing its own design rather than a one-line add), `Honeypot.io` (a 2024 report said it
would shut down by year-end; current status too ambiguous to rely on), and two sites
confirmed dead in the same research pass and never added at all: Sweden's Blocket Jobb
(closed December 2024) and Finland's Oikotie Työpaikat (closed February 2025, `jobly.fi`
above is its live replacement).

**`GOOGLE_GLOBAL_EXTRA_SITES` confirmed-pattern coverage**: after the user asked to go
through the remaining unconfirmed ones directly rather than waiting for real usage to
surface them, a real Playwright fetch of each (not a guess) settled all 7 that were
originally left unresearched:
- **Confirmed and fixed** — `remoteok.com` (`/remote-jobs/{slug}-{id}`), `aijobs.net`
  (`/job/{slug}-{id}/` — note the singular "job", unlike `aijobs.ai`'s plural path),
  and `wellfound.com` (`/jobs/{id}-{slug}`) all returned real job cards with these
  patterns on the first real fetch; added to `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS`.
  (`wellfound.com`'s own support docs warn against hand-constructing its *search* URLs
  — irrelevant here, since this dict only recognizes real links Google's index already
  found, never builds a search URL of its own.)
- **Confirmed actively blocked, not just unconfirmed** — `weworkremotely.com` served a
  Cloudflare bot-challenge page instead of real content to a real Playwright-driven
  Chrome fetch (not even a headless-detection issue — the same browser channel that
  worked fine everywhere else got walled here specifically). Left with no pattern, same
  as `jooble.org`. (`ziprecruiter.com`, a separate `COUNTRY_JOB_SITES['United States']`
  entry rather than a global site, hit the identical Cloudflare wall in the same test
  session — see its own note further up.)
- **`work.turing.com` and `work.mercor.com` were marked "no public listing at all" here
  — this turned out to be wrong**, corrected in the manual-assisted-search round below
  once the user actually opened both himself: both have a real, public, no-login search.
  Still no entry in this specific dict, though, for an unrelated reason — their role
  cards have no real `<a href>` for `_deepen_google_results` to follow at all (a
  different failure mode than "no listing"), so they're handled entirely through
  `MANUAL_ASSIST_GLOBAL_SITES` instead. See "Manual-assisted search, round 2" below for
  what was actually found.
- `workatastartup.com`, `remotive.com`, `arc.dev`, and `aijobs.ai` already had a
  confirmed pattern from the original research pass. `jooble.org`'s own job-URL pattern
  *was* researched and confirmed too — real, live testing of the direct-search feature
  below found Apify's own crawler infrastructure gets blocked by the site entirely,
  unrelated to whether the pattern itself is correct, so its
  `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` entry was removed again rather than kept as dead
  weight.

That's all 11 `GOOGLE_GLOBAL_EXTRA_SITES` domains settled one way or another for this
specific dict (which only ever helps `_deepen_google_results`, Apify's cloud-hosted
crawl): 7 with a confirmed pattern, 4 with none for `_deepen_google_results` purposes
specifically (`jooble.org` — crawler-infra blocking despite a correct pattern;
`weworkremotely.com` — active Cloudflare blocking, headless-specific as it turned out;
`work.turing.com`/`work.mercor.com` — no real `<a href>` on their role cards at all).
Three of those four (all but `ziprecruiter.com`-style pure blocks) later got real
coverage anyway, just through a different mechanism — see "Manual-assisted search"
below.

## Direct site search — bypassing Google's location matching entirely

The user pushed back hard on the "embed the city name as plain text in a Google query"
mechanism described above: a genuinely relevant listing on a real job board might never
literally contain the city name at all (a "Remote" posting usually doesn't name an
exact city), and — a real, live test proved the opposite failure too — Google's
full-text index can also be fooled into matching the *wrong* place entirely. Searching
`jooble.org/SearchResult?rgns=Oslo` on Jooble's global/US domain returned real jobs in
**Oslo, Minnesota**, not Oslo, Norway — the identical-looking query string means
something completely different depending on which of Jooble's country subdomains it's
run against.

**The fix the user asked for**: wherever a real, structured location-search mechanism could
be confirmed for a specific site — not Google guessing from indexed text, but a URL
parameter, path segment, or subdomain the site itself uses internally to filter its own
results — build that URL directly and crawl it, instead of ever routing that site
through Google's `site:` + location-text approach.

**This is purely additive.** The existing known-sites/global-sites/open-web Google
stages described above are completely unchanged and still run exactly as before; direct
site search is a new step, `_run_direct_site_searches`, that runs after them (still
inside the same Google actor-order step) and just adds whatever real job pages it finds
on top. A real result found this way can only add coverage, never remove anything
Google already found — this was a deliberate design choice specifically so this large
change couldn't regress anything already working.

### The research: 66 domains checked

Every domain in `COUNTRY_JOB_SITES` (55 unique) and `GOOGLE_GLOBAL_EXTRA_SITES` (11)
was researched for a real, verifiable location mechanism (5 parallel research passes,
following up on the Jooble discovery). Results fell into four groups:

1. **Genuinely usable, HTML search pages a crawler can follow** — the ~29 domains that
   initially became `DIRECT_SEARCH_URL_BUILDERS` entries at this research stage (see
   the code comment above that dict for the full reasoning and every domain's URL
   template): `finn.no`, `arbeidsplassen.nav.no`, `jobindex.dk`, `it-jobbank.dk`,
   `duunitori.fi`, `karriere.at`, `stepstone.at`, `stepstone.de`, `xing.com`,
   `iamexpat.de`, `iamexpat.nl`, `moovijob.com`, `jobs.ch`, `jobup.ch`,
   `swissdevjobs.ch`, `itjobs.pt`, `tecnoempleo.com`, `apec.fr`, `hellowork.com`,
   `reed.co.uk`, `totaljobs.com`, `cv-library.co.uk`, `cwjobs.co.uk`,
   `wearedevelopers.com`, `dice.com`, `ziprecruiter.com`, `jobbank.gc.ca`,
   `seek.com.au`, `careerone.com.au`, `jora.com`, plus the two
   global sites `jooble.org` and `arc.dev`. **Four of these (`duunitori.fi`,
   `jooble.org`, `seek.com.au`, `careerone.com.au`) were later removed after real, live
   testing found Apify's own crawler infrastructure gets blocked by each of them
   entirely** — see "Real, live testing" below; a domain having a real, confirmed URL
   mechanism doesn't guarantee Apify can actually reach it. `apec.fr` and
   `swissdevjobs.ch` also lost their country-wide search (both had a guessed URL that
   turned out not to exist/redirect to a login wall), while keeping their confirmed
   job-URL patterns for whenever a real match is found another way.
2. **A real mechanism exists, but it's a JSON REST API, not an HTML page**
   (`arbeitsagentur.de`, `arbetsformedlingen.se`, `francetravail.fr`) — a crawler can't
   extract `<a href>` links from a JSON response, so using these properly needs a
   separate HTTP+JSON integration. **Two of the three were built** (see "Direct JSON API
   integrations" below) — `arbetsformedlingen.se` (Sweden) and `arbeitsagentur.de`
   (Germany) both turned out to need no registration at all; `francetravail.fr` still
   requires registered credentials RoleHound doesn't have, so it's left on the
   Google-only path.
3. **No real mechanism found at all** — JS-rendered SPAs with no discoverable URL
   parameter (`werk.nl`, `nationalevacaturebank.nl`, `app.welcometothejungle.com`,
   `vdab.be`, `jobat.be`, `leforem.be`, `jobnet.dk`, `empleate.gob.es`), login-gated even
   for search (`adem.public.lu`), form-only with an unconfirmed resulting query string
   (`eluta.ca`), or genuine "traps" the research explicitly flagged as unsafe to
   hand-construct: `wellfound.com`'s own support docs say not to build its URLs
   directly. (`work.turing.com`/`work.mercor.com` were placed in this category too at
   this stage of the research — wrong, as a much later real test found; see
   "Manual-assisted search, round 2" further down for the correction.) `aijobs.ai`'s
   city-looking URL path
   (`/job-location-category/{city}-{country}`) was tested live and confirmed to
   silently return country-wide results regardless of the city named in the URL —
   exactly the same failure mode as Jooble's wrong-subdomain trap, just with no correct
   version to fall back to.
4. **A real mechanism exists but with no confirmed way to add a keyword/role search on
   top of it** — `net-empregos.com` and `sapoemprego.pt` have a confirmed *location*
   parameter, but no confirmed way to combine it with a role search; `europa.eu` (EURES)
   needs a country/NUTS-region code lookup table for anything beyond a bare country,
   plus its detail pages are JS-rendered. (`infojobs.net` was originally grouped here
   too, but a later pass found this was never actually the limiting problem — Spain has
   no defined city in `CITIES`, so a location parameter was never useful to begin with;
   what was actually missing was a plain keyword search, and a real fetch found one —
   see the unresolved-sites pass below.)

### Known traps avoided

Two specific "looks right but silently returns the wrong place" failures were found and
deliberately avoided (beyond the aijobs.ai one above):
- **`builtin.com/jobs/{city}`** looked like a clean per-city URL, but a real test
  (`/jobs/new-york`) returned mostly German/Berlin/Munich listings, not NYC ones — the
  actually-correct mechanism is builtin's separate city subdomains (`builtinnyc.com`,
  `builtinchicago.org`, etc.). Since none of `builtin.com`'s country (United States) has
  a defined city in this app's `CITIES` list, this trap never actually gets triggered in
  practice — `builtin.com` has no `DIRECT_SEARCH_URL_BUILDERS` entry at all, so it stays
  on the Google-only path.
- **`jobbank.gc.ca`**'s plain city-name query params (`locationstring=`/`locationparam=`)
  looked plausible but silently ignored the filter in testing — only an opaque numeric
  `mid=` location ID actually scopes results, and there's no public mapping from city
  name to that ID. Since Canada also has no defined city in `CITIES`, `jobbank.gc.ca`'s
  builder only ever does a plain keyword search with no location parameter at all
  (`?searchstring=Data+Scientist`) — country-wide, which needs no location ID to begin
  with, sidestepping the trap entirely rather than working around it.
- **`jooble.org` itself**, the original discovery that started all of this — its country
  subdomains (`no.jooble.org`, `de.jooble.org`, etc.) were confirmed correct for Norway
  at this research stage, with the other 17 countries planned to reuse the existing
  `COUNTRY_ISO2` mapping as a reasonable inference. This URL construction was never the
  problem, though — real testing afterward found Apify's crawler infrastructure gets
  actively blocked by jooble.org regardless of the URL. See "Real, live testing" below
  for what actually happened to `jooble.org`'s entry.

### The safety net: what happens when a URL guess is wrong (or a site changes)

Not every URL in `DIRECT_SEARCH_URL_BUILDERS` was verified at the *exact* combination
RoleHound needs (many are inferred from a confirmed pattern seen on a different city on
the same site, applied here to Oslo/Berlin/Vienna/Amsterdam/Copenhagen) — and any site,
confirmed or not, can silently change its URL format at any time in the future. The user
explicitly asked for this to never fail silently: `_run_direct_site_searches` tracks,
per constructed URL, whether crawling it actually turned up any real job link (matching
that domain's confirmed `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` glob). If a URL for a
domain that *does* have a confirmed job-URL pattern comes back with zero real job
links, it logs the same yellow, step-by-step warning style as the other two warning
types — but naming the exact URL that failed, since a wrong guess here is much more
specific/actionable than "this domain returned nothing":
```
WARNING: <domain>'s direct search URL for <location> returned no individual job
links -- its URL format may have changed:
    1 - Open <the exact URL> and see what it actually shows
    2 - If it's broken, empty, or redirected somewhere odd, go to <domain>'s
        homepage, search "Data Scientist" manually, and copy the new working URL
    3 - Send the new URL back here so it can be fixed
```
This is a *third* yellow warning type, alongside the two described above (no confirmed
deep-crawl pattern; zero results anywhere in the run) — each catching a different
failure mode, all in the same log, all actionable the same way.

### One trade-off accepted: a single role term, not the full role list

Direct URLs are built with a single canonical search term, `"Data Scientist"`
(`_DIRECT_ROLE_TERM`), not the full `GOOGLE_QUERY_ROLE_TERMS` OR-list used everywhere
else — most of these sites' own search boxes take one plain keyword, not an OR
expression the way Google's full-text search does. This does mean a listing titled
purely "Machine Learning Engineer" with no mention of "Data Scientist" anywhere on the
page could be missed by a site's own search *specifically through this direct path* —
but since this is purely additive on top of the unchanged Google stages (which still
search all 4 role terms as before), nothing is actually lost; this path only ever adds
extra coverage the Google stages might have missed for location reasons, never replaces
their broader role-term coverage.

### Real, live testing (not just research) — bugs found and fixed

The user explicitly asked for this feature to be tested for real, batch by batch, with real
Apify calls against the actual sites (not mocked data) — [owner's note: run the strongest test possible; cost does not matter] The first real batch (Norway + Denmark, city-level)
surfaced three genuine bugs, all fixed before continuing to further batches:

1. **`duunitori.fi` hung the whole batched crawler call for 10+ minutes** on a single
   start URL, then failed anyway. A live test with `client.log()` showed the actor
   retrying against something that never resolved. A follow-up isolated test (both
   `playwright:adaptive` and plain-HTTP `cheerio` crawler modes) still returned zero
   content, even for the start URL itself, while a plain fetch to the exact same URL
   succeeded instantly with real content — this points to Apify's own crawler
   infrastructure (datacenter IPs) being blocked by the site, not anything fixable via
   URL, timeout, or crawler-engine choice. **Fix**: `maxRequestRetries: 1` added to both
   crawler calls in this file (`_run_direct_site_searches` and `_deepen_google_results`)
   so one bad site can never stall the rest of a batch for more than 2x
   `requestTimeoutSecs`, **and** `duunitori.fi` removed from
   `DIRECT_SEARCH_URL_BUILDERS` entirely (see the code comment there) — it's back on
   the Google-only path, which already worked before this feature existed.
   `requestTimeoutSecs` itself went through its own tuning arc after a later batch —
   see the note below.
2. **`jooble.org` — the original site that started this whole feature — turned out to
   be unusable too**, for a different reason: a live test with full Apify run logs
   showed `Received blocked status code: 403`, retried 10 times including through
   Apify's own "UNBLOCKER proxy group," still blocked, confirmed across both
   `playwright:adaptive` and `playwright:chrome` crawler types and multiple
   `requestTimeoutSecs` values (30s, 45s). This is jooble.org actively blocking Apify's
   infrastructure specifically —
   the identical URL loads fine via a plain browser-like fetch. **Fix**: removed from
   `DIRECT_SEARCH_URL_BUILDERS` (and its job-URL pattern removed from
   `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` too, so `_deepen_google_results` doesn't keep
   wastefully attempting the same blocked deep-crawl whenever jooble.org shows up in a
   regular Google result). The user's original Jooble discovery (the Oslo/Minnesota
   wrong-subdomain trap) is still fully documented above as the reason this whole
   direct-search feature exists — the site itself just can't be reached by this
   particular tool regardless.
3. **`arbeidsplassen.nav.no`'s own city filter isn't strictly precise** — a live test
   for Oslo found its UI genuinely shows "Oslo" as an active filter chip, but the
   results still mixed in real jobs located in Stavanger, Trondheim, and Gjøvik
   (confirmed identical with both the `municipals[]=` and `municipals[0]=` param
   forms, ruling out a URL-encoding bug — this is the site's own search blending in
   "similar/nearby" recommendations, a common job-board UX pattern). Since the user asked
   for genuinely correct results, not just "the site says it filtered," **fix**: a new
   `_mentions_city(city, text)` check in `_run_direct_site_searches` drops any
   individual job-page row (for a city-level task) whose own crawled text doesn't
   actually contain the requested city name — aware of local-language spellings
   (`_CITY_LOCAL_SPELLINGS`: "Vienna"/"Wien", "Copenhagen"/"København") so a real,
   correct posting in the local language isn't wrongly rejected. Re-tested after the
   fix: `arbeidsplassen.nav.no` for Oslo went from a mixed 14/17-ish correct to 22/22
   genuinely Oslo-located results.
4. **`requestTimeoutSecs` tuning arc** — a second real batch (Austria + Germany, 9
   domains at once) found `stepstone.at`/`stepstone.de` both marked as total connection
   failures (red) at 30s. Isolated single-domain tests of the exact same URLs succeeded
   fine, finding real Vienna/Berlin postings — but averaged ~40-42s per page under the
   crawler's own reported stats, meaning 30s was simply too tight for a legitimate,
   working site once it's competing for resources alongside 8 other domains in the same
   batched run. Bumped to 45s (still failed occasionally), then to 60s — the actor's own
   original default, restored once duunitori.fi's block was independently reconfirmed
   at every tested timeout value (so lowering it below the default was never actually
   protecting against duunitori.fi specifically, only shaving a few seconds off other
   sites' failure detection — not worth the false red flags on legitimate slow sites).
   Re-tested at 60s: 0 of 9 domains failed to connect (down from 2 at 30s) — StepStone
   sites still sometimes only yield the listing page rather than deep-crawled individual
   postings under heavy concurrent load, but never a total failure anymore.
5. **`jobup.ch`'s guessed URL (`/en/emplois/`) was a genuine 404** — a real fetch
   confirmed the correct path is `/en/jobs/` (matching the domain's already-confirmed
   `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` entry, `/en/jobs/detail/**`, which was correct
   all along — only the *search* URL builder had the wrong path). **Fix**: corrected to
   `/en/jobs/?term=...`.
6. **`apec.fr`'s guessed URL (`motsCles=` alone, no location param) redirects to a
   login page**, not search results — research had only confirmed the `lieux=` region
   parameter works (711 = Île-de-France), never a working param-free "whole of France"
   search. **Fix**: returns `None` (no direct-search attempt) rather than risk hitting
   the login wall again; France still has strong coverage via the now-confirmed-working
   `hellowork.com`.
7. **`swissdevjobs.ch`'s guessed country-wide URL (`/jobs/all`) returns a genuine 403**
   — the only confirmed pattern is `/jobs/{category}/{city}` for a *specific* city
   (Zurich/Geneva were the confirmed examples), and Switzerland has no defined city in
   `CITIES`, so there's no safe single-city substitute that wouldn't silently exclude
   the rest of the country. **Fix**: returns `None`.
8. **`seek.com.au` and `careerone.com.au` both bot-block nearly every individual job
   page with a 403**, confirmed independently for each (not one causing the other to
   fail — an isolated single-domain test of `careerone.com.au` alone still failed the
   same way). The failure mode is worse than a simple block: Crawlee's automatic
   session-rotation retry logic re-attempts each blocked link several times, and with
   dozens of real job links discovered from one listing page, this compounded into
   **26+ minutes** of wasted retries in one real test for only 3 usable postings from
   `seek.com.au` — a real production UX risk (a user's search visibly hanging), not
   just a cost concern. **Fix**: both removed from `DIRECT_SEARCH_URL_BUILDERS` *and*
   `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` (so `_deepen_google_results` doesn't risk the
   same retry storm if either domain surfaces in a normal Google result) — Australia's
   direct-search coverage is now `jora.com` only, which was confirmed clean and fast
   across every real test.

9. **`jobly.fi` (Finland) had a confirmed job-URL pattern in
    `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` from the original research, but its
    `DIRECT_SEARCH_URL_BUILDERS` entry was simply never written** — an oversight, not a
    site-side problem. Found by auditing every domain with a confirmed pattern against
    the builders dict for any other gaps like this one (none found beyond this).
    **Fix**: added `_direct_url_jobly_fi` (`https://www.jobly.fi/en/jobs/{role}`,
    country-wide only — Finland has no defined city) and confirmed via a real Apify
    test: 4 real Finnish postings found (Data Scientist, Lead Data Platform Engineer,
    2x Data Scientist Customer Solutions), matching the already-confirmed
    `/en/job/**` pattern exactly.

**Final tally across all 6 real test batches (every one of the 66 researched domains
covered, at both country-wide and city-specific granularity where applicable)**:
Norway/Denmark (Oslo/Copenhagen), Austria/Germany (Vienna/Berlin),
Luxembourg/Switzerland/Portugal/Spain/Amsterdam, United Kingdom/France, United
States/Canada/Australia, and a final sweep of the country-wide (no city) variants for
Norway/Denmark/Sweden/Austria/Germany/Netherlands that the city-focused batches hadn't
covered. Every batch finished at 0 total-connection failures after fixes. A second
Apify account was used partway through after the first hit its free-tier `$10/month`
hard usage cap (a real platform limit, not a bug) — worth knowing if this feature is
re-tested this thoroughly again before the next monthly reset. **Final confirmed set**:
28 unique domains actively participate in direct search (started at 31; lost
`duunitori.fi`, `jooble.org`, `seek.com.au`, `careerone.com.au`, and one confirmed-dead
Swedish domain; gained `jobly.fi` back from the missed-builder oversight above, and
`tyomarkkinatori.fi` from the unresolved-sites pass below — net 28. `apec.fr` and
`swissdevjobs.ch` keep their confirmed job-URL patterns but no longer attempt a guessed
country-wide search URL).

**Later reduced to 26** — `jobs.ch` and `jobup.ch` were removed from this set in a
later cost-optimization round; see "Removed for cost: domains already covered by a
free API" below. This number is kept here as an honest historical record of the real
research batch that produced it, not retroactively edited.

### Direct JSON API integrations (`_run_direct_api_searches`)

**Structural cleanup from a later audit**: this function used to repeat the same
try/fetch/log-success/log-error shape ~11 times, once per source (~250 lines of
near-duplicate code). `_run_direct_api_source(rows, name, fetch_callable, help_text,
progress_cb)` now wraps that shared shape once — each simple source (Reed, France
Travail, EURES, Remotive, RemoteOK, arbeitnow.com, SwissDevJobs, JobCloud,
arbetsformedlingen.se, arbeitsagentur.de) is now a single call passing its own
zero-arg fetch closure. Jooble's own loop is kept separate/custom (its lifetime-budget
tracking and low-budget warning don't fit the shared shape), but every other source
funnels through the one helper.

`arbetsformedlingen.se` (Sweden) and `arbeitsagentur.de` (Germany) are the two sites
whose real, confirmed location mechanism is a REST API returning JSON, not an HTML
page — `website-content-crawler` has nothing to extract `<a href>` links from in a
JSON response, so these were left out of `_run_direct_site_searches` and given their
own, separate integration instead: a plain `requests` HTTP call, parsed directly, with
**no Apify actor involved at all** — cheaper than a crawl and gives richer,
already-structured data (title, company, exact city, posting date, description) than
scraping would.

- **`arbetsformedlingen.se`**: Sweden's own official open-data JobSearch API
  (`jobsearch.api.jobtechdev.se`) — genuinely public, no registration or API key
  needed. A real test call returned 45 jobs for "Data Scientist," each with the full
  job description text included directly in the response (richer than most scraped
  sources). Country-wide only, since Sweden has no defined city in `CITIES`.
- **`arbeitsagentur.de`**: Germany's real Arbeitsagentur job-search REST API
  (`rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`). Returns 403
  without an API key, but `jobboerse-jobsuche` — not a secret, it's the public client
  key the official Arbeitsagentur app itself uses, long documented in the open-source
  `bundesAPI/jobsuche-api` community project — got a real 200 response in testing (302
  total "Data Scientist" results in Germany, 100 confirmed fetched). This search
  response doesn't include full description text (only structured summary fields:
  title, company, city, posting date), so rows from this source have a thinner,
  synthesized `description` than most other sources — still enough for the
  keyword/Claude filters downstream, just not a full JD. Supports both country-wide
  (`wo=` omitted) and Berlin-specific (`wo=Berlin&umkreis=25`, confirmed to return
  genuinely Berlin-based results in testing) — and, matching how country/city
  selections are independent everywhere else in this app, **selecting both Germany and
  Berlin runs both the country-wide and the Berlin-specific API call**, not just one.
  The individual job URL is constructed directly from the API's own `referenznummer`
  field (`https://www.arbeitsagentur.de/jobsuche/jobdetail/{referenznummer}`), confirmed
  to match the site's real URL pattern exactly via a live fetch (`referenznummer
  16012-44394245-821-S` for a Jenoptik AG posting matched the exact detail-page URL for
  that same posting).
- **`francetravail.fr`** also has a real, documented API
  (`api.francetravail.io/partenaire/offresdemploi/v2/offres`, with `commune`/`rayon`
  parameters), but unlike the two above, it requires registered OAuth2 credentials from
  France Travail's own developer portal that RoleHound doesn't have — not attempted, left
  on the Google-only path. France already has solid coverage via the confirmed-working
  `hellowork.com` direct search.

- **`jooble.org` — solved a completely different way than the browser-based
  `MANUAL_ASSIST_GLOBAL_SITES` attempt above.** That attempt was removed after real
  testing found jooble.org's Cloudflare Turnstile check blocks Playwright's browser
  session itself (confirmed with screenshots: the checkbox is real and clickable, the
  click does register and move to "Verifying you are human...", but it never resolves
  — Cloudflare is detecting the CDP automation channel, not just headless mode, so no
  amount of a human sitting there watching gets past it). The user pushed back on
  accepting that as final ([owner's note: the only way is to automate these things] — automating this is
  the only way, he has no time to search manually) and found the real fix himself:
  Jooble has an official REST API (`{domain}.jooble.org/api/{key}`, a plain
  server-to-server POST with no browser involved at all, so Cloudflare never even sees
  it). He requested his own free API keys directly from Jooble (one per country
  domain — a key from `de.jooble.org` only works for `de.jooble.org`, confirmed by
  Jooble's own docs) and sent them back one at a time to be wired in as each arrived.
  **16 of RoleHound's 18 countries are live** (`JOOBLE_API_COUNTRIES` in `pipeline.py`):
  Germany, Netherlands, Austria, Norway, France, Denmark, Sweden, Italy, Switzerland,
  Finland, Belgium, Spain, United Kingdom, Australia, Canada, and Portugal — the 5 with
  a matching `CITIES` city (Germany/Berlin, Netherlands/Amsterdam, Austria/Vienna,
  Norway/Oslo, Denmark/Copenhagen) support both country-wide and city-specific calls,
  independent-selection style same as `arbeitsagentur.de` above; the rest are
  country-wide only since their countries have no defined city. Luxembourg and United
  States are the only 2 without a key (Jooble doesn't publish domains for them the same
  way). Every single one of the 16 was confirmed with a real, live call before being
  considered done — not just the first one and an assumption the rest would work the
  same way: 30 genuine "Data Scientist" postings per domain, every time, response fields
  `title`/`location`/`snippet`/`salary`/`source`/`type`/`link`/`company`/`updated`/`id`
  all present and correctly mapped.
  - **The free tier is a lifetime cap of 500 requests total per key, not monthly** — a
    hard constraint the user flagged before sending the first key. Every real call is
    tracked in a small local counter file (`data/jooble_usage.json`, one count per
    domain code, via `_read_jooble_usage`/`_record_jooble_usage`), and the log gives an
    explicit low-budget warning once a key drops to 50 or fewer requests remaining, and
    a hard stop (skipped, not attempted) once a key hits 0 — with the exact instructions
    to ask Jooble for a higher limit or a new key. This is the one integration in this
    file where testing itself has a real, non-refundable cost — every verification call
    made during development was deducted from the user's own real 500-request budget, not a
    free sandbox.
  - Adding another country only takes a new `JOOBLE_API_COUNTRIES` entry (domain code →
    country name, matching city or `None`) plus a `jooble_{code}_api_key` in
    `settings.json` once the user has requested that domain's key — no other code changes
    needed.

This runs additively, in the same step as (and right after) `_run_direct_site_searches`
— logging the same `WARNING:`/`SUCCESS:`/`ERROR:` yellow/green/red convention used
throughout, so a failed API call gets the same "here's what to check manually" guidance
as any other failure mode in this file.

**A per-site status indicator in the Log**, also requested directly: a yellow "Checking
`<domain>` for `<location>`: `<url>`" line is logged right before each direct-search URL
is crawled, followed after the crawl by either a green line (a real connection was made
to that exact URL — regardless of whether 0 or 50 individual job postings were found
under it, that distinction is folded into the same green line's text) or a red line (no
connection could be made to it at all, with the same 3-step "check it yourself and send
back the fix" instructions used elsewhere). The Log panel can't recolor an existing
line, so this is two separate lines rather than one line changing color, but reads the
same visually: yellow, then green/red right after. This *replaced* the narrower
original "no individual job links found" warning (which only distinguished "found
something" vs "found nothing to deep-crawl") with a strictly more informative 3-state
signal (connection failed entirely / connected but nothing to deep-crawl / connected
with real postings) — implemented as `SUCCESS:`/`ERROR:` prefixed log lines (green/red
in `LOG_COLORS`), alongside the existing `WARNING:` (yellow) used for the "checking..."
line and the two other warning types described above.

**`app.welcometothejungle.com` (formerly Otta, acquired by Welcome to the Jungle in
January 2024) was investigated separately and more carefully** — the user initially asked
about `welcometothejungle.com` as a possible multi-country ("France, Germany, Spain,
Italy, Belgium") addition, which turned out to be wrong (`/de` and `/es` locale paths on
the main site both 404). A deeper investigation specifically into
`app.welcometothejungle.com`'s real coverage — its own official "Job locations we
support" Help Center article, cross-checked against real indexed job postings per
country — found genuine listings only for France, Germany, Netherlands, Spain, United
Kingdom, United States, and Canada (plus only Amsterdam/Berlin of the 5 cities; Vienna,
Oslo, Copenhagen have no presence at all). The user asked for it to be included wherever one
of those 7 countries is searched, so — uniquely among `COUNTRY_JOB_SITES` entries — the
same domain is listed under all 7 of those countries' entries rather than being added to
`GOOGLE_GLOBAL_EXTRA_SITES` (which would have wastefully queried it for the other 11
countries and 3 unsupported cities it has no real presence in). The plain
`welcometothejungle.com` (non-`app.` original site, France-specific) was not added —
only the researched-and-confirmed `app.` subdomain was.

The user also asked (separately,
per-country, per-site) for a manual-check handoff on the harder remaining failures — see
`Failed-Sites-Need-Manual-Check.md` (no longer in the repository) was originally
generated for the user to open each failing search URL by hand and report back what he sees.
The user then asked to resolve as many of these as possible without waiting on manual
browsing, so a further real-testing round (WebFetch + WebSearch research followed by real
Apify `playwright:adaptive` crawls for every URL that looked even slightly promising, not
just guessing again) went through the entire list. Two were found to be simply dead
(fixed by removal, not by finding a working URL); the rest were conclusively confirmed
unfixable, each for a specific, verified reason rather than a generic "didn't work":

- **`te-palvelut.fi` (Finland) — its search backend is dead too, but its real successor
  was found and fixed.** `paikat.te-palvelut.fi` (the actual search subdomain) no longer
  resolves via DNS at all. Its real successor, `tyomarkkinatori.fi`, first looked
  JS-only — three guessed parameters (`haku=`, `keyword=`, `ammatti=`) were all silently
  ignored, each returning the identical unfiltered ~11,700-result count. But the user
  searched the site himself in a real browser, got a correctly filtered 16-result page,
  and sent back the exact URL from his address bar: `?q=Data%20Scientist`. Confirmed via
  a real Apify test — 16 genuine postings (Poolia IT, Terveystalo, etc.), matching what
  The user saw. **Fix**: `_direct_url_tyomarkkinatori_fi` added, `tyomarkkinatori.fi` back in
  `COUNTRY_JOB_SITES['Finland']` and `DIRECT_SEARCH_URL_BUILDERS`, with a confirmed
  job-detail pattern (`/henkiloasiakkaat/avoimet-tyopaikat/{uuid}/{lang}`) in
  `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` too. A good reminder that "JS-only, no URL
  parameter works" sometimes just means the *guessed* parameter names were wrong, not
  that no real one exists — worth asking the person who can actually drive a browser
  before writing a site off.
- **`sapoemprego.pt` (Portugal) — a confirmed trap, not just "didn't work."** A real A/B
  test (crawling the exact same URL with `q=data+scientist` vs. a nonsense query,
  `q=xyzabc123nonexistentquery999`) returned byte-for-byte the same generic "featured"
  listings (Gestor Comercial, McDonald's, MEO Recrutamento...) either way — the `q=`
  parameter is silently ignored and the site just always shows sponsored placements.
  Exactly the same failure shape as `jobbank.gc.ca`'s ignored `locationstring=` and
  `aijobs.ai`'s ignored city path documented above. **Fix**: confirmed to have no
  keyword-search mechanism at all; stays on the Google-only path, no direct-search
  builder added (would have silently returned wrong-role jobs on every run otherwise).
- **`vdab.be` and `actiris.brussels` (Belgium) — genuinely JS-rendered, confirmed with the
  real crawler, not just a plain fetch.** Both already had a confirmed job-*detail* URL
  pattern from earlier research (used for Google's known-site deep-crawl), but real
  `playwright:adaptive` Apify test runs against their guessed search URLs
  (`vdab.be/vindeenjob/vacatures?trefwoorden=...`,
  `actiris.brussels/fr/citoyens/offres-d-emploi/?keyword=...`) each came back with only
  the bare shell page (203 and 240 characters respectively) and zero discoverable links
  to crawl deeper into — even a real browser-rendering crawler gets nothing before the
  page's own JavaScript populates results client-side. **No direct-search builder was
  added for either** — they remain Google-only with their existing confirmed deep-crawl
  patterns, which is genuinely as far as this mechanism can take them.
- **`leforem.be` (Belgium) — confirmed the search box doesn't work via any URL
  parameter**, not just the wrong one. Both `motCle=`/`motCles=` and `q=` were tested for
  real: every one of them left the page's own "Mot-clé... défini" filter chip reading
  "Aucun mot-clé ou métier défini" (no keyword defined) and returned the identical
  ~38,000-result unfiltered count regardless of which term was tried — the site clearly
  needs a client-side interaction (typing into the field triggers an API call) that a URL
  parameter can't reproduce.
- **`jobat.be` (Belgium) and `karrierestart.no` (Norway) — same client-side-only search
  pattern**, confirmed via real crawls: both `?keywords=`/`?q=` guesses rendered a full
  page of real facet/filter content (job-type, city, profession lists) but the only
  links discoverable to crawl further were generic category/filter pages, never an
  actual filtered job-listing card — the keyword search itself is JS-driven and never
  reflected in the URL at all.
- **`nationalevacaturebank.nl` (Netherlands) — confirmed unreachable**, not just
  guessed-wrong: a real Apify crawl of the guessed search URL came back with 0 characters
  of content at all (compare to vdab.be/actiris.brussels' at-least-got-the-shell 200+
  chars) — this domain blocks the crawler outright, matching what a direct fetch attempt
  also showed (an immediate connection refusal before any content exchange).
- **`werk.nl` (Netherlands) and `adem.public.lu` (Luxembourg) — confirmed genuinely
  login-gated**, not just cookie-walled: `werk.nl`'s search page redirects through a real
  OAM/DigiD authentication endpoint (`login.werk.nl/oam/server/...`) before any content
  loads, and `adem.public.lu`'s actual JobBoard link points to `jobboard.adem.lu/login`
  with an explicit "Connectez-vous pour consulter les offres" message — both require a
  real account, which this app deliberately never does.
- **`eluta.ca` (Canada) — confirmed to be a genuine `href="#!"` trap.** A real fetch does
  show actual rendered job cards (BMO, TD Bank, Lyft postings, etc. — not a bot-block
  page), but every one of their links is a literal `#!` placeholder handled by an
  in-page JavaScript click handler, not a real URL a crawler's `<a href>` extraction can
  follow — there is no way to discover the individual job page URL without executing
  that click.
- **`ziprecruiter.com` (US) and `cadremploi.fr` (France) — reconfirmed still blocked**,
  same as the original manual-check findings (company/location filter pages only for
  ZipRecruiter; a near-empty 290-character response for Cadremploi, consistent with its
  earlier-documented login-wall redirect). Both remain low-priority per the user's own
  triage (US already has `dice.com`; France already has `hellowork.com`,
  `francetravail.fr`, and `apec.fr`).
- **`jobnet.dk` (Denmark) and `empleate.gob.es`/`sepe.es` (Spain) were not re-tested this
  round** — both are explicitly low-priority in the user's own triage (Denmark already has
  `jobindex.dk`/`it-jobbank.dk`; Spain already has `infojobs.net`) and neither had a new
  lead to test against.

Most of this round's real, live testing didn't find a new working direct-search URL —
every other candidate was a confirmed dead end (login wall, JS-only search, blocked
crawler, `href="#!"` trap) or an already-known one re-confirmed with sharper evidence.
"Still broken after real testing" is itself a useful, final answer for a site, not a
sign more guessing would eventually work — which is exactly why `tyomarkkinatori.fi`
(above) only got fixed once the user, not another guess, supplied the real URL.

### Removed for cost: domains already covered by a free API

A later Apify-cost audit found a real, recurring inefficiency: several domains were
being searched through **two** mechanisms at once — the free direct-API integrations
above, *and* Google's paid known-sites `site:` query / Deep-Crawl / (for two of them)
a dedicated Direct Site Search crawl — even though the free API already returns the
exact same real listings. Since Filter's own dedup (exact-URL match, then
company+country+85%-similar-title) would just throw the Apify-sourced duplicate away
moments later, this was pure wasted spend, not extra coverage.

**Removed from `COUNTRY_JOB_SITES` / `GOOGLE_GLOBAL_EXTRA_SITES` /
`GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` entirely** (the free API is now their *only*
source) — checked one at a time and confirmed each free API's own description quality
is equal to or better than what Google+Deep-Crawl could find, so this is a genuine
zero-quality-loss cost cut for five of the six:
- **`arbetsformedlingen.se`** (Sweden) — free API includes the *full* job description
  text already.
- **`europa.eu` (EURES)** — free API includes the full job description text already;
  removed from all 14 country entries it was previously listed under. Italy's and
  Sweden's `COUNTRY_JOB_SITES` entries are gone entirely now that their only members
  were removed this way (both still get a real Startup-sites-stage query from
  `COUNTRY_STARTUP_SITES`, completely unaffected).
- **`remotive.com`** and **`remoteok.com`** (global) — both free APIs include the full
  job description text already.
- **`jobs.ch`** and **`jobup.ch`** (Switzerland) — also removed from
  `DIRECT_SEARCH_URL_BUILDERS` (`_direct_url_jobs_ch`/`_direct_url_jobup_ch` deleted
  entirely, since they were only ever used there), on top of the known-sites/Deep-Crawl
  removal — these two were being searched through **three** paid mechanisms at once
  before this. **This one is the real, accepted trade-off**: the free JobCloud API's
  own rows only carry the job title as `description` (no full JD text — see
  `_fetch_jobcloud`'s own comment), thinner than what a real Deep-Crawl could
  occasionally find. The user confirmed he's fine with that trade-off for the cost saved.

**Deliberately kept exactly as before**: `arbeitsagentur.de` (Germany). Its free API
row (`_fetch_arbeitsagentur_de`) only carries a synthesized summary, not the real JD
text either — but unlike the five removed above, Google's own known-sites query for
this domain plus Deep-Crawl has a real, confirmed chance of finding the fuller,
richer description a Deep-Crawl visit to the actual page can extract. Removing it
would have been a genuine quality loss, not a free cost cut, so it stays fully
searched through every mechanism, same as always. `swissdevjobs.ch` (which also has
its own free API, `_fetch_swissdevjobs`) was **not** part of this round either — it
wasn't raised/discussed, so it's untouched; its Apify direct-search URL builder
already returns `None` unconditionally anyway (no working country-wide URL was ever
found for it — see the existing note above), so there was no live-URL cost being
duplicated there in the first place, only the known-sites/Deep-Crawl overlap, which
was left as-is.

### Manual-assisted search — for sites a human can open but Apify's crawler can't

After the unresolved-sites pass above, the user pushed on the remaining categories directly:
[owner's note: can a popup come out of the app so the Security step can be passed and the app can continue?] (can you make a popup that pops out of the app
so I can clear the security part myself, so the app can continue?). Several of the
"unfixable" categories above share the same real shape: the site works completely fine
for a human, and only Apify's crawler infrastructure (a datacenter IP, no cookie-consent
click, no login session) is what's actually blocked. A URL fix can't solve that — but a
human, briefly, can.

**How it works** (`_run_manual_assisted_search`, wired through `manual_assist_cb`): for
a curated list of domains (`MANUAL_ASSIST_SITES`), RoleHound launches a real, visible
Chrome or Microsoft Edge window — whichever is actually installed on the user's own PC,
launched via Playwright's `channel` option rather than a bundled/headless browser — and
navigates it to that site's best-known search URL. A dialog pops up in RoleHound itself
("Continue" / "Skip this site") while the worker thread blocks on a `threading.Event`.
The user clears whatever's in the way in the real browser window — a captcha, a cookie
wall, a login, or just typing his own search into a JS-only search box — then clicks
Continue. RoleHound then reads that exact page: if the domain has a confirmed
individual-job-link pattern, it visits each one (through the same browser, same
cleared session, no further clicks needed) and extracts title/description from each;
otherwise it captures whichever page the user ended up on as a single row, the same honest
fallback used elsewhere in this file rather than silently returning nothing.

**11 domains are covered**, each mapped to its confirmed real search URL from the
research above:
- **Apify-blocked infra** (the crawler gets zero content or an explicit 403,
  confirmed earlier): `duunitori.fi`, `seek.com.au`, `careerone.com.au`,
  `nationalevacaturebank.nl`.
- **Genuinely login-gated**: `werk.nl`, `adem.public.lu` — the user logs in himself; RoleHound
  never touches credentials.
- **JS-only search, confirmed no URL parameter works**: `vdab.be`, `actiris.brussels`,
  `jobat.be`, `leforem.be`, `karrierestart.no` — the user types the search himself.

**`jooble.org` was originally left out** of this list even though it's the same
"blocked infra" shape as the first four — its country routing needs the correct
country subdomain (`no.jooble.org` vs. the global `.org`), the exact Oslo/Minnesota trap
that started this whole feature, and an automated stage getting that wrong would
produce wrong-country jobs that look confirmed. Once this feature actually shipped and
The user started testing it live, he pushed back on leaving fixable sites out just because
the fully-automated version would've been risky — with a human genuinely watching every
result before it's accepted, the risk that justified excluding it stopped applying. See
`MANUAL_ASSIST_GLOBAL_SITES` below.

### Manual-assisted search, round 2 — global sites, and two research mistakes corrected

The user asked to keep going through the sites that still said "go search this one
yourself" and see which of those could also get the automatic-popup treatment. Two of
them turned into real corrections of earlier research, found because the user tested them
himself in his own browser rather than trusting the write-up:

- **`work.turing.com` and `work.mercor.com` were wrongly marked "no public listing at
  all"** in the original `GOOGLE_GLOBAL_EXTRA_SITES` research pass. The user opened both
  himself, before logging in, and sent back real screenshots: Turing's "Explore roles"
  page has a genuine search box and 257 browsable roles across categories including
  "ML, Data & AI"; Mercor's "Explore opportunities" page showed real project-based
  listings (Data Science and Analytics Experts, Data Scientist Talent Network, etc.) for
  a live "Data scientist" search. Both got added to `MANUAL_ASSIST_GLOBAL_SITES` — global
  because they're remote-work platforms with no country of their own, so they run on
  every search regardless of which countries are selected.
  - `work.turing.com/jobs?search=Data+Scientist` was confirmed to genuinely filter (13
    results vs. 257 unfiltered) — a real URL parameter, so no typing needed from the user.
    But its role cards have zero real `<a href>` (0 matches in the raw HTML — they're
    JS-only click targets, same shape as `eluta.ca`'s `href="#!"` trap), so
    `job_link_glob` is `None`: the filtered listing page itself is captured as the row.
  - `work.mercor.com/explore`'s search box is entirely client-side — the URL stayed
    exactly `/explore` even after the user searched and sent back the address bar's URL, so
    there's no parameter to build. He types the search himself once the browser opens.
- **`weworkremotely.com` was correctly found to be Cloudflare-blocked, but the original
  test used `headless=True`** — re-tested with `headless=False` (what this feature
  always launches) and the block never appeared: real content loaded on the first try,
  786KB of HTML, real "Data Scientist" postings visible right on the listing page
  (Proxify AB, Toptal). The block was a headless-detection thing specifically, not a
  block on automation in general. Added to `MANUAL_ASSIST_GLOBAL_SITES` with its real
  search URL (`/remote-jobs/search?term=...`) — but with a second real finding along the
  way: automated `page.goto()` calls into individual job links *after* that first human-
  initiated load do still hit the Cloudflare wall ("Just a moment..."), even though the
  initial page didn't. So `job_link_glob` is deliberately `None` here too — only the
  listing page (whose text already contains real titles) gets captured, no further
  automated navigation is attempted.
- **`jooble.org`** was added back in too, using the plain global domain
  (`jooble.org/SearchResult?ukw=...`) rather than any country subdomain, with its
  already-confirmed job-detail pattern (`jooble.org/desc/**`) — the user can see and correct
  a wrong-country result himself in the open browser, the exact safety net that was
  missing when this was Google-only.

`work.mercor.com` (still no real listing/filter URL) is expected to only ever add one
row per run — the generic "opportunities" page, filtered by whatever the user typed himself.
This confirms a pattern worth remembering from this whole project: research done by
reading and guessing can be wrong in either direction (a site can look fixable and not
be, or look unfixable and actually be fine) — the only fully reliable check is someone
actually opening the real page.

**Location-aware where a real city mechanism was confirmed.** Of the 11 domains,
`Netherlands` (`Amsterdam`) and `Norway` (`Oslo`) are the only ones whose country has a
defined city in `CITIES` — checked both, live:
- `karrierestart.no/jobb/oslo` is a real, confirmed city filter (the page's own "Du har
  søkt: Arbeidssted: Oslo" chip proves it, not just a plausible-looking path).
- `nationalevacaturebank.nl/vacatures/amsterdam` is real too — a live test hit the same
  DPG Media cookie gate as the country-wide URL, but the gate's own `callbackUrl`
  parameter shows it redirects straight back to that exact path once cleared.
- `werk.nl` has no confirmed city URL (not guessed blindly, consistent with every other
  domain in this file) — the user is present anyway and can type "Amsterdam" into its own
  location field once he's past the DigiD login.

**Packaging**: needs the `playwright` pip package (added to `requirements.txt`) and its
driver folder (a bundled `node.exe` + JS driver scripts — not a Python module, so
PyInstaller needs it added explicitly as `datas` in `RoleHound.spec`, at the same relative
path it's extracted to at runtime). No browser binary is bundled at all — `channel`
locates the system's own installed Chrome/Edge, keeping the .exe's size increase to
roughly the driver's size rather than a full browser download. Verified end-to-end with
a real frozen test .exe (not just the dev venv) before shipping: it launched a real,
visible Chrome window and loaded a real page, confirming the driver bundling actually
works once packaged, not just in the dev environment.

**Opt-out**: `settings.json`'s `manual_assist_enabled` (defaults to `True`) is read by
`SearchWorker` and passed straight through as `None` for `manual_assist_cb` when
`False`, which skips this whole stage exactly like no UI being wired up at all — no
checkbox in the Setup Wizard yet, so toggling it currently means editing the settings
file directly. This only matters for an unattended run the user isn't watching, since
otherwise the search would sit waiting at the first popup indefinitely.

### Two yellow warnings, covering different failure modes

Rather than silently doing nothing when a `COUNTRY_JOB_SITES`/`GOOGLE_GLOBAL_EXTRA_SITES`
site isn't working as expected, RoleHound logs a yellow warning in the Log panel with the
same simple 3-step format either way, so the user can go verify and report back what he
finds:
```
WARNING: <domain> ... To help:
    1 - Open https://<domain>
    2 - Paste "Data Scientist" in its search box and press Search
    3 - Copy the resulting page's URL and send it back
```
There are two distinct triggers for this, covering two different things that can go
wrong, each logged **once per domain per run** (not once per location, to avoid
spamming the log when a domain is simply thin across many countries):

1. **No confirmed deep-crawl pattern** (`_deepen_google_results`) — the domain *did*
   show up in this run's Google results, but isn't in
   `GOOGLE_KNOWN_SITE_JOB_URL_PATTERNS` yet, so its listing page couldn't be crawled
   deeper into individual job postings. This was the original warning, built when the user
   asked for a live feedback loop instead of exhaustively pre-testing every possible
   domain.
2. **Zero results at all** (`_warn_zero_result_google_sites`) — the domain was supposed
   to be searched for at least one selected country/city (it's in that country's
   `COUNTRY_JOB_SITES` entry, or it's one of the always-searched
   `GOOGLE_GLOBAL_EXTRA_SITES`), but this run's Google results contained nothing from it
   at all. The user asked for this as a blanket safety net covering *every* site RoleHound
   searches via Google, confirmed pattern or not — a domain can go quiet for reasons that
   have nothing to do with a missing deep-crawl pattern (a typo'd/dead/renamed domain,
   Google indexing it poorly, a robots block, or — especially relevant for the
   remote-first global sites — a listing that's real but never mentions the specific city
   being searched for, since Google's `site:` search only matches text it has actually
   indexed on that domain; see "How location actually works for Google-searched sites"
   below for more on that last case).

A domain can trigger warning 2 without ever reaching warning 1 (if it never shows up in
results at all, `_deepen_google_results` never even considers it) — the two are checked
independently, in that order, right after Google's results are normalized in
`run_search`.

### How location actually works for Google-searched sites

Neither `COUNTRY_JOB_SITES` nor `GOOGLE_GLOBAL_EXTRA_SITES` sites are queried through
their own internal location filter or API — RoleHound never talks to remoteok.com's or
finn.no's own search backend directly. Location scoping happens entirely through the
Google query text itself: `build_google_job_queries` embeds the plain location name
(e.g. `Oslo`) right next to the `site:` restriction —
`(role terms) jobs Oslo (site:remoteok.com OR site:wellfound.com OR ...)` — and it's
Google's own full-text index that has to have both the site restriction and the word
"Oslo" match on the same indexed page.

**This has a real, inherent limitation, especially for remote-first global sites**: if
a listing on a genuinely remote-friendly site never mentions "Oslo" anywhere in its
indexed text (a plausible, common case — a "Remote" listing often just says "Remote",
not naming every city its candidate could be in), Google won't surface it for that
city's query, even though the job itself would be perfectly relevant. This is a
limitation of using Google as a full-text-search proxy rather than each site's own
structured location data, not a bug — and it's exactly the kind of thing the zero-result
warning above (case 2) helps surface: a global site returning zero results for one
specific city is often this limitation showing up, not necessarily a broken domain.

**Why the query is built this way**: since Google has no structured "job title" field
to search like the platform actors do, `build_google_job_queries` uses a curated list
of **actual job-title phrases** (`GOOGLE_QUERY_ROLE_TERMS`) rather than reusing the much
broader `KEYWORDS` OR-list built for the platform APIs — a bare `AI` or `Big Data` term
is far too noisy for Google's full-text search, and the full `KEYWORDS` list would also
blow past Google's ~32-word query limit.

`GOOGLE_QUERY_ROLE_TERMS` was deliberately trimmed twice, for two different reasons:
first from an original 8 terms down to 5 (dropping `"ML Engineer"`, `"NLP Engineer"`,
`"Computer Vision Engineer"`) to free up word budget for more entries in
`GOOGLE_EXCLUDED_TLD_HINTS` (below); later from 5 down to the current 4
(`"Data Scientist"`, `"Data Engineer"`, `"Machine Learning Engineer"`, `"AI Engineer"` —
dropping `"Data Analyst"`) to free up word budget for the 4 remote/AI-focused sites
added to `GOOGLE_GLOBAL_EXTRA_SITES` (see the word-budget note above). Trade-off
accepted deliberately both times: a listing titled exactly "NLP Engineer" or "Data
Analyst" with none of the 4 remaining phrases appearing anywhere else on the page could
be missed by Google's stages specifically (LinkedIn/Indeed/Glassdoor are unaffected —
see "The search keywords (`KEYWORDS`)" below).

### The search keywords (`KEYWORDS`)

The role/topic terms actually sent to LinkedIn/Indeed/Glassdoor (a plain `OR`-joined
string, no ~32-word limit to worry about — unlike Google's `GOOGLE_QUERY_ROLE_TERMS`
above, which is a deliberately short, separate list):

`Data Science, Data Scientist, Data Engineer, Machine Learning, ML, AI, Artificial
Intelligence, Data Engineering, Deep Learning, NLP, Natural Language Processing,
Computer Vision, AI Engineer, ML Engineer, MLOps, Generative AI, GenAI, LLM, Big Data`
(19 terms).

`TOPIC_KEYWORDS` mirrors this same list (used only for the Job Search page's
display-only "Show only / Hide" topic filter, not the actual search query) and is kept
in sync whenever `KEYWORDS` changes.

**Trimmed from 27 to 19 terms** — the user asked to drop the analytics/analyst-flavored and
a couple of rarely-relevant terms entirely (not just from Google's shorter list this
time): `Data Analysis`, `Data Analyst`, `Data Analytics`, `Analytics Engineer`,
`Predictive Analytics`, `Predictive Modeling`, `Neural Network`, `Reinforcement
Learning`. This affects every platform (LinkedIn, Indeed, Glassdoor, and Google, since
Google's shorter list never had most of these anyway) — those role/topic terms will no
longer independently pull in a listing that doesn't also mention one of the 19 terms
still in the list.

**Full page content, not just Google's snippet**: the run always sets
`"websiteContentScraper": {"enable": True}` — an Apify add-on that scrapes the full
text of every organic result's page (`websiteContent.text`), not just Google's short
snippet. Without this, there wouldn't be enough text for the translate/filter/Claude
pipeline to work with. `maxPagesPerQuery: 3` is used (≈30 results per query).

**Normalizing Google's output** (`normalize_google_search_result`): Google doesn't
return structured job fields the dedicated actors do — no `company`, no `posted_date`.
`location`/`country` are filled in from the city the query was built for (matched back
via `_city_from_search_term`, which looks for a known city name inside the
`searchQuery.term` field the actor's dataset items carry); `description` prefers the
full scraped `websiteContent.text` over Google's short snippet, falling back to the
snippet if that page failed to scrape.

**Verified against a real run** (a small, deliberately cheap test search for Oslo,
`maxPagesPerQuery: 1`, once Apify quota was available again) — confirmed working
exactly as designed:
- `searchQuery.term` does carry the exact query text, so `_city_from_search_term`
  correctly attributed the result page to `"Oslo"`.
- `organicResults[].websiteContent.text` was populated with real page text (ranging
  ~200–6000 characters across the 10 results in that test), confirming
  `websiteContentScraper` and the description fallback both work.
- The `glassdoor.ca` leak described above was found in this exact test, and confirmed
  fixed by switching the app-side filter to brand-substring matching.

**Cost note**: `websiteContentScraper` is a paid per-page add-on, and `maxPagesPerQuery:
3` means up to ~30 results per city × 5 cities = up to 150 pages scraped in one run —
still meaningfully more per search than Indeed/Glassdoor/LinkedIn, though far less than
the earlier 4-query-per-city version (600 pages) before the LinkedIn/Indeed/Glassdoor
exclusion was added. The user explicitly said cost wasn't a concern and asked for "the most
accurate and best possible results."

## Startup Websites Search & Company Popularity

The biggest new feature added this session: a **4th Google query stage**, restricted via
`site:` OR-clauses to dedicated startup/scaleup job boards, plus a brand-new **Company
Popularity** column that (among other things) uses this new stage to label a listing
`'Startup'` automatically, with no Claude call needed.

### The 4th query stage

`build_google_job_queries` now builds, per selected location, in this exact order:
**Known-sites → Startup-sites → Global-extra-sites → Open-web**. The new stage sits
between the existing known-sites and global-extra-sites stages — run second, so a
location's own dedicated startup boards are checked right after its general-purpose
local job boards, before the broader global sites and the open web:

```python
def add_location(location: str, known_sites_country: str | None):
    known_clause = _known_sites_clause(known_sites_country)
    if known_clause:
        lines.append(f'{role_clause} jobs {location} {known_clause}')
    startup_clause = _startup_sites_clause(known_sites_country)
    if startup_clause:
        lines.append(f'{role_clause} jobs {location} {startup_clause}')
    for global_clause in global_clauses:
        lines.append(f'{role_clause} jobs {location} {global_clause}')
    lines.append(f'{role_clause} jobs {location} {exclude_clause}')
```

A country/city with no `COUNTRY_STARTUP_SITES` entry just skips this one stage (the
other three still always run) — same per-country gap handling as `COUNTRY_JOB_SITES`
already had. In the Log, this stage's results are its own section, "Startup Websites
Search," nested under "Google" right alongside "Known Websites" — see
[the Log panel](#the-log-panel) above for exactly why they share the same combined
actor call and the same cost line.

Two new dicts in `pipeline.py`:

- **`GLOBAL_STARTUP_SITES = ['startup.jobs', 'topstartups.io']`** — searched for every
  location regardless of country, same pattern as `GOOGLE_GLOBAL_EXTRA_SITES`. Both were
  confirmed real and active during the Netherlands research pass but turned out not to
  be Dutch-specific at all (they just happen to have a Netherlands filter page, same as
  any other country), so they were moved here instead of being duplicated into every
  country's own list.
- **`COUNTRY_STARTUP_SITES`** — per-country dedicated startup boards, researched one
  country at a time, with real live verification (via a real fetch — checking real
  listing counts, company names, posting dates) for every single one:

| Country | Domain(s) | What was confirmed |
|---|---|---|
| Netherlands | `scaleupjobs.nl`, `jobfluent.com`, `jobs.siliconcanals.com`, `startupmap.iamsterdam.com`, `magnet.me`, `us.foundersbase.com` | 6 sites, the original research batch |
| Germany | `berlinstartupjobs.com`, `startuplist.de` | 2 sites |
| France | `la-french-tech.welcomekit.co` (official French-government-backed startup board), `www.licornesociety.com` | 2 sites; 859 open positions on licornesociety.com at time of checking |
| United Kingdom | `londonstartupjobs.co.uk` | 1 site; a sister site to berlinstartupjobs.com from the same operator |
| Sweden | `thehub.io` (shared Nordic board), `www.supjobs.com` | 2 sites; thehub.io had 216 filtered jobs, supjobs.com had 81 pages of listings |
| Denmark, Finland, Norway | `thehub.io` | 1 each — thehub.io explicitly covers Denmark/Finland/Iceland/Norway/Sweden, added to all 4 in-app countries at once (Iceland isn't in `COUNTRIES`) |
| Switzerland | `www.startupticker.ch` | 1 site; 40 recently-published jobs, powered by Joinup |
| Austria | `metajob.at`, `austrianstartups.com` | 2 sites; metajob.at had 225 real, recently-dated Vienna postings — a second, deeper research pass after the user flagged Austria as especially important to him |
| Italy | `startupjobsitaly.com`, `xjobs.cdpventurecapital.it` | 2 sites; 205 positions + CDP Venture Capital's own portfolio board |
| Spain | `www.startuphub.ai` | 1 site; 183 open roles explicitly branded "AI and tech startups" |
| Portugal | `www.startupjobs.pt` | 1 site; real listings from Feedzai, Coverflex, Imaginary Cloud |
| United States | `jobs.a16z.com` | 1 site; Andreessen Horowitz's own VC-portfolio board — confirmed live with **852 companies, 18,964 jobs** |
| Canada | `www.startupsnorth.ca`, `dmz.torontomu.ca` | 2 sites; startupsnorth.ca had 2,344+ open positions, 465 added in the week of checking alone |
| Australia | `jobs.blackbird.vc`, `squarepeg.getro.com` | 2 sites; both VC-portfolio boards (Blackbird Ventures / Square Peg Capital), 1,195 and 1,673 open jobs respectively |

**Belgium and Luxembourg have zero country-specific entries** — real research found
nothing usable for either (see rejections below).

### Every rejected site, and why

This doc's style always explains what was tried and rejected, not just what was kept —
the reasoning below is transcribed from the real comment block directly above
`COUNTRY_STARTUP_SITES` in `pipeline.py`:

- **Sites returning a real HTTP 403 to a direct fetch attempt** (likely blocking
  automated access outright, so they couldn't be confirmed live/crawlable even though
  Google's own index may have them): `handpickedberlin.com` (Germany), `startup.ch`
  (Switzerland), `startupgalaxy.com.au` (Australia — StartupAUS itself, the obvious
  first candidate, was also confirmed disbanded in 2021), `workinstartups.com` (UK),
  `crunchboard.com` (US — TechCrunch's own job board), `skillbourg.com`.
- **Dead / expired domains**: `dutchtechjobs.com` (Netherlands — confirmed
  dead/expired-domain-for-sale despite still being listed on Startup Amsterdam's own
  official page).
- **Confirmed real but with zero current listings**: `sting.co` (Sweden — Stockholm
  Innovation & Growth's own startup jobs page; a real fetch found "0 results"/"No items
  found" at the time of checking, so not worth including even though the site itself is
  legitimate).
- **Real and active, but NOT startup-specific** — the most important recurring
  rejection reason, since being found via this stage means an automatic `'Startup'`
  label with **no** Claude verification (see below) — a non-startup-specific source
  would wrongly mislabel a big company: `builtinlondon.uk` (UK — lists Mastercard, Wells
  Fargo, Cloudflare alongside real startups), `spainjobs.io` (Spain — lists Google,
  Microsoft, Affirm), `landing.jobs` (Portugal — explicitly "Tech Jobs in Europe," not
  Portugal-specific, with corporate partners like Siemens/Volkswagen), `Agoria`/
  `portal.agoria.be` (Belgium). `himalayas.app` was tried too (huge, 97k+ listings) but
  rejected for the same reason — real enterprises like Thomson Reuters, Humana, Santander
  showed up in real listings, general remote work rather than startup-specific.
- **`karriere.at/jobs/startup/wien`** (Austria) has a real startup-filtered section, but
  `karriere.at` is already a `COUNTRY_JOB_SITES` entry for Austria, and the same domain
  can't be searched in two disjoint stages (see `_google_query_stage`'s disjointness
  requirement below) — not duplicated here.
- **`austrianstartups.com/opportunities`** is a JS-rendered community platform a direct
  fetch couldn't read — but a real Google search confirmed individually-indexed
  opportunity pages do exist (e.g. `austrianstartups.com/opportunities/302304`), a
  weaker verification bar than the others, noted for that reason, but kept alongside
  `metajob.at` as a genuine additional source anyway.

### `_google_query_stage`'s `'startup'` classification, and why `wellfound.com` stays out

`_google_query_stage(term)` now also classifies a `'startup'` stage: it checks
`GLOBAL_STARTUP_SITES` first, then every `COUNTRY_STARTUP_SITES` value list, for a
substring match against the query text. This only works because
`COUNTRY_JOB_SITES`/`COUNTRY_STARTUP_SITES`/`GOOGLE_GLOBAL_EXTRA_SITES` are all kept
pairwise disjoint by design — the same requirement `_google_query_stage`'s `'known'` vs
`'global'` classification already relied on.

**`wellfound.com` (Wellfound/AngelList Talent) is deliberately kept OUT of
`COUNTRY_STARTUP_SITES`, despite genuinely being a startup site** — it's already in
`GOOGLE_GLOBAL_EXTRA_SITES`. Adding it to `COUNTRY_STARTUP_SITES` too would double-search
it (once in each stage's query) and break the disjointness `_google_query_stage`'s
classification depends on. Same reasoning kept `dutchtechjobs.com` and
`workatastartup.com` (Y Combinator, already global) out of any per-country list.

### Company Popularity column — built, then removed entirely

A "Company Popularity" column existed for part of this project: `job['company_fame']`,
a 5-level badge (`Startup`/`Unknown`/`Known`/`Well Known`/`Famous`) assessed via a real,
separately-billed Claude call with the `web_search_20250305` tool, once per unique
`(company, country)` pair.

**Removed entirely, at the user's explicit request**, for two real reasons:
1. **Cost**: after prompt caching was added to the Claude screening pass (see
   [the Claude final pass](#the-claude-final-pass) below), this was the single largest
   *remaining* recurring Claude cost — a real web-search call per unique company, on
   every Filter run, with no caching of its own.
2. **It mostly wasn't useful in real use**: The user reported it mostly came back
   `Unknown`. Investigated for real (not guessed) — a diagnostic batch of real Claude
   calls against known companies (including a genuinely small one) all correctly
   returned real, sensible verdicts, so the *mechanism* worked; the actual root cause,
   found by inspecting the user's own real `jobs.json`, was upstream of Claude entirely:
   most Google-sourced listings have no `company` field at all (Google itself doesn't
   return one), and when `_extract_company_from_text`'s regex heuristic *did* extract
   something, it sometimes extracted the wrong text — a real example found in the user's
   own data: the title `"Data Science Expert - Mercor Jobs"` (a `"<Job Title> - <Site
   Name> Jobs"` aggregator-page title, the reverse of the pattern the prefix regex
   assumes) had `"Data Science Expert"` — the job title, not a company — extracted as
   the "company," guaranteeing an `Unknown` verdict since it isn't a real company at
   all. Fixing the *company* was going to need its own project; removing the feature
   that spent real money asking Claude about wrong/missing company names was the
   simpler, immediate fix.

**What was kept**: the one genuinely free part — a listing found via the Startup
Websites Search stage (`google_stage == 'startup'`) is, by construction, already known
to be a startup, no Claude call ever needed for that specific case. The user asked for this
signal to move into the **Type** badge instead of its own column: `pipeline.
display_category(job)` appends `" Startup"` to the job's own `Category` (e.g. `"Full-
Time Startup"`, `"Internship Startup"`) when `google_stage == 'startup'`, otherwise
returns the plain category unchanged. Used everywhere the Type badge is shown (Jobs
page, Excel export) — the *stored* `Category` field itself stays clean/unsuffixed
(`"Full-Time"`), so `CATEGORY_ORDER`-based sorting and `CATEGORY_BADGE_COLORS` lookups
are completely unaffected; the badge's color still comes from the plain base category
(no separate color table needed for the suffixed text). Applications page never showed
a Type/Category column at all, so it simply lost the Company Popularity column with
nothing added in its place.

## Pre-flight health check — before every real search

After this session's Jooble/Reed/EURES/France Travail/Remotive/RemoteOK/SwissDevJobs/
jobs.ch/jobup.ch integrations were all added, the user asked a natural follow-up: of all
these mechanisms, which is most likely to silently break, and what can be done about it
*before* a real search burns Apify credits and Jooble's limited request budget on
sources that turn out to be down? The answer is `_run_preflight_checks` in
`pipeline.py`, called from `run_search()` right after the existing Apify-token check and
before anything else — a cheap, real connectivity check of every source relevant to the
countries/cities actually selected, reported in two sections in the Log:

- **Section 1: Google Search** — a single trivial query against the Google Search actor
  itself (only run if `'google'` is in the selected actor order and at least one
  country/city is selected). Logs `SUCCESS: Section 1: Google Search — Completed
  (100%).` in green, or `ERROR: Section 1: Google Search — Failed (0%).` in red.
- **Section 2: API** — every configured, currently-relevant direct-API source gets its
  own check: `arbetsformedlingen.se`, `arbeitsagentur.de`, each configured Jooble
  country key, Reed, France Travail (token-only), EURES, Remotive, RemoteOK,
  `arbeitnow.com`, and (only if Switzerland is selected) SwissDevJobs/jobs.ch/jobup.ch
  — using the exact same country/city relevance scoping `_run_direct_api_searches`
  already uses, so a source irrelevant to this run is never checked. Logs `SUCCESS:
  Section 2: API — Completed (100%, N/N).` or `ERROR: Section 2: API — Failed (X%,
  N/M OK).`
  - **Real gap found and fixed in a later audit**: `arbeitnow.com` (the Sponsorship
    Visa "type (a)" source, unconditionally called every run) was missing from this
    check entirely — a break in that one source would only ever have been discovered
    mid-search, defeating the whole point of checking it here first. Added.
- **Jooble is checked config-only** (key present, correctly shaped, still under its
  500-lifetime cap) — **no network call** — specifically to avoid burning any of that
  scarce real budget just running a health check. Every other API source above gets a
  real, minimal live request, since none of them have that scarcity problem.

**If problems are found**, the search pauses (blocking the worker thread, same
`threading.Event` + `result_holder` pattern already used by the manual-assist popup) and
a dialog (`PreflightProblemsDialog`) lists each one with its reason. Where the problem is
something RoleHound can actually fix live — a missing or rejected API key — there's an
inline field to paste a replacement right there, and a fixed key is both used
immediately for this run and saved to `settings.json` for next time. Where it isn't
fixable live (a changed URL pattern, a real block), there's nothing to type — just
"Continue" to skip that source and carry on, or "Cancel search" to stop entirely before
spending anything on the real run. This deliberately matches how the user answered when
asked what to do here: [owner's note: only warn, skip it automatically and carry on with the rest] for anything
unfixable, but with a real chance to fix what can actually be fixed, rather than only
ever skipping.

Cancelling from this dialog is caught in its own local `try/except SearchCancelled`
around just the pre-flight call — separate from the existing outer
`try/except SearchCancelled` further down that wraps the real fetch loop — so a cancel
here logs a clean "Search cancelled by you during the pre-flight check." message and
returns an empty result, instead of surfacing as a generic "Search failed" error (which
is what would happen if it were left to propagate to `SearchWorker.run()`'s catch-all
exception handler).

## How a search actually runs

For every selected country, every selected platform actor gets called (in the order
configured in the wizard — **default order is Indeed, then Glassdoor, then LinkedIn**,
changed deliberately from an earlier LinkedIn-first order). So total actor calls =
`countries × enabled platforms`.

Each Apify actor call is started with `.start()` (not the blocking `.call()`) and then
polled every 4 seconds, logging its live status (`READY` → `RUNNING` → `SUCCEEDED`), so
you can always tell it's working — a single run can take anywhere from ~10 seconds to a
couple of minutes.

**Up to `SEARCH_MAX_CONCURRENT_PLATFORMS` (2) of these run at once, not one at a time —
renamed from `SEARCH_MAX_CONCURRENT_ACTORS`, and the whole concurrency model changed
from per-(platform, location) pair to per-PLATFORM.** Originally, every individual
`(platform, loc_type, location)` combination was submitted to the executor as its own
unit of work, so Indeed/Norway and Indeed/Germany could end up running on two different
threads at once, interleaved with Glassdoor/LinkedIn's own calls. It's now
`run_platform_locations(platform, items)`: **one thread per selected platform**, and
that thread works through its own countries/cities **sequentially, in order** — Indeed's
own thread never runs two of Indeed's own locations at once. Up to
`SEARCH_MAX_CONCURRENT_PLATFORMS` platforms (not platform+location pairs) run
concurrently, so with the default 3 platforms selected, at most 2 of
Indeed/Glassdoor/LinkedIn are ever running at the same moment, with the 3rd starting the
instant one of the first two finishes. This is what gives each platform its own single,
clean, independently-ticking header line in the Log (`PLATFORM_START:<platform>` /
`PLATFORM_END:<platform>`, with each of its own locations nested underneath via
`LOCATION_START:`/`LOCATION_DONE:`) instead of several platforms' location lines
interleaving in real-completion order. `2` specifically (not higher) is still because a
real test once hit Apify's own account-level concurrent-memory limit trying 3 actor
calls in parallel (`"you will exceed the memory limit of 16384MB for all your Actor
runs and builds (currently used: 16384MB, requested: 8192MB)"`) — 2 actors of that size
fit under the cap, a 3rd doesn't. Raising this constant is safe only if the Apify plan's
memory limit goes up. Cancelling mid-search (see below) still works the same way: a
cancel request stops any *queued* (not-yet-started) platform from ever starting
(`Future.cancel()`, which only succeeds on a not-yet-running future) while letting
whatever's already running finish or self-abort within a few seconds via its own
polling loop.

Threads are the right tool here (not multiprocessing) because each actor call is
network/polling-bound — waiting on Apify's servers, not doing local CPU work — the exact
same reasoning already used for `translate_many`'s parallel translation calls below. The
shared `rows` list and `done` progress counter are only ever touched from the single
thread that's draining `as_completed(futures)`, never from inside a worker thread
itself (`done` is guarded by a `threading.Lock`, `done_lock`, since it IS incremented
from inside each platform's own worker thread as it finishes each of its locations).

The Google actor call (a single call covering every selected country/city in one batch
of queries) isn't part of this — it was already just one Apify call, so there's nothing
to parallelize there; it still runs after the platform executor finishes (`executor.
shutdown(wait=True)` blocks until every platform thread is done), so Google's own
"Pre-API Check"/known-sites/startup-sites/deep-crawl/direct-site-search sub-timers are
guaranteed to be the only thing running by the time they start.

### Real cancel bug found and fixed: 4 blocking Apify calls couldn't be interrupted

The existing per-actor-call cancel pattern above (`.start()` + poll-every-4-seconds +
`should_cancel()` check + `client.run(run_id).abort()`) was already used for the
Indeed/LinkedIn/Glassdoor/Google actor calls — but `_deepen_google_results`,
`_run_direct_site_searches`, `_preflight_check_google`, and `_verify_direct_search_url`
all still used the SDK's simpler, **blocking** `.call()` for their own Apify calls. A
blocking `.call()` has no way to notice a mid-search Cancel click until Apify itself
finishes that run naturally — for a deep-crawl, that can be many minutes — even though
the rest of the app stayed responsive the whole time (it's a different `QThread` that's
blocked, not the GUI thread, so the window itself never froze; the Log just went quiet).
The user reported this as **owner's note: a very big problem** (a very big problem) after finding he'd
had to go into the Apify Console himself and manually abort runs — and even then the Log
showed nothing stopping.

**Fix**: a new shared helper, `_run_actor_cancellable(client, actor_id, run_input,
should_cancel=None, memory_mbytes=None, poll_interval=4)` in `pipeline.py` — the exact
same start/poll/abort pattern `run_search`'s own `run_actor_and_fetch` closure already
used, now pulled out and shared, and used by all four of the previously-blocking call
sites (each already had, or was given, `except SearchCancelled: raise` before its own
generic `except Exception:` handler, so a cancel there no longer gets swallowed as a
plain failure). Verified with:
- A real, live end-to-end test: called `_run_actor_cancellable` against a REAL running
  Apify actor, simulated a Cancel click after 2 polls — `SearchCancelled` was raised in
  5.4 real seconds, and a direct Apify API check afterward confirmed the run really was
  `ABORTED` on Apify's own side within seconds, not left running and still billing.
- Mocked tests confirming `_deepen_google_results`, `_run_direct_site_searches`, and
  `_verify_direct_search_url` no longer swallow `SearchCancelled` as a generic failure.

### The main Google Search actor call now gets the full account memory too

`_DEEP_CRAWL_MEMORY_MBYTES = 16384` (the account's full, real, confirmed memory cap) was
already used for `_deepen_google_results`/`_run_direct_site_searches`. This session the
same boost was extended to the **main Google Search actor call itself** —
`run_actor_and_fetch` gained an optional `memory_mbytes` parameter, passed as
`_DEEP_CRAWL_MEMORY_MBYTES` only for the Google call, **never** for Indeed/LinkedIn/
Glassdoor. This is deliberately conditional: those three can run two at once via
`SEARCH_MAX_CONCURRENT_PLATFORMS`, and each would try to claim the full account memory
cap simultaneously if this were unconditional, which the account doesn't have room for.
Google's own call is always the *only* thing running by the time it starts (the platform
executor's `shutdown(wait=True)` has already waited for everything else to finish), so
it's safe to hand it the same full-cap boost. Verified via a real mocked test inspecting
the actual `.start()` call's kwargs.

**LinkedIn, since 4 October 2026, is `apimaestro/linkedin-jobs-scraper-api`** — read `T-16`
before this paragraph, because everything this section used to say about LinkedIn described the
actor it replaced. That actor was given a search URL with `f_WT=2` baked in
(`build_linkedin_remote_search_url`, still in the codebase for its tests) and **ignored it**: the
same URL without `f_WT` returned the identical 300 jobs, about 6% of them Remote. The new actor
takes plain fields, its `remote` field is a real filter, and every row comes back with LinkedIn's
own Hybrid / On-site / Remote tag, which the Work Location rule reads before any wording.

**~~Italy is still searched without the remote filter~~ — removed by `T-23`:** Remote is asked for in
Italy, Turin and Milan exactly as everywhere. The client-side Remote rule still runs on every listing regardless; the tag is evidence it
reads, not a replacement for it.

**Resilience**: if anything interrupts the search partway through — Apify credits
running out, a network outage, any unexpected error — whatever was already fetched is
still processed (dedup, translate, categorize, sort) and shown, instead of being lost.
This is implemented as an outer `try/except` around the whole fetch loop in
`run_search`, on top of the pre-existing per-actor-call `try/except` that already
skips a single failed call and moves to the next country.

## The categorize/sort pipeline (what a raw Search actually still does)

**Real correction to this doc**: an earlier version of this section (and of the
"two-phase model" summary above it) described deduplication and fake-listing removal as
running during Search (Phase 1). That's no longer true and hadn't been for a while —
`run_search` doesn't call `_remove_duplicates_list`/`_remove_fake_listings_list` at all
any more; both were moved entirely into `reapply_filters` (Filter), specifically so a
raw Search shows every listing exactly as fetched, with zero cleanup of any kind, not
even dedup — see "Phase 2 — what the Filter button does" below for where they actually
run now. What genuinely still runs during every Search, always, regardless of filters,
is just categorizing and sorting. Deliberately does **not** translate anything either —
translation is content processing and belongs entirely in Phase 2, so the raw Search
view always shows every listing exactly as fetched, in its original language, untouched
until you click Filter. (An earlier version mistakenly ran translation inside
`run_search` itself, which meant the slow network translation calls happened *before*
you'd even clicked Filter, defeating the point of the two-phase design — this was found
and fixed, well before dedup/fake-removal were moved out too.)

1. **Categorize** (`categorize`) — purely informational `Type` tag, does not filter
   anything. Checks for `part-time`/`part time` → **Part-Time**, `internship` →
   **Internship**, `thesis` → **Thesis** (title+description substring match); otherwise
   falls back to LinkedIn's own `employmentType` field (Full-time/Contract/Temporary/
   Internship/Volunteer/Other), defaulting to **Full-Time** if nothing is known. Since
   this runs on untranslated text during Search, a non-English listing's badge may be
   briefly wrong until Filter re-translates and re-categorizes it.
2. **Sort** — uncertain-Type listings last, then Part-Time → Internship → Thesis →
   Full-Time → everything else, Italy first within each group.
   `is_category_uncertain` flags a listing as uncertain when its Type badge is only
   "Full-Time" by default (no English category keyword matched, no `employmentType`
   field) *and* it's not in English — e.g. a German "Praktikum" (internship) posting
   won't match the English keyword list, so instead of silently mislabeling it
   Full-Time, it's pushed to the very end of the raw Search list. Once you click
   Filter, it's translated, recategorized correctly, and the whole kept list is
   re-sorted from scratch by the corrected `Category` (see `reapply_filters`) — so this
   flag only affects the raw, pre-Filter ordering.

## Phase 2 — what the Filter button does (`reapply_filters`)

Nothing below this point ever runs during Search — only when you click **Filter**.
`reapply_filters` is structured into **7 discrete, individually-timed
steps** (originally 8 — a "Company Popularity" step was removed entirely, see
[Company Popularity column — built, then removed
entirely](#company-popularity-column--built-then-removed-entirely) above), each with
its own `FILTER_STEP_START:key|label` / `FILTER_STEP_DONE:
key|label|detail` progress marker (see [the Log panel](#the-log-panel) above for how
this renders — a nested "Filter" section with each step as its own live-ticking
sub-timer). Steps 4 and 5 below check several discrete rules *per listing across a
loop*, not as one-off actions, so — per the user's ask that the actual rule names be visible
in the Log, not just each step's own single summary count — each also logs a static
checklist of rule names (`FILTER_STEP_ITEM:key|label`) right before its own
`FILTER_STEP_DONE`. This checklist is a static "this rule genuinely ran against every
listing in this step" list (`FILTER_RULES_STEP_CHECKLIST` / `FILTER_CLAUDE_STEP_
CHECKLIST` in `pipeline.py`), not live per-listing progress — it's only ever emitted
once the step's real loop has already fully finished.

### Step 1 — Finding Company Names for Removing Duplicates (`_fill_missing_company_names`)

Google-sourced listings never arrive with a real `company` field (Google itself doesn't
return one, unlike Indeed/LinkedIn/Glassdoor's structured APIs) — this weakens
duplicate detection specifically for them, since step 2's near-duplicate check groups by
`company + country`, so a Google row with no company can only ever be caught by the
exact-URL check, not the fuzzy-title check. This is Filter's real first step, run
*before* dedup, so the near-duplicate check right after it actually has something to
group Google rows by.

`_extract_company_from_text(title, description)` tries a small set of well-anchored
regex patterns, in order, against a listing's own text — deliberately **regex-only, not
Claude** (a real search can return thousands of listings, too many/slow/expensive to
send each one to Claude just for this): `"<Job Title> at <Company>"` at the end of a
title (`_COMPANY_TITLE_SUFFIX_PATTERN`), `"<Company> - <Job Title>"` /
`"<Company>: <Job Title>"` / `"<Company> | <Job Title>"` at the start of a title
(`_COMPANY_TITLE_PREFIX_PATTERN`, a very common aggregator-listing title format), or
`"<Company> is hiring/looking for/seeking/searching for ..."` at the very start of the
description (`_COMPANY_HIRING_PATTERN`). A candidate is only accepted if it also passes
`_looks_like_real_company_name` (2–60 chars, contains a letter, and isn't one of
`_COMPANY_FROM_TEXT_STOPWORDS` — generic words like `remote`, `job`, `hiring`,
`confidential`, `linkedin`, etc.). Deliberately conservative: an unmatched listing is
left with `company=None` exactly as before, never given a guessed name, since a wrong
guess would actively cause a *false* duplicate match in the very next step.
`_fill_missing_company_names` never overwrites an existing value, and mutates `jobs` in
place. Logged as `... — Finished (N filled)`.

`_strip_company_from_title` is a related helper used only inside step 2's own
near-duplicate comparison (never for display) — it strips an already-normalized company
name back out of a title before comparing similarity, so `"Acme Corp - Data Scientist"`
still compares well against a clean `"Data Scientist"` from another source, exactly the
case a Google-sourced row hits once step 1 has extracted its company from that same
title text.

### Step 2 — Removing Duplicates & Fake Listings (`_remove_duplicates_list` / `_remove_fake_listings_list`)

Moved here from `run_search` (The user asked for a raw search to show every listing exactly
as fetched, and for Filter to be the one place all cleanup/filtering happens) — same
algorithm as before, just operating on a plain list of job dicts instead of a pandas
DataFrame: exact same URL → duplicate; same company+country with an 85%+-similar title
(via `difflib.SequenceMatcher`, now comparing the company-stripped titles from step 1's
helper above) → duplicate. `is_likely_fake` (dropped if it trips 2+ of the fake-listing
signals — see the original list further down) is unchanged. Logged as `... — Finished
(N removed)`, combining both dedup and fake-removal counts.

### Step 3 — Checking Language (detection only — **nothing is translated**)

**THIS STEP NO LONGER TRANSLATES, AND THE TEXT THAT SAID IT DID HAS BEEN REMOVED RATHER THAN
LEFT TO MISLEAD.** It described `langdetect`, `deep-translator`'s `GoogleTranslator`, a
4,500-character cap and a 30-worker thread pool. None of that runs. See
[3 · Language](#3--language) for what replaced it (`O-16`, `R-3`) and why.

What the step does now: detect each listing's language with **`lingua`**, restricted to the
languages this app can actually meet, and stamp `detected_language` and `needs_translation`
on the row. That is all. Every rule after it reads the posting **in its own language**, from
per-country, per-language vocabularies, which is what made the translator unnecessary — and
on the real Netherlands data removed 92% of what the DeepL bill would have been, because the
503 listings that fail `silent_about_english` are dropped before anything would have paid to
translate them.

`needs_translation` keeps its name, and it is still load-bearing: it is how
`rules.silent_about_english` knows a posting is not in English, which is the only rule that
cares. (The Jobs table had a **Language** column that showed the answer per listing; it was
removed once `English?` existed, and the data behind it stays on every row.)

Below `_MIN_LANGDETECT_CHARS` the answer is `unknown`, deliberately **not** `en` — see
[`_MIN_LANGDETECT_CHARS`](#_min_langdetect_chars--why-very-short-text-is-unknown-not-en).

### Step 4 — Applying Filters (**4** keyword rules, `FILTER_RULES_STEP_CHECKLIST`)

**Six became four**, and both removals are findings worth reading before changing anything
here: *Too senior* went with `T-14` (and it was the **second** of the two places the Level
deleted), and *Lacks English mention* was deleted earlier, for dropping a listing over
silence rather than over anything it said.

The four that run, in this exact order — see
[the content filters](#the-content-filters--exact-rules-in-exact-order) below for each one:

```
Work Location rule
Wants another language instead of English      (renamed with T-12 -- it deletes much less now)
Text-based sponsorship restriction
Unpaid
```

`Category` and `Seniority` are written onto every surviving row in this same loop, and
`English` beside them — the three classified columns, none of which deletes anything. There
is no "after translation" any more: `Category` is computed from the posting's own words, in
its own language, which is what `T-2` was about.

Once the loop finishes the checklist logs all four names as `Checked`. Logged as
`... — Finished (N removed)`.

### Step 5 — Claude Review (only if an Anthropic key is configured, `FILTER_CLAUDE_STEP_CHECKLIST`)

See [the Claude final pass](#the-claude-final-pass) below for the full detail. Skipped
entirely (no step logged at all) if no Anthropic key is set — **or if no résumé has been
chosen**, since every fact about the candidate now comes from it; the Log says so in amber
rather than running Claude against nobody. Once every survivor has been screened (or reused
from cache — see **Cross-run caching of Claude's decision** below), the checklist logs the
nine questions this part covers: can the work be done from where he lives, language,
pay, **what level it is pitched at — reported, not filtered** (`T-4`), is it a real job,
citizenship/residency, is it the job title searched for, university country, and who the
employer is. Logged as `... — Finished (N flagged, N
screened, N cached)`, plus an error count if any individual Claude call itself errored.

This part **decides only**. It no longer scores: the Match % moved to Step 5b, where it is
read against the résumé. The prompt it uses is the one belonging to Remote / Not Remote —
**two documents for the job pass, not eight** (`T-5`): rule 4 and the level paragraph were the
only things that differed between the Levels, and since rule 4 stopped filtering (`T-4`) all
four Levels share one text. Thesis and Internship keep their own pair each. All eight
`Job-Filter-Claude-Apify*.md` files beside the app are still mirrored byte-for-byte and still
checked by test 4.42 — four of them are simply identical to each other now.

**A consequence worth knowing before editing a prompt**: `_claude_screen_cache_key` hashes the
prompt text, so the key no longer varies by Level — one verdict serves all four, where the
same listing used to be asked about four times. Any prompt edit invalidates every cached
verdict and the next Filter re-bills them. That is the price of changing a rule, not a bug.

### Step 5b — Résumé Match (part two, `claude_screen/worth.py`)

Of what part one kept, how well does each listing match the résumé? One request per listing,
sent as one queued batch (half price), with the résumé in the system prompt and the job
title and Level on each listing. It writes `claude_match` (0–100), `apply_verdict`
(apply / check / skip), `apply_note`, `resume_strengths` and `resume_gaps`, plus its own
cache key — a listing whose text, title, Level and résumé are unchanged is never asked
again. A "skip", or a score under `RESUME_MATCH_MINIMUM` (36), is flagged for the review
dialog exactly like a part-one drop; nothing here deletes anything by itself.

This replaced a pass that judged every listing against a paragraph hard-coded in the file
("entry or junior level, in data, ML or AI") — written before the field became a title the user
types, and never updated when it did (fault M-2).

### Step 6 — Checking Sponsorship Visa

Runs on survivors of both the keyword-rule loop and Claude's pass. Fills in
`sponsorship_visa = 'Unknown'` for anything still unset, reclassifies
`NO_SPONSORSHIP_PROCESS_COUNTRIES` listings to `"Employer's Discretion"`, then runs
`_apply_sponsor_list_matches_to_jobs` (the real `SPONSOR_LIST_COUNTRIES` fuzzy-match
check, including its own cache-first company legal-name resolution — see [Sponsorship
Visa column](#sponsorship-visa-column) below) on the **full** kept list. No `N`-count
detail in this step's own log line (an empty `detail` after the pipe) beyond the
`GLOG:filter_step:sponsorship` lines it emits for sponsor-list loads and legal-name
cache-hit/fresh-lookup counts.

**Real bug fixed earlier this session**: this used to run only on `non_flagged_kept`
(excluding Claude-flagged listings still awaiting a decision in `ClaudeReviewDialog`),
under the same "don't spend real money on a likely-discarded listing" reasoning that
used to apply to the now-removed Company Popularity step right after it. That reasoning
doesn't actually apply here — the register fetch/match itself is free (a 30-day-cached
HTTP fetch plus a local string comparison) — so excluding flagged listings saved
nothing, while leaving a listing the user later keeps anyway (via the review dialog's
override) with a needlessly wrong `'Unknown'` badge that could have been computed for
free. Now runs on `kept` in full. (Legal-name resolution itself, moved into this step
this session, DOES make a real Claude call on a cache miss — see below for how that cost
is minimized.)

### Step 7 — Sorting Results

(Was Step 8 — the previous Step 7, "Assessing Company Popularity," was removed
entirely; see [Company Popularity column — built, then removed
entirely](#company-popularity-column--built-then-removed-entirely) above.)

If an Anthropic key is configured, the whole kept list is sorted by `claude_match`
descending (best match first, unscored listings last) — the score Step 5b wrote against
the résumé. Without a Claude key, the
original category sort (Part-Time → Internship → Thesis → Full-Time, Italy first) is
used instead — see [Match % column and sort](#match--column-and-sort-jobs-page) below.

### Language-detection short-text bug fix

The user reported suspicion that Filter was dropping genuinely-English listings for not
containing the literal word "English." Investigation found — and proved with a real,
reproducible test — that `langdetect` misdetects **short** text badly. Real, actual test
results: `'AI'`/`'AI'` → detected as **Hungarian**; `'Data'`/`'Data'` → **Indonesian**;
`'Remote'`/`'Remote'` → **Romanian**; `'🚀 Data Scientist 🚀'` → **Albanian**.

The failure chain: once a genuinely-English short listing gets misdetected as
non-English, it goes through `maybe_translate` (a near no-op, since it's already
English) and gets `was_translated=True` — which then feeds directly into
`lacks_english_mention()` (content filter rule 3). A real English job posting almost
never contains the literal word "English" anywhere in its text (it doesn't need to), so
it gets wrongly dropped by that rule.

**Fix**: `detect_language` now returns `'unknown'` (never even attempting
`langdetect.detect()`) for any combined title+description text under
`_MIN_LANGDETECT_CHARS = 40` characters:

```python
_MIN_LANGDETECT_CHARS = 40


def detect_language(row) -> str:
    text = f"{row.get('title') or ''} {row.get('description') or ''}".strip()
    if len(text) < _MIN_LANGDETECT_CHARS:
        return 'unknown'
    try:
        return detect(text)
    except LangDetectException:
        return 'unknown'
```

`'unknown'` is already treated identically to `'en'` everywhere translation-skip logic
is checked (`maybe_translate` skips translation for both), so a short listing simply
never risks being mis-bucketed either way, regardless of its real language.

Verified with a real before/after test: the same 4 short strings above all now correctly
return `'unknown'`, while real full-length English/German sample text still correctly
detects as `'en'`/`'de'`. Also verified the *full* bug scenario end-to-end: `'AI'`/`'AI'`
no longer gets translated at all, and `lacks_english_mention` now correctly returns
`False` (i.e. the listing is kept).

## The content filters — exact rules, in exact order

These only run when you click **Filter** (`reapply_filters`), never during a raw
search — specifically, this is **Step 4, "Applying Filters"**, of the 7-step
`reapply_filters` breakdown above. All of them read `f"{title} {description}"` (or similar) as one combined,
lowercased string — **title and description are always checked together as a single
piece of text, with no special priority between them** (see
[Design decisions](#design-decisions-and-things-that-were-tried-and-reverted) for why
an earlier "check title first, separately" design was built and then explicitly
reverted).

Filters run in this exact order; a listing dropped by an earlier one never reaches the
later ones:

### 1. Remote rule (`passes_remote_rule`)
- ~~If `location` mentions Milan/Milano or Turin/Torino → kept, no matter what work mode is
  mentioned.~~ **Removed by `T-23`:** no city is exempt.
- Otherwise: dropped if the text contains any of `on-site, onsite, on site, in-office,
  in office, in-person, office-based, office based, hybrid`.
- Dropped if it contains any of: `no remote, not remote, remote not available, remote
  work not permitted, remote work not available, without remote, remote is not,
  on-site only, onsite only, must be on-site, must work on-site, fully on-site,
  in-office only, in-person only, office-based only`.
- Dropped if there's a conflicting **location label** (see next section).
- Otherwise kept **only if** the text contains one of: `remote, wfh, work from home,
  100% remote, remote-first, remote only`.

### Location-label sub-check (`has_conflicting_location_label`)
Regex: `\b(?:role location|locations only|location only|locations|location)\s*:\s*([^\n\r]{0,120})`
(case-insensitive). If any match's captured value does **not** mention `italy`/`italia`
or a Milan/Turin name, the listing is dropped — a "Remote" tag next to `Location:
Germany` usually means "remote, but you must be based in Germany".

### 2. Requires a second language (`requires_language_besides_english`)
**This paragraph described two rules that no longer exist in this form; both were rewritten
and the old text is kept nowhere.** Read [3 · Language](#3--language) for the current rule
and `T-12` for why it deletes so much less than it did.

In short: there is no translation step any more, so nothing is read "after translation". The
posting is read in its own language, and it is dropped only when it demands a language the user
lacks **and never names English beside it** — *"Sehr gute Deutschkenntnisse"*, *"vloeiend
Nederlands"*. A posting that wants English **and** another language is kept and labelled
`English + Other` in the table, which is the user's own instruction (`T-12`, `T-13`).

### 3. Never mentions English at all (`rules.silent_about_english`)
Applies only to a posting the detector found is **not** in English, and reads the ORIGINAL
text, not a translation: the listing's own word counts, so "Engels" and "Englisch" are looked
for as well as "English" — of 553 non-English Netherlands listings, 47 said "Engels" and only
3 said "English". A posting with no description at all is exempt, for the same reason it is
exempt from the Work Location rule: there is no text for the word to appear in.

(The old `lacks_english_mention`, which ran after translation and deleted a listing for
silence, is gone. Its two constants are gone with it, and a test asserts they stay gone.)

### 4. Sponsorship restriction (`has_sponsorship_restriction`)
Dropped if the text contains any of (24 phrases): `e-verify, everify, not eligible for
immigration sponsorship, not eligible for sponsorship, no sponsor available, no
sponsorship available, will not sponsor, unable to sponsor, not able to sponsor, does
not sponsor, can not sponsor, cannot sponsor, no visa sponsor, no visa sponsorship,
sponsor is not available, sponsorship is not available, authorized to work without
sponsorship, no h1b, h1b not sponsored, must be a us citizen, us citizenship required,
green card holder, security clearance required, itar, export control`.

### 5. Unpaid (`is_unpaid`)
Dropped if the text contains any of (20 phrases): `unpaid, no salary, no pay, without
pay, volunteer, voluntary, no compensation, non-paid, nonpaid, no stipend, pro bono,
self-funded, self funded, expenses only, unwaged, no wage, unsalaried, gratis, without
remuneration, for college credit only, credit only, compensation: none`.

### 6. Seniority — **this rule no longer deletes anything** (`is_too_senior`)

**Read `T-14` and `T-4` before anything below.** Nothing is removed for its seniority in the
job pass. `rules.seniority_of` labels each listing `Intern` / `Junior` / `Mid` / `Senior` /
`Lead` / `Unspecified`, the Seniority column shows it, and its filter button narrows the view
without deleting. Claude's rule 4 reports the level in the `seniority` field and keeps the
listing.

`is_too_senior` itself is kept and still tested, because the **Internship and Thesis** modules
use it — and because deleting a working rule whose last caller went away is how a module
becomes unreachable (`L-2`). The description that follows is what it still matches, for those
two modules:
- Dropped if LinkedIn's own `seniorityLevel` field is exactly `director`, `executive`,
  or `mid-senior level`.
- Dropped if the text contains any of: `senior, sr., principal, manager, director, head
  of, chief, vp, vice president, president, team lead, supervisor, department head,
  leadership`.
- Dropped if the text matches "N+ years" for N = 3 through 10 (regex handles `5+
  years`, `+5 years`, `5 + years`).
- Dropped if the text matches a range like "3-4 years" through "9-10 years" — any range
  whose lower bound is already ≥3 (regex: `\b([3-9]|10)\s*-\s*([3-9]|10)\s*years?\b`,
  with the code additionally checking the high number is actually greater than the low
  number).

**Nothing else is filtered.** Employment type (Full-Time vs Part-Time vs Contract) is
purely informational (the `Type` badge), never a removal reason.

## The Claude final pass

If (and only if) an Anthropic API key is set in the wizard, after all the keyword
filters above run, **every survivor** gets sent to Claude one more time
(`claude_screen_one`, model `claude-haiku-4-5-20251001`) — this is **Step 5, "Claude
Review"**, of the 7-step `reapply_filters` breakdown above.

**Deliberately sequential, not parallelized** — unlike the actor calls in Search
(above) and the translation calls in `translate_many` (below), the Claude loop in
`reapply_filters` is a plain `for` loop: one job screened at a time, waiting for each
response before sending the next. The user explicitly asked for this when Search's actor
calls were parallelized, so Claude keeps behaving as a simple, predictable queue rather
than firing many requests at once — keeps output/log ordering clean and avoids tuning
concurrency against whatever Anthropic rate-limit tier the API key happens to be on.

**Prompt caching, added after a full-codebase token-cost audit**: `CLAUDE_SCREEN_SYSTEM_PROMPT`
below is thousands of tokens and was being sent as a plain string on every single call
in this sequential per-listing loop — full input-token price, every time, even though
it's byte-identical across the whole loop. `claude_screen_one` now sends it as its own
`system` content block with `cache_control: {"type": "ephemeral"}`. Only the first call
per ~5-minute cache window pays full price for the base prompt; every later call in the
same Filter run reads it at the much lower cached-input rate — a real, sizeable,
easily-avoidable cost for any Filter run over more than a couple of jobs. Confirmed
working with a real, live call: a second real Claude call in the same session showed
`cache_read_input_tokens=4994` in the API's own response usage metadata, meaning the
~5,000-token system prompt was read from cache rather than billed at full price again.
(`_assess_company_fame`'s own smaller system prompt was cached the same way while it
existed — see [Company Popularity column — built, then removed
entirely](#company-popularity-column--built-then-removed-entirely) for why that whole
feature, cache and all, was removed shortly after.)

**Three further cost-optimizations, added this session** — see the three subsections
below: the "breakdown" text Claude used to write on every call is gone entirely (never
read by anyone), company legal-name resolution moved out of this call into its own
disk-cached, dedup'd step, and Claude's own KEEP/DROP/MATCH decision is now cached
across Filter re-runs so an unchanged listing is never re-sent at all.

**The system prompt is no longer a short paraphrase — it's the user's own, much more
complete prompt**, kept verbatim in [`Job-Filter-Claude-Apify.md`](Job-Filter-Claude-Apify.md)
at the project root and mirrored exactly in `CLAUDE_SCREEN_SYSTEM_PROMPT`
(keep both in sync if either is edited).

**Real drift found and fixed during a comprehensive audit**: the two had already fallen
out of sync in three ways — `Job-Filter-Claude-Apify.md` still had Rule 9 Part A
(degree completion) as a live, active DROP rule (never updated when Part A was disabled
in `pipeline.py` earlier this session), Rule 8's keyword list still listed the 8
analytics-flavored terms already trimmed out of `KEYWORDS`/`TOPIC_KEYWORDS`/the real
`CLAUDE_SCREEN_SYSTEM_PROMPT`'s own Rule 8, and the entire "Output Format" section
(the `KEEP`/`DROP`/`MATCH` structure the app actually parses) was missing from the `.md`
file altogether. None of this affected the running app (only `CLAUDE_SCREEN_SYSTEM_PROMPT`
in `pipeline.py` is ever actually sent to Claude — the `.md` file is a pure
human-readable reference copy), but it meant the reference file no longer matched
reality. Re-synced.

It replaced the original 5-rule paraphrase
after Claude's real-world output was found to be inconsistent — the new version gives
Claude:
- The user's full real profile (residency, citizenship, languages, degree status, real
  experience/projects/skills) so it can judge fit and score a match honestly, never
  fabricating skills he doesn't have.
- The exact same keyword dictionaries the app's own keyword filters use for Remote,
  Language, Sponsorship, Compensation, and Seniority (rules 2, 3, 4, 6, 7) — so Claude's
  judgment lines up with the deterministic filters instead of a vague restatement of
  them.
- **4 additional rules the keyword filters don't cover at all**: Rule 1 (fake job / paid
  training program dressed up as a job), Rule 5 (citizenship/residency requirements,
  distinct from the Sponsorship rule — this is about the *applicant's* citizenship, not
  the company's ability to sponsor a visa), Rule 8 (Domain Fit — is this actually a
  Data/ML/AI-type role at all), and Rule 9 (Degree Completion / University Enrollment —
  originally two parts, catching "must already hold a degree" (Part A) or "must be
  enrolled at a university in country X" (Part B) requirements the user can't meet, with an
  Italy/university exception mirroring the Milan/Turin remote exception — **see below,
  Part A is now disabled**).
- An explicit instruction to judge by **meaning, not just exact keyword match** — the
  dictionaries are described to Claude as representative examples of a pattern, not an
  exhaustive list, so a differently-worded sentence with the same meaning still triggers
  the rule.

### Rule 9 Part A (degree completion) disabled

The user asked for Part A — dropping a listing that requires an already-completed degree —
to be disabled entirely, since he's a current student, not yet graduated, and this rule
was catching listings he'd genuinely be fine applying to. `CLAUDE_SCREEN_SYSTEM_PROMPT`'s
Rule 9 text now reads:

```
Part A -- Completed degree required: DISABLED, do not apply this part at all -- never DROP a
posting for this reason. (The user asked for this to be turned off. Original rule, kept here only
for reference in case it's ever turned back on: DROP if the text contains one of these phrases
and none of these exception words appear anywhere in the text ("pursuing", "currently
enrolled", "current student", "in progress", "expected graduation", "about to graduate",
"final year", "recently completed or currently pursuing"): "completed degree", "degree
completed", ...)

Part B -- Enrollment required at a university in a specific country:
- If the location includes Milan/Milano or Turin/Torino, or the requirement is explicitly for
  Italy/Italian universities -> skip this part, KEEP -- ...
- Otherwise, DROP if the text contains any of these: ...
```

The original Part A rule text is deliberately **kept inline, not deleted** — explicitly
marked "DISABLED, do not apply" with the original phrase list preserved for reference in
case it's ever turned back on, matching this doc's own "document what was tried and
reverted, don't just delete it" philosophy. Part B (university enrollment in a specific
other country, with the Italy/university exception) is completely unaffected and still
fully active. `FILTER_CLAUDE_STEP_CHECKLIST`'s Rule 9 entry is labeled just "University
enrollment rule" (not "Degree completion / university enrollment rule") to reflect that
only Part B is genuinely being checked now.

This also required confirming there was no *separate*, mechanical (non-Claude)
keyword-based version of this same check anywhere among the keyword-based Filter rules
(Step 4 above — six when this was written, four now: see `T-14`) — there wasn't; Rule 9 only ever existed inside
`CLAUDE_SCREEN_SYSTEM_PROMPT`, so disabling Part A there was the only place this needed
to change.

The full listing (not just the description) is still sent as one combined block —
title, company, location, platform-reported employment type/seniority level, and
description — via `_claude_screen_prompt`.

**Claude's response format** (enforced by an explicit "Output Format" section appended
to the prompt, needed so the app can reliably parse it):
```
KEEP
or
DROP: <reason in 10 words or fewer, naming which rule (1-9) it broke>
MATCH: <integer 0-100>
```
`claude_screen_one` parses line 1 for the KEEP/DROP decision and reason, and searches
the whole response for a `MATCH: N` line (regex, case-insensitive) to extract the match
percentage — returned separately from the KEEP/DROP decision so a percentage is
recorded **even for listings Claude flags to DROP** (so you can still see roughly how
good the technical fit was, independent of the hard-blocker reason).

### The "breakdown" text — removed entirely

The response used to have optional trailing lines with "a short breakdown of what
matches and what the real gaps are." A real grep across the whole `app/` tree
(`title|claude_match|company_legal_name|breakdown`) confirmed this text was never
stored on any job dict and never displayed anywhere in the UI — it was pure output
tokens, billed on every single Claude Review call, for something nobody ever read. The user
asked for it gone. `CLAUDE_SCREEN_SYSTEM_PROMPT`'s "Final Step" and "Output Format"
sections now explicitly say "no written breakdown or explanation... with nothing else,"
and `claude_screen_one`'s `max_tokens` dropped from `500` (`800` when it also resolved a
company name) to `100`, matching the now much shorter expected reply
(`KEEP`/`DROP: <reason>` + `MATCH: <int>`, nothing more).

### Company legal-name resolution — decoupled, cached, deduplicated

This used to run **inside** `claude_screen_one` itself (`resolve_company_name=True`,
a second, addendum-driven task tacked onto the same KEEP/DROP/MATCH call, with a real
`web_search` tool) — with **zero deduplication**: a company posting 5 listings
triggered 5 separate real, billed web searches for the exact same legal name, on every
single Filter run, forever. The user asked for this fixed with a persistent, country-organized
cache checked *before* ever considering a real query. Now:

- `claude_screen_one` no longer touches company names at all — it's back to a plain,
  fast KEEP/DROP/MATCH call with no `tools` kwarg.
- A brand-new, dedicated function, `_resolve_company_legal_name(client, company,
  country)`, with its own small, focused system prompt
  (`_COMPANY_LEGAL_NAME_SYSTEM_PROMPT`) and its own `web_search` tool, does exactly
  this one task and nothing else.
- A new disk cache, `company_legal_names.json` in `storage.DATA_DIR`
  (`_load_company_legal_name_cache`/`_save_company_legal_name_cache`), shaped
  `{country: {normalized_company: legal_name_or_null}}` — organized by country per
  The user's request, and with **no expiry**, since a company's officially registered legal
  name essentially never changes (unlike the sponsor lists themselves, which DO refresh
  every 30 days).
- The whole thing now lives entirely inside `_apply_sponsor_list_matches_to_jobs`
  (Step 6, see below) as a 3-pass design per country: (1) match each job's own raw
  company name against the register directly — free, no Claude, catches most real
  matches (including cases like "Booking.com" vs the register's "Booking.com B.V.",
  since suffix-stripped normalization already collapses those); (2) for survivors,
  build the set of **unique** remaining company names and resolve each **at most once**
  — cache hit first, a real Claude call only on a genuine miss, and the result (even a
  `None`/"couldn't resolve") is written back to the cache so the exact same company is
  never queried again on any future Filter run; (3) re-check survivors against the
  register using whatever legal name (cached or freshly resolved) is now available.
  With no Anthropic key configured, pass 2 is skipped entirely (no client to call) and
  survivors are just left at whatever `sponsorship_visa` they already had.

### Cross-run caching of Claude's KEEP/DROP/MATCH decision

The user flagged the real remaining waste directly: **every time Filter was clicked again,
every single listing — even ones already screened, with absolutely nothing changed —
was sent to Claude in full, again.** Fixed with a content-addressed cache stored right
on the job dict, no separate cache file needed:

- `_CLAUDE_SCREEN_PROMPT_VERSION` — a `sha256` hash (first 12 hex chars) of
  `CLAUDE_SCREEN_SYSTEM_PROMPT`'s own text, computed once at import time. Deliberately
  **not** a hand-maintained version counter the user would have to remember to bump — any
  future edit to a rule automatically changes this hash.
- `_claude_screen_cache_key(job)` — hashes `_CLAUDE_SCREEN_PROMPT_VERSION` together
  with the exact same per-listing prompt text `_claude_screen_prompt(job)` builds
  (title/company/location/platform/employment_type/seniority_level/description). This
  one hash captures **both** invalidation triggers the user cared about in one mechanism:
  a rule change (prompt version changes) and a content change (a re-fetched listing
  with different text) both correctly force a fresh screen; unchanged content *and* an
  unchanged ruleset hash identically and correctly skip the real API call.
- After a successful (non-errored) screen, `reapply_filters` stores
  `job['claude_screen_cache_key']`, `job['claude_screen_drop']`, and
  `job['claude_screen_reason']` on the job dict (alongside the existing
  `job['claude_match']`). An **errored** call deliberately does NOT update the cache
  key — a transient network/API failure must be retried on the next Filter run, never
  silently frozen in as "no decision" forever.
- On the next Filter run, before calling Claude at all, the loop recomputes the cache
  key for the job's *current* state and compares it to the stored one. A match skips
  the real API call entirely and reuses the stored decision — including correctly
  re-populating `claude_flagged` (with its stored reason) for a listing that was
  previously flagged for DROP, so `ClaudeReviewDialog`'s confirm/override UX behaves
  identically whether the decision came from a fresh call or a cache hit.
- The `FILTER_STEP_DONE:claude` log line's detail changed from `"N flagged"` to `"N
  flagged, N screened, N cached"`, and a `GLOG:filter_step:claude` info line reports
  the cache-hit count too, so it's visible in the Log exactly how much of a given
  Filter run's Claude Review step was real API work vs. free reuse.

Verified with real, live Claude calls (not just mocked ones): running `reapply_filters`
twice in a row on the same unchanged job showed the real API call happen once on the
first run and **zero** real calls on the second, with `claude_match` correctly
preserved from the cached decision both times.

**Crucially, Claude does not remove anything by itself.** Every listing it flags is
collected (with its reason) and shown to you in a **review dialog**
(`ClaudeReviewDialog`) after the Filter run finishes:

- A table lists every flagged listing: row number, title, company, Claude's reason.
- A text field lets you type the row numbers you want to **keep anyway** (comma-
  separated), overriding Claude.
- **"Remove Flagged"** — deletes everything Claude flagged, except the numbers you
  typed to keep.
- **"Cancel (keep everyone)"** — aborts the whole Claude removal step; nothing gets
  removed, all Claude's flags are ignored.

Every listing Claude flags is also logged **in red** in real time as it's found
(`Row "Title" (Company) flagged by Claude — <reason>`). If Claude's API call itself
errors (invalid key, no credits, network issue), that listing is kept automatically
(fails open — a broken API call must never silently delete data), no match percentage
is recorded for it (shown as `—` in the Jobs table), and the error is logged in red. If
every check succeeds with zero API errors, a **green** success line is logged at the
end.

### Match % column and sort (Jobs page)

Every job dict gets a `claude_match` field (0-100, or `None` if Claude wasn't run or
that one call errored) set during the Claude pass above. The Jobs table
([`jobs_page.py`](app/ui/jobs_page.py)) shows this as a **"Match %" column, immediately
left of Apply**, colored:
- **80-100%** → strong green
- **50-79%** → yellow
- **below 50%** → red
- no score available → `—`, no color

When an Anthropic key is configured, `reapply_filters`'s final sort switches from the
usual category-based sort to sorting the **entire kept list by `claude_match`,
descending** — best match first, listings with no score (API error) sorted last. Without
a Claude key, the original category sort (Part-Time → Internship → Thesis → Full-Time,
Italy first) is unchanged.

## The Job Search page

**Columns**, in order — the three classified ones (Seniority, Type, English?) sit together
and in that order, because that is the order the user groups by:

| # | column | what it is |
|---|---|---|
| 0 | `#` | row number |
| 1 | Title | |
| 2 | Company | |
| 3 | Country | |
| 4 | Sponsorship Visa | badge |
| 5 | **Seniority** | badge · Intern/Junior/Mid/Senior/Lead/Unspecified · `T-3`, `T-10` |
| 6 | **Type** | badge · a `"... Startup"` suffix marks a Startup Websites Search find, see [Company Popularity column](#company-popularity-column--built-then-removed-entirely) |
| 7 | **English?** | badge · English only / English + Other / Other only · `T-12`, `T-13` |
| 8 | Details | platform · location · posted date |
| 9 | Match % | the résumé score, only populated when a Claude key is configured |
| 10 | Worth it? | apply / check first / skip, from part two of Claude |
| 11 | Found as | which searched title found this listing |
| 12 | Apply | |
| 13 | Remove | |

**There is no Language column.** It showed what the advert was *written* in and was removed
the moment `English?` existed — *owner's note: with an English? column present, delete the Language column* — because
`English?` answers the question it was kept for: what the advert asks of the reader. Only the
column went. `detected_language` and `needs_translation` are still stamped on every row and
`silent_about_english` still reads them, so no verdict changed; a test asserts both the
column's absence and the data's presence. Every constant after `ENGLISH_COLUMN` moved down
one (`DETAILS_COLUMN` 9→8 … `REMOVE_COLUMN` 14→13), the fourth time this file has had `M-9`.

Each of Country, Sponsorship, **Seniority**, **Type**, **English?** and Found as has its own
Excel-style `ColumnFilterButton` above the table: the values actually present, with counts,
and you tick the ones you want. They change what is **displayed** and delete nothing.

**Real crash bug found and fixed**: the Details column built its text with
`job.get('platform', '').capitalize()` — that default only applies when the key is
**missing** entirely; a job dict with `'platform'` explicitly present but `None` (a
plausible shape for an old or hand-edited `jobs.json` row, since that file is never
schema-migrated on load the way `applications.json`'s `status` field is) crashed the
whole Jobs page with `AttributeError: 'NoneType' object has no attribute 'capitalize'`.
Fixed to `(job.get('platform') or '').capitalize()`, matching the same `or ''` pattern
already used for `location`/`posted_date` right next to it. Found via a real
`JobsPage.show_jobs()` render test with a synthetic all-`None` job row.

- **Click anywhere on a row** (except Apply/Remove) opens the listing in your browser.
- **Apply** → shows the JD and lets you attach documents; confirming logs it to My
  Applications **and automatically removes that job from the Job Search list** (since
  it's now tracked as an application instead).
- **Remove** → deletes that one listing permanently, no confirmation (for bulk cleanup
  use the Filter button or Clear Search instead).
- **Show only** — a dropdown checklist of the same role-type keywords used in the
  search query (Data Scientist, Machine Learning, AI Engineer, ...). Picking any of them
  filters what's **displayed** — this never touches saved data, it's purely a view
  filter. **Reset** clears the selection.
- Row count shown above the table (`N listing(s)`, or `N of M listings shown (display
  filter active)`).
- **New Search** → opens the wizard, starts a fresh Phase 1 search; new results are
  added **on top** of whatever's already saved (nothing from a previous search is ever
  lost by running a new one).
- **Filter** → runs Phase 2 (see above) on everything currently saved.
- **Clear Search** → see [below](#clear-search--clear-my-applications).

## The My Applications page

**Columns:** `#`, Title, Company, Country, Sponsorship Visa (colored badge), Days Ago,
Applied On, Documents, Status, Remove.

- **Days Ago** and **Applied On** are both derived from the same stored `apply_date`
  (format `dd/mm/yyyy`, parsed leniently — also accepts the older `dd/mm/yyyy HH:MM`
  format from before the time-of-day was dropped from newly-created records). Days Ago
  shows "Today", "1 day ago", or "N days ago".
- **Documents** → a **Download** button that builds a `.zip` on demand
  (`storage.build_documents_zip`) containing `Job Description.txt` plus every attached
  document, all nested inside one folder named after the zip itself (so extracting
  produces one tidy folder, not scattered files) — default filename
  `{Company}_Documents.zip`, default location your Downloads folder.
- **Status** → a colored button showing the current status (text is naturally centered
  since `QPushButton` centers its label by default), with a `QMenu` attached listing
  **Processing** (yellow `#F5A623`, default), **Accept** (green `#2ECC71`), **Reject**
  (red `#E74C3C`) — click it to open the menu and pick one. Changing it saves instantly.
  **This was originally a `QComboBox`** made `setEditable(True)` with a read-only
  centered `QLineEdit` purely to center the text — that broke the dropdown, because an
  editable combo box only opens its popup when you click the tiny arrow, not anywhere
  on the widget. Replaced with a plain button + menu, which is both centered and fully
  clickable everywhere. If a future centering need comes up for a `QComboBox` again,
  don't reach for `setEditable(True)` — it silently breaks click-to-open.
- **Remove** → deletes that application record and its copied documents folder.
- **Clear My Applications** → see below.
- Row count shown above the table (`N application(s)`).
- Click anywhere on a row (except Documents/Status/Remove) to reopen the original
  listing.

## The Log panel

Always-visible, scrollable, monospace log at the bottom of the window (both pages).
Every meaningful step gets a timestamped line: token verification, per-actor-call
status with elapsed time, translation progress, Claude drop reasons, search/filter
completion, applications, removals, exports, errors. Supports four colors via
`LogPanel.log(message, level=...)` / `LogPanel.log_keyed(...)` (`LOG_COLORS` in
`app/ui/log_panel.py`):

- `'info'` (default) — green (`#8ee08e`)
- `'error'` — red (`#ff5c5c`) — used for search/filter failures and every Claude DROP
- `'success'` — green (`#4caf50`, brighter than default) — used when Claude finishes
  with zero API errors, and for every "genuinely connected/succeeded" step line
- `'warning'` — yellow (`#e0b400`) — used for the various "here's what to check
  yourself" warnings described throughout this doc

Implemented via `QTextCursor` + `QTextCharFormat` on a `QPlainTextEdit` (which, despite
the name, still supports per-run character formatting through its text cursor). Has a
**Clear Log** button, which also stops every still-running `QTimer` and clears all of
the nesting state described below (`_line_blocks`, `_group_anchor`, `_group_parent`).

`MainWindow._on_progress_log` inspects each progress message for an `ERROR:`,
`SUCCESS:`, or `WARNING:` prefix (set by the pipeline functions) and strips it before
logging with the matching color; anything without a prefix logs at the default info
color. A large block of **structured, keyed** message prefixes (`TOKEN_CHECK_*`,
`PREFLIGHT_*`, `KNOWN_SITES_*`, `STARTUP_SITES_*`, `DEEP_CRAWL_*`, `DIRECT_SITE_*`,
`DIRECT_API_*`, `MANUAL_ASSIST_*`, `GLOG:*`, `GOOGLE_STAGE_FAILED`, `FILTER_*`,
`PLATFORM_*`, `LOCATION_*`) is parsed *before* that generic convention — each one
routes to `LogPanel.start_timer_line`/`stop_timer_line`/`log_section_header`/
`log_keyed` instead of a plain `log()` call, which is what builds the nested,
live-ticking structure described next. `GLOG:<group>|<level>|<text>` is the generic
one of the bunch — a one-shot, nested status line for anything that doesn't need its
own live-ticking header (see "Real inconsistency found and fixed" below).

### Nested "Object" redesign — real grouping and live per-second timers

This session the Log panel gained real nesting/grouping support, so a section like
"Google" or "Filter" reads like a collapsed object with its own live-ticking sub-steps
nested underneath it, instead of a flat stream of lines in arrival order. The mechanism
(`app/ui/log_panel.py`):

- **`_line_blocks: dict[str, QTextBlock]`** — key → the exact `QTextBlock` holding that
  key's most recent `log_keyed()` line, so a later call with the same key updates that
  line **in place** (its position in the document never changes) instead of appending a
  new one. A `QTextBlock` is a stable handle to its own paragraph, unlike a plain block
  number/index — it stays valid even as other blocks are inserted/removed elsewhere in
  the document, which matters once a line can be inserted in the *middle* of the
  document (next point), not only at the very end.
- **`_group_anchor: dict[str, QTextBlock]`** — group name → the block *after which* the
  next new line for that group should be inserted. This is what keeps e.g. one
  platform's own location lines visually contiguous under its own header even though
  several platforms run concurrently and their real completion order interleaves —
  without it, a new line always landed at the absolute end of the document, so two
  platforms running in parallel would interleave their lines together instead of each
  staying grouped under its own header.
- **`_group_parent: dict[str, str]`** — child group → parent group, recorded whenever a
  section header is created nested under a parent (the `group` parameter on
  `start_timer_line`/`log_section_header`), e.g. `{'preflight': 'platform:Google'}`.
- **`_propagate_anchor(key, block)`** — sets `key`'s own anchor to `block`, then walks
  *up* the parent chain via `_group_parent` setting every ancestor's anchor to `block`
  too, so the next sibling section inserted anywhere in that ancestry lands after this
  entire subtree, not just after this one line. This is what makes multi-level nesting
  (e.g. a Pre-API Check item, nested two levels under "Google") correctly push every
  ancestor's insertion point forward, not just its immediate parent's.
- **`start_timer_line(key, label, group=None)`** — logs a new line with a live `m:ss`
  elapsed-time counter that ticks up once per second, entirely locally in the UI (a
  `QTimer`, not tied to how often the backend actually reports progress). `group`
  (optional) nests this header itself under a *parent* group — separate from `key`,
  which is always also registered as this header's own anchor regardless of `group`, so
  its own future children (logged with `group=key`) insert right after it.
- **`stop_timer_line(key, label, suffix='', level='info')`** — stops the ticking
  `QTimer` and writes one final line with the elapsed time frozen plus an optional
  suffix (e.g. `' — Completed'`). A safe no-op if `key`'s timer was never started (or
  was already stopped) — several call sites rely on this (see `GOOGLE_STAGE_FAILED`
  below) so they can unconditionally try to stop several timers at once.
- **`log_section_header(key, message, level='info', group=None)`** — like `log_keyed`,
  but also registers `key` as an anchor for its own future children, for a static
  sub-header with no live progress to tick (no `QTimer` involved at all).

**Real bug found and fixed**: `_tick_timer_line` used to do `self._group_anchor[key] =
block` on every single 1-second tick. Since `log_keyed`'s in-place-update path returns
the *same* `QTextBlock` every tick (only the text changes, never the position), this
looked harmless — but it wrongly reset a **parent** group's anchor back to the parent's
own header position on every tick, even after deeper-nested children had already pushed
that anchor forward via `_propagate_anchor`. Concretely: `'platform:Google'` ticks once
a second for the whole Google phase while deeper sections (Pre-API Check's own items,
Known Websites, etc.) are still being added underneath it — each of those pushes
`_group_anchor['platform:Google']` forward so the *next* sibling section lands after
them. Overwriting it back to the header's own block on every tick undid that forward
push moments later, so whichever section got added right after an unlucky tick landed
back up at the header instead of after the section that was actually added last.
**Confirmed via a real screenshot bug report** — a "Known Websites" line appearing in
the middle of "Pre-API Check"'s own API-check child lines, instead of after all of
them — and **reproduced/fixed with a real widget test** (interleaving `_tick_timer_line`
calls between child insertions). **Fix**: removed that line entirely from
`_tick_timer_line` — an in-place-updated block's position never actually moves, so no
anchor update was ever needed on tick at all.

**A second, real instance of the exact same bug class was found in `stop_timer_line`**
during a later full-codebase audit — it ended with `self._group_anchor[key] = block`
too, which is wrong for the identical reason: if a child was already logged under
`group=key` *before* the corresponding `stop_timer_line(key, ...)` call fired (e.g.
Direct Site Search's own yellow "Checking domain..." lines, logged right after
`start_timer_line` and well before the real crawl call returns), this line would reset
that group's anchor back to the header's own position, discarding the forward progress
those already-added children made — so the *next* sibling section (e.g. "Direct API
Search") would insert itself wedged between the header and its own already-existing
children instead of after all of them. It was harmless purely by accident of the
current call ordering elsewhere (nothing else happened to log a child before its own
`stop_timer_line` fired) — not by design. **Fix**: the exact same one as
`_tick_timer_line` — remove the anchor touch entirely, don't replace it with anything.
Re-verified with a real widget test reproducing "Direct Site Search"'s actual
before-and-after-stop child ordering.

**Real bug found and fixed in the same audit: nothing ever reset `_line_blocks`/
`_group_anchor`/`_group_parent` between two separate Search or Filter runs in the same
session** (only the "Clear Log" button did). Since every structured/keyed log line uses
a stable key (`'filter'`, `'known_sites'`, `'platform:Indeed'`,
`'location:Indeed:Italy'`, ...), running Search or Filter a second time reused the
*first* run's keys — so `log_keyed`'s in-place-update path silently rewrote the old run's
lines (wherever they sat in the scrollback) instead of appending fresh ones, making a
completed section visually "resurrect" and start ticking again at its old position,
with anything logged in between (e.g. "Applied to...") left stranded below it. This is
a routine scenario, not a rare edge case — the whole point of the Filter button is being
re-clickable any time a rule changes. **Fix**: `LogPanel.reset_keys()` — clears all
key/anchor tracking (stopping any leftover `QTimer`s too) *without* touching the visible
log text — called from `MainWindow.start_search`/`handle_filter_existing` right before
each new run starts. Verified with a real widget test: without the fix, a second run's
lines land *before* something logged in between; with it, they correctly land after.

### What the Google section actually looks like in the Log

```
Google  0:XX — Completed
    Pre-API Check  0:XX — Completed for Finland - Norway - Netherlands
        → Google Search actor | OK
        → API | remotive.com | Global | OK
        → API | europa.eu (EURES) | Finland | OK
    Known Websites  0:XX — Succeed  $0.15
        → finn.no | Succeed | 12 job(s) found
    Startup Websites Search  0:XX — Succeed  $0.15
        → scaleupjobs.nl | Succeed | 4 job(s) found
    Deep-Crawl  0:XX — Succeed  $0.42
        → finn.no | Succeed | 7 new page(s) found
    Direct Site Search  0:XX — Succeed  $0.00
        → Checking finn.no for Oslo: https://www.finn.no/job/search?q=...
        → finn.no for Oslo: 5 individual job posting(s) found.
    Direct API Search  0:XX — Completed
        → Checking arbetsformedlingen.se for Sweden (direct API call)
        → arbetsformedlingen.se for Sweden: 12 individual job posting(s) found.
    Manual-Assist Search  0:XX — Completed
        → Opening a real browser for work.turing.com (Global): https://work.turing.com/jobs?search=...
```

**Real inconsistency found and fixed in a later audit**: Direct Site Search's own
per-domain checking/success/error lines, every direct-API source's lines (Sweden/
Germany/Jooble/Reed/France Travail/EURES/Remotive/RemoteOK/arbeitnow.com/
SwissDevJobs/JobCloud), Manual-Assist's per-site lines, and the Sponsorship Visa list
load/refresh lines all used to go through the plain `WARNING:`/`SUCCESS:`/`ERROR:`
convention — which routes to a flat, unindented `LogPanel.log()` call always appended
at the absolute end of the document, so none of them ever actually appeared nested
under their own section the way Known Websites/Startup Websites/Deep-Crawl's own
per-site result lines already did (this is exactly why the example above, before this
fix, showed nothing under "Direct Site Search" at all). **Fix**: a new generic
`GLOG:<group>|<level>|<text>` progress-message prefix — each such line gets its own
unique, never-updated `log_keyed()` key (so it's still inserted exactly once, in
arrival order) with the right `group`, nesting it properly. Direct API Search and
Manual-Assist also gained their own `DIRECT_API_START`/`_END` and
`MANUAL_ASSIST_START`/`_END` header timers (nested under "Google", same as Known
Websites/Deep-Crawl/Direct Site Search) so they read as their own real sections too,
instead of just being lines that happened to fall between other sections. Separately,
`_apply_sponsor_list_matches_to_jobs` (called from Filter's "Checking Sponsorship
Visa" step) used to always be called with `progress_cb=None`, so its own
"Sponsorship Visa list for X loaded/could not be refreshed" lines never reached the Log
at all despite the plumbing already existing — now wired through and nested under
that step.

- **Pre-API Check's completion suffix changed** from a `(passed/checked)` count to
  `for {countries/cities dash-joined}` (`PREFLIGHT_END:status|locations` in
  `_on_progress_log`, `locations.replace('-', ' - ')`) — status (green success / red
  error) still drives the line's color exactly as before; only the trailing text
  changed, per the user's ask that the suffix name *what* was checked, not *how many*
  checks passed.
- **"Known Websites" and "Startup Websites Search" come from the exact same single,
  combined Google Search actor call.** `KNOWN_SITES_START`/`STARTUP_SITES_START` both
  fire right before that one call (`run_actor_and_fetch(GOOGLE_SEARCH_ACTOR, ...)`), and
  `KNOWN_SITES_HEADER:`/`STARTUP_SITES_HEADER:` both fire right after it returns, both
  carrying the exact same `usageTotalUsd` — there is no way to split cost per sub-stage
  of one combined call, so both sections' own cost line is genuinely identical, by
  design, not a bug. Their own per-site result lines (`KNOWN_SITE_RESULT:`/
  `STARTUP_SITE_RESULT:domain|count`) are only logged once the whole call is done (no
  live per-site progress is possible either, for the same reason), and only for sites
  that actually returned something.
- **Deep-Crawl and Direct Site Search each have their own real, separate
  `usageTotalUsd`**, from their own separate actor calls (`_deepen_google_results`,
  `_run_direct_site_searches`).
- **`GOOGLE_STAGE_FAILED`**: if anything fails anywhere inside the whole Google stage,
  this message stops any still-ticking Known Websites/Startup Websites Search/
  Deep-Crawl/Direct Site Search timer with a red `' — Failed'` suffix, so nothing ticks
  forever just because the failure happened in a different sub-stage. Since
  `stop_timer_line` is a safe no-op for a timer that was never started, `_on_progress_log`
  can unconditionally try to stop all four.
- **Deep-Crawl's per-site breakdown counts NEW pages added** per known-site domain
  (`domain_added_counts`, the pages `_deepen_google_results` discovered by following a
  listing page's own links) — a genuinely different number from Known Websites' own
  count, which is job postings *found* in the original combined query
  (`known_site_counts`).

### What the Filter section actually looks like in the Log

See [Phase 2 — what the Filter button does](#phase-2--what-the-filter-button-does-reapply_filters)
below for the full, current 7-step breakdown this section reflects — this is a major
restructure from the old flat, ungrouped Filter progress-message style. Same nested
pattern as Google: one header timer (`'filter'`), with each of the 7 steps as its own
nested, independently-ticking `Running → Finished` timer underneath it
(`FILTER_STEP_START:key|label` / `FILTER_STEP_DONE:key|label|detail`, `group='filter'`),
and — for the two steps that run a real per-rule loop across every listing rather than
one discrete action — a static checklist of the rule names logged right before that
step's own `FILTER_STEP_DONE` (`FILTER_STEP_ITEM:key|label`, `group='filter_step:{key}'`).

## Clear Search / Clear My Applications

Both are **deliberately hard to trigger by accident** — a red button that opens a
`TypeToConfirmDialog` (`app/ui/confirm_dialog.py`): the destructive "Delete Everything"
button stays disabled until you type the *exact* phrase shown (`Clear My Search` or
`Clear My Applications`) into a text field. No partial match, no case-insensitivity —
exact string equality only.

- **Clear Search** wipes `jobs.json` to an empty list.
- **Clear My Applications** wipes `applications.json` to an empty list **and** deletes
  the entire `documents/` folder (recreating it empty), so no orphaned attached files
  are left behind.

## Excel export

**Export Excel** (top-right of the navbar) opens a **Save As** dialog (not a bare
folder picker — an earlier version used `getExistingDirectory`, which was confusing;
now `getSaveFileName` with default name `RoleHound_Export.xlsx` in your Downloads
folder). Whatever base name you choose, two files are written next to it:
`{name}_Jobs.xlsx` and `{name}_Applications.xlsx`.

Both are built with `app/excel_export.py` using `openpyxl` directly (not
`pandas.to_excel`, which has no styling) for a genuinely professional look:

- Colored header row (`#5B8CFF`, the app's accent blue, white bold text), frozen
  (`freeze_panes='A2'`), with Excel's native auto-filter enabled.
- Zebra-striped body rows (`#F2F5FC` on even rows).
- **Type** (Jobs sheet) and **Status** (Applications sheet) are colored badge cells
  using the exact same hex colors as the desktop app (`CATEGORY_BADGE_COLORS` /
  `STATUS_COLORS`) — the Jobs sheet's **Type** cell text goes through
  `pipeline.display_category`, same as the desktop Jobs page, so a startup-stage
  listing shows `"... Startup"` there too (the color still comes from the plain base
  category).
- **Link** column is a real clickable hyperlink (`Open ↗`), not just text.
- Description/Job Description columns use wrap-text with a generous row height (42px)
  so the JD is actually readable, not truncated.
- Thin light-gray borders throughout, Calibri font.

**Jobs sheet columns**: Title, Company, Country, Sponsorship Visa, Type, Platform,
Location, Posted Date, Link, Description.
**Applications sheet columns**: Title, Company, Country, Sponsorship Visa, Applied On,
Documents (file count), Status, Link, Job Description.

### Real, serious crash bug found and fixed: Export Excel broke on almost every real export

Found during a full comprehensive-test pass (a real `build_jobs_workbook` call, not just
reading the code): `SPONSORSHIP_BADGE_COLORS['Unknown']` (and, at the time, the
since-removed `FAME_BADGE_COLORS['Unknown']`) in `app/styles.py` were `'#555'` — a
3-digit CSS-shorthand hex color. Qt's `QColor` (used for the same badge everywhere in
the desktop UI) accepts that shorthand just fine, but `openpyxl`'s `Color`/`PatternFill`
(used by `excel_export.py`'s `_badge_cell`) does **not** — it requires an exact 6-digit
(RGB) or 8-digit (ARGB) hex string, and raised `ValueError: Colors must be aRGB hex
values` the moment it tried to color a cell for either value. Since `'Unknown'` is the
single most common Sponsorship Visa value in real usage (the default for every country
without a real sponsor-list source), this meant **Export Excel crashed on almost every
real export**, caught by `MainWindow.handle_export`'s own `except Exception` (so it
failed with a reported error rather than silently, but still a full, reproducible break
of a core feature). **Fix**: changed to the full 6-digit `'#555555'` (identical color,
just openpyxl-safe). Verified with a real `openpyxl.Workbook` build (crashed before the
fix, succeeded after) and re-confirmed through the real `handle_export` code path with
real fetched-and-filtered job data.

## Sponsorship Visa column

A `Sponsorship Visa` column (Yes / Unknown / Employer's Discretion, colored badge —
green for Yes, gray for Unknown, purple `#5c4fa8` for Employer's Discretion) was added
to the Job Search table, the My Applications table, and both Excel export sheets, right
after Country. The user's request was specific: for each country, find
either (a) a job board that already tags its own listings as visa-sponsored, or (b) an
official list of visa-sponsoring companies to cross-reference each listing's employer
against — and default to `Unknown` (never guess "No") wherever neither exists yet for a
country.

**Currently implemented: type (a), via `arbeitnow.com`.** `_fetch_arbeitnow_sponsorship`
in `pipeline.py` calls the free, keyless `GET
https://www.arbeitnow.com/api/job-board-api?visa_sponsorship=true` endpoint — a job
board that already self-tags every listing it returns as visa-sponsored, no
cross-referencing needed. Confirmed with a real call: 140 genuine listings, fields
`slug`, `company_name`, `title`, `description`, `remote`, `url`, `tags`, `job_types`,
`location`, `created_at`. Every row it returns gets `sponsorship_visa = 'Yes'` directly,
is filtered client-side by the searched role term (title/description/tags), and is
dropped entirely if its free-text `location` can't be mapped to one of the countries
this app knows about (`_arbeitnow_location_to_country`, a hint table covering roughly 20
UK/Germany/Australia/Netherlands/Austria/Switzerland/France/Spain/Canada/US city and
country names) — the app never guesses a country for one of these rows. This runs
unconditionally in `_run_direct_api_searches` (no country/city gating), right after the
RemoteOK block.

Every other row from every other source (Indeed, LinkedIn, Glassdoor, Google, every
other direct-API integration, manual-assist) gets `sponsorship_visa = 'Unknown'` by
default — added once, uniformly, right after `df['Category'] = df.apply(categorize,
axis=1)` in `run_search`, so it applies regardless of which platform actually found the
listing:

```python
if 'sponsorship_visa' not in df.columns:
    df['sponsorship_visa'] = 'Unknown'
else:
    df['sponsorship_visa'] = df['sponsorship_visa'].fillna('Unknown')
```

**Type (b), the official company-list countries — now implemented for 4 countries,**
via `SPONSOR_LIST_COUNTRIES = {'Netherlands', 'United Kingdom', 'United States',
'Canada'}`. Every listing whose `country` is one of these gets its employer
fuzzy-matched (`_normalize_company_name`, stripping legal-entity suffix words like
`bv`/`gmbh`/`ltd` so "Booking.com" and "Booking.com B.V." compare equal) against that
country's real, official register — a match sets `sponsorship_visa = 'Yes'`. If the raw
ad text doesn't match closely enough on its own, `_apply_sponsor_list_matches_to_jobs`
falls back to resolving the company's real legal name (cache-first, at most one real
Claude call ever per unique company — see **Company legal-name resolution — decoupled,
cached, deduplicated** above) and re-checks with that instead.

- **Netherlands** (`_fetch_ind_nl_sponsor_list`) — IND's "Register of Recognised
  Sponsors" (~12,900 companies), scraped from its own HTML table.
- **United Kingdom** (`_fetch_uk_sponsor_list`) — the Home Office's real, genuinely
  downloadable CSV register. Its URL is dated (changes on every republish, e.g.
  `...-2026-08-28.csv`), so the real download link is found by regex against the
  gov.uk publications page itself rather than hardcoded. Confirmed via a real
  fetch+parse: 142,988 data rows (one per organisation+immigration-route combination)
  collapsing to 127,464 unique organisation names, matching the Home Office's own
  reported ~127,500 figure.

**Netherlands and UK are both a genuine, legally-mandatory employer-side gate** — a job
offer from a company that isn't on that specific list literally cannot result in that
visa. **United States and Canada, newly added this session, are a different shape**:
neither the US H-1B system nor Canada's LMIA system legally *requires* pre-approval —
any US employer can technically file an H-1B petition, and any compliant Canadian
employer can apply for an LMIA. So a `'Yes'` badge for these two means "this company has
real, recent, official *filing history*," not "this company is legally certified" — a
softer signal than NL/UK's, but still genuinely meaningful (not a guess).

- **United States** (`_fetch_uscis_h1b_sponsor_list`) — real, official, downloadable
  per-fiscal-year CSVs from USCIS at a predictable URL pattern
  (`https://www.uscis.gov/sites/default/files/document/data/h1b_datahubexport-{year}.csv`),
  combining the last 5 available fiscal years (`_USCIS_H1B_YEARS = [2023, 2022, 2021,
  2020, 2019]` — the archive doesn't go past 2023 at this URL pattern, confirmed via
  real 404 checks on 2024/2025/2026). Confirmed via a real, live, full end-to-end fetch:
  **131,841 unique real employer names**.
- **Canada** (`_fetch_canada_lmia_sponsor_list`) — Canada's real, official open-data
  LMIA employer dataset on `open.canada.ca` (a CKAN instance, dataset id
  `90fed587-1364-4f33-a9ee-208181dc0b97`). There's no single stable "latest file" URL —
  one resource is published per quarter, English/French XLSX pairs since ~2023Q4, CSV
  before that — so the real, current resource URLs are discovered dynamically via
  CKAN's own real JSON API (`package_show`) on every refresh, never hardcoded. Only the
  most recent `_CANADA_LMIA_QUARTERS = 8` English XLSX resources (~2 years) are used.
  Parsed with `openpyxl` (already a project dependency, used by `excel_export.py`) —
  real structure confirmed: row 1 is a report title spanning all columns, row 2 is the
  real header (`'Province/Territory', 'Program Stream', 'Employer', ...`), data from
  row 3.

**A real, genuinely interesting technical obstacle was found and solved along the way**:
both USCIS' file endpoint and open.canada.ca's file-download endpoint sit behind a WAF
that specifically blocks Python's `requests` library — confirmed via direct, repeated,
controlled testing: `requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})` gets a
403 from USCIS, or open.canada.ca's own tiny "Request Rejected" HTML page, even with a
full, realistic browser header set (`Accept`/`Accept-Language`/`Referer`, not just
`User-Agent`) — while the **exact same URL** succeeds immediately through `curl`
(confirmed with both Git Bash's curl and, separately, Windows' own built-in `curl.exe`,
confirmed present at `C:\Windows\system32\curl.exe` on Windows 10 1803+/11 by default).
This is almost certainly TLS/HTTP client fingerprinting (e.g. Akamai Bot Manager, common
on `.gov` sites) rather than anything about the actual header content. **Fix**: a new
shared `_curl_get(url, headers=None, timeout=90)` helper in `pipeline.py` that shells
out to `curl.exe` via `subprocess` instead of using `requests` — used by only these two
fetchers; every other sponsor-list fetcher (IND, UK) still uses plain `requests` since
neither of those sites blocks it. Worth noting honestly: during heavy repeated testing
in one session, open.canada.ca's WAF also temporarily rate-limited *every* client
(including curl itself) after enough requests in a short window — this cleared on its
own, and the underlying design/parsing logic had already been fully verified against
real data (a real 529KB XLSX download, correctly parsed for the `Employer` column)
before that temporary rate-limit kicked in.

**`_SPONSOR_LIST_CACHE_MAX_AGE_DAYS = 30`** — every register above is cached to disk and
only re-downloaded once the cached copy is 30 days old, since none of these lists change
meaningfully day-to-day.

**Australia's own official register is confirmed not yet released** (expected around
September 2026). The remaining 12 countries (Italy, Denmark, Finland, Norway, Sweden,
Austria, Belgium, France, Luxembourg, Switzerland, Portugal, Spain) genuinely have **no
employer-side pre-approval process at all** — see the next section — so `Unknown` isn't
a gap for them, it's the honestly-correct answer given the badge's third value.

### Italy and Finland reclassified to "Employer's Discretion"; a real research correction

`NO_SPONSORSHIP_PROCESS_COUNTRIES` — countries whose work-visa system needs no special
employer-side process at all, where the user can get the visa himself off a plain job offer
from **any** compliant employer in that country, not just some — grew by two this
session, both backed by real research documented directly in the code comment above the
set:

- **Italy**: real research found the Decreto Flussi/Nulla Osta process is quota- and
  eligibility-based (any registered, compliant employer that can pay the offered salary
  qualifies) rather than a pre-approved employer list — no public register of approved
  sponsors exists at all.
- **Finland**: real research (a deliberate, more careful **follow-up** pass, after the
  original "only ~66 companies" claim used here was challenged) confirmed **any**
  company with a Finnish business ID and demonstrated financial stability can sponsor a
  residence permit via Migri's Enter Finland service. The "~66 companies" figure
  previously used for Finland was actually Migri's own **optional** "Employer
  certification" fast-track programme — not a requirement to sponsor at all, the same
  shape as Sweden/Denmark/Portugal's own optional fast-track programmes (see the
  surrounding comment for those). Treating that narrow, opt-in list as the real
  Yes/Unknown source would have wrongly shown `Unknown` for the vast majority of real,
  fully-able-to-sponsor Finnish employers who simply never opted into certification.
  **This is a real correction of a previous, wrong research conclusion from earlier in
  the project** — worth keeping documented here in the same "here's what we got wrong
  and how it was found" style as the rest of this doc, not silently fixed.

`NO_SPONSORSHIP_PROCESS_COUNTRIES` is now: `Germany, Denmark, Norway, Sweden, Austria,
Belgium, France, Luxembourg, Switzerland, Portugal, Spain, Italy, Finland` (13
countries). A listing from one of these gets `sponsorship_visa = "Employer's
Discretion"` (a distinct third badge value, `#5c4fa8` in `SPONSORSHIP_BADGE_COLORS`) —
a stronger, different fact than `Unknown` (which means "this country needs a specific
employer's sponsorship and we don't know if this one qualifies"): here there is no
employer-side gate to even check.

## App icon

The `.exe`'s icon (and the running window's taskbar/title-bar icon) is
`Icon.ico` (in the project's root folder) — a multi-resolution ICO (16/24/32/48/64/128/256 px) converted
from a user-supplied `Icon.png` via Pillow:

```python
from PIL import Image
img = Image.open('Icon.png').convert('RGBA')
img.save('Icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
```

`main.py` sets it as the app-wide window icon via a `resource_path()` helper that
resolves correctly both in dev (relative to `main.py`) and inside the frozen exe
(relative to PyInstaller's `sys._MEIPASS` extraction directory — the icon file is
bundled in via `--add-data "Icon.ico;."`). The PyInstaller build command also takes
`--icon Icon.ico` so the `.exe` file itself (as seen in Windows Explorer) uses it too.

**If the taskbar/Explorer still shows the old default icon after rebuilding** — this
was seen once and confirmed to be Windows' own icon cache, not a build problem
(verified by extracting the icon actually embedded in the rebuilt `.exe` with
`[System.Drawing.Icon]::ExtractAssociatedIcon()` in PowerShell — it was correct).
Rebuilding the exe repeatedly at the exact same path makes Windows cache the old icon
against that path. Fix: close the app and restart the computer (clears the icon cache);
no code change needed.

### The icon "won't fix itself" across restarts — two real, separate problems found

The user reported the icon still showing wrong even across app restarts (not just the
one-time cache issue above). Two genuinely separate real problems were found and fixed:

1. **The `Icon.ico` file itself was malformed.** Direct inspection with Pillow found it
   had only **one** frame, and that one frame was **253×256 pixels — not square**. A
   valid Windows icon needs square, multi-resolution frames; a non-square single-frame
   ICO is exactly the kind of file that can render as a generic/blank icon in some
   Windows UI surfaces even though it opens "fine" elsewhere. **Fix**: regenerated a
   proper icon from the same source artwork with all 7 standard square sizes (16/24/32/
   48/64/128/256), confirmed afterward via Pillow (`im.info['sizes']` listing all 7).
2. **Even after that fix and a full Explorer icon-cache clear** (deleting
   `%LocalAppData%\Microsoft\Windows\Explorer\iconcache_*.db` plus the older
   `IconCache.db`, then restarting Explorer), **the Taskbar still showed a generic icon
   for the live running window specifically.** This was narrowed down carefully, not
   guessed at:
   - Extracting the icon directly from the built `.exe`'s own PE resource (via
     `win32gui.ExtractIconEx`, rendered to a real PNG) showed the correct custom logo.
   - Querying the LIVE running window directly via the real Windows API (`WM_GETICON`
     message, sent to the actual running window handle, rendered to a real PNG) *also*
     showed the correct logo.

   Both of those together prove the code and the build were correct, and the window was
   genuinely reporting the right icon to Windows — the remaining issue is understood to
   be a stubborn Explorer/Taskbar-level caching quirk specifically, not a code bug. Two
   real, standard fixes were applied regardless (both worth keeping even though they
   didn't fully resolve this specific remaining Taskbar quirk on their own):
   - `window.setWindowIcon(app_icon)` is now called explicitly on the `MainWindow`
     instance itself in `main.py`, not just `QApplication.setWindowIcon(app_icon)`
     (which was already there) — a known, commonly-reported real Windows+Qt gotcha
     where the Taskbar button icon is tied to the top-level window's *own* icon and
     doesn't always reliably inherit the QApplication-level one alone in a frozen build.
   - `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('RoleHound.App')`
     (`main.py`'s `_set_windows_app_user_model_id`) is called before `QApplication` is
     even constructed — Windows groups/identifies a running window's Taskbar button by
     its AppUserModelID, not just its own `HICON`; without a unique one set, a frozen
     PyInstaller app can get lumped in under a generic/default identity, a known real
     cause of exactly this symptom. Windows-only (`sys.platform == 'win32'` guard),
     best-effort — wrapped in `try/except Exception: pass` so it can never crash the
     app if the call itself fails on some system.

   Status as of this session: both fixes are shipped and worth keeping regardless, but
   the specific stubborn Taskbar-for-the-live-window symptom was still being
   investigated as the last relevant exchange on this topic — if it resurfaces, start
   from the `WM_GETICON`/`ExtractIconEx` verification above (both already confirmed
   correct) rather than re-suspecting the build or the icon file itself.

## Where everything is stored, and the exact file formats

All local JSON, no database:

| Running as... | Data folder |
|---|---|
| `python main.py` (dev) | `data/`, next to `main.py` |
| `RoleHound.exe` (packaged) | `%APPDATA%\JobDesk\` |

This split is deliberate (`storage._resolve_data_dir`, checks `sys.frozen`) — a
PyInstaller onefile exe's own directory is a temporary extraction path, not a stable
place to keep user data.

**Worth remembering during live debugging**: the actually-running `RoleHound.exe` reads
and writes `%APPDATA%\JobDesk\settings.json` (and `jobs.json`/`applications.json`
alongside it), **not** the repo's own `data/` folder — that's only ever used by
`python main.py` in dev. This was a real, separate, useful fact the cancel-bug
diagnostic session above turned up: checking the wrong one while debugging live search
activity (e.g. Apify run history) gave completely wrong results — a run history check
against the wrong account showed zero matching activity for real, contemporaneous
search activity, purely because the wrong `settings.json`'s API token was being read.

### `settings.json`
```json
{
  "apify_token": "apify_api_...",
  "anthropic_api_key": "sk-ant-...",
  "limit_enabled": true,
  "limit_value": 100,
  "limit_per_call": 100,
  "countries": ["Italy", "Germany", "..."],
  "actor_order": ["indeed", "glassdoor", "linkedin"],
  "date_labels": {"linkedin": "Past week", "indeed": "Last 7 days", "glassdoor": "Last 7 days"},
  "date_values": {"linkedin": "pastWeek", "indeed": "7", "glassdoor": 7}
}
```

### `jobs.json`
A flat list of job dicts, newest search results prepended (added on top) each time,
never automatically pruned except by Remove/Clear Search/Filter. Each entry has (not
all fields always present): `id` (uuid, assigned in `storage.prepend_jobs`), `title`,
`company`, `location`, `posted_date`, `url`, `description`, `platform`, `country`,
`employment_type` (LinkedIn only), `seniority_level` (LinkedIn only), `Category`,
`was_translated` (bool, only present if translation happened).

### `applications.json`
A flat list of application dicts. Each: `id` (uuid), `title`, `company`, `country`,
`location`, `platform`, `category`, `url`, `description`, `documents` (list of absolute
paths to copied files), `status` (`Processing`/`Accept`/`Reject` — older data may still
say `Accepted`/`Rejected`, auto-migrated on load by `storage.load_applications`),
`apply_date` (`dd/mm/yyyy`, older entries may have a trailing ` HH:MM` that's still
parsed correctly).

### `documents/<application-id>/`
Copies (never the originals) of whatever files you attached when applying, one
subfolder per application, named by that application's `id`. Deleted automatically
when that application is removed or when Clear My Applications is used.

## Project file structure

> **Note on the project folder's name:** this app's folder has been renamed at least
> once already (it was originally `RoleHoundApp`, later renamed to `1 - App`) and may be
> renamed again — none of the code depends on the folder being called anything
> specific. Wherever this doc says "the project folder", it means wherever `main.py`
> currently lives, not a literal fixed name.

```
<project folder>/
├── main.py                       entry point -- QApplication, window icon, MainWindow
├── tests/                        the 3,167-assertion campaign; `python tests/run_all.py`
├── RoleHound.spec                  PyInstaller spec -- THE build entry point (bundles the
│                                  Playwright driver + Icon.ico); see "Building the .exe"
├── requirements.txt              PySide6, apify-client, pandas, requests, openpyxl,
│                                  pyinstaller, lingua-language-detector, anthropic,
│                                  playwright, beautifulsoup4
├── Icon.png / Icon.ico           app icon (source PNG + generated multi-res ICO)
├── Job-Filter-Claude-Apify*.md   the eight verbatim prompt mirrors. NEVER edited by hand
│                                  (`M-1`) -- regenerated from `system_prompt_for`, and
│                                  held byte-identical by t4. Four of the eight are now
│                                  copies of each other (`T-5`: two prompts, not eight)
├── app/
│   ├── pipeline/                  the search/normalize/translate/filter/sort/Claude logic,
│   │                              split into layers -- each may only import from the ones
│   │                              above it, which keeps the import graph acyclic
│   │   ├── __init__.py            facade: re-exports all 264 names (explicit __all__), so
│   │   │                          `from app import pipeline` keeps working unchanged
│   │   ├── errors.py              SearchCancelled
│   │   ├── text.py                dig / strip_html / is_true_flag / text_of
│   │   ├── geo.py                 country + city reference tables
│   │   ├── rules.py               the content rules that decide what survives Filter
│   │   ├── language.py            langdetect + translation (and the language cache)
│   │   ├── company.py             working out a listing's real employer name
│   │   ├── claude_screen.py       the Claude pass and legal-name lookups
│   │   ├── sponsorship.py         sponsor registers + fuzzy employer matching
│   │   ├── apify.py               running actors, reading datasets
│   │   ├── sources_urls.py        per-site search-URL builders
│   │   ├── sources_apis.py        direct API fetchers, one per job board
│   │   ├── sources_norm.py        per-platform row normalizers
│   │   ├── google.py              query building + result deepening
│   │   ├── preflight.py           pre-run health checks
│   │   ├── filters.py             reapply_filters -- the Filter button
│   │   └── search.py              run_search + _run_google_phase -- the Search button
│   ├── search_worker.py           QThread wrappers: SearchWorker, FilterWorker
│   ├── storage.py                 JSON persistence (settings, jobs, applications, zip/export helpers)
│   ├── excel_export.py            styled openpyxl workbook builders for Export Excel
│   ├── styles.py                  QSS stylesheet + category badge colors
│   └── ui/
│       ├── main_window.py         navbar, page switching, wiring workers/dialogs to the UI
│       ├── setup_wizard.py        token/limit/date-range/actor-order/country-picker/API-keys dialog
│       ├── jobs_page.py           Job Search table, display filter, Apply/Remove, row numbers
│       ├── applications_page.py   My Applications table, status dropdown, row numbers
│       ├── apply_dialog.py        JD viewer + document attacher, shown on Apply
│       ├── log_panel.py           the bottom scrollable colored log
│       ├── confirm_dialog.py      TypeToConfirmDialog (type-exact-phrase destructive confirm)
│       ├── claude_review_dialog.py  lists Claude-flagged listings, lets you override before deleting
│       ├── preflight_problems_dialog.py  per-source problems from the pre-flight check, with inline key fixes
│       └── broken_urls_dialog.py  collects a real URL for each domain that returned nothing
└── data/                          (dev-mode data folder; not used by the packaged exe)
```

**Correction from a full-codebase audit**: this tree previously listed `python-dotenv`
as a dependency (it is not imported anywhere) while omitting `playwright` and
`beautifulsoup4` (both genuinely required), and left out `RoleHound.spec`,
`preflight_problems_dialog.py` and `broken_urls_dialog.py` entirely. Now matches
`requirements.txt` and the real folder.

## Running from source

```bash
cd "<project folder>"              # wherever main.py currently lives
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
python main.py
```

## Building the .exe

```bash
cd "<project folder>"
.venv\Scripts\python -m PyInstaller RoleHound.spec --noconfirm
```

**Build from `RoleHound.spec`** — it's the checked-in, reproducible build definition, and
it sets `upx=True` (compression) which a bare command line wouldn't.

> **Correction.** An earlier revision of this section claimed the spec is *required*
> because it "bundles Playwright's driver folder … listed explicitly in `datas`", and
> warned that a one-liner build produces an exe whose manual-assist stage fails at
> runtime. **Both halves of that were wrong**, and the claim was written from memory of a
> build log rather than by opening the file. The spec's `datas` is
> `[('Icon.ico', '.')]` and it never mentions Playwright at all. The driver *is* bundled
> — a real check of the build TOC found 783 Playwright entries including `node.exe` —
> but by **Playwright's own PyInstaller hook**
> (`playwright/_impl/__pyinstaller/hook-playwright.sync_api.py`), which ships inside the
> package and fires for any PyInstaller build, one-liner included. So the spec is the
> right thing to use, just not for the stated reason, and the one-liner is not broken.

Result: `dist\RoleHound.exe` — a single self-contained file, no Python installation
needed to run it. Copy it anywhere; it always stores its data in `%APPDATA%\JobDesk`
regardless of where the exe itself lives.

> **Note:** If `RoleHound.exe` is currently running, the build fails with a
> `PermissionError` (file in use) — close the app (or `taskkill /F /IM RoleHound.exe`)
> first.

## Design decisions and things that were tried and reverted

Kept here specifically because this kind of context is the first thing to get lost.

- **Raw search, filter-on-demand (current design)** replaced an earlier version where
  `run_search` applied all content filters immediately. Switched so the actual Apify
  output is always visible/debuggable, and so filter changes don't require a new
  (slow, credit-costing) search.
- **Title-vs-description priority was built, then explicitly reverted.** At one point
  the Remote/Seniority/Sponsorship rules were rewritten so the *title* was checked
  first and independently, with different rules for what counted as a title failure vs
  falling through to the JD. This went through several conflicting iterations (title
  wins outright → title-then-JD both must pass → JD should have priority over title)
  before the decision was made to **throw all of it away** and go back to the original,
  simplest design: title and description are concatenated into one string and checked
  together, with no special-casing either way. If this ever needs revisiting, don't
  assume title-priority logic is still wanted — it was deliberately removed.
- **LinkedIn's `f_WT=2` URL trick — retired 4 October 2026 (`T-16`)**:
  `curious_coder/linkedin-jobs-scraper` does not return a structured `workplaceType` field, and
  `f_WT=2` was measured **ignored** (same 300 jobs with and without). The 23 September
  conclusion that *"the actor, the public page and its JSON-LD all lack the field, and the
  decision is to stop looking"* was **correct about those three routes and wrong as a decision**:
  all three were routes into the same actor or its page, and a different actor returns the tag on
  every row. LinkedIn now runs on `apimaestro/linkedin-jobs-scraper-api`. The client-side keyword
  Remote rule stays mandatory regardless. See
  [*Signals we went looking for and could not get*](#m--signals-we-went-looking-for-and-could-not-get).
  And note `f_WT=2` was itself a real fault for months: it was applied to *every* search
  regardless of work mode, so a Not Remote run asked LinkedIn for remote work only (O-12).
- **Full-text language detection instead of a short prefix**: `langdetect` was
  misclassifying German job postings as English when only a short prefix (title + first
  300 chars) was checked, because that prefix was dominated by English loanwords like
  "Data Engineering". Switched to detecting on the full title+description text.
- **Claude never auto-deletes.** Early design had Claude's final pass silently remove
  whatever it flagged. Changed so Claude only *flags* candidates with a reason, and a
  review dialog always asks for human confirmation (or explicit "remove all") before
  anything is actually deleted — and any Claude API error fails open (keeps the
  listing) rather than risking silent data loss.
- **Excel export changed from a folder-picker to a Save-As dialog** — `
  getExistingDirectory` felt confusing ("why does it insist on a folder, not a path?");
  switched to `getSaveFileName` so it feels like choosing where to save a file, and the
  two output files are named after whatever base name was chosen.
- **Actor order changed from LinkedIn-first to Indeed → Glassdoor → LinkedIn** as the
  new default, and made fully user-configurable (drag-to-reorder, checkable) in the
  wizard rather than hardcoded.
- **Status changed from an editable `QComboBox` back to a `QPushButton` + `QMenu`.**
  Centering the status text via `setEditable(True)` + a centered read-only `QLineEdit`
  looked right but silently broke click-anywhere-to-open (editable combos only open
  their popup from the small arrow). A button with a menu gets centered text for free
  and stays fully clickable.
- **Translation was made parallel** (`translate_many`, `ThreadPoolExecutor`,
  `TRANSLATE_MAX_WORKERS = 30`) after real use showed it was the single slowest part of
  a search covering multiple non-English-speaking countries. Detection (local, fast)
  still runs sequentially first; only the actual network translation calls run
  concurrently. Verified up to 30 concurrent requests against Google Translate's free
  endpoint with no errors — going much higher risks Google rate-limiting the requests,
  not overloading the local machine (it's pure I/O wait, not CPU work).

## Full-codebase audit — 30 findings, all fixed

A complete line-by-line review of all 11,693 lines (17 files) was run against the
Document's stated intent. 21 of the 30 findings were reproduced by actually running the
code, not inferred from reading it. Everything below is fixed and re-verified; the
detail lives in the code comments at each site.

### The six that destroyed data, money or results

1. **A cities-only search silently ran all 18 countries.** `run_search` opened with
   `countries = countries or COUNTRIES`, and an empty list is falsy — so the
   cities-only selection the wizard explicitly allows was read as "search everything".
   Picking just Amsterdam made **57 paid actor calls instead of 3**, built 74 Google
   query lines instead of 4, and spent 16 of Jooble's non-renewable 500 lifetime
   requests. Fixed with `COUNTRIES if countries is None else list(countries)`, which
   distinguishes "not passed" from "deliberately empty". Re-verified against the real
   `run_search` with a mocked Apify client: **exactly 1 actor call** for one
   platform × one city.
2. **Four integrations produced rows the Filter always deleted.** `arbeitsagentur.de`
   (a synthesized `"<title> at <company> in <city>"`), `jobs.ch`/`jobup.ch` (the title,
   verbatim), all 16 Jooble domains (a truncated snippet) and `swissdevjobs.ch` (the
   role name) have no real JD text — so they can never contain a remote keyword, and
   the Remote rule deleted **100%** of their rows on every Filter run. Two documented
   decisions rested on this not being true: arbeitsagentur.de was deliberately kept on
   the *paid* Google path too "for description quality", and the jobs.ch/jobup.ch
   trade-off was recorded as "thinner data" when it was really total loss. The user chose
   to half-exempt them: those rows now carry `thin_description = True`, every DROP
   signal still applies (an explicitly on-site or hybrid listing is still removed) but
   the positive "must say remote" requirement is waived, and Claude's own Remote rule
   still re-checks them in Step 5. Verifying that fix surfaced a second gate with the
   identical root cause — `lacks_english_mention` also reads JD text that isn't there —
   so it skips thin rows too. Confirmed end-to-end through the **real fetcher
   functions**: all four now survive, an on-site thin row is still dropped, and rich
   sources are completely unaffected.
3. **Cancelling a search threw away everything already fetched**, despite the Document
   promising the opposite. Two separate causes: the `should_cancel()` check sat at the
   *top* of the `as_completed` loop, raising before `rows.extend(future.result())`
   drained the platform that had just finished; and `run_platform_locations` raised
   mid-loop, discarding its own `platform_rows`. Both fixed — every completed future is
   always drained, and a cancelled platform returns what it has. Re-verified against the
   real `run_search`: **21 rows kept where it previously kept 0**, while still stopping
   early (7 of 9 calls).
4. **Export Excel crashed on ordinary scraped text.** openpyxl rejects control
   characters outright (`IllegalCharacterError`), and `websiteContentScraper`/deep-crawl
   descriptions are raw page text that genuinely contains them — the same class of bug
   as the `'#555'` colour crash fixed earlier, on the same export path. A new `_xl()`
   helper strips them and trims to Excel's real 32,767-character cell limit, applied to
   **every** text cell in both workbooks (a scraped title or company name can carry them
   too), not just descriptions.
5. **A failed translation deleted the listing.** `_translate_text` correctly failed open
   and returned the original text, but `maybe_translate` set `was_translated = True`
   regardless — so `lacks_english_mention` found no "english" in the still-German text
   and dropped it. A Google Translate hiccup didn't skip translation, it destroyed data.
   `_translate_text` now reports success, and nothing is written back unless the
   translation genuinely worked.
6. **One id-less flagged listing deleted every other id-less listing.** `remove_ids`
   collected `None`, and the filter then removed every job whose id was `None`. Now
   requires a truthy id, so a missing one can never match.

### Wrong output and real waste

7. **Germany's and the Netherlands' startup results were stamped Berlin and Amsterdam.**
   Location attribution substring-searched the *whole* query, and two startup domains
   contain a city name — `berlinstartupjobs.com` and `startupmap.iamsterdam.com`. Every
   result from those country-wide searches was saved with the wrong `location`.
   `_location_from_search_term` now matches only the query's real location slot (between
   `" jobs "` and the site clause), which a domain name cannot collide with. Verified
   across all 18 countries and all 5 cities: **zero misattributions**.
8. **Deep-crawled pages inherited the wrong country.** The parent lookup used
   `domain_to_row`, which holds whichever result for that domain came *first* — and
   `app.welcometothejungle.com` is listed under 7 countries, `wearedevelopers.com` under
   4. A French posting could be stored as `country='Canada'`, which then drives the wrong
   Sponsorship Visa badge. The accurate signal (`crawl.referrerUrl`) was already being
   fetched but only consulted as a fallback that never fired for same-domain crawls;
   it's now tried first.
9. **The wizard's "result limit per search" silently dropped whole locations from
   Google.** For the three job actors one dataset item is one job, but for Google one
   item is a *page* — and the queries are ordered country by country, so truncating cut
   off the last locations entirely. `run_actor_and_fetch` gained an `item_limit`, and
   the Google call passes its own real ceiling (`query lines × maxPagesPerQuery`).
10. **Filter permanently truncated long JDs to 4,500 characters.** Google Translate's
    free tier really does cap a request there, but the *truncated* result was written
    back over the description and saved — a real 20,000-character deep-crawled JD lost
    15,500 characters from `jobs.json`, the Apply dialog, the Excel export and the
    documents zip alike. Now split into chunks on sentence/space boundaries and rejoined
    (`_split_for_translation`, up to `_MAX_TRANSLATE_CHUNKS = 6`). Verified: 23,800
    characters in, 23,800 out.
11. **A listing you chose to keep was re-flagged forever.** The new decision cache stored
    `claude_screen_drop=True`, so overriding Claude in the review dialog lasted exactly
    one run — and because a cache hit makes no API call, Claude could never revise its
    own verdict either. The override is now recorded as `claude_screen_user_kept` and
    honoured, and cleared automatically if the listing's content or a rule actually
    changes.
12. **An API error erased a good Match % score.** `claude_match` was assigned before the
    error branch, so a failed call overwrote a valid score with `None` and sorted the
    listing to the bottom. It now only writes on success, matching how the cache key was
    already (correctly) handled.
13. **Sponsorship spent real Claude money on listings about to be deleted.** Running
    Step 6 on the full `kept` list was correct while it was free, but company legal-name
    resolution moved into that step and a cache miss now costs a billed `web_search`.
    Flagged listings still get the free register match and any cached name, but never
    trigger a fresh paid lookup (`no_paid_lookup_for`).
14. **A failed Google stage left four Log timers ticking forever.**
    `PLATFORM_END:Google` only fired on the fully-successful path, and
    `GOOGLE_STAGE_FAILED` stopped just 4 of the 8 timers the stage can start. The header
    now closes from a `finally` (and on the pre-check-cancelled path), and the handler
    covers `preflight`, `direct_api` and `manual_assist` too.

### Cost, accuracy and gaps

15. **The pre-flight check started a billed Apify run on every search** — a real actor
    run with `queries: "test"`, plus 20–60s of dead time, purely to prove reachability,
    right after the token check and right before the real Google call. Replaced with
    `client.actor(...).get()`: same question, no compute cost, no wait.
16. **Jooble's lifetime counter drifted below reality.** Usage was recorded only after a
    fully successful fetch, so a 5xx or a parse failure on a request Jooble had already
    counted left the tally permanently short — the dangerous direction against a hard
    500-request cap. Now counted the moment the request demonstrably reaches Jooble, via
    an `on_request_sent` callback fired before `raise_for_status()`.
17. **Language detection ran twice on every non-English listing** (`translate_many` to
    build its work list, then `maybe_translate` again on the same text). Verified: 5 rows
    caused 10 langdetect runs; now 5.
18. **The seniority rule missed two common phrasings.** The range pattern capped *both*
    bounds at 10, so "10-15 years" matched nothing; only `-`, `/` and `|` counted as
    separators, so "5 to 7 years" slipped through; and a bare "8 years of experience
    required" was caught by no pattern at all. All three now covered, with a lookbehind
    so a junior-friendly "1-3 years of experience" is still correctly kept. Verified
    against 13 cases including the false-positive guards: **0 failures**.
19. **Fifteen sources reported themselves as "Google".** Reed, EURES, Remotive, RemoteOK,
    arbeitnow, SwissDevJobs, JobCloud, arbetsförmedlingen, arbeitsagentur and all 16
    Jooble domains tagged their rows `platform='google'`, so the Details column and the
    Excel Platform column named a source that never touched them — and it removed the one
    field that answers "which integration is actually earning its keep?". Each now
    reports its real name. Only genuine Google-stage rows (deep-crawl, direct site
    search, manual-assist) still say `google`. Side benefit: the zero-result warning no
    longer has a direct-API row masking a genuinely broken Google `site:` query.
20. **Updating a wrapped Log line left the old text behind.** `select(LineUnderCursor)`
    selects one *visual* line, and `QPlainTextEdit` wraps by default — so the multi-line
    `GLOG:` warnings kept their wrapped remainder on every update. Now selects the block.
21. **Dedup merged two different jobs when the title was just the company name.**
    Stripping the company left both sides empty, and `SequenceMatcher` scores two empty
    strings as a perfect 1.0. A blank stripped title is now skipped; real near-duplicates
    still merge.

### Cleanup, dead code and doc drift

22. `want_remotive = True` made `_run_direct_api_searches`' early-return unreachable —
    and its condition also omitted `eures_iso2_codes` and `want_switzerland_apis`, so it
    was dead code hiding two missing terms. Removed.
23. **Closing the app during a Claude Filter run abandoned a live thread.**
    `FilterWorker` had no cancel at all, so `closeEvent` waited 2 seconds and closed
    anyway. It now has `request_cancel()`, polled between listings inside
    `reapply_filters` — which also means **the Cancel button now works for Filter**, not
    just Search, and cancelling keeps every decision already made.
24. **An older `settings.json` crashed Search with a `KeyError`.** `apify_token`,
    `limit_per_call` and `date_values` were read by direct index while everything else
    used `.get()` — and the Document itself tells you to hand-edit that file. Now defaulted,
    with a clear "open the wizard" dialog when the token is genuinely missing.
25. `_deepen_google_results` subscripted `run['defaultDatasetId']` instead of using the
    `_get_default_dataset_id` helper that exists for exactly that. Fixed.
26. Comments claiming `GOOGLE_QUERY_ROLE_TERMS` holds "5 terms" (it holds 4) and that the
    global stage is "2 lines for 7 sites" (it is 1 line for 8) — the numbers someone
    would trust next time a site is added. Corrected. The budget itself was re-measured
    and is still correct: worst case 30 words, and all three site lists are still
    pairwise disjoint.
27. The build section documented a raw PyInstaller one-liner rather than `RoleHound.spec`;
    see [Building the .exe](#building-the-exe).
28. **Six credentials had no UI at all.** The 16 Jooble keys, the Reed key, the two France
    Travail credentials and `manual_assist_enabled` could only be set by hand-editing the
    one file the wizard rewrites on save. The wizard now has a collapsible **"Optional API
    keys"** section covering every one of them, plus the manual-assist toggle.
29. Two unused locals in `reapply_filters` (`total`, and the loop index `i`). Removed.
30. **Claude's per-listing input is now the dominant cost, not the output.** With the
    breakdown gone and `max_tokens` at 100, each call still sends up to 6,000 characters
    of description as *uncached* input. The user reviewed this and chose to keep the full
    6,000-character window — accuracy over cost — so `_CLAUDE_SCREEN_DESCRIPTION_MAX_CHARS`
    is deliberately unchanged. Recorded here so the trade-off is a decision, not an
    oversight.

## Audit round two — 16 findings, 4 of them caused by round one

A second full review, run against the code *after* the 30 fixes above, with the sharpest
attention on those fixes themselves. **Four findings were regressions round one
introduced**, and one was worse than the bug it replaced. They are recorded here in full
rather than quietly corrected, because the pattern that produced them is the useful part.

**The pattern: a fix verified only on the unit is not verified.** Round one checked the
`thin_description` change on hand-built dictionaries and never once ran it through the
real `run_search` → pandas → `jobs.json` path, which is exactly where it broke. Round two
verified every finding end-to-end through that full path.

### The regressions

1. **`thin_description` silently switched the Remote rule off for every listing.**
   `if row.get('thin_description'):` reads as obviously correct and is not. Only 4 of
   ~20 row builders set that key, and `pd.DataFrame(rows)` fills a missing key with
   `NaN` — which is **truthy** in Python. So the flag read `True` for *every row in the
   dataset*, disabling both `passes_remote_rule`'s positive check and
   `lacks_english_mention` app-wide. It triggered whenever a single thin row existed
   (Germany, Switzerland, or any of the 16 Jooble countries — most real searches), and
   survived save/reload so it kept applying. Verified: an on-site Indeed listing with no
   remote wording survived Filter.
   **Fix:** a new `is_true_flag()` helper — `pd.isna()`-based, so it is correct for
   `None`, `NaN` and `numpy.bool_` alike (`is True` alone would reject the numpy case
   once every row happens to carry the key) — used by both rules, plus a
   `fillna(False).astype(bool)` normalization at the DataFrame boundary so a real `False`
   reaches disk.
2. **`jobs.json` stopped being valid JSON.** The same `NaN` reached `json.dumps`, which
   writes a bare `NaN` literal — legal for Python's parser, illegal for every other one
   (jq, `JSON.parse`, editor validators). For an app whose entire storage model is "plain
   JSON you can open and read", that quietly broke the core promise.
   **Fix:** every saver now goes through one `storage._write_json`, which recursively
   maps NaN/inf/-inf to `None` before dumping and keeps `allow_nan=False` as a backstop.
   *(This fix was itself wrong on the first attempt — see [audit round
   three](#audit-round-three--13-findings-0-critical) below.)*
3. **Chunked translation still truncated, just later.** Round one replaced a hard
   4,500-character cut with chunking, but capped it at 6 chunks — so a 52,000-character
   JD still lost 25,000 characters silently. The round-one test used 23,800 characters,
   *under* the new ceiling, so it reported success.
   **Fix:** `_split_for_translation` returns the remainder, and `_translate_text` appends
   it in its original language behind an explicit `[untranslated — original text
   continues below]` marker. The chunk cap stays (it bounds cost); the silence is gone.
4. **The new seniority pattern deleted junior-friendly listings.** The
   `(?:\s+\S+){0,3}` gap between "N years" and "experience" crossed sentence boundaries,
   so `"Our team grew 8 years running. No prior experience needed."` was dropped. The
   13-case round-one suite passed because every case kept both halves in one clause.
   **Fix:** the gap now excludes sentence punctuation and only accepts real connector
   words, and a match only counts when its own sentence contains a requirement word
   (`required`, `minimum`, `at least`, …) and no waiver (`no prior experience`, `gain`,
   …). Re-verified on 18 cases including every false positive found.

Two round-one fixes were also only **half-applied**: the `_get_default_dataset_id` helper
replaced one raw `run['defaultDatasetId']` out of three (the other two now fixed,
confirmed by AST that zero raw subscripts remain in executable code), and the
real-source-name change left manual-assist rows still tagging themselves `platform:
'google'` — which additionally made them count as evidence a domain was healthy in
`_warn_zero_result_google_sites`, suppressing genuine broken-URL warnings.

**A documentation error too:** the "Building the .exe" note round one rewrote was
factually wrong on both counts — see the correction in that section. It was written from
memory of a build log instead of by opening the spec file.

### The rest

- **A thin row with no company was deleted as "fake" in step 2**, before the step-4
  exemption could save it — a thin description is under 50 characters by definition, and
  `arbeitsagentur.de`'s `firma` field really can come back empty. `is_likely_fake` now
  skips the short-description signal for `thin_description` rows.
- **Legal-name resolution was paying Claude to web-search regex guesses.**
  `_extract_company_from_text` is documented to sometimes extract a job title instead of
  a company — the exact reason Company Popularity was deleted for wasting money — and
  those names were being sent for billed searches. Guesses are now marked
  `company_from_text` and never trigger a paid lookup, and
  `_MAX_LEGAL_NAME_LOOKUPS_PER_RUN = 25` caps the spend per run with a Log line when it's
  reached (names cache permanently, so coverage is only delayed).
- **`direct_search_overrides.json` was re-read from disk 217 times per search** — now
  memoized on mtime+size, measured down to 1.
- **`(x or '').capitalize()` still crashed on NaN** (the `or ''` guard only catches
  `None`; NaN is truthy), and neighbouring cells rendered a literal `"nan"`. A shared
  `pipeline.text_of()` now handles None/NaN/non-strings in one place for both the Jobs
  table and the Excel export, and a NaN `claude_match` shows `—` instead of `nan%`.
- **The pre-flight ran up to 11 real HTTP calls sequentially** at `timeout=15` each, one
  of them (`EURES`) the real 50-result search function rather than a probe. Checks now
  run concurrently, and EURES gets a `resultsPerPage: 1` probe.
- **Direct Site Search over-reported**: its counter incremented before the wrong-city
  filter, so it could announce "N postings found" when all N were dropped. It now counts
  after, and reports the discrepancy.
- **The Apply dialog rendered scraped job titles as HTML** (`QLabel` defaults to
  `AutoText`), so a real title like `C++ & Data <Scientist>` had `<Scientist>` swallowed
  as an unknown tag. Every field is `html.escape()`d now.
- **The progress bar froze partway on cancel** — round one's break-on-cancel fixed real
  data loss but stopped incrementing `done`. Skipped locations are now accounted for.
- `QDesktopServices.openUrl()` gets an explicit `QUrl` instead of relying on PySide6's
  implicit string conversion.

## Audit round three — 13 findings, 0 critical

A third full review, run against the code after all 46 earlier fixes. **No critical
findings this time**, and the two rules that round two broke are holding under
adversarial input. Two of round two's own fixes still needed correcting.

| | findings | critical | regressions |
|---|---|---|---|
| Round one | 30 | 6 | — |
| Round two | 16 | 2 | 4 |
| **Round three** | **13** | **0** | **2** |

### The two round-two fixes that were themselves wrong

1. **The NaN guard could crash every save path.** Round two's `save_jobs` fix was wrong
   three ways at once: `_json_safe` can never run for a float (`json.dumps` consults
   `default=` only for types it does *not* recognise, and `float` is recognised — so the
   docstring's promise was unreachable code); the fallback walked only the top level of
   each record, so a `NaN` nested in a list or dict still raised; and `inf` was missed
   entirely, since the test used was `v != v`, which is `False` for infinity. Net effect:
   a *data-quality* bug had been turned into a `ValueError` out of a function every save
   path calls — Filter, Apply, Remove, Clear.
   **Fix:** one `storage._write_json` used by all three savers, with a recursive
   `_json_sanitize` mapping every non-finite float to `None` before dumping.
   `allow_nan=False` stays as a backstop that should now never fire. Verified against 7
   NaN/inf shapes including a triple-nested one, all saving cleanly and all producing
   strict-valid JSON.
2. **Only `save_jobs` had been hardened.** `save_applications` still wrote bare `NaN`
   literals — and `add_application` copies its fields straight off a job dict, which is
   exactly where a pandas NaN comes from. So the invalid-JSON problem round two claimed
   to have solved was still live one file over. Both it and `save_settings` now go
   through the same helper.

Two smaller ones came from round two as well: the concurrent pre-flight reported all of
Jooble's config-only checks before every network source (the Log order no longer matched
the order sources actually run in — now queued through the same path), and half of the
DataFrame boolean normalization is unreachable insurance rather than a live guard, which
the comment now says outright instead of implying.

### The rest

- **Cancelling Filter still spent money.** The Cancel added in round one broke out of the
  Claude loop and then fell straight into the Sponsorship step, which could still make up
  to `_MAX_LEGAL_NAME_LOOKUPS_PER_RUN = 25` real, billed `web_search` calls *after* the
  user asked it to stop. `should_cancel` is now threaded into
  `_apply_sponsor_list_matches_to_jobs` and checked before each fresh lookup; the free
  register match still runs, since it costs nothing.
- **Cancel was honoured in exactly one of Filter's seven steps.** It was checked only
  inside the Claude loop, so cancelling during translation (30 concurrent network calls)
  appeared to do nothing, and with no Claude key configured Cancel did nothing at all.
  There is now a `_cancelled()` check between steps and inside the rules loop, and
  `translate_many` takes `should_cancel`, cancels pending futures and tolerates
  `CancelledError`.
- **The same `.get(key, default)` bug, in a third place.** `record.get('status',
  'Processing')` on the Applications page: the default only fires when the key is
  *missing*, so an explicitly-`None` status rendered a blank, unlabelled button. It
  failed quietly rather than crashing, which is why two earlier audits walked past it.
- **Four different literals encoded one fallback colour** — `'#555'` at the Qt call
  sites, `'555555'` in two export cells, `'888888'` in a third. That mismatch is
  precisely how the original Excel crash shipped (Qt accepts 3-digit shorthand, openpyxl
  raises on it). Now one `styles.FALLBACK_BADGE_COLOR`, six-digit, imported by all four.
- **The sponsor register was re-read and re-normalized on every Filter click** — the
  30-day disk cache stopped the download, not the work. Normalizing a real 130,000-name
  register takes ~0.36s, paid again per country per run. Now memoized on the cache
  file's mtime+size, the same pattern used for `_load_direct_search_overrides`.
- **A `|` in a probe's error message would have corrupted a Log line.** Worth recording
  how this was handled: I checked whether real `requests`/`urllib3` messages actually
  contain one — they don't, so it was latent, not live. Fixed anyway, since
  `rpartition`/`partition` makes it structurally impossible rather than dependent on that
  staying true. A failed probe's message is also trimmed to 120 characters for the Log
  line (a real DNS failure measured 310); the dialog still shows it in full.
- **The three description ceilings are now documented as related** — 27,000 translated,
  6,000 kept from a manual page, 6,000 shown to Claude. They are deliberately
  independent, and the two 6,000s being equal is coincidence, not a shared constant. The
  comment says so, so a future change to one doesn't silently assume the others.

### What was checked and found correct

Reported because "I verified this" is information too:

- **Round two's Remote-rule fix holds.** `is_true_flag` returns the right answer for all
  12 value shapes it can receive — Python bool, NaN, `numpy.bool_`, `pd.NA`, strings,
  ints — and `text_of` for all 7. The DataFrame normalization handles an explicit `None`,
  not just a missing key.
- **The reworked seniority rule survives adversarial input** — all 10 new shapes correct,
  including bullet lists, "our founders have 20 years of experience", "the company has 12
  years of experience", and a requirement and a waiver in different sentences.
- **The translation marker is inert.** `[untranslated — original text continues below]`
  collides with none of the six keyword lists and doesn't contain "english", so it can't
  accidentally satisfy or trip a filter. A JD whose only "remote" mention sits past the
  27,000-character mark still survives.
- **Claude's prompt caching is intact and the cost shape is right** — the cached prefix
  is a byte-identical constant, the keyword rules run before Claude so it only sees
  survivors, and a cached DROP costs nothing. **Correcting a round-one suggestion of my
  own**: I proposed dropping `Platform` from the per-listing prompt as unused signal.
  Checking the actual prompt text shows `Platform`, employment type and seniority level
  are all genuinely referenced by the 9 rules — removing them would have cost real
  accuracy for ~52 tokens.

## The test suite (`tests/`)

```bash
.venv\Scripts\python tests\run_all.py            # everything, including live APIs
.venv\Scripts\python tests\run_all.py --offline  # skip the suite that spends money
```

**871 assertions, all green.** Seven suites, exit code 0 only when every one passes:

| Suite | Assertions | Covers |
|---|---|---|
| `t1_rules.py` | 147 | every content rule and helper, adversarially — remote, language, sponsorship, unpaid, seniority, categorize, fake detection, `is_true_flag`/`text_of`, company extraction, language detection, translation chunking |
| `t2_sources.py` | 90 | every data source's real row shape, built by the **real fetcher code** with mocked HTTP, then pushed through the real Filter |
| `t3_storage.py` | 86 | round trips, non-finite floats, unicode/emoji, corrupt files, legacy migration, the documents zip, a 2,000-job payload |
| `t4_pipeline.py` | 142 | `run_search` with a mocked Apify, location scoping, concurrency, cancel, the DataFrame boundary, Filter step structure, sort order, Google query construction |
| `t5_ui.py` | 180 | every page and dialog rendered with hostile data (all-`None`, all-`NaN`, empty dict, unmapped enums, markup, control characters, 60k text), plus the Excel export and the Log panel — and **import safety**: every module in `app/`/`app/ui/` imported in a fresh subprocess with no `QApplication`, the test that would have caught the 0xC0000409 startup crash |
| `t6_live.py` | 68 | **real** calls to all 9 free JSON APIs, a real Claude screening, cache-hit verification, and one small real Apify actor run |

The live suite reads the **packaged** app's credentials from
`%APPDATA%\JobDesk\settings.json` (the dev `data/settings.json` points at a different
Apify account) and skips the paid actor run if under $0.30 of monthly budget remains.

### Three real bugs the campaign found

1. **Google Translate's error page was being saved as the job description.** The free
   endpoint intermittently answers with an HTML error page —
   `"Error 500 (Server Error)!!1500.That's an error…"` — and `deep_translator` returns
   that as if it were the translation rather than raising. So the row's real description
   was **overwritten with the error text**, `was_translated` was set, and
   `lacks_english_mention` then deleted the listing for not mentioning English. The
   round-two fail-open fix only covered raised *exceptions*; a successful-looking
   response carrying an error page walked straight past it. Caught by translating the
   same two listings 20 times and hitting it once — and it was the real cause of a test
   that had been failing 2 runs in 5 and been written off as flakiness.
   **Fix:** `_looks_like_translate_error_page` detects it, the call is retried
   (`_TRANSLATE_ATTEMPTS = 3` with jittered backoff — exactly what a transient 500
   deserves), and if every attempt fails the **original text is kept untouched**.
   Re-measured: 6 consecutive clean runs, from 2-in-5 failing.
2. **`_extract_company_from_text` was storing job titles as company names.** The
   `"<Company> - <Job Title>"` prefix pattern matched the extremely common
   `"Data Scientist - Remote"` shape and returned the *role*. Measured across 9 realistic
   titles: **7 extracted a job title, not an employer**. This is precisely the failure the
   Document already blamed for Company Popularity's deletion — never fixed at the source —
   and it had two live consequences: the Company column showed a job title, and the fake
   name became a dedup key. Verified: two genuinely different employers, both titled
   `"Data Scientist - Remote"`, were grouped under the same invented company and **one
   real listing was deleted**. Fixed by rejecting any candidate containing a role word,
   which returns the extractor to its own stated promise of leaving `company=None` rather
   than guessing.
3. **Two NaN crashes in the render/export paths.** A `NaN` `sponsorship_visa` reached
   `QTableWidgetItem` as a float and raised `OverflowError` — and because that happens
   mid-render, **one bad row blanked the entire Jobs page**. A `NaN` `url` reached
   openpyxl's hyperlink target and failed the whole Excel export. Both are the same
   NaN-is-truthy family as the round-two bug, in the last two places `or ''` was still
   being trusted. Fixed at the boundaries (`_link_cell`, the badge values, and
   `html.escape` in the Apply dialog) rather than per call site.

Five further "failures" were **stale assertions in the older test files** — each written
against an earlier state of the code, each verified against the live code (two via AST)
before being corrected rather than silently deleted. Two legacy tests had also been
disagreeing with each other about the Filter step count; the one asserting 7 for a
*no-Claude-key* run was the wrong half (6 is correct; 7 is the with-key count).

## Performance pass — measured, not guessed

A full read of every line with one question: where is time actually going? Every change
below was profiled first, verified to produce **identical output** afterwards, and kept
only because the measurement justified it. Two plausible-sounding ideas were measured and
**thrown away** — they are recorded here so nobody re-proposes them.

**Headline: clicking Filter over 800 listings went from 14,120 ms to 1,203 ms — 11.7x,
and 36x on a second click — with the survivor count byte-identical (3 of 800 throughout).**

### 1. Language detection is memoised (the big one)

Profiling put **~19 s of a ~28 s** Filter run inside langdetect's n-gram extraction —
more than every other step combined. `detect_language` deliberately scans the *full*
title+description (see `_MIN_LANGDETECT_CHARS`), and that cannot be shortened safely.

It can, however, be *not repeated*. `DetectorFactory.seed` is pinned at import, so
`detect()` is deterministic: the same text always yields the same verdict. The verdict is
now memoised on the row (`_lang_detected`) next to a **SHA-1 of the exact text it came
from** (`_lang_detected_for`), and reused only while that fingerprint matches.

Keying on the text, not on a "done" flag, is what makes it correct: translation
*replaces* the description and a deep-crawl can fill one in later, and both must
re-detect rather than serve a stale answer. A hash rather than the text itself because
this persists into `jobs.json` — storing the description twice would roughly double the
file, while hashing 22,000 characters costs ~10 us against a 33 ms `detect()`. The
write-back is guarded to real `dict`s, because `detect_language` is also called with
pandas rows during raw Search display and those must never be mutated.

**And Search now fills that cache instead of throwing its work away.** `is_category_uncertain`
already ran langdetect at Search time on every listing whose Type badge it couldn't pin
down without translation — measured at **4,434 ms over 552 of 800 listings** — and because
a DataFrame row is a `pandas.Series`, not a `dict`, the write-back guard above (correctly)
refused to memoise onto it. Filter then repeated all of it.

`_detect_language_pair` now computes the verdict and fingerprint into two real DataFrame
columns *before* anything asks for them, and those columns ride through
`df.to_dict('records')` into `jobs.json`. So `is_category_uncertain` reads the answer, and
**Filter's language step opens an already-warm cache — langdetect is called 0 times on a
fresh load.** Detecting every row rather than only the uncertain ones is deliberate: it
doesn't increase total work (800 detections once, versus 552 at Search plus 800 at Filter),
and it moves what remains off the Filter button — which you sit and wait on — and under
Search, which is network-bound and minutes long regardless.

The realistic path a person actually takes, 800 listings:

| | before | after |
|---|---|---|
| Search post-processing | ~4,400 ms | 10,956 ms (absorbs the detection) |
| **Filter, first click** | **14,120 ms** | **1,203 ms** (11.7x) |
| **Filter, every click after** | 14,120 ms | **392 ms** (36x) |

Survivor count identical at 3/800 throughout. Verified separately: 400 listings pushed
through the real `_finish_run_search_df`, every verdict equal to raw `detect()` (0
mismatches), all 400 surviving `save_jobs`/`load_jobs`, and `detect()` called **0 times**
by the Filter that followed.

Verified with six checks: verdicts identical to raw `detect()` across 300 mixed
DE/EN/FR listings; second pass identical to first; re-detection *does* fire when the
description changes (de -> en); a forged stale entry is ignored; a `pandas.Series` gains
no keys; sub-40-character text still short-circuits. Then round-tripped through the real
`save_jobs`/`load_jobs` — cache intact on 40/40 listings, `jobs.json` still valid JSON,
~130 bytes per listing of overhead.

### 2. Sponsor-list matching — 7.5x

`_company_matches_sponsor_list` fuzzy-matches every listing's employer against a
government register of up to ~130,000 names. Three mechanical speedups, no rule changes:

- a **length-bucketed index**, since `SequenceMatcher.ratio()` cannot reach the threshold
  between two names of very different lengths;
- `real_quick_ratio()` / `quick_ratio()` as a **prefilter** — both are documented *upper
  bounds* on `ratio()`, so anything they reject could never have passed;
- a **per-register verdict memo**, since the same employer recurs across many listings.

Index and memo live under tuple keys (`('__len_index__',)`, `('__verdict_cache__',)`)
that can never collide with a real normalized company name.

**217.6 s -> 29 s** for 200 listings against 30 companies. Differentially verified against
the old logic across 533 probes: **0 mismatches**.

### 3. Two hot regex guards — 21.2x on the common path

`is_too_senior` ran three `years?` regexes over every description; `has_conflicting_location_label`
ran a scan for location contradictions. Both now bail early on a cheap substring test
(`'year' not in combined_text`, `'location' not in text.lower()`) — a string the regex
would have had to contain anyway, so a listing that lacks it could never have matched.

Verified across 1,083 generated descriptions x 2 functions: **0 mismatches**.

### 4. Qt: per-row work hoisted out of the render loop

Rendering 1,000 rows: **1,965 ms -> 1,257 ms**.

- **`_non_editable_flags()`** (7 call sites across 3 files). `~Qt.ItemIsEditable` is not
  a cheap C bit-flip — it goes through Python's `enum` module (`__invert__` -> `_decompose`
  -> a comprehension over every flag), costing **508 ms of a 1,678 ms render**. Computed
  once, **lazily** (see the crash below); verified to compare equal to the per-item value,
  with `ItemIsEditable` cleared and every other flag preserved. 200,000 lookups: 84 ms
  cached vs 16,306 ms recomputing — 193x of the win kept despite the function call.
- **Per-row stylesheets -> global QSS.** The Jobs and Applications tables built an Apply
  and a Remove button *per row* and called `setStyleSheet()` on each, making Qt re-parse
  the CSS every single time (~200 ms per 1,000 rows). They now carry object names
  (`RowApplyButton`, `RowRemoveButton`, `RowDownloadButton`, `DangerButton`) styled once
  in `styles.py`.
- **One shared `QCursor`** instead of a fresh `QCursor(Qt.PointingHandCursor)` per button
  per row.

### 5. Excel export — shared style objects

openpyxl style objects are immutable value objects the workbook interns anyway, but the
export built a fresh `Alignment` for **every cell** (~10,000 on a 1,000-row export) plus a
`Font`, `Fill` and `Alignment` per badge. They are now module constants, with badge fills
memoised by colour. **2,240 ms -> 1,754 ms** for 1,000 rows, 0 style mismatches across
610 cells.

Stopped there deliberately: the remaining ~1.75 s is openpyxl's own style *interning*
(`hash()` on every `cell.font =` assignment, 294k calls). Beating it means writing
`cell._style.fontId` through private APIs — a corrupt-workbook risk on any openpyxl
upgrade, for a one-click export that already finishes in under two seconds.

### Measured and rejected

- **Regex alternation instead of `any(kw in text ...)` loops.** Sounded faster; measured
  **0.3x** — i.e. materially *slower*. Not applied.
- **Capping the langdetect window.** The documented misdetection bug is exactly this: a
  1,284-character English opener made every window below 3,000 characters report the
  wrong language. A cap high enough to be safe (10,000) turns out to touch **no real
  listing on disk** — the longest is 4,499 characters — so it buys nothing for real risk.
  Not applied; memoisation (#1) got the win instead.
- **Replacing `setCellWidget` with an item delegate** (408 ms/1,000 rows) and
  **`_remove_fake_listings_list`** (214 ms). Both are real costs, but both need a redesign
  whose behaviour risk outweighs the gain at realistic table sizes. Left alone.

### The crash this pass caused, and how it got caught

The first build of this optimisation pass **shipped an .exe that died instantly on
launch** with `0xC0000409` (STATUS_STACK_BUFFER_OVERRUN) — while all 506 tests passed.

The cause was the Qt hoists above. Written as module-level constants:

```python
_NON_EDITABLE_FLAGS = QTableWidgetItem().flags() & ~Qt.ItemIsEditable   # at import time
_HAND_CURSOR = QCursor(Qt.PointingHandCursor)                           # at import time
```

Constructing a Qt widget — or any `QGuiApplication`-dependent object like a `QCursor` —
**before a `QApplication` exists** is undefined behaviour. It happened to work when run
from source and in every test, because `tests/harness.py` builds a `QApplication` *before*
importing the UI modules. The frozen app imports them *first*. The test suite could not
have caught this in-process at any assertion count: once a `QApplication` exists it cannot
be un-created, so the failing order is unreachable from inside a passing test process.

Fixed by making both **lazy** — built on first use, when a `QApplication` is guaranteed to
exist — which keeps 193x of the speedup.

The permanent regression test imports **every** module in `app/` and `app/ui/` in a
**fresh subprocess** with no `QApplication`, asserting each imports cleanly and that none
of them quietly constructs a `QApplication` of its own. That is the frozen app's exact
import order, and it is the only way this class of bug is visible. Suite 5 went from 72 to
105 assertions.

This is the same lesson as audit round one, in a new costume: **a fix verified only on the
unit is not verified.** Last time the gap was "tested on hand-built dicts, never through
pandas". This time it was "tested in a process that had already done the setup the real
binary hasn't done yet." The build is not verified until the built artifact is launched —
so that is now part of the routine, not an afterthought.

All **539** assertions (471 offline + 68 live) pass, and the rebuilt `RoleHound.exe` was
launched and confirmed running with a live window before this was called done.


## The modularization pass — `pipeline.py` became `app/pipeline/`

`pipeline.py` had grown to **6,453 lines — 64% of the whole codebase in one file**, with
134 functions and 129 constants. The median function in it was a healthy 14 lines; the
damage was concentrated in the file's sheer size and in nine functions over 80 lines,
`run_search` worst at 610. That is what makes a bug hard to find: not bad code, but too
much of it in one place with no map.

**This was a restructure, not a rewrite.** Rewriting would have thrown away the dozens of
comments in this file that each record a real, expensive bug — the NaN guards, the
langdetect misdetection window, the Excel `#555` crash, the 0xC0000409 post-mortem. Those
comments are the most valuable thing in the file. Every one moved with its code.

### How it was done safely

Moving 6,453 lines by hand is how you lose code. Instead the split was computed:

1. **A dependency graph** of all 264 top-level names, built with `ast` — for each name,
   which other top-level names its body references.
2. **A layer assignment**, lowest first, with the rule that a module may only import from
   modules below it. The first pass reported **7 layering violations**; each was a
   genuine mis-grouping (a registry dict separated from the functions it points at, a
   Canadian government dataset id that pattern-matched as an Apify dataset), and fixing
   them left the module graph **provably acyclic** — checked before a single line moved.
3. **Mechanical extraction**, each definition moved verbatim together with the comment
   block above it.
4. **Proof of identity**: every one of the 264 definitions was found in the new package
   and its AST compared against the original. `MISSING 0, EXTRA 0, DUPLICATED 0, CODE
   DIFFERS 0.`

The layout, lowest level first — each may only import from the ones above it:

| module | lines | holds |
|---|---|---|
| `errors` | 7 | `SearchCancelled` |
| `text` | 183 | `dig`, `strip_html`, `is_true_flag`, `text_of` |
| `geo` | 201 | country/city tables |
| `rules` | 371 | the content rules |
| `language` | 379 | detection + translation |
| `company` | 259 | employer-name extraction |
| `claude_screen` | 402 | the Claude pass |
| `sponsorship` | 702 | sponsor registers + matching |
| `apify` | 95 | actor plumbing |
| `sources_urls` | 583 | per-site search URLs |
| `sources_apis` | 483 | direct API fetchers |
| `sources_norm` | 102 | platform row normalizers |
| `google` | 817 | query building + deepening |
| `preflight` | 444 | pre-run health checks |
| `filters` | 310 | `reapply_filters` |
| `search` | 1,519 | `run_search` |

`__init__.py` re-exports all 264 names with an explicit `__all__`, so every existing
`from app import pipeline` / `pipeline.whatever` in the app keeps working untouched — the
split is invisible from the outside.

### Bugs and problems found and fixed along the way

- **The generator's own `id()` bug.** The token cache was keyed on `id(body)`, and CPython
  reuses the id of a freed temporary string — so one module was handed another's token set
  and lost its `datetime` import. Caught because the suite ran, not because it looked
  wrong. Now keyed on the text.
- **Imports decided from prose.** Import detection ran a word regex over the raw text, so a
  name mentioned only in a *comment* counted as a use, dragging **35 unnecessary imports**
  into modules that never referenced them. Now AST-based, and multi-name `from X import
  a, b, c` is trimmed to just the names used.
- **Two dead locals.** `want_jooble` and `want_remotive` in `_run_direct_api_searches`
  survived an early-return that was deleted. Nothing read either. A variable that reads
  like a decision but controls nothing costs the next debugger real time to rule out, so
  both are gone; the reasoning stayed.
- **A hardcoded absolute path in a test.** `t2_sources.py` read the pipeline source from
  `C:\Users\the user\...` — it now resolves relative to the test file, and reads the whole
  package.
- **41 orphaned comment lines.** A comment block separated from its statement by two blank
  lines was missed by the first extraction pass, which would have stranded the notes
  explaining why seek.com.au, careerone.com.au and jooble.org are excluded from direct
  search. The coverage check caught it; comment runs are now absorbed into the block that
  follows them.
- **`DetectorFactory.seed = 0` nearly lost.** It is a bare statement, not a definition, so
  the definition-based extraction did not see it. Without it langdetect is
  non-deterministic and the language cache's entire correctness argument collapses. It is
  now explicitly injected into `language.py`.

### `run_search`: 610 → 434 lines

Its largest piece was a 192-line `if run_google:` block — a genuinely separable phase
(pre-check, the one combined Google actor call, normalizing pages into rows, then the four
additive follow-up searches). It only ever appended to `rows` and read `done`/`total` to
report progress, so it lifted out into **`_run_google_phase`** with the nested
`run_actor_and_fetch` closure passed in explicitly.

That branch had **never been executed by a test** — every existing `run_search` test used
`actor_order=('indeed',)`. It now has one: suite 4 drives the whole Google phase against a
fake Apify client, asserting the organic result becomes a row, that an excluded job board
(LinkedIn) never does, and that all six progress markers fire. Suite 4 went 43 → 54.

### Where it landed

- **pyflakes reports 0 findings across the entire package** — no undefined names, no
  unused imports.
- **550 assertions green** (482 offline + 68 live), up from 539.
- The rebuilt `RoleHound.exe` was launched and confirmed running with a live window.
- No performance regression: Filter's first click 918 ms, subsequent 381 ms, survivors
  identical at 3/800.

### What is still big

Five functions remain over 150 lines: `_run_direct_site_searches` (266), `_deepen_google_results`
(235), `reapply_filters` (211), `_run_direct_api_searches` (187), `_preflight_check_api_sources`
(183). Each is a genuine sequential phase rather than tangled logic, and each is now
isolated in a module of its own — but none has been split, and none should be split
without a test covering it first, which is the lesson the Google phase just taught.


## Splitting the big functions — tests first, every time

The package split fixed *where* code lives. This pass fixed *how big each piece is*. The
rule throughout, learned the hard way from the Google phase: **a function with no test
does not get split until it has one.** Splitting code you cannot verify is a guess.

| function | before | after | what came out |
|---|---|---|---|
| `reapply_filters` | 211 | **56** | one function per pipeline step (7) |
| `_deepen_google_results` | 235 | **60** | `_deep_crawl_plan`, `_deep_crawl_run_input`, `_absorb_deep_crawl_items` |
| `_run_direct_site_searches` | 266 | **63** | `_direct_site_tasks`, `_direct_site_run_input`, `_absorb_direct_site_items`, `_report_direct_site_outcomes` |
| `run_search` | 434 | **~230** | `_build_search_plan`, `_run_actor_and_fetch`, `_process_plan_item`, `_run_platform_locations`, `_SearchProgress` |
| `_run_google_phase` | 206 | **142** | `_absorb_google_pages`, `_run_google_followups` |
| `_preflight_check_api_sources` | 183 | **~50** | `_register_api_preflight_checks` (harness vs catalogue) |
| `_run_manual_assisted_search` | 158 | **~60** | `_launch_manual_assist_browser`, `_manual_assist_one_site` |
| `_run_direct_api_searches` | 187 | **126** | `_run_jooble_searches` |

**Functions over 120 lines: 9 → 5.** Median function length: **16 lines**. The five that
remain are deliberate: `_register_api_preflight_checks` and `_run_direct_api_searches` are
flat catalogues — one block per source, and splitting a list into smaller lists helps
nobody.

### `reapply_filters` reads as the pipeline now

Every step was already delimited by its own `FILTER_STEP_START`/`FILTER_STEP_DONE` pair,
but all seven were inlined in one body. Each is now its own function, and the top-level
reads as seven calls you can take in at a glance — so "which step broke?" is answered by
reading eight lines, not 211.

### `run_search`: the `nonlocal` that was blocking everything

Its three helpers could not be lifted out for one reason: the progress counter was a plain
`int` mutated through `nonlocal` from worker threads, guarded by a separately-declared
`done_lock`. Nothing but a closure can reach a `nonlocal`, so all three had to stay nested
— and nested means untestable.

Both became one `_SearchProgress` object holding the counter *and* its lock. That made the
pairing structural rather than a convention, and the three helpers became ordinary
module-level functions. `run_search` binds them with `functools.partial`, so every call
site inside it reads exactly as before — only the definitions moved.

This was safe to do mechanically because `done`/`total` feed **only** the progress display
— every single use is a `progress_cb` argument — so a mistake could show a wrong number
but could not touch a row of data.

### The tests written to make this possible

Suite 4 went from **43 to 142 assertions**, almost all of them characterization tests
written *against the unsplit code* and then required to pass unchanged afterwards:

- **`_deepen_google_results`** (18) — including that a linked page inherits its
  **referrer's** country rather than the first row for that domain. That rule exists
  because of a real bug where a French listing was stored as `country='Canada'`, and it
  had never been tested.
- **`_run_direct_site_searches`** (14) — the listing page kept as a fallback row, referrer
  matching, excluded boards, and that a failed crawl loses nothing.
- **`_run_direct_api_searches`** (18) — mostly Jooble's lifetime budget. That key allows
  500 requests *forever*, so it is the one place a bug is unrecoverable rather than
  annoying: an exhausted key is never called again, a malformed one is flagged, a failure
  is logged rather than raised.
- **`_preflight_check_api_sources`** (26) — that Jooble is **never** probed over the
  network (same budget), that results are reported in **queue order** rather than
  completion order (asserted by making the first check the slowest), and that a failure
  becomes a structured problem dict.
- **`_build_search_plan`** (11) — the location-scoping rules, now checkable directly
  instead of inferred from how many times a fake actor was called.

Three of those tests failed when first written, and in **all three cases the test was
wrong, not the code**: a Jooble country with no key is deliberately *not* a problem
("just not set up yet"); `arbetsformedlingen.se`'s API is hosted at `jobtechdev.se`; and
the direct-API source labels carry the location (`'arbetsformedlingen.se for Sweden'`).
Each was verified against the code and the assertion corrected rather than the behaviour
changed.

### Where it landed

- **pyflakes: 0 findings across the entire application.**
- **638 assertions green** (570 offline + 68 live), up from 550.
- The rebuilt `RoleHound.exe` was launched and confirmed running with a live window.


## The UI layer — where the biggest function actually was

Every pass so far had worked on `app/pipeline/`. Measuring the UI layer for the first
time found something uncomfortable: **the single largest function in the whole codebase
was not in the pipeline at all.**

`MainWindow._on_progress_log` was **286 lines, 43 if/elif branches, 25 message
prefixes** — larger than `run_search` — and it renders every line you read in the Log.
It had **zero test coverage**. The Log protocol was tested only from the *producing* side
(that the pipeline emits `FILTER_STEP_START:` and friends); nothing had ever checked that
anything *received* them correctly.

### Golden snapshot first

A 286-line string dispatcher cannot be split safely on inspection. So before touching it:
a realistic full-search transcript covering **all 25 prefixes** was pushed through it, and
the exact rendered Log text recorded as a golden file (`tests/golden_progress_log.txt`).
Wall-clock timestamps and live timer values are normalised, so the snapshot is stable
across runs — the first version was not, and would have passed only in the second it was
written.

Any change to the dispatcher must now reproduce that output **character for character**.

### From a chain to a table

The shape turned out to be perfectly regular: 32 guard clauses, each an exact match or a
prefix test, each ending in `return`. So each became a small handler method, and the
routing became a declared table:

```python
_LOG_ROUTES = (
    ('exact' , 'TOKEN_CHECK_START', '_log_token_check_start'),
    ('prefix', 'TOKEN_CHECK_ITEM:', '_log_token_check_item'),
    ...
)
```

Order is preserved exactly — one ordered tuple walked in the same sequence the if/elif
chain used — so no message can route differently than before. The golden snapshot came
back **byte-identical**.

The table is a module-level constant rather than a class attribute, because the Log
protocol belongs to the protocol, not to a window instance. That has a real payoff: the
protocol can now be **inspected by a test**, which was not expressible before. Suite 5
now asserts that every structured message the pipeline emits **has a route** — without it,
a newly-added message silently falls through to the generic handler and renders as a raw
protocol string in the Log.

### `SetupWizard.__init__`: 228 lines

A constructor doing five unrelated jobs. The file already had `_build_api_keys_section`,
so the pattern existed and had simply never been applied to the rest. Split into
`_build_credentials_section`, `_build_date_section`, `_build_platform_section`,
`_build_country_section` and `_build_button_bar`, so `__init__` now shows the dialog's
structure at a glance. Its 13 existing round-trip assertions were the safety net.

### A failure worth recording

The first version of the dispatch refactor failed all 71 of its own tests. The cause was
**the test, not the code**: the light stand-in used to drive `_on_progress_log` had a log
panel and nothing else, which was enough when the function was self-contained but not once
it delegates to sibling handlers. The stand-in now borrows `MainWindow`'s methods via
`__getattr__` instead of constructing a whole window. Worth stating plainly: splitting a
function *does* change what its caller needs, and a test written against the monolith can
legitimately need updating — the discipline is proving the *output* is unchanged, which
the golden snapshot did.

### Where it landed

- **Functions over 100 lines, whole app: 8 → 7**, and the largest UI function went from
  286 lines to a table plus 31 handlers.
- **713 assertions green** (645 offline + 68 live), up from 638.
- **pyflakes: 0 findings across the entire application.**
- Median function length across all 348 functions: **10 lines**.
- The rebuilt `RoleHound.exe` was launched and confirmed running with a live window.


## `search.py` became a subpackage

The last file over 1,500 lines. Split the same way as the pipeline itself: dependency
graph first, layer assignment, prove the module graph is acyclic, then move definitions
verbatim.

| module | lines | holds |
|---|---|---|
| `direct_site` | 303 | crawling each job board's own search URL |
| `direct_api` | 213 | public-API sources, and Jooble's lifetime budget |
| `manual_assist` | 193 | the sites that need a real browser and a human |
| `google_phase` | 305 | the combined Google call and its follow-ups |
| `runner` | 641 | `run_search`, the plan, the worker threads, `_SearchProgress` |

**Zero layering violations on the first attempt**, and all 25 definitions verified
byte-identical afterwards (`MISSING 0, EXTRA 0, CHANGED 0`). No file in `app/pipeline/`
now exceeds 863 lines.

### A real find: the facade had drifted

Syncing `app/pipeline/__init__.py` against what its submodules actually contain revealed
that **four modules were out of date** — `filters` re-exported 3 of 10 names, `google` 19
of 24, `preflight` 9 of 10, `search` 9 of 25. Every function created by the earlier
function-splitting passes had been reachable as `pipeline.search.X` but not as
`pipeline.X`. Nothing depended on the missing 29, so nothing was broken — but a facade
that claims to re-export everything and quietly doesn't is the kind of half-truth that
costs someone an afternoon. Rebuilt from the real contents; `__all__` is now 293 names.

### Test changes this forced

`from .x import name` binds a new name in the importing module, so a monkeypatch has to
target the namespace the **caller** reads it from. Every patch was retargeted to its real
owner (`runner`, `google_phase`, `direct_site`, `direct_api`), and `t2_sources.py`'s
cross-source scan switched from `glob` to `rglob` so it still sees the whole package.
This is the third time packaging has moved a patch target; it is a normal consequence,
not a defect.

**713 assertions green, pyflakes 0, exe rebuilt and confirmed running.**


## Static type checking (mypy)

Tests only check the paths they happen to run. A type checker checks every path in every
function, including the error branches nothing exercises — which is exactly where this
project's most expensive bugs lived: a value that is a `str` on the happy path and `None`
or a pandas `NaN` float on another.

`mypy.ini` configures it, and `tests/t0_static.py` runs it (plus pyflakes) as suite 0 of
the campaign, so it cannot quietly rot.

### Two configuration traps, both real

**`check_untyped_defs = True` is the setting that makes this meaningful.** Without it,
mypy skips the *body* of any function with no annotations — which was most of this
codebase — and reports almost nothing while appearing to pass. The first run without it
found 7 issues; with it, 41.

**PySide6 ships a `.pyi` stub with a syntax error in it** (`QtGui.pyi:1073`, an unexpected
indent in their own generated file). A stub that will not parse is fatal: mypy aborts the
entire run at that line and checks nothing of ours, while printing a confident-looking
single error. `follow_imports = skip` does not help — mypy still parses it. The fix is
`no_site_packages = True` plus a per-library `ignore_missing_imports`.

### What the 41 findings actually were

Triaged one by one, and the result was consistent: **not one was a live crash.** Every
function mypy flagged for receiving `None` already guarded against it — `sanitize_filename`
does `name or ''`, `_extract_company_from_text` does `(title or '').strip()`, and all four
were confirmed None-safe by calling them.

What mypy really found is that **the annotations were lying.** They promised `str` on
functions that genuinely accept `str | None`. That is worse than no annotation at all: it
invites someone to trust the signature and delete the guard that makes it safe.

| category | count | fix |
|---|---|---|
| annotations claiming `str` on None-safe functions | 13 | widened to `str \| None` |
| containers mypy could not infer from `{}` / `[]` | 9 | annotated |
| defaults that never matched their parameter's type | 3 | corrected (a tuple default on a `list[str]` param, `None` on `list[str]`, `frozenset()` on `set[int]`) |
| `Optional` used where the invariant was implicit | 6 | narrowed explicitly, or asserted with the reason |
| a cache stored as an attribute on a function object | 2 | moved to a module-level dict |
| deliberate mixed-key dict (the sponsor register) | 2 | typed as `dict` and documented |

Two structural improvements came out of it. `_load_direct_search_overrides` kept its cache
as an *attribute on the function object* — legal, but invisible to every tool and
surprising to read; it is a module-level dict now. And `MainWindow` assigned
`wizard.result_settings` (which is `None` until the wizard validates) straight into
`self.settings`; it now checks first, so a future dialog path that accepts without
building cannot overwrite `settings.json` with `None`.

### One bug I nearly introduced

Fixing a set-vs-list complaint, `broken_domains = sorted(broken_domains)` was renamed to
`ordered_broken_domains` — but two lines below still read the old name, so
`broken_urls_cb` would have received an unsorted **set** instead of the sorted **list**.
Caught by grepping the uses immediately after the rename, before running anything. Renames
are not local.

### How much is mypy actually catching? An honest measurement

Injecting a realistic bug — `_probe: str = row.get("title")`, where `.get()` can return
`None` — gives two very different answers:

| the function's signature | mypy |
|---|---|
| `def is_unpaid(row):` (as it is today) | **blind** — `row` is `Any`, so `.get()` is `Any`, and `Any` satisfies everything |
| `def is_unpaid(row: dict[str, str]):` | **caught**: `Incompatible types in assignment (expression has type "Optional[str]", variable has type "str")` |

So mypy's reach is directly proportional to how many parameters carry annotations, and
most still do not. **A green mypy run today proves less than it appears to.** It is a real
safety net for the annotated surface and worth keeping green, but it is not yet checking
the core data path.

(That measurement itself needed correcting: the first three attempts at it silently
patched nothing, because the real signature is `def is_unpaid(row):` and the string being
replaced assumed `-> bool`. Three "mypy did not catch it" results were no-ops, and had I
trusted them I would have concluded something false about the tool.)

### The next real step, and why it is not just "annotate everything"

The obvious move — annotate `row: dict[str, str]` — would be **another lie**. A RoleHound
listing is heterogeneous: `title` is a `str`, `claude_match` an `int | None`,
`thin_description` a `bool`, and `description` can arrive as a pandas `NaN` float. The
honest tool for that shape is a `TypedDict` declaring each field's real type, which would
let mypy check the core data path properly. That is a real piece of work and has not been
done.

**719 assertions green (651 offline + 68 live), pyflakes 0, mypy 0 across 38 files.**


## The app now reads new job sites by itself

Google finds a page full of jobs on a site RoleHound has never seen. Until now that was a
dead end: the page became one row, every posting behind it was lost, and the domain went
into a dialog asking the user to open the site, find a posting, and paste its URL back. In one
real search **31 domains** were in that state.

Now the app works it out itself, in the same run.

### The method, and why each step is there

Copied from what actually worked when a person did it by hand:

1. **Find the container holding the job cards.** A job board renders its postings as a
   repeated block. This is the strongest signal on the page and needs no model.
2. **Take the links from inside that container only.** This is what separates the four
   real postings on berlinstartupjobs.com from the ~130 navigation, category and company
   links around them.
3. **Open one and confirm it is a single posting** — its title is not "27 Data Scientist
   Jobs in Berlin", its body is substantial, and it contains posting language.
4. **Confirm the glob does not also match the non-job links.** This is what separates
   `/engineering/**` (postings) from `/jobs/**` (postings *and* search pages).

Where the structure is genuinely ambiguous, Claude reads the **link text** — a posting's
link text is a job title, a category's is a topic. Its answer goes through steps 3 and 4
unchanged and is never trusted on its own. Paths it names that were not actually on the
page are discarded.

Whatever is learned is saved to `discovered_job_patterns.json` and merged into the
built-in table, so a site is learned **once, ever**. A hand-written pattern always wins.

### Why the verification is not optional

A first version skipped steps 3 and 4 and simply took the most common path segment. Every
domain it "verified" looked fine until the URLs were opened:

    builtin.com/jobs/eu/germany/berlin/data-analytics/search/data-science  <- a search page
    arbeitnow.com/jobs/companies                                          <- a company index
    spaceindividuals.com/jobs/australia                                   <- a country page

All three match `/jobs/**`. Accepting them would have aimed a **paid** crawler at search
pages — worse than no pattern at all.

### Four bugs found while building it

- **The biggest group won.** Only the largest candidate group was kept, so on
  berlinstartupjobs.com the navigation menu (16 guide articles) beat the 4 real postings
  and they were discarded before they could be checked. Every group is now verified in
  turn.
- **Claude was asked for glob syntax** and returned a regex (`/*/[a-z0-9-]+/`) the matcher
  could not use, so it silently fell back. It is now asked to *list the posting URLs* —
  the part it is good at — and the glob is derived locally.
- **`?share=` links counted as separate pages**, so a real posting with six share buttons
  looked like an index and was rejected. Siblings are now compared as normalized pages.
- **A single container was ignored.** The code required three or more elements matching the
  selector, missing the commonest shape of all: one `<div class="jobs-list-items">` holding
  twenty links. Repetition is established by the link count, not the element count.

mypy caught a fifth before it ran: `_glob_for` returns `str | None` and its result was
being handed straight to `fnmatch`.

### What is left for the user

Only sites a **person** has to clear: a cookie banner, a consent wall, a sign-in, or a
listing built entirely in JavaScript. The dialog says so now, and explicitly states that
working out how a site builds its job links is not his job. The Log names the reason per
site — "refuses automated requests (HTTP 403)" or "builds its job list with JavaScript".

**871 assertions green, pyflakes 0, mypy 0 across 40 files, exe rebuilt and confirmed
running.**


## Known limitations

- **Apify usage limits.** The free plan gives $5/month of credits — a full multi-
  country, multi-platform search can burn through that. `Monthly usage hard limit
  exceeded` means you need to top up or wait for the next billing cycle.
- **Translation still adds some latency** even though it now runs in parallel (up to 30
  concurrent requests, see [Design decisions](#design-decisions-and-things-that-were-tried-and-reverted))
  — a search covering many non-English-speaking countries will still take noticeably
  longer than an English-only one, just not as long as before.
- **The keyword filters are literal substring/regex matches, not language
  understanding** — they can occasionally over- or under-match on unusual phrasing
  (e.g. "hybrid role, fully remote-friendly culture" could trip the on-site/hybrid
  keyword despite being genuinely remote). The Claude final pass exists specifically to
  catch cases like this that keyword matching can't.
- **LinkedIn's workplace tag, employment type and every LinkedIn filter** depend on what the
  third-party `apimaestro/linkedin-jobs-scraper-api` Apify actor currently returns (`work_type`,
  `job_insights`, `remote`, `date_posted`, `sort`, `easy_apply`, `under_10_applicants`); if it
  changes its output schema, `normalize_linkedin_pro` and `actor_filters` need updating. It
  returns no seniority field, so the Seniority column reads the title for LinkedIn rows.
- Indeed and Glassdoor don't expose an `employmentType`-equivalent field, so their
  `Type` badge falls back to keyword detection or defaults to Full-Time.
