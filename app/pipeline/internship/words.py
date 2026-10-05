# -*- coding: utf-8 -*-
"""The Internship module's own vocabulary. Shared with nothing.

Sina's instruction: Job, Thesis and Internship are three parallel modules with nothing
whatsoever in common -- "نه دیکشنری مشترک نه هیچی". So this file, thesis/words.py and
country_rules.py have the same shape and none of the same contents, and none of the three
imports another. Each can be tuned or broken without touching the other two.

The repetition between the three is deliberate and must stay. A later reader who merges them
back together to save duplication reintroduces exactly the failure this prevents.

WHY THE TITLE IS ENOUGH

An advert offering an internship says so in its title. One that merely mentions the word is
something else entirely, and every false positive measured over 5,468 real listings came
from a body:

    "Let op: dit is geen stageplek"          -- Dutch for "this is NOT an internship"
    "in partnership with the Co-Op"          -- the supermarket
    "we connect learners to apprenticeships" -- what the company sells
    "Positionsebene Berufseinstieg"          -- a metadata field on Austrian boards

Reading titles is what lets `stageplek` and `co-op` be in this list at all: over there they
were unusable, here they are exactly right.

WORDS DELIBERATELY LEFT OUT

    ausbildung / auszubildende   German for vocational training, and for "education" in the
                                 requirements of nearly every German advert. Measured: it
                                 labelled 1,227 of 1,491 listings on a real Austrian search.
    berufseinstieg               a metadata field far more often than a role.
"""
from __future__ import annotations

import re
import unicodedata


# Which languages a listing's words are read in -- this module's own copy, covering the
# eighteen countries Job Finder searches.
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

CITY_LANGUAGES = {
    'Milan': ('it', 'en'), 'Milano': ('it', 'en'),
    'Turin': ('it', 'en'), 'Torino': ('it', 'en'),
    'Brussels': ('nl', 'fr', 'en'), 'Bruxelles': ('nl', 'fr', 'en'),
    'Zurich': ('de', 'en'), 'Zürich': ('de', 'en'),
    'Geneva': ('fr', 'en'), 'Genève': ('fr', 'en'),
    'Vienna': ('de', 'en'), 'Wien': ('de', 'en'),
    'Graz': ('de', 'en'), 'Villach': ('de', 'en'), 'Linz': ('de', 'en'),
    'Amsterdam': ('nl', 'en'), 'Rotterdam': ('nl', 'en'), 'Eindhoven': ('nl', 'en'),
    'Helsinki': ('fi', 'sv', 'en'),
    'Stockholm': ('sv', 'en'), 'Oslo': ('no', 'en'), 'Copenhagen': ('da', 'en'),
}


# ---------------------------------------------------------------------------------------
# The words
# ---------------------------------------------------------------------------------------
#
# `internship` is read from the TITLE and says what a posting is. The other four are read
# from the whole posting and say what to do about it.

