# -*- coding: utf-8 -*-
"""The Senior profile's own vocabulary -- every word, in all 13 languages.

Senior: senior individual contributors, and only that: 5 years and more. Keeps senior titles; drops entry, junior, mid and leadership titles -- and Lead, Staff and Principal, which Sina decided are not Senior.

A FULL COPY, on purpose. Sina's rule for the profiles is the rule he set for the three
modules: completely separate, every word written out for each one, "حتی اگر Redundancy
باشه". So this file repeats most of what the Junior profile (app/pipeline/country_rules.py)
and the other profiles hold -- the remote, language, sponsorship and unpaid vocabulary is
the same today. It is repeated so that tuning a word here can never move another profile.

Generated from the Junior vocabulary rather than typed, so that every copied section is
exactly Junior's. ONE thing differs, in the same place Junior keeps it:

    Junior       `senior`        the words that make a listing too senior for Junior
    this file    `wrong_level`   the words that make a listing the wrong level for Senior

Like Junior's, it is read against the TITLE only -- see _SECTION_SCOPE in rules.py for the
594 wrong deletions that taught the Junior profile this.
"""
from __future__ import annotations

ENGLISH: dict = {
    'name': 'English',
    'english_mention': ['english'],
    'remote': ['remote', 'remotely', 'work from home', 'working from home', 'work-from-home',
     'works from home', 'from home', 'at home role', 'home-based', 'home based',
     'homebased', 'home working', 'homeworking', 'home office', 'home-office', 'wfh',
     'w.f.h', 'telecommut', 'telework', 'tele-work', 'teleworking', 'fully remote',
     'full remote', 'fully-remote', '100% remote', '100 % remote', 'all-remote',
     'all remote', 'remote-first', 'remote first', 'remote-friendly', 'remote friendly',
     'remote-only', 'remote position', 'remote role', 'remote job', 'remote work',
     'remote working', 'remote opportunity', 'remote team', 'work from anywhere',
     'work anywhere', 'from anywhere', 'based anywhere', 'anywhere in the world',
     'anywhere in europe', 'anywhere in the eu', 'location independent',
     'location-independent', 'location agnostic', 'geographically flexible',
     'virtual position', 'virtual role', 'virtual job', 'digital nomad', 'nomad-friendly',
     'no office', 'officeless', 'office-free', 'anywhere-based', 'work off-site',
     'off-site work', 'smart working', 'smartworking', 'agile working', 'remote job',
     'remote working', 'home working'],
    'on_site': ['on-site', 'onsite', 'on site', 'in-office', 'in office', 'in-person', 'in person',
     'office-based', 'office based', 'hybrid working', 'hybrid work', 'hybrid model',
     'hybrid role', 'hybrid setup', 'hybrid arrangement', 'days in the office',
     'days a week in the office', 'days per week in the office', 'office attendance',
     'relocation required', 'must relocate', 'willing to relocate', 'physically present',
     'presence in the office', 'at our offices', 'based in our office',
     'commutable distance', 'commuting distance', 'our office in', 'office in ',
     'at our office', 'at our offices', 'you will be based in', 'will be based in',
     'based in our', 'located in', 'work in our', 'working in our office', 'join us in our',
     'in the heart of', 'come to the office', 'office location', 'work location',
     'based at our office', 'office days', 'office day'],
    'not_remote': ['no remote', 'not remote', 'non-remote', 'remote not available',
     'remote work not available', 'remote work not permitted', 'remote is not',
     'remote work is not', 'without remote', 'on-site only', 'onsite only', 'on site only',
     'office only', 'office-only', 'fully on-site', 'fully onsite', '100% on-site',
     '100% onsite', 'strictly on-site', 'strictly onsite', 'no home office',
     'no work from home', 'no working from home', 'no remote work', 'no telecommuting',
     'no telework', 'not a remote position', 'not a remote role', 'this is not a remote',
     'remote work is not possible', 'no remote option'],
    'other_language_required': ['german required', 'dutch required', 'french required', 'italian required',
     'spanish required', 'portuguese required', 'swedish required', 'norwegian required',
     'danish required', 'finnish required', 'fluent german', 'fluent dutch',
     'fluent french', 'fluent italian', 'fluent spanish', 'fluent portuguese',
     'fluent swedish', 'fluent norwegian', 'fluent danish', 'fluent finnish',
     'fluent in german', 'fluent in dutch', 'fluent in french', 'fluent in italian',
     'fluent in spanish', 'fluent in portuguese', 'fluent in swedish',
     'fluent in norwegian', 'fluent in danish', 'fluent in finnish', 'native german',
     'native dutch', 'native french', 'native speaker of german', 'german language skills',
     'dutch language skills', 'french language skills', 'command of german',
     'command of dutch', 'proficiency in german', 'proficiency in dutch',
     'business fluent german', 'business-fluent german', 'good german', 'good dutch skills',
     'knowledge of german', 'knowledge of dutch', 'speak the local language',
     'local language is required'],
    'no_sponsorship': ['no visa sponsorship', 'not sponsor', 'do not sponsor', 'does not sponsor',
     'cannot sponsor', 'unable to sponsor', 'no sponsorship', 'without sponsorship',
     'not eligible for sponsorship', 'not eligible for immigration sponsorship',
     'sponsorship is not available', 'sponsorship not available', 'we do not provide visa',
     'no work permit sponsorship', 'must already have the right to work',
     'must have the right to work', 'existing right to work', 'valid work permit required',
     'valid work authorisation', 'valid work authorization', 'eu citizens only',
     'eu nationals only', 'must be eligible to work', 'no relocation support',
     'no relocation assistance'],
    'unpaid': ['unpaid', 'un-paid', 'non-paid', 'not paid', 'without pay', 'without payment',
     'no salary', 'no compensation', 'no remuneration', 'without remuneration',
     'voluntary position', 'volunteer position', 'volunteer role', 'pro bono',
     'equity only', 'equity-only', 'for equity', 'self-funded', 'self funded',
     'own funding', 'bring your own funding', 'expenses only', 'stipend only',
     'unpaid internship', 'unpaid trainee'],
    'thesis': ['thesis', 'master thesis', "master's thesis", 'bachelor thesis', 'final project',
     'graduation project', 'dissertation'],
    'internship': ['internship', 'intern ', 'trainee', 'traineeship', 'apprentice', 'apprenticeship',
     'working student', 'placement year', 'co-op', 'graduate programme',
     'graduate program'],
    'part_time': ['part-time', 'part time', 'parttime', 'half-time', 'mini job', 'hours per week',
     'hrs/week'],
    'wrong_level': ['head of', 'vp of', 'vice president', 'chief ', 'cto', 'cio', 'ceo', 'coo', 'director',
     'executive', 'principal', 'staff engineer', 'distinguished engineer', 'team lead',
     'tech lead', 'engineering manager', 'department head', 'senior manager',
     'general manager', 'partner', 'founding engineer', 'mid-level', 'mid level',
     'midlevel', 'intermediate', 'junior', 'jr', 'entry level', 'entry-level', 'graduate',
     'new grad', 'early career', 'early-career'],
}

