"""Running Apify actors and reading their datasets."""
from __future__ import annotations

import time
from apify_client import ApifyClient

from .errors import (SearchCancelled)


# LinkedIn moved to apimaestro's actor on 4 October 2026 (Document T-16), and the reason is one
# field. The actor before it, curious_coder/linkedin-jobs-scraper, returns no workplace type:
# the Hybrid / On-site / Remote chip LinkedIn shows next to a job is not in its output, not in
# the page it scrapes (a 274,866-character fetch of one advert contained the word "hybrid"
# zero times -- the chip renders only for a logged-in session), and its remote filter f_WT was
# measured IGNORED. So every Remote search bought office jobs at $0.002 a row and then guessed
# from prose, and three adverts in a row that Sina opened were tagged Hybrid on LinkedIn.
#
# This actor returns `work_type` on every row and has a remote filter that is honoured.
# Measured, same query: 100 of 100 rows tagged Remote with it, and the job IDPP -- whose text
# says "Working Model: Remote" and whose tag says Hybrid -- came back tagged Hybrid, which is
# what Sina saw.
#
# IT IS MORE EXPENSIVE PER ROW, NOT LESS, and an earlier version of this comment said the
# opposite. The actor's own price is $0.005 a job (read from its pricing events, not from a
# run's usageTotalUsd, which comes back empty for pay-per-event runs at the moment they
# finish) against $0.002 for the actor it replaced -- 2.5 times as much. What makes it cheaper
# PER USEFUL ROW is the remote filter: the old actor's 300 rows were about 6% Remote, so a
# Remote row cost ~$0.03; this one returns only Remote rows, so one costs $0.005. Per search
# the ceiling is about 155 rows, $0.78. Document T-16 has the arithmetic.
LINKEDIN_ACTOR = 'apimaestro/linkedin-jobs-scraper-api'

# Kept so the history is readable and so a test can say what was replaced. Nothing runs it.
LINKEDIN_LEGACY_ACTOR = 'curious_coder/linkedin-jobs-scraper'


INDEED_ACTOR = 'valig/indeed-jobs-scraper'


GLASSDOOR_ACTOR = 'valig/glassdoor-jobs-scraper'


WEBSITE_CONTENT_CRAWLER_ACTOR = 'apify/website-content-crawler'


# Real, verified via Apify's own actor input schema (GET .../builds/default): this
# actor auto-scales its browser/HTTP-client concurrency up to `maxConcurrency` (default
# 200) based on available CPU/memory, but the ACTOR RUN itself only gets the actor's
# own default of 8192MB unless told otherwise -- which caps how far that auto-scaling
# can actually go before the run risks running out of memory and crashing. Both
# deep-crawl calls below (_deepen_google_results and _run_direct_site_searches) always
# run AFTER Indeed/LinkedIn/Glassdoor/Google's own initial search call have all
# already finished (see run_search), so nothing else is using this account's compute
# at that moment -- safe to hand this one run the account's full memory cap (16384MB,
# confirmed via a real client.user().limits() call) instead of the actor's own lower
# default. This does NOT change what gets crawled (same maxCrawlPages, same coverage)
# -- it just gives the exact same work more real parallelism to run faster, at
# roughly the same total compute-unit cost (Apify bills memory x time, so 2x the
# memory for roughly half the wall-clock time nets out close to even).
# A quarter of the account's 16,384MB allowance, not all of it. Asking for the whole thing
# means the run can only start when nothing else is running, and Apify refuses it outright
# ("you will exceed the memory limit of 16384MB for all your Actor runs and builds")
# whenever another actor is still finishing -- which, during a real search, it usually is.
# Measured on a live Austria run: ten freshly-learned sites produced zero jobs for exactly
# this reason.
_DEEP_CRAWL_MEMORY_MBYTES = 4096