ENGLISH = {
    'internship': [
        'intern', 'interns', 'internship', 'internships', 'internship programme',
        'internship program', 'summer internship', 'winter internship',
        'spring internship', 'intern position', 'intern role', 'student intern',
        'research intern', 'industrial placement', 'work placement',
        'student placement', 'placement year', 'sandwich year', 'sandwich placement',
        'year in industry', 'industrial year', 'trainee', 'traineeship',
        'graduate scheme', 'graduate programme', 'graduate program',
        'apprenticeship', 'apprentice', 'working student', 'student assistant',
        'student worker', 'student job', 'co-op', 'coop', 'co op',
        'cooperative education', 'summer analyst', 'summer associate', 'summer student',
        'praktikum',            # German boards post English titles with the German word
    ],
    'remote': [
        'remote', 'remotely', 'fully remote', '100% remote', 'remote-first', 'remote first',
        'remote only', 'remote-friendly', 'work from home', 'work-from-home', 'wfh',
        'work from anywhere', 'home office', 'home-office', 'homeoffice',
        'telecommute', 'telecommuting', 'telework', 'teleworking', 'distributed team',
        'anywhere in europe', 'location independent', 'virtual internship',
        'remote internship', 'can be done remotely', 'from home',
    ],
    'on_site': [
        'on-site', 'onsite', 'on site', 'in-office', 'in office', 'in-person', 'in person',
        'office-based', 'office based', 'hybrid', 'on our premises', 'on campus',
        'at our office', 'at our site', 'presence required', 'days in the office',
        'days per week in the office', 'relocation required', 'commuting distance',
        'within commuting', 'in our laboratory', 'in our lab',
    ],
    'not_remote': [
        'no remote', 'not remote', 'remote is not', 'remote work is not',
        'no home office', 'no work from home', 'not available remotely',
        'cannot be done remotely', 'this is not a remote', 'no remote option',
        'remote working is not', 'no telework', 'must be on-site', 'must be onsite',
        'strictly on-site', 'strictly onsite', 'fully on-site', 'fully onsite',
        'on-site only', 'onsite only', 'office attendance is mandatory',
    ],
    'unpaid': [
        'unpaid', 'un-paid', 'non-paid', 'not paid', 'without pay', 'without salary',
        'no salary', 'no remuneration', 'no compensation', 'voluntary basis', 'volunteer',
        'self-funded', 'self funded', 'at your own expense', 'equity only', 'equity-only',
        'expenses only', 'no financial compensation', 'this is an unpaid',
        'unpaid internship',
    ],
    'other_language_required': [],       # English is the language Sina reads
    'english_mention': [
        'english',
    ],
}

GERMAN = {
    'internship': [
        'praktikum', 'praktikums', 'praktikant', 'praktikantin', 'praktikanten',
        'pflichtpraktikum', 'pflichtpraktikant', 'ferialpraktikum', 'ferialpraktikant',
        'berufspraktikum', 'sommerpraktikum', 'praktikumsplatz', 'praktikumsstelle',
        'fachpraktikum', 'industriepraktikum', 'forschungspraktikum',
        'werkstudent', 'werkstudentin', 'werkstudierende', 'werkstudententaetigkeit',
        'studentische hilfskraft', 'studentische aushilfe', 'studentenjob',
        'trainee', 'traineeprogramm', 'traineestelle', 'volontariat', 'volontaer',
        'volontär', 'schnupperpraktikum',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'praxissemester', 'abschlusspraktikum', 'praxisphase', 'freiwilliges praktikum',
    ],
    'remote': [
        'remote', 'homeoffice', 'home office', 'home-office', 'heimarbeit',
        'mobiles arbeiten', 'mobile arbeit', 'telearbeit', 'von zu hause',
        'ortsunabhaengig', 'ortsunabhängig', 'ortsungebunden', 'remote-freundlich',
        'vollstaendig remote', 'vollständig remote', 'komplett remote',
        'remote moeglich', 'remote möglich', 'homeoffice moeglich', 'homeoffice möglich',
        'von ueberall', 'von überall',
    ],
    'on_site': [
        'vor ort', 'praesenz', 'präsenz', 'praesenzpflicht', 'präsenzpflicht',
        'im buero', 'im büro', 'hybrid', 'hybrides arbeiten', 'anwesenheit erforderlich',
        'tage im buero', 'tage im büro', 'am standort', 'in unserem buero',
        'in unserem büro', 'umzug erforderlich', 'im labor', 'laborarbeit',
    ],
    'not_remote': [
        'kein homeoffice', 'kein home office', 'keine remote', 'nicht remote',
        'kein remote', 'nicht im homeoffice', 'remote nicht moeglich',
        'remote nicht möglich', 'homeoffice nicht moeglich', 'homeoffice nicht möglich',
        'ausschliesslich vor ort', 'ausschließlich vor ort', 'nur vor ort',
        'keine telearbeit',
    ],
    'unpaid': [
        'unbezahlt', 'unbezahltes', 'unbezahltes praktikum', 'ohne bezahlung',
        'ohne verguetung', 'ohne vergütung', 'unentgeltlich', 'ehrenamtlich',
        'freiwilligenarbeit', 'keine verguetung', 'keine vergütung', 'nicht verguetet',
        'nicht vergütet', 'auf eigene kosten', 'selbst finanziert',
    ],
    'other_language_required': [
        'deutschkenntnisse', 'sehr gute deutschkenntnisse', 'deutsch in wort und schrift',
        'verhandlungssicheres deutsch', 'fliessend deutsch', 'fließend deutsch',
        'deutsch als muttersprache', 'muttersprachliche deutschkenntnisse',
        'deutsch erforderlich', 'deutsch zwingend', 'sehr gutes deutsch',
        'gute deutschkenntnisse',
    ],
    'english_mention': [
        'englisch',
        'englischkenntnisse',
        'english',
    ],
}

