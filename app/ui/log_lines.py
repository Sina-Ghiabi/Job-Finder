# -*- coding: utf-8 -*-
"""Turning a progress message into a line in the Log.

The pipeline reports what it is doing as plain strings on a callback -- "PLATFORM_START:
Indeed", "GLOG:pattern|info|...", "FILTER_STEP_DONE:dedup|...|476 removed". Something has to
know that each of those becomes a heading, or an indented result under a heading, or a green
line that replaces an amber one in place. That knowledge is here, and it is the only thing
here.

It used to be forty-four methods on MainWindow, which made a window class two thirds
formatter. They moved unchanged: they never read the window's state, only the Log panel they
write to and a counter for the one-shot lines that must never collapse onto each other.
"""
from __future__ import annotations


# How much of a failed pre-flight probe's raw error message goes into a single Log
# line. The full text still reaches PreflightProblemsDialog, which has room for it.
_PREFLIGHT_REASON_MAX_CHARS = 120


def _format_cost(raw: str) -> str:
    """Formats a real usageTotalUsd value (passed through progress_cb as a plain str,
    since it may be None when Apify didn't report one) as '$X.XX' -- falls back to
    '$0.00' rather than showing the literal 'None' if the value is missing."""
    try:
        return f"${float(raw):.2f}"
    except (TypeError, ValueError):
        return "$0.00"


