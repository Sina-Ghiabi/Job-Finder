from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QScrollArea, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app import pipeline, storage
from app.pipeline import actor_filters, sources_enabled


class SetupWizard(QDialog):
    """Startup dialog: Apify token, optional per-search result limit, and how far back
    each platform should search (each platform has its own date-filter options)."""

    def __init__(self, saved_settings: dict, parent=None):
        super().__init__(parent)
        # Kept so _build_result_settings can start from a COPY of everything already
        # saved and only overwrite the fields this wizard actually has UI for --
        # real bug fixed here: it used to build self.result_settings as a brand-new
        # dict from scratch, which silently deleted every setting the wizard has no
        # field for (the 16 Jooble country API keys -- each with a lifetime-capped 500
        # -request budget -- reed_uk_api_key, francetravail_client_id/secret) the
        # moment Save or Start Search was clicked, even
        # ones just entered live via the pre-flight problems dialog's "fix" fields.
        self._saved_settings = saved_settings
        self.setWindowTitle("RoleHound — Search Setup")
        self.setMinimumWidth(480)
        self.resize(480, 720)

        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(0)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Everything except the bottom Cancel/Start Search buttons lives inside a
        # scroll area, so on shorter screens the buttons are always reachable instead
        # of being pushed off the bottom of the dialog.
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setStyleSheet("background-color: #141a2b; border: none;")
        outer_layout.addWidget(scroll_area, stretch=1)

        content = QWidget()
        content.setStyleSheet("background-color: #141a2b;")
        scroll_area.setWidget(content)

        # None until Save/Start Search validates and builds it -- see
        # _build_result_settings, which returns False and leaves this None if the
        # selection is empty.
        self.result_settings: dict | None = None

        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 16)

        self._build_credentials_section(layout, saved_settings)

        # First, because it is the first question: what are we looking for at all?
        self._build_kind_section(layout, saved_settings)

        self._build_date_section(layout, saved_settings)

        self._build_platform_section(layout, saved_settings)

        # Straight after the platform checklist, because it is the same question one level
        # down: having chosen who to ask, what do we ask each of them for?
        self._build_actor_filter_section(layout, saved_settings)

        # After the panel exists, because the Remote / Not Remote choice SETS two of its dropdowns.
        self._wire_work_mode(saved_settings)

        self._build_country_section(layout, saved_settings)

        layout.addWidget(self._build_api_keys_section(saved_settings))

        self._build_button_bar(outer_layout)

    def _build_credentials_section(self, layout, saved_settings: dict):
        """The Apify token, the optional Anthropic key, and the per-search result limit."""
        title = QLabel("Configure your search")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel("These settings are used every time you start a new search.")
        hint.setObjectName("HintLabel")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)

        self.token_input = QLineEdit(saved_settings.get('apify_token', ''))
        self.token_input.setPlaceholderText("apify_api_...")
        self.token_input.setEchoMode(QLineEdit.Password)
        form.addRow("Apify API token:", self.token_input)

        show_token = QCheckBox("Show token")
        show_token.toggled.connect(
            lambda checked: self.token_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        form.addRow("", show_token)

        self.anthropic_key_input = QLineEdit(saved_settings.get('anthropic_api_key', ''))
        self.anthropic_key_input.setPlaceholderText("sk-ant-... (optional)")
        self.anthropic_key_input.setEchoMode(QLineEdit.Password)
        form.addRow("Anthropic API key:", self.anthropic_key_input)


        show_anthropic_key = QCheckBox("Show key")
        show_anthropic_key.toggled.connect(
            lambda checked: self.anthropic_key_input.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        form.addRow("", show_anthropic_key)

        anthropic_hint = QLabel("Optional — lets the Filter button ask Claude to double-check every listing as a final pass.")
        anthropic_hint.setObjectName("HintLabel")
        anthropic_hint.setWordWrap(True)
        form.addRow("", anthropic_hint)

        # THE RESULT CAP IS GONE, ON INSTRUCTION
        #
        # There used to be a checkbox and a number here. Sina's rule, given twice: "هیچ Limit
        # ای نباید در پیدا کردن آگهی باشد" and then, when the cost of removing it came up,
        # "بالا رفتن تعداد نتایج هیچ اشکالی ندارد / سقف نتایج رو هم بردار اصلا / هرچی بیشتر
        # بهتر". A control whose only correct setting is "off" is a way to set it wrongly by
        # accident, which is what happened: the cap sat at 100 and both LinkedIn and Glassdoor
        # returned exactly 100 listings on a German run, each with more to give and neither
        # saying so.
        #
        # Every search now asks for everything (NO_RESULT_LIMIT in search/runner.py).
        limit_note = QLabel('Every search returns everything it finds — there is no result '
                           'limit.')
        limit_note.setObjectName("HintLabel")
        limit_note.setWordWrap(True)
        form.addRow("Results:", limit_note)

        layout.addLayout(form)

    def _build_kind_section(self, layout, saved_settings: dict):
        """What to search for: the résumé, one job title, one Level, Remote or Not Remote.

        This replaced three checkboxes -- Jobs, Internships, Theses -- and a field written into
        the code. Sina's design:

          * the résumé, PDF or Word and nothing else: Claude screens with the Level's profile,
            then scores what is left against it -- "چند درصد ... با رزومه ای که آپلود کردی
            همخونی داره";
          * one job title, "مثلا Data Engineer", from which every query and every title check
            is built;
          * one Level, exactly one: Thesis, Internship, Entry, Junior, Mid or Senior -- so Job
            and Internship are always separate runs;
          * Remote, which is every rule exactly as it was, or Not Remote, which keeps the
            other answer.
        """
        heading = QLabel("What are you looking for?")
        heading.setObjectName("SectionTitle")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)

        # The résumé used to be chosen here. It now lives in the Filter window, because that
        # is where it is used: a search collects postings and never opens the résumé, while
        # the Filter is what sends each survivor to Claude to be scored against it. Choosing
        # it next to the match slider means a wrong résumé is caught before a run pays to
        # score against it -- see FilterDialog._resume_box.

        # --- job title --------------------------------------------------------------------
        self.title_input = QLineEdit(saved_settings.get('search_title')
                                     or pipeline.DEFAULT_SEARCH_TITLE)
        self.title_input.setPlaceholderText("e.g. Data Engineer")
        form.addRow("Job title:", self.title_input)
        self.title_forms_label = QLabel()
        self.title_forms_label.setObjectName("FieldHint")
        self.title_forms_label.setWordWrap(True)

        def _show_forms(text):
            forms = pipeline.title_forms(text)
            self.title_forms_label.setText("Searched as: " + " · ".join(forms))

        self.title_input.textChanged.connect(_show_forms)
        _show_forms(self.title_input.text())
        form.addRow("", self.title_forms_label)

        # --- Type -------------------------------------------------------------------------
        # Any / Thesis / Internship, and nothing about seniority. Sina: "اون بخش Seniority رو از
        # Search حذف کن ... Thesis میگرده دنبال Thesis، Internship میگرده دنبال Internship، و Any
        # میگرده دنبال هر چیزی که میتونه پیدا کنه". Seniority is a column in the table now, picked
        # there; asking an actor about it was measured to add one to three rows (Document T-19).
        # Stored under the old `search_level` key so every reader of it keeps working, and an old
        # value (junior, mid, ...) opens here as Any.
        self.level_combo = QComboBox()
        for key in pipeline.SEARCH_TYPES:
            self.level_combo.addItem(key.title(), key)
        saved_type = pipeline.clean_search_type(saved_settings.get('search_level'))
        self.level_combo.setCurrentIndex(max(0, self.level_combo.findData(saved_type)))
        form.addRow("Type:", self.level_combo)

        # --- Remote / Not Remote ----------------------------------------------------------
        self.work_mode_combo = QComboBox()
        self.work_mode_combo.addItem("Remote", 'remote')
        self.work_mode_combo.addItem("Any", 'any')
        # `search_workplace` is this row's own saved value. Settings saved before it existed
        # carry only the Filter's `search_work_mode`: Remote there is Remote here, anything
        # else (Not Remote) is Any.
        saved_mode = saved_settings.get('search_workplace')
        if saved_mode not in ('remote', 'any'):
            saved_mode = 'remote' if pipeline.clean_work_mode(
                saved_settings.get('search_work_mode')) == 'remote' else 'any'
        self.work_mode_combo.setCurrentIndex(max(0, self.work_mode_combo.findData(saved_mode)))
        form.addRow("Remote / Any:", self.work_mode_combo)

        layout.addLayout(form)

    # ----------------------------------------------------- Remote / Not Remote and the panel --
    def _wire_work_mode(self, saved_settings: dict) -> None:
        """Type locks Remote for Thesis and Internship; Remote / Not Remote sets the dropdowns.

        Sina: "اگر من Thesis و Internship انتخاب کردم کلا Remote غیر قابل کلیک بشه". A thesis or an
        internship is almost never remote, and measured -- asked for remote-only, LinkedIn and
        Glassdoor returned nothing for either (Document T-19). So choosing either one disables the
        Remote entry and moves the choice to Not Remote; going back to Any gives the entry back
        and puts back what was chosen before.

        And: "بعد هر انتخابی که کردم اونجا مستقیما در مقدار پارامتر مربوطه به اون Actor قرار داده
        بشه". The two actor parameters that mean "remote or not" -- LinkedIn's `remote` and
        Glassdoor's `remoteWorkType` -- are SET by this choice, so the panel always shows what
        will be sent. Changing either afterwards is his, and is sent as chosen.
        """
        self._mode_before_lock = None
        saved_panel = (saved_settings.get(actor_filters.SETTINGS_KEY) or {})
        # A panel value he saved explicitly is his and is left alone; one that was never saved
        # is derived from the mode, so opening the window on Not Remote does not show a Remote
        # dropdown that nothing ever set.
        explicit = {(platform, key) for platform, values in saved_panel.items()
                    if isinstance(values, dict) for key in values}
        if any(pair not in explicit for pair in (('linkedin', 'remote'),
                                                 ('glassdoor', 'remoteWorkType'),
                                                 ('indeed', 'location'))):
            self._sync_panels_to_mode(only_missing=explicit)
        self.level_combo.currentIndexChanged.connect(self._on_type_changed)
        self.work_mode_combo.currentIndexChanged.connect(lambda _i: self._sync_panels_to_mode())
        if self._type_locks_remote():
            self._lock_remote(initial=True)

    def _type_locks_remote(self) -> bool:
        return self.selected_level() in ('thesis', 'internship')

    def _lock_remote(self, initial: bool = False) -> None:
        """Remote greyed out, and Not Remote chosen."""
        if not initial and self._mode_before_lock is None:
            self._mode_before_lock = self.work_mode_combo.currentData()
        entry = self.work_mode_combo.model().item(self.work_mode_combo.findData('remote'))
        entry.setEnabled(False)
        self.work_mode_combo.setItemData(self.work_mode_combo.findData('remote'),
                                         'Not available for Thesis and Internship',
                                         Qt.ToolTipRole)
        self.work_mode_combo.setCurrentIndex(self.work_mode_combo.findData('any'))
        self._sync_panels_to_mode()

    def _unlock_remote(self) -> None:
        entry = self.work_mode_combo.model().item(self.work_mode_combo.findData('remote'))
        entry.setEnabled(True)
        self.work_mode_combo.setItemData(self.work_mode_combo.findData('remote'), None,
                                         Qt.ToolTipRole)
        if self._mode_before_lock is not None:
            self.work_mode_combo.setCurrentIndex(
                max(0, self.work_mode_combo.findData(self._mode_before_lock)))
            self._mode_before_lock = None
        self._sync_panels_to_mode()

    def _on_type_changed(self, _index: int) -> None:
        if self._type_locks_remote():
            self._lock_remote()
        else:
            self._unlock_remote()

    def _sync_panels_to_mode(self, only_missing=None) -> None:
        """Remote -> LinkedIn `remote`=remote and Glassdoor `remoteWorkType`=Yes; Any -> LinkedIn
        `remote`=Any ('') and Glassdoor No. Indeed has no such parameter. With `only_missing`, a dropdown he saved explicitly is not touched."""
        remote = self.selected_workplace() == 'remote'
        targets = (('linkedin', 'remote', 'remote' if remote else ''),
                   ('glassdoor', 'remoteWorkType', True if remote else False),
                   ('indeed', 'location', 'remote' if remote else ''))
        for platform, key, value in targets:
            if only_missing is not None and (platform, key) in only_missing:
                continue
            combo = getattr(self, 'actor_filter_inputs', {}).get(platform, {}).get(key)
            if combo is not None:
                combo.setCurrentIndex(max(0, combo.findData(value)))

    def selected_level(self) -> str:
        """'any', 'thesis' or 'internship' -- saved as `search_level`."""
        return pipeline.clean_search_type(self.level_combo.currentData())

    def selected_workplace(self) -> str:
        """'remote' or 'any' -- what the actors are asked for."""
        return 'remote' if self.work_mode_combo.currentData() == 'remote' else 'any'

    def selected_work_mode(self) -> str:
        """The Filter's own Remote / Any, saved as `search_work_mode`: the same choice, so a
        search for Any is also judged as Any."""
        return self.selected_workplace()

    def selected_kinds(self) -> list:
        """What the chosen Type searches for: one kind, or all three for Any."""
        level = self.selected_level()
        return [level] if level in ('thesis', 'internship') else ['job', 'internship', 'thesis']

    def _build_date_section(self, layout, saved_settings: dict):
        """How far back to search. One choice, not three.

        It used to be one combo per platform, because each actor's own date filter takes
        different values -- and that is exactly what made it possible to pick something one
        platform does not have. "Last 30 days" is ordinary for Glassdoor and has never
        existed for Indeed, and choosing it cost a two-hour German search its entire Indeed
        leg.

        So Sina picks one range and `pipeline.date_settings_for` turns it into whatever each
        actor accepts. Where a platform cannot reach that far back it gets its own maximum,
        and the line underneath says so -- see pipeline.DATE_RANGES.
        """
        date_title = QLabel("How far back should the search go?")
        date_title.setObjectName("SectionTitle")
        layout.addWidget(date_title)

        date_form = QFormLayout()
        date_form.setSpacing(10)

        self.date_combo = QComboBox()
        self.date_combo.addItems(pipeline.DATE_RANGE_LABELS)
        self._select(self.date_combo,
                     saved_settings.get('date_range') or pipeline.DEFAULT_DATE_RANGE)
        date_form.addRow("Posted within:", self.date_combo)
        layout.addLayout(date_form)

        # The shortfall, in words, for whichever range is selected. Never hidden: a platform
        # quietly searching a different period than the one chosen is how this went wrong.
        self.date_note = QLabel()
        self.date_note.setObjectName("FieldHint")
        self.date_note.setWordWrap(True)

        def _show_note():
            note = pipeline.date_range_note(self.date_combo.currentText())
            self.date_note.setText(note)
            self.date_note.setVisible(bool(note))

        self.date_combo.currentTextChanged.connect(lambda _t: _show_note())
        _show_note()
        layout.addWidget(self.date_note)

    def _build_platform_section(self, layout, saved_settings: dict):
        """Which platforms to run, and in what order -- a drag-to-reorder checklist."""
        actor_title = QLabel("Which platforms, and in what order?")
        actor_title.setObjectName("SectionTitle")
        layout.addWidget(actor_title)

        actor_hint = QLabel("Drag to reorder · uncheck to skip a platform entirely.")
        actor_hint.setObjectName("HintLabel")
        layout.addWidget(actor_hint)

        saved_order = saved_settings.get('actor_order') or pipeline.DEFAULT_ACTOR_ORDER
        saved_enabled = set(saved_settings.get('actor_order') or pipeline.DEFAULT_ACTOR_ORDER)
        # keep any platform missing from a saved order at the end (using ALL_PLATFORMS, not
        # just DEFAULT_ACTOR_ORDER, so a platform like 'google' -- opt-in, unchecked by
        # default -- still always shows up in the list instead of being invisible)
        ordered_platforms = list(saved_order) + [p for p in pipeline.ALL_PLATFORMS if p not in saved_order]

        self.actor_list = QListWidget()
        self.actor_list.setFixedHeight(110)
        self.actor_list.setDragDropMode(QListWidget.InternalMove)
        for platform in ordered_platforms:
            item = QListWidgetItem(pipeline.PLATFORM_LABELS[platform])
            item.setData(Qt.UserRole, platform)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if platform in saved_enabled else Qt.Unchecked)
            self.actor_list.addItem(item)
        layout.addWidget(self.actor_list)

        # The fifth switch. The four platforms are the checklist above; this is everything
        # else a search asks, as one box -- Sina's own shape for it: "فقط برای Google Indeed
        # Glassdoor LinkedIn API ها".
        self.source_checkboxes: dict[str, QCheckBox] = {}
        for source in sources_enabled.SOURCES:
            box = QCheckBox(source.label)
            box.setChecked(sources_enabled.is_enabled(saved_settings, source.key))
            box.setToolTip(source.hint)
            self.source_checkboxes[source.key] = box
            layout.addWidget(box)
            if source.hint:
                hint = QLabel(source.hint)
                hint.setObjectName("HintLabel")
                hint.setWordWrap(True)
                layout.addWidget(hint)

    def _selected_sources(self) -> dict:
        """Which actor-backed sources are ticked, in the shape is_enabled reads.

        Starts from the defaults so a key this window has no box for stays whatever the
        table says rather than vanishing -- the same reason _build_result_settings copies
        the saved settings instead of building a fresh dict.
        """
        picked = sources_enabled.defaults()
        for key, box in getattr(self, 'source_checkboxes', {}).items():
            picked[key] = box.isChecked()
        return picked

    def _build_actor_filter_section(self, layout, saved_settings: dict):
        """One box per platform, holding that platform's own filters and nothing else.

        Sina's words: "برای هر Actor بر اساس Field های همون Actor برام قرار بده و به صورت
        Dropdown که فقط انتخاب کنیم یا به صورت Checkbox" -- per actor, that actor's own
        fields, chosen rather than typed. And, after the testing: only the ones that work.

        Every control here is built from `actor_filters.FIELDS`, which is also what the
        request builders read. That is what makes "no room for a mistake" structural rather
        than careful: a filter cannot be shown without being sent, and cannot be sent
        without being shown. Nothing in that table was put there without being measured
        against the live actor, which is why LinkedIn's box is the short one -- its remote,
        seniority and sort parameters are accepted and silently dropped, so offering them
        would be a window that lies.
        """
        title = QLabel("What to ask each platform for")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        # No explanatory text anywhere in this panel -- Sina: "برای پارامتر های Actor ها توضیح
        # ننویس". The parameter's own name, and a dropdown in front of it. What each one was
        # measured to do is in Document T-6 / T-16 and in actor_filters.Field.hint, which the
        # window no longer shows.

        # {platform: {field key: the widget holding it}}, read back by _selected_actor_filters.
        self.actor_filter_inputs: dict[str, dict] = {}

        for platform in pipeline.ALL_PLATFORMS:
            fields = actor_filters.fields_for(platform)
            if not fields:
                # Google has no actor filters of its own -- it is driven entirely by the
                # queries built for it -- so it gets no box rather than an empty one.
                continue
            chosen = actor_filters.chosen_for(saved_settings, platform)
            # A plain widget with its own title, not a QGroupBox: in the dark theme the group
            # boxes had no frame and their titles were drawn half under the previous box's rows.
            box = QWidget()
            box.setProperty('actor_platform', platform)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 8, 0, 8)
            platform_title = QLabel(pipeline.PLATFORM_LABELS.get(platform, platform.capitalize()))
            platform_title.setObjectName("PlatformTitle")
            box_layout.addWidget(platform_title)
            form = QFormLayout()
            box_layout.addLayout(form)
            form.setSpacing(8)
            self.actor_filter_inputs[platform] = {}

            for field in fields:
                widget = self._actor_filter_widget(field, chosen.get(field.key))
                self.actor_filter_inputs[platform][field.key] = widget
                form.addRow(field.label, widget)
            layout.addWidget(box)

    @staticmethod
    def _actor_filter_widget(field, value):
        """The one control for one field: a dropdown, whatever the field's kind.

        Sina asked for a dropdown in front of every parameter, so a tick is a No / Yes list and
        a number is a list of sensible limits, and the FIELD says what to offer
        (Field.dropdown_options). The value stored is the one the actor is given, never the
        label -- the labels are prose and will be reworded.
        """
        combo = QComboBox()
        for option_value, option_label in field.dropdown_options(value):
            combo.addItem(option_label, option_value)
        at = combo.findData(value)
        if at < 0 and field.kind == actor_filters.FLAG:
            at = combo.findData(bool(value))
        combo.setCurrentIndex(at if at >= 0 else 0)
        return combo

    def _selected_actor_filters(self) -> dict:
        """What the boxes say, in the shape apply_to_request reads."""
        picked: dict[str, dict] = {}
        for platform, widgets in getattr(self, 'actor_filter_inputs', {}).items():
            values: dict = {}
            for field in actor_filters.fields_for(platform):
                widget = widgets.get(field.key)
                if widget is None:
                    continue
                chosen = widget.currentData()
                if field.kind == actor_filters.FLAG:
                    values[field.key] = bool(chosen)
                elif field.kind == actor_filters.NUMBER:
                    values[field.key] = int(chosen or 0)
                else:
                    values[field.key] = chosen
            picked[platform] = values
        return picked

    def _build_country_section(self, layout, saved_settings: dict):
        """The country/city tree.

        A COUNTRY AND ITS OWN CITIES ARE NO LONGER BOTH CHOOSABLE, AND THAT IS A COST FIX

        They used to be independent -- "checking both is redundant but not wrong". It turned
        out to be expensive rather than redundant. The search plan is
        platform x (countries + cities), so Netherlands AND Amsterdam is two locations and
        1.75x the actor runs, for listings the Netherlands search already returns and dedup
        then throws away. Sina watched a search go from about 4 euros to over 11 and guessed
        the cause himself: "من فکر کنم مثلا هم Netherlands رو انتخاب کردم هم Amesterdam / شاید
        این فکر کرده باید 2 تا جستجو بزنه". He was right.

        So checking a country now disables its own cities: the country already includes them.
        A city is still selectable on its own, which is the case the city rows exist for --
        searching Amsterdam without paying for the whole of the Netherlands.
        """
        countries_title = QLabel("Which countries and/or cities should it search?")
        countries_title.setObjectName("SectionTitle")
        layout.addWidget(countries_title)

        countries_hint = QLabel(
            "Check a country to search the whole country — its cities are then included, so "
            "they are greyed out. Check a city on its own to search only that city."
        )
        countries_hint.setObjectName("HintLabel")
        countries_hint.setWordWrap(True)
        layout.addWidget(countries_hint)

        # `or` would be wrong here: if the user explicitly saved with zero countries
        # checked (e.g. a cities-only search), saved_settings['countries'] is a real,
        # present [] -- `[] or pipeline.COUNTRIES` would silently fall back to "all
        # countries" and re-check everything the next time the wizard opens. Only
        # missing the key at all (a first-ever run, no saved settings yet) should
        # default to "all countries".
        raw_saved_countries = saved_settings.get('countries')
        saved_countries = set(raw_saved_countries if raw_saved_countries is not None else pipeline.COUNTRIES)
        # Cities default to none selected (unlike countries, which default to all) --
        # city search is opt-in, same as the 'google' platform checkbox above.
        saved_cities = set(saved_settings.get('cities') or [])

        # A country with cities (pipeline.COUNTRY_CITIES) gets those cities nested
        # underneath it as their own checkable child rows. Still no tristate parent and no
        # auto-check-children -- but a checked country now DISABLES its cities, because the
        # country search already covers them and paying for both is what doubled the bill.
        self.countries_tree = QTreeWidget()
        self.countries_tree.setHeaderHidden(True)
        self.countries_tree.setFixedHeight(280)
        for country in pipeline.COUNTRIES:
            country_item = QTreeWidgetItem([country])
            country_item.setFlags(country_item.flags() | Qt.ItemIsUserCheckable)
            country_item.setCheckState(0, Qt.Checked if country in saved_countries else Qt.Unchecked)
            self.countries_tree.addTopLevelItem(country_item)
            for city in pipeline.COUNTRY_CITIES.get(country, []):
                city_item = QTreeWidgetItem([city])
                city_item.setFlags(city_item.flags() | Qt.ItemIsUserCheckable)
                city_item.setCheckState(0, Qt.Checked if city in saved_cities else Qt.Unchecked)
                city_item.setData(0, Qt.UserRole, 'city')
                country_item.addChild(city_item)
            # Starts collapsed (not expanded) -- clicking anywhere on a country row
            # with cities toggles it open/closed (see _on_country_tree_item_clicked),
            # rather than always showing every city up front. A child's check state is
            # unaffected by whether it's currently visible -- collapsing Norway after
            # checking Oslo does not uncheck Oslo, Qt tree items keep their check state
            # regardless of expand/collapse.
        self.countries_tree.itemClicked.connect(self._on_country_tree_item_clicked)
        # itemChanged rather than itemClicked, because a check state also changes from
        # "Select all", "Clear all" and from loading saved settings -- and the cities have to
        # follow the country in every one of those, not only when Sina clicks the row.
        self.countries_tree.itemChanged.connect(self._on_country_tree_item_changed)
        layout.addWidget(self.countries_tree)
        self._sync_city_rows()

        countries_buttons = QHBoxLayout()
        select_all_btn = QPushButton("Select all")
        select_all_btn.clicked.connect(lambda: self._set_all_countries(Qt.Checked))
        clear_all_btn = QPushButton("Clear all")
        clear_all_btn.clicked.connect(lambda: self._set_all_countries(Qt.Unchecked))
        countries_buttons.addWidget(select_all_btn)
        countries_buttons.addWidget(clear_all_btn)
        countries_buttons.addStretch(1)
        layout.addLayout(countries_buttons)

    def _build_button_bar(self, outer_layout):
        """Cancel / Save / Start Search.

        Added to the OUTER layout, not the scrolling content, so the buttons stay
        reachable however tall the settings above get."""
        # Cancel/Save/Start Search live outside the scroll area (added to outer_layout,
        # not `layout`), so they're always visible regardless of how tall the content
        # above is.
        self.should_start_search = False  # set by whichever of Save/Start Search was clicked

        button_bar = QWidget()
        button_bar.setStyleSheet("background-color: #141a2b;")
        buttons = QHBoxLayout(button_bar)
        buttons.setContentsMargins(24, 12, 24, 20)
        buttons.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setToolTip("Save these settings without starting a search.")
        save_btn.clicked.connect(self._on_save)
        start_btn = QPushButton("Start Search")
        start_btn.setObjectName("PrimaryButton")
        start_btn.clicked.connect(self._on_start)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        buttons.addWidget(start_btn)
        outer_layout.addWidget(button_bar)


    def _build_api_keys_section(self, saved_settings: dict) -> QWidget:
        """Free direct-API credentials. Every one of these
        used to have no UI at all -- the only documented way to set them was hand-editing
        %APPDATA%\\JobDesk\\settings.json, the one file this dialog rewrites whenever it
        saves. Collapsed by default (click the header to open) since it's optional setup,
        not part of a normal search."""
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)

        self._api_keys_toggle = QPushButton("▸  Optional API keys (Jooble, Reed, France Travail)")
        self._api_keys_toggle.setCheckable(True)
        self._api_keys_toggle.setStyleSheet(
            "QPushButton { text-align: left; font-weight: 600; padding: 8px 12px; }"
        )
        box.addWidget(self._api_keys_toggle)

        body = QWidget()
        body.setVisible(False)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 0, 0, 0)
        body_layout.setSpacing(10)

        note = QLabel(
            "All optional and all free. Leave any of them blank to skip that source. "
            "Jooble keys are per-country and capped at 500 requests each for their whole "
            "lifetime, so only fill in the countries you actually search."
        )
        note.setObjectName("HintLabel")
        note.setWordWrap(True)
        body_layout.addWidget(note)

        keys_form = QFormLayout()
        keys_form.setSpacing(8)

        self.reed_key_input = QLineEdit(saved_settings.get('reed_uk_api_key', ''))
        self.reed_key_input.setPlaceholderText("reed.co.uk jobseeker API key (United Kingdom)")
        keys_form.addRow("Reed:", self.reed_key_input)

        self.francetravail_id_input = QLineEdit(saved_settings.get('francetravail_client_id', ''))
        self.francetravail_id_input.setPlaceholderText("France Travail client ID")
        keys_form.addRow("France Travail ID:", self.francetravail_id_input)

        self.francetravail_secret_input = QLineEdit(saved_settings.get('francetravail_client_secret', ''))
        self.francetravail_secret_input.setPlaceholderText("France Travail client secret")
        self.francetravail_secret_input.setEchoMode(QLineEdit.Password)
        keys_form.addRow("France Travail secret:", self.francetravail_secret_input)

        # One row per Jooble country domain, labelled with the country it serves so it's
        # obvious which key does what -- the settings key itself is jooble_{code}_api_key.
        self.jooble_key_inputs: dict[str, QLineEdit] = {}
        for code, (country, _city) in pipeline.JOOBLE_API_COUNTRIES.items():
            field = QLineEdit(saved_settings.get(f'jooble_{code}_api_key', ''))
            field.setPlaceholderText(f"{code}.jooble.org key")
            self.jooble_key_inputs[code] = field
            keys_form.addRow(f"Jooble — {country}:", field)

        body_layout.addLayout(keys_form)

        box.addWidget(body)
        self._api_keys_toggle.toggled.connect(body.setVisible)
        self._api_keys_toggle.toggled.connect(
            lambda checked: self._api_keys_toggle.setText(
                ("▾  " if checked else "▸  ") + "Optional API keys (Jooble, Reed, France Travail)"
            )
        )
        return container

    @staticmethod
    def _select(combo: QComboBox, label: str):
        idx = combo.findText(label)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_country_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        # Clicking anywhere on a country row (not just its tiny expand arrow) that has
        # cities toggles it open/closed -- clicking a city row itself, or a country
        # with no cities, does nothing here (just checks/unchecks as normal).
        if item.parent() is None and item.childCount() > 0:
            item.setExpanded(not item.isExpanded())

    def _on_country_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        """A country's check state changed, so its cities have to follow it."""
        if item.parent() is None:
            self._sync_city_rows()

    def _sync_city_rows(self):
        """Grey out and clear the cities of any checked country.

        The country search already covers them, and selecting both is what took a search
        from 4 euros to over 11: the plan is platform x (countries + cities), so the same
        listings were fetched twice and deduplicated afterwards.

        Cleared as well as disabled, because a city left checked underneath a newly checked
        country would still be in `cities` when the wizard is read -- disabled in Qt means
        "cannot be clicked", not "does not count".
        """
        if not hasattr(self, 'countries_tree'):
            return
        tree = self.countries_tree
        tree.blockSignals(True)          # setCheckState below would re-enter this handler
        try:
            for i in range(tree.topLevelItemCount()):
                country_item = tree.topLevelItem(i)
                country_checked = country_item.checkState(0) == Qt.Checked
                for j in range(country_item.childCount()):
                    city_item = country_item.child(j)
                    if country_checked:
                        city_item.setCheckState(0, Qt.Unchecked)
                        city_item.setFlags(city_item.flags() & ~Qt.ItemIsEnabled)
                        city_item.setToolTip(0, 'Included in the whole-country search.')
                    else:
                        city_item.setFlags(city_item.flags() | Qt.ItemIsEnabled)
                        city_item.setToolTip(0, '')
        finally:
            tree.blockSignals(False)

    def _set_all_countries(self, state):
        # Applies to every country row AND every nested city row -- "Select all"/"Clear
        # all" affects both together.
        for i in range(self.countries_tree.topLevelItemCount()):
            country_item = self.countries_tree.topLevelItem(i)
            country_item.setCheckState(0, state)
            for j in range(country_item.childCount()):
                country_item.child(j).setCheckState(0, state)
        self._sync_city_rows()

    def _selected_actor_order(self) -> list[str]:
        selected = []
        for i in range(self.actor_list.count()):
            item = self.actor_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected

    def _selected_countries(self) -> list[str]:
        return [
            self.countries_tree.topLevelItem(i).text(0)
            for i in range(self.countries_tree.topLevelItemCount())
            if self.countries_tree.topLevelItem(i).checkState(0) == Qt.Checked
        ]

    def _selected_cities(self) -> list[str]:
        """The chosen cities -- never one whose country is also chosen.

        _sync_city_rows already unchecks those, and this is the second guard on the same
        rule, because the cost of getting it wrong is paid in euros: a city under a chosen
        country is a whole extra location in the search plan, returning listings the country
        search already returns.
        """
        selected = []
        for i in range(self.countries_tree.topLevelItemCount()):
            country_item = self.countries_tree.topLevelItem(i)
            if country_item.checkState(0) == Qt.Checked:
                continue
            for j in range(country_item.childCount()):
                city_item = country_item.child(j)
                if city_item.checkState(0) == Qt.Checked:
                    selected.append(city_item.text(0))
        return selected

    def _build_result_settings(self) -> bool:
        """Validates the form and fills self.result_settings. Returns True on success,
        False (with a warning already shown) if something required is missing --
        shared by both Save and Start Search, since a saved config should be just as
        valid/usable later as one that's about to be searched with immediately."""
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "Missing token", "Please enter your Apify API token.")
            return False

        countries = self._selected_countries()
        cities = self._selected_cities()
        if not countries and not cities:
            QMessageBox.warning(self, "Nothing selected", "Please select at least one country or city to search.")
            return False

        actor_order = self._selected_actor_order()
        if not actor_order:
            QMessageBox.warning(self, "No platforms selected", "Please select at least one platform (Indeed/Glassdoor/LinkedIn/Google).")
            return False
        # Note: cities are searched by Indeed/Glassdoor/LinkedIn directly (their own
        # 'location' fields), not only via Google -- so no country/city cross-requirement
        # is enforced here beyond "at least one of countries or cities is selected" above.

        search_title = ' '.join(self.title_input.text().split())
        if not search_title:
            QMessageBox.warning(self, "Missing job title",
                                "Please type the job title to search for, e.g. Data Engineer.")
            return False
        # There is deliberately no résumé check here any more. A search does not read the
        # résumé -- it collects postings -- so refusing to start one over a missing résumé
        # was refusing the wrong thing at the wrong moment. The Filter window, which is what
        # actually scores against it, asks for it there instead.

        date_range_label = self.date_combo.currentText()

        # Starts from a COPY of everything already saved (Jooble/Reed/France Travail
        # credentials, anything else this wizard has no field
        # for) and only overwrites the keys this wizard actually manages below -- see
        # the note on self._saved_settings in __init__ for why this matters.
        self.result_settings = dict(self._saved_settings)
        self.result_settings.update({
            'apify_token': token,
            'anthropic_api_key': self.anthropic_key_input.text().strip(),
            # No cap, ever. The three keys are still written so a settings file saved by an
            # older build keeps the same shape, and so nothing that reads them has to learn
            # that they went away -- but they are now constants, not choices. See the note
            # where the removed checkbox used to be.
            'limit_enabled': False,
            'limit_value': pipeline.NO_RESULT_LIMIT,
            'limit_per_call': pipeline.NO_RESULT_LIMIT,
            'cities': cities,
            'countries': countries,
            'actor_order': actor_order,
            # What each platform is asked for, per platform. Written under the key
            # actor_filters.SETTINGS_KEY so the table that defines these fields is also the
            # thing that names where they live -- see app/pipeline/actor_filters.py.
            actor_filters.SETTINGS_KEY: self._selected_actor_filters(),
            # Which actor-backed sources may run. Written under the key the table owns,
            # for the same reason the filters are -- one place names it.
            sources_enabled.SETTINGS_KEY: self._selected_sources(),
            # One chosen range, and the per-platform values derived from it in one place.
            # `date_values` keeps its shape so everything reading it carries on unchanged;
            # what has gone is the chance of the three disagreeing.
            'date_range': date_range_label,
            'date_values': pipeline.date_settings_for(date_range_label),
            # What to look for: one title, one Level, Remote or Not Remote. `search_for` is
            # the one search the Level runs, kept for everything that already reads it.
            'search_title': search_title,
            'search_level': self.selected_level(),
            'search_workplace': self.selected_workplace(),
            'search_work_mode': self.selected_work_mode(),
            'search_for': self.selected_kinds(),
            'reed_uk_api_key': self.reed_key_input.text().strip(),
            'francetravail_client_id': self.francetravail_id_input.text().strip(),
            'francetravail_client_secret': self.francetravail_secret_input.text().strip(),
        })
        for code, field in self.jooble_key_inputs.items():
            self.result_settings[f'jooble_{code}_api_key'] = field.text().strip()
        return True

    def _on_save(self):
        # Deliberately does NOT close the dialog (no self.accept()) -- Save is meant to
        # let you keep configuring/reviewing without losing your place, e.g. while
        # deliberately not starting a search yet (out of Apify credits, still deciding
        # on countries/cities, etc.). Persists straight to disk here rather than only
        # via MainWindow after the dialog closes, since Start Search/Cancel might not
        # happen for a while (or at all) after this.
        if not self._build_result_settings():
            return
        # _build_result_settings returning True is exactly what guarantees this is a
        # dict rather than None; assert says so instead of leaving it implied.
        assert self.result_settings is not None
        storage.save_settings(self.result_settings)
        QMessageBox.information(self, "Saved", "Settings saved.")

    def _on_start(self):
        if not self._build_result_settings():
            return
        self.should_start_search = True
        self.accept()