DUTCH = {
    'internship': [
        'stage', 'stages', 'stagiair', 'stagiaire', 'stageplek', 'stageplaats',
        'stageopdracht', 'stageperiode', 'meeloopstage', 'onderzoeksstage',
        'snuffelstage', 'bedrijfsstage', 'stagiar', 'stagair', 'afstudeerstage',
        'werkstudent', 'studentenbaan', 'bijbaan student', 'studentassistent',
        'trainee', 'traineeship', 'traineeprogramma', 'starterstraject',
        'werkervaringsplaats', 'leerwerkplek', 'stagevacature',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'meewerkstage', 'studentmedewerker',
    ],
    'remote': [
        'remote', 'thuiswerken', 'thuiswerk', 'vanuit huis', 'op afstand',
        'thuiswerkdagen', 'thuiswerkvergoeding', 'volledig remote',
        'volledig thuiswerken', 'plaatsonafhankelijk', 'telewerken',
        'thuiswerkmogelijkheden',
    ],
    'on_site': [
        'op kantoor', 'op locatie', 'op de locatie', 'hybride', 'aanwezigheid vereist',
        'dagen op kantoor', 'op ons kantoor', 'standplaats', 'verhuizing vereist',
        'in persoon', 'in het lab',
    ],
    'not_remote': [
        'geen thuiswerk', 'niet thuiswerken', 'geen remote', 'niet remote',
        'thuiswerken is niet', 'remote is niet mogelijk', 'uitsluitend op kantoor',
        'alleen op kantoor', 'volledig op kantoor',
    ],
    'unpaid': [
        'onbetaald', 'onbetaalde', 'zonder vergoeding', 'geen vergoeding',
        'vrijwillig', 'vrijwilligerswerk', 'onbezoldigd', 'geen stagevergoeding',
        'op eigen kosten',
    ],
    'other_language_required': [
        'nederlands vereist', 'goede beheersing van het nederlands',
        'vloeiend nederlands', 'nederlands in woord en geschrift',
        'nederlands als moedertaal', 'moedertaal nederlands',
        'nederlandse taal vereist', 'goede kennis van het nederlands',
    ],
    'english_mention': [
        'engels',
        'engelse',
        'english',
    ],
}

FRENCH = {
    'internship': [
        'stage', 'stages', 'stagiaire', 'stagiaires', 'stage conventionne',
        'stage conventionné', 'stage de fin d etudes', "stage de fin d'etudes",
        'stage de cesure', 'stage de césure', 'stage ouvrier', 'stage de master',
        'stage ingenieur', 'stage ingénieur', 'stage etudiant', 'stage étudiant',
        'alternance', 'alternant', 'alternante', 'apprentissage', 'apprenti', 'apprentie',
        "contrat d'apprentissage", 'contrat de professionnalisation',
        'etudiant en alternance', 'étudiant en alternance', 'stage d ete', "stage d'ete",
    ],
    'remote': [
        'teletravail', 'télétravail', 'a distance', 'à distance', 'remote',
        'travail a domicile', 'travail à domicile', 'depuis chez vous', 'de chez vous',
        '100% teletravail', '100% télétravail', 'full remote', 'entierement a distance',
        'entièrement à distance',
    ],
    'on_site': [
        'sur site', 'sur place', 'au bureau', 'en presentiel', 'en présentiel',
        'hybride', 'presence requise', 'présence requise', 'jours au bureau',
        'dans nos locaux', 'demenagement requis', 'déménagement requis',
        'au laboratoire',
    ],
    'not_remote': [
        'pas de teletravail', 'pas de télétravail', 'sans teletravail',
        'sans télétravail', 'aucun teletravail', 'aucun télétravail',
        'uniquement sur site', 'exclusivement sur site', '100% presentiel',
        '100% présentiel',
    ],
    'unpaid': [
        'non remunere', 'non rémunéré', 'non remuneree', 'non rémunérée',
        'sans remuneration', 'sans rémunération', 'benevole', 'bénévole',
        'benevolat', 'bénévolat', 'aucune remuneration', 'aucune rémunération',
        'a vos frais', 'stage non remunere', 'stage non rémunéré',
    ],
    'other_language_required': [
        'francais courant', 'français courant', 'maitrise du francais',
        'maîtrise du français', 'francais requis', 'français requis',
        'francais langue maternelle', 'français langue maternelle',
        'bilingue francais', 'bilingue français',
    ],
    'english_mention': [
        'anglais',
        'anglaise',
        'english',
    ],
}

