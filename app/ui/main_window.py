from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app import pipeline, resume, storage
from app.pipeline.claude_screen import prompt as claude_prompt
from app.pipeline.drop_note import clear_drop_note
from app.search_worker import FilterWorker, HealthCheckWorker, SearchWorker
from app.pipeline import filter_signature, title_equivalents
from app.ui.apply_dialog import ApplyDialog
from app.ui.applications_page import ApplicationsPage
from app.ui.claude_review_dialog import ClaudeReviewDialog
from app.ui.filter_dialog import FilterDialog
from app.ui.jobs_page import JobsPage
from app.ui.log_lines import LogLines
from app.ui.log_panel import LogPanel
from app.ui.preflight_problems_dialog import PreflightProblemsDialog
from app.ui.setup_wizard import SetupWizard


# Fallback used when settings.json predates (or is missing) the date_values block. Read
# from the same table the wizard picks from, so the default cannot drift away from what the
# wizard would have produced -- and so each actor still gets its own type: LinkedIn a
# keyword string, Indeed a number as a string, Glassdoor a plain integer.
DEFAULT_DATE_VALUES = pipeline.date_settings_for(pipeline.DEFAULT_DATE_RANGE)


# The entire Log protocol, in one place and in the exact order the old
# if/elif chain tested it. Each entry routes one message shape to one small
# handler below. Adding a message type is one line here plus one method --
# it used to mean finding the right spot inside a 286-line chain.
#
# 'exact' matches the whole message; 'prefix' matches its start (the rest of
# the message is that handler's payload).
_LOG_ROUTES = (
    ('exact' , 'TOKEN_CHECK_START'       , '_log_token_check_start'),
    ('prefix', 'TOKEN_CHECK_ITEM:'       , '_log_token_check_item'),
    ('exact' , 'HEALTH_START'            , '_log_health_start'),
    ('prefix', 'HEALTH_ITEM:'            , '_log_health_item'),
    ('prefix', 'HEALTH_END:'             , '_log_health_end'),
    ('exact' , 'PREFLIGHT_START'         , '_log_preflight_start'),
    ('prefix', 'PREFLIGHT_ITEM:'         , '_log_preflight_item'),
    ('prefix', 'PREFLIGHT_END:'          , '_log_preflight_end'),
    ('exact' , 'KNOWN_SITES_START'       , '_log_known_sites_start'),
    ('prefix', 'KNOWN_SITES_HEADER:'     , '_log_known_sites_header'),
    ('prefix', 'KNOWN_SITE_RESULT:'      , '_log_known_site_result'),
    ('exact' , 'STARTUP_SITES_START'     , '_log_startup_sites_start'),
    ('prefix', 'STARTUP_SITES_HEADER:'   , '_log_startup_sites_header'),
    ('prefix', 'STARTUP_SITE_RESULT:'    , '_log_startup_site_result'),
    ('exact' , 'DEEP_CRAWL_START'        , '_log_deep_crawl_start'),
    ('prefix', 'DEEP_CRAWL_HEADER:'      , '_log_deep_crawl_header'),
    ('prefix', 'DEEP_CRAWL_SITE_RESULT:' , '_log_deep_crawl_site_result'),
    ('exact' , 'DIRECT_SITE_START'       , '_log_direct_site_start'),
    ('prefix', 'DIRECT_SITE_HEADER:'     , '_log_direct_site_header'),
    ('exact' , 'GOOGLE_STAGE_FAILED'     , '_log_google_stage_failed'),
    ('exact' , 'FILTER_START'            , '_log_filter_start'),
    ('exact' , 'FILTER_END'              , '_log_filter_end'),
    ('prefix', 'FILTER_STEP_START:'      , '_log_filter_step_start'),
    ('prefix', 'FILTER_STEP_ITEM:'       , '_log_filter_step_item'),
    ('prefix', 'FILTER_STEP_DONE:'       , '_log_filter_step_done'),
    ('prefix', 'PLATFORM_START:'         , '_log_platform_start'),
    ('prefix', 'PLATFORM_END:'           , '_log_platform_end'),
    ('prefix', 'LOCATION_START:'         , '_log_location_start'),
    ('exact' , 'ENRICH_START'             , '_log_enrich_start'),
    ('exact' , 'ENRICH_END'               , '_log_enrich_end'),
    ('prefix', 'ENRICH_SITE_RESULT:'      , '_log_enrich_site_result'),
    ('exact' , 'PATTERN_DISCOVERY_START'  , '_log_pattern_start'),
    ('exact' , 'PATTERN_DISCOVERY_END'    , '_log_pattern_end'),
    ('prefix', 'PATTERN_SITE_RESULT:'     , '_log_pattern_site_result'),
    ('exact' , 'PATTERN_CRAWL_START'      , '_log_pattern_crawl_start'),
    ('exact' , 'PATTERN_CRAWL_END'        , '_log_pattern_crawl_end'),
    ('prefix', 'PATTERN_CRAWL_SITE_RESULT:', '_log_pattern_crawl_site_result'),
    ('prefix', 'GLOG:'                   , '_log_glog'),
    ('prefix', 'DIRECT_API_START'        , '_log_direct_api_start'),
    ('prefix', 'DIRECT_API_END'          , '_log_direct_api_end'),
    ('prefix', 'BROWSER_SITES_START'     , '_log_browser_sites_start'),
    ('prefix', 'BROWSER_SITES_END'       , '_log_browser_sites_end'),
    ('prefix', 'LOCATION_DONE:'          , '_log_location_done'),
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RoleHound")
        self.resize(1600, 960)
        self.showMaximized()

        self.settings = storage.load_settings()
        self.worker: SearchWorker | None = None
        self.filter_worker: FilterWorker | None = None
        # What the Filter now running was asked for. Held from the moment it starts until it
        # finishes, because the signature may only be written once there is a result it
        # describes -- and must be dropped if the run fails. None when nothing is running.
        self._pending_filter: dict | None = None
        self.health_worker: HealthCheckWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_navbar())

        self.stack = QStackedWidget()
        self.jobs_page = JobsPage()
        self.applications_page = ApplicationsPage()
        self.stack.addWidget(self.jobs_page)
        self.stack.addWidget(self.applications_page)
        root_layout.addWidget(self.stack, stretch=1)

        self.log_panel = LogPanel()
        # Every Log line is rendered by this, not by the window (see app/ui/log_lines.py).
        self.log_lines = LogLines(self.log_panel)
        root_layout.addWidget(self.log_panel)

        self.jobs_page.new_search_btn.clicked.connect(self.open_setup_wizard)
        self.jobs_page.apply_requested.connect(self.handle_apply)
        self.jobs_page.remove_requested.connect(self.handle_remove_job)
        self.jobs_page.filter_requested.connect(self.handle_filter_existing)
        self.jobs_page.health_check_requested.connect(self.handle_health_check)
        self.jobs_page.clear_all_requested.connect(self.handle_clear_all_jobs)
        self.jobs_page.cancel_search_requested.connect(self.handle_cancel_search)

        self._select_page(0)
        self.jobs_page.show_jobs(storage.load_jobs())
        self.log_panel.log("RoleHound started — showing previously saved listings.")
        # Anything the loaders above could not read. They return empty rather than
        # crashing, which is right, and used to say nothing at all -- so a damaged
        # jobs.json was indistinguishable from a search that found nothing.
        self._report_storage_problems()
        self._report_interrupted_search()

        # Sequence counter for GLOG: messages (nested, one-shot status lines from
        # Direct Site Search / Direct API Search / Browser-Only Sites / sponsor checks)
        # -- each needs its own unique key so it never accidentally collides with (and
        # in-place-updates) another one-shot line; see _on_progress_log's GLOG: handler.
        self._glog_seq = 0

    def _build_navbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("NavBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)

        brand = QLabel("RoleHound")
        brand.setObjectName("BrandLabel")
        layout.addWidget(brand)

        self.jobs_nav_btn = QPushButton("Job Search")
        self.jobs_nav_btn.setCheckable(True)
        self.jobs_nav_btn.setChecked(True)
        self.jobs_nav_btn.clicked.connect(lambda: self._select_page(0))

        self.apps_nav_btn = QPushButton("My Applications")
        self.apps_nav_btn.setCheckable(True)
        self.apps_nav_btn.clicked.connect(lambda: self._select_page(1))

        layout.addWidget(self.jobs_nav_btn)
        layout.addWidget(self.apps_nav_btn)
        layout.addStretch(1)

        export_btn = QPushButton("Export Excel")
        export_btn.clicked.connect(self.handle_export)
        layout.addWidget(export_btn)
        return bar

    def _select_page(self, index: int):
        self.stack.setCurrentIndex(index)
        self.jobs_nav_btn.setChecked(index == 0)
        self.apps_nav_btn.setChecked(index == 1)
        if index == 1:
            self.applications_page.reload()

    def open_setup_wizard(self):
        wizard = SetupWizard(self.settings, self)
        if wizard.exec() != SetupWizard.Accepted:
            # The dialog closing via Cancel doesn't mean nothing changed -- the Save
            # button writes to disk without closing the dialog, so pick up any such
            # change now instead of leaving self.settings stale until app restart.
            self.settings = storage.load_settings()
            return
        # Accepted means Start Search was clicked, which only happens after
        # _build_result_settings succeeded -- so result_settings is a dict here. Guard
        # anyway rather than assume: a future dialog path that accepts without
        # building would otherwise overwrite settings.json with None.
        if wizard.result_settings is not None:
            self.settings = wizard.result_settings
            storage.save_settings(self.settings)
        if wizard.should_start_search:
            self.start_search()

    def start_search(self):
        # Real bug fixed here: without this, a second Search in the same session would
        # reuse the first run's log keys ('platform:Indeed', 'known_sites', ...) and
        # silently rewrite those old lines in place instead of appending fresh ones --
        # see LogPanel.reset_keys' own docstring.
        # Real crash fixed here: apify_token / limit_per_call / date_values used to be
        # read by direct index while every other key used .get(). A settings.json
        # written before one of them existed -- or hand-edited, which the Document
        # actually tells you to do to add Jooble/Reed keys -- raised KeyError straight
        # out of this click handler with no dialog and no log line. The wizard is the
        # one place that can fix a genuinely missing token, so that's where it points.
        if not self.settings.get('apify_token'):
            QMessageBox.warning(
                self, "Setup needed",
                "No Apify token is saved yet. Open New Search and fill in the wizard first.",
            )
            return
        self.log_panel.reset_keys()
        self.jobs_page.set_searching(True, cancellable=True)
        self.log_panel.log("Search started.")
        self.worker = SearchWorker(
            self.settings['apify_token'],
            self.settings.get('limit_per_call') or 1000,
            self.settings.get('date_values') or DEFAULT_DATE_VALUES,
            self.settings.get('countries'),
            search_for=self.settings.get('search_for'),
            # Always both: once in English, once in the country's own language.
            search_languages=pipeline.ALL_SEARCH_LANGUAGES,
            actor_order=self.settings.get('actor_order'),
            cities=self.settings.get('cities'),
            jooble_api_keys={
                code: self.settings[f'jooble_{code}_api_key']
                for code in pipeline.JOOBLE_API_COUNTRIES
                if self.settings.get(f'jooble_{code}_api_key')
            },
            reed_uk_api_key=self.settings.get('reed_uk_api_key'),
            francetravail_credentials=(
                (self.settings['francetravail_client_id'], self.settings['francetravail_client_secret'])
                if self.settings.get('francetravail_client_id') and self.settings.get('francetravail_client_secret')
                else None
            ),
            anthropic_api_key=self.settings.get('anthropic_api_key') or None,
            # The one title and the one Level chosen in Search decide every query, and
            # Remote / Not Remote decides what LinkedIn is asked for -- it is the only
            # source of the three that filters by working arrangement at its own end.
            search_title=self.settings.get('search_title'),
            search_level=self.settings.get('search_level'),
            search_work_mode=self.settings.get('search_work_mode'),
            # The per-platform filters from the Search window. The whole settings dict is
            # passed rather than the one key, because actor_filters owns the key name and
            # reads it itself -- one place decides where these live.
            actor_filter_settings=self.settings,
        )
        self.worker.progress.connect(self.jobs_page.set_progress)
        self.worker.progress.connect(self._on_progress_log)
        self.worker.finished_ok.connect(self._on_search_finished)
        self.worker.failed.connect(self._on_search_failed)
        self.worker.preflight_problems_needed.connect(self._on_preflight_problems_needed)
        self.worker.start()

    def handle_cancel_search(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.log_panel.log("Cancelling search — showing whatever was found so far…")
        # The same button now also stops a Filter run: its Claude Review step is one
        # sequential API call per listing, so a big Filter used to be uninterruptible.
        if self.filter_worker and self.filter_worker.isRunning():
            self.filter_worker.request_cancel()
            self.log_panel.log("Cancelling Filter — keeping every decision made so far…")

    def _on_progress_log(self, message: str, done: int, total: int):
        # Structured, per-platform granular log events (see run_search's
        # run_platform_locations/process_plan_item) -- each selected platform
        # (Indeed/LinkedIn/Glassdoor) gets its own live-ticking header line, and each
        # of its countries/cities gets its own line that updates in place from
        # 'Starting…' to a final green 'Succeeded'/red 'Failed', with the real dollar
        # cost Apify reports for that run when available. Parsed before the generic
        # ERROR:/SUCCESS:/WARNING: convention below, which every other operation in
        # the app still uses unchanged.
        for kind, key, handler in _LOG_ROUTES:
            if (message == key) if kind == 'exact' else message.startswith(key):
                getattr(self.log_lines, handler)(message)
                return

        if message.startswith('ERROR:'):
            self.log_panel.log(f"[{done}/{total}] {message[len('ERROR:'):].strip()}", level='error')
        elif message.startswith('SUCCESS:'):
            self.log_panel.log(f"[{done}/{total}] {message[len('SUCCESS:'):].strip()}", level='success')
        elif message.startswith('WARNING:'):
            self.log_panel.log(f"[{done}/{total}] {message[len('WARNING:'):].strip()}", level='warning')
        else:
            self.log_panel.log(f"[{done}/{total}] {message}")

    def _on_preflight_problems_needed(self, problems: list, event, result_holder: dict):
        # Runs on the main/GUI thread (Qt queues this slot call automatically, since the
        # signal was emitted from the worker thread) while SearchWorker blocks on `event`.
        try:
            dlg = PreflightProblemsDialog(problems, self)
            dlg.exec()
            result_holder['cancel'] = dlg.cancelled
            result_holder['resolved_keys'] = dlg.resolved_keys
            if dlg.resolved_keys:
                # Persist any live fix straight to settings.json too, so the next
                # search doesn't need it typed in again.
                for settings_key, value in dlg.resolved_keys.items():
                    if '|||' in value and settings_key == 'francetravail_client_id':
                        client_id, client_secret = value.split('|||', 1)
                        self.settings['francetravail_client_id'] = client_id
                        self.settings['francetravail_client_secret'] = client_secret
                    else:
                        self.settings[settings_key] = value
                storage.save_settings(self.settings)
                self.log_panel.log(f"Saved {len(dlg.resolved_keys)} fixed key(s) for next time.", level='success')
        finally:
            event.set()

    def handle_health_check(self):
        """The free sweep: every site, API and saved pattern, against the real web.

        Deliberately separate from Search. A search costs money and answers "what jobs are
        there"; this costs nothing and answers "is anything broken" -- which is the question
        worth asking BEFORE paying, and the only one that catches a job board changing
        under the app while every test stays green.
        """
        if self.health_worker is not None and self.health_worker.isRunning():
            return
        self.log_panel.reset_keys()
        self.jobs_page.set_searching(True, cancellable=False)
        self.log_panel.log('Health check started — no Apify credit is spent on any of this.')
        self.health_worker = HealthCheckWorker(self.settings, parent=self)
        self.health_worker.progress.connect(self._on_progress_log)
        self.health_worker.finished_ok.connect(self._on_health_check_finished)
        self.health_worker.failed.connect(self._on_health_check_failed)
        self.health_worker.start()

    def _on_health_check_finished(self, problems: list):
        self.jobs_page.set_searching(False)
        if not problems:
            self.log_panel.log('Health check finished — everything checked is working.',
                               level='success')
            return
        self.log_panel.log('Health check finished — %d problem(s) found.' % len(problems),
                           level='error')
        dialog = PreflightProblemsDialog(problems, self)
        dialog.exec()

    def _on_health_check_failed(self, message: str):
        self.jobs_page.set_searching(False)
        self.log_panel.log(f"Health check FAILED: {message}", level='error')

    def _report_storage_problems(self):
        """Put anything storage could not read into the Log, in red.

        The loaders return empty instead of raising, so the app survives a damaged or
        half-synced file -- but until this existed they also said nothing, and an
        unreadable jobs.json looked exactly like a search that found nothing. The user asked
        for the opposite: [owner's note: show a red mark wherever something goes wrong, so a problem is visible].
        """
        for problem in storage.take_load_problems():
            self.log_panel.log(problem, level='error')

    def _report_interrupted_search(self):
        """Say so when the last search did not finish, and where its listings are.

        A search that completes deletes its own checkpoint, so finding one here means the
        last one died — a crash, a power cut, a closed terminal. This existed because one
        did: a three-hour German search was killed by a segmentation fault inside a C
        library, and every listing it had collected went with it because nothing had been
        written down. Now it has been, and the point of saying so is that the work is
        recoverable rather than merely mourned.
        """
        saved = storage.load_search_checkpoint()
        if not saved:
            return
        self.log_panel.log(
            'The last search did not finish — it stopped during "%s" on %s. The %s '
            'listing(s) it had already collected were saved and are still in %s.'
            % (saved.get('stage') or 'an unknown stage',
               str(saved.get('saved_at') or 'an unknown time').replace('T', ' at '),
               format(int(saved.get('count') or 0), ','),
               storage.SEARCH_CHECKPOINT_PATH),
            level='warning')

    def _on_search_finished(self, df):
        self.jobs_page.set_searching(False)
        new_jobs = df.to_dict('records') if df is not None and not df.empty else []
        merged = storage.prepend_jobs(new_jobs)
        # Into the Bank as well, untouched. Filter reads from there, so trying another Level
        # or Remote / Not Remote never means paying for this search again.
        banked = storage.add_to_bank(new_jobs)
        # The pool just changed, so the stored Filter signature no longer describes it. The
        # signature hashes the pool for exactly this reason and would differ anyway; clearing
        # it here means the Filter window never even offers a shortcut it would then refuse.
        storage.clear_filter_state()
        self.jobs_page.show_jobs(merged)
        self.log_panel.log(f"Search finished — {len(new_jobs)} new listings added on top ({len(merged)} total).")
        self.log_panel.log(f"Bank now holds {banked} unfiltered listing(s) — the Filter reads "
                           f"from there, so it can be re-run for any Level or work mode "
                           f"without searching again.", level='success')
        self._report_storage_problems()

    def _on_search_failed(self, message: str):
        self.jobs_page.set_searching(False)
        self.log_panel.log(f"Search FAILED: {message}", level='error')
        QMessageBox.critical(self, "Search failed", message)

    def handle_apply(self, job: dict):
        dialog = ApplyDialog(job, self)
        if dialog.exec() != ApplyDialog.Accepted:
            return
        storage.add_application(job, dialog.document_paths)
        self.log_panel.log(f"Applied to '{job.get('title')}' at {job.get('company')}.")

        job_id = job.get('id')
        if job_id:
            remaining = storage.delete_job(job_id)
            self.jobs_page.show_jobs(remaining)

        QMessageBox.information(
            self, "Application saved",
            "This application was added to 'My Applications' and removed from the Job Search list.",
        )
        self.applications_page.reload()

    def handle_remove_job(self, job_id: str):
        remaining = storage.delete_job(job_id)
        self.jobs_page.show_jobs(remaining)
        self.log_panel.log("Removed a listing.")

    def handle_clear_all_jobs(self):
        storage.clear_jobs()
        self.jobs_page.show_jobs([])
        self.log_panel.log("Cleared all saved job listings.")

    def handle_filter_existing(self):
        """Open the Filter window, and act on what it says.

        The user's design, in his words: click Filter and every option there is opens in one
        window; Submit closes it and the filtering starts; click Filter again and one button
        takes every filter off and shows the whole Bank. And a Filter already run with exactly
        these choices must show its previous answer instead of being run again.

        Three things can come back, and each has to be handled here rather than deeper down,
        because only this method knows what is currently on screen:

            cleared      show the Bank, unfiltered
            unchanged    show what the last run kept -- free, instant
            changed      run the Filter for real
        """
        # From the Bank, not from what the last Filter left behind: a second Filter must see
        # every listing the search paid for, not only the survivors of the first one. Falls
        # back to the saved listings for a pool searched before the Bank existed.
        jobs, searched_at = storage.load_bank()
        if not jobs:
            jobs = storage.load_jobs()
        if not jobs:
            self.log_panel.log("Filter: nothing saved to check.")
            return

        previous = storage.load_filter_state()
        dialog = FilterDialog(self._filter_settings(previous), len(jobs),
                              last_run=str(previous.get('described') or ''), parent=self,
                              field_counts=self._searched_titles(previous))
        if dialog.exec() != QDialog.Accepted:
            return

        if dialog.cleared:
            self._show_unfiltered(jobs)
            return

        chosen = dialog.chosen
        described = filter_signature.describe(chosen)
        signature = self._filter_signature_for(chosen, jobs)

        # The whole point of the window. Nothing about the choices, the pool, the résumé or
        # the rules has moved, so the answer on disk is still the answer -- and re-running
        # would spend Claude credit to arrive at it again.
        if previous.get('signature') and previous['signature'] == signature:
            kept = storage.load_jobs()
            if kept:
                self.jobs_page.show_jobs(kept)
                self.log_panel.log("Filter unchanged — showing the %d listing(s) the last "
                                   "run kept. Nothing was re-checked." % len(kept),
                                   level='success')
                self.log_panel.log("  %s" % described)
                return
            # jobs.json is gone or unreadable while the shortcut survived. Filter for real
            # rather than show nothing; the shortcut is not worth trusting over the data.
            self.log_panel.log("Filter: the saved result is missing, so this runs again.",
                               level='warning')

        self._remember_filter_choices(chosen)
        self._pending_filter = {'signature': signature, 'choices': chosen,
                                'described': described}
        self._start_filter(jobs, searched_at, chosen, described)

    def _searched_titles(self, previous: dict) -> list:
        """The job titles this search asked for, for the Filter window's own list.

        Read from what was SEARCHED -- title_equivalents' cached answer for the title -- and
        never by scanning the pool. The user was explicit: [owner's note: it must not read every advert to list titles; show only the titles that were searched].

        `client=None`, so this never asks Claude just to open a window: an answer already
        cached is used, and a title never asked about yet simply offers nothing, which the
        window words as "only the title above was searched for".
        """
        title = ((previous.get('choices') or {}).get('search_title')
                 or self.settings.get('search_title'))
        if not title:
            return []
        try:
            names = title_equivalents.equivalents_for(title)
            return title_equivalents.searched_titles(title, names)
        except Exception:
            # Opening the Filter window must never fail over this. No list means no choice to
            # narrow by, which is the same as ticking all of them.
            return []

    def _filter_settings(self, previous: dict) -> dict:
        """What the window should open showing: the last Filter's choices, else Search's."""
        if previous.get('choices'):
            return dict(previous['choices'])
        return {
            'search_title': self.settings.get('search_title'),
            'search_level': self.settings.get('search_level'),
            'search_work_mode': self.settings.get('search_work_mode'),
            'countries': self.settings.get('countries'),
            'cities': self.settings.get('cities'),
            'date_range': self.settings.get('date_range'),
            'min_match_percent': 0,
            'categories': [],
            'sponsorship': '',
            'fields': [],
            'use_claude': True,
        }

    def _filter_signature_for(self, chosen: dict, jobs: list) -> str:
        """This Filter, over this pool, under these rules."""
        # Both are read defensively: a missing résumé or an unreachable prompt must make the
        # signature differ (so the Filter runs again) rather than raise on the way to a
        # window the user just pressed a button on.
        try:
            resume_mark = resume.fingerprint(claude_prompt.current_resume_text())
        except Exception:
            resume_mark = ''
        try:
            prompt_mark = claude_prompt.prompt_version_for(
                {pipeline.search_title.LEVEL_ROW_KEY: chosen.get('search_level'),
                 pipeline.search_title.WORK_MODE_ROW_KEY: chosen.get('search_work_mode')})
        except Exception:
            prompt_mark = ''
        return filter_signature.filter_signature(
            chosen, filter_signature.pool_fingerprint(jobs), resume_mark, prompt_mark)

    def _remember_filter_choices(self, chosen: dict) -> None:
        """Keep the choices in settings, so Search and the window agree next time."""
        for key in ('search_title', 'search_level', 'search_work_mode'):
            if chosen.get(key):
                self.settings[key] = chosen[key]
        storage.save_settings(self.settings)

    def _show_unfiltered(self, jobs: list) -> None:
        """Every filter off: the Bank exactly as the search left it."""
        storage.clear_filter_state()
        storage.save_jobs(jobs)
        self.jobs_page.show_jobs(jobs)
        self.log_panel.log("Filters cleared — showing all %d listing(s) from the Bank."
                           % len(jobs), level='success')

    def _start_filter(self, jobs: list, searched_at: str, chosen: dict,
                      described: str) -> None:
        """Run the Filter for real, with the choices the window collected."""
        self.log_panel.log("Filtering the Bank — %d listing(s)%s."
                           % (len(jobs),
                              ' searched %s' % searched_at[:10] if searched_at else ''))
        anthropic_key = (self.settings.get('anthropic_api_key') or None
                         if chosen.get('use_claude', True) else None)
        # Same reset as start_search -- Filter is explicitly meant to be re-run repeatedly
        # (see README), so this is the routine, not the rare, case.
        self.log_panel.reset_keys()
        # cancellable=True now that FilterWorker has a real request_cancel() -- the Claude
        # Review step is the longest thing this app does.
        self.jobs_page.set_searching(True, cancellable=bool(anthropic_key))
        note = " (with Claude final pass)" if anthropic_key else " (keyword rules only)"
        self.log_panel.log(f"Filter started{note} — re-checking {len(jobs)} saved listing(s).")
        # Kept so the final "removed N listing(s)" summary can be computed as a straight
        # before/after total -- see the note on _filter_original_count's first use.
        self._filter_original_count = len(jobs)
        self.log_panel.log("Filtering for: %s" % described)
        self.filter_worker = FilterWorker(jobs, anthropic_api_key=anthropic_key,
                                          search_title=chosen.get('search_title'),
                                          search_level=chosen.get('search_level'),
                                          search_work_mode=chosen.get('search_work_mode'),
                                          search_countries=chosen.get('countries'),
                                          search_cities=chosen.get('cities'),
                                          date_range=chosen.get('date_range'),
                                          categories=chosen.get('categories'),
                                          sponsorship=chosen.get('sponsorship'),
                                          min_match_percent=chosen.get('min_match_percent'),
                                          fields=chosen.get('fields'))
        self.filter_worker.progress.connect(self._on_progress_log)
        self.filter_worker.finished_ok.connect(self._on_filter_finished)
        self.filter_worker.failed.connect(self._on_filter_failed)
        self.filter_worker.start()

    def _on_filter_finished(self, kept: list, removed: int, claude_flagged: list,
                            theses: list, internships: list):
        self.jobs_page.set_searching(False)

        final_kept = kept
        if claude_flagged:
            dialog = ClaudeReviewDialog(claude_flagged, self)
            if dialog.exec() == ClaudeReviewDialog.Accepted:
                # Real bug fixed here: this used to be built as
                # `{item['job'].get('id') for … if … not in keep_ids}`, so a flagged job
                # with no id put None into the set -- and the filter below then removed
                # EVERY id-less job, including ones Claude never flagged. Requiring a
                # truthy id means a missing one can never match anything.
                remove_ids = set()
                for item in claude_flagged:
                    job_id = item['job'].get('id')
                    if job_id and job_id not in dialog.keep_ids:
                        remove_ids.add(job_id)
                # Records the override on the job itself, so the cached DROP verdict
                # doesn't re-flag this exact listing on every future Filter run -- see
                # reapply_filters' claude_screen_user_kept check. Without this, keeping a
                # flagged listing had to be re-done, by hand, forever.
                # A listing flagged by part two (the résumé match) records its own override,
                # so keeping it does not also silence a later part-one verdict, and the
                # reverse.
                for item in claude_flagged:
                    if item['job'].get('id') in dialog.keep_ids:
                        override = ('resume_match_user_kept' if item.get('part') == 'resume'
                                    else 'claude_screen_user_kept')
                        item['job'][override] = True
                        # And the "why this was removed" note comes off now, not at the next
                        # Filter run. It is no longer true the moment the user overrules it, and
                        # in between he can apply to this listing -- add_application copies
                        # the description into the record, so the note would be filed against
                        # a job he applied to.
                        clear_drop_note(item['job'])
                final_kept = [j for j in kept if j.get('id') not in remove_ids]
                self.log_panel.log(
                    f"Claude review: removed {len(remove_ids)} flagged listing(s), "
                    f"kept {len(dialog.keep_ids)} despite being flagged.",
                    level='success',
                )
            else:
                self.log_panel.log("Claude review cancelled — kept every flagged listing.")

        # The Job module's count is reported first and on its own, before the other two
        # modules are folded in -- otherwise "removed N" silently changes meaning the moment
        # a thesis is added back, and that number is the one the user reads to check the Job
        # filter still does what it did.
        total_removed = self._filter_original_count - len(final_kept)
        self.log_panel.log(f"Filter re-applied — removed {total_removed} listing(s), {len(final_kept)} remain.")

        # One Level at a time now, so one module runs and its survivors ARE `kept`. These two
        # lists stay in the signal for the moment where all three ran at once; anything in
        # them is merged the way it always was, and normally they are empty.
        for name, found in (('Thesis', theses), ('Internship', internships)):
            if not found:
                continue
            seen = {str(j.get('id') or j.get('url') or '') for j in final_kept}
            added = [j for j in found
                     if str(j.get('id') or j.get('url') or '') not in seen
                     or not (j.get('id') or j.get('url'))]
            final_kept = final_kept + added
            self.log_panel.log(
                f"{name} — {len(found)} listing(s) found, {len(added)} of them new.",
                level='success',
            )

        storage.save_jobs(final_kept)
        self.jobs_page.show_jobs(final_kept)
        # Only now: the signature stands for "jobs.json holds the answer to these choices",
        # and until this line it did not. Written after the review dialog too, so a run where
        # The user removed flagged listings by hand is remembered as it ended, not as it began.
        pending = getattr(self, '_pending_filter', None)
        if pending:
            storage.save_filter_state(pending['signature'], pending['choices'],
                                      pending['described'], len(final_kept))
            self._pending_filter = None

    def _on_filter_failed(self, message: str):
        self.jobs_page.set_searching(False)
        # A failed run leaves jobs.json holding whatever the previous one produced, so any
        # stored signature is now a promise about the wrong data. Forgetting it costs one
        # re-filter; keeping it would show a stale answer as if it were current.
        self._pending_filter = None
        storage.clear_filter_state()
        self.log_panel.log(f"Filter FAILED: {message}", level='error')
        QMessageBox.critical(self, "Filter failed", message)

    def handle_export(self):
        default_path = str(Path.home() / 'Downloads' / 'RoleHound_Export.xlsx')
        chosen_path, _ = QFileDialog.getSaveFileName(
            self, "Choose where to save the export", default_path, "Excel files (*.xlsx)"
        )
        if not chosen_path:
            return
        try:
            jobs_path, apps_path = storage.export_excels(chosen_path)
        except Exception as e:
            self.log_panel.log(f"Export FAILED: {e}", level='error')
            QMessageBox.critical(self, "Export failed", str(e))
            return
        self.log_panel.log(f"Exported: {jobs_path} and {apps_path}")
        QMessageBox.information(
            self, "Export complete",
            f"Saved:\n{jobs_path}\n{apps_path}",
        )

    def closeEvent(self, event):
        # Both workers are asked to stop BEFORE being waited on. Real bug fixed here for
        # the Filter one: it had no cancel mechanism at all, so this just waited 2
        # seconds on a run that could have hundreds of Claude calls left, then closed
        # anyway -- leaving a live QThread running into interpreter shutdown. It now
        # stops between listings, so the wait usually succeeds.
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
        if self.filter_worker and self.filter_worker.isRunning():
            self.filter_worker.request_cancel()
        if self.worker and self.worker.isRunning():
            self.worker.wait(5000)
        if self.filter_worker and self.filter_worker.isRunning():
            self.filter_worker.wait(5000)
        event.accept()