GERMAN: dict = {
    'name': 'German',
    'english_mention': ['englisch'],
    'remote': ['homeoffice', 'home-office', 'home office', 'im homeoffice', 'remote', 'remote-arbeit',
     'remote arbeit', 'remotearbeit', 'vollständig remote', 'komplett remote',
     '100% remote', '100 % remote', 'remote-first', 'ortsunabhängig',
     'ortsunabhängiges arbeiten', 'ortunabhängig', 'mobiles arbeiten', 'mobile arbeit',
     'mobiles büro', 'mobile office', 'telearbeit', 'teleheimarbeit', 'telearbeitsplatz',
     'teleworking', 'heimarbeit', 'von zu hause', 'von zuhause', 'von daheim',
     'arbeiten von zu hause', 'arbeit von zu hause', 'zuhause arbeiten',
     'im home-office arbeiten', 'überall arbeiten', 'von überall', 'von überall arbeiten',
     'arbeiten wo du willst', 'wohnortunabhängig', 'standortunabhängig', 'virtuelles team',
     'e-work'],
    'on_site': ['vor ort', 'vor-ort', 'präsenz', 'präsenzpflicht', 'in präsenz', 'präsenzarbeit',
     'im büro', 'büropräsenz', 'anwesenheit im büro', 'anwesenheitspflicht',
     'persönliche anwesenheit', 'hybrides arbeiten', 'hybrid-modell', 'hybridmodell',
     'hybrides modell', 'teilweise im büro', 'tage im büro', 'tage pro woche im büro',
     'umzug erforderlich', 'umzugsbereitschaft', 'wohnsitz in', 'am standort',
     'an unserem standort', 'im unternehmen vor ort', 'unser büro in', 'in unserem büro',
     'sie arbeiten in', 'bürotage', 'tage im büro pro woche'],
    'not_remote': ['kein homeoffice', 'kein home office', 'kein home-office', 'keine heimarbeit',
     'kein remote', 'keine remote', 'nicht remote', 'remote nicht möglich',
     'homeoffice nicht möglich', 'kein mobiles arbeiten', 'ausschließlich vor ort',
     'nur vor ort', 'ausschließlich in präsenz', 'nur in präsenz', '100% vor ort',
     'vollständig vor ort', 'keine remote-arbeit', 'ohne homeoffice',
     'kein telearbeitsplatz'],
    'other_language_required': ['deutschkenntnisse', 'deutsch-kenntnisse', 'gute deutschkenntnisse',
     'sehr gute deutschkenntnisse', 'ausgezeichnete deutschkenntnisse',
     'verhandlungssicheres deutsch', 'verhandlungssichere deutschkenntnisse',
     'fließend deutsch', 'fließende deutschkenntnisse', 'fliessend deutsch',
     'deutsch in wort und schrift', 'deutsch fließend in wort und schrift',
     'muttersprache deutsch', 'deutsch als muttersprache', 'muttersprachliches deutsch',
     'deutsch auf muttersprachlichem niveau', 'deutsch c1', 'deutsch c2', 'deutsch b2',
     'deutschniveau', 'sichere deutschkenntnisse', 'perfektes deutsch',
     'exzellentes deutsch', 'deutsch erforderlich', 'deutsch zwingend',
     'gute kenntnisse der deutschen sprache', 'beherrschung der deutschen sprache',
     'französischkenntnisse', 'italienischkenntnisse', 'niederländischkenntnisse'],
    'no_sponsorship': ['kein visum', 'kein visa-sponsoring', 'kein visasponsoring',
     'keine visumsunterstützung', 'kein sponsoring', 'keine sponsoring',
     'arbeitserlaubnis erforderlich', 'gültige arbeitserlaubnis',
     'arbeitserlaubnis für die eu', 'eu-arbeitserlaubnis',
     'aufenthaltserlaubnis erforderlich', 'gültige aufenthaltsgenehmigung', 'nur eu-bürger',
     'eu-staatsbürgerschaft erforderlich', 'bereits eine arbeitserlaubnis',
     'keine unterstützung bei der visabeschaffung', 'keine umzugsunterstützung'],
    'unpaid': ['unbezahlt', 'unbezahltes praktikum', 'unentgeltlich', 'ohne vergütung',
     'keine vergütung', 'ohne bezahlung', 'ehrenamtliche tätigkeit', 'ehrenamtliche stelle',
     'freiwilligenarbeit', 'freiwillig unbezahlt', 'auf freiwilliger basis', 'kein gehalt',
     'ohne gehalt', 'selbstfinanziert', 'eigenfinanziert', 'nur aufwandsentschädigung',
     'aufwandsentschädigung statt gehalt'],
    'thesis': ['abschlussarbeit', 'masterarbeit', 'bachelorarbeit', 'diplomarbeit', 'doktorarbeit',
     'studienarbeit', 'thesis', 'dissertation', 'forschungsarbeit', 'diplomand',
     'bachelorand', 'masterand', 'doktorand'],
    'internship': ['praktikum', 'praktikant', 'praktikantin', 'werkstudent', 'werkstudentin', 'trainee',
     'traineeprogramm', 'volontariat', 'volontär', 'berufseinstieg', 'ferialpraktikum',
     'ferialjob', 'pflichtpraktikum', 'berufspraktikum', 'praxissemester',
     'schnupperpraktikum', 'hospitanz', 'studentische hilfskraft'],
    'part_time': ['teilzeit', 'in teilzeit', 'minijob', 'mini-job', 'geringfügig',
     'geringfügige beschäftigung', 'stunden pro woche', 'std./woche', 'wochenstunden',
     'halbtags'],
    'wrong_level': ['leiter', 'leiterin', 'leitung', 'abteilungsleiter', 'bereichsleiter', 'teamleiter',
     'gruppenleiter', 'geschäftsführer', 'geschäftsführung', 'vorstand', 'prokurist',
     'direktor', 'niederlassungsleiter', 'führungskraft', 'führungserfahrung', 'leitende',
     'junior', 'nachwuchs', 'berufseinsteiger', 'einsteiger', 'absolvent',
     'hochschulabsolvent', 'direkteinstieg', 'einstiegsposition', 'berufsstart'],
}

