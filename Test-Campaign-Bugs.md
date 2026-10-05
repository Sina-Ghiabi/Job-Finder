# Fault register — the ten-country test campaign

One register, kept across every country. Faults are recorded as they are found and fixed
**after** a country's run is finished, never during it: fixing mid-run changes the thing
being measured. The next country's run then re-checks everything marked FIXED, which is why
nothing is ever deleted from this file.

Every entry names its evidence — a log line, a real URL, a measured number. Nothing here is
written from reasoning alone.

| Status | Meaning |
|---|---|
| **OPEN** | found, not yet fixed |
| **FIXED** | fixed and re-measured, awaiting confirmation on the next country |
| **CONFIRMED** | a later country's run proved the fix holds |
| **RESOLVED** | investigated and found not to be a fault |
| **BY DESIGN** | looks like a fault, is a deliberate choice |

---

## Where the faults are clustering

Updated as the campaign goes. This is the part to read first.

| Area | Open | Fixed | Total | What keeps going wrong here |
|---|---|---|---|---|
| **Telling a page of jobs from a job** | 0 | 4 | 4 | The hardest single question in the project. A URL is the only honest signal and every board shapes it differently. |
| **The keyword filters** | 0 | 3 | 4 | A word that means one thing about a desk means another about a server. Three of the four were vocabulary; the fourth was a rule that turned out to be right. |
| **Getting the real text of a posting** | 0 | 3 | 3 | Sites return menus, sign-in walls and JavaScript shells; length alone never proves a page is a posting. |
| **Reporting a failure** | 0 | 1 | 1 | Things fail quietly. A search can finish "successfully" and be short several hundred listings. |
| **What an actor will accept** | 0 | 1 | 1 | An actor refuses a value outright rather than trimming it, and takes its whole platform down with it. |
| **Claude's screening stage** | 0 | 1 | 1 | A JSON schema that permitted one field and demanded eight. |
| **Cost arithmetic** | 0 | 1 | 1 | Stages were left out of estimates; corpora differ six-fold between countries. |
| **How the code is edited** | 0 | 1 | 1 | A regex written through a shell heredoc became an unmatchable pattern. |
| **Telling Sina which site to go and fix** | 3 | 1 | 4 | Three separate messages sent him to fix sites that were working. A wrong warning costs more than no warning. |
| **The search crashing outright** | 0 | 2 | 2 | A C library in a thread pool, and nothing written to disk until the end — so one crash costs three hours and every credit spent. |
| **What the search asks for** | 0 | 4 | 4 | The newest area and the largest. Everything else is about what happens to a listing after it is found; these are listings never found at all. |
| **One title, six Levels, a résumé** | 2 | 6 | 10 | A promise with no test (a mirror file), text that outlived the decision it described (a hard-coded bio), and headers that outran their own rows (the Excel export). The two open ones are in Junior, left untouched on purpose. |
| **What a page gives us about itself** | 0 | 5 | 6 | The Oslo run. A location that was an object, a title that was half the board's name, a description that was somebody else's vacancy. None of them was a rule being wrong; all of them were the app believing a page about itself. |

**Three faults are open as of 13 September 2026 — K-2, K-3 and K-4, all found today and all in the same place: what the Log tells Sina to go and fix.** Germany's two runs are finished and every fault
either fixed and re-measured, or investigated and found not to be one.

The pattern across the campaign so far: **most faults are about not being able to tell what a
fetched page actually is.** Not the filters, not Claude, not the rules Sina wrote — the step
before all of them, where a URL and some HTML have to be turned into "this is one vacancy,
and here is its text". That is where the ambiguity lives.

The second pattern, and the one that cost the most: **a failure that does not say why.** Two
separate faults this campaign were each a one-line fix and each hid for hours behind an
unlabelled log line — a search finishing with two of its three platforms silently missing.
C-1 was the fault that hid other faults, exactly as it was written down.

The third, worth stating because it changed how the campaign is run: **three of my own
diagnoses were wrong and only measurement caught them** — a per-host fetch limit that fixed
nothing, a "173 listings" figure that was really 4, and a lower-case country code I had typed
into my own probe and then read back as the app's behaviour. Each is recorded where it
happened rather than quietly corrected.

---

## A · Telling a page of jobs from a job

### A-1 · A page of jobs was being screened as if it were a job · **FIXED**

73 of the 557 Austrian listings that reached Claude were not vacancies — category pages,
saved searches, indexes:

```
karriere.at/jobs/software              "Software Jobs | aktuell 1.500+ offen"
karriere.at/jobs/maria-enzersdorf      "Jobs in Maria Enzersdorf | aktuell 3.900+ offen"
arc.dev/en-gq/remote-jobs              "Remote Jobs in Equatorial Guinea"
eudatajobs.com/search                  "Find the best European jobs in Data and AI"
```

They are also the most expensive listings in the corpus — 6,885 characters at the median
against 3,775 for a real posting — because a page of forty jobs is longer than one job.

Fixed by `app/pipeline/pages.py`. Austria 557 → 499, Netherlands 93 → 79, about 15% of the
text that reaches Claude.

### A-2 · The first version of that rule ate real vacancies · **FIXED**

A rule reading the word "jobs" from the title or path flagged 27 genuine single postings out
of 73, including five Indeed jobs and three EURES "Student Job (f/m/x)" listings:

```
arc.dev/remote-jobs/data-cleaning                    a category page
arc.dev/remote-jobs/details/experienced-backend-dev  one job, same prefix
nl.indeed.com/job/back-end-developer-a64bd8cad308    one job, id glued to the slug
```

Fixed by deciding from the shape of the URL: a details segment, a run of five or more
digits, or a trailing token carrying a digit means one posting and outranks the title.
Digits separate an id from a word — "software", "maria-enzersdorf" and "data-cleaning" carry
none. Checked against 14 real URLs, 14 correct.

### A-3 · An index page is dropped even when nothing could be taken out of it · **FIXED, then reversed**

Sina's question, and the sharpest one asked so far. The design is: open the page, take the
vacancies, then discard the page. Measured over all 197 Austrian index pages:

```
197 index pages, every one fetched successfully
165 gave up postings — 2,185 of them
 32 gave up nothing
```

Those 32 are discarded anyway, and whatever they listed goes with them. Not one failed to
fetch, so this is not a network problem — it is that no link on the page was recognisable as
a posting. By site:

```
karriere.at        8     metajob.at            5     remoterocketship.com  2
weworkremotely     2     wearedevelopers.com   2     tuvaustria.com        2
```

`navartisglobal.com/data-engineer-jobs-in-austria` is the clearest: 84 links on the page,
not one matching any known posting shape.

The first fix was a rule: **a page that could not be emptied must not be dropped.** Keeping
it costs a few junk rows that Claude will judge; dropping it loses work silently.

**Sina's question reversed it, and he was right.** *"88 صفحه‌ای که نگه داشته شدند به چه دردی
میخورند؟"* — measured on the second German run, to nothing at all:

```
88 pages could not be emptied
76 dropped by the ordinary filters anyway
12 reached Claude -- and every one was an index page
```

```
Data Science Jobs in Germany - 2026        wellfound.com/role/l/data-science/germany
AI Engineer Jobs in Munich, Germany - 2026 wellfound.com/role/l/ai-engineer/munich
AI Jobs in Berlin                          aijobs.ai/job-location-category/berlin-germany
```

Not one real vacancy among them; 61,845 characters of nothing.

The original reasoning was wrong in a specific way. Keeping a page saves the vacancies inside
it only if keeping it is a route to them — and when the page could not be emptied, it is not.
Those jobs were never collected, no later step collects them, and the page itself is not a
job. Nothing is lost by discarding it that was not already lost.

What the rule was really protecting is A-4, and that is now handled where it belongs — see
below. So every index page is dropped, emptied or not, and the ones that gave nothing up are
**named in the Log by host**, because that is the actionable part:

```
88 page(s) list jobs but none of their postings could be recognised, so they are dropped
rather than sent on as adverts: wellfound.com (7), aijobs.ai (3), spaceindividuals.com (1).
These sites need a posting URL pattern before their jobs can be collected.
```

A count is something nobody can act on. A host is the whole of what is needed to close the
gap. Result: 807 listings reaching Claude → 795, and none of them an index page.

### A-4 · Two real vacancies flagged as index pages · **FIXED**

Among the 32 above, two are not index pages at all:

```
aop-health.com/global_en/careers/jobs/supply-chain-business-excellence-manager
weworkremotely.com/remote-jobs/airbnb-senior-data-scientist
```

Both are single vacancies. They were caught because the path contains `/careers/jobs/` and
`/remote-jobs/`, and neither carries a numeric id — so the single-posting test could not
overrule the listing test.

The signal being missed is that the last path segment is a **job title**, not a category:
"supply-chain-business-excellence-manager" and "airbnb-senior-data-scientist" are long and
specific, where "software", "devops" and "data-cleaning" are one or two generic words.

Fixed by `_TITLE_SHAPED_SEGMENT` — four or more hyphenated words in the last segment, vetoed
by `_SLUG_SAYS_LIST` when the slug itself says "jobs". Verified against the two vacancies
this entry named and against four real index pages:

| what it really is | one job? | index page? |
|---|---|---|
| `aop-health.com/…/careers/jobs/supply-chain-business-excellence-manager` | **yes** | no |
| `weworkremotely.com/remote-jobs/airbnb-senior-data-scientist` | **yes** | no |
| `wellfound.com/role/l/data-science/germany` | no | **yes** |
| `aijobs.ai/germany` | no | **yes** |
| `navartisglobal.com/data-engineer-jobs-in-austria` | no | **yes** |
| `arc.dev/remote-jobs/data-cleaning` | no | **yes** |

Six of six. This is also what made A-3's reversal safe: a genuine vacancy misread as an index
never reaches `remove_listing_pages` as a candidate, so dropping unopened index pages cannot
cost a real job.

---

## G · Claude's screening stage

### G-1 · The Job module's batch screening decided nothing at all · **FIXED**

The worst fault found so far, and it had been live since the claude_screen package was
split. Every grouped screening request came back as:

```json
{"answers":[{"listing":1}]}
```

Thirteen output tokens. No verdict, no reason, no match. `_read_structured_answer` treats a
missing verdict as "not a DROP", so **every listing came back KEPT and unscored, and the
whole first Claude pass decided nothing** — on every search, for as long as the batch path
has existed.

The cause is one missing merge in `_GROUP_ITEM_SCHEMA`:

```python
_GROUP_ITEM_PROPERTIES = {'listing': {...}}          # only this one
_GROUP_ITEM_SCHEMA = {
    'properties': _GROUP_ITEM_PROPERTIES,             # so: one property
    'required': ['listing'] + _SCREEN_OUTPUT_SCHEMA['required'],   # but eight required
    'additionalProperties': False,                    # and the rest forbidden
}
```

The grammar permitted exactly one field, demanded eight, and emitted what it was permitted.
The comment above it said "the single-listing schema with a listing number added" — which is
what it was meant to be and never was.

How it hid for so long: no error was raised, an answer came back for every listing, the
token bill looked plausible, and a stage whose job is to remove things removing nothing
looks exactly like a stage with nothing to remove.

What exposed it: Sina asked why Claude would delete the silent listings anyway. Measuring
that gave 60 KEEPs out of 60 with `match` of `None` on every one — and a 13-token answer
cannot hold a match percentage.

Fixed by merging the real properties in. The same listing now answers in 130 tokens:

```json
"verdict": "DROP", "rule": 8,
"reason": "Requires enrolment at university outside Italy.", "match": 25
```

The Thesis and Internship modules were never affected — they merge correctly.

**Everything measured about Claude's job screening before this is void**, including the
60-of-60 in F-4 below and any earlier statement about what Claude keeps or drops.

---

## F · The keyword filters — what happens before Claude

This is where most listings actually die. Of Germany's 5,718, **4,483 never reach Claude**:
1,069 duplicates, 2 fakes, then 1,702 to the work-location rule, 836 to seniority, 605 to
the English rule. Claude decides the fate of the remaining 1,235; the rules decide 78%.

The work-location rule is the biggest single step, so it was read phrase by phrase:

```
  991  said nothing about working arrangements at all
  156  "hybrid"
   88  "am standort"
   64  "on-site"
   61  "vor ort"
   37  "hybrid working"
   34  "in person"
   34  "hybrides arbeiten"
   26  "on-premise" / "on-premises"
   24  "arbeitsort"
   12  "einsatzort"
```