ITALIAN = {
    'internship': [
        'tirocinio', 'tirocinante', 'tirocini', 'tirocinio curriculare',
        'tirocinio extracurriculare', 'tirocinio formativo', 'stage', 'stagista',
        'stage curriculare', 'stage extracurriculare', 'stage estivo',
        'apprendistato', 'apprendista', 'praticante', 'studente lavoratore',
        'programma di tirocinio', 'internship', 'stage aziendale',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'praticantato',
    ],
    'remote': [
        'da remoto', 'in remoto', 'remoto', 'lavoro da casa', 'smart working',
        'telelavoro', 'lavoro agile', 'completamente da remoto', 'full remote',
        'da qualsiasi luogo',
    ],
    'on_site': [
        'in sede', 'presso la sede', 'in ufficio', 'in presenza', 'ibrido',
        'presenza richiesta', 'giorni in ufficio', 'nei nostri uffici',
        'trasferimento richiesto', 'in laboratorio',
    ],
    'not_remote': [
        'no smart working', 'niente smart working', 'non da remoto', 'no remoto',
        'solo in sede', 'esclusivamente in sede', 'unicamente in sede',
        'senza smart working', '100% in presenza',
    ],
    'unpaid': [
        'non retribuito', 'non retribuita', 'senza retribuzione', 'nessun compenso',
        'senza compenso', 'volontario', 'volontariato', 'a titolo gratuito',
        'nessun rimborso', 'tirocinio non retribuito',
    ],
    'other_language_required': [
        'italiano fluente', 'ottima conoscenza dell italiano',
        "ottima conoscenza dell'italiano", 'italiano madrelingua',
        'madrelingua italiana', 'italiano richiesto', 'lingua italiana richiesta',
    ],
    'english_mention': [
        'inglese',
        'english',
    ],
}

SPANISH = {
    'internship': [
        'practicas', 'prácticas', 'practicante', 'becario', 'becaria',
        'beca de practicas', 'beca de prácticas', 'practicas curriculares',
        'prácticas curriculares', 'practicas extracurriculares',
        'prácticas extracurriculares', 'contrato en practicas',
        'contrato en prácticas', 'practicas de verano', 'prácticas de verano',
        'practicas profesionales', 'prácticas profesionales',
        'estudiante en practicas', 'estudiante en prácticas', 'aprendiz',
        'programa de talento joven', 'internship', 'trainee',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'pasante',
    ],
    'remote': [
        'remoto', 'en remoto', 'teletrabajo', 'trabajo desde casa', 'desde casa',
        'a distancia', '100% remoto', 'totalmente remoto', 'trabajo remoto',
        'desde cualquier lugar',
    ],
    'on_site': [
        'presencial', 'en la oficina', 'en nuestras oficinas', 'hibrido', 'híbrido',
        'presencia requerida', 'dias en la oficina', 'días en la oficina', 'en sede',
        'traslado requerido', 'en el laboratorio',
    ],
    'not_remote': [
        'sin teletrabajo', 'no teletrabajo', 'no hay teletrabajo', 'no remoto',
        'sin opcion de teletrabajo', 'sin opción de teletrabajo', '100% presencial',
        'totalmente presencial', 'solo presencial',
    ],
    'unpaid': [
        'no remunerado', 'no remunerada', 'sin remuneracion', 'sin remuneración',
        'sin sueldo', 'sin salario', 'voluntario', 'voluntariado', 'no retribuido',
        'practicas no remuneradas', 'prácticas no remuneradas',
    ],
    'other_language_required': [
        'espanol fluido', 'español fluido', 'castellano fluido',
        'nivel nativo de espanol', 'nivel nativo de español', 'espanol nativo',
        'español nativo', 'imprescindible espanol', 'imprescindible español',
    ],
    'english_mention': [
        'ingles',
        'inglés',
        'english',
    ],
}