DUTCH: dict = {
    'name': 'Dutch',
    'english_mention': ['engels'],
    'remote': ['thuiswerk', 'thuiswerken', 'thuis werken', 'vanuit huis', 'vanuit thuis',
     'werken vanuit huis', 'werk vanuit huis', 'thuiswerkdag', 'thuiswerkdagen',
     'thuiswerkplek', 'op afstand', 'werken op afstand', 'werk op afstand', 'afstandswerk',
     'remote', 'volledig remote', '100% remote', 'remote-first', 'telewerk', 'telewerken',
     'thuiswerkmogelijkheden', 'flexibele werkplek', 'plaatsonafhankelijk',
     'locatieonafhankelijk', 'overal werken', 'werken waar je wilt', 'vanuit elke locatie',
     'digitale nomade', 'volledig vanuit huis', 'volledig thuiswerken',
     'vanuit huis werken', 'werken vanuit huis', 'remote job'],
    'on_site': ['op kantoor', 'op locatie', 'op de werkvloer', 'kantoorwerk', 'op ons kantoor',
     'hybride werken', 'hybride model', 'hybride functie', 'dagen op kantoor',
     'dagen per week op kantoor', 'aanwezigheid op kantoor', 'aanwezig op kantoor',
     'kantooraanwezigheid', 'fysiek aanwezig', 'verhuizing vereist', 'bereid te verhuizen',
     'woonachtig in', 'in de buurt van ons kantoor', 'standplaats', 'ons kantoor in',
     'op ons kantoor in', 'je werkt op', 'werklocatie', 'standplaats', 'gevestigd in',
     'werken op kantoor', 'kantoordag', 'kantoordagen', 'op locatie werken',
     'hybride werkvorm', 'dagen per week op kantoor', 'standplaats is'],
    'not_remote': ['geen thuiswerk', 'geen thuiswerken', 'niet thuiswerken', 'geen remote', 'niet remote',
     'remote niet mogelijk', 'thuiswerken is niet mogelijk', 'alleen op kantoor',
     'uitsluitend op kantoor', 'volledig op kantoor', '100% op kantoor',
     'alleen op locatie', 'uitsluitend op locatie', 'geen mogelijkheid tot thuiswerken',
     'geen telewerk'],
    'other_language_required': ['nederlands vereist', 'nederlandse taal', 'goede beheersing van het nederlands',
     'uitstekende beheersing van het nederlands', 'vloeiend nederlands',
     'vloeiende beheersing van het nederlands', 'nederlands in woord en geschrift',
     'nederlands als moedertaal', 'moedertaal nederlands', 'nederlands op moedertaalniveau',
     'nederlands niveau c1', 'nederlands c1', 'nederlands c2', 'nederlands b2',
     'goede nederlandse taalvaardigheid', 'beheersing van de nederlandse taal',
     'nederlandstalig', 'frans vereist', 'franse taal', 'tweetalig nederlands frans'],
    'no_sponsorship': ['geen visum', 'geen visumsponsoring', 'geen sponsoring', 'wij sponsoren geen',
     'geen werkvergunning', 'werkvergunning vereist', 'geldige werkvergunning',
     'geldige verblijfsvergunning', 'verblijfsvergunning vereist', 'alleen eu-burgers',
     'eu-burger', 'reeds gerechtigd om te werken', 'recht om in nederland te werken',
     'geen verhuisvergoeding'],
    'unpaid': ['onbetaald', 'onbetaalde stage', 'zonder vergoeding', 'geen vergoeding',
     'geen salaris', 'zonder salaris', 'vrijwilligerswerk', 'vrijwilligersfunctie',
     'op vrijwillige basis', 'onkostenvergoeding', 'alleen onkostenvergoeding',
     'zelf gefinancierd', 'zelffinanciering'],
    'thesis': ['afstudeeropdracht', 'afstudeerstage', 'scriptie', 'masterscriptie',
     'bachelorscriptie', 'afstudeerproject', 'thesis'],
    'internship': ['stage', 'stagiair', 'stagiaire', 'stageplaats', 'stageopdracht', 'werkstudent',
     'trainee', 'traineeship', 'leerwerkplek', 'starterfunctie'],
    'part_time': ['deeltijd', 'parttime', 'part-time', 'uur per week', 'uren per week', 'bijbaan',
     'in deeltijd'],
    'wrong_level': ['hoofd', 'hoofd van', 'afdelingshoofd', 'teamleider', 'teamlead', 'manager',
     'directeur', 'directie', 'bestuurder', 'leidinggevende', 'leidinggevende ervaring',
     'principal', 'medior', 'junior', 'starter', 'startersfunctie', 'afgestudeerde',
     'pas afgestudeerd', 'traineeship'],
}

FRENCH: dict = {
    'name': 'French',
    'english_mention': ['anglais', 'anglaise', 'anglophone'],
    'remote': ['télétravail', 'teletravail', 'télé-travail', 'en télétravail', 'télétravail total',
     'télétravail complet', 'full remote', 'full-remote', '100% télétravail',
     '100 % télétravail', 'télétravail à 100', 'travail à distance', 'à distance',
     'travail a distance', 'travailler à distance', 'depuis chez vous', 'depuis chez soi',
     'depuis votre domicile', 'à domicile', 'travail à domicile', 'travailler de chez vous',
     'de la maison', 'remote', 'remote-first', 'télétravailleur', 'télétravailleuse',
     'nomadisme numérique', 'nomade numérique', 'où que vous soyez', "depuis n'importe où",
     'indépendant du lieu', 'sans bureau'],
    'on_site': ['présentiel', 'en présentiel', 'sur site', 'sur place', 'au bureau', 'dans nos locaux',
     'dans nos bureaux', 'présence au bureau', 'présence sur site', 'travail hybride',
     'mode hybride', 'jours au bureau', 'jours par semaine au bureau', 'jours de présence',
     'déménagement requis', 'mobilité géographique', 'résider à', 'basé à', 'poste basé',
     'rattaché au site', 'nos bureaux à', 'notre bureau à', 'lieu de travail',
     'poste basé à', 'basé à'],
    'not_remote': ['pas de télétravail', 'sans télétravail', 'télétravail non', 'aucun télétravail',
     'télétravail impossible', 'télétravail non possible', 'pas de remote',
     'uniquement en présentiel', 'exclusivement en présentiel', '100% présentiel',
     '100 % présentiel', 'uniquement sur site', 'exclusivement sur site',
     'présence obligatoire', 'pas de travail à distance'],
    'other_language_required': ['français courant', 'français couramment', 'maîtrise du français',
     'excellente maîtrise du français', 'parfaite maîtrise du français',
     'bonne maîtrise du français', 'français langue maternelle',
     'langue maternelle française', 'niveau c1 en français', 'français c1', 'français c2',
     'français b2', 'français exigé', 'français requis', 'français impératif',
     "français à l'écrit et à l'oral", 'très bon niveau de français', 'francophone',
     'bilingue français', 'allemand courant', "maîtrise de l'allemand",
     'néerlandais courant', 'luxembourgeois', 'italien courant'],
    'no_sponsorship': ['pas de visa', 'pas de parrainage', 'aucun parrainage', 'sans parrainage',
     'nous ne parrainons pas', 'permis de travail requis', 'permis de travail valide',
     'titre de séjour valide', 'autorisation de travail requise',
     'autorisation de travail valide', "ressortissants de l'ue uniquement",
     "citoyens de l'ue uniquement", 'droit de travailler', 'déjà autorisé à travailler',
     "pas d'aide à la relocalisation"],
    'unpaid': ['non rémunéré', 'non rémunérée', 'sans rémunération', 'aucune rémunération',
     'pas de rémunération', 'non payé', 'sans salaire', 'aucun salaire', 'poste bénévole',
     'à titre bénévole', 'stage non rémunéré', 'stage non-rémunéré', 'autofinancé',
     'défraiement uniquement', 'indemnité de stage uniquement'],
    'thesis': ['mémoire', "mémoire de fin d'études", "projet de fin d'études", 'thèse',
     "stage de fin d'études"],
    'internship': ['stage', 'stagiaire', 'alternance', 'alternant', 'apprentissage', 'apprenti',
     'contrat de professionnalisation', 'césure', 'jeune diplômé'],
    'part_time': ['temps partiel', 'à temps partiel', 'mi-temps', 'heures par semaine', 'heures/semaine'],
    'wrong_level': ['directeur', 'directrice', 'direction', 'chef de', 'responsable de',
     "responsable d'équipe", "chef d'équipe", 'manager', 'encadrement',
     'expérience managériale', 'cadre dirigeant', 'président', 'confirmé', 'junior',
     'jeune diplômé', 'débutant', 'premier emploi', "sortie d'école"],
}