### F-1 · "on-premise" is about servers, not desks · **FIXED**

26 listings dropped for `on-premise` or `on-premises`. In data work that phrase means the
infrastructure runs on the company's own hardware rather than in a cloud — it says nothing
about where the person sits, and a great many genuinely remote data-engineering roles
mention it as a technology.

The word is in `ON_SITE_OR_HYBRID_KEYWORDS` in `rules.py`, which is the Job module's
vocabulary — the one Sina has said not to touch. It still needs raising, because this is not
a borderline judgement: `on-premise` is a deployment model.

### F-2 · "hybrid" fires on cloud architecture and on benefit lists · **FIXED**

156 listings dropped for the bare word. Two false shapes, both real:

```
Senior AI Engineer – Architecture & Platform (m/w/d)
   "...container-orchestrierung (eks, kubernetes/kubeflow) oder einem
    hybrid-ansatz erfahrung mit infrastructure-as-code..."

User Experience Designer "Agentic-AI & Simulation" (d/m/w/x)
   "...flexible arbeitszeit möglich  hybrides arbeiten möglich
    gesundheitsmaßnahmen betriebliche altersversorgung..."
```

The first is a cloud architecture. The second is a **benefits list** — "hybrid working
possible" beside flexible hours and a pension, which is an offer of flexibility, not a
requirement to attend.

Note the shape it shares with B-1 and B-2: a phrase in a benefits list means the opposite of
the same phrase in a requirements list, and none of these rules can tell the two apart.

### F-3 · "arbeitsort" and "einsatzort" are form fields · **FIXED**

36 listings. Both are administrative fields German boards fill in on every posting,
including remote ones — arbeitsagentur.de and EURES print "Arbeitsort: Berlin, Bonn" whether
or not the work happens there.

### F-4 · 991 listings dropped for saying nothing · **RESOLVED — the rule is right**

The largest group by far. It is Sina's own rule — a job advert that never raises the subject
means an office — and it was justified by a measurement:

> Removed, it let through 128 listings that said nothing whatsoever about working
> arrangements. Claude then deleted them anyway, writing "on-site role in Amsterdam" for
> each, which the text never said.

That is the docstring of `passes_work_location_rule`, and the argument was sound: the
listings died either way, so paying to translate and screen them first bought nothing.

**That measurement no longer holds, because the Claude prompt was changed today.** Rule 1 is
now a ladder ending in:

```
1d. Otherwise → KEEP

Three things are NOT a reason to drop under this rule:
  · the Location and Company lines in the block above
  · the absence of a remote statement — that is 1d, and 1d is a KEEP
  · anything you would describe as "implied"
```

Claude was deleting them for exactly the reasoning that prompt now forbids. So the keyword
rule is still dropping 991 German listings on the strength of a behaviour that has been
fixed, and nobody has re-measured since.

Sina asked the question that exposed this: *"چرا به هر حال Claude حذفشون میکنه؟"* — and the
honest answer is that it probably no longer does.

**The measurement was taken, and it settles it the other way.** Forty of the 1,176 silent
listings in the second German corpus, screened one at a time under the current prompt:

```
KEPT      0 of 40
DROPPED  40 of 40
```

Not a useful number — none. Claude deletes every one, so the keyword rule is saving the cost
of screening 1,176 listings to reach exactly the same answer. Sina's original reasoning holds
and the rule stays as it is.

Why they die, which is worth knowing because only one of these reasons is about location:

| | |
|---|---|
| Rule 1 — presence | 24 |
| Rule 2 — German required | 10 |
| Rule 4 — years of experience | 5 |
| Rule 8 | 1 |

Sixteen of the forty are dropped for reasons that have nothing to do with where the work
happens, so even a perfect location rule would not save them.

**One new observation, recorded rather than acted on.** Among the 24 Rule 1 drops, some are
plainly right — a machine operator, a mass-spectrometry post, "onboarding requires 6 months
in the Munich office" is in the text. Others read exactly like the inference the prompt
forbids: "Location requires presence in Germany", "Position requires presence at TUD
Dresden". That is the 1a–1d ladder not fully taking. It changes nothing today, because these
listings never reach Claude — the keyword rule drops them first — but it would matter for any
listing that does.

These are not broken listings either — they are complete adverts:

```
562 of the 991 come from EURES, 155 from arbeitsagentur.de
median length 3,155 characters
only 9 have under 300 characters
```

72% come from two official European portals that republish without a work-mode field.

---

## B · Getting the real text of a posting

### B-1 · A description that was only a navigation menu · **FIXED**

Every arc.dev posting arrived with exactly 505 characters, all of it the site's own menu:

```
"For companies Hire developers Hire designers Hire marketers Hire product managers ..."
```

Not one word of the vacancy. `thin_description` is set by character count, so 505 characters
passed for a real description and the row went to Claude, which was asked to judge a job it
had not been shown.

Fixed by `enrich.looks_like_chrome_only`: a description carrying none of the words a posting
has (requirements, we offer, Aufgaben, wir bieten…) is treated as thin whatever its length,
and re-fetched. Recovered a real posting for 8 of the 12 tried, every one a remote role.

The proof it works came later, from listings it caused to be dropped:

```
Performance Test Lead - IoT & SCADA    "Remote anywhere Hourly rate 5+ years 40 hours"
Experienced Backend Developer - Arc    "Remote anywhere Hourly rate 5+ years 40 hours"
```

Five or more years. The owner has two. They were surviving only because the posting was
unreadable.

### B-2 · Enrichment could replace a good description with a longer bad one · **FIXED**

The guard only measured length:

```python
if len(text) >= ENRICH_MIN_USEFUL_CHARS and len(text) > len(current):
```

Longer is not better. A sign-in wall is easily longer than a 4,344-character posting.
`Data Scientist / Business Analyst (m/w/d)` at CompuGroup Medical disappeared from a real
run this way — traced by hand afterwards, the row passes every rule and every filter, so
nothing removed it; its text was changed under it.

Fixed by splitting the question in two. `looks_like_chrome_only` decides whether a fetch is
worth spending and forgives a long page. `carries_posting_words` decides whether a fetched
page may REPLACE what is there, and forgives nothing — that distinction is the whole fix.

---

## C · Reporting a failure

### C-1 · A failure that would not say why · **FIXED**

```
LOCATION_DONE:Indeed|Germany|FAILED|
```

The field after `FAILED` is the reason, and it is empty.

Running the actor by hand produced the answer immediately, and it was a good one:

```
Input is not valid: Field input.datePosted must be equal to one of the
allowed values: "", "1", "3", "7", "14"
```

That message names the field, the value and the alternatives. It reached Apify's client, and
then went nowhere. Two hours of a German search ran without Indeed because a perfectly clear
explanation was dropped on its way to the Log.

`LOCATION_DONE` carries the cost in that last field, not the reason; the reason goes to a
separate `  ! …failed:` line. That line does reach the Log — but with no level, so it renders
as ordinary grey text among hundreds of progress ticks, which is why it may as well not have.

**Fixed by making it an `ERROR:` line** naming the platform, the location and the actor's own
complaint:

```
ERROR: Indeed found nothing for Germany — Input is not valid: Field input.limit must be <= 1000
```

The actor's message is always specific and always actionable; it names the field, the value
and the alternatives. Losing it costs a whole platform for a whole run, silently — which is
exactly what happened twice, and both times the fault underneath was a one-line fix.

**It hid one again, on the very next run.** The second German search, 12 September, opened
with the same line for two platforms at once:

```
LOCATION_DONE:Indeed|Germany|FAILED|
LOCATION_DONE:Glassdoor|Germany|FAILED|
```

Both inside one second of starting — too fast to be a search — and the reason was in the
`  ! …failed:` line that the run script was filtering out as noise, exactly as described
above. Running the two actors by hand gave the answer in thirty seconds: see H-1. The fault
is not that a bug existed; it is that a search ran on without two of its three platforms and
said nothing about why.

### H · What an actor will accept

#### H-1 · "No limit" is a value two of the three actors refuse · **FIXED**

Sina's instruction was unambiguous — *"هیچ Limit ای نباید در پیدا کردن آگهی باشد"* — and
`NO_RESULT_LIMIT = 100000` carried it out. Two of the three actors reject it outright:

```
Indeed     Input is not valid: Field input.limit must be <= 1000
Glassdoor  Input is not valid: Field input.limit must be <= 1000
```

Not trimmed to the maximum. Refused, before the run starts, and the whole platform's leg is
lost. Read from the actors' own published input schemas rather than guessed:

| actor | field | maximum |
|---|---|---|
| `valig/indeed-jobs-scraper` | `limit` | **1000** |
| `valig/glassdoor-jobs-scraper` | `limit` | **1000** |
| `curious_coder/linkedin-jobs-scraper` | `limitPerSource` | none |

So removing the limit is what stopped Glassdoor returning anything, and Indeed with it. The
fix is `_ACTOR_RESULT_CEILING` in `search/runner.py`, on the same principle `DATE_RANGES`
already uses for dates: **give each platform its own furthest reach, never a value it will
reject.** Verified live afterwards — Indeed 733 listings in 45 seconds, Glassdoor 753 in 89.

Global by construction: the ceiling is per actor, not per country.

#### H-2 · Country codes for Indeed · **NOT A FAULT**

Indeed's schema accepts lower case only (`de`, not `DE`). All 18 entries in `COUNTRY_ISO2`
are already lower case, so nothing was ever wrong. I reported this as a second bug first,
having typed `'DE'` into my own probe and then read my own typing back as the app's
behaviour. `.lower()` was added anyway, so that a nineteenth country entered as `GB` cannot
silently cost the Indeed leg.

### C-2 · Indeed itself · **RESOLVED — my error, not the app's**

The invalid `datePosted` came from the test script, not from RoleHound. `INDEED_DATE_OPTIONS`
in `text.py` already holds exactly what the actor accepts:

```python
'Last 1 day': '1', 'Last 3 days': '3', 'Last 7 days': '7', 'Last 14 days': '14',
'Any time': ''
```

I passed `'Last 30 days'`, which is not one of them and never was. Re-run with a real value,
Indeed succeeded and returned listings:

```
Student Assistant Computer Vision/Deep Learning
AI Product Builder / Vibe Coding Specialist (m/w/d)
WORKING STUDENT (M/F/D) - AI Innovation & Integration
Junior Data Product & AI Engineer - remote (m/w/d)
```

Worth keeping in the record for one reason: Indeed offers **at most 14 days**, where
LinkedIn and Glassdoor go back a month. The German run is missing Indeed entirely and will
need repeating; every later country gets it from the start.

---

## D · Cost arithmetic

### D-1 · The Claude cost estimate was wrong twice · **FIXED**

Told Sina ten countries would cost about $2.50. Both the number and the reasoning were
wrong: the Job module's `worth` stage was left out entirely, and Austria's 557 survivors
were counted as the Netherlands' 93.

Re-measured — exact input tokens from the API's own counter over every real listing, output
tokens from 20 real billed calls on the heaviest descriptions:

```
one screening call, mean of 20 real calls   5,871 input / 13 output tokens   $0.00297
Austria, pass 1, one listing at a time      557 x that                       $1.65
```

The heaviest single listing was 24,124 characters and cost half a cent on its own — and it
was an index page, which is what led to A-1.

---

## E · How the code is edited

### E-1 · A regex stored as a backspace character · **FIXED**

Writing the silent-about-English rule through a shell heredoc turned `\b` into an actual
backspace byte in the source, so the compiled pattern began `\x08` and never matched
anything. Every English posting read as foreign.

Caught only because an unrelated older test failed. Without that test it would have quietly
deleted almost everything. The fix is in the record rather than the code: regexes are
written with the editor, never through a shell heredoc.

---

## I · What the search asks for

The area this campaign found last and which turned out to matter most. Every fault above is
about what happens to a listing **after** it is found; these are about listings that were
never found at all, and nothing downstream can recover from that.

### I-1 · Nothing ever searched for a thesis or an internship · **FIXED**

Sina's question: *"آیا تمام Internship ها و Thesis ها نیز به درستی گرفته می شدند؟"* — and the
number that prompted it, from a real German run: **4 theses and 53 internships** out of 4,812
listings, in the country of the Masterarbeit and the Werkstudent.

The modules were not at fault. Asked of every title in the corpus that plainly offers one:

