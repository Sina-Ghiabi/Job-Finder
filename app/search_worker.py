from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from app import pipeline


class SearchWorker(QThread):
    progress = Signal(str, int, int)
    finished_ok = Signal(object)  # pandas DataFrame -- also used for a cancelled search
    failed = Signal(str)
    # list[dict] problems, threading.Event, result_holder dict -- see
    # _preflight_problems_cb below. Emitted across threads, so Qt auto-connects it as a
    # queued connection and the slot runs on whichever thread owns the receiver (the
    # main/GUI thread) while this worker thread blocks on the Event until that slot
    # calls event.set().
    preflight_problems_needed = Signal(list, object, object)

    def __init__(self, token, limit_per_call, date_settings, countries, actor_order=None, cities=None,
                 search_for=None, search_languages=None,
                 jooble_api_keys=None, reed_uk_api_key=None,
                 francetravail_credentials=None, anthropic_api_key=None, parent=None,
                 search_title=None, search_level=None, search_work_mode=None,
                 actor_filter_settings=None,
                 ):
        super().__init__(parent)
        self.token = token
        self.limit_per_call = limit_per_call
        self.date_settings = date_settings
        self.search_for = search_for
        self.search_languages = search_languages
        self.search_title = search_title
        self.search_level = search_level
        # Read by LinkedIn's request builder: a Not Remote search must not ask the largest
        # source in the app for remote work only. See _linkedin_request.
        self.search_work_mode = search_work_mode
        self.countries = countries
        self.actor_order = actor_order
        self.cities = cities
        self.jooble_api_keys = jooble_api_keys
        self.reed_uk_api_key = reed_uk_api_key
        self.francetravail_credentials = francetravail_credentials
        self.anthropic_api_key = anthropic_api_key
        # The per-platform filters chosen in the Search window, carried as the whole
        # settings dict: app/pipeline/actor_filters.py owns the key they live under and
        # reads it itself, so only one place knows that name.
        self.actor_filter_settings = actor_filter_settings
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def _preflight_problems_cb(self, problems: list) -> dict:
        event = threading.Event()
        result_holder = {'cancel': False, 'resolved_keys': {}}
        self.preflight_problems_needed.emit(problems, event, result_holder)
        # Wake up periodically instead of blocking forever, so a cancel requested while
        # this window is still open (or never answered) cannot hang the whole search.
        while not event.wait(timeout=0.5):
            if self._cancel_requested:
                return {'cancel': True, 'resolved_keys': {}}
        return result_holder

    def run(self):
        try:
            # run_search() handles a cancel request internally -- it returns whatever was
            # already fetched (via finished_ok) instead of raising, so cancelling never
            # discards partial results. pipeline.SearchCancelled never escapes it.
            df = pipeline.run_search(
                self.token,
                self.limit_per_call,
                self.date_settings,
                search_for=self.search_for,
                search_languages=self.search_languages,
                search_title=self.search_title,
                search_level=self.search_level,
                search_work_mode=self.search_work_mode,
                actor_filter_settings=self.actor_filter_settings,
                countries=self.countries,
                actor_order=self.actor_order,
                cities=self.cities,
                progress_cb=lambda msg, done, total: self.progress.emit(msg, done, total),
                should_cancel=lambda: self._cancel_requested,
                jooble_api_keys=self.jooble_api_keys,
                reed_uk_api_key=self.reed_uk_api_key,
                francetravail_credentials=self.francetravail_credentials,
                preflight_problems_cb=self._preflight_problems_cb,
                anthropic_api_key=self.anthropic_api_key,
            )
            self.finished_ok.emit(df)
        except Exception as e:
            self.failed.emit(str(e))