ITALIAN: dict = {
    'name': 'Italian',
    'english_mention': ['inglese', 'inglesi'],
    'remote': ['lavoro da remoto', 'da remoto', 'in remoto', 'lavoro remoto', 'remoto',
     'smart working', 'smartworking', 'smart-working', 'telelavoro', 'tele-lavoro',
     'lavoro agile', 'lavoro da casa', 'da casa', 'lavorare da casa', 'da qualsiasi luogo',
     'ovunque', 'lavoro ovunque', 'full remote', '100% remoto', '100% da remoto',
     'completamente da remoto', 'remote-first', 'indipendente dalla sede',
     'senza sede fissa', 'nomade digitale'],
    'on_site': ['in sede', 'presso la sede', 'in ufficio', 'presenza in ufficio', 'in presenza',
     'lavoro in presenza', 'sul posto', 'presso i nostri uffici', 'ibrido', 'lavoro ibrido',
     'modalità ibrida', 'giorni in ufficio', 'giorni a settimana in ufficio',
     'presenza richiesta', 'trasferimento richiesto', 'disponibilità al trasferimento',
     'residenza a', 'i nostri uffici a', 'sede di lavoro', 'con sede a', 'onsite',
     'on site'],
    'not_remote': ['no smart working', 'niente smart working', 'senza smart working', 'non da remoto',
     'no remoto', 'nessun lavoro da remoto', 'solo in sede', 'esclusivamente in sede',
     'solo in ufficio', 'esclusivamente in presenza', 'solo in presenza', '100% in sede',
     'presenza obbligatoria', 'non è previsto lo smart working'],
    'other_language_required': ['italiano fluente', "ottima conoscenza dell'italiano",
     "buona conoscenza dell'italiano", "padronanza dell'italiano", 'italiano madrelingua',
     'madrelingua italiana', 'italiano livello c1', 'italiano c1', 'italiano c2',
     'italiano b2', 'italiano richiesto', 'conoscenza della lingua italiana',
     'lingua italiana', 'italiano scritto e parlato', 'tedesco fluente',
     'francese fluente'],
    'no_sponsorship': ['nessun visto', 'no visto', 'nessuna sponsorizzazione',
     'non offriamo sponsorizzazione', 'permesso di soggiorno richiesto',
     'permesso di lavoro valido', 'permesso di soggiorno valido', 'solo cittadini ue',
     'cittadinanza ue', 'già autorizzato a lavorare', 'diritto di lavorare in italia',
     'nessun supporto al trasferimento'],
    'unpaid': ['non retribuito', 'non retribuita', 'senza retribuzione', 'nessuna retribuzione',
     'non pagato', 'senza stipendio', 'nessun compenso', 'senza compenso',
     'posizione volontaria', 'a titolo volontario', 'tirocinio non retribuito',
     'stage non retribuito', 'autofinanziato', 'solo rimborso spese', 'rimborso spese'],
    'thesis': ['tesi', 'tesi di laurea', 'tesi magistrale', 'progetto di tesi', 'tirocinio di tesi'],
    'internship': ['tirocinio', 'tirocinante', 'stage', 'stagista', 'apprendistato', 'apprendista',
     'neolaureato', 'praticante'],
    'part_time': ['part time', 'part-time', 'tempo parziale', 'a tempo parziale', 'ore settimanali',
     'ore a settimana'],
    'wrong_level': ['responsabile', 'responsabile di', 'direttore', 'direttrice', 'direzione', 'capo',
     'capo squadra', 'team leader', 'dirigente', 'manager', 'esperienza manageriale',
     'principal', 'middle', 'junior', 'neolaureat', 'prima esperienza', 'primo impiego'],
}

SPANISH: dict = {
    'name': 'Spanish',
    'english_mention': ['inglés', 'ingles', 'inglesa'],
    'remote': ['teletrabajo', 'tele-trabajo', 'en teletrabajo', 'trabajo remoto', 'trabajo en remoto',
     'en remoto', 'remoto', 'remote', 'full remote', '100% remoto', '100 % remoto',
     'totalmente remoto', 'completamente remoto', 'trabajo desde casa', 'desde casa',
     'trabajar desde casa', 'desde su casa', 'desde cualquier lugar', 'trabajo a distancia',
     'a distancia', 'trabajo deslocalizado', 'sin oficina', 'independiente de la ubicación',
     'nómada digital', 'remote-first'],
    'on_site': ['presencial', 'trabajo presencial', 'de forma presencial', 'en la oficina',
     'en nuestras oficinas', 'en el centro de trabajo', 'asistencia a la oficina',
     'híbrido', 'trabajo híbrido', 'modelo híbrido', 'modalidad híbrida',
     'días en la oficina', 'días a la semana en la oficina', 'traslado requerido',
     'disponibilidad para trasladarse', 'residencia en', 'nuestras oficinas en',
     'lugar de trabajo', 'con sede en'],
    'not_remote': ['sin teletrabajo', 'no teletrabajo', 'no hay teletrabajo', 'no se ofrece teletrabajo',
     'sin trabajo remoto', 'no remoto', 'solo presencial', 'únicamente presencial',
     '100% presencial', 'exclusivamente presencial', 'presencialidad obligatoria',
     'no se admite teletrabajo'],
    'other_language_required': ['español fluido', 'castellano fluido', 'dominio del español',
     'excelente dominio del español', 'nivel nativo de español', 'español nativo',
     'lengua materna española', 'español c1', 'español c2', 'español b2',
     'nivel c1 de español', 'se requiere español', 'imprescindible español',
     'conocimiento del español', 'catalán', 'se valorará el catalán',
     'imprescindible catalán'],
    'no_sponsorship': ['sin visado', 'no patrocinamos', 'sin patrocinio', 'no ofrecemos visado',
     'permiso de trabajo requerido', 'permiso de trabajo válido', 'permiso de residencia',
     'autorización de trabajo', 'solo ciudadanos de la ue', 'ciudadanía de la ue',
     'ya autorizado para trabajar', 'derecho a trabajar en españa',
     'sin ayuda a la reubicación'],
    'unpaid': ['no remunerado', 'no remunerada', 'sin remuneración', 'sin sueldo', 'sin salario',
     'no retribuido', 'sin retribución', 'puesto voluntario', 'a título voluntario',
     'prácticas no remuneradas', 'beca no remunerada', 'autofinanciado', 'solo gastos'],
    'thesis': ['tesis', 'trabajo fin de máster', 'trabajo fin de grado', 'tfg', 'tfm',
     'proyecto final de carrera'],
    'internship': ['prácticas', 'becario', 'becaria', 'beca', 'pasantía', 'aprendiz', 'trainee',
     'recién titulado', 'recién graduado'],
    'part_time': ['media jornada', 'jornada parcial', 'tiempo parcial', 'part time', 'part-time',
     'horas semanales', 'horas por semana'],
    'wrong_level': ['director', 'directora', 'dirección', 'jefe de', 'jefa de', 'responsable de',
     'líder de equipo', 'gerente', 'manager', 'experiencia en gestión de equipos',
     'principal', 'semi senior', 'semi-senior', 'semisenior', 'ssr', 'junior', 'júnior',
     'recién titulad', 'recién graduad', 'primer empleo', 'sin experiencia'],
}