| | titles carrying the word | recognised |
|---|---|---|
| Thesis | 9 | **9** |
| Internship | 110 | **100** |

Thesis recall was perfect. The ten internship misses were `Ausbildung` (a three-year
vocational qualification) and `Duales Studium` (a degree programme) — neither is an
internship, and most were job-category labels rather than titles, so rejecting them is right.

There were only 9 thesis titles **because the search never asked for one.** The keywords sent
to every actor, and the four role terms sent to Google, are job titles:

```
"Data Science"  "Data Scientist"  "Data Engineer"  "Machine Learning"  ML  AI  …
```

Not one of `Masterarbeit`, `Abschlussarbeit`, `thesis`, `Praktikum`, `Werkstudent` or
`internship` appears in any query this app sends. Three parallel modules were sifting the
results of a search built for one of them.

**Fixed by making the search three searches**, in the order Sina specified — Jobs found and
closed, then Internships, then Theses — all landing in one pool that the existing filters
separate exactly as before. Three checkboxes at the top of Search choose which run.

Why three separate searches rather than one wider one: **Indeed and Glassdoor cap a single
call at 1,000 results** (see H-1). OR-ing thesis words into the job query would make all three
kinds share those 1,000 places, so adding theses would have cost jobs. Three calls means three
ceilings — the split raises Job's own recall rather than spending it.

And why checkboxes rather than an always-on change: with Jobs alone ticked the search takes
**one pass with the same keyword object it always used**, so the path Sina asked never to
disturb is provably the path it takes. Verified:

```
search_for=None                 -> 1 actor call: ['job']
search_for=['job']              -> 1 actor call: ['job']
search_for=[job,internship,thesis] -> 3 actor calls: ['job','internship','thesis']
```

### I-2 · A kind word alone returns the wrong field entirely · **FIXED**

Found while building I-1, by asking Indeed for the obvious query:

```
Praktikum OR Werkstudent OR Internship
   -> "Praktikum Nachhaltigkeit"      sustainability
   -> "Praktikum Producing"           media
```

Nothing in this app checks that a listing is about data or AI. The Job module has no such
rule, and neither do the other two — **the search keywords are the only field filter that
exists.** A kind word on its own therefore returns every internship in the country.

Fixed by putting the kind group and the role group side by side, which both actors read as
AND:

```
(Praktikum OR Werkstudent) ("Data Science" OR "Machine Learning")
   -> "Praktikum R&D Laser Application – Data Fusion"
   -> "PRAKTIKANT / WERKSTUDENT AI, DATA ENGINEERING UND SCIENCE (M/W/D)"
   -> "Internship and Masterthesis (m/f/d) in the Area of Large Language Models"
```

Four query shapes were tried live against the actors before this was chosen.

### I-3 · The role words were English only · **FIXED**

The same build, one step later. A first version of the role group carried English terms
alone. Measured against Indeed for Germany, 200 internship results each:

| role words | results named in German |
|---|---|
| English only | 23 |
| plus the German ones | **47** |

Both runs hit the cap, so the real gap is wider. These appear only with the German terms:

```
Werkstudent Künstliche Intelligenz – KI im Arbeitsalltag (m/w/d)
Praktikum - Künstliche Intelligenz (KI) in der Technischen Entwicklung
```

A German employer writes "Künstliche Intelligenz", a Finn writes "Tekoäly", and neither says
"Artificial Intelligence" anywhere on the page. Since the query is the only thing that checks
a listing is about data at all, a missing language is a whole country's postings never seen.
The role group now carries all twelve languages the app searches, plus Polish.

**Note for the Job pass, deliberately not acted on.** `KEYWORDS` — the job search — is still
English only and has the same gap. Fixing it would find more jobs and would also change the
one path Sina has asked twice to leave alone: *"به هیچ عنوان نمیخوام که Job دیگه دست بخوره."*
Recorded here for him to decide.

### I-4 · A dozen of the best German boards were searched for the wrong thing · **FIXED**

Caught by watching the Internship run's Log go past, which is the only way it could have been
caught -- every test passes, every count looks reasonable, and the queries are correct
everywhere they were checked:

```
[20:32:03] Checking stepstone.de for Germany: .../jobs/data-scientist
[20:32:03] Checking xing.com for Germany: ...?keywords=Machine+Learning+Engineer
```

That is the **internship** search asking StepStone and XING for "Data Scientist".

The pass's phrases reach the three actors (I-1), the Google queries (I-1) and the direct
APIs -- EURES, arbeitsagentur.de and the rest (I-1). They did not reach
`_run_direct_site_searches`, which is a different function covering a different set of
sources: stepstone.de, xing.com, wearedevelopers.com, iamexpat.de, arc.dev and the other
per-site search URLs. That one read `DIRECT_API_ROLE_TERMS` directly, so all three passes
asked it the same four job titles.

Which means the Internship and Thesis passes were quietly re-running the Job search against a
dozen of the best German boards -- paying for it, and finding nothing new, while the sources
most likely to carry a Werkstudent posting were never asked for one.

Fixed the same way the other three were: `role_terms` threaded through
`_run_direct_site_searches` and `_direct_site_tasks`, defaulting to the old constant so the
Job pass is unchanged.

**Worth noting how it hid.** Nothing failed. The searches ran, returned listings, and cost
what they always cost. Four separate code paths take a search term and three of them had been
found; the fourth looked identical from every angle except the one that mattered.

---

## J · The search crashing outright

### J-1 · A segmentation fault three hours into a run · **FIXED — cause not proven**

The third German run, with every fix of the day in it, got further than any before and then
died:

```
[03:32:54] 1596 listing(s) posted more than 30 days ago removed; 5851 kept.
[03:32:54] 134 page(s) in this search list jobs rather than being one.
[03:36:14] 722 posting(s) found inside. Fetching each one.
Segmentation fault                                      [exited with code 139]
```

Three hours and $6.40 of Apify credit, and **every listing collected went with it.** No
Python traceback, because the process was killed outright — a crash inside a C library cannot
be caught, retried or logged by anything in Python.

Two candidates, and the first one is wrong. I said so first and it is worth recording:
Playwright's sync API is not thread-safe and this stage fetches eight pages at a time — but
`fetcher.py` has carried a `_BROWSER_LOCK` around the browser rung all along, so those calls
were already serialised. Reading the code before claiming the cause would have shown that.

The remaining candidate is `curl_cffi`, which both the `chrome_tls` and `crawler` rungs use
and which has no such protection:

```python
response = curl_requests.get(url, impersonate='chrome', ...)
```

That builds a throwaway session per call, over a CFFI binding to libcurl. Hundreds of them
created and destroyed concurrently across eight threads is the documented way to get exactly
this crash. Fixed with a thread-local session — made once per thread and reused, which is
what the library asks for and is also faster. Stress-tested afterwards: 60 fetches, 8
threads, 2 seconds, 60 × HTTP 200, no crash.

**Marked FIXED but the cause is not proven, and that distinction matters here.** A segfault
leaves nothing behind to read, and the crash is probabilistic — so a run that does not crash
proves very little. What can be said is that the one unprotected use of a C library inside a
thread pool is now protected in the way its own documentation asks for.

### J-2 · A crash loses every listing collected so far · **FIXED**

The fault underneath J-1, and it outlives whatever caused that crash. `run_search` holds
every listing in memory until the very end and writes nothing until it returns. Any death of
the process — a segfault, a power cut, a killed terminal — costs the entire run: three hours
of fetching and every Apify credit spent on it.

Fixed: the collected rows are written to disk after every stage — each search pass, the
Google stage, the date filter, the expansion — to `search_checkpoint.json`, separate from
`jobs.json` because a half-finished search is not a result. A search that completes deletes
its own, so one found at startup means the last one did not finish, and the Log says when,
at which stage, and how many listings are still there.

Three rules, and the first is the one that matters: **it can never break the search it
protects.** Insurance that can cost you the thing it insures is worse than none, so an
unserialisable row is skipped rather than raised. A corrupt checkpoint reads as nothing and
is reported. And a cancelled search clears nothing, because it genuinely did not finish.

Working in the very next run: with the Internship search still going and credit nearly out,
**6,903 listings were already safe on disk.**

---

## K · Telling Sina which site to go and fix

A site that cannot be read is worth a line in the Log, because Sina can sometimes do
something about it. A site that reads perfectly well is not — and three separate messages
were telling him to go and fix things that were not broken.

### K-1 · "53 XING pages gave up nothing" — XING was working · **FIXED**

The Job run reported:

```
81 page(s) list jobs but none of their postings could be recognised, so they are
dropped: www.xing.com (53), wellfound.com (7), berlinstartupjobs.com …
```

Read as an instruction, that says XING is broken. It is not. In the same run:

```
162 XING postings in the final corpus, every one a single posting
 96 of them recovered from inside those very pages
793 listings in total recovered from inside listing pages
```

Those 53 pages gave up nothing **new** — `postings_inside` deliberately skips a link the
search already has, which is exactly what the later pages of a paginated listing look like.
Fixed by separating the two cases, which had been reported as one number:

```
N page(s) held only postings the search already had — nothing missed there.   (info)
N of M page(s) list jobs but nothing on them could be recognised as a posting
  — those sites need a URL pattern before their jobs can be collected.        (warning)
```

Only the second is a warning, and only the second names hosts.

### K-2 · "nothing could open it" for three sites that open fine · **OPEN**

The same run reported `eudatajobs.com`, `jobtensor.com` and `www.kununu.com` as unreadable.
Fetched again by hand, all three return 200:

| site | status | what is actually there |
|---|---|---|
| eudatajobs.com | 200, 18,605 bytes | 9 links — `/companies/`, `/books/`, `/search/`. The jobs are behind its search, not on the page. |
| jobtensor.com | 200, 120,299 bytes | opens; its "postings" are articles |
| kununu.com | 202, 665,292 bytes | opens behind a cookie wall; it is an employer-REVIEW site, not a job board |

The message is wrong in a way that costs Sina's time: it sends him to fix a site that opens.
What is true is narrower — nothing on the page was recognisable as a posting, which is K-1's
second case.

### K-3 · Articles and company pages pass as job postings · **MEASURED — NOT WORTH A FIX**

**Measured after L-3, against every corpus on disk — 34,693 unique listings.** kununu.com
contributed 1 row, and it is not treated as a posting. jobtensor.com contributed 5, and 2 get
through: one article ("100 most in-demand IT skills") and one Berlin listing page
(`…-Machine-Learning-Jobs-in-Berlin`). **Two listings in 35,000.**

The examples below were links found while expanding pages; almost none of them ever became
a row. The only fix available is the one this entry warned against, and L-3 then measured it
twice: tightening the address rule cost real vacancies both times. Two stray rows, which
Claude's rule 5 drops anyway, do not justify that risk. Reopen only if a real run shows more.

The original report:

Found while checking K-2, and this one changes what reaches Claude. `is_single_posting_url`
accepts any last path segment of four or more hyphenated words, and these all qualify:

```
jobtensor.com/top-it-skills-kenntnisse          an article
jobtensor.com/top-occupations-it-branche        an article
kununu.com/de/octopus-energy-metering-germany   a company profile
kununu.com/de/kartenliebe2                      a company profile
```

Eleven of kununu's 38 links read as postings and not one is a job. The rule was measured
against real vacancy URLs and holds for them; it was never measured against articles or
company profiles, which have exactly the same shape.

Worth fixing carefully rather than quickly: the same rule is what rescues
`aop-health.com/…/careers/jobs/supply-chain-business-excellence-manager` (A-4), so
tightening it blindly costs real vacancies.

### K-4 · Four sites need an account, and it is not yet known whether they are worth one · **OPEN**

Of the ten sites the Job run could not read, four are simply behind a login:

```
work.mercor.com                 sign-in wall
startup.jobs                    login wall
www.efinancialcareers.ch        login (German)
www.efinancialcareers-gulf.com  sign-in wall
```

Sina asked what he could do, and this is the one category where the answer is "make a free
account". Told him not to yet: of those same ten sites, three turned out to have no postings
at all and two are behind CAPTCHAs, so the odds are not obviously good. What is needed first
is a measurement of how many relevant jobs sit behind each wall — his time is worth more than
a guess.

Two more are beyond anyone's reach: `careers.bcg.com` and `careers.dhl.com` both answer with
a CAPTCHA, which an account does not open.

---

## L · The move to DevOps and MLOps, and what the first run under it exposed