PORTUGUESE = {
    'internship': [
        'estagio', 'estágio', 'estagiario', 'estagiário', 'estagiaria', 'estagiária',
        'estagio curricular', 'estágio curricular', 'estagio profissional',
        'estágio profissional', 'estagio de verao', 'estágio de verão',
        'programa de estagios', 'programa de estágios', 'estagio de investigacao',
        'estágio de investigação', 'aprendiz', 'trainee', 'internship',
    ],
    'remote': [
        'remoto', 'trabalho remoto', 'em casa', 'a partir de casa', 'teletrabalho',
        'trabalho a distancia', 'trabalho à distância', '100% remoto',
        'totalmente remoto', 'de qualquer lugar',
    ],
    'on_site': [
        'presencial', 'no escritorio', 'no escritório', 'nos nossos escritorios',
        'nos nossos escritórios', 'hibrido', 'híbrido', 'presenca obrigatoria',
        'presença obrigatória', 'no laboratorio', 'no laboratório',
    ],
    'not_remote': [
        'sem teletrabalho', 'nao remoto', 'não remoto', 'sem trabalho remoto',
        '100% presencial', 'totalmente presencial', 'apenas presencial',
    ],
    'unpaid': [
        'nao remunerado', 'não remunerado', 'sem remuneracao', 'sem remuneração',
        'voluntario', 'voluntário', 'voluntariado', 'sem vencimento',
        'estagio nao remunerado', 'estágio não remunerado',
    ],
    'other_language_required': [
        'portugues fluente', 'português fluente', 'dominio do portugues',
        'domínio do português', 'portugues nativo', 'português nativo',
        'lingua portuguesa obrigatoria', 'língua portuguesa obrigatória',
    ],
    'english_mention': [
        'ingles',
        'inglês',
        'english',
    ],
}

SWEDISH = {
    'internship': [
        'praktik', 'praktikplats', 'praktikant', 'sommarpraktik', 'lia',
        'larande i arbete', 'lärande i arbete', 'trainee', 'traineeprogram',
        'traineeprogrammet', 'studentmedarbetare', 'extrajobb student',
        'sommarjobb student', 'studentassistent', 'internship', 'praktikperiod',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'praktikantplats',
    ],
    'remote': [
        'distans', 'pa distans', 'på distans', 'distansarbete', 'hemifran',
        'hemifrån', 'jobba hemifran', 'jobba hemifrån', 'remote', 'helt pa distans',
        'helt på distans',
    ],
    'on_site': [
        'pa plats', 'på plats', 'pa kontoret', 'på kontoret', 'hybrid',
        'narvaro kravs', 'närvaro krävs', 'dagar pa kontoret', 'dagar på kontoret',
    ],
    'not_remote': [
        'inget distansarbete', 'ingen distans', 'ej distans', 'inte pa distans',
        'inte på distans', 'endast pa plats', 'endast på plats',
    ],
    'unpaid': [
        'obetald', 'obetalt', 'utan lon', 'utan lön', 'ingen lon', 'ingen lön',
        'ideellt', 'volontar', 'volontär', 'ingen ersattning', 'ingen ersättning',
        'obetald praktik',
    ],
    'other_language_required': [
        'flytande svenska', 'goda kunskaper i svenska', 'svenska kravs',
        'svenska krävs', 'svenska i tal och skrift', 'modersmal svenska',
        'modersmål svenska',
    ],
    'english_mention': [
        'engelska',
        'english',
    ],
}