def _run_actor_cancellable(client: ApifyClient, actor_id: str, run_input: dict,
                            should_cancel=None, memory_mbytes: int | None = None, poll_interval: int = 4) -> dict:
    """start() + poll + abort(), same real pattern already used by run_search's own
    run_actor_and_fetch for Indeed/LinkedIn/Glassdoor/Google -- used here instead of
    the simpler blocking .call() specifically so Cancel can actually interrupt one of
    these runs within a few seconds. A real bug Sina reported: with the old .call(),
    clicking Cancel while a deep-crawl/direct-site-search/Google-preflight call was
    in flight left the Log frozen (no further lines) for as long as that ONE Apify run
    took to finish on its own -- which for a deep crawl can be minutes -- even though
    the rest of the app stayed responsive (a separate QThread, not the GUI thread, was
    the one actually blocked). Raises SearchCancelled if should_cancel() fires."""
    kwargs = {}
    if memory_mbytes is not None:
        kwargs['memory_mbytes'] = memory_mbytes
    run = client.actor(actor_id).start(run_input=run_input, **kwargs)
    run_id = run.get('id') if isinstance(run, dict) else getattr(run, 'id', None)
    if not run_id:
        raise RuntimeError(f"could not start actor run: {run!r}")
    while True:
        run_info = client.run(run_id).get()
        status = run_info.get('status') if isinstance(run_info, dict) else getattr(run_info, 'status', None)
        if status in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT', 'TIMED_OUT'):
            return run_info
        if should_cancel and should_cancel():
            try:
                client.run(run_id).abort()
            except Exception:
                pass
            raise SearchCancelled()
        time.sleep(poll_interval)

# --------------------------------------------------------------------------------------
# Crawling a list of URLs without losing any of them
# --------------------------------------------------------------------------------------
# Sina's rule for this whole section: do it in small pieces, take as long as it takes, and
# lose nothing. Three call sites crawl URL lists (the Google deep crawl, the newly-learned
# sites, and the direct site search) and each used to do it as one run asking for the
# account's entire 16,384MB. Apify refuses that outright whenever anything else is running,
# and all three responded by returning nothing.
#
# The refusal is temporary -- it means "the account is busy", not "this cannot be done" --
# so the fix is to wait and ask again, in pieces small enough to fit beside other runs.

_CRAWL_BATCH_ATTEMPTS = 4          # per batch, before it is broken up
_CRAWL_RETRY_SECONDS = (20, 45, 90)  # waits between attempts; the last repeats
_CRAWL_BUSY_MARKERS = ('memory limit', 'exceed the memory', 'not enough memory',
                       'rate limit', 'too many requests', 'concurrent runs')


def _crawl_is_busy_error(error: Exception) -> bool:
    """Is this Apify saying "not now" rather than "not ever"?

    Only these are worth waiting for. A 404, a bad actor id or a malformed input will
    fail identically however long the wait, and retrying those would turn one broken URL
    into four times the delay for nothing.
    """
    text = str(error).lower()
    return any(marker in text for marker in _CRAWL_BUSY_MARKERS)


