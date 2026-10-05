# -*- coding: utf-8 -*-
"""The note saying why a listing was removed, kept on the end of the listing itself.

Sina's request, and the reason for it: a removal used to leave no trace on the listing. The
quote Claude had to produce before it could drop anything was checked and then thrown away --
`drop_evidence` appeared in exactly one line of the whole app, the line that validated it --
so afterwards nobody could read why a job had gone. Auditing the real Germany run meant
writing a throwaway script for it, and two of ninety-four drops could not be explained at all.

So the reason now rides on the listing, at the very end of its text, between two `$$`
markers:

    ... the posting, exactly as the board wrote it ...

    $$ WHY THIS WAS REMOVED
    Rule 2 - Requires German C1; his résumé says A2.
    Quoted from this posting: "sehr gute Deutschkenntnisse in Wort und Schrift"
    $$

`$$` rather than the `&` Sina also suggested, for two reasons that are not cosmetic: `&`
is html-unescaped in the normalisation step, which would eat the marker, and it is common in
real postings ("R&D", "Risk & Compliance"). `$$` doubled is rare even in a posting that
quotes a salary.

**A note is display text, never input.** It is stripped everywhere the description is read as
evidence, and that is the whole risk this module exists to contain: left in, the note would be
sent to Claude next run as if the posting itself said it, and would change the screening cache
key so every listing was re-screened and re-billed. The strip sites are
`_claude_screen_prompt` (which the cache key hashes, so both are covered by the one call),
`worth.py`'s résumé-match prompt, `_evidence_is_real`, and the duplicate check's body
comparison.
"""
import re

# The marker, written once. Both ends are the same, so a note is easy to spot by eye.
MARKER = '$$'

_HEADING = 'WHY THIS WAS REMOVED'

# Exactly one blank line between the posting and the note, written and matched as the same
# fixed string so the note can be taken off again without touching anything else.
_SEPARATOR = '\n\n'

# Anchored to the end, non-greedy, and consuming ONLY the separator this module wrote --
# `(?:\n\n)?` rather than `\s*`, and no rstrip in set_drop_note.
#
# The first version had both, and measurement caught what that cost: of fourteen real German
# listings, three ended in their own blank lines ("...Apply Now!\n\n"), and rstrip ate them.
# The posting that came back was two characters shorter than the one that went in, so its
# screening cache key changed, so a flagged listing was re-screened and re-billed on every
# later run -- the exact failure this module exists to prevent, reintroduced by a tidy-up.
# The round trip has to be exact to the character, and there is a test that says so.
_NOTE = re.compile(r'(?:\n\n)?\$\$ %s\b.*?\n\$\$\s*\Z' % _HEADING, re.S | re.I)


def listing_text_without_note(text) -> str:
    """The posting as the board wrote it, with any note of ours taken back off.

    Safe on text that has no note, on None, and on text that has been through the note
    twice -- which cannot happen, but costs nothing to survive.
    """
    stripped = str(text or '')
    while True:
        shorter = _NOTE.sub('', stripped)
        if shorter == stripped:
            return stripped
        stripped = shorter


def drop_note_of(job: dict) -> str:
    """The note currently on this listing, or '' when it carries none."""
    found = _NOTE.search(str(job.get('description') or ''))
    return found.group(0).strip() if found else ''


def clear_drop_note(job: dict) -> None:
    """Take the note off, because this listing is not removed any more.

    Called on every listing Claude keeps, not only on ones that once had a note: a verdict
    can change between runs -- a re-fetched posting, an edited rule, Sina keeping a flagged
    row by hand -- and a stale note claiming a kept job was removed is worse than none.
    """
    if not job.get('description'):
        return
    cleaned = listing_text_without_note(job['description'])
    if cleaned != job['description']:
        job['description'] = cleaned


def set_drop_note(job: dict, reason, evidence=None) -> None:
    """Put the reason, and the posting's own words behind it, on the end of the listing.

    `evidence` is the phrase Claude had to quote from the posting before it was allowed to
    drop anything; it is absent for a removal that rests on a number rather than a sentence
    (a résumé match below the minimum), and the note then carries the reason alone rather
    than pretending to a quote it does not have.
    """
    clear_drop_note(job)
    text = str(reason or '').strip() or 'unspecified reason'
    lines = ['%s %s' % (MARKER, _HEADING), text]
    quote = ' '.join(str(evidence or '').split())
    if quote:
        lines.append('Quoted from this posting: "%s"' % quote)
    lines.append(MARKER)
    # The posting is not tidied on its way past. Its own trailing blank lines are part of it,
    # and taking them off here makes the round trip lossy -- see _NOTE for what that cost.
    body = str(job.get('description') or '')
    job['description'] = (body + _SEPARATOR if body else '') + '\n'.join(lines)