class FilterWorker(QThread):
    progress = Signal(str, int, int)
    # kept jobs (incl. Claude-flagged), removed-by-keywords count, claude_flagged, then the
    # Thesis module's survivors and the Internship module's. Three separate lists because
    # they are three separate modules -- see run().
    finished_ok = Signal(list, int, list, list, list)
    failed = Signal(str)

    def __init__(self, jobs, anthropic_api_key=None, parent=None, search_title=None,
                 search_level=None, search_work_mode=None, search_countries=None,
                 search_cities=None, date_range=None, categories=None, sponsorship=None,
                 min_match_percent=0, fields=None):
        super().__init__(parent)
        self.jobs = jobs
        self.anthropic_api_key = anthropic_api_key
        # What Sina chose in Search. Filter judges by what is chosen NOW -- a listing saved by
        # last week's search is judged by today's title, Level and Remote choice.
        self.search_title = search_title
        self.search_level = search_level
        self.search_work_mode = search_work_mode
        # The countries and cities chosen in Search, read only by the Not Remote place rule:
        # a job you have to show up for has to be somewhere you are looking. Both, because a
        # city search stores no country at all.
        self.search_countries = search_countries
        self.search_cities = search_cities
        # The rest of what the Filter window offers. These were collected by the window and
        # never reached the pipeline, so a Netherlands Part-Time filter returned German
        # full-time listings -- see chosen_filters for the whole story.
        self.date_range = date_range
        self.categories = categories
        self.sponsorship = sponsorship
        self.min_match_percent = min_match_percent
        # Which of the searched job titles to read. Chosen in the Filter window, and
        # the one choice there that changes what a run COSTS rather than what it shows.
        self.fields = fields
        self._cancel_requested = False

    def request_cancel(self):
        """Filter's Claude Review step is one sequential API call per surviving listing,
        so a Filter run over a few hundred jobs can take minutes with no way to stop it.
        This flag is polled between listings inside reapply_filters -- cancelling keeps
        every decision already made rather than discarding the run. It also gives
        MainWindow.closeEvent something to actually ask for: it used to just wait 2
        seconds and then close anyway, abandoning a live QThread at interpreter
        shutdown."""
        self._cancel_requested = True

    def run(self):
        """The one module the chosen Level belongs to, over the saved listings.

        Sina's design: one Level at a time -- Thesis, Internship, or a job at Entry, Junior,
        Mid or Senior -- so Job and Internship are never one run. The three modules still
        share nothing; only one of them is asked.

        Thesis and Internship: their module recognises, filters and screens (part one of
        Claude), then the résumé match (part two) scores what is left. Every listing part two
        flags goes to the same review dialog as a Job listing, so nothing is deleted without
        Sina seeing it. Their survivors come back as `kept`, which is what the review dialog
        and the save below work on.

        The four job Levels: reapply_filters does all of it, both parts included.
        """
        try:
            emit = lambda msg, done, total: self.progress.emit(msg, done, total)  # noqa: E731
            cancelled = lambda: self._cancel_requested  # noqa: E731
            level = pipeline.clean_level(self.search_level)

            if level in ('thesis', 'internship'):
                find = (pipeline.find_thesis_postings if level == 'thesis'
                        else pipeline.find_internship_postings)
                emit('FILTER_START', 0, 1)
                kept, _reasons = find([dict(job) for job in self.jobs], progress_cb=emit,
                                     anthropic_api_key=self.anthropic_api_key,
                                     should_cancel=cancelled,
                                     search_title=self.search_title,
                                     search_work_mode=self.search_work_mode)
                claude_flagged: list = []
                pipeline.step_resume_match(kept, claude_flagged, self.anthropic_api_key,
                                           progress_cb=emit, should_cancel=cancelled)
                # Best match first, as the Job Levels are sorted.
                kept.sort(key=lambda j: -(j.get('claude_match')
                                          if isinstance(j.get('claude_match'), int) else -1))
                emit('FILTER_END', 0, 1)
                removed = len(self.jobs) - len(kept)
                self.finished_ok.emit(kept, removed, claude_flagged, [], [])
                return

            kept, removed, claude_flagged = pipeline.reapply_filters(
                self.jobs,
                progress_cb=emit,
                anthropic_api_key=self.anthropic_api_key,
                should_cancel=cancelled,
                search_title=self.search_title,
                search_level=level,
                search_work_mode=self.search_work_mode,
                search_countries=self.search_countries,
                search_cities=self.search_cities,
                date_range=self.date_range,
                categories=self.categories,
                sponsorship=self.sponsorship,
                min_match_percent=self.min_match_percent,
                fields=self.fields,
            )
            self.finished_ok.emit(kept, removed, claude_flagged, [], [])
        except Exception as e:
            self.failed.emit(str(e))


class HealthCheckWorker(QThread):
    """Runs the free health check off the GUI thread.

    Same shape as the two workers above, and separate from them on purpose: this one
    spends no money, so it must never be confused with a Search at the call site. The
    problems it finds are handed to the same window a search uses, with Claude's fix
    advice already attached.
    """

    progress = Signal(str, int, int)
    finished_ok = Signal(list)   # list[dict] problems -- empty means everything passed
    failed = Signal(str)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.settings = settings or {}
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            settings = self.settings
            jooble_keys = {
                key.replace('jooble_', '').replace('_api_key', ''): value
                for key, value in settings.items()
                if key.startswith('jooble_') and key.endswith('_api_key') and value
            }
            francetravail = None
            if settings.get('francetravail_client_id'):
                francetravail = (settings.get('francetravail_client_id'),
                                 settings.get('francetravail_client_secret'))
            problems = pipeline.run_health_check(
                apify_token=settings.get('apify_token'),
                countries=settings.get('countries') or [],
                cities=settings.get('cities') or [],
                jooble_api_keys=jooble_keys,
                reed_uk_api_key=settings.get('reed_uk_api_key'),
                francetravail_credentials=francetravail,
                progress_cb=lambda msg, done, total: self.progress.emit(msg, done, total),
                should_cancel=lambda: self._cancel_requested,
            )
            # The same plain-language advice a search's problems get. Best-effort: a
            # missing or failing Claude key leaves the problems listed in full without it.
            pipeline.explain_problems(
                problems, anthropic_api_key=settings.get('anthropic_api_key'),
                progress_cb=lambda msg, done, total: self.progress.emit(msg, done, total))
            self.finished_ok.emit(problems)
        except pipeline.SearchCancelled:
            self.finished_ok.emit([])
        except Exception as e:
            self.failed.emit(str(e))