NORWEGIAN = {
    'internship': [
        'praksis', 'praksisplass', 'praktikant', 'internship', 'trainee',
        'traineeprogram', 'traineeprogrammet', 'studentassistent',
        'sommerjobb for studenter', 'sommerstudent', 'laerling', 'lærling',
        'laerlingplass', 'lærlingplass', 'praksisopphold',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'studentjobb', 'praktikplass',
    ],
    'remote': [
        'hjemmekontor', 'fjernarbeid', 'remote', 'jobbe hjemmefra', 'hjemmefra',
        'pa avstand', 'på avstand', 'helt remote',
    ],
    'on_site': [
        'pa kontoret', 'på kontoret', 'pa stedet', 'på stedet', 'hybrid',
        'tilstedevaerelse kreves', 'tilstedeværelse kreves',
    ],
    'not_remote': [
        'ikke hjemmekontor', 'ingen hjemmekontor', 'ikke remote', 'ikke fjernarbeid',
        'kun pa kontoret', 'kun på kontoret',
    ],
    'unpaid': [
        'ulonnet', 'ulønnet', 'uten lonn', 'uten lønn', 'ingen lonn', 'ingen lønn',
        'frivillig', 'ingen godtgjorelse', 'ingen godtgjørelse',
    ],
    'other_language_required': [
        'flytende norsk', 'gode norskkunnskaper', 'norsk kreves',
        'norsk muntlig og skriftlig', 'morsmal norsk', 'morsmål norsk',
    ],
    'english_mention': [
        'engelsk',
        'english',
    ],
}

DANISH = {
    'internship': [
        'praktik', 'praktikplads', 'praktikant', 'praktikophold', 'praktikforloeb',
        'praktikforløb', 'studiejob', 'studentermedhjaelper', 'studentermedhjælper',
        'trainee', 'traineeforloeb', 'traineeforløb', 'elevplads', 'laerling',
        'lærling', 'internship',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'studenterjob',
    ],
    'remote': [
        'hjemmearbejde', 'hjemmefra', 'arbejde hjemmefra', 'remote', 'fjernarbejde',
        'distancearbejde', 'helt remote',
    ],
    'on_site': [
        'pa kontoret', 'på kontoret', 'pa stedet', 'på stedet', 'hybrid',
        'fysisk tilstedevaerelse', 'fysisk tilstedeværelse',
    ],
    'not_remote': [
        'ikke hjemmearbejde', 'intet hjemmearbejde', 'ikke remote',
        'kun pa kontoret', 'kun på kontoret',
    ],
    'unpaid': [
        'ulonnet', 'ulønnet', 'uden lon', 'uden løn', 'ingen lon', 'ingen løn',
        'frivillig', 'frivilligt arbejde', 'ingen betaling', 'ulonnet praktik',
        'ulønnet praktik',
    ],
    'other_language_required': [
        'flydende dansk', 'gode danskkundskaber', 'dansk kraeves', 'dansk kræves',
        'dansk i skrift og tale', 'modersmal dansk', 'modersmål dansk',
    ],
    'english_mention': [
        'engelsk',
        'english',
    ],
}

FINNISH = {
    'internship': [
        'harjoittelu', 'harjoittelija', 'harjoittelupaikka', 'kesaharjoittelu',
        'kesäharjoittelu', 'kesaharjoittelija', 'kesäharjoittelija',
        'tyoharjoittelu', 'työharjoittelu', 'harjoitteluohjelma', 'trainee',
        'traineeohjelma', 'opiskelija-assistentti', 'kesatyo opiskelijoille',
        'kesätyö opiskelijoille', 'oppisopimus', 'internship',
    ],
    'remote': [
        'etatyo', 'etätyö', 'etana', 'etänä', 'remote', 'kotoa kasin', 'kotoa käsin',
        'taysin etana', 'täysin etänä', 'etatyomahdollisuus', 'etätyömahdollisuus',
    ],
    'on_site': [
        'toimistolla', 'paikan paalla', 'paikan päällä', 'hybridi', 'lasnaolo',
        'läsnäolo', 'paivaa toimistolla', 'päivää toimistolla',
    ],
    'not_remote': [
        'ei etatyota', 'ei etätyötä', 'vain toimistolla', 'ainoastaan toimistolla',
        'ei etatyomahdollisuutta', 'ei etätyömahdollisuutta',
    ],
    'unpaid': [
        'palkaton', 'palkatonta', 'ilman palkkaa', 'ei palkkaa', 'vapaaehtoinen',
        'vapaaehtoistyo', 'vapaaehtoistyö', 'ei korvausta', 'palkaton harjoittelu',
    ],
    'other_language_required': [
        'sujuva suomi', 'sujuvaa suomea', 'suomen kieli vaaditaan',
        'hyva suomen kielen taito', 'hyvä suomen kielen taito', 'suomea vaaditaan',
    ],
    'english_mention': [
        'englanti',
        'englannin',
        'englantia',
        'english',
    ],
}