class LogLines:
    """Renders progress messages into a LogPanel.

    One instance per window, holding the panel it writes to. `_glog_seq` gives every
    generic status line a key of its own -- without it, two lines logged under the same
    group would overwrite each other rather than stack.
    """

    def __init__(self, log_panel):
        self.log_panel = log_panel
        self._glog_seq = 0

    def _log_token_check_start(self, message: str):
        self.log_panel.log('Token Check:')

    def _log_token_check_item(self, message: str):
        # Keyed (not plain log()) so the Apify credit line can be refreshed in
        # place every ~10s for the rest of the search (see run_search's
        # _poll_apify_credit) instead of stacking a new line each time -- keyed by
        # the part of the label before ' - ' (e.g. 'Apify Token'), which stays
        # fixed even though the $ amount after it changes on every refresh.
        label, status = message[len('TOKEN_CHECK_ITEM:'):].split('|', 1)
        key = f"token_check:{label.split(' - ')[0]}"
        if status == 'OK':
            self.log_panel.log_keyed(key, f"    → {label} | OK", level='success')
        elif status == 'SKIPPED':
            self.log_panel.log_keyed(key, f"    → {label} | Not Configured")
        else:
            self.log_panel.log_keyed(key, f"    → {label} | Failed", level='error')

    def _log_health_start(self, message: str):
        # A top-level timer, not nested under a platform: the health check is its own
        # action, run on its own, and has no search around it to belong to.
        self.log_panel.start_timer_line('health', 'Health Check')

    def _log_health_item(self, message: str):
        # name|OK  or  name|FAILED|reason
        parts = message[len('HEALTH_ITEM:'):].split('|')
        name = parts[0]
        status = parts[1] if len(parts) > 1 else 'OK'
        reason = parts[2] if len(parts) > 2 else ''
        self._glog_seq += 1
        if status == 'OK':
            # An OK line can still carry something worth reading -- what is left to spend,
            # what a search costs. That detail used to be dropped on the floor here, which
            # is why the budget lines arrived in the Log as two bare "OK"s.
            text = f"    → {name} | OK"
            if reason:
                text += f" ({reason[:_PREFLIGHT_REASON_MAX_CHARS]})"
            self.log_panel.log_keyed(f'health:{self._glog_seq}', text,
                                     level='success', group='health')
        elif status == 'OFF':
            # Same as the pre-flight's own OFF line: a source with no key is switched off,
            # not broken, and amber says that where red would not.
            text = f"    → {name} | Switched off"
            if reason:
                text += f" ({reason[:_PREFLIGHT_REASON_MAX_CHARS]})"
            self.log_panel.log_keyed(f'health:{self._glog_seq}', text,
                                     level='warning', group='health')
        else:
            text = f"    → {name} | FAILED"
            if reason:
                text += f" ({reason[:_PREFLIGHT_REASON_MAX_CHARS]})"
            self.log_panel.log_keyed(f'health:{self._glog_seq}', text,
                                     level='error', group='health')

    def _log_health_end(self, message: str):
        status, _, detail = message[len('HEALTH_END:'):].partition('|')
        level = 'success' if status == 'OK' else 'error'
        self.log_panel.stop_timer_line('health', 'Health Check',
                                       suffix=f" — {detail}", level=level)

    def _log_preflight_start(self, message: str):
        # Nested under the outer 'Google' header (started before this fires -- see
        # run_search) so the user sees ONE continuous Google timer covering the whole
        # phase, with Pre-API Check as its own nested, independently-ticking
        # sub-timer underneath it.
        self.log_panel.start_timer_line('preflight', '    Pre-API Check', group='platform:Google')

    def _log_preflight_item(self, message: str):
        # name|status|reason|relevant_countries -- relevant_countries (dash-joined,
        # e.g. "Sweden-Norway") is only present for the direct-API sources (each
        # one is only ever checked for the countries/cities that actually made it
        # relevant this run -- see _preflight_check_api_sources), not for the
        # Google Search actor check itself, which isn't tied to one API or country.
        # rsplit for the trailing countries field, then split for the leading
        # name/status: the `reason` in between is a raw str(e) from a failed probe
        # and is the ONLY field that can contain a '|' of its own. Splitting from
        # both ends means such a reason can never push its remainder into the
        # countries slot. (Verified that real requests/urllib3 messages don't
        # currently contain one -- this makes it structurally impossible rather
        # than relying on that staying true.)
        payload = message[len('PREFLIGHT_ITEM:'):]
        head, _, countries_raw = payload.rpartition('|')
        if not head:  # no trailing countries field at all
            head, countries_raw = payload, ''
        name, _, rest = head.partition('|')
        status, _, reason = rest.partition('|')
        # A failed probe's message can be 300+ characters (a real DNS failure
        # measured 310), which wraps across several visual lines in the Log. The
        # dialog still shows the whole thing; the Log line gets the readable part.
        if len(reason) > _PREFLIGHT_REASON_MAX_CHARS:
            reason = reason[:_PREFLIGHT_REASON_MAX_CHARS - 1].rstrip() + '…'
        countries = countries_raw.replace('-', ' - ') if countries_raw else ''
        prefix = f"API | {name}" if countries else name
        middle = f" | {countries}" if countries else ''
        key = f'preflight_item:{name}'
        if status == 'OK':
            self.log_panel.log_keyed(key, f"        → {prefix}{middle} | OK", level='success', group='preflight')
        elif status == 'OFF':
            # A source with no key is not a fault, and putting it in red beside real
            # failures made a healthy run read as a broken one. Amber, and it says what is
            # actually true: this source contributes nothing to this search.
            detail = f" ({reason})" if reason else ''
            self.log_panel.log_keyed(
                key, f"        → {prefix}{middle} | Switched off{detail}",
                level='warning', group='preflight',
            )
        else:
            detail = f" ({reason})" if reason else ''
            self.log_panel.log_keyed(
                key, f"        → {prefix}{middle} | Failed{detail}", level='error', group='preflight',
            )

    def _log_preflight_end(self, message: str):
        # status|locations (dash-joined countries/cities this check covered) --
        # replaced the old (passed/checked) count per the user's ask: the suffix now
        # names what was checked, not how many items passed. Pass/fail still
        # decides the line's color exactly as before.
        status, locations = message[len('PREFLIGHT_END:'):].split('|', 1)
        location_list = locations.replace('-', ' - ') if locations else ''
        suffix = f' — Completed for {location_list}' if location_list else ' — Completed'
        if status == 'OK':
            self.log_panel.stop_timer_line('preflight', '    Pre-API Check', suffix=suffix, level='success')
        else:
            self.log_panel.stop_timer_line(
                'preflight', '    Pre-API Check', suffix=f'{suffix} (some checks failed)', level='error',
            )

    def _log_known_sites_start(self, message: str):
        # Real, live-ticking timer -- started right as the one combined Google
        # Search actor call that produces the known-site results begins (it can
        # take a minute or more). The user asked for this directly: with only a
        # summary line appearing once everything was already done, there was no
        # way to tell this stage had actually started instead of the app being
        # stuck.
        self.log_panel.start_timer_line('known_sites', '    Known Websites', group='platform:Google')

    def _log_known_sites_header(self, message: str):
        # Stops the timer above with the real usageTotalUsd from that same call --
        # always fires (even with zero known-site results) so the timer never ticks
        # forever. The per-site job-count lines below are only added when there's
        # something to show.
        cost = message[len('KNOWN_SITES_HEADER:'):]
        self.log_panel.stop_timer_line(
            'known_sites', '    Known Websites', suffix=f' — Succeed  {_format_cost(cost)}', level='success',
        )

    def _log_known_site_result(self, message: str):
        # domain|count -- logged once the whole Google Actor call is done (no live
        # per-site progress or per-site cost is possible: every known site for a
        # location shares one combined query in a single batched Apify call, see
        # run_search's own comment on this). Only sites that returned something are
        # shown.
        domain, count = message[len('KNOWN_SITE_RESULT:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'known_site:{domain}', f"        → {domain} | Succeed | {count} job(s) found",
            level='success', group='known_sites',
        )

    def _log_startup_sites_start(self, message: str):
        # Same combined actor call as Known Websites -- its own section, per
        # The user's ask, so startup/scaleup-specific boards are visually separate
        # from the general-purpose ones.
        self.log_panel.start_timer_line('startup_sites', '    Startup Websites Search', group='platform:Google')

    def _log_startup_sites_header(self, message: str):
        cost = message[len('STARTUP_SITES_HEADER:'):]
        self.log_panel.stop_timer_line(
            'startup_sites', '    Startup Websites Search', suffix=f' — Succeed  {_format_cost(cost)}',
            level='success',
        )

    def _log_startup_site_result(self, message: str):
        domain, count = message[len('STARTUP_SITE_RESULT:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'startup_site:{domain}', f"        → {domain} | Succeed | {count} job(s) found",
            level='success', group='startup_sites',
        )

    def _log_deep_crawl_start(self, message: str):
        self.log_panel.start_timer_line('deep_crawl', '    Deep-Crawl', group='platform:Google')

    def _log_deep_crawl_header(self, message: str):
        status, cost = message[len('DEEP_CRAWL_HEADER:'):].split('|', 1)
        if status == 'SUCCESS':
            self.log_panel.stop_timer_line(
                'deep_crawl', '    Deep-Crawl', suffix=f' — Succeed  {_format_cost(cost)}', level='success',
            )
        else:
            self.log_panel.stop_timer_line('deep_crawl', '    Deep-Crawl', suffix=' — Failed', level='error')

    def _log_deep_crawl_site_result(self, message: str):
        domain, count = message[len('DEEP_CRAWL_SITE_RESULT:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'deep_crawl_site:{domain}', f"        → {domain} | Succeed | {count} new page(s) found",
            level='success', group='deep_crawl',
        )

    def _log_direct_site_start(self, message: str):
        self.log_panel.start_timer_line('direct_site', '    Direct Site Search', group='platform:Google')

    def _log_direct_site_header(self, message: str):
        status, cost = message[len('DIRECT_SITE_HEADER:'):].split('|', 1)
        if status == 'SUCCESS':
            self.log_panel.stop_timer_line(
                'direct_site', '    Direct Site Search', suffix=f' — Succeed  {_format_cost(cost)}', level='success',
            )
        else:
            self.log_panel.stop_timer_line('direct_site', '    Direct Site Search', suffix=' — Failed', level='error')

    def _log_google_stage_failed(self, message: str):
        # Stops any Known Websites/Deep-Crawl/Direct Site Search Running timer that
        # was started but never reached its own normal stop line, since something
        # failed somewhere inside the whole Google stage -- without this, a timer
        # started right before the failure would tick forever with no way to know
        # it actually stopped. stop_timer_line is a safe no-op for a key that was
        # never started (or already stopped), so all three can just be called.
        # Real bug fixed here: this list used to cover only the four INNER timers,
        # so a Google-stage failure left 'preflight', 'direct_api' and
        # 'browser_sites' ticking forever (the outer 'platform:Google' header is now
        # closed by run_search's own finally, see PLATFORM_END:Google).
        for key, label in (
            ('preflight', '    Pre-API Check'),
            ('known_sites', '    Known Websites'),
            ('startup_sites', '    Startup Websites Search'),
            ('deep_crawl', '    Deep-Crawl'),
            ('direct_site', '    Direct Site Search'),
            ('direct_api', '    Direct API Search'),
            ('browser_sites', '    Browser-Only Sites'),
        ):
            self.log_panel.stop_timer_line(key, label, suffix=' — Failed', level='error')

    def _log_filter_start(self, message: str):
        # Same nested Object pattern as the Google section: one header timer
        # ('Filter'), with each of its 7 steps as its own nested, independently
        # ticking Running -> Finished timer underneath -- The user asked for exactly
        # this shape here too, simple and readable at a glance.
        self.log_panel.start_timer_line('filter', 'Filter')

    def _log_filter_end(self, message: str):
        self.log_panel.stop_timer_line('filter', 'Filter', suffix=' — Completed', level='success')

    def _log_filter_step_start(self, message: str):
        key, label = message[len('FILTER_STEP_START:'):].split('|', 1)
        self.log_panel.start_timer_line(f'filter_step:{key}', f'    {label}', group='filter')

    def _log_filter_step_item(self, message: str):
        # One rule/check name per line, nested under its own step, marked
        # "Checked" (green) -- The user asked for the actual rule names to be visible
        # in the Log itself, not just each step's own single summary count. Always
        # emitted right before that step's own FILTER_STEP_DONE, so every rule
        # listed here genuinely already ran against every listing by this point.
        key, label = message[len('FILTER_STEP_ITEM:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'filter_item:{key}:{label}', f"        → {label} | Checked",
            level='success', group=f'filter_step:{key}',
        )

    def _log_filter_step_done(self, message: str):
        key, label, detail = message[len('FILTER_STEP_DONE:'):].split('|', 2)
        suffix = f' — Finished ({detail})' if detail else ' — Finished'
        self.log_panel.stop_timer_line(f'filter_step:{key}', f'    {label}', suffix=suffix, level='success')

    def _log_platform_start(self, message: str):
        platform = message[len('PLATFORM_START:'):]
        self.log_panel.start_timer_line(f'platform:{platform}', platform)

    def _log_platform_end(self, message: str):
        platform = message[len('PLATFORM_END:'):]
        self.log_panel.stop_timer_line(f'platform:{platform}', platform, suffix=' — Completed', level='success')

    def _log_location_start(self, message: str):
        platform, location = message[len('LOCATION_START:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'location:{platform}:{location}', f"    → {location} | Running", group=f'platform:{platform}',
        )

    def _log_glog(self, message: str):
        # group|level|text -- a generic, one-shot, nested status line: real bug
        # fixed here. Direct Site Search / Direct API Search / Browser-Only Sites /
        # sponsor-list-load lines used to be logged through the plain
        # ERROR:/SUCCESS:/WARNING: convention below, which routes to a flat,
        # unindented LogPanel.log() call always appended at the absolute end of the
        # document -- so they never actually appeared nested under their own
        # section (e.g. "Direct Site Search") the way Known Websites/Startup
        # Websites/Deep-Crawl's own per-site result lines already did. Each such
        # line now gets its own unique key (never updated in place, just inserted
        # once, keeping the group's insertion-order semantics) so it can be
        # properly grouped/indented via log_keyed's `group` param instead.
        group, level, text = message[len('GLOG:'):].split('|', 2)
        self._glog_seq += 1
        self.log_panel.log_keyed(f'glog:{self._glog_seq}', f"        → {text}", level=level, group=group)

    def _log_pattern_crawl_start(self, message: str):
        # The second, small crawl that goes back to the sites just learned. Nested under
        # Google with the other additive stages.
        self.log_panel.start_timer_line('pattern_crawl', '    Collecting From New Sites',
                                        group='platform:Google')

    def _log_pattern_crawl_end(self, message: str):
        self.log_panel.stop_timer_line('pattern_crawl', 'Completed')

    def _log_pattern_crawl_site_result(self, message: str):
        domain, count = message[len('PATTERN_CRAWL_SITE_RESULT:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'pattern_crawl:{domain}',
            f'        → {domain} | {count} job(s) collected',
            level='success', group='pattern_crawl')

    def _log_pattern_start(self, message: str):
        # Nested under Google like the other additive stages. This is the step that used
        # to be a manual job: finding, for a site RoleHound cannot read, how it builds its
        # job links.
        self.log_panel.start_timer_line('pattern', '    Learning New Sites',
                                        group='platform:Google')

    def _log_pattern_end(self, message: str):
        self.log_panel.stop_timer_line('pattern', 'Completed')

    def _log_pattern_site_result(self, message: str):
        domain, count = message[len('PATTERN_SITE_RESULT:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'pattern_site:{domain}',
            f'        → {domain} | learned how it links its jobs ({count} pattern(s))',
            level='success', group='pattern')

    def _log_enrich_start(self, message: str):
        # Nested under the same Google header as the other additive stages, with a live
        # timer -- fetching a few hundred pages is quick but not instant, and a silent
        # Log during it reads as a hang.
        self.log_panel.start_timer_line('enrich', '    Fetching Missing Descriptions',
                                        group='platform:Google')

    def _log_enrich_end(self, message: str):
        self.log_panel.stop_timer_line('enrich', 'Completed')

    def _log_enrich_site_result(self, message: str):
        domain, count = message[len('ENRICH_SITE_RESULT:'):].split('|', 1)
        self.log_panel.log_keyed(
            f'enrich_site:{domain}',
            f'        → {domain} | {count} description(s) recovered',
            level='success', group='enrich')

    def _log_direct_api_start(self, message: str):
        self.log_panel.start_timer_line('direct_api', '    Direct API Search', group='platform:Google')

    def _log_direct_api_end(self, message: str):
        self.log_panel.stop_timer_line('direct_api', '    Direct API Search', suffix=' — Completed', level='success')

    def _log_browser_sites_start(self, message: str):
        self.log_panel.start_timer_line('browser_sites', '    Browser-Only Sites', group='platform:Google')

    def _log_browser_sites_end(self, message: str):
        self.log_panel.stop_timer_line('browser_sites', '    Browser-Only Sites', suffix=' — Completed', level='success')

    def _log_location_done(self, message: str):
        platform, location, status, cost = message[len('LOCATION_DONE:'):].split('|', 3)
        cost_suffix = f" | {cost}$" if cost else ''
        group = f'platform:{platform}'
        if status == 'SUCCESS':
            self.log_panel.log_keyed(
                f'location:{platform}:{location}', f"    → {location} | Succeed{cost_suffix}",
                level='success', group=group,
            )
        else:
            self.log_panel.log_keyed(
                f'location:{platform}:{location}', f"    → {location} | Failed{cost_suffix}",
                level='error', group=group,
            )