PORTUGUESE: dict = {
    'name': 'Portuguese',
    'english_mention': ['inglês', 'ingles', 'inglesa'],
    'remote': ['teletrabalho', 'tele-trabalho', 'em teletrabalho', 'trabalho remoto',
     'trabalho à distância', 'à distância', 'remoto', 'em remoto', 'remote', 'full remote',
     '100% remoto', 'totalmente remoto', 'completamente remoto',
     'trabalho a partir de casa', 'a partir de casa', 'trabalhar de casa', 'em casa',
     'de qualquer lugar', 'em qualquer lugar', 'sem escritório',
     'independente da localização', 'nómada digital', 'nômade digital', 'remote-first'],
    'on_site': ['presencial', 'trabalho presencial', 'em regime presencial', 'no escritório',
     'nos nossos escritórios', 'nas instalações', 'presença no escritório', 'híbrido',
     'trabalho híbrido', 'regime híbrido', 'modelo híbrido', 'dias no escritório',
     'dias por semana no escritório', 'mudança de residência', 'residência em',
     'deslocação para', 'os nossos escritórios em', 'local de trabalho', 'com sede em'],
    'not_remote': ['sem teletrabalho', 'não há teletrabalho', 'sem trabalho remoto', 'não remoto',
     'apenas presencial', 'exclusivamente presencial', '100% presencial',
     'somente presencial', 'presença obrigatória', 'não é possível teletrabalho'],
    'other_language_required': ['português fluente', 'domínio do português', 'excelente domínio do português',
     'português nativo', 'língua materna portuguesa', 'português c1', 'português c2',
     'português b2', 'nível c1 de português', 'obrigatório português', 'requer português',
     'conhecimento de português', 'português falado e escrito'],
    'no_sponsorship': ['sem visto', 'não patrocinamos', 'sem patrocínio', 'autorização de residência',
     'autorização de trabalho válida', 'visto de trabalho válido', 'apenas cidadãos da ue',
     'cidadania da ue', 'já autorizado a trabalhar', 'direito a trabalhar em portugal',
     'sem apoio à relocalização'],
    'unpaid': ['não remunerado', 'não remunerada', 'sem remuneração', 'sem salário', 'sem vencimento',
     'posição voluntária', 'a título voluntário', 'estágio não remunerado',
     'estágio curricular não remunerado', 'autofinanciado', 'apenas ajudas de custo'],
    'thesis': ['tese', 'dissertação', 'projeto final', 'trabalho final de mestrado'],
    'internship': ['estágio', 'estagiário', 'estagiária', 'estágio curricular', 'estágio profissional',
     'trainee', 'recém-licenciado'],
    'part_time': ['tempo parcial', 'part time', 'part-time', 'meio período', 'horas por semana',
     'horas semanais'],
    'wrong_level': ['diretor', 'diretora', 'direção', 'director', 'chefe de', 'responsável por',
     'líder de equipa', 'gestor', 'gerente', 'manager', 'experiência de gestão', 'pleno',
     'junior', 'júnior', 'recém-licenciad', 'recém-formad', 'primeiro emprego',
     'sem experiência'],
}

SWEDISH: dict = {
    'name': 'Swedish',
    'english_mention': ['engelsk'],
    'remote': ['distansarbete', 'på distans', 'arbeta på distans', 'jobba på distans', 'distansjobb',
     'helt på distans', '100% distans', 'heldistans', 'hemarbete', 'hemifrån',
     'arbeta hemifrån', 'jobba hemifrån', 'arbete hemifrån', 'hemmakontor', 'hemmajobb',
     'distansarbetsplats', 'remote', 'remote-first', 'var som helst',
     'arbeta var som helst', 'platsoberoende', 'oberoende av plats', 'digital nomad',
     'telependling'],
    'on_site': ['på plats', 'arbete på plats', 'på kontoret', 'på vårt kontor', 'kontorsarbete',
     'närvaro på kontoret', 'fysisk närvaro', 'hybridarbete', 'hybridmodell',
     'hybridlösning', 'dagar på kontoret', 'dagar i veckan på kontoret', 'flytt krävs',
     'bosatt i', 'placering i', 'vårt kontor i', 'arbetsplats', 'placering'],
    'not_remote': ['inget distansarbete', 'ingen distans', 'ej distansarbete',
     'distansarbete är inte möjligt', 'inget hemarbete', 'ej hemifrån', 'endast på plats',
     'enbart på plats', 'endast på kontoret', '100% på plats', 'obligatorisk närvaro',
     'ingen möjlighet till distansarbete'],
    'other_language_required': ['flytande svenska', 'goda kunskaper i svenska', 'mycket goda kunskaper i svenska',
     'behärskar svenska', 'svenska i tal och skrift', 'svenska som modersmål',
     'modersmål svenska', 'svenska på modersmålsnivå', 'svenska krävs', 'krav på svenska',
     'svenska c1', 'svenska b2', 'svenskspråkig', 'finska kunskaper'],
    'no_sponsorship': ['inget visum', 'ingen visumsponsring', 'ingen sponsring', 'arbetstillstånd krävs',
     'giltigt arbetstillstånd', 'uppehållstillstånd krävs', 'endast eu-medborgare',
     'eu-medborgarskap', 'redan rätt att arbeta', 'rätt att arbeta i sverige',
     'ingen flyttersättning'],
    'unpaid': ['obetald', 'obetalt', 'utan lön', 'ingen lön', 'utan ersättning', 'ingen ersättning',
     'ideellt arbete', 'volontärarbete', 'frivilligarbete', 'obetald praktik',
     'egenfinansierad', 'endast kostnadsersättning'],
    'thesis': ['examensarbete', 'exjobb', 'masteruppsats', 'kandidatuppsats', 'uppsats', 'avhandling'],
    'internship': ['praktik', 'praktikant', 'trainee', 'traineeprogram', 'lärling', 'nyexaminerad', 'lia'],
    'part_time': ['deltid', 'på deltid', 'deltidstjänst', 'timmar per vecka', 'extrajobb'],
    'wrong_level': ['chef', 'avdelningschef', 'gruppchef', 'teamchef', 'enhetschef', 'verksamhetschef',
     'direktör', 'vd', 'ledare', 'teamledare', 'ledarerfarenhet', 'principal', 'junior',
     'nyexaminerad', 'nyutexaminerad', 'traineeprogram'],
}

