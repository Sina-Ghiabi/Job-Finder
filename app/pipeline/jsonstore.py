# -*- coding: utf-8 -*-
"""Reading a small JSON file from the data directory, cached on the file itself.

Four places in the pipeline keep a JSON file the app both reads constantly and writes to
mid-run -- the fetch strategy per domain, the direct-search URL overrides, the discovered
job-URL patterns, and the visa-sponsor registers. Each had written out the same twenty
lines: check the path exists, stat it for an mtime-and-size stamp, return the memoised value
when the stamp is unchanged, otherwise read and parse and store.

The stamp, rather than a plain "load once" flag, is the part that matters and the part that
was easiest to get subtly wrong in a fifth copy. These files are written *during* a run --
a URL pattern learned at minute ten has to be visible at minute eleven -- so a cache keyed
on the file's own mtime and size picks the new value up on the next call, while still
sparing the 217 open()+parse cycles a single 18-country search would otherwise spend on one
unchanging file.
"""
from __future__ import annotations

import json


def load_cached_json(path, cache: dict, clean=None) -> dict:
    """Return the parsed file, reading it only when it has changed since last time.

    `cache` is any dict the caller owns; this uses one key in it, 'value', holding
    (stamp, parsed). `clean` is an optional callable applied to the parsed dict before it
    is stored -- that step is the only thing the four callers did differently, so it is the
    only thing they still pass.

    Anything unreadable, unparseable, or not a JSON object comes back as {}. These files are
    caches and learned state, never the user's own data: a corrupt one should cost the run
    its memory of a URL pattern, not the run itself.
    """
    if not path.exists():
        cache['value'] = (None, {})
        return {}

    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        # A file that cannot be stat'd is still worth trying to read; it just cannot be
        # cached, because there is nothing to notice a later change by.
        stamp = None

    cached_stamp, cached_value = cache.get('value', (object(), {}))
    if stamp is not None and stamp == cached_stamp:
        return cached_value

    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        value = {}
    if not isinstance(value, dict):
        value = {}
    if clean is not None:
        value = clean(value)

    cache['value'] = (stamp, value)
    return value
