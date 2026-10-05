# -*- coding: utf-8 -*-
"""The Thesis module's own vocabulary. Shared with nothing.

Sina's instruction: Job, Thesis and Internship are three parallel modules that have nothing
whatsoever in common -- "نه دیکشنری مشترک نه هیچی". So this file, internship/words.py and
country_rules.py have the same shape and none of the same contents, and none of the three
imports another. Each can be tuned or broken without touching the other two.

The repetition between the three is deliberate and must stay. A later reader who merges
them back together to save duplication reintroduces exactly the failure this prevents: a
thesis change reaching the salaried rules through a shared helper, silently.

WHAT A THESIS ADVERT LOOKS LIKE, AND WHY THE TITLE IS ENOUGH

An advert offering a thesis says so in its title -- "Master Thesis - Brillouin-Active
Integrated Photonics". One that merely mentions the word is a salaried job talking about
something else, and every false positive measured over 5,468 real listings came from a body:
"Internationale Projektarbeit möglich" is a perk, "Positionsebene Berufseinstieg" is a
metadata field. So `thesis` is read from the title. The other sections describe where the
work happens and what it pays, which belongs in the body, and are read from everything.

WORDS DELIBERATELY LEFT OUT

    ausbildung / auszubildende   German for vocational training, and for "education" in the
                                 requirements of nearly every German advert. Measured: it
                                 labelled 1,227 of 1,491 listings on a real Austrian search.
    promotion                    a doctorate in German, a pay rise in English.
    projektarbeit                a perk on salaried adverts far more often than a thesis.
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

# A city can be more specific than its country -- Belgium loads four languages, and a
# Brussels advert is almost never in German.
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
# `thesis` and `phd` are read from the TITLE and say what a posting is. The other four are
# read from the whole posting and say what to do about it.

ENGLISH = {
    'thesis': [
        'thesis', 'theses', 'master thesis', "master's thesis", 'masters thesis',
        'bachelor thesis', "bachelor's thesis", 'bachelors thesis', 'diploma thesis',
        'thesis project', 'thesis student', 'thesis position', 'thesis internship',
        'thesis work', 'dissertation', 'final year project', 'final-year project',
        'capstone project', 'graduation project', 'graduation assignment',
        'degree project', 'master project', "master's project", 'masters project',
        'student research project',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'msc thesis', 'master thesis project', 'research thesis',
    ],
    'phd': [
        'phd', 'ph.d', 'ph. d', 'doctoral', 'doctorate', 'doctoral candidate',
        'doctoral researcher', 'phd candidate', 'phd position', 'phd student',
        'phd researcher', 'phd thesis', 'doctoral thesis', 'doctoral dissertation',
    ],
    'remote': [
        'remote', 'remotely', 'fully remote', '100% remote', 'remote-first', 'remote first',
        'remote only', 'remote-friendly', 'work from home', 'work-from-home', 'wfh',
        'work from anywhere', 'home office', 'home-office', 'homeoffice',
        'telecommute', 'telecommuting', 'telework', 'teleworking', 'distributed team',
        'anywhere in europe', 'location independent', 'remote thesis',
        'can be done remotely', 'from home', 'virtual placement',
    ],
    'on_site': [
        'on-site', 'onsite', 'on site', 'in-office', 'in office', 'in-person', 'in person',
        'office-based', 'office based', 'hybrid', 'on our premises', 'on campus',
        'at our office', 'at our site', 'presence required', 'days in the office',
        'days per week in the office', 'relocation required', 'commuting distance',
        'within commuting', 'in our laboratory', 'in our lab', 'laboratory work on site',
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
    ],
    'other_language_required': [],       # English is the language Sina reads
    'english_mention': [
        'english',
    ],
    'master': [
        'master thesis',
        "master's thesis",
        'masters thesis',
        'master project',
        "master's project",
        'masters project',
        'msc thesis',
        'm.sc. thesis',
        'graduate thesis',
        'master student',
        "master's student",
    ],
    'bachelor': [
        'bachelor thesis',
        "bachelor's thesis",
        'bachelors thesis',
        'bachelor project',
        "bachelor's project",
        'bsc thesis',
        'b.sc. thesis',
        'undergraduate thesis',
        'bachelor student',
        "bachelor's student",
        'undergraduate student',
    ],
}

GERMAN = {
    'thesis': [
        'masterarbeit', 'master-arbeit', 'masterthesis', 'master thesis',
        'bachelorarbeit', 'bachelor-arbeit', 'bachelorthesis', 'bachelor thesis',
        'diplomarbeit', 'abschlussarbeit', 'abschlussarbeiten', 'studienarbeit',
        'seminararbeit', 'forschungsarbeit', 'examensarbeit', 'abschlussthesis',
        'thesis', 'diplomand', 'diplomandin', 'masterand', 'masterandin',
        'bachelorand', 'bachelorandin',
    ],
    'phd': [
        'doktorarbeit', 'doktorand', 'doktorandin', 'doktorandenstelle',
        'doktoratsstelle', 'doktorat', 'promotionsstelle', 'promotionsvorhaben',
        'dissertation', 'phd', 'ph.d',
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
        'unbezahlt', 'unbezahltes', 'ohne bezahlung', 'ohne verguetung',
        'ohne vergütung', 'unentgeltlich', 'ehrenamtlich', 'freiwilligenarbeit',
        'keine verguetung', 'keine vergütung', 'nicht verguetet', 'nicht vergütet',
        'auf eigene kosten', 'selbst finanziert',
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
    'master': [
        'masterarbeit',
        'master-arbeit',
        'masterthesis',
        'master thesis',
        'diplomarbeit',
        'masterand',
        'masterandin',
        'diplomand',
        'diplomandin',
        'masterstudent',
        'masterstudium',
    ],
    'bachelor': [
        'bachelorarbeit',
        'bachelor-arbeit',
        'bachelorthesis',
        'bachelor thesis',
        'bachelorand',
        'bachelorandin',
        'bachelorstudent',
        'bachelorstudium',
    ],
}

DUTCH = {
    'thesis': [
        'afstudeerscriptie', 'afstudeeropdracht', 'afstudeeronderzoek', 'afstudeerproject',
        'afstudeerstage', 'afstudeerder', 'afstuderen', 'eindscriptie', 'eindopdracht',
        'eindwerk', 'scriptie', 'masterscriptie', 'bachelorscriptie', 'thesis',
        'onderzoeksopdracht', 'afstudeerplek',
    ],
    'phd': ['promovendus', 'promovenda', 'proefschrift', 'promotieonderzoek',
            'promotieplaats', 'phd', 'ph.d', 'doctoraat'],
    'remote': [
        'remote', 'thuiswerken', 'thuiswerk', 'vanuit huis', 'op afstand',
        'thuiswerkdagen', 'thuiswerkvergoeding', 'volledig remote',
        'volledig thuiswerken', 'plaatsonafhankelijk', 'telewerken',
        'thuiswerkmogelijkheden',
    ],
    'on_site': [
        'op kantoor', 'op locatie', 'op de locatie', 'hybride', 'aanwezigheid vereist',
        'dagen op kantoor', 'op ons kantoor', 'standplaats', 'verhuizing vereist',
        'in persoon', 'in het lab', 'in ons laboratorium',
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
    'master': [
        'masterscriptie',
        'masterthesis',
        'master thesis',
        'afstudeerscriptie',
        'masterstudent',
    ],
    'bachelor': [
        'bachelorscriptie',
        'bachelorthesis',
        'bachelor thesis',
        'bachelorstudent',
        'hbo-scriptie',
    ],
}

FRENCH = {
    'thesis': [
        'memoire', 'mémoire', 'memoire de fin', 'mémoire de fin', 'memoire de master',
        'mémoire de master', 'travail de fin d etudes', "travail de fin d'etudes",
        'projet de fin d etudes', "projet de fin d'etudes", 'pfe',
        'projet de recherche etudiant', 'projet de recherche étudiant',
        'memoire de recherche', 'mémoire de recherche',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        "stage de fin d'études", 'stage de fin d’études', 'stage de master',
        "projet de fin d'études",
    ],
    'phd': ['doctorant', 'doctorante', 'these de doctorat', 'thèse de doctorat',
            'doctorat', 'phd', 'ph.d'],
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
        'au laboratoire', 'en laboratoire',
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
        'a vos frais',
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
    'master': [
        'memoire de master',
        'projet de fin d etudes',
        'master 2',
        'niveau master',
        'etudiant en master',
    ],
    'bachelor': [
        'licence',
        'niveau licence',
        'etudiant en licence',
    ],
}

ITALIAN = {
    'thesis': [
        'tesi', 'tesi di laurea', 'tesi magistrale', 'tesi triennale',
        'tesi sperimentale', 'tesi di ricerca', 'tesi aziendale', 'elaborato finale',
        'prova finale', 'progetto di tesi', 'tesista', 'lavoro di tesi',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'tesi di laurea magistrale', 'tirocinio di tesi',
    ],
    'phd': ['dottorato', 'dottorando', 'dottoranda', 'tesi di dottorato', 'phd', 'ph.d'],
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
        'nessun rimborso',
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
    'master': [
        'tesi magistrale',
        'tesi di laurea magistrale',
        'laurea magistrale',
        'studente magistrale',
    ],
    'bachelor': [
        'tesi triennale',
        'laurea triennale',
        'studente triennale',
    ],
}

SPANISH = {
    'thesis': [
        'tesis', 'tesina', 'trabajo fin de grado', 'trabajo de fin de grado',
        'trabajo fin de master', 'trabajo de fin de master', 'trabajo de fin de máster',
        'tfg', 'tfm', 'proyecto fin de carrera', 'proyecto final de carrera',
        'proyecto fin de grado', 'memoria de investigacion', 'memoria de investigación',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'trabajo fin de máster', 'proyecto de fin de máster', 'proyecto de fin de master',
    ],
    'phd': ['tesis doctoral', 'doctorado', 'doctorando', 'doctoranda', 'phd', 'ph.d'],
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
    'master': [
        'trabajo fin de master',
        'trabajo de fin de master',
        'tfm',
        'estudiante de master',
    ],
    'bachelor': [
        'trabajo fin de grado',
        'proyecto fin de grado',
        'tfg',
        'estudiante de grado',
    ],
}

PORTUGUESE = {
    'thesis': [
        'tese', 'tese de mestrado', 'dissertacao', 'dissertação',
        'dissertacao de mestrado', 'dissertação de mestrado', 'monografia',
        'trabalho de conclusao de curso', 'trabalho de conclusão de curso',
        'projeto final de curso', 'projecto final de curso', 'tcc',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'projeto de fim de curso', 'trabalho final de mestrado',
    ],
    'phd': ['tese de doutoramento', 'doutoramento', 'doutorando', 'doutoranda',
            'phd', 'ph.d'],
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
    'master': [
        'dissertacao de mestrado',
        'tese de mestrado',
        'mestrado',
        'estudante de mestrado',
    ],
    'bachelor': [
        'licenciatura',
        'estudante de licenciatura',
        'trabalho de licenciatura',
    ],
}

SWEDISH = {
    'thesis': [
        'examensarbete', 'exjobb', 'examensuppsats', 'kandidatuppsats',
        'magisteruppsats', 'masteruppsats', 'uppsats', 'sjalvstandigt arbete',
        'självständigt arbete', 'examensarbetare', 'thesis',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'examensjobb', 'examensarbete master',
    ],
    'phd': ['doktorand', 'doktorsavhandling', 'forskarutbildning', 'phd', 'ph.d'],
    'remote': [
        'distans', 'pa distans', 'på distans', 'distansarbete', 'hemifran',
        'hemifrån', 'jobba hemifran', 'jobba hemifrån', 'remote', 'helt pa distans',
        'helt på distans',
    ],
    'on_site': [
        'pa plats', 'på plats', 'pa kontoret', 'på kontoret', 'hybrid',
        'narvaro kravs', 'närvaro krävs', 'dagar pa kontoret', 'dagar på kontoret',
        'i laboratoriet',
    ],
    'not_remote': [
        'inget distansarbete', 'ingen distans', 'ej distans', 'inte pa distans',
        'inte på distans', 'endast pa plats', 'endast på plats',
    ],
    'unpaid': [
        'obetald', 'obetalt', 'utan lon', 'utan lön', 'ingen lon', 'ingen lön',
        'ideellt', 'volontar', 'volontär', 'ingen ersattning', 'ingen ersättning',
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
    'master': [
        'masteruppsats',
        'magisteruppsats',
        'masterexamen',
        'masterstudent',
    ],
    'bachelor': [
        'kandidatuppsats',
        'kandidatexamen',
        'kandidatstudent',
    ],
}

NORWEGIAN = {
    'thesis': [
        'masteroppgave', 'bacheloroppgave', 'masteravhandling', 'prosjektoppgave',
        'semesteroppgave', 'hovedoppgave', 'avhandling', 'thesis',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'masterprosjekt',
    ],
    'phd': ['doktorgrad', 'doktoravhandling', 'stipendiat', 'phd', 'ph.d'],
    'remote': [
        'hjemmekontor', 'fjernarbeid', 'remote', 'jobbe hjemmefra', 'hjemmefra',
        'pa avstand', 'på avstand', 'helt remote',
    ],
    'on_site': [
        'pa kontoret', 'på kontoret', 'pa stedet', 'på stedet', 'hybrid',
        'tilstedevaerelse kreves', 'tilstedeværelse kreves', 'i laboratoriet',
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
    'master': [
        'masteroppgave',
        'masteravhandling',
        'masterstudent',
        'mastergrad',
    ],
    'bachelor': [
        'bacheloroppgave',
        'bachelorgrad',
        'bachelorstudent',
    ],
}

DANISH = {
    'thesis': [
        'speciale', 'specialeprojekt', 'kandidatafhandling', 'bachelorprojekt',
        'bachelorafhandling', 'afgangsprojekt', 'afhandling', 'hovedopgave', 'thesis',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'masterprojekt', 'kandidatspeciale',
    ],
    'phd': ['ph.d.-afhandling', 'phd', 'ph.d', 'doktorgrad', 'erhvervsphd'],
    'remote': [
        'hjemmearbejde', 'hjemmefra', 'arbejde hjemmefra', 'remote', 'fjernarbejde',
        'distancearbejde', 'helt remote',
    ],
    'on_site': [
        'pa kontoret', 'på kontoret', 'pa stedet', 'på stedet', 'hybrid',
        'fysisk tilstedevaerelse', 'fysisk tilstedeværelse', 'i laboratoriet',
    ],
    'not_remote': [
        'ikke hjemmearbejde', 'intet hjemmearbejde', 'ikke remote',
        'kun pa kontoret', 'kun på kontoret',
    ],
    'unpaid': [
        'ulonnet', 'ulønnet', 'uden lon', 'uden løn', 'ingen lon', 'ingen løn',
        'frivillig', 'frivilligt arbejde', 'ingen betaling',
    ],
    'other_language_required': [
        'flydende dansk', 'gode danskkundskaber', 'dansk kraeves', 'dansk kræves',
        'dansk i skrift og tale', 'modersmal dansk', 'modersmål dansk',
    ],
    'english_mention': [
        'engelsk',
        'english',
    ],
    'master': [
        'kandidatafhandling',
        'specialeprojekt',
        'speciale',
        'kandidatstuderende',
    ],
    'bachelor': [
        'bachelorprojekt',
        'bachelorafhandling',
        'bachelorstuderende',
    ],
}

FINNISH = {
    'thesis': [
        'opinnaytetyo', 'opinnäytetyö', 'opinnayte', 'opinnäyte', 'diplomityo',
        'diplomityö', 'pro gradu', 'gradu', 'kandidaatintyo', 'kandidaatintyö',
        'kandidaatintutkielma', 'maisterintutkielma', 'tutkielma', 'lopputyo',
        'lopputyö', 'thesis',
    ],
    'phd': ['vaitoskirja', 'väitöskirja', 'tohtorikoulutettava', 'tohtoriopiskelija',
            'phd', 'ph.d'],
    'remote': [
        'etatyo', 'etätyö', 'etana', 'etänä', 'remote', 'kotoa kasin', 'kotoa käsin',
        'taysin etana', 'täysin etänä', 'etatyomahdollisuus', 'etätyömahdollisuus',
    ],
    'on_site': [
        'toimistolla', 'paikan paalla', 'paikan päällä', 'hybridi', 'lasnaolo',
        'läsnäolo', 'paivaa toimistolla', 'päivää toimistolla', 'laboratoriossa',
    ],
    'not_remote': [
        'ei etatyota', 'ei etätyötä', 'vain toimistolla', 'ainoastaan toimistolla',
        'ei etatyomahdollisuutta', 'ei etätyömahdollisuutta',
    ],
    'unpaid': [
        'palkaton', 'palkatonta', 'ilman palkkaa', 'ei palkkaa', 'vapaaehtoinen',
        'vapaaehtoistyo', 'vapaaehtoistyö', 'ei korvausta',
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
    'master': [
        'maisterintutkielma',
        'pro gradu',
        'diplomityo',
        'diplomityö',
        'maisteriopiskelija',
    ],
    'bachelor': [
        'kandidaatintyo',
        'kandidaatintyö',
        'kandidaatintutkielma',
        'kandidaattiopiskelija',
    ],
}

LUXEMBOURGISH = {
    'thesis': [
        'diplomaarbecht', 'masteraarbecht', 'bacheloraarbecht', 'ofschlossaarbecht',
        'memoire', 'mémoire', 'travail de fin d etudes', 'thesis',
        # Added 4 October 2026 (Document T-19): every word the search sends must be
        # one this module recognises, or it is fetched and then thrown away.
        'masterarbeit', 'mémoire de master',
    ],
    'phd': ['doktorand', 'doctorant', 'these de doctorat', 'thèse de doctorat',
            'phd', 'ph.d'],
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
    'master': [
        'masteraarbecht',
        'memoire de master',
        'master thesis',
    ],
    'bachelor': [
        'bacheloraarbecht',
        'bachelor thesis',
    ],
}

POLISH = {
    'thesis': [
        'praca dyplomowa', 'praca magisterska', 'praca inzynierska',
        'praca inżynierska', 'praca licencjacka', 'praca badawcza',
        'projekt dyplomowy', 'thesis',
    ],
    'phd': ['rozprawa doktorska', 'praca doktorska', 'doktorant', 'doktorantka',
            'phd', 'ph.d'],
    'remote': [
        'zdalnie', 'praca zdalna', 'zdalna', 'z domu', 'praca z domu',
        'w pelni zdalnie', 'w pełni zdalnie', 'remote', 'home office',
    ],
    'on_site': [
        'w biurze', 'stacjonarnie', 'praca stacjonarna', 'hybrydowo',
        'praca hybrydowa', 'obecnosc wymagana', 'obecność wymagana',
        'w laboratorium',
    ],
    'not_remote': [
        'bez pracy zdalnej', 'brak pracy zdalnej', 'nie zdalnie',
        'tylko stacjonarnie', 'wylacznie stacjonarnie', 'wyłącznie stacjonarnie',
    ],
    'unpaid': [
        'bezplatny', 'bezpłatny', 'bezplatne', 'bezpłatne', 'nieplatny', 'niepłatny',
        'bez wynagrodzenia', 'wolontariat', 'wolontariusz', 'brak wynagrodzenia',
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
    'master': [
        'praca magisterska',
        'student studiow magisterskich',
        'studia magisterskie',
    ],
    'bachelor': [
        'praca licencjacka',
        'praca inzynierska',
        'praca inżynierska',
        'student studiow licencjackich',
    ],
}


SECTIONS = ('english_mention', 'thesis', 'phd', 'master', 'bachelor', 'remote', 'on_site', 'not_remote', 'unpaid',
            'other_language_required')

LANGUAGES = {
    'en': ENGLISH, 'de': GERMAN, 'nl': DUTCH, 'fr': FRENCH, 'it': ITALIAN,
    'es': SPANISH, 'pt': PORTUGUESE, 'sv': SWEDISH, 'no': NORWEGIAN, 'da': DANISH,
    'fi': FINNISH, 'lb': LUXEMBOURGISH, 'pl': POLISH,
}


def _ascii(term: str) -> str:
    """'opinnäytetyö' -> 'opinnaytetyo'. Boards strip accents constantly, and a term
    spelled only one way misses every posting that spelled it the other."""
    return ''.join(c for c in unicodedata.normalize('NFD', term)
                   if unicodedata.category(c) != 'Mn')


for _words in LANGUAGES.values():
    for _name in SECTIONS:
        _words[_name] = sorted({t for term in _words[_name] for t in (term, _ascii(term))})


# Terms that must not match inside a longer word. Everything else keeps an open tail so a
# stem finds its inflections -- "masterarbeit" finds "masterarbeiten", "tesi" would find
# "tesina" if it were not listed here.
#
#   gradu      -> graduate, graduation
#   tcc/tfg/tfm/pfe -> initialisms, and they sit inside dozens of ordinary words
#   tesi       -> tesina is a different thing, and "tesi" alone must not claim it
#   phd/thesis -> exact by nature; an open tail buys nothing and risks "phdx" ids
_CLOSED_TAIL = frozenset({
    'gradu', 'tcc', 'tfg', 'tfm', 'pfe', 'tesi', 'these', 'thèse', 'thesis', 'theses',
    'phd', 'ph.d', 'ph. d', 'remote', 'remoto', 'distans', 'uppsats', 'scriptie',
    'speciale', 'doktorat', 'afhandling', 'avhandling',
})


def languages_for(country=None, location=None) -> tuple:
    """Which vocabularies to read a listing with.

    Decided from the country and the city alone, with no language detector, and that is a
    deliberate difference from how the salaried module does it. A title is a handful of
    words -- far too little for a detector to be reliable on -- and this module reads
    titles. An advert whose country is unknown (a global startup board sends plenty) is read
    with every vocabulary rather than one guessed from a sentence, so a German thesis on an
    unlabelled board is still found.
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

    Longest first, so "master thesis" is reported rather than the "thesis" inside it -- the
    matched phrase is what the Log shows Sina, and the specific one is more use.
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