NORWEGIAN: dict = {
    'name': 'Norwegian',
    'english_mention': ['engelsk'],
    'remote': ['hjemmekontor', 'heimekontor', 'på hjemmekontor', 'fra hjemmekontor', 'hjemmefra',
     'heimefrå', 'jobbe hjemmefra', 'arbeide hjemmefra', 'jobb hjemmefra', 'hjemmearbeid',
     'heimearbeid', 'fjernarbeid', 'fjernjobb', 'arbeid på avstand', 'på avstand', 'remote',
     'remote-first', 'fullt remote', '100% remote', 'stedsuavhengig',
     'stedsuavhengig arbeid', 'jobbe hvor som helst', 'hvor som helst fra',
     'digital nomade', 'distansearbeid'],
    'on_site': ['på kontoret', 'på vårt kontor', 'kontorarbeid', 'på arbeidsplassen', 'fysisk oppmøte',
     'oppmøte på kontoret', 'tilstedeværelse', 'hybridarbeid', 'hybridmodell',
     'hybrid arbeidshverdag', 'dager på kontoret', 'dager i uken på kontoret',
     'flytting kreves', 'bosatt i', 'arbeidssted', 'vårt kontor i', 'arbeidssted er'],
    'not_remote': ['ikke hjemmekontor', 'ingen hjemmekontor', 'ikke mulig med hjemmekontor',
     'ikke fjernarbeid', 'ingen fjernarbeid', 'ikke remote', 'kun på kontoret',
     'bare på kontoret', 'utelukkende på kontoret', '100% på kontoret',
     'obligatorisk oppmøte'],
    'other_language_required': ['flytende norsk', 'gode norskkunnskaper', 'meget gode norskkunnskaper',
     'behersker norsk', 'norsk muntlig og skriftlig', 'norsk som morsmål', 'morsmål norsk',
     'norsk på morsmålsnivå', 'norsk kreves', 'krav om norsk', 'norsk c1', 'norsk b2',
     'norskspråklig', 'skandinavisk språk'],
    'no_sponsorship': ['ingen visum', 'ingen visumstøtte', 'ingen sponsing', 'arbeidstillatelse kreves',
     'gyldig arbeidstillatelse', 'oppholdstillatelse kreves', 'kun eu-borgere',
     'eøs-borgere', 'allerede rett til å arbeide', 'rett til å jobbe i norge',
     'ingen flyttestøtte'],
    'unpaid': ['ubetalt', 'ulønnet', 'uten lønn', 'ingen lønn', 'uten godtgjørelse',
     'ingen godtgjørelse', 'frivillig arbeid', 'ulønnet praksis', 'egenfinansiert',
     'kun utgiftsdekning'],
    'thesis': ['masteroppgave', 'bacheloroppgave', 'oppgave', 'avhandling', 'hovedoppgave'],
    'internship': ['praksis', 'praktikant', 'internship', 'trainee', 'traineeprogram', 'lærling',
     'nyutdannet'],
    'part_time': ['deltid', 'på deltid', 'deltidsstilling', 'timer i uken', 'ekstrajobb'],
    'wrong_level': ['leder', 'avdelingsleder', 'teamleder', 'gruppeleder', 'fagleder', 'daglig leder',
     'direktør', 'sjef', 'ledererfaring', 'junior', 'nyutdannet', 'nyutdanna',
     'traineeprogram'],
}

DANISH: dict = {
    'name': 'Danish',
    'english_mention': ['engelsk'],
    'remote': ['hjemmearbejde', 'hjemmefra', 'arbejde hjemmefra', 'arbejde fra hjemmet',
     'hjemmearbejdsplads', 'hjemmekontor', 'fjernarbejde', 'distancearbejde', 'telearbejde',
     'arbejde på afstand', 'på afstand', 'remote', 'remote-first', 'fuldt remote',
     '100% remote', 'stedsuafhængig', 'arbejd hvor som helst', 'hvor som helst fra',
     'digital nomade', 'fleksibel arbejdsplads'],
    'on_site': ['på kontoret', 'på vores kontor', 'kontorarbejde', 'på arbejdspladsen',
     'fysisk fremmøde', 'fremmøde på kontoret', 'tilstedeværelse', 'hybridarbejde',
     'hybridmodel', 'hybridarbejdsplads', 'dage på kontoret', 'dage om ugen på kontoret',
     'flytning påkrævet', 'bosat i', 'arbejdssted', 'vores kontor i', 'arbejdssted er'],
    'not_remote': ['intet hjemmearbejde', 'ingen hjemmearbejde', 'ikke hjemmearbejde',
     'ikke muligt at arbejde hjemmefra', 'intet fjernarbejde', 'ikke remote',
     'kun på kontoret', 'udelukkende på kontoret', '100% på kontoret',
     'obligatorisk fremmøde'],
    'other_language_required': ['flydende dansk', 'gode danskkundskaber', 'meget gode danskkundskaber',
     'behersker dansk', 'dansk i skrift og tale', 'dansk som modersmål', 'modersmål dansk',
     'dansk på modersmålsniveau', 'dansk kræves', 'krav om dansk', 'dansk c1', 'dansk b2',
     'dansktalende', 'skandinavisk sprog'],
    'no_sponsorship': ['intet visum', 'ingen visumstøtte', 'ingen sponsorering', 'arbejdstilladelse påkrævet',
     'gyldig arbejdstilladelse', 'opholdstilladelse påkrævet', 'kun eu-borgere',
     'eu-statsborgerskab', 'allerede ret til at arbejde', 'ret til at arbejde i danmark',
     'ingen flyttehjælp'],
    'unpaid': ['ubetalt', 'ulønnet', 'uden løn', 'ingen løn', 'uden vederlag', 'intet vederlag',
     'frivilligt arbejde', 'ulønnet praktik', 'selvfinansieret', 'kun udgiftsdækning'],
    'thesis': ['speciale', 'kandidatspeciale', 'bachelorprojekt', 'afhandling', 'afgangsprojekt'],
    'internship': ['praktik', 'praktikant', 'internship', 'trainee', 'traineeforløb', 'elev',
     'nyuddannet'],
    'part_time': ['deltid', 'på deltid', 'deltidsstilling', 'timer om ugen', 'studiejob'],
    'wrong_level': ['leder', 'afdelingsleder', 'teamleder', 'gruppeleder', 'chef', 'direktør',
     'administrerende direktør', 'ledelseserfaring', 'junior', 'nyuddannet', 'dimittend',
     'graduate'],
}