Sina moved the Job and Internship searches off data science onto DevOps and MLOps, with
every junior and entry-level form of them, in all 13 languages and 18 countries. Thesis was
left exactly as it was. The previous vocabulary is kept whole in
`../Vocabulary-Backup/OLD-VOCABULARY.txt` and `original-source/`.

One measurement shaped the whole change: across 17,544 real European titles, **DevOps and
MLOps are never translated** — 273 and 38 occurrences, always in those letters, and zero for
every local form tried. So the local-language passes carry the English role words and add
what the local language *does* translate: the word for a beginner (`Berufseinsteiger`,
`Absolvent`, `Neolaureato`, `Jeune Diplômé`) and the word for an internship.

First real run, Austria, Job only — 3,450 listings, 171 minutes. The entry-level query
alone added 245 listings the broad query never returned; the German beginner-word pass added
533 more.

### L-1 · The local job query crashed on every call · **FIXED**

Splitting the role vocabulary so Thesis could keep its own renamed `_LANGUAGE_ROLE_WORDS`,
but `keywords_for` still referred to the old name. Because the name sat inside a function
body, importing the module raised nothing: the app started cleanly and would have failed at
the first local search. Caught by Sina asking whether the Junior words were actually
attached to the role words in every language — they were not attached to anything.

### L-2 · The Job module's field filter had never run · **FIXED**

`job_field_words.py` was written when the Pool was built and then imported by nothing. The
Internship and Thesis modules call their own copies from their finders; the Job copy was dead
code, and no test could have noticed. Measured on the Austrian run: **86 of 411** jobs
reaching Claude were Vertrieb, Verkauf, Copywriter, Customer Support, Maschinenbau and HR —
and not one of the 86 named anything in the field, so wiring it in costs nothing real.

Now the first content rule in `reapply_filters`, because it is the cheapest: one regex on the
title. Test 4.4b guards it. Its arrival broke section 4.4's fixtures, titled `Thin`,
`Onsite` and `Remote` — placeholders that could only ever pass because the filter was not
running.

### L-3 · Index pages that count their vacancies were claimed as postings · **FIXED**

Fourteen reached Claude in Austria. `is_single_posting_url` won outright on each:

```
158 Jobs Hainburg an der Donau                    karriere.at/jobs/hainburg-an-der-donau
Your search returned 22 jobs                      pnet.co.za/cmp/en/…-14116/jobs
Devops Engineer Jobs und Stellenangebote in Salzburg   stepstone.at/jobs/devops-engineer/in-salzburg
```

The fix is a title rule allowed to outrank the address: **a real vacancy never counts
vacancies.** `_COUNTS_VACANCIES` reads "158 Jobs", "aktuell 1.100+ offen", "Ihre Suche
ergab 30 Treffer", "9 results for". Two address rules were added beside it: a path ending at
`/jobs` is a list, and `/jobs/<role>/in-<place>` is a filtered list.

Measured against 31,351 real rows: **348 index pages now dropped, 1 real vacancy rescued**
(a Toyota posting at `icims.com/jobs/5612/job`, previously thrown away), **0 regressions**.

Getting there took two reverted attempts, both exactly the failure K-3 warns about:

- *Is the slug a place?* — reading German joining words (`-an-der-`, `-in-`). Those letters
  occur mid-phrase in English, and it immediately lost
  `/remote-jobs/toptal-ai-ml-engineer-for-AN-ai-driven-e-commerce-platform`.
- *Does the slug name a role?* — a word list of roles. Job titles are too varied; it lost a
  dozen at once, including `/remote-jobs/toggl-senior-full-stack`.

`weworkremotely.com/remote-jobs/<slug>` and `karriere.at/jobs/<place>` are the same shape,
and no vocabulary separates them from the address alone. The title does. **K-3 stays open**:
articles and company profiles do not count vacancies, so this rule does not reach them.

Two narrowings along the way, both from real rows: `positions` was dropped from the count
rule ("Intern 3 Months + Full time 3 Positions" counts openings in one posting), and a
query-string id must be *named* (`?ashby_jid=`) — a bare 24-character hex value was a
MongoDB filter parameter on a meetfrank.com index page.

### L-4 · wearedevelopers.com serves every vacancy twice · **FIXED**

The site publishes a Markdown copy of each page at the same address plus `.md` — "Every page
supports .md". Google indexes both and the crawler follows the link between them. Across
every corpus on disk: **95 mirror rows, all from wearedevelopers.com, not one with a title.**
Different address, so duplicate removal missed them; empty title, so the field filter kept
them. One reached Claude in Austria and was **kept, listed as "None"**.

Corrected rather than deleted, so a raw search still shows what it fetched: the address is
put back and the title and company are read out of the Markdown. Of 95: 67 live, **67 titles
and 67 companies recovered**; 12 are "Job Not Found" pages, deliberately left untitled; 16
carry no text. Applied at `_finish_run_search_df` for new searches and in `reapply_filters`
for rows already saved.

### L-5 · Exact-address duplicates kept the first copy, not the best · **FIXED**

The title pass of `_remove_duplicates_list` always walked best copy first; the exact-address
pass walked the list as it arrived. Harmless until L-4 put mirrors on their real address:
16 mirrors carry no text, and one arriving first would have deleted the full posting. Both
passes now walk the same best-first order. Test 4.4c puts the empty mirror first on purpose.

### L-6 · Taken-down vacancies reached Claude as live jobs · **FIXED**

A board still serves the address after a posting closes, with a notice in place of the job.
Nothing checked. Across **34,693 unique listings: 27 say they are gone, all 27 were read, all
27 are** — "This job has expired", "leider nicht mehr verfügbar", "Job Not Found | The
Muse", and `PL/SQL DevOps Engineer` four times over, "This job is no longer available".

Read from the first 600 characters only, where a board puts its notice; an advert saying
something else is "no longer supported" does so in its body. Removed at the pool right after
enrichment — not before, because many pages only receive their text during enrichment — and
again at Filter for rows saved before a posting closed.

### L-7 · A 5,685-listing corpus was overwritten · **FIXED (run script, not the app)**

The Austrian data-science run of 14 September was saved as `austria_job.json`; the DevOps
run the next day wrote to the same name. Only its printed totals survived. Runs are now
stamped (`austria_job_0915-0138.json`) with a stable name pointing at the newest.

### L-8 · A regex silently lost its word boundary · **FIXED — and every file checked**

Written through a shell here-document, `\b` became a backspace character, so
`_MIRROR_GONE` could never match. The result was still correct — the title rule found no
field label on a "Job Not Found" page — which is exactly why it would have gone unnoticed.
Caught because the measurement reported "0 gone" while listing twelve. Every one of the
project's 80 source files was then scanned for control characters: none elsewhere.

---

## M · One title, six Levels, a résumé, and Remote / Not Remote

Sina replaced every field vocabulary with one job title he types ("مثلا Data Engineer"), the
Job / Internship / Thesis checkboxes with one Level (Thesis, Internship, Entry, Junior, Mid,
Senior), the hard-coded profile in every Claude prompt with the résumé he uploads (PDF or
Word only), and added Remote / Not Remote. Entry, Mid and Senior are copies of the Junior
profile — vocabulary, level rule, Claude prompt — with only the level changed. The previous
files are kept in `../Vocabulary-Backup/before-title-filter/`.

Claude now works in two parts: part one decides KEEP or DROP by the Level's profile, part two
scores what is left against the résumé (`claude_screen/worth.py`).

Measured before commit: the five offline suites green (1,923 assertions), the whole keyword
Filter run on the real Austrian corpus (3,450 listings) for every Level in both modes, and the
LIVE suite run against the real APIs — Claude screened a real listing and scored three more
against a résumé (62%, 68%, 68%), a second Filter run made zero billed calls in either part,
and the Apify actor run cost $0.0010.

### M-1 · Job-Filter-Claude-Apify.md had drifted from the prompt it mirrors · **FIXED**

The prompt's own docstring promised the two were byte-identical; nothing tested it, and the
DevOps change edited one and not the other. Now eight mirrors (four Levels × Remote and Not
Remote) are generated with their prompts and Suite 4.42 holds every one byte-identical.

### M-2 · The second Claude pass judged every listing against a stale, hard-coded bio · **FIXED**

`worth.py` described Sina as "entry or junior level, in data, ML or AI" — written before the
field became a title and never updated, so a DevOps or Data Engineering run was still judged
as data science. Replaced by the résumé match, for all six Levels, with its own cache key.

### M-3 · A title-only check would have deleted every thesis · **FIXED (measured, not chosen)**

