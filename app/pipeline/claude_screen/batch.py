# -*- coding: utf-8 -*-
"""Waiting for a queued batch to finish.

Both Claude passes send a batch and then sit here. Batches are answered on their own
schedule rather than immediately, so this is a poll, and the three things that can go
wrong -- the user cancels, a retrieve call fails transiently, the batch never ends --
are the same for both. It lives in its own module so the second pass does not have to
import from the first: they share a mechanism, not a subject.
"""
from __future__ import annotations

import time


_BATCH_POLL_SECONDS = 30
_BATCH_MAX_WAIT_SECONDS = 24 * 60 * 60
def _await_batch(client, batch_id, total, label, progress_cb=None, should_cancel=None) -> bool:
    """Wait for a batch to finish. True when it ended, False when it was cancelled or timed out.

    Both Claude passes send a batch and then sit here. Batches are queued rather than
    answered, so this is a poll, and the three things that can go wrong are the same for
    both: the user presses Cancel, the retrieve call itself fails transiently, or the batch
    never ends at all. Written once so a fix to any of them reaches both passes.

    A failed retrieve is slept through rather than treated as an ending: the batch is still
    running on Anthropic's side, and giving up on one bad HTTP response would abandon work
    already paid for.
    """
    started = time.time()
    while True:
        if should_cancel and should_cancel():
            try:
                client.messages.batches.cancel(batch_id)
            except Exception:
                pass
            if progress_cb:
                progress_cb("GLOG:filter_step:%s|warning|Batch cancelled. Listings keep "
                            "whatever verdicts they already had." % label, 0, 1)
            return False
        try:
            current = client.messages.batches.retrieve(batch_id)
        except Exception:
            time.sleep(_BATCH_POLL_SECONDS)
            continue
        if current.processing_status == 'ended':
            return True
        if time.time() - started > _BATCH_MAX_WAIT_SECONDS:
            if progress_cb:
                progress_cb("GLOG:filter_step:%s|error|The batch did not finish within 24 "
                            "hours. Screening will fall back to one call at a time." % label,
                            0, 1)
            return False
        if progress_cb:
            counts = getattr(current, 'request_counts', None)
            done = (getattr(counts, 'succeeded', 0) or 0) if counts else 0
            progress_cb("  Waiting for Claude's batch… (%d of %d answered, %.0f minutes so far)"
                        % (done, total, (time.time() - started) / 60), done, total)
        time.sleep(_BATCH_POLL_SECONDS)