FINNISH: dict = {
    'name': 'Finnish',
    'english_mention': ['englan'],
    'remote': ['etätyö', 'etätyötä', 'etätyössä', 'etätyön', 'etätyömahdollisuus', 'etätyöpäivä',
     'etätyöskentely', 'etänä', 'työskentely etänä', 'täysin etänä', 'kokonaan etänä',
     'etätoimisto', 'kotoa käsin', 'työ kotoa', 'työskentely kotoa', 'kotitoimisto',
     'kotona tehtävä työ', 'monipaikkainen työ', 'monipaikkaisuus', 'remote',
     'remote-first', 'paikkariippumaton', 'paikasta riippumaton', 'mistä tahansa',
     'työskentele mistä tahansa', 'liikkuva työ'],
    'on_site': ['lähityö', 'lähityötä', 'lähityössä', 'toimistolla', 'toimistotyö', 'työpaikalla',
     'paikan päällä', 'läsnäolo toimistolla', 'fyysinen läsnäolo', 'hybridityö',
     'hybridimalli', 'päivää toimistolla', 'päivää viikossa toimistolla',
     'muutto vaaditaan', 'asuinpaikka', 'toimipaikka', 'toimistomme',
     'työpaikka sijaitsee'],
    'not_remote': ['ei etätyötä', 'ei etätyömahdollisuutta', 'etätyö ei ole mahdollista',
     'ei mahdollisuutta etätyöhön', 'ei remote', 'vain toimistolla',
     'ainoastaan toimistolla', 'pelkästään lähityötä', 'vain lähityötä',
     'läsnäolo pakollinen', '100% lähityötä'],
    'other_language_required': ['sujuva suomi', 'sujuva suomen kieli', 'hyvä suomen kielen taito',
     'erinomainen suomen kielen taito', 'suomen kielen taito', 'suomi äidinkielenä',
     'äidinkielenä suomi', 'suomea vaaditaan', 'suomen kieli vaaditaan', 'suomi c1',
     'suomi b2', 'suomenkielinen', 'ruotsin kielen taito', 'ruotsia', 'kaksikielinen'],
    'no_sponsorship': ['ei viisumia', 'ei viisumitukea', 'ei sponsorointia', 'työlupa vaaditaan',
     'voimassa oleva työlupa', 'oleskelulupa vaaditaan', 'vain eu-kansalaiset',
     'eu-kansalaisuus', 'oikeus työskennellä suomessa', 'ei muuttotukea'],
    'unpaid': ['palkaton', 'palkatta', 'ilman palkkaa', 'ei palkkaa', 'ei korvausta',
     'ilman korvausta', 'vapaaehtoistyö', 'palkaton harjoittelu', 'omakustanteinen',
     'vain kulukorvaus'],
    'thesis': ['opinnäytetyö', 'diplomityö', 'pro gradu', 'gradu', 'väitöskirja', 'lopputyö'],
    'internship': ['harjoittelu', 'harjoittelija', 'työharjoittelu', 'trainee', 'traineeohjelma',
     'oppisopimus', 'vastavalmistunut'],
    'part_time': ['osa-aikainen', 'osa-aikatyö', 'osa-aikaisesti', 'tuntia viikossa', 'iltatyö'],
    'wrong_level': ['johtaja', 'osastopäällikkö', 'tiiminvetäjä', 'tiimipäällikkö', 'päällikkö', 'esimies',
     'toimitusjohtaja', 'johtoryhmä', 'esimieskokemus', 'junior', 'nuorempi',
     'vastavalmistun', 'trainee'],
}

LUXEMBOURGISH: dict = {
    'name': 'Luxembourgish',
    'english_mention': ['englesch'],
    'remote': ['doheem schaffen', 'vun doheem', 'heemaarbecht', 'télétravail', 'remote', 'op distanz',
     'aus der distanz'],
    'on_site': ['op der plaz', 'am büro', 'präsenz', 'hybridaarbecht'],
    'not_remote': ['kee remote', 'keng heemaarbecht', 'nëmmen am büro'],
    'other_language_required': ['lëtzebuergesch', 'lëtzebuergesch erfuerderlech', 'lëtzebuergesch geschwat',
     'luxembourgeois', 'letzeburgesch'],
    'no_sponsorship': ['keng visa', 'keng ënnerstëtzung fir visa'],
    'unpaid': ['onbezuelt', 'ouni bezuelung'],
    'thesis': ['ofschlossaarbecht', 'thesis'],
    'internship': ['stage', 'stagiaire', 'praktikum'],
    'part_time': ['deelzäit', 'temps partiel'],
    'wrong_level': ['chef', 'direkter', 'leeder', 'junior', 'absolvent', 'debutant'],
}

POLISH: dict = {
    'name': 'Polish',
    'english_mention': ['angielsk', 'english'],
    'remote': ['praca zdalna', 'zdalnie', 'zdalna', 'praca z domu', 'home office', 'remote',
     'w pełni zdalnie', 'elastyczne miejsce pracy'],
    'on_site': ['stacjonarnie', 'praca stacjonarna', 'w biurze', 'hybrydowo', 'praca hybrydowa',
     'miejsce pracy', 'w naszym biurze'],
    'not_remote': ['bez pracy zdalnej', 'brak pracy zdalnej', 'tylko stacjonarnie',
     'wyłącznie stacjonarnie'],
    'other_language_required': ['język polski', 'znajomość polskiego', 'biegła polszczyzna', 'polski w mowie i piśmie'],
    'no_sponsorship': ['bez sponsorowania wizy', 'wymagane pozwolenie na pracę'],
    'unpaid': ['bezpłatny', 'bezpłatne praktyki', 'wolontariat', 'nieodpłatnie'],
    'thesis': ['praca dyplomowa', 'praca magisterska'],
    'internship': ['staż', 'stażysta', 'praktyki', 'praktykant'],
    'part_time': ['niepełny etat', 'pół etatu', 'godzin tygodniowo'],
    'wrong_level': ['kierownik', 'dyrektor', 'menedżer', 'lider zespołu', 'regular', 'junior', 'młodszy',
     'absolwent', 'bez doświadczenia', 'pierwsza praca'],
}

LANGUAGES: dict = {
    'en': ENGLISH,
    'pl': POLISH,
    'de': GERMAN,
    'nl': DUTCH,
    'fr': FRENCH,
    'it': ITALIAN,
    'es': SPANISH,
    'pt': PORTUGUESE,
    'sv': SWEDISH,
    'no': NORWEGIAN,
    'da': DANISH,
    'fi': FINNISH,
    'lb': LUXEMBOURGISH,
}