Job and Internship titles name a job; thesis titles name a topic ("Masterarbeit Deep Learning
auf Zeitreihendaten"). On 334 real German theses the title alone kept **0** for "Data Science"
and 1 for "Data Engineering". Thesis alone reads title OR description: **160 of 334** kept for
"Data Science", 24 of them off-subject and left for Claude's rule 6. Job and Internship stay
title-only: on 8,801 German jobs "Data Engineering" keeps 1,262, and what it drops sharing the
word "data" is Data Scientist, Data Analyst and Data Architect.

### M-4 · The résumé block brought cache marks into batched requests · **FIXED**

Adding the résumé as a cached system block put `cache_control` on the batch path too, which
Suite 4 forbids: parallel requests each write the cache instead of reading it. Caught by that
test. Batched requests (part one, part two, Thesis, Internship) send one plain string; only
the one-at-a-time path keeps the mark.

### M-5 · The résumé path was fixed at import time · **FIXED**

`resume.py` computed its folder from `storage.DATA_DIR` when imported, before the test harness
moves storage to a temporary folder — so a test saving a résumé would have replaced the one
Sina really uploaded. The path is now resolved on every call, and Suite 4.40 checks it points
inside the test folder.

### M-6 · HTML entities are not unescaped before the rules read a posting · **FIXED (O campaign)**

Measured at last, which is what it was waiting for: **26,445 entities across the five real
corpora**, on 27–43% of listings (`&amp;` 26,445, `&gt;` 5,483, `&lt;` 5,189, `&nbsp;`
4,528), from the sources that hand over plain text rather than HTML — `strip_html` already
unescapes the HTML ones. And the number that decided how to fix it: running the Work Location
rule, the seniority rule, the unpaid rule and the language rule over all 24,295 listings both
ways, **zero keyword verdicts change**. So this was never a filtering fault. It is what Sina
reads in the table and the export, and what Claude is handed: "technology &amp;amp; domain
knowledge". Unescaped in the Filter's first step, where the title is already being cleaned;
the Bank keeps the untouched original. Covered by 4.entities.

### M-6 (original entry) · HTML entities are not unescaped before the rules read a posting

`&#39;` reaches `rule_text` as-is, so phrases with an apostrophe — several French ones in the
Junior vocabulary — cannot match a posting that encodes it. Found while copying the Junior
vocabulary into the new profiles; the profiles copy Junior exactly, so all four share it.
Not fixed: it changes the Junior module, which Sina called complete.

### M-7 · "Graduates aged 18 to 28 years" is read as an experience range · **FIXED (O campaign)**

The level rule read any range of years as a demand for experience, so a VIE graduate
programme — the opposite of a senior job — was dropped for being open to "graduates aged 18
to 28 years".

Measured across all five corpora before touching it: **272 ranges matched, 208 beside an
experience word, 5 beside an age word, and not one experience range anywhere starting at 12
or more**. That shape gave two narrow guards rather than the blunt "require an experience
word", which would have let real senior postings through ("Minimum of 4-6 years in a GTM
Operations role" never says the word): an age word within 90 characters disqualifies the
range outright, in every language the app reads (`aged`, `Alter`, `leeftijd`, `età`, `ålder`),
and a lower bound of 12 or more has to be vouched for by an experience word.

Re-measured after: **6 listings out of 24,295 change verdict** — the VIE programme (two
copies in each of two corpora) and two texts about a wind farm's "20-30 year lifespan". Every
one of them an age or a lifetime, none of them a job requirement. Covered by 1.35.

### M-9 · The Excel export wrote its rows one set of columns short · **FIXED**

Found while checking what else the new fields had to reach. `JOB_HEADERS` gained "Worth it?"
and "Why" when the second Claude pass was built; the row writer never did. So every export
put the link under **Worth it?**, the description under **Why**, and left two empty columns
at the end — a file that opens perfectly and says the wrong thing. The résumé match's score
now has a column of its own in both workbooks, and Suite 5 checks each value sits under the
header that names it, so the next mismatch fails loudly.

### M-10 · A live test called a healthy source broken · **RESOLVED — not a fault**

The live run failed on `remoteok.com: returned real listings`. Its API is the hundred newest
remote jobs worldwide, not a search index: measured the same minute, "Data Scientist" matched
0 and "engineer" matched 44. The source was fine; the test asserted that a fixed term always
matches. It now proves the feed is alive with a common word before failing.

### M-8 · Lead and Staff titles pass the keyword stage for Mid and Senior · **BY DESIGN**

"DevOps Lead Engineer" survived the Mid and Senior keyword rules on the Austrian run. Junior
behaves the same — its word list has no bare "lead" either, and that row falls for Junior only
through LinkedIn's "Mid-Senior level" field. The profiles copy Junior's template; rule 4 of the
Mid and Senior prompts names lead, staff and principal roles, and Claude drops them there.

---

## N · The first run under the new design: Data Engineer, Entry, Remote, Oslo

Sina's own résumé (PDF), the title box set to `Data Engineer`, Level `Entry`, `Remote`, one
city. 77 minutes, $2.42 of Apify, **1,018 listings**: Google 537, LinkedIn 220,
workatastartup 167, Glassdoor 38, Indeed 18, the free APIs the rest. Then the Filter: 204
duplicates, 694 dropped by the title check, 58 by the Work Location rule, 27 by the country
vocabularies, 19 by the sentence rules, 16 to Claude, 13 flagged, **3 left**.

Every one of the 1,018 was read against every rule, and every rule that fired was read back.
Five faults came out of it. The verdicts themselves were right: "Rule 1 - Hybrid role
requires 3 days in-office at Oslo or Stockholm HQ", "Rule 2 - Norwegian required, not in
résumé", "Rule 4 - Wants 3–7 years professional experience", "Rule 7 - Field is Data
Engineer, not Data Scientist".

### N-1 · Glassdoor's location arrived as a raw object · **FIXED**

`{'countryId': 180, 'id': 2918317, 'name': 'Oslo', 'type': 'C'}` was stored as the location —
all 38 Glassdoor rows. It showed in the table and the Excel export, and every rule that reads
the listing's text read it too. `normalize_glassdoor` now asks for `location.name` first and
unwraps an object if one still arrives.

### N-2 · The board's own name was part of the job title · **FIXED**

A page's `<title>` usually ends with the site: **456 of the 1,018** carried one — 224 "|
Wellfound", 170 "| FINN.no", 10 "| arbeidsplassen.no", and thehub.io puts its name in front
("The Hub | Internship Data Engineer | SurplusMap"). That name went into the table, the
export, the duplicate check and Claude's Title line. `strip_site_name_from_title` removes the
site's own name from either end, matched against the address the row came from — never a
general "cut everything after the last dash", which would eat "Data Engineer - Microsoft
Fabric".

### N-3 · "Lead Data Engineer" was the wrong level for nobody · **FIXED**

Junior's word list carries "team lead" but not "lead" on its own, so every profile copied
from it kept a title that says plainly what it is. Measured: **50 distinct titles** in this
one run, "Lead Data Engineer" at NAV among them, all at Entry level. Entry, Mid and Senior now
drop "lead" and "staff" as their own words — with a tail guard, because without one "Data
Engineer, Leading Bank" was dropped for the word "Leading". Junior is untouched, as Sina asked;
rule 4 of its prompt catches these at Claude's stage.

### N-4 · A page gave the board's list of other vacancies instead of the posting · **FIXED**

aijobs.net renders its posting pages as a list of other jobs — "[SE][Full Time] USD 145K-166K
Remote job [R]", 265 such tags, and not one line of the advert. One of the two in this run was
**kept as remote work, and the word "Remote" came from somebody else's vacancy**. The existing
chrome-only check excused it for being long, which is exactly what an index page is.
`is_board_index_text` now recognises the shape; such a page is re-fetched, and if it still
reads that way its text is cleared and the row is marked as having no description — like the
four sources that never send one. Measured across 21,679 real listings from four runs: 8 hits,
every one of them aijobs.net, each carrying 264 to 271 tags where nothing else reaches eight.

### N-5 · One job on two boards was shown twice · **FIXED**

SurplusMap's internship came back from finn.no as "Internship Data Engineer" and from
thehub.io as "Internship Data Engineer | SurplusMap" — the same posting, 99.4% the same text.
The duplicate check strips the employer's name from a title, but only when the SOURCE named
the employer, and at that point neither row had: the name is read out of the posting later, by
Claude. So the two titles scored 84 against a 90 cut and both were shown. A short tail after a
pipe is now dropped from the comparison key; a long one ("Data Engineer | Build the data
foundation for the future of care") is the job itself and is kept.

### N-7 · lxml killed the process, 56 minutes into the Amsterdam run · **FIXED**

The search died with no Python error of any kind -- no traceback, no log line, exit code 5.
Windows recorded what Python could not:

```
Faulting application: python.exe
Faulting module:      etree.cp38-win_amd64.pyd      (lxml)
Exception code:       0xc0000005                    (access violation)
```

trafilatura extracts with lxml, whose C parser is not safe to drive from several threads at
once -- and `enrich_thin_descriptions` runs it in an eight-thread pool. It fell over on the
first batch of 99 pages. This is the same family as J-1, which was mitigated with the
checkpoint rather than cured; the cure is a lock held while trafilatura parses. Nothing else
slows down: extraction is a few milliseconds of CPU against a network fetch of a second or
more, and the fetches still run in parallel -- measured, 64 parses on 8 threads in 0.7s.

**Nothing was lost.** The checkpoint J-1 produced held all 2,616 rows the search had paid
$3.07 for, and the run was finished from it without spending anything more. Test 1.34 drives
48 parses through 8 threads; if the lock is ever removed it will not fail, it will take the
suite down -- which is what the fault does.

### N-8 · A vacancy that counts vacancies is a listings page, in eleven languages · **FIXED**

The companion to N-4. A real advert never says how many jobs there are; a listings page opens
with the count. The rule that caught this only read English, so "31 data scientist vacatures
in Amsterdam" and "1.234 Stellenangebote" went through as vacancies, into the table, the
duplicate check and Claude's Title line.

`_COUNTS_VACANCIES` now carries the word for a vacancy in every language the app searches —
`vacatures`, `Stellenangebote`, `Treffer`, `banen`, `offres`, `emplois`, `annunci`, `ofertas`,
`vagas`, `lediga jobb`, `stillinger`, `työpaikkaa` — and allows up to four words between the
number and it ("31 open data science vacatures"). Measured over the five real corpora,
~25,000 listings: **142 distinct listing-page titles caught, zero false positives** — every
hit read back by hand before the rule shipped. Covered by 1.33.

### N-6 · Indeed and Glassdoor return very little for a city search · **INVESTIGATED**

Both reported $0.00 and looked broken. They are not: 18 and 38 real rows came back, their
cost simply rounds to nothing, and the Indeed actor does accept `no` (Norway) — its country
list was read from the actor's own schema, and all 18 RoleHound countries are in it. Small is
what Indeed and Glassdoor are on this market: 21 and 46 rows on the earlier Austrian run too.

---

## O · The wide campaign: every Level, both work modes, 24,295 real listings

Sina asked for one large test that measures everything, after a Junior/Remote run over the
Amsterdam pool came back empty and he asked, reasonably, whether the filters were working at
all. The campaign has four parts, and the point of the shape is that each part can only be
answered by evidence the part before it cannot produce.

**A · the suites.** 1,982 assertions offline. Four failed at the start of the campaign and
all four were mine: the "three years or fewer" bullet added to the Junior prompt that morning
had not been propagated to the three generated profiles or the four Markdown mirrors. Fixed
by regenerating; the campaign then added 19 assertions for the Bank (3.bank), 26 for the
quote guard (4.quote), 10 for the age ranges (1.35), and the rest for the faults below —
**2,063 passing, 0 failing**.

**B · the rule matrix.** Every corpus we own × six Levels × both work modes: **60
configurations over 24,295 real listings**, no Claude, checked against six invariants that
have to hold whatever the corpus:

| | invariant | result |
|---|---|---|
| I1 | rows in = rows kept + every removal the Log reports | held, all 60 |
| I2 | Entry's survivors ⊆ Junior's (Junior has no lower bound) | held |
| I3 | Remote and Not Remote never keep the identical set | held |
| I4 | the same input twice gives the same output | held |
| I5 | a level word in the title decides, in both directions | held |
| I6 | no configuration raises | held |

That matrix is what answers Sina's doubt directly: the Amsterdam pool at Junior/Remote keeps
18 and at Junior/Not Remote keeps 49, of which **18 survive Claude and score 11 "worth
applying to", 7 "worth opening first"**. Nothing was broken. Entry + Remote is simply a
very narrow slice: the postings that fit his level exactly — ING's "at least 1 year", Young
Analytics' "0 – 2 years", Kramp's "entry-level candidates encouraged" — are all hybrid or
on-site, and the Remote requirement is what emptied the result.

**B2 · the two Levels the matrix cannot reach.** Thesis and Internship never go through a
profile: FilterWorker sends them to their own modules. Measured separately, and that is where
O-2 came from.

**C · Claude.** 111 DROPs across six configurations, each reason checked against the words of
the posting it was reading — in the posting's own language, after the first pass mistook
`Nederlands` for a missing `Dutch` and reported thirteen false alarms of its own. The same
six configurations were then re-run after each fix, which is the only way to tell a fix from
a hope:

| pass | what changed | DROPs | resting on nothing | listings that survived |
|---|---|---|---|---|
| 1 | — (the measurement) | 111 | **17** (15.3%) | 29 |
| 2 | the silence guard, written into every rule | 117 | 11 (9.4%) | 32 |
| 3 | `drop_evidence`, checked against the posting | 99 | 5 (5.1%) | 37 |
| 4 | the quote also has to fit the rule it is offered for | 94 | **2** (2.1%) | **42** |

Thirteen listings that had been dropped on nothing are back, and the two that remain are
quotes the auditor cannot classify rather than drops it can show to be wrong.

**D · the app itself.** The Bank's wiring (5.bank drives `handle_filter_existing` with a
captured worker and proves the Filter is handed the Bank's 3 listings rather than the 1 the
last Filter kept), the Excel export's column alignment, the wizard's résumé validation, and a
rebuilt exe carrying every module the new code needs. 295 assertions in Suite 5, all green.

### O-1 · A Not Remote search kept a job in another country · **FIXED**

`Data Analyst / Data Scientist (H/F)`, Paris, survived a Not Remote search for Amsterdam.
The Work Location rule reads the words about remote work and never the place, which is right
for Remote — remote work can be done from anywhere — and wrong for Not Remote, where being
there is the whole point. Two ways a foreign listing arrives: a multi-country board
(`arbeitnow.fr` in a Netherlands run), and the saved pool itself, which grows with every
search — the Oslo pool still carried **296 Vienna listings** from the week before.

New step `_step_place`, Not Remote only, and deliberately timid: the country is known on
87–100% of rows (measured across all five corpora), so it drops only a row that names a
single, plain country that is not one of the searched ones. Empty country, a list of
countries, and a board's "Worldwide" all survive. Measured before shipping: **4 removals
across four corpora** — Paris out of Amsterdam, and Hamburg, London and Graz out of Oslo —
and **zero** in the Germany and Austria runs, where nothing foreign had survived to that
point. Covered by 4.place.

One more thing had to be true for any of it to matter: a city search stores no country at
all. Sina's own settings for the Amsterdam run were `cities=['Amsterdam'], countries=[]`, so
the first version of this rule would have sat switched off on every search he actually runs.
The step now reads the chosen cities too, through `geo.CITY_COUNTRY`.

### O-2 · The Thesis and Internship modules reported the opposite of what they did · **FIXED**

In a Not Remote search both modules removed *remote* postings — correctly — and wrote the
reason as `cannot be done from Turin`. The rule itself reads the work mode properly; only the
sentence in the Log did not, so the one line Sina gets told him the opposite of what happened.
Both now say `remote work, which a Not Remote search excludes`. Covered by 4.why.

This came out of a count that looked alarming and was not: of 889 internship titles in the
German internship corpus the module returned 10. The reasons, once printed, were
`title does not name Data Engineer` 1,814 (Deutsche Bank's "Internship in Technology, Data &
Innovation" genuinely does not), then the work-mode rule — and in Not Remote the same pool
gives 18, which is the module tracking the mode, not missing postings.

### O-3 · Claude dropped listings for what a posting does not say · **FIXED**

The systemic one. Of 111 DROPs, **17** rested on silence rather than words:

- `Rule 3 - Unpaid volunteer position.` on Simon-Kucher's consulting internship, IFF's
  Cognitive Data Science internship and REV'IT!'s — none of which mentions money at all
- `Rule 1 - On-site in Kuala Lumpur; he is in Turin.` where the posting names a city and
  never asks anyone to sit in it
- `Rule 1 - Location Vancouver; no on-site requirement stated` — the reason says outright
  that nothing was stated, and drops anyway
- `Rule 4 - Medior level exceeds junior; 2+ years implied.`
- `Rule 4 - Experience requirement unclear; posting vague on seniority level.`

Rule 1 already carried the guard ("anything you would describe as implied ... is a KEEP"),
which is why only one on-site case slipped through; rules 2, 3 and 4 did not. Fixed in two
stages, because the first stage was not enough:

1. **The guard, stated for every rule.** It now lives in the shared **Never DROP for**
   section, so all four Levels and both work modes get it from one edit: silence about money
   is not unpaid, a posting that names no language demands none, and a reason containing
   "not stated", "unclear", "vague" or "implied" is a KEEP. Re-run over the same six
   configurations: **17 of 111 → 11 of 117**. Better, and still six listings dropped on
   things their postings never said — the same six, run after run.
2. **The quote, checked.** `drop_evidence` is now a required field in the answer schema,
   asked for *before* the verdict like `checked` and `location_basis`, and holding the
   posting's own words for whatever the DROP claims. `_read_structured_answer` looks those
   words up in the listing (letters and digits only, so punctuation and casing cannot
   reject a real quote) and a DROP that cannot show them becomes a KEEP. This is the half
   that does not depend on Claude agreeing, and it is the same mechanism already trusted for
   `employer_evidence`, where an invented company name would be matched against a government
   sponsor register.

3. **The quote has to fit the rule.** Checking that quoted words are in the posting stops an
   invented sentence, not an irrelevant one: "Rule 3 - unpaid volunteer position" survived
   pass 3 by quoting a true sentence about HVAC platforms. A quote offered for rule 3 now has
   to contain a word about not being paid, one for rule 2 a language, one for rule 4 a number
   or a seniority word — in any of the languages the app reads. Rules 1 and 5 to 8 ask only
   that the quote be real. **2 of 94.**

The direction of the failure is deliberate: a wrongly-kept listing costs Sina one line in the
review dialog, a wrongly-dropped one costs him a job he never sees.

### O-4 · The Bank: the Filter used to eat the pool it filters · **FIXED**

Not a wrong verdict — a design fault Sina found by describing the app back to me. A search
banks its listings, the Filter judges them, `save_jobs` then wrote the survivors over
`jobs.json`, and the pool was gone: trying another Level, or Not Remote, meant paying Apify
for the same search again. Everything measured in this campaign was only possible because the
Amsterdam pool had been kept by hand outside the app.

`bank.json` now holds what a search returned, keyed by URL so re-searching a city does not
bank a posting twice and the newest copy of a posting wins. The Filter reads from the Bank
and never writes to it, so any Level and either work mode can be tried as often as Sina
likes for the price of the Claude calls alone. Same forgiveness as `jobs.json` — this file is
the only copy of what a search paid for, so a damaged row is dropped and never the pool.
Covered by 3.bank (storage) and 5.bank (the wiring, which is where the fault actually was:
`handle_filter_existing` called `load_jobs`).

The Amsterdam pool was seeded into the Bank by hand once, so the app opens with 2,602
listings to filter at any Level, for nothing.

### O-6 · The same job from two boards was shown twice · **FIXED**

Found by asking, after everything above was committed, whether the app was now working
"without errors" — and measuring instead of answering. The real Amsterdam result Sina would
have opened held **8 duplicate pairs among its 48 listings**: QuantumBlack's Data Scientist on
LinkedIn and on qarera, Metyis' Data Science Analyst on both, Robeco's Junior Climate Data
Scientist on LinkedIn and quantjobs, Philips' internship on qarera and startup.jobs, Genmab's
on LinkedIn and vacaturesinfarma.

Two reasons the existing dedup cannot see them, and the second is the interesting one:

- A board appends its own tail to the title — "Data Science Analyst **at Metyis**", "Junior
  Climate Data Scientist **at Robeco | Quant Jobs**" — so the title keys differ.
- Two boards render one vacancy at very different lengths (3,802 characters against 1,929),
  so the description test never reaches its threshold. And the employer, which would settle
  it outright, **is not known yet**: dedup runs first, before anything has read the posting,
  and the Filter deliberately clears guessed company names at that point.

So the test that needs the employer runs where the employer exists — after Claude has quoted
it out of the posting. `_step_merge_twins` merges two rows when the employer matches, the
title matches once the board's tail is stripped, the countries agree, and the addresses are on
different sites. The fuller description survives, and a copy Claude flagged never beats the
twin it did not object to — with its flag removed from the review dialog, so nothing points at
a row that is gone. The same test also runs inside the original dedup, for the rows that do
arrive with a company name (6 more merges on the German corpus).

Measured over 171 rows from five real Claude results: **18 merges, every one of them the same
job on two sites**, no wrong merge. Two pairs are deliberately left alone — Capgemini's
listing calls the employer "Capgemini" on one site and "Capgemini Engineering" on the other,
and inventing a rule to bridge that would start merging real openings. Covered by 4.twins.

### O-5 · A two-year requirement was the wrong level for nobody · **FIXED**

`workatastartup.com/jobs/97349` — "Have at least 2 years experience with ETL processes" — was
dropped under Junior as `Rule 4 - Requires at least 2 years experience`, though Junior's own
rule 4 says "1–3 years is fine".

The line saying so belongs **inside rule 4**, which is the one passage each profile writes
for itself — the first attempt put it in the shared section, where "a minimum of three years
or fewer is his level" was copied verbatim into Entry, for whom two years really is a
reason to drop. Caught before it shipped, by reading the generated diff. Each Level now
states its own: Entry "no experience at all, or capped at one year", Junior "three years or
fewer", Mid "anywhere from 2 to 5", Senior "five years or more".

### O-7 · A source with no key was reported as broken · **FIXED**

Sina, reading the Health Check: `nl.jooble.org | FAILED (no API key configured, so this
source contributes no listings)` — "this is the problem we have". It was not a problem; it
was a source he had never set up, printed in red beside things that were genuinely broken,
which made a healthy run read as a broken one.

The reasoning that put it there still holds — a national board switched off for a country
being searched is worth knowing, and silence about it is worse — so the line stays. What
changes is what it says: a third verdict, `OFF`, rendered amber as "Switched off", kept out
of the failure count, out of the problems list and out of the dialog that interrupts a
search. The reason now names the country that loses the source and where a free key comes
from. Queued through the same ordered pass as every other check, so the Log still reads in
the order sources actually run. Covered by 4.12 and 5.off.

Sina then asked whether he should go and find a Jooble key. Measured first, because the
answer was not obvious: across three corpora the national boards are the best sources per
listing brought — arbeitsagentur.de 741 brought / 40 survived (5.4%), werk.nl 121/6 (5.0%),
against LinkedIn's 1,512/12 (0.8%) and Glassdoor's 1,578/12 (0.8%) — and both of those work
with no key at all. Jooble is an aggregator of the same boards, so most of what it adds is
removed as duplicates, and its free key allows 500 requests for its whole lifetime. He got
one anyway; it is stored and verified (HTTP 200, 100 matches for Data Scientist in
Amsterdam), and it cost 1 of those 500.

### O-8 · The Health Check could not say what anything costs · **FIXED**

Sina asked for the two numbers the check was missing: how much Apify credit and how much
Claude credit are left, and what a normal search costs.

Apify answers exactly — the account reports its usage and its cap — so that line is a fact:
`$10.00 of $10.00 left this month — about 3 more city searches at $2.40–$3.10 each`, the
range being the two real searches this campaign paid for (Oslo $2.42 for 1,018 listings,
Amsterdam $3.07 for 2,616).

Anthropic does not: an ordinary API key cannot ask for a balance, which lives behind the
organisation Admin API and a different kind of key. Rather than guess or stay silent, the
app now counts what it spends itself — every response reports its own tokens, and
`claude_screen/spend.py` prices them (batch at half, cache writes at 1.25×, cache reads at
0.1×) into `claude_spend.json`. The line reports spending and the rate behind it: `$0.02
spent by this app in total; the last Filter read 3 listing(s) for $0.02 (about $0.0051 each,
so a run that sends 50 to Claude costs around $0.25)`.

Wiring it up caught a fault of its own: `spend.record` was called in `screen.py` before the
import existed, and the NameError landed inside the `except` that turns any screening error
into a KEEP. Three test listings came back KEEP with no reason; with the import, the same
three came back DROP with quoted reasons. A silent import error was turning every verdict
into "keep" — found because the ledger reported nothing and the number was checked rather
than assumed. Covered by 4.spend and 5.budget.

### O-9 · The search asked for cities Sina never chose · **FIXED (his rule, not a fault)**

LinkedIn caps one query at 1,000 jobs, so for every selected country the app also asked for
that country's strongest city — Berlin for Germany, Milan for Italy. It was measured before
being built: a Berlin-only run returned 120 jobs of which **48 were not in the 1,000** the
Germany-wide run had already paid for, and on the real German corpus LinkedIn returned
exactly 2,000 rows, which is two queries each hitting the cap.

Sina ended it anyway, and his reason is the better one: *"من میخوام فقط جا هایی که انتخاب
کردم رو ببینم ولا غیر / به هیچ عنوان نباید شهر های دیگه ای که خودت به نظرت خوب اومده رو
اضافه کنی"*. A tool that quietly searches places you did not ask for is not thorough, it is
untrustworthy — and the cost is real too, at roughly $4 of LinkedIn per country per pass.

Removed from the plan, along with the helper and the budget constant that served it. The
city table stays, because it answers a different question: which country a city belongs to,
for any city Sina types (`CITY_COUNTRY` only knows the wizard's own list, and a row whose
country cannot be resolved loses its country field and its local-language pass). Verified on
his own example — Berlin + Munich + Amsterdam produces 9 actor calls and 11 Google query
lines, and the only place names anywhere in them are Berlin, Munich and Amsterdam. Covered
by 4.1, 4.x and 7.11, including a test that fails if any helper capable of adding a city
comes back.

### O-10 · The money path was one 465-line function · **FIXED**

Sina: *"به خرد ترین و ماژول های کوچک تبدیلش کن که به راحتی بشه مدریت اش کرد … ازت میخوام این
بخش یکی از امن ترین بخش های برنامه بشه و دیگه مثل بالا نگی اینجا یکی از شکننده ترین بخش های
برنامه هستش"*. `run_search` was 465 lines in a 1,652-line file that held three unrelated
jobs at once, and every question about it could only be asked by running a whole search.

**Tests first**, because refactoring the least-tested and most expensive path in the app is
exactly where a refactor does damage. Suite 7 is 105 assertions, entirely offline, around
the one function that spends real credit — see the commit for what it holds. Only then was
a line of it moved, and it stayed green through every step.

**Then the split**, one piece at a time:

| | before | after |
|---|---|---|
| `runner.py` | 1,652 lines | 1,145 |
| `queries.py` (new) | — | 689 lines, pure: words in, strings out, no network or clock |
| `run_search` | 465 lines | 203, of which 41 are its docstring |
| longest remaining | `run_search` 465 | `_run_platform_passes` 89 |

The phases are now named things that can be read, tested and fixed one at a time:
`_check_tokens`, `_resolve_passes`, `_start_credit_poller`, `_run_platform_passes`,
`_run_google_passes`, `_drop_stale`, `_open_listing_pages`, `_fill_in_and_prune`,
`_report_late_problems`, `_finish_run_search_df`. The three-way `if platform ==` inside
`_process_plan_item` became `_linkedin_request` / `_indeed_request` / `_glassdoor_request`
plus a table, so a fourth actor is a function and a line rather than another branch.

**And the redundancy Sina asked about, found by measuring rather than guessing.** The split
left runner re-exporting 27 names from queries; 18 of them nobody read. Tests were reading
the vocabulary through `runner` instead of from where it lives, and `app.pipeline`'s public
API took `KEYWORDS` the same way. All of it now points at the source, and `pyflakes` across
the whole app reports nothing at all.

One real fault came out of the clean-up: `claude_screen/company.py` imported the spend
ledger and never called it, so a run with sponsor look-ups in it — the dearest Claude call
of the three, because it searches the web — was reported at less than it cost.

### O-11 · Five more functions nobody could hold in their head · **FIXED**

Sina asked for the same treatment across the rest of the app, "طوری باشه که اگر مشکلی پیش
اومد سریع بفهمیم مشکل چیه". Measured first, so the list is the app's and not a taste: every
function over 60 lines, with its branch count and how many separate blocks it holds.

| | before | after |
|---|---|---|
| `run_health_check` | 157 lines, **34 branches** — the most in the app | 47, plus `_check_the_app_itself`, `_check_apify_and_apis`, `_check_job_sites`, `_check_saved_patterns` |
| `expand_listing_pages` | 156, 26 branches | 34, plus `_collect_links_inside` and `_build_rows_from_links` |
| `_apply_sponsor_list_matches_to_jobs` | 140, 25 branches | 89, plus `_match_against_register`, `_companies_worth_looking_up`, `_resolve_legal_names`, `_match_by_legal_name`, and a `_LegalNameBudget` for the five counters the loop was mutating |
| `enrich_thin_descriptions` | 150, 20 branches | 104, with `_fetch_round` finally out of the closure |
| `learn_missing_job_patterns` | 114, 20 branches | 70, plus `_domains_worth_learning` and `_learn_one_domain` |
| `_render` (Jobs table) | 115 lines, **no docstring at all** | 14, plus seven `_render_*_cell` methods, each carrying the bug note that belongs to it |

Two of the six had already marked their own seams in comments — `run_health_check` with five
section headers, `expand_listing_pages` with two — which is the clearest possible sign that
one function was holding several jobs.

**Three faults came out of doing it:**

1. **Switched-off sources had gone silent in the Health Check.** Turning a missing key from
   FAILED into an OFF line (O-7) made them invisible there, because the Health Check reports
   what `_preflight_check_api_sources` *returns* and passes it no progress callback. Sina
   asked to be told a source is off — just not in red — so the off list now travels with the
   problems, and the Health Check prints it in amber.
2. `_fetch_round` in enrich.py was nested purely to reach two `nonlocal` counters, so it
   could never be called or tested on its own. `_EnrichTally` holds them; the round moved out.
3. A late import in learn.py was left unused by the move, and another was needed in the
   function that now does the work.

**Left alone, deliberately.** `_register_api_preflight_checks` (186 lines) and
`_run_direct_api_searches` (162) are catalogues: one independent block per source, read top
to bottom, and splitting them would add a layer without removing a decision.
`reapply_filters` (170) already does nothing but call `_step_*` in order. The big data files
— `country_rules.py` at 1,174 lines, the `words.py` vocabularies — are tables, not logic.

### O-12 · A Not Remote search asked LinkedIn for remote work only · **FIXED**

Found by Sina asking a plain question during the real Germany run — do Remote / Not Remote
and the Level change what is *searched*, or only what is filtered? Answering it honestly
meant reading the request each platform is actually sent, and one of them was wrong:

```
linkedin → urls: 'https://www.linkedin.com/jobs/search/?...&f_WT=2&...'
```

`f_WT=2` is LinkedIn's own **remote-only** filter, and it was on every search of every
country except Italy, whatever work mode Sina had selected. So a Not Remote run asked the
largest single source in the app for nothing but remote work — the exact opposite of the
selection, and silently: the listings that came back looked perfectly normal.

The history explains it without excusing it. The app was remote-only when that URL was
written; Not Remote arrived later and was built into the Filter, and nobody went back to the
search. `search_work_mode` reached `reapply_filters` and stopped there — it was not even a
parameter of `run_search`.

Now it is, and it travels the whole way: `SearchWorker` → `run_search` → `_process_plan_item`
→ `_actor_request` → `_linkedin_request`, which drops the remote filter for a Not Remote run
exactly as it already did for Italy. Indeed and Glassdoor take the flag and ignore it — they
do not filter by working arrangement at their end — and there is a test for that too, so
nobody later "fixes" them into silently narrowing a search. Covered by 7.16, including one
that drives a whole search and inspects the URL LinkedIn is really handed.

**The answer to the question that found it**, for the record:

| | changes the search? | where it is applied |
|---|---|---|
| Level (Entry/Junior/Mid/Senior) | **yes**, the second of the two queries: `"Junior Data Scientist" OR …` against `"Senior Data Scientist" OR …`. The first query is level-free, so every level is collected either way | `queries.keywords_for` |
| Remote / Not Remote | only LinkedIn, and only since this fix | `_linkedin_request`, then the Filter |

### O-13 · The deep crawl worked for 83 minutes without saying a word · **FIXED**

The real Germany run opened 781 listing pages. Between "Reading listing pages" and the next
line, the Log showed nothing for **83 minutes** — no count, no batch, no page. The stage was
working perfectly the whole time; there was simply no way to know that from the outside.

That is not a cosmetic complaint. A stage that can run over an hour in silence is
indistinguishable from a hang, and the only other sign of life — Apify credit ticking down —
stalls too while a batch waits for its run to finish. Sina's reasonable response to a
one-hour silence is to kill the app, which throws away everything already paid for.

`crawl_urls_in_batches` now says how much work there is before it starts, and reports after
every batch:

```
781 page(s) to open, in 8 batch(es) of up to 100. Each batch is one Apify run;
the count below moves as they finish.
Batch 3 of 8 done — 287 page(s) read so far, $1.14 spent on this stage.
```

The spend is in the line on purpose: it is the number that decides whether to wait or stop.

### O-14 · 38 German listings were not in Germany · **FIXED**

Found by auditing the Germany run's own output rather than its code. Google returns no
location field, so a Google result is stamped with the country whose query produced it —
right for 5,495 of 5,662 listings, and wrong for the ones a German query surfaced from
somewhere else entirely: a Casablanca job, a Lisbon job, a New York job, all filed under
Germany.

`country_from_listing_location` reads the place the listing names itself, from its location
field or from the bullet segments of its title, and returns another country **only when it is
certain**: the place must be one the app already knows, the text must not also name the
searched country, the place must not be "Remote" or "Europe", and exactly one country must be
named. Anything less returns `None` and the stamp stands, because the country picks the
language vocabulary for later rules — a wrong label does more damage than a vague one.

**The first version of this was wrong, and reading the output caught it.** It looked at only
the last bullet segment, so "Software Architect at openigloo • Berlin • Hyderabad" became
India and a job naming both New York and a Swiss city became Switzerland. Every segment is
read now, and two countries means no answer. Verified by printing all 132 relabels across
8,133 rows of four real corpora and reading each one; no listing is removed by this rule.
Covered by 7.18–7.20.

### O-15 · A removal left no trace on the listing · **FIXED**

Sina asked for it in one sentence: keep the reason a listing was removed on the end of the
listing, between markers, so it can be read rather than taken on trust.

It was worth asking for. `drop_evidence` — the phrase Claude must quote from the posting
before it is allowed to drop anything — appeared in exactly **one line of the whole app**, the
line that validated it, and was then discarded. Auditing the real Germany run therefore
needed a throwaway script, and two of ninety-four drops could not be explained at all.

Now `app/pipeline/drop_note.py` writes it where he asked:

```
... the posting, exactly as the board wrote it ...

$$ WHY THIS WAS REMOVED
Rule 2 - German fluency required, the owner has only basic German
Quoted from this posting: "Gute Deutsch- und Englischkenntnisse."
$$
```

`$$`, not the `&` he also offered: `&` is html-unescaped in the normalisation step, which
would eat the marker, and it is common in real postings ("R&D", "Risk & Compliance").

**The note lives in `description`, which is also what every rule and Claude read** — that is
the whole risk, and the containment is one line at the top of `reapply_filters`:
`clear_drop_note(job)`, before any step sees the listing. Left in, "Rule 2 - Requires German
C1" would be read on the next run as the *posting* demanding German. The note is written back
only where a removal is decided, from the stored verdict, so a cached drop reads like a fresh
one and a row Sina keeps by hand loses its note instead of keeping a stale claim.

**The first version had a real bug, and only measurement found it.** `set_drop_note` did
`body.rstrip()` — tidy, and wrong. `description` is hashed into the screening cache key, so a
posting that came back two newlines shorter than it went in missed the cache. Measured on
fourteen real German listings, three ended in their own blank lines (`"...Apply Now!\n\n"`)
and three of fourteen were therefore re-screened and re-billed: the exact failure the module
exists to prevent, reintroduced by a tidy-up. No rstrip now, a fixed `\n\n` separator matched
by the same string, and the round trip is exact to the character.

Proved on real listings and the real ledger, not argued:

| | pass 1 (nothing cached) | pass 2 (the same listings, notes included) |
|---|---|---|
| cost | $0.0252, 5 API calls | **$0.0000, 0 API calls** |
| cache | 0 of 14 | **14 of 14** |
| flagged | 6 | 6, the same six |
| notes written | 6 | 6, none doubled |

Covered by section 4.note, including the seven endings a posting can have.

### O-16 · The language filter caught 13 of 1,778 · **FIXED**

Found by Sina, from the far end, and it is the largest fault of the whole campaign.

He read the two REPLY listings the Germany run had shown him, saw
`Kommunikationsstärke in Deutsch und Englisch` in one of them, and asked the obvious
question: *"مگه یک فیلتر نداشتیم که اگر زبان دیگه ای غیر از انگلیسی خواست باید حذف بشه؟"*

There is one. It was catching almost nothing:

```
1,778 German listings state a German requirement, in German
        caught :    13
        missed : 1,765        (99%)
```

**The cause is a change that was never finished.** `requires_language_besides_english` was
written when every listing was translated to English before the keyword stage, so it only
ever needed English words. Translation was then removed to stop paying DeepL, and every other
rule was given multilingual vocabulary — this one was not. Its own docstring still promised
the text would arrive in English, which is how it stayed invisible: the code read exactly as
intended, against an assumption that had quietly stopped being true.

Two concrete gaps, both fatal in German:

```
looked for  english    →  the posting writes  Englisch     (not even a substring)
looked for  deutsch\b  →  the posting writes  Deutschkenntnisse  (compounds have no boundary)
```

Three shapes are read now, because a posting states the demand in three ways — the pair
(`Deutsch und Englisch`), the level (`Sehr gute Deutschkenntnisse`, which names no English at
all and so was invisible to the old pattern entirely), and the numeric (`Niveau C1`) — in
German, Dutch, French, Spanish, Portuguese, Danish, Norwegian, Swedish, Finnish and Polish.

| | before | after |
|---|---|---|
| German requirement caught | 13 | **1,704** of 1,778 |
| Germany, of 5,442 | — | 2,432 removed (45%) |
| Netherlands, of 2,377 | — | 479 removed (20%) |

**Three faults were made and caught while building it**, two by reading a random thirty of
the 2,934 listings the new rule removes, one by a probe:

- `Englisch und idealerweise Deutsch` — *ideally*. The softener sits **inside** the matched
  phrase, where the existing "is a plus" check, which only reads the clause *after* a match,
  could never see it. `_LANGUAGE_IDEALLY` reads the span itself.
- `proficiency in Dutch, or the willingness to learn` — an invitation, not a wall.
- **Italian was added to the vocabulary, and must not be.** It is deliberately absent: the
  owner has only basic Italian and lives in Italy, so treating it as a language he lacks deletes the listings
  closest to him. A four-line probe caught a regression that would have emptied Italy.

And one existing test earned its place: `Professional working proficiency in English or
Russian` must be kept, because *or* means English is enough. The pair pattern has known that
since "or" was removed from its conjunctions; the new levelled pattern had to be told
separately, and the test said so before anything shipped.

Covered by section 1.language — 16 walls, 11 non-walls, 4 Italian probes and the
`Deutschland`/`deutsch` separation.

### O-17 · A board's own editorial reached the "apply" list · **FIXED**

Found by Sina reading the nine listings Claude had marked **apply** on the Germany run. Three
of them were not vacancies at all:

```
How to become a Data Scientist in Germany     kellerwest.com/career-advice/…
Data Scientist (m/f/d): Salary, tasks & jobs  hays.de/en/job-profiles/data-scientist
The Helmholtz Information & Data Science …    helmholtz-hida.de/en/discover-hida/…
```

A careers article, a reference page for the role, and an organisation describing itself.

**Nothing looked for them, and the reason is structural.** `pages.py` knows two kinds of
non-vacancy: a page OF vacancies (`_LISTING_URL`, `_COUNTS_VACANCIES`) and a curated article
listing COMPANIES (`_COLLECTION_URL`). These are a third kind — one page, one topic, no
vacancies anywhere on it — so neither pattern has anything to fire on, and their addresses
are title-shaped, so `_SINGLE_POSTING_URL` reads them as one posting. Claude kept them
honestly too: they are about data science, they list the skills, and rule 5 asked about a
page "listing many jobs", which none of them is.

`is_editorial_page` reads the address first and the title second, and runs in the Filter with
the cheap rules — in the Filter rather than only in `run_search`, because the Bank already
holds thousands of rows collected before this existed. 33 of the Bank's 8,133, every one read
by eye: German wage tax, work permits, co-working spaces, a driving licence, a B1 exam diary,
"Be or Become a 'Marketing and Sales' employee".

**The first draft took four real postings, and they were the best kind in the corpus** — an
employer's own site, no agency in between — because German employers file openings under
*Über uns / Karriere*:

```
wwf.de/ueber-uns/stellenangebote/stellenangebot/stelle/data-integration-bi-specialist
s-kreditpartner.de/ueber-uns/karriere/stellenangebote/werkstudent-data-science-…
lzpd.polizei.nrw/artikel/ml-data-scientist-wmd
```

So `/about-us/`, `/ueber-uns/`, `/artikel/`, `/news/` and `/presse/` are deliberately absent,
and `_VACANCY_IN_URL` overrules everything: an address naming a vacancy **is** one, whatever
section holds it. The job word has to be a whole path segment — a looser `/jobs?[/-]` read
Hays' `/job-profiles/` as the word "job" and rescued the very page that started this.

**And the fix reopened O-5's fault, which is why that test exists.** Rule 5 lives in ten
places — Junior remote and not-remote, Entry, Mid and Senior twice each, and the Internship
module under its own number and wording. Changing one made the Levels disagree, and the guard
written after O-5 caught it immediately:

```
FAIL  remote: the Levels differ only in the level paragraph and rule 4
FAIL  Job-Filter-Claude-Apify.md is the junior remote prompt, byte for byte
```

All ten were then rewritten from one source string by script rather than by hand, and the
eight `.md` mirrors regenerated from the prompt itself, so the two cannot drift.

On the Germany survivors: 37 → 17, the three articles among the 20 removed.
Covered by section 1.editorial — 7 articles, 6 real vacancies, and the `/job-profiles/` case.

### O-18 · A dead source reported itself as a quiet one · **FIXED**

Found by testing something else. The live suite, run after the hybrid fix, said:

```
EURES: returned real listings -- 0 rows
```

Probed directly it answered the same three times in **1.3 seconds**, against **37 seconds and
990 rows the same morning**. Fast and empty is not a slow day.

The real answer was an HTTP error, and europa.eu hands a failing caller to
sorry.ec.europa.eu — whose page, in every EU language, reads *"The server is temporarily
unavailable. Please try again later."* Within the hour the 403 became a **500**, which settles
what it is: **their server is down, not blocking us.** (The first write-up of this called it a
you-are-blocked page. Sina sent a screenshot of the actual page, and it says otherwise.)

`_paginate_rows` swallowed it:

```python
except Exception:
    break          # "one bad page keeps what the earlier ones returned"
```

Keeping earlier pages when a later one fails is right and stays. Doing the same for page
**one** is not: nothing has been collected yet, so there is nothing to protect, and the caller
gets an empty list **indistinguishable from a search that genuinely matched nothing**.

**This is O-7 in its worst direction.** O-7 was a working source reported as broken, which
trains you to ignore red lines. This is a broken source reported as *quiet*, which gives you
nothing to ignore at all — and EURES is one of the two sources that supply most of a German
search. It could have been down for weeks without a single line saying so.

Headers do not help: a browser User-Agent, Accept and Origin all get the same answer. The fix
does not try to get past it. It makes it visible.

Covered by section 2.first-page — six checks, including the two that matter in opposite
directions: a failure on page two keeps page one, and an empty first page is still an empty
result rather than an error.

### O-18 · A dead source reported itself as a quiet one · **FIXED**

Found by testing something else. The live suite, run after the hybrid fix, said:



Probed directly it answered the same three times in **1.3 seconds**, against **37 seconds and
990 rows the same morning**. Fast and empty is not a slow day.

The real answer was an HTTP error, and  hands a failing caller to
 — whose page, in every EU language, reads *"The server is temporarily
unavailable. Please try again later."* Within the hour the 403 became a **500**, which settles
what it is: **their server is down, not blocking us.** (The first write-up of this called it a
you-are-blocked page. Sina sent a screenshot of the actual page, and it says otherwise.)

 swallowed it:



Keeping earlier pages when a later one fails is right and stays. Doing the same for page
**one** is not: nothing has been collected yet, so there is nothing to protect, and the caller
gets an empty list **indistinguishable from a search that genuinely matched nothing**.

**This is O-7 in its worst direction.** O-7 was a working source reported as broken, which
trains you to ignore red lines. This is a broken source reported as *quiet*, which gives you
nothing to ignore at all — and EURES is one of the two sources that supply most of a German
search. It could have been down for weeks without a single line saying so.

Headers do not help: a browser User-Agent,  and  all get the same answer. The
fix does not try to get past it. It makes it visible.

Covered by section 2.first-page — six checks, including the two that matter in opposite
directions: a failure on page two keeps page one, and an empty first page is still an empty
result rather than an error.

### What the O campaign did NOT settle

Sina asked, at the end of it, whether everything now works without errors. It did not. He was
then shown the list below and **decided, item by item, that he can live with all of it**. They
are recorded as his decisions, not as open faults, and are not to be reopened as bugs:

- **2 of 94 Claude DROPs cannot be tied to the posting** — *"این هم اشکالی نداره اکیه"*. The
  quote guard catches an invented sentence and an irrelevant one; what it cannot catch is a
  real, on-topic quote that does not actually prove the claim, and both remaining cases are in
  that gap. O-15 does not close it but changes what the next one costs to find: the quote is on
  the listing now, so reading a removal no longer takes a script.
- **Capgemini's two listings still show twice** (O-6) — *"این مهم نیست اکیه"*. One site names
  the employer "Capgemini", the other "Capgemini Engineering". The rule that would bridge them
  would also merge "Siemens" with "Siemens Healthineers", and losing a real opening costs more
  than showing a duplicate row.

And one item that was on this list and **should never have been**, withdrawn after Sina
questioned it:

- ~~The Not Remote country rule only knows the cities in `geo.CITY_COUNTRY`.~~ He asked the
  obvious question — he can only tick boxes the app offers, so how would an unknown city ever
  be chosen? It cannot. `geo.CITIES` (what the wizard builds checkboxes from) and
  `geo.CITY_COUNTRY` (what the rule reads) are the same seven cities: Amsterdam, Berlin,
  Vienna, Oslo, Copenhagen, Milan, Turin. The caveat was about someone later adding a city to
  one list and forgetting the other — a note for whoever does that, never something that could
  affect a search today, and listing it as a live fault was wrong.

Three items that were open at the end of O are now closed, and the record should say so:

- ~~Suite 6 (live sources) has not been run.~~ **Run, 70/70 green**, as part of the full
  2,309-assertion pass after O-14.
- ~~No fresh Apify search has been run since the changes.~~ **The whole-of-Germany run is
  that search**: 5,662 listings, 156.3 minutes, $6.17, no crash — and it is what found O-12,
  O-13 and O-14.
- ~~The rebuilt exe has not been launched.~~ Sina opened it and used it; the Health Check
  work (O-7, O-8) came out of that session. The exe is rebuilt again after O-12/13/14.

## Settled — do not reopen

### S-1 · One listing per Claude request. Never three.

Sina's decision, and the evidence is his. Grouping listings into one request was measured on
the Job module's 93-listing corpus, same prompt, every size in one batch so nothing else
could differ:

```
one at a time   3 kept      the reference
three           6 kept      96.7% agreement
ten             9 kept      93.4% agreement
```

Every single disagreement at the larger sizes was a listing wrongly **KEPT**. Crowding a
request does not make Claude reason worse about the advert in front of it so much as make it
less willing to say no.

It also makes a verdict depend on which adverts happen to travel with it: a QuantumBlack
internship scored 85% in one run and was dropped in the next, and the only thing that had
changed was its neighbours.

A later measurement appeared to show the two agreeing after the rule-1 prompt fix — 0
disagreements over 12 listings. That measurement proves nothing: all 12 were DROPs, and the
disagreement was only ever in the KEEPs. It was cited once as a reason to reconsider
grouping; it is not one.

Saving roughly $7 across ten countries is not worth a listing Sina never sees.

---

## Investigated and not faults

### R-1 · 17 listings disappeared after index-page expansion · **RESOLVED**

Of the 77 that stopped reaching Claude: 57 index pages correctly dropped, 13 the same job at
a better address, 3 correctly dropped once their real text was read (B-1), 1 an index page,
1 a title truncated past the fuzzy threshold, 1 a posting that no longer exists, and 1 which
turned out to be B-2.

The 13 are an improvement. De-duplication now sees the employer's own posting beside the
republished one and keeps the better copy:

```
at.linkedin.com/jobs/view/lead-solution-architect…  ->  karriere.at/jobs/7858703
europa.eu/eures/portal/jv-se/jv-details/MTczMTI2…  ->  karriere.at/jobs/7862143
```

Austria: 557 listings reached Claude before, 663 after.

### R-2 · Jooble has no API key · **BY DESIGN**

Reported by the pre-flight check before any credit was spent. Jooble's free tier is capped
at 500 calls for the life of the account, which is why it is not configured.

### R-3 · DeepL has no API key · **BY DESIGN**

Also reported up front. Worth remembering while reading German results: their translations
came from Google Translate, the weaker of the two routes — measured at 12 of 122 listings
translated on one real run.

### R-4 · Indeed and Glassdoor collapsed after the move to DevOps · **NOT A FAULT**

Austria, before and after: Indeed 316 → 21, Glassdoor 875 → 46. Read as a broken query at
first. Every row they returned was then read: DevOps Engineer, Junior Data Platform Engineer,
Observability & AIOps Engineer, AI/ML Ops Engineer, Platform Engineering Lead — essentially
all on target. A broken query returns nothing or rubbish, not that. The old query asked for
the whole of data science and got 875 mostly-irrelevant rows; the new one asks for a narrow
field and gets 46 relevant ones. LinkedIn (1,356) and Google (1,322) held steady, so the
market is there.

### R-5 · A vacancy with no title reaches Claude · **BY DESIGN**

`blum-careers.com/…/business-analytics-consultant-2` arrived from Google with no title; its
text opens with it. Kept, because a missing title is never grounds to delete — the rule the
date and field filters both follow — and Claude judges it on the text. Deliberately not
repaired by lifting a title out of the body: guessing from body text is what made the first
date filter wrong.

---

## Country log

| # | Country | Run | Result |
|---|---|---|---|
| 1 | Germany | `germany_log.txt` | in progress |
| 2 | Austria | DevOps/MLOps, Job only | 3,450 listings → 319 to Claude → **17 kept**, screened before L-4 and L-6 were fixed; one of the 17 was the untitled mirror. After the fixes 318 reach Claude. 2 junior DevOps roles, 1 fully remote. Exposed L-1 to L-8. |
| 3 | Norway | Data Engineer, Entry, Remote, Oslo | 1,018 listings, $2.42, 77 minutes → 16 to Claude → **0 real survivors** (the 2 that remained were dead aijobs.net pages). Exposed N-1 to N-5. |
| 4 | Netherlands | Data Scientist, Amsterdam | 2,616 listings, $3.07 — the pool the whole O campaign was measured on. Entry/Remote **0**, Junior/Remote **0**, Junior/Not Remote **18 kept, 11 of them "worth applying to"**. Exposed N-7, N-8 and O-1 to O-5. |
| 5 | — | | |
| 6 | — | | |
| 7 | — | | |
| 8 | — | | |
| 9 | — | | |
| 10 | — | | |