LUXEMBOURGISH = {
    'internship': [
        'praktikum', 'praktikant', 'stage', 'stagiaire', 'leierplaz', 'léierplaz',
        'leierjong', 'stage professionnel', 'stage de fin d etudes', 'internship',
        'trainee', 'apprentissage',
    ],
    'remote': [
        'teletravail', 'télétravail', 'remote', 'doheem schaffen', 'home office',
        'homeoffice', 'a distance', 'à distance', 'vun doheem',
    ],
    'on_site': [
        'sur site', 'am buro', 'am büro', 'op der plaz', 'hybrid', 'en presentiel',
        'en présentiel', 'presence requise', 'présence requise',
    ],
    'not_remote': [
        'kee teletravail', 'pas de teletravail', 'pas de télétravail',
        'kein homeoffice', 'uniquement sur site',
    ],
    'unpaid': [
        'onbezuelt', 'net bezuelt', 'non remunere', 'non rémunéré', 'benevole',
        'bénévole', 'sans remuneration', 'sans rémunération',
    ],
    'other_language_required': [
        'letzebuergesch erfuerderlech', 'lëtzebuergesch erfuerderlech',
        'luxembourgeois requis', 'luxembourgish required',
        'gutt letzebuergesch', 'gutt lëtzebuergesch',
    ],
    'english_mention': [
        'englesch',
        'anglais',
        'english',
    ],
}

POLISH = {
    'internship': [
        'staz', 'staż', 'stazysta', 'stażysta', 'stazystka', 'stażystka',
        'praktyka', 'praktyki', 'praktykant', 'praktykantka',
        'praktyka studencka', 'praktyki studenckie', 'praktyki zawodowe',
        'staz absolwencki', 'staż absolwencki', 'program stazowy', 'program stażowy',
        'internship', 'trainee',
    ],
    'remote': [
        'zdalnie', 'praca zdalna', 'zdalna', 'z domu', 'praca z domu',
        'w pelni zdalnie', 'w pełni zdalnie', 'remote', 'home office',
    ],
    'on_site': [
        'w biurze', 'stacjonarnie', 'praca stacjonarna', 'hybrydowo',
        'praca hybrydowa', 'obecnosc wymagana', 'obecność wymagana',
    ],
    'not_remote': [
        'bez pracy zdalnej', 'brak pracy zdalnej', 'nie zdalnie',
        'tylko stacjonarnie', 'wylacznie stacjonarnie', 'wyłącznie stacjonarnie',
    ],
    'unpaid': [
        'bezplatny', 'bezpłatny', 'bezplatne', 'bezpłatne', 'nieplatny', 'niepłatny',
        'bez wynagrodzenia', 'wolontariat', 'wolontariusz', 'brak wynagrodzenia',
        'bezplatny staz', 'bezpłatny staż',
    ],
    'other_language_required': [
        'jezyk polski wymagany', 'język polski wymagany', 'biegly polski',
        'biegły polski', 'polski w mowie i pismie',
    ],
    'english_mention': [
        'angielski',
        'angielskiego',
        'angielskim',
        'english',
    ],
}


SECTIONS = ('english_mention', 'internship', 'remote', 'on_site', 'not_remote', 'unpaid',
            'other_language_required')

