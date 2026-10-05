# -*- coding: utf-8 -*-
"""Writing down what a running search has collected, so a crash cannot take it.

A three-hour German search died with a segmentation fault part-way through fetching the 722
postings it had just found inside index pages. No Python traceback -- the process was killed
outright, because the crash was inside a C library and nothing in Python can catch that.
Three hours of work and $6.40 of Apify credit went with it, and so did every listing
collected, because `run_search` holds the whole run in memory and writes nothing until it
returns.

There is no way to handle a crash like that. The only defence is to have already written the
rows down, so this saves after each stage: each search pass, the Google stage, the date
filter, the expansion. A crash then costs the stage that was running rather than the run.

Separate from `jobs.json` deliberately. A half-finished search is not a result -- it has not
been deduplicated, dated or filtered -- and merging it into the real list would make a
crashed run indistinguishable from a good one. It goes to its own file, the next start says
it found one, and the user decides.

A thin wrapper over `app.storage` rather than calling it directly from the runner: the
pipeline does not otherwise import the storage layer, and one import in one small module is
easier to keep honest than one buried in the middle of run_search.
"""
from __future__ import annotations


def save(stage: str, rows: list) -> None:
    """Write down what has been collected so far. Never raises, never blocks the search.

    Anything at all going wrong here must be survivable: this is insurance, and insurance
    that can cost you the thing it insures is worse than none. A failed write leaves the
    previous checkpoint in place, which is still better than nothing.
    """
    try:
        from app import storage
        storage.save_search_checkpoint(stage, rows)
    except Exception:                                           # noqa: BLE001
        pass


def clear() -> None:
    """Drop the checkpoint, once a search has finished properly.

    This is what gives the file its meaning: a checkpoint found at startup means the last
    search did not finish, because a search that finishes removes its own.
    """
    try:
        from app import storage
        storage.clear_search_checkpoint()
    except Exception:                                           # noqa: BLE001
        pass