def crawl_urls_in_batches(client, actor_id: str, urls: list, build_input, batch_size: int,
                          should_cancel=None, progress_cb=None, label: str = 'crawl',
                          memory_mbytes: int | None = None) -> tuple:
    """Crawl every URL in `urls`, in batches, and return (items, failed_urls, usd).

    build_input(batch) -> the actor run input for that batch.

    A batch that fails because the account is busy is retried with a growing wait. A batch
    that still fails is split and its URLs are tried one at a time, so one unreachable page
    cannot cost the others. `failed_urls` is what genuinely could not be crawled after all
    of that -- it is returned rather than swallowed so the caller can report it.
    """
    import time as _time

    items: list = []
    failed: list = []
    spent = 0.0
    if not urls:
        return items, failed, spent

    batches = [urls[i:i + batch_size] for i in range(0, len(urls), max(1, batch_size))]

    def run_one(batch, attempts):
        """Returns (dataset items, usd) or raises the last error."""
        last = None
        for attempt in range(attempts):
            if should_cancel and should_cancel():
                raise SearchCancelled()
            try:
                run = _run_actor_cancellable(
                    client, actor_id, build_input(batch),
                    should_cancel=should_cancel, memory_mbytes=memory_mbytes)
                status = (run.get('status') if isinstance(run, dict)
                          else getattr(run, 'status', None))
                if status != 'SUCCEEDED':
                    raise RuntimeError('run ended with status %s' % status)
                dataset_id = _get_default_dataset_id(run)
                if not dataset_id:
                    raise RuntimeError('could not find dataset id on run object: %r' % (run,))
                used = (run.get('usageTotalUsd') if isinstance(run, dict)
                        else getattr(run, 'usage_total_usd', None))
                try:
                    used = float(used or 0)
                except (TypeError, ValueError):
                    used = 0.0
                return list(client.dataset(dataset_id).iterate_items()), used
            except SearchCancelled:
                raise
            except Exception as exc:
                last = exc
                if not _crawl_is_busy_error(exc) or attempt == attempts - 1:
                    break
                wait = _CRAWL_RETRY_SECONDS[min(attempt, len(_CRAWL_RETRY_SECONDS) - 1)]
                if progress_cb:
                    progress_cb('GLOG:%s|info|Apify is busy; waiting %ds and trying these '
                                '%d page(s) again (attempt %d of %d).'
                                % (label, wait, len(batch), attempt + 2, attempts), 0, 1)
                _time.sleep(wait)
        raise last if last else RuntimeError('crawl failed with no error recorded')

    if progress_cb and len(batches) > 1:
        progress_cb('GLOG:%s|info|%d page(s) to open, in %d batch(es) of up to %d. Each '
                    'batch is one Apify run; the count below moves as they finish.'
                    % (label, len(urls), len(batches), batch_size), 0, 1)

    for index, batch in enumerate(batches, 1):
        try:
            got, used = run_one(batch, _CRAWL_BATCH_ATTEMPTS)
            items.extend(got)
            spent += used
            # Said out loud, because silence here is indistinguishable from a hang. On the
            # real Germany run this stage worked for 83 minutes without writing one line:
            # the only sign it was alive was the credit ticking down, and that stalls too
            # while a batch waits for Apify. A stage that can run over an hour has to say
            # where it is.
            if progress_cb:
                progress_cb('GLOG:%s|info|Batch %d of %d done — %d page(s) read so far, '
                            '$%.2f spent on this stage.'
                            % (label, index, len(batches), len(items), spent), 0, 1)
            continue
        except SearchCancelled:
            raise
        except Exception as exc:
            if progress_cb:
                progress_cb('GLOG:%s|warning|Batch %d of %d did not go through (%s). '
                            'Trying its %d page(s) one at a time so none are lost.'
                            % (label, index, len(batches), str(exc)[:70], len(batch)), 0, 1)

        # One at a time, so a single bad URL costs only itself.
        for url in batch:
            try:
                got, used = run_one([url], 2)
                items.extend(got)
                spent += used
            except SearchCancelled:
                raise
            except Exception as exc:
                failed.append(url)
                if progress_cb:
                    progress_cb('GLOG:%s|warning|Could not crawl %s (%s).'
                                % (label, str(url)[:70], str(exc)[:60]), 0, 1)

    return items, failed, spent



def _get_default_dataset_id(run):
    if isinstance(run, dict):
        return run.get('defaultDatasetId') or run.get('default_dataset_id')
    return getattr(run, 'default_dataset_id', None) or getattr(run, 'defaultDatasetId', None)


class ActorRunFailed(RuntimeError):
    """Same as a plain RuntimeError, but carries the real usage_usd cost Apify reports
    for the run even though it failed (Apify still bills for compute already spent on
    a FAILED/ABORTED/TIMED-OUT run) -- so the caller can still log what that failed
    attempt cost, not just that it failed."""

    def __init__(self, message: str, usage_usd: float | None = None):
        super().__init__(message)
        self.usage_usd = usage_usd


DEFAULT_ACTOR_ORDER = ['indeed', 'glassdoor', 'linkedin']


# How often the live "Apify Token - $X.XX credit" line in the Log refreshes during a
# search -- Sina asked for this after noticing it only ever showed the balance from the
# very start of the run, even on a long search that kept spending real credit.
_APIFY_CREDIT_POLL_SECONDS = 10