# --------------------------------------------------------------------------------------
# Every accented term also has to match its unaccented spellings, because job ads write
# both. Sina's requirement, and it is not cosmetic: 463 of the 1,697 terms below carry a
# character outside ASCII, and a posting that writes "Prasenzpflicht" or "praesenzpflicht"
# instead of "Präsenzpflicht" would otherwise sail past the rule that exists to catch it.
# Scrapers strip diacritics, HTML entities get mangled, and people simply type without
# them.
#
# There are TWO conventions and real text uses both, so both are generated:
#
#     strip     ä -> a    ö -> o    ü -> u    å -> a    ø -> o    ß -> ss
#     expand    ä -> ae   ö -> oe   ü -> ue   å -> aa   ø -> oe   æ -> ae
#
# German and the Nordic languages use the expanded form when a keyboard has no umlaut
# ("Buero" for "Büro"); Romance languages simply drop the accent ("ingles" for "inglés").
# Generating both costs nothing and covers whichever the posting used.
#
# Generated rather than hand-written on purpose: 463 hand-typed duplicates would be wrong
# somewhere, and a term added later would silently miss its variants.
_STRIP_MAP = {
    'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss', 'å': 'a', 'ø': 'o', 'æ': 'ae',
    'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a',
    'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
    'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
    'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o',
    'ú': 'u', 'ù': 'u', 'û': 'u',
    'ç': 'c', 'ñ': 'n', 'ý': 'y', 'ÿ': 'y', 'ð': 'd', 'þ': 'th',
}
_EXPAND_MAP = dict(_STRIP_MAP)
_EXPAND_MAP.update({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'å': 'aa', 'ø': 'oe'})


def _fold(term: str, mapping: dict) -> str:
    return ''.join(mapping.get(ch, ch) for ch in term)


def _with_ascii_variants(terms: list) -> list:
    """The list, plus the unaccented spellings of anything that has an accent."""
    out: list = []
    seen: set = set()
    for term in terms:
        for variant in (term, _fold(term, _STRIP_MAP), _fold(term, _EXPAND_MAP)):
            if variant and variant not in seen:
                seen.add(variant)
                out.append(variant)
    return out




# The languages a country's job ads are actually written in. English is on every one of
# them: in all 18 of these countries a large share of technical ads is written in English,
# and after translation every listing is read in English anyway.
COUNTRY_LANGUAGES = {
    'Italy': ('it', 'en'),
    'Denmark': ('da', 'en'),
    'Finland': ('fi', 'sv', 'en'),
    'Norway': ('no', 'en'),
    'Sweden': ('sv', 'en'),
    'Austria': ('de', 'en'),
    'Belgium': ('nl', 'fr', 'de', 'en'),
    'France': ('fr', 'en'),
    'Germany': ('de', 'en'),
    'Netherlands': ('nl', 'en'),
    'Luxembourg': ('fr', 'de', 'lb', 'en'),
    'Switzerland': ('de', 'fr', 'it', 'en'),
    'Portugal': ('pt', 'en'),
    'Spain': ('es', 'en'),
    'United Kingdom': ('en',),
    'United States': ('en',),
    'Canada': ('en', 'fr'),
    'Australia': ('en',),
}

# A city the wizard offers, mapped to the country whose vocabulary its ads use.
CITY_LANGUAGES = {
    'Amsterdam': ('nl', 'en'),
    'Berlin': ('de', 'en'),
    'Vienna': ('de', 'en'),
    'Oslo': ('no', 'en'),
    'Copenhagen': ('da', 'en'),
    'Milan': ('it', 'en'),
    'Turin': ('it', 'en'),
}

SECTIONS = ('remote', 'on_site', 'not_remote', 'other_language_required',
            'no_sponsorship', 'unpaid', 'wrong_level', 'thesis', 'internship', 'part_time',
            'english_mention')


# Run last, once SECTIONS names every list to expand. See _with_ascii_variants above for
# why both the stripped and the expanded spelling are generated.
for _language in LANGUAGES.values():
    for _section in SECTIONS:
        _language[_section] = _with_ascii_variants(_language[_section])


# What lingua answers, mapped to the vocabulary that answer should load. lingua is
# configured with exactly the languages this app searches (see language.py), so the only
# gaps are Norwegian -- it reports Bokmal, 'nb' -- and Polish, which has no vocabulary of
# its own here and therefore falls back to the country's set.
DETECTED_TO_VOCABULARY = {
    'en': 'en', 'de': 'de', 'nl': 'nl', 'fr': 'fr', 'it': 'it', 'es': 'es',
    'pt': 'pt', 'sv': 'sv', 'da': 'da', 'fi': 'fi',
    'no': 'no', 'nb': 'no', 'nn': 'no',
    'lb': 'lb', 'pl': 'pl',
}


def languages_for(country=None, location=None, detected=None) -> tuple:
    """Which language vocabularies apply to a listing.

    When the listing's own language has been detected and this module has a vocabulary for
    it, that vocabulary is what gets loaded -- Sina's design, and it is both more precise
    and much cheaper than the alternative: a Belgian listing used to be checked against
    Dutch, French, German and English all at once, so a French phrase could fire on a Dutch
    advert.

    English is loaded alongside it, and that is deliberate rather than a hedge. Job ads in
    these countries mix English into the local language constantly -- a Dutch posting
    saying "op kantoor" may also say "fully remote" in English, and the remote signal is
    what STOPS the on-site words from deleting it. Dropping English here would delete that
    listing for a phrase its own text contradicts. Two vocabularies, not four.

    With no detection (or a language with no vocabulary of its own, such as Polish), every
    language the country's ads are written in is loaded, exactly as before -- an unknown
    language must never mean "no vocabulary at all", which would silently disable every
    rule for that listing.
    """
    vocabulary = DETECTED_TO_VOCABULARY.get(str(detected or '').strip().lower())
    if vocabulary:
        return (vocabulary,) if vocabulary == 'en' else (vocabulary, 'en')

    codes: list = []
    for key, mapping in ((location, CITY_LANGUAGES), (country, COUNTRY_LANGUAGES)):
        for code in mapping.get(str(key or '').strip(), ()):
            if code not in codes:
                codes.append(code)
    if not codes:
        # An unknown or missing country must never mean "no vocabulary at all" -- that
        # would silently disable every rule for the listing. Everything is checked.
        return tuple(LANGUAGES)
    if 'en' not in codes:
        codes.append('en')
    return tuple(codes)


def terms_for(section: str, country=None, location=None, detected=None) -> list:
    """Every term in `section`, for the languages that apply to this listing."""
    if section not in SECTIONS:
        raise KeyError(section)
    out: list = []
    seen = set()
    for code in languages_for(country, location, detected):
        for term in LANGUAGES[code][section]:
            if term not in seen:
                seen.add(term)
                out.append(term)
    return out


# The one section read against the TITLE only -- the same as the Junior profile's
# _SECTION_SCOPE in rules.py, and for the same reason: matched against a whole advert,
# "manager" is the hiring manager and "hoofd" is head office. A level word describes the job
# only in the job's own title.
SECTION_SCOPE = {'wrong_level': 'title'}