LANGUAGES = {
    'en': ENGLISH, 'de': GERMAN, 'nl': DUTCH, 'fr': FRENCH, 'it': ITALIAN,
    'es': SPANISH, 'pt': PORTUGUESE, 'sv': SWEDISH, 'no': NORWEGIAN, 'da': DANISH,
    'fi': FINNISH, 'lb': LUXEMBOURGISH, 'pl': POLISH,
}


def _ascii(term: str) -> str:
    """'kesäharjoittelu' -> 'kesaharjoittelu'. Boards strip accents constantly, and a term
    spelled only one way misses every posting that spelled it the other."""
    return ''.join(c for c in unicodedata.normalize('NFD', term)
                   if unicodedata.category(c) != 'Mn')


for _words in LANGUAGES.values():
    for _name in SECTIONS:
        _words[_name] = sorted({t for term in _words[_name] for t in (term, _ascii(term))})


# Terms that must not match inside a longer word. Everything else keeps an open tail so a
# stem finds its inflections -- "praktikum" finds "praktikums", "stagiair" finds
# "stagiaire". These are the ones where an open tail was measured to be wrong:
#
#   intern      -> internal, international, internet
#   coop/co-op  -> co-operation, co-operative
#   stage       -> the English "final stage interview". The word is real in Dutch, French,
#                  Italian and Luxembourgish, and English is always loaded alongside them,
#                  so the tail has to close.
#   lia         -> liability, liaison
#   praktik     -> Swedish/Danish for the placement; open it and it swallows "praktikum",
#                  which belongs to German and is listed there in its own right
#   staz        -> stazione, stazionario
_CLOSED_TAIL = frozenset({
    'intern', 'interns', 'coop', 'co-op', 'co op', 'stage', 'stages', 'lia', 'praktik',
    'staz', 'staż', 'praksis', 'remote', 'remoto', 'distans', 'praktyka', 'praktyki',
    'stagiar', 'stagair',
})


def languages_for(country=None, location=None) -> tuple:
    """Which vocabularies to read a listing with.

    Decided from the country and the city alone, with no language detector, and that is a
    deliberate difference from how the salaried module does it. A title is a handful of
    words -- far too little for a detector to be reliable on -- and this module reads
    titles. An advert whose country is unknown (a global startup board sends plenty) is read
    with every vocabulary rather than one guessed from a sentence, so a German internship on
    an unlabelled board is still found.
    """
    codes: list = []
    for key, mapping in ((location, CITY_LANGUAGES), (country, COUNTRY_LANGUAGES)):
        text = str(key or '').strip().lower()
        if not text:
            continue
        for name, languages in mapping.items():
            if name.lower() in text:
                for code in languages:
                    if code not in codes:
                        codes.append(code)
        if codes:
            break
    if not codes:
        # No country and no recognised city. Everything is read -- an unknown origin must
        # never mean "no vocabulary at all", which would silently find nothing.
        return tuple(LANGUAGES)
    if 'en' not in codes:
        codes.append('en')
    return tuple(codes)


def terms_for(section: str, country=None, location=None) -> list:
    """Every term in `section` for the languages that apply to this listing."""
    if section not in SECTIONS:
        raise KeyError(section)
    out: list = []
    seen = set()
    for code in languages_for(country, location):
        for term in LANGUAGES[code][section]:
            if term not in seen:
                seen.add(term)
                out.append(term)
    return out


_PATTERN_CACHE: dict = {}


def pattern_for(section: str, country=None, location=None):
    """The compiled matcher for one section, for one listing's languages.

    Longest first, so "summer internship" is reported rather than the "internship" inside
    it -- the matched phrase is what the Log shows Sina, and the specific one is more use.
    """
    key = (section, str(country or ''), str(location or ''))
    pattern = _PATTERN_CACHE.get(key)
    if pattern is None:
        parts = [re.escape(term) + (r'\b' if term in _CLOSED_TAIL else '')
                 for term in sorted(terms_for(section, country, location),
                                    key=len, reverse=True)]
        pattern = re.compile(r'\b(?:%s)' % '|'.join(parts)) if parts else re.compile(r'(?!)')
        _PATTERN_CACHE[key] = pattern
    return pattern
