"""The Claude prompts for an Any search -- derived from the Not Remote ones, never typed again.

Sina: the Search window and the Filter window offer Remote and Any. Any keeps every listing
whatever it says about where the work is done: remote, hybrid, on-site, or silent. So the
one thing that differs from the Not Remote prompts is the question of where the work is
done -- the paragraph "what he is looking for" and rule 1 -- and nothing else may differ.

A sixth, seventh and eighth hand-written copy of six long prompts would be the "one rule in
several places" this project's README warns about, so the Any text is MADE from the Not
Remote one by replacing exactly those two passages. It refuses (raises) if either passage is
not found exactly once, so editing a Not Remote prompt until it no longer fits fails the
tests and the import, loudly, instead of silently sending a half-changed prompt.
"""
import re

_RULE_1_ANY = """1. **Where the work is done is never a reason to drop.** Sina has asked for roles done
   remotely, hybrid or on site, in any country. Say in `location_basis` what the posting
   says about where the work happens, or that it says nothing, and make the verdict
   agree with it: this rule never drops a listing.
"""

_RULE_2_INTERNSHIP_ANY = """2. **Working-student roles are not a reason to drop.** "Werkstudent", "working student",
   "student worker", "studentische Hilfskraft", "studiejob", "studentmedarbetare",
   "student assistant", "Studentenjob", "praktikant naast je studie" — kept as its own rule so
   the numbering is the same in every search. Whether such a role is done remotely, on site,
   hybrid, or the posting is silent about it, it is a KEEP.
"""

_LOOKING_FOR = {
    'job': ("**A job that is not remote**", "**A job done anywhere** — remote, hybrid or on-site, for any\n"
            "company in any country. That is the point of this search: Sina has asked for roles of\n"
            "every kind of workplace.\n"),
    'thesis': ("A **master's thesis in the work named on the Field line of the posting, that is not written",
               "A **master's thesis in the work named on the Field line of the posting**, written\n"
               "remotely, hybrid or on site, at a company or an institute in any country. That is the\n"
               "point of this search: Sina has asked for theses wherever they are written.\n"),
    'internship': ("A **paid internship in the work named on the Field line of the posting, that is not",
                   "A **paid internship in the work named on the Field line of the posting**, done\n"
                   "remotely, hybrid or on site, for a company in any country. That is the point of\n"
                   "this search: Sina has asked for internships wherever they are done.\n"),
}


def any_workplace_prompt(not_remote_prompt: str, kind: str) -> str:
    """`not_remote_prompt` with rule 1 and the "looking for" paragraph made indifferent to where
    the work is done. `kind` is 'job', 'thesis' or 'internship'."""
    start_marker, paragraph = _LOOKING_FOR[kind]
    text = not_remote_prompt
    if text.count(start_marker) != 1:
        raise ValueError('Any prompt: the "looking for" paragraph was found %d times'
                         % text.count(start_marker))
    begin = text.index(start_marker)
    end = text.index('\n\n', begin) + 1
    text = text[:begin] + paragraph + text[end:]
    rule_1 = list(re.finditer(r'(?m)^1\. \*\*', text))
    rule_2 = list(re.finditer(r'(?m)^2\. \*\*', text))
    if len(rule_1) != 1 or len(rule_2) != 1 or rule_2[0].start() < rule_1[0].start():
        raise ValueError('Any prompt: rule 1 / rule 2 not found exactly once each')
    text = text[:rule_1[0].start()] + _RULE_1_ANY + text[rule_2[0].start():]
    if kind != 'internship':
        return text
    # The internship prompt's rule 2 is rule 1a again, for working-student roles -- a drop for
    # being remote -- and is turned the same way.
    rule_2 = list(re.finditer(r'(?m)^2\. \*\*', text))
    rule_3 = list(re.finditer(r'(?m)^3\. \*\*', text))
    if len(rule_2) != 1 or len(rule_3) != 1 or 'working-student' not in text[
            rule_2[0].start():rule_3[0].start()]:
        raise ValueError('Any prompt: the working-student rule was not found as rule 2')
    return text[:rule_2[0].start()] + _RULE_2_INTERNSHIP_ANY + text[rule_3[0].start():]
