"""Suite 1 -- every content-filter rule and helper, adversarially."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import section, check, check_no_raise, summary
from app import pipeline as p
import math

D = 'Remote role with competitive salary and great benefits offered for our growing team.'


def job(**kw):
    base = {'title': 'Data Scientist', 'description': D, 'company': 'Acme',
            'country': 'Germany', 'url': 'https://x/1', 'location': 'Remote'}
    base.update(kw)
    return base


# =============================================================== remote rule
section('1.1  passes_work_location_rule')
for text, want, why in [
    ('This is a fully 100% remote position for our team here.', True, 'explicit remote'),
    ('Work from home, flexible hours, great benefits offered.', True, 'wfh'),
    ('WFH friendly team with competitive salary offered here.', True, 'wfh acronym'),
    ('Remote-first company with a great culture and benefits.', True, 'remote-first'),
    ('This role is on-site in our Berlin office building.', False, 'on-site'),
    ('Hybrid role, three days per week in the office please.', False, 'hybrid'),
    ('This is an in-person role at our headquarters here.', False, 'in-person'),
    ('Office-based position with great benefits for the team.', False, 'office-based'),
    ('Remote work not available for this particular position.', False, 'no-remote phrase'),
    ('Fully on-site only, no exceptions for this role here.', False, 'on-site only'),
    # Silence drops the listing, and that was reversed twice before it settled. Removing
    # the requirement let through 128 real listings that said nothing whatsoever about
    # working arrangements; Claude then deleted them anyway, inventing "on-site role in
    # Amsterdam" as the reason. They died either way -- the only difference was that they
    # were translated and screened first, at real cost. Sina's call is that a Dutch advert
    # silent about work mode is an office job. The four text-less sources keep their
    # exemption; see the thin_description case below.
    ('Great opportunity with competitive salary and benefits.', False, 'silence drops it'),
]:
    check(f'{why}: {"keep" if want else "drop"}',
          p.passes_work_location_rule(job(description=text, location='')) is want,
          repr(text[:50]))

# REMOTE MEANS REMOTE, EVERYWHERE. Sina: "اگر نوشتم Remote دیگه بره کلا دنبال Remote حتی اگر Turin
# یا Milan بود / اگر خودم بخواد Any رو Search میکنم". Milan and Turin are cities like any other.
check('Milan is judged like any other city: strictly on-site is dropped',
      p.passes_work_location_rule(job(description='Strictly on-site, hybrid, no remote at all.',
                               location='Milan, Italy')) is False)
check('Torino (local spelling) too',
      p.passes_work_location_rule(job(description='On-site only in our office.',
                               location='Torino, Italia')) is False)
check('location field alone can confirm remote',
      p.passes_work_location_rule(job(description='Great role with benefits.', location='Remote')) is True)
# The "Location:" label rule is gone -- Sina's call. A company stating where IT is based is
# not stating where the WORKER must be, and almost every remote posting names its own city
# somewhere.
check('a Location: label naming a city no longer drops a remote listing',
      p.passes_work_location_rule(job(description='Fully remote role! Location: Germany', location='')) is True)
check('Location: Italy is allowed',
      p.passes_work_location_rule(job(description='Fully remote role. Location: Italy', location='')) is True)
check('thin_description waives the POSITIVE check only',
      p.passes_work_location_rule(job(description='Data Scientist at X in Berlin',
                               location='', thin_description=True)) is True)
check('thin_description does NOT waive on-site',
      p.passes_work_location_rule(job(description='Data Scientist at X (hybrid working)',
                               location='', thin_description=True)) is False)
# The bare word on its own is no longer an on-site statement, and that is deliberate. It
# was the single most expensive entry in the list: on the German corpus it alone dropped
# 117 listings whose text said nothing else about attendance, because it fires on cloud
# architecture ("einem hybrid-ansatz", a deployment topology) and inside benefit lists
# ("hybrides Arbeiten möglich" beside flexible hours and a pension, which offers
# flexibility rather than demanding attendance). Every qualified form still counts.
check('the bare word "hybrid" alone is not an on-site statement',
      p.passes_work_location_rule(job(
          description='Remote-friendly platform team. Experience with a hybrid-ansatz '
                      'across EKS and Kubeflow, infrastructure-as-code, and Python.',
          location='')) is True)
check('a NaN thin_description flag is not truthy, so silence still drops it',
      p.passes_work_location_rule(job(description='Plain role, benefits offered.',
                               location='', thin_description=float('nan'))) is False)
check('a real thin_description flag exempts the listing',
      p.passes_work_location_rule(job(description='Data Scientist at Acme in Berlin',
                               location='', thin_description=True)) is True)
check_no_raise('all-None row does not crash',
               lambda: p.passes_work_location_rule({'title': None, 'description': None, 'location': None}))
check_no_raise('empty dict does not crash', lambda: p.passes_work_location_rule({}))

# =============================================================== language rules
section('1.2  requires_language_besides_english')
# THE PAIRING IS A KEEP SINCE 4 OCTOBER, AND THE FIRST TWO OF THESE USED TO BE True.
#
# Sina set out the four shapes a posting can have and asked for the third one back:
# "اگر به صورت ترکیبی میگفت انگلیسی و یه زبان دیگه باید این رو هم قبول بکنه". A posting that
# wants English alongside Dutch has said the work can be done in a language he has, and
# whether the second one is a wall is a judgement about his own CV that he makes himself.
#
# So only one shape is still a reason to delete: a language he lacks, with English never
# named beside it. Both halves of that are asserted below, at length, because this rule now
# deletes far less than it did and the half that survived is the half worth guarding.
for text, want in [
    ('Fluent in English and German required for this role.', False),
    ('German and English fluency is required for the job.', False),
    ('Fluent English required only for this remote position.', False),
    ('We work in English. No other language needed here.', False),
    ('Sehr gute Deutschkenntnisse in Wort und Schrift erforderlich.', True),
]:
    check(f'2nd-language: {text[:42]}', p.requires_language_besides_english(job(description=text)) is want)

# This rule used to be two bare substrings -- "english and" / "and english" anywhere in the
# text. On 2,542 real listings it deleted 95, and a good share had nothing to do with a
# language requirement. Every line below is taken from a real listing.
for _label, _text in (
    ('English plus a non-language noun',
     'Excellent English and strong communication skills round off your profile.'),
    ('English plus an unrelated benefit',
     'Compensation and English benefits & perks are listed on our careers page.'),
    ('language courses offered as a perk',
     'We offer German and English language courses free of charge to all staff.'),
    ('English plus enthusiasm',
     'Strong communication skills, business-fluent English and enthusiasm for the mission.'),
    ('English and a file format',
     'Please send your CV in English and in Word or PDF format to our team.'),
    ('English and an internet connection',
     'Excellent spoken English and good internet connection for remote work.'),
    ('English as the working language',
     'We are a diverse team from all over the world and English is our language of work.'),
    ('either/or, so English alone is enough',
     'C1+ level in either English or Spanish; fluency in either is fine.'),
    ('either/or again',
     'Professional working proficiency in English or Russian is required.'),
    ('a rule about documents, not about the applicant',
     'If the documents are not in German or English, a certified translation is needed.'),
    ('a second language offered as a bonus',
     'Clear, structured communication in English (German is a HUGE plus, we all speak it).'),
    ('the German idiom for "nice to have"',
     'Englisch erforderlich, Deutschkenntnisse von Vorteil.'),
    ('nice to have, said plainly', 'English required; German nice to have.'),
):
    check(f'not a second language: {_label}',
          p.requires_language_besides_english(job(description=_text)) is False, _text[:56])

# EVERY ONE OF THESE ASSERTED True UNTIL 4 OCTOBER, AND EVERY ONE NAMES ENGLISH.
#
# They were written as "the demands the substring test MISSED" -- real second-language
# requirements that "english and" / "and english" failed to catch, and the pair pattern was
# built to catch them. They are kept here, all of them, with the verdict turned round,
# because they are the best collection in the project of what the pairing actually looks
# like in a real advert and they are now exactly what must NOT be deleted.
for _label, _text in (
    ('an ampersand instead of "and"',
     'Fluency in German & English required to communicate at all levels.'),
    ('the level written in between',
     'Fluency in German (C1 level) and English for stakeholder discussions.'),
    ('a parenthetical in between',
     'German (native or C2) and English (fluent): both are used daily here.'),
    ('the word "skills" in between',
     'Excellent written and spoken German skills and English skills required.'),
    ('a level on each side',
     'Language proficiency: C1 level in English and B2 level in German.'),
    ('CEFR levels in German',
     'Deutsch C1, Englisch mindestens B1-B2, strukturierte Arbeitsweise.'),
    ('a third language listed too',
     'Business-level proficiency in German, English, and Japanese is expected.'),
    ('English first, the other language after',
     'Fluent in English and at least basic skills in German are needed.'),
    ('an unnamed second language',
     'Fluent in English and at least one more language; persuasive communicator.'),
    ('the local language',
     'Fluent written and spoken communication in English and in local language.'),
    # And three the pair pattern never caught even when it was the rule that deleted, because
    # its conjunction list is `and & + / plus sowie und` -- so the Dutch "en", the French "et"
    # and the Italian "e" were all missing. The test the pairing is checked by now needs no
    # conjunction at all, so every language's "and" is covered for free.
    ('the Dutch "en", which the pair pattern never knew',
     'Je beheerst Nederlands en Engels op professioneel niveau.'),
    ('the French "et", likewise',
     "Vous maîtrisez le français et l'anglais couramment."),
    ('a bulleted language list, where no single clause holds both',
     '* Nederlands: vloeiend\n* Engels: goede beheersing'),
):
    check(f'the pairing is a keep: {_label}',
          p.requires_language_besides_english(job(description=_text)) is False, _text[:56])

# THE HALF THAT STILL DELETES -- a language he lacks, English never named beside it.
#
# This is the whole of what the rule does now, so it is asserted in each language the
# vocabulary covers rather than in English alone. None of these names English anywhere.
for _label, _text in (
    ('Dutch, the level stated',
     'Uitstekende beheersing van de Nederlandse taal is vereist.'),
    ('German, the level stated',
     'Sehr gute Deutschkenntnisse in Wort und Schrift erforderlich.'),
    ('German, the level stated numerically',
     'Verhandlungssichere Deutschkenntnisse auf Niveau C1.'),
    ('German, in English',
     'Fluent German is required for this role.'),
    ('French', 'Maîtrise du français exigée pour ce poste.'),
    ('Spanish', 'Se requiere dominio del español para este puesto.'),
):
    check(f'still deleted, no English beside it: {_label}',
          p.requires_language_besides_english(job(description=_text)) is True, _text[:56])

# Italian is NOT in that list, deliberately: the owner has only basic Italian and lives in Italy, so
# treating it as a language he lacks deletes the listings closest to him. Asserted here
# because it is the one language whose absence from _OTHER_LANGUAGES is a decision.
check('an Italian requirement is not a reason to delete',
      p.requires_language_besides_english(job(
          description='Ottima conoscenza della lingua italiana richiesta.')) is False)

# The qualifier has to attach to the language, not to the next section's heading. The text
# this used to be asserted on named English, so it is a keep now for that reason alone and
# would no longer test anything; the German demand is the same shape without the English.
check('a "Desirable:" heading after the requirement does not excuse it',
      p.requires_language_besides_english(job(
          description='Fluent German skills '
                      'Desirable: Initial experience with Python.')) is True)

# The window that decides "beside it" is 160 characters each side, and it is wide on purpose:
# this test can only ever rescue a listing, so the cost of its width is a posting that names
# English somewhere unrelated reaching Claude, and the cost of its narrowness is deleting one
# Sina asked to see. Both ends of it are pinned so neither can drift unnoticed.
_FAR = 'Sehr gute Deutschkenntnisse erforderlich. %s Englisch wird im Team gesprochen.'
check('English 40 characters away still counts as beside it',
      p.requires_language_besides_english(job(description=_FAR % ('x' * 40))) is False)
check('English 400 characters away does not',
      p.requires_language_besides_english(job(description=_FAR % ('x' * 400))) is True)

# The "it never mentioned English" rule was deleted, and every check that used to stand
# here went with it. It deleted a listing for being SILENT rather than for saying anything:
# a posting written in Dutch that never happens to use the word "English" has not told
# anyone that English is unusable there. Sina removed it for the same reason he removed the
# location-label rule and the must-prove-it-is-remote requirement.
#
# requires_language_besides_english, tested above, is the rule that still does this job and
# does it the right way round -- it fires on a posting that ASKS for another language.
check('the rule and both constants that served it are gone',
      not hasattr(p, 'lacks_english_mention')
      and not hasattr(p, '_MIN_CHARS_FOR_ENGLISH_SILENCE')
      and not hasattr(p, '_INTERNATIONAL_WORKPLACE_PATTERN'))
check('it is off the Filter checklist too',
      not any('English mention' in item for item in p.filters.FILTER_RULES_STEP_CHECKLIST),
      p.filters.FILTER_RULES_STEP_CHECKLIST)

# The listings it used to delete must now survive the whole rule loop.
for _label, _text in (
    ('a long advert that simply never names a language',
     'Wir suchen eine Data Scientist. ' * 60),
    ('a short one that says nothing either', 'Data Scientist bei Acme in Berlin.'),
):
    # 'Homeoffice' is appended so the Work Location rule is satisfied and the listing is
    # judged on the language question, which is what this block is about.
    _kept, _removed = p.filters._step_rules(
        [{'title': 'Data Scientist', 'country': 'Germany',
          'description': _text + ' Homeoffice moeglich, remote work possible.',
          'was_translated': True}], None, lambda: False)
    check(f'now kept: {_label}', len(_kept) == 1 and _removed == 0, (_label, _removed))


# =============================================================== sponsorship / unpaid
section('1.3  has_sponsorship_restriction / is_unpaid')
for kw in ['e-verify', 'will not sponsor', 'must be a us citizen', 'no h1b', 'itar',
           'security clearance required', 'green card holder']:
    check(f'sponsorship kw: {kw}',
          p.has_sponsorship_restriction(job(description=f'Remote role. {kw} applies here.')) is True)
check('clean row has no sponsorship restriction',
      p.has_sponsorship_restriction(job()) is False)

for kw in ['unpaid', 'volunteer', 'no compensation', 'pro bono', 'expenses only', 'credit only']:
    check(f'unpaid kw: {kw}',
          p.is_unpaid(job(description=f'Remote internship, {kw} position here.')) is True)
check('paid role is not flagged unpaid', p.is_unpaid(job()) is False)

# The rule used to match these 22 words anywhere in the text, and on 2,542 real listings
# that deleted 222 of them -- essentially all wrongly. These are the exact sentences, taken
# from the real listings that were being thrown away.
for _label, _text in (
    ('unpaid leave offered as a benefit',
     '30 days annual leave plus additional freetime options and unpaid leave.'),
    ('paid volunteering days',
     'Benefits: 2 paid volunteering days a year. Employee shares programme.'),
    ('a volunteer day perk',
     'Take one day each year to volunteer at a charitable organization.'),
    ('volunteer opportunities in a benefits list',
     'Perks: Company Lunch, Wellness benefits, Volunteer opportunities.'),
    ('voluntary used about staff turnover',
     'In three years we have had zero voluntary employee churn.'),
    ('voluntary work named as a life event',
     'We accommodate the realities of life: parenthood, caregiving, voluntary work.'),
    ('a job board filter menu',
     'Job type Part-time Full-time Self-employed Student Seasonal Temp Volunteer '
     'Career level Student/Intern Entry level'),
    ('gratis, which is just German for free',
     'Wir bieten: Getraenke und Obst gratis im Buero.'),
    ('a company describing its own financing',
     'We are profitable and self-funded, built by a small, senior, flat team.'),
    ("a board's label for a salary it does not know",
     'No salary info. Apply now to find out more about this role.'),
):
    check(f'not unpaid: {_label}',
          p.is_unpaid(job(description=_text)) is False, _text[:58])

# ...while every listing that really is unpaid must still go. These are the four the rule
# still catches out of the same 2,542, plus the bootcamp shape it was written for.
for _label, _text in (
    ('an explicitly unpaid volunteer role',
     'Note: This is an UNPAID volunteer opportunity! Job brief: we are looking for...'),
    ('an unpaid internship',
     'Please only apply if you are comfortable with an unpaid internship structure.'),
    ('a non-paid internship',
     'This is a full-time, non-paid, remote internship role.'),
    ('equity only, no cash',
     'Compensation: This is an equity-only role, no salary at this stage.'),
    ('a self-funded programme, which is what that phrase was for',
     'This is a self-funded programme; course fees apply before you start.'),
    ('the German phrasing', 'Ehrenamtliche Stelle, ohne Verguetung.'),
    ('a plainly stated unpaid position', 'The position is unpaid.'),
):
    check(f'unpaid: {_label}', p.is_unpaid(job(description=_text)) is True, _text[:58])

# =============================================================== seniority
section('1.4  is_too_senior')
for text, want, why in [
    ('Senior Data Scientist wanted for our remote team.', True, 'senior in text'),
    ('8 years of experience required for this position.', True, 'bare N years + required'),
    ('Minimum 6 years experience in data science please.', True, 'minimum'),
    ('At least 7 years of relevant experience is needed.', True, 'at least'),
    ('10-15 years of experience required for this role.', True, 'wide range'),
    ('5 to 7 years of experience in machine learning.', True, '"to" separator'),
    ('3-4 years of experience with Python and SQL here.', True, 'small range'),
    ('10+ years of experience leading data teams here.', True, 'plus form'),
    ('0-2 years of experience welcome, entry level role.', False, 'junior range'),
    ('1-3 years of experience, great for new graduates.', False, 'junior range 2'),
    ('No experience required, we will train you fully.', False, 'explicit waiver'),
    ('Our team grew 8 years running. No prior experience needed.', False, 'cross-sentence'),
    ('You will gain 3 years worth of experience in one.', False, 'gain, not require'),
    ('We were founded 5 years ago and value real experience.', False, 'company age'),
    ('The company has 12 years of experience in the market.', False, 'company experience'),
    ('Celebrating 10 years! No experience required at all.', False, 'anniversary'),
]:
    check(f'{why}: {"drop" if want else "keep"}', p.is_too_senior(job(description=text)) is want,
          repr(text[:55]))

for lvl in ['Director', 'Executive', 'Mid-Senior level', 'MID-SENIOR LEVEL']:
    check(f'seniority_level field: {lvl}', p.is_too_senior(job(seniority_level=lvl)) is True)
for lvl in ['Entry level', 'Associate', 'Internship', None, '']:
    check(f'seniority_level field ok: {lvl!r}', p.is_too_senior(job(seniority_level=lvl)) is False)

# This rule deleted 1,563 of 2,542 real listings -- more than any other -- and 797 of those
# went purely on a word buried somewhere in the description. Every sentence below is taken
# verbatim from a listing it was throwing away.
for _label, _text in (
    ('vp inside VPN', 'Gute Kenntnisse in Netzwerksicherheit, Firewalls, VPN und IAM.'),
    ('vp inside VPN again', 'Erfahrung in LAN, WLAN, TCP/IP, DHCP, DNS oder VPN.'),
    ('director inside Active Directory',
     'Betreuung von Active Directory, Microsoft Exchange und Microsoft 365.'),
    ('a manager you work WITH', 'You will work closely with the engineering manager.'),
    ('managers as colleagues',
     'Collaborate with cross-functional teams including product managers and engineers.'),
    ('a manager who is the client',
     'Wir unterstuetzen Banken, Versicherungen und Asset Manager dabei.'),
    ('a similar-jobs sidebar', 'More jobs. Similar jobs: Senior Data Engineer at Instaffo.'),
    ("a job board's filter menu",
     'Career level Student/Intern Entry level Senior executive (CEO, CFO, President)'),
    ('a later career step', 'Roles such as Principal Investigator come later in the track.'),
    ('leadership as a skill', 'We value teamwork as well as leadership skills.'),
    ('a board of directors clause',
     'Subject to approval by the Alphabet Inc. board of directors or its delegate.'),
):
    check(f'not too senior: {_label}', p.is_too_senior(job(description=_text)) is False,
          _text[:58])

# ...and the description still counts where it names THIS role's level, which is a real
# case: a listing titled "7P331 - AI Engineer" whose body says "als Senior AI Engineer".
for _label, _text in (
    ('as a senior X', 'As a Senior Data Scientist you will lead the modelling work.'),
    ('German als', 'Als Senior AI Engineer beraetst du unsere Kunden bei der Umsetzung.'),
    ('we are looking for a senior X',
     'We are looking for a Senior Machine Learning Engineer to join us.'),
    ("we're hiring a senior X", "We're hiring for a Principal Data Engineer this quarter."),
    ('senior X wanted', 'Senior Data Scientist wanted for our remote team.'),
    ('German gesucht', 'Senior Data Engineer (m/w/d) gesucht fuer unser Team.'),
    ('as the head of', 'As the Head of Analytics you will own the roadmap.'),
):
    check(f'too senior: {_label}', p.is_too_senior(job(description=_text)) is True, _text[:58])

# The title is still read as the plainest statement of level there is.
for _title in ('Senior Data Scientist', 'Head of Data', 'Engineering Manager',
               'Principal ML Engineer', 'VP of Engineering', 'Team Lead Analytics'):
    check(f'a senior title is enough on its own: {_title}',
          p.is_too_senior({'title': _title, 'description': 'A role on our team.'}) is True)
for _title in ('Data Scientist', 'Junior Data Engineer', 'Working Student Data Science',
               'IT Administrator Active Directory'):
    check(f'a non-senior title is not: {_title}',
          p.is_too_senior({'title': _title, 'description': 'A role on our team.'}) is False)

# =============================================================== categorize
section('1.5  categorize / display_category / is_category_uncertain')
for text, want in [
    ('This is a part-time remote role for our team.', 'Part-Time'),
    ('Master thesis project on machine learning here.', 'Thesis'),
    ('Standard remote role with benefits for our team.', 'Full-Time'),
    # Changed deliberately, and this line is the change: the body used to be searched for
    # the bare word "internship" and this said Internship. It now says Full-Time, because
    # naming an internship is not the same as being one. See the Glovo advert in 1.kind.
    ('Data Science Internship, remote, paid position.', 'Full-Time'),
]:
    check(f'categorize -> {want}', p.categorize(job(description=text)) == want,
          p.categorize(job(description=text)))
# What a real internship looks like: it says so in its title.
for title, want in [('Data Science Intern', 'Internship'),
                    ('Praktikum Data Science (m/w/d)', 'Internship'),
                    ('PhD Candidate in Computer Vision', 'PhD'),
                    ('Afstudeerstage Data & AI', 'Thesis'),
                    ('Data Scientist', 'Full-Time')]:
    check(f'categorize by title -> {want}',
          p.categorize({'title': title, 'description': D}) == want,
          p.categorize({'title': title, 'description': D}))
for et, want in [('Full-time', 'Full-Time'), ('Contract', 'Contract'),
                 ('Temporary', 'Temporary'), ('Volunteer', 'Volunteer')]:
    check(f'employment_type {et} -> {want}',
          p.categorize({'title': 'X', 'description': 'plain role', 'employment_type': et}) == want)
check('NaN employment_type falls back to Full-Time',
      p.categorize({'title': 'X', 'description': 'plain', 'employment_type': float('nan')}) == 'Full-Time')

check('display_category plain', p.display_category({'Category': 'Full-Time'}) == 'Full-Time')
check('display_category startup suffix',
      p.display_category({'Category': 'Internship', 'google_stage': 'startup'}) == 'Internship Startup')
check('display_category missing Category', p.display_category({}) == 'Other')
check('display_category NaN google_stage is safe',
      p.display_category({'Category': 'Full-Time', 'google_stage': float('nan')}) == 'Full-Time')

# =============================================================== fake detection
section('1.6  is_likely_fake')
check('clean listing is not fake', p.is_likely_fake(job()) is False)
check('2 signals (no company + short desc) IS fake',
      p.is_likely_fake({'title': 'X', 'company': '', 'description': 'tiny', 'url': 'https://u'}) is True)
check('1 signal alone is not fake',
      p.is_likely_fake({'title': 'X', 'company': 'Acme', 'description': 'tiny', 'url': 'https://u'}) is False)
check('thin_description waives the short-desc signal',
      p.is_likely_fake({'title': 'X', 'company': '', 'description': 'Data Scientist',
                        'url': 'https://u', 'thin_description': True}) is False)
check('a genuinely fake thin row is still caught',
      p.is_likely_fake({'title': 'earn $ fast', 'company': '', 'description': 'no experience needed',
                        'url': '', 'thin_description': True}) is True)
for kw in ['earn $', 'guaranteed income', 'wire transfer', 'pyramid', 'registration fee']:
    check(f'fake kw + no company: {kw}',
          p.is_likely_fake({'title': 'Job', 'company': '', 'description': f'{kw} today',
                            'url': 'https://u'}) is True)

# =============================================================== helpers
section('1.7  is_true_flag / text_of')
import numpy as np
import pandas as pd
for label, v, want in [('True', True, True), ('False', False, False), ('None', None, False),
                       ('nan', float('nan'), False), ('np.bool_ True', np.bool_(True), True),
                       ('np.bool_ False', np.bool_(False), False), ('pd.NA', pd.NA, False),
                       ('1', 1, True), ('0', 0, False), ('"x"', 'x', True), ('""', '', False)]:
    check(f'is_true_flag({label})', p.is_true_flag(v) is want, p.is_true_flag(v))
for label, v, want in [('None', None, ''), ('nan', float('nan'), ''), ('pd.NA', pd.NA, ''),
                       ('str', 'Indeed', 'Indeed'), ('int', 42, '42'),
                       ('np.str_', np.str_('X'), 'X')]:
    check(f'text_of({label})', p.text_of(v) == want, repr(p.text_of(v)))
check('text_of result is always .capitalize()-safe',
      all(isinstance(p.text_of(v), str) for v in [None, float('nan'), pd.NA, 1, 'a', ['l']]))

section('1.8  company name normalisation')

# Still needed, and needed for exactly one thing now: matching a listing's employer against
# a government sponsor register. Stripping the legal suffix is what lets a listing that
# says "Uber" match a register that says "Uber B.V." -- see _sponsor_name_matches.
for name, want in [('Booking.com B.V.', 'bookingcom'), ('Booking.com', 'bookingcom'),
                   ('BOOKING COM', 'booking com'), ('Acme Ltd', 'acme'),
                   ('Acme GmbH', 'acme'), ('Foo A/S', 'foo'), ('', '')]:
    check(f'_normalize_company_name({name!r})', p._normalize_company_name(name) == want,
          repr(p._normalize_company_name(name)))
check('_strip_company_from_title strips',
      p._strip_company_from_title('Acme Corp - Data Scientist', 'acme corp') == '- data scientist')

# The regex company GUESS is gone -- deleted once dedup stopped needing a company name at
# all. These check that it stays gone: it returned a job title as an employer often enough
# to be documented, and the name it produced went on to a sponsor-register match.
for _gone in ('_extract_company_from_text', '_fill_missing_company_names',
              '_looks_like_real_company_name', '_step_fill_missing'):
    check(f'the company guess stays deleted: {_gone}', not hasattr(p, _gone))

section('1.9  language detection & translation split')
check('short text -> unknown', p.detect_language({'title': 'AI', 'description': 'AI'}) == 'unknown')
check('empty -> unknown', p.detect_language({}) == 'unknown')
check('real English detected',
      p.detect_language({'title': 'Data Scientist',
                         'description': 'We are looking for a data scientist to join our team '
                                        'in a fully remote position with great benefits.'}) == 'en')

# Short descriptions are the case the detector was changed for. A wrong verdict here does
# not mislabel a listing -- it translates an English posting into English, marks it
# was_translated, and lacks_english_mention then deletes it. Measured over 400 real
# listings cut to 180 characters, the previous detector (langdetect) was wrong on 21 of
# them and lingua on 4, which is the whole reason for the swap.
for _text, _want in (
    ('Wir suchen einen Datenanalysten in Muenchen fuer unser Team.', 'de'),
    ('Data analyst wanted in Munich to join our growing team.', 'en'),
    ('Nous recherchons un ingenieur donnees pour notre equipe a Paris.', 'fr'),
    ('Cerchiamo un data scientist per il nostro team a Milano.', 'it'),
    ('Wij zoeken een data engineer voor ons team in Amsterdam.', 'nl'),
):
    check(f'a short {_want} description is detected correctly',
          p.detect_language({'title': '', 'description': _text}) == _want,
          '%s -> %s' % (_want, p.detect_language({'title': '', 'description': _text})))

# The detector is built on first use, not at import: preloading the models costs ~4s, and
# paying that on every launch of a desktop app that may never run a Filter is not a trade
# worth making. It must also be built exactly once under the 30-worker translate pool.
check('the detector is built lazily, not at import time',
      p.language._DETECTOR is not None, 'should be built by now, after the checks above')
check('and only ever once',
      p.language._detector() is p.language._detector())
check('a detector failure is an unknown, never an exception',
      p.language._detect(None) == 'unknown')
# Translation was removed once the vocabularies covered thirteen languages -- the
# chunker, the DeepL and Google backends, and the retry machinery went with it.
# Detection stayed, and is tested above.

section('1.10  misc helpers')
for url, want in [('https://linkedin.com/jobs/1', True), ('https://uk.indeed.com/x', True),
                  ('https://glassdoor.ca/x', True), ('https://finn.no/job/ad/1', False),
                  ('', False), (None, False)]:
    check(f'_is_excluded_job_board({url!r})', p._is_excluded_job_board(url) is want)
check('_mentions_city exact', p._mentions_city('Oslo', 'Job in Oslo, Norway') is True)
check('_mentions_city local spelling', p._mentions_city('Vienna', 'Stelle in Wien') is True)
check('_mentions_city Copenhagen local', p._mentions_city('Copenhagen', 'Job i København') is True)
check('_mentions_city miss', p._mentions_city('Oslo', 'Job in Bergen') is False)


section('1.x  the Remote rule, against real listings it used to throw away')

# Measured on 2,848 real listings from a real search: 1,549 mentioned remote work in some
# language and the rule dropped 1,204 of them. Judged against Sina's actual constraint on
# 80 of those, it kept 4 of 21 usable jobs. These are the exact shapes it was losing.

def _row(title, description, location=None, thin=False):
    return {'title': title, 'description': description, 'location': location,
            'country': 'Germany', 'thin_description': thin}


# -- German: the standard phrasing, worth nothing to the old vocabulary ---------------
for _phrase, _label in (
    ('Homeoffice möglich, Vollzeit', 'Homeoffice möglich'),
    ('Homeoffice: Umfang: Nach Vereinbarung', 'Homeoffice nach Vereinbarung'),
    ('Teilweise Home-Office', 'Teilweise Home-Office'),
    ('Wir bieten mobiles Arbeiten an', 'mobiles Arbeiten'),
    ('Telearbeit ist möglich', 'Telearbeit'),
    ('Arbeit von zu Hause', 'von zu Hause'),
):
    check(f'a German listing saying "{_label}" is kept',
          p.passes_work_location_rule(_row('Data Scientist (m/w/d)',
                                    'Wir suchen eine Data Scientist. ' + _phrase)),
          _phrase)

# -- a stated remote signal outweighs an incidental office mention --------------------
# 562 listings were dropped purely because the word "hybrid" appeared somewhere on the
# page -- most often in the job board's own filter menu, not in the role's terms.
_MENU = ('Workplace Full Remote Hybrid On-site Employment type Part-time Full-time. '
         'Senior Data Scientist. This role is fully remote.')
check('a filter menu listing every work mode does not disqualify a remote role',
      p.passes_work_location_rule(_row('Senior Data Scientist', _MENU)), _MENU[:60])
check('  ...and the same page without the remote statement is still dropped',
      not p.passes_work_location_rule(_row('Senior Data Scientist',
                                    'Workplace Hybrid On-site Employment type Full-time. '
                                    'Senior Data Scientist in our Berlin office.')))
check('a role that says remote AND mentions an office reaches Claude rather than dying here',
      p.passes_work_location_rule(_row('Data Engineer',
                                'We are fully remote. The team meets in person twice a '
                                'year, otherwise you work from wherever you are.')))

# The third gate was tightened afterwards, and this case moved with it. A label that names
# a city AND says remote in the same breath is naming where the company is, not where the
# person must be -- see 1.y. A label with no remote wording still disqualifies.
check('a "Location:" label that also says remote no longer disqualifies',
      p.passes_work_location_rule(_row('Data Engineer',
                                'Location: Germany (Hamburg) — remote from other '
                                'German locations is possible.')))
check('  ...and neither does a bare "Location: Berlin" when the role is remote',
      p.passes_work_location_rule(_row('Data Engineer',
                                'Fully remote team. Location: Berlin, Germany.')))

# -- what must STILL be dropped: no positive signal at all ----------------------------
check('an on-site role with no remote wording is still dropped',
      not p.passes_work_location_rule(_row('Data Scientist',
                                    'You will work in our Berlin office, on-site, five '
                                    'days a week with the team.')))
check('a role that explicitly refuses remote is still dropped',
      not p.passes_work_location_rule(_row('Data Scientist',
                                    'This position is remote work not permitted. Office '
                                    'attendance in Munich required.')))
check('a listing saying nothing about work mode is dropped',
      not p.passes_work_location_rule(_row('Data Scientist',
                                    'We build models in Python and SQL for our clients.')))

# -- the rules that must not have changed ---------------------------------------------
check('a Turin listing is no longer exempt: on-site is dropped',
      not p.passes_work_location_rule(_row('Data Scientist', 'On-site in our office.', location='Turin')))
check('a Milan listing is no longer exempt: hybrid is dropped', 
      not p.passes_work_location_rule(_row('Data Scientist', 'Hybrid, in office.', location='Milano')))
check('...and a Milan listing that says it is remote is kept, like any other',
      p.passes_work_location_rule(_row('Data Scientist', 'Fully remote role.', location='Milano')))
check('a row from a source that returns no description survives',
      p.passes_work_location_rule(_row('Data Scientist', 'Data Scientist at Acme in Berlin',
                                thin=True)))
check('  ...but a thin row that is explicitly on-site is still dropped',
      not p.passes_work_location_rule(_row('Data Scientist',
                                    'Data Scientist at Acme, on-site only in Berlin',
                                    thin=True)))

# -- the vocabulary itself --------------------------------------------------------------
for _word in ('homeoffice', 'home office', 'mobiles arbeiten', 'telearbeit',
              'work from anywhere', 'remote'):
    check(f'"{_word}" is recognised as a remote signal',
          _word in p.REMOTE_CONFIRMATION_KEYWORDS, p.REMOTE_CONFIRMATION_KEYWORDS)



section('1.y  a Location label is not a restriction any more')

# This section used to test has_conflicting_location_label, a rule that deleted any listing
# whose text named a location other than Italy/Milan/Turin. Sina had it removed and the
# function with it: a company saying where IT is based says nothing about where the WORKER
# must be, and nearly every remote posting names its own city somewhere.
check('the rule and its helper are gone', not hasattr(p, 'has_conflicting_location_label'))
check('so is the pattern it used', not hasattr(p, 'LOCATION_LABEL_PATTERN'))

for _label, _text in (
    ('Remote (Everywhere) with an office city',
     'Job Location: Remote ( Everywhere ) - London +3 |Full Time'),
    ('a German city with hybrid/remote in the label',
     'Location: Germany (Jungingen, Hamburg | hybrid / remote) or Poland | Full-time'),
    ('worldwide', 'Location: Worldwide - work from anywhere'),
    # Each carries a remote word, because the point of these is the LOCATION LABEL, not
    # whether the role is remote -- and a posting with no remote word is now dropped by
    # question 4 of the rule before the label is ever reached.
    ('a plain city with no remote wording of its own',
     'Fully remote. Location: Berlin, Germany. Full-time permanent role.'),
    ('a role location', 'This role is remote. Role Location: Munich office'),
    ('several cities', 'Work from home. Locations: Hamburg, Frankfurt'),
    ('an Italian city', 'Fully remote role. Location: Milan, Italy'),
):
    check(f'a location label saying {_label} does not delete the listing',
          p.passes_work_location_rule({'title': 'Data Scientist', 'country': 'Germany',
                                       'description': _text}), _text[:56])


section('1.t  translation must never destroy the evidence')

# The failure that started this: Google rendered the Dutch "thuiswerkvergoedingen" as
# "home work allowances", the app did not recognise that as remote work, and 53 real Dutch
# listings were deleted for saying nothing about remote when their own text said it plainly.
#
# The rule that made translation unnecessary is below: the Work Location rule reads a
# posting in the posting's own language, so a Dutch advert never needed to become an
# English one for the vocabulary to find its words.

# On the real Netherlands data, that rule and the country vocabulary together take 1,417
# listings down to 872 -- which is why nothing had to be translated to get there.
_before_translation = [
    {'title': 'Data Engineer', 'country': 'Netherlands',
     'description': 'Wij bieden volledig thuiswerken. ' * 30},
    {'title': 'Data Engineer', 'country': 'Netherlands',
     'description': 'Alleen op kantoor in Amsterdam, fulltime. ' * 30},
]
_kept, _removed = p.filters._step_work_location(_before_translation, None, lambda: False)
check('the Work Location rule reads untranslated Dutch, so it can run first',
      len(_kept) == 1 and _removed == 1, (len(_kept), _removed))
check('  ...and it keeps the one whose own language says remote',
      'thuiswerken' in _kept[0]['description'])


section('1.z  a keyword must never match inside an unrelated word')

# The largest single loss ever measured in this app, and it was invisible: the sponsorship
# rule's 'itar' (the US export-control regime) matched inside "Mitarbeiter" -- the ordinary
# German word for "employee", present in almost every German advert. On a real 2,901-listing
# corpus it deleted 983 listings, 34% of everything the search had collected, with no message
# anywhere. 'military' and 'sanitary' hid it in English too.
for _text in (
    'Wir bieten unseren Mitarbeitern flexible Arbeitszeiten und Homeoffice.',
    'Wissenschaftlicher Mitarbeiter (m/w/d) im Bereich Data Science',
    'Rund 470.000 Mitarbeitenden weltweit.',
    'Military veterans are strongly encouraged to apply.',
    'Experience with sanitary engineering systems is a plus.',
):
    check('an ordinary word containing "itar" is not a sponsorship restriction',
          not p.has_sponsorship_restriction({'title': '', 'description': _text}), _text[:52])

# What the rule must still catch -- the boundary fix must not have bought recall with a miss.
for _text in ('This position is ITAR-controlled.',
              'Subject to ITAR and export control regulations.',
              'We are unable to sponsor visas for this role.',
              'Applicants must be authorized to work without sponsorship.',
              'No visa sponsorship is available.',
              'This employer is an E-Verify participant.',
              'Must be a US citizen with an active security clearance required.'):
    check('a genuine sponsorship restriction is still caught',
          p.has_sponsorship_restriction({'title': '', 'description': _text}), _text[:52])

# The boundary is leading-only on purpose, so a keyword still matches when the real text
# continues past it. A trailing boundary would have silently broken these.
for _text in ('There is no visa sponsorship offered.',
              'The company does not sponsors relocation.'):
    check('a keyword still matches when the word continues past it',
          p.has_sponsorship_restriction({'title': '', 'description': _text}), _text[:52])

# Same shape, different list: 'hybrid' and 'on-site' inside the run-together facet text
# Google's job cards emit ("timehybridmid2", "timeon-sitemid5", "germanyhybridmid2"). 25 real
# listings in the same corpus carry those tokens while saying nothing about a hybrid
# arrangement.
for _token in ('timehybridmid2 dataengineer germany',
               'employmenttimeon-sitemid5 posted today',
               'germanyhybridmid2 datascientist'):
    check('a run-together facet token is not an on-site statement',
          not p._ON_SITE_OR_HYBRID_PATTERN.search(_token), _token[:52])

for _token in ('this is a hybrid role', 'work is on-site in Berlin',
               'an office-based position', 'hybrides Arbeitsmodell in Berlin'):
    check('a real on-site statement is still matched',
          bool(p._ON_SITE_OR_HYBRID_PATTERN.search(_token.lower())), _token[:52])

# Where the verdict actually flips: a thin_description row is exempt from the "must contain
# a remote keyword" requirement, so for those rows -- and only those -- a stray 'hybrid' in
# run-together text was the difference between kept and deleted. These are exactly the four
# German-heavy direct-API sources that set the flag.
_thin = {'title': 'Data Engineer', 'country': 'Germany', 'thin_description': True,
         'description': 'timehybridmid2 dataengineer germany'}
check('a thin-description row survives a run-together "hybrid" token',
      p.passes_work_location_rule(_thin))
check('a thin-description row with a real hybrid statement is still dropped',
      not p.passes_work_location_rule(dict(_thin, description='This is a hybrid role in Berlin.')))

# The asymmetry itself is the design decision, so state it as a test: the rescue list is
# deliberately NOT boundary-matched, because a stray match there only keeps a listing Sina
# can ignore, while a stray match in the drop list destroys one he will never see.
check('the drop list is boundary-matched',
      p._ON_SITE_OR_HYBRID_PATTERN.pattern.startswith(r'\b'))

section('1.w  the remote vocabulary, in the languages this app searches')

# Found by asking the corpus the opposite question: of the listings the Remote rule
# DELETED, which contain a remote-sounding phrase the list did not know? These sentences
# are the answers, verbatim.
for _label, _text in (
    ('telecommuting', '40 days per year for telecommuting and a pension plan.'),
    ('home-based teams', 'This initiative spans many teams that are home-based.'),
    ('a company with no office',
     'Over 200 people work on this in a 100% distributed setting - we have no office.'),
    ('work-from-home equipment',
     'Benefits per month, per your choice: work-from-home equipment or gym membership.'),
    ('smart working', 'We offer attractive conditions (smart working, flexible hours).'),
    ('Dutch', 'Een thuiswerkvergoeding van EUR 3,05 per dag en 20 vakantiedagen.'),
    ('Swedish', 'Vi erbjuder flexibilitet samt möjlighet till att arbeta hemifrån.'),
    ('Swedish, the other word', 'Vi erbjuder distansarbete på heltid för rätt person.'),
    ('French', 'Télétravail possible 3 jours par semaine depuis chez vous.'),
    ('Spanish', 'Se ofrece teletrabajo total para este puesto.'),
    ('Polish', 'Praca zdalna w pelnym wymiarze godzin.'),
    ('Italian', 'Offriamo lavoro agile e orari flessibili.'),
):
    check(f'a remote signal in {_label} is recognised',
          p.passes_work_location_rule({'title': 'Data Scientist', 'country': 'Germany',
                                'description': _text}), _text[:56])

# The same search turned these up far more often, and none of them means the job can be
# done from Turin. They are listed here so that nobody adds them to the rescue list later.
#
# Each is paired with an explicit on-site word, and that pairing is the test. A remote
# signal SUPPRESSES the on-site check -- that is how a job board's own filter menu stopped
# killing 562 listings. So if one of these phrases were wrongly counted as a remote signal,
# it would suppress the on-site word sitting right next to it and the listing would
# survive. It must not.
for _label, _text in (
    ('hybrid working, which is the opposite',
     'Modernes, hybrides Arbeiten in High-End Offices sowie neue Technik.'),
    ('where the company operates, not the role',
     'Ein deutschlandweit agierender Konzeptpartner. Präsenzpflicht im Büro.'),
    ('a workation perk',
     'Workation: up to 30 days per year in selected countries. This role is on-site.'),
    ('flexible hours, not flexible location',
     'Großzügiges flexibles Arbeiten, Anwesenheit im Büro erforderlich.'),
    ('colleagues who are distributed',
     'Collaborate with a distributed team of engineers. In-person role, our offices.'),
):
    check(f'not a remote signal: {_label}',
          not p.passes_work_location_rule({'title': 'Data Scientist', 'country': 'Germany',
                                           'description': _text}), _text[:56])

for _label, _country, _lang, _text in (
    ('our office in', 'Netherlands', 'en', 'You will join us at our office in Amsterdam.'),
    ('you will be based in', 'Netherlands', 'en',
     'You will be based in Rotterdam with the wider team.'),
    ('in the heart of', 'Netherlands', 'en',
     'Work in a modern office in the heart of Rotterdam.'),
    ('Dutch werklocatie', 'Netherlands', 'nl', 'Werklocatie: Utrecht, 32 uur per week.'),
    ('German Arbeitsort', 'Germany', 'de', 'Arbeitsort ist unser Standort in Hamburg.'),
):
    check(f'an office sentence with no keyword is caught: {_label}',
          not p.passes_work_location_rule({'title': 'Data Engineer', 'country': _country,
                                           'detected_language': _lang,
                                           'description': _text}), _text[:52])

check('the rescue list is left as a plain substring list',
      isinstance(p.REMOTE_CONFIRMATION_KEYWORDS, list)
      and all(isinstance(k, str) for k in p.REMOTE_CONFIRMATION_KEYWORDS))


section('1.d  dedup: the same job, and the jobs that only look the same')

# Sina's design: clean the two titles down to their words, and if those say it is the same
# job, let the two DESCRIPTIONS decide. Every case below came out of running it against the
# real 2,199-listing Netherlands search, not from imagination.

# --- the title key ------------------------------------------------------------------------
for _label, _title, _company, _expected in (
    ('leaves an ordinary title alone', 'Data Engineer', '', 'data engineer'),
    ('lowercases', 'DATA PLATFORM ENGINEER', '', 'data platform engineer'),
    ('drops bracketed hours', 'Data Platform Engineer (32-40 uur)', '', 'data platform engineer'),
    ('drops a reference number', 'Data Analist (9212028)', '', 'data analist'),
    ('drops a gender tag', 'Softwareentwickler (m/w/d)', '', 'softwareentwickler'),
    ('drops a salary tail', 'Associate Scientist | tot €4.000', '', 'associate scientist'),
    ('drops every symbol', 'Site Reliability / GitOps Engineer!', '', 'site reliability gitops engineer'),
    ('joins a hyphenated word the same way as a spaced one', 'Data-analist', '', 'data analist'),
    ('drops digits', 'Data Engineer 2026', '', 'data engineer'),
    ('trims', '   Data Engineer   ', '', 'data engineer'),
    ('drops the company after "at"', 'Data Engineer at Merapar', 'Merapar', 'data engineer'),
    ('drops the company after a dash', 'Merapar - Data Engineer', 'Merapar', 'data engineer'),
    ('survives a None title', None, '', ''),
):
    check(f'title key {_label}',
          p.dedup_title_key(_title, _company) == _expected,
          repr(p.dedup_title_key(_title, _company)))

# The cleaning must never be handed the GUESSED company name. Stripping the guess was
# measured to eat the title itself -- _extract_company_from_text reads "Data Scientist -
# Causal Inference and Experimentation" as a company called "Causal Inference and
# Experimentation", and stripping that leaves the bare words "data scientist", which then
# matches every other Data Scientist posting in the run.
check('a specialism is not mistaken for decoration',
      p.dedup_title_key('Data Scientist - Causal Inference and Experimentation', '')
      == 'data scientist causal inference and experimentation',
      p.dedup_title_key('Data Scientist - Causal Inference and Experimentation', ''))
# Brackets go wholesale, as Sina specified -- no judgement call about which ones hold
# decoration and which hold meaning. That is a deliberate trade: it means "Redactie
# Assistent (Werkstudent 6-10 uur)" and plain "Redactie Assistent" reach the description
# comparison as the same title, and the DESCRIPTIONS then have to be the ones that keep a
# working-student posting apart from the full-time one. On the real Netherlands rows they
# do -- those two score 53% against each other, nowhere near the 80% needed to merge.
check('brackets go wholesale, decoration or not',
      p.dedup_title_key('Redactie Assistent (Werkstudent 6-10 uur)', '') == 'redactie assistent',
      p.dedup_title_key('Redactie Assistent (Werkstudent 6-10 uur)', ''))


def _dedup(rows):
    kept, removed = p._remove_duplicates_list([dict(r) for r in rows])
    return [r.get('id') for r in kept], removed


_BOILERPLATE = (
    'We are a fast growing company and we offer a competitive salary, 25 days of holiday, '
    'a pension scheme, a learning budget, and a fully remote way of working. We believe in '
    'diversity and welcome applicants from every background. Our hiring process is four '
    'stages and we aim to give feedback within one week. ') * 4

# --- the same job, from two sources -------------------------------------------------------
_kept, _removed = _dedup([
    {'id': 'employer', 'title': 'Data Engineer at Merapar', 'company': 'Merapar',
     'url': 'https://merapar.com/jobs/data-engineer', 'description': _BOILERPLATE},
    {'id': 'eures', 'title': 'Data Engineer', 'company': '',
     'url': 'https://europa.eu/eures/portal/jv-se/jv-details/abc', 'description': _BOILERPLATE},
])
check('one posting republished under a different title is one job', _removed == 1, _kept)
check('the copy that survives is the employer\'s own, not the republisher\'s',
      _kept == ['employer'], _kept)

# The old rule could not see this pair at all: one source writes the trading name, the
# other the registered legal name, so grouping by company never compared them.
_kept, _removed = _dedup([
    {'id': 'direct', 'title': 'Medewerker Resource Planning', 'company': 'KPMG',
     'url': 'https://werkenbijkpmg.nl/vacancy/medewerker', 'description': _BOILERPLATE},
    {'id': 'board', 'title': 'Medewerker Resource Planning',
     'company': 'Klynveld Peat Marwick Goerdeler',
     'url': 'https://www.glassdoor.com/job-listing/j?jl=1010252229406',
     'description': _BOILERPLATE},
])
check('two spellings of one company no longer hide a duplicate', _removed == 1, _kept)
check('the direct link survives, not the aggregator', _kept == ['direct'], _kept)

# --- the jobs that only LOOK the same -------------------------------------------------------
# This is the failure mode that set the threshold. An employer writes one boilerplate and
# posts every opening inside it, so two unrelated jobs come out 80-99% alike in body text.
# The title is the only thing that still distinguishes them, so it decides.
for _label, _a, _b in (
    ('two roles at one agency', 'Senior React Full-stack Developer', 'Senior Data Engineer'),
    ('two internships at one company', 'Internship - Global Commercial Strategy',
     'Internship - Regional Talent & Leadership'),
    ('two PhD positions in one group', 'PhD in De Novo Protein Design for Continuous Biosensing',
     'PhD on Nanoswitches for Continuous Nucleic Acid Monitoring'),
    ('four AI product roles at one startup', 'Technical Product Manager - AI Stockbroking',
     'Technical Product Lead - AI Neobank'),
    ('designer and designer', 'Business Designer', 'Service Designer'),
    ('engineer and scientist', 'Senior Machine Learning Engineer', 'Machine Learning Scientist'),
    ('expert and specialist', 'Data Quality Expert', 'Data Quality Specialist'),
    ('a role and its senior form', 'Data Steward', 'Master Data Steward'),
    ('a role and its working-student form', 'Data-analist', 'Werkstudent Data-analist'),
):
    _kept, _removed = _dedup([
        {'id': 'a', 'title': _a, 'company': 'Acme', 'url': 'https://acme.com/a',
         'description': _BOILERPLATE},
        {'id': 'b', 'title': _b, 'company': 'Acme', 'url': 'https://acme.com/b',
         'description': _BOILERPLATE},
    ])
    check(f'identical boilerplate does not merge {_label}', _removed == 0, (_kept, _a, _b))

# --- and the other direction: the title alone is never enough -------------------------------
_kept, _removed = _dedup([
    {'id': 'one', 'title': 'Data Scientist', 'company': 'Alpha', 'url': 'https://alpha.com/1',
     'description': 'Build demand forecasting models for a retail chain, working in Python '
                    'and dbt against a Snowflake warehouse. Fully remote within the EU.'},
    {'id': 'two', 'title': 'Data Scientist', 'company': 'Beta', 'url': 'https://beta.com/2',
     'description': 'Join our clinical research group to design trial analyses in R, '
                    'working alongside biostatisticians. Remote, with quarterly meetups.'},
])
check('the same title at two companies is not a duplicate when the postings differ',
      _removed == 0, _kept)

_kept, _removed = _dedup([
    {'id': 'first', 'title': 'Data Scientist', 'company': 'Alpha',
     'url': 'https://alpha.com/same', 'description': 'Anything at all.'},
    {'id': 'second', 'title': 'Something Else Entirely', 'company': 'Beta',
     'url': 'https://alpha.com/same', 'description': 'Completely different words here.'},
])
check('the same URL is still a duplicate whatever the text says', _removed == 1, _kept)

# --- the empty-string trap ------------------------------------------------------------------
# Two empty strings score a perfect 1.0 against each other. A title that cleans away to
# nothing, or a listing with no description yet, must therefore never be merged on that
# evidence -- this exact bug once silently merged unrelated postings.
_kept, _removed = _dedup([
    {'id': 'x', 'title': '2026', 'company': '', 'url': 'https://x.com/1', 'description': ''},
    {'id': 'y', 'title': '###', 'company': '', 'url': 'https://y.com/2', 'description': ''},
])
check('two titles that clean away to nothing are not merged', _removed == 0, _kept)

_kept, _removed = _dedup([
    {'id': 'x', 'title': 'Data Engineer', 'company': '', 'url': 'https://x.com/1',
     'description': ''},
    {'id': 'y', 'title': 'Data Engineer', 'company': '', 'url': 'https://y.com/2',
     'description': ''},
])
check('two listings with no description yet are not merged on the title alone',
      _removed == 0, _kept)

check('dedup on an empty list returns an empty list', _dedup([]) == ([], 0))

# --- which copy survives ----------------------------------------------------------------------
# Not cosmetic: the surviving copy is the one Claude reads and the one Sina clicks.
_kept, _removed = _dedup([
    {'id': 'excerpt', 'title': 'Data Engineer', 'company': 'Acme',
     'url': 'https://europa.eu/eures/portal/jv-se/jv-details/xyz',
     'description': _BOILERPLATE[:600]},
    {'id': 'full', 'title': 'Data Engineer', 'company': 'Acme',
     'url': 'https://acme.com/careers/data-engineer', 'description': _BOILERPLATE},
])
check('a truncated republication loses to the full posting', _kept == ['full'], _kept)

_kept, _removed = _dedup([
    {'id': 'short', 'title': 'Data Engineer', 'company': 'Acme',
     'url': 'https://acme.com/a', 'description': _BOILERPLATE[:900]},
    {'id': 'long', 'title': 'Data Engineer', 'company': 'Acme',
     'url': 'https://acme.com/b', 'description': _BOILERPLATE},
])
check('between two direct links the fuller description survives', _kept == ['long'], _kept)

check('the thresholds are the measured ones',
      p._DEDUP_TITLE_SIMILARITY_THRESHOLD == 0.90
      and p._DEDUP_DESCRIPTION_SIMILARITY_THRESHOLD == 0.80,
      (p._DEDUP_TITLE_SIMILARITY_THRESHOLD, p._DEDUP_DESCRIPTION_SIMILARITY_THRESHOLD))


section('1.c  the country object reads the posting in its OWN language')

# Sina's design: work out what language the posting is written in, check it against THAT
# language's vocabulary, and flag whether it needs translating -- all before the translator
# runs. A Belgian listing used to be checked against Dutch, French, German and English all
# at once, so a French phrase could fire on a Dutch advert.

from app.pipeline import country_rules as _cr  # noqa: E402

check('an English posting loads the English vocabulary and nothing else',
      _cr.languages_for('Belgium', None, 'en') == ('en',),
      _cr.languages_for('Belgium', None, 'en'))
for _detected, _want in (('nl', ('nl', 'en')), ('fr', ('fr', 'en')), ('de', ('de', 'en')),
                         ('fi', ('fi', 'en')), ('it', ('it', 'en'))):
    check(f'a {_detected} posting loads {_detected} + English',
          _cr.languages_for('Belgium', None, _detected) == _want,
          _cr.languages_for('Belgium', None, _detected))

# English rides along with every other language on purpose. Job ads in these countries mix
# English into the local language constantly, and the remote signal is what STOPS the
# on-site words deleting a listing -- so dropping English would delete a Dutch advert for a
# phrase its own English sentence contradicts.
check('a Dutch advert whose remote promise is in English survives',
      p.passes_work_location_rule({
          'title': 'Data Engineer', 'country': 'Netherlands',
          'description': 'Je werkt op kantoor of thuis. This role is fully remote.'}))

# lingua reports Norwegian as Bokmal.
check("lingua's 'nb' maps to the Norwegian vocabulary",
      _cr.languages_for('Norway', None, 'nb') == ('no', 'en'))
# Polish is not one of the 18 countries but lingua detects it, so it has its own vocabulary
# rather than falling back -- a Polish advert in Germany is judged on Polish words.
check('Polish has a vocabulary of its own', _cr.languages_for('Germany', None, 'pl') == ('pl', 'en'))
check('a language lingua cannot name falls back to the country, never to nothing',
      _cr.languages_for('Germany', None, 'unknown') == ('de', 'en'))
check('no detection at all still loads every language the country uses',
      _cr.languages_for('Belgium') == ('nl', 'fr', 'de', 'en'))
check('an unknown country loads everything rather than nothing',
      set(_cr.languages_for('Atlantis')) == set(_cr.LANGUAGES))

# -- the two flags ------------------------------------------------------------------------
_dutch = {'title': 'Data Scientist', 'country': 'Netherlands',
          'description': 'Wij zoeken een data scientist. Je werkt volledig vanuit huis en '
                         'hebt ruime ervaring met Python en SQL en met het bouwen van '
                         'datapijplijnen voor onze klanten in heel Nederland.'}
_english = {'title': 'Data Scientist', 'country': 'Netherlands',
            'description': 'We are looking for a data scientist to build forecasting '
                           'models. You will work fully remotely with a small team and '
                           'have experience with Python, SQL and cloud data warehouses.'}
check('a Dutch posting is detected as Dutch', p.classify_language(_dutch) == 'nl')
check('  ...and flagged for translation', _dutch[p.NEEDS_TRANSLATION_KEY] is True)
check('an English posting is detected as English', p.classify_language(_english) == 'en')
check('  ...and flagged as needing none', _english[p.NEEDS_TRANSLATION_KEY] is False)
check('the language is recorded on the row for the Jobs table to show',
      _dutch[p.DETECTED_LANGUAGE_KEY] == 'nl' and _english[p.DETECTED_LANGUAGE_KEY] == 'en')

check('a listing too short to detect is flagged as needing no translation, not deleted',
      p.classify_language({'title': 'X', 'description': ''}) == 'unknown')

# The flag still matters: it is what tells the country object which vocabulary to load
# for a listing, and it is set once rather than re-derived per rule.
_rows = [dict(_dutch), dict(_english)]
for _r in _rows:
    p.classify_language(_r)
check('the flag marks exactly the non-English rows',
      [_r.get(p.NEEDS_TRANSLATION_KEY) for _r in _rows] == [True, False])

# -- and the point of it all: the right vocabulary fires ------------------------------------
check('a Dutch demand for Dutch is caught in Dutch, before any translation',
      p.country_rule_hit('other_language_required', {
          'title': 'Data Engineer', 'country': 'Netherlands',
          'description': 'Voor deze functie is een goede beheersing van de Nederlandse '
                         'taal vereist, evenals ervaring met Python en SQL en het '
                         'ontwerpen van datamodellen voor onze klanten.'})
      == 'beheersing van de nederlandse taal')
check('a German demand for German is caught in German',
      p.country_rule_hit('other_language_required', {
          'title': 'Data Engineer', 'country': 'Germany',
          'description': 'Für diese Position sind verhandlungssichere Deutschkenntnisse '
                         'erforderlich sowie Erfahrung mit Python und SQL und dem Aufbau '
                         'von Datenpipelines für unsere Kunden.'}))
check('an English posting is not searched with Dutch words',
      not p.country_rule_hit('other_language_required', {
          'title': 'Data Engineer', 'country': 'Netherlands',
          'description': 'We build data pipelines in Python and SQL for clients across '
                         'Europe. You will join a small remote team and own delivery '
                         'end to end for two of our largest accounts.'}))


section('1.e  a listing must be findable however its accents were typed')

# Sina's requirement: every term has to match in three spellings -- the English word, the
# local word written in ASCII, and the local word written in its own letters. 463 of the
# object's terms carry a character outside ASCII, and job ads write all three: scrapers
# strip diacritics, HTML entities get mangled, and people type without them.
#
# The variants are GENERATED at import rather than hand-written, so these checks are what
# stops that generation from silently breaking.

# One sentence, three spellings, same verdict every time.
for _label, _country, _lang, _section, _text in (
    ('German umlaut',   'Germany', 'de', 'on_site',
     'Für diese Stelle gilt Präsenzpflicht im Büro.'),
    ('German stripped', 'Germany', 'de', 'on_site',
     'Fur diese Stelle gilt Prasenzpflicht im Buro.'),
    ('German expanded', 'Germany', 'de', 'on_site',
     'Fuer diese Stelle gilt Praesenzpflicht im Buero.'),
    ('Danish o-slash',  'Denmark', 'da', 'on_site',
     'Fysisk fremmøde på kontoret er påkrævet.'),
    ('Danish stripped', 'Denmark', 'da', 'on_site',
     'Fysisk fremmode pa kontoret er pakraevet.'),
    ('Finnish umlaut',  'Finland', 'fi', 'remote', 'Teemme etätyötä joka päivä.'),
    ('Finnish stripped', 'Finland', 'fi', 'remote', 'Teemme etatyota joka paiva.'),
    ('Swedish ring',    'Sweden',  'sv', 'remote', 'Du kan arbeta på distans.'),
    ('Swedish stripped', 'Sweden', 'sv', 'remote', 'Du kan arbeta pa distans.'),
    ('French accent',   'France',  'fr', 'unpaid', 'Ce stage est non rémunéré.'),
    ('French stripped', 'France',  'fr', 'unpaid', 'Ce stage est non remunere.'),
):
    _row = {'title': 'Data Engineer', 'country': _country, 'detected_language': _lang,
            'needs_translation': True, 'description': _text}
    check(f'{_section} still fires: {_label}', p.country_rule_hit(_section, _row), _text[:48])

# Both conventions are generated, and the original is never lost.
_de = p.country_rules.LANGUAGES['de']['on_site']
check('the accented original survives generation', 'präsenzpflicht' in _de)
check('  ...and the stripped spelling exists', 'prasenzpflicht' in _de)
check('  ...and the expanded one too', 'praesenzpflicht' in _de)
_da = p.country_rules.LANGUAGES['da']['on_site']
check('o-slash strips to o and expands to oe',
      'fysisk fremmode' in _da and 'fysisk fremmoede' in _da, _da[:6])
_sv = p.country_rules.LANGUAGES['sv']['remote']
check('a-ring strips to a and expands to aa',
      'arbeta pa distans' in _sv and 'arbeta paa distans' in _sv)

check('generation adds terms and removes none',
      all(len(p.country_rules.LANGUAGES[c][s]) >= 1
          for c in p.country_rules.LANGUAGES for s in p.country_rules.SECTIONS
          if p.country_rules.LANGUAGES[c][s]))
check('every list is free of duplicates after generation',
      all(len(set(p.country_rules.LANGUAGES[c][s])) == len(p.country_rules.LANGUAGES[c][s])
          for c in p.country_rules.LANGUAGES for s in p.country_rules.SECTIONS))
check('nothing generated is empty',
      not any(term == '' for c in p.country_rules.LANGUAGES
              for s in p.country_rules.SECTIONS for term in p.country_rules.LANGUAGES[c][s]))


section('1.f  a foreign posting that never mentions English is dropped before translation')

# Sina's rule, and its placement is the point: it runs BEFORE the translator, so a listing
# it removes costs nothing to remove. On the real Netherlands data it takes out 644 of the
# 1,162 reaching it and cuts what goes to DeepL from 1,299,146 characters to 160,152.

# The word "English" has to be recognised in all three spellings, per language. Every one
# of these mentions English and must therefore SURVIVE.
for _label, _country, _lang, _text in (
    ('Dutch says Engels',        'Netherlands', 'nl', 'Beheersing van het Engels is vereist.'),
    ('Dutch says Engelstalig',   'Netherlands', 'nl', 'Wij zijn een Engelstalig team.'),
    ('Dutch says English',       'Netherlands', 'nl', 'Je werkt in English met het team.'),
    ('German Englischkenntnisse', 'Germany', 'de', 'Gute Englischkenntnisse erforderlich.'),
    ('German englischsprachig',  'Germany', 'de', 'Ein englischsprachiges Arbeitsumfeld.'),
    ('French anglais',           'France', 'fr', "Maîtrise de l'anglais requise."),
    ('French anglophone',        'France', 'fr', 'Environnement anglophone.'),
    ('Italian inglese',          'Italy', 'it', 'Buona conoscenza dell’inglese.'),
    ('Spanish with accent',      'Spain', 'es', 'Se requiere inglés fluido.'),
    ('Spanish without accent',   'Spain', 'es', 'Se requiere ingles fluido.'),
    ('Portuguese with accent',   'Portugal', 'pt', 'É necessário inglês fluente.'),
    ('Portuguese without',       'Portugal', 'pt', 'E necessario ingles fluente.'),
    ('Swedish engelska',         'Sweden', 'sv', 'Flytande engelska krävs.'),
    ('Norwegian engelsk',        'Norway', 'no', 'Flytende engelsk er et krav.'),
    ('Danish engelsk',           'Denmark', 'da', 'Flydende engelsk kræves.'),
    ('Finnish englanti',         'Finland', 'fi', 'Sujuva englannin kielen taito.'),
    ('Finnish compound',         'Finland', 'fi', 'Englanninkielinen työympäristö.'),
):
    _row = {'title': 'Data Engineer', 'country': _country, 'detected_language': _lang,
            'needs_translation': True, 'description': _text}
    check(f'kept, it names English: {_label}',
          not p.silent_about_english(_row), _text[:52])

# And these say nothing about English at all, so they go.
for _label, _country, _lang, _text in (
    ('Dutch',  'Netherlands', 'nl',
     'Wij zoeken een data engineer met ervaring in Python en SQL voor ons team.'),
    ('German', 'Germany', 'de',
     'Wir suchen eine Data Engineer mit Erfahrung in Python und SQL für unser Team.'),
    ('Finnish', 'Finland', 'fi',
     'Etsimme data engineeriä, jolla on kokemusta Pythonista ja SQL:stä.'),
):
    _row = {'title': 'Data Engineer', 'country': _country, 'detected_language': _lang,
            'needs_translation': True, 'description': _text}
    check(f'dropped, silent about English: {_label}', p.silent_about_english(_row))

# A source that returns no description is exempt, the same way it is exempt from the Work
# Location rule. This is a real arbeitsagentur.de row: the whole description is twenty-nine
# characters of English, the language detector calls it Danish, and the rule then deleted it
# for never mentioning English. Four sources return rows this thin by design.
_THIN = {'title': 'Data Scientist', 'company': 'Jenoptik AG', 'country': 'Germany',
         'platform': 'arbeitsagentur.de', 'thin_description': True,
         'description': 'Data Scientist at Jenoptik AG'}
check('a source that returns no description is exempt',
      not p.silent_about_english(dict(_THIN, detected_language='da',
                                      needs_translation=True)))
check('and the same row without the thin flag is not exempt',
      p.silent_about_english(dict(_THIN, thin_description=False,
                                  detected_language='da', needs_translation=True)))

# A listing already in English is never touched -- it is written in the language Sina reads.
check('an English posting is never dropped by this rule',
      not p.silent_about_english({
          'title': 'Data Engineer', 'country': 'Netherlands', 'detected_language': 'en',
          'needs_translation': False,
          'description': 'We build data pipelines in Python and SQL for our clients.'}))

# It reads the ORIGINAL text, not a translation. Translation turns "Engels" into "English"
# and would make every listing look like it had mentioned it -- which is exactly why the
# rule sits before the translator rather than after.
check('a translated row is judged on what the board actually wrote',
      p.silent_about_english({
          'title': 'Data Engineer', 'country': 'Netherlands', 'detected_language': 'nl',
          'needs_translation': True,
          p.ORIGINAL_DESCRIPTION_KEY: 'Wij zoeken een data engineer met Python.',
          'description': 'We are looking for a data engineer with English and Python.'}))

check('it is the first rule the country step asks',
      p.filters.COUNTRY_RULE_SECTIONS[0][1] is None
      and 'English' in p.filters.COUNTRY_RULE_SECTIONS[0][0],
      p.filters.COUNTRY_RULE_SECTIONS[0])


# Both sides of every comparison are lowercased, and nothing relies on a regex flag to
# paper over it: the pattern is compiled WITHOUT re.IGNORECASE, deliberately. That is
# faster on an alternation this size, and it means a term added in the wrong case fails
# loudly here instead of silently never matching in production.
check('every vocabulary term is lowercase',
      not [t for c in p.country_rules.LANGUAGES for s in p.country_rules.SECTIONS
           for t in p.country_rules.LANGUAGES[c][s] if t != t.lower()],
      [t for c in p.country_rules.LANGUAGES for s in p.country_rules.SECTIONS
       for t in p.country_rules.LANGUAGES[c][s] if t != t.lower()][:5])
check('rule_text lowercases what it returns',
      p.rule_text({'title': 'REMOTE Data Engineer', 'description': 'HOMEOFFICE'})
      == 'remote data engineer homeoffice')
check('a SHOUTING posting still matches',
      p.country_rule_hit('remote', {'title': 'DATA ENGINEER', 'country': 'Netherlands',
                                    'detected_language': 'nl',
                                    'description': 'VOLLEDIG THUISWERKEN MOGELIJK'}))
check('  ...and so does a Title Cased one',
      p.country_rule_hit('on_site', {'title': 'Data Engineer', 'country': 'Germany',
                                     'detected_language': 'de',
                                     'description': 'Es Gilt Präsenzpflicht Im Büro.'}))


# =========================================== the Thesis and Internship modules
#
# Three parallel modules -- Job, Thesis, Internship -- that share no vocabulary, no rules
# and no helpers. These check both halves of that: that each finds what it is for, and that
# none of them can reach into another.
import ast  # noqa: E402
import io  # noqa: E402
from app.pipeline import thesis as TH  # noqa: E402
from app.pipeline import internship as IN  # noqa: E402

NL_BODY = ('Voor onze afdeling zoeken wij een enthousiaste kandidaat die met ons '
           'meedenkt over data en klantbeleving binnen ons team in Nederland.')
DE_BODY = ('Fuer unser Team suchen wir eine engagierte Person, die uns bei Auswertungen '
           'und Berichten unterstuetzt und gemeinsam mit uns Themen weiterentwickelt.')

section('1.20  the three modules share nothing')
# Read from the syntax tree, not grepped: a module name inside a comment or a docstring is
# not an import, and this claim is too important to check with a substring search.
def _imports(*paths):
    names = set()
    for path in paths:
        tree = ast.parse(io.open(path, encoding='utf-8').read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add(('.' * node.level) + (node.module or ''))
    return names


_JOB = ('app/pipeline/filters.py', 'app/pipeline/rules.py', 'app/pipeline/country_rules.py')
_TH = ('app/pipeline/thesis/words.py', 'app/pipeline/thesis/finder.py',
       'app/pipeline/thesis/field_words.py', 'app/pipeline/thesis/__init__.py')
_IN = ('app/pipeline/internship/words.py', 'app/pipeline/internship/finder.py',
       'app/pipeline/internship/field_words.py', 'app/pipeline/internship/__init__.py')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_full = lambda paths: [os.path.join(_ROOT, p) for p in paths]  # noqa: E731

for name, mine, forbidden in (
        ('Thesis', _TH, ('rules', 'country_rules', 'filters', 'internship')),
        ('Internship', _IN, ('rules', 'country_rules', 'filters', 'thesis')),
        ('Job', _JOB, ('thesis', 'internship'))):
    leaks = sorted(i for i in _imports(*_full(mine))
                   if any(f in i for f in forbidden))
    check(f'the {name} module imports nothing from the other two', not leaks, leaks)

check('Thesis and Internship do not share a vocabulary object',
      TH.words.LANGUAGES is not IN.words.LANGUAGES)
check('Thesis does not share one with the Job module',
      TH.words.LANGUAGES is not p.country_rules.LANGUAGES)
check('Internship does not share one with the Job module',
      IN.words.LANGUAGES is not p.country_rules.LANGUAGES)
# Editing one must not move another. The strongest form of the claim, and cheap to check.
TH.words.LANGUAGES['en']['thesis'].append('zzz-canary')
check('a word added to Thesis does not appear in Internship',
      'zzz-canary' not in IN.words.LANGUAGES['en']['internship'])
check('  ...nor in the Job module',
      'zzz-canary' not in p.country_rules.LANGUAGES['en']['thesis'])
TH.words.LANGUAGES['en']['thesis'].remove('zzz-canary')

# The title check, the newest thing these three modules each carry a copy of. It was once a
# field word list written once and imported by both student modules; Sina overruled that --
# "نه همه باید جدا باشند / حتی اگر این بخش های آنها نیز مشترک است" -- so there are three
# files, and when the word lists became the title he types, each file kept its own copy of
# the matching code. This proves it.
import re as _re                                                  # noqa: E402
from app.pipeline.thesis import field_words as _TH_FIELD          # noqa: E402
from app.pipeline.internship import field_words as _IN_FIELD      # noqa: E402
from app.pipeline import job_field_words as _JOB_FIELD            # noqa: E402

check('each module has its own title-check FILE',
      len({_TH_FIELD.__file__, _IN_FIELD.__file__, _JOB_FIELD.__file__}) == 3,
      [_TH_FIELD.__file__, _IN_FIELD.__file__, _JOB_FIELD.__file__])
# Changing how one module reads a title, and watching where it lands, is the only honest
# test -- an identity check on compiled patterns fails for modules that are separate, since
# re.compile caches by pattern string (E-1 in the fault register).
_saved = _IN_FIELD._form_patterns
try:
    _IN_FIELD._form_patterns = lambda _title: ((_re.compile('zzz-canary', _re.I),),)
    check("a change to Internship's title check does not reach Thesis",
          not _TH_FIELD.title_is_in_field('zzz-canary placement', 'Data Engineering'))
    check('  ...nor the Job module',
          not _JOB_FIELD.title_is_in_field('zzz-canary placement', 'Data Engineering'))
    check('  ...but does reach Internship itself',
          _IN_FIELD.title_is_in_field('zzz-canary placement', 'Data Engineering'))
finally:
    _IN_FIELD._form_patterns = _saved
check('every language carries every Thesis section',
      not [(c, s) for c in TH.words.LANGUAGES for s in TH.words.SECTIONS
           if s not in TH.words.LANGUAGES[c]])
check('every language carries every Internship section',
      not [(c, s) for c in IN.words.LANGUAGES for s in IN.words.SECTIONS
           if s not in IN.words.LANGUAGES[c]])
check('all eighteen countries map to a language in the Thesis module',
      len(TH.words.COUNTRY_LANGUAGES) == 18, len(TH.words.COUNTRY_LANGUAGES))
check('  ...and in the Internship module',
      len(IN.words.COUNTRY_LANGUAGES) == 18, len(IN.words.COUNTRY_LANGUAGES))
# Compiled without re.IGNORECASE, deliberately: faster on an alternation this size, and a
# term added in the wrong case fails loudly here rather than silently never matching.
for label, mod in (('Thesis', TH), ('Internship', IN)):
    wrong = [t for c in mod.words.LANGUAGES for s in mod.words.SECTIONS
             for t in mod.words.LANGUAGES[c][s] if t != t.lower()]
    check(f'every {label} term is lowercase', not wrong, wrong[:5])

section('1.21  the Thesis module')
for title, body, country, want, why in [
    ('Master Thesis - Radio Propagation Modelling', D, 'Austria', True, 'English thesis'),
    ('Bachelor Thesis Artificial Intelligence', D, 'Austria', True, 'bachelor thesis'),
    ('Afstudeerstage HBO: AI & E-Learning', NL_BODY, 'Netherlands', True, 'Dutch'),
    ('Masterarbeit Maschinelles Lernen', DE_BODY, 'Austria', True, 'German'),
    ('Data Scientist Intern', D, 'Austria', False, 'an internship is not a thesis'),
    ('Senior Data Scientist', D, 'Austria', False, 'an ordinary job'),
]:
    check(f'{why}: {title[:40]!r}', TH.is_thesis(job(title=title, country=country,
                                                     description=body)) is want)
# Every one of these was measured firing wrongly on a real corpus, and every one from a
# BODY. Reading the title alone is what makes them harmless.
for body, why in [
    ('Internationale Projektarbeit ist moeglich.', 'a perk on a salaried job'),
    ('Positionsebene Berufseinstieg', 'a metadata field'),
    ('You will support our thesis students with their work.', 'someone else\'s thesis'),
]:
    check(f'body-only mention is not a thesis: {why}',
          TH.is_thesis(job(title='Data Scientist', description=body)) is False)

# `_search_title` is the job title in the Search box, which the Filter writes onto every row.
# Set here to what each thesis is about, so these checks reach the rule they are about rather
# than stopping at the title check.
check('a PhD thesis is dropped',
      TH.survives(job(title='PhD Thesis "Satellite Remote Sensing"',
                      description='Fully remote.', _search_title='Remote Sensing'))[0] is False)
check('  ...and the reason says so',
      TH.survives(job(title='PhD Thesis "Satellite Remote Sensing"',
                      description='Fully remote.', _search_title='Remote Sensing'))[1]
      == 'a PhD, not a thesis')
check('a Doktorandenstelle is dropped',
      TH.survives(job(title='Doktorandenstelle Photonik', country='Austria',
                      description=DE_BODY + ' Remote moeglich.'))[0] is False)
# Reading the title is what makes this safe: a Master's thesis whose body mentions PhD
# colleagues is still a Master's thesis.
check('a Master thesis mentioning PhD colleagues survives',
      TH.survives(job(title='Master Thesis - Photonics', _search_title='Photonics',
                      description='Fully remote. You will work with our PhD students.'))[0]
      is True)
# The difference from the salaried rule, and the reason the module exists. Measured over
# both real corpora, 38% of these adverts never raise the subject at all.
silent = job(title='Master Thesis - Photonics', location='Villach',
             description='You will join our research team and write your thesis with us.')
check('a silent thesis survives the Thesis location rule',
      TH.passes_location_rule(silent) is True)
check('  ...where the Job module would have dropped it',
      p.passes_work_location_rule(silent) is False)
check('a stated on-site thesis outside Milan/Turin is dropped',
      TH.passes_location_rule(job(title='Master Thesis', location='Vienna',
                                  description='On-site in our Vienna office.')) is False)
check('  ...and the same wording in Turin is dropped too: no city is exempt',
      TH.passes_location_rule(job(title='Tesi di laurea', location='Torino',
                                  description='In sede, tre giorni in ufficio.')) is False)
check('an unpaid thesis is dropped',
      TH.survives(job(title='Master Thesis - Photonics',
                      description='Fully remote. This is an unpaid position.'))[0] is False)
check('a listings page is not a vacancy',
      TH.survives(job(title='Thesis Jobs | aktuell 5 offen | karriere.at',
                      description='Fully remote.'))[1] == 'a listings page, not a vacancy')

section('1.22  the Internship module')
for title, body, country, want, why in [
    ('Data Scientist Intern', D, 'Austria', True, 'title ENDING in the word'),
    ('Internship - Speech Recognition', D, 'Austria', True, 'English internship'),
    ('Stage Data Scientist', NL_BODY, 'Netherlands', True, 'Dutch stage'),
    ('Praktikum im Bereich IT-Reporting', DE_BODY, 'Austria', True, 'German Praktikum'),
    ('Werkstudent Data & AI', DE_BODY, 'Austria', True, 'German working student'),
    ('Software Engineer, Product (Co-op)', D, 'Canada', True, 'a co-op'),
    ('Internal Communications Manager', D, 'Austria', False, '"intern" in "internal"'),
    ('International Sales Lead', D, 'Austria', False, '"intern" in "international"'),
    ('Master Thesis - Photonics', D, 'Austria', False, 'a thesis is not an internship'),
    ('Senior Data Scientist', D, 'Austria', False, 'an ordinary job'),
]:
    check(f'{why}: {title[:40]!r}',
          IN.is_internship(job(title=title, country=country, description=body)) is want)
for body, why in [
    ('Let op: dit is geen stageplek voor studenten.', 'Dutch "this is NOT an internship"'),
    ('We are in partnership with the Co-Op supermarket.', 'the supermarket'),
    ('We connect learners to apprenticeships worldwide.', 'what the company sells'),
]:
    check(f'body-only mention is not an internship: {why}',
          IN.is_internship(job(title='Data Scientist', description=body)) is False)

check('a silent internship survives the Internship location rule',
      IN.passes_location_rule(job(title='Internship Data', location='Graz',
                                  description='Join our team for six months.')) is True)
check('a stated on-site internship outside Milan/Turin is dropped',
      IN.passes_location_rule(job(title='Internship Data', location='Vienna',
                                  description='On-site in our Vienna office.')) is False)
check('  ...and the same wording in Milan is dropped too: no city is exempt',
      IN.passes_location_rule(job(title='Tirocinio curriculare', location='Milano',
                                  description='In sede, ibrido, tre giorni.')) is False)
check('an explicit denial of remote is dropped even when remote appears',
      IN.passes_location_rule(job(title='Internship Data',
                                  description='Remote work is not available.')) is False)
check('an unpaid internship is dropped',
      IN.survives(job(title='Data Science Intern', _search_title='Data Science',
                      description='Fully remote. This is an unpaid internship.'))[0] is False)
check('  ...and the reason says so',
      IN.survives(job(title='Data Science Intern', _search_title='Data Science',
                      description='Fully remote. This is an unpaid internship.'))[1]
      == 'unpaid')
check('an internship needing German is dropped',
      IN.survives(job(title='Praktikum IT-Reporting', country='Austria',
                      description=DE_BODY + ' Remote moeglich. Sehr gute '
                                            'Deutschkenntnisse erforderlich.'))[0] is False)
# The Thesis module has a PhD rule; this one must not, because here the word means nothing.
check('the Internship module has no PhD rule',
      IN.survives(job(title='Data Science Intern', _search_title='Data Science',
                      description='Fully remote. Work with our PhD team.'))[0] is True)

section('1.23  the three modules over one set of listings')
rows = [
    # location='' matters: the base helper says 'Remote', which would let these through the
    # salaried rule too and defeat the point. Both say nothing about where -- the exact
    # shape 38% of them have.
    job(title='Master Thesis - Photonics', url='https://x/thesis', location='',
        description='You will write your thesis with our research team in Villach.'),
    job(title='Internship - Speech Recognition for Robotics', url='https://x/intern',
        location='', description='Join our robotics team in Villach for six months.'),
    job(title='Senior Data Scientist', url='https://x/senior'),
    job(title='Data Engineer', url='https://x/plain', description=D),
]
kept, _removed, _flagged = p.reapply_filters([dict(r) for r in rows])
# Each module is given the job title its own listing is about, so what is tested here is
# which KIND of listing each module recognises -- not the title check, which has its own
# section.
theses, _tr = p.find_thesis_postings([dict(r) for r in rows], search_title='Photonics')
interns, _ir = p.find_internship_postings([dict(r) for r in rows],
                                          search_title='Speech Recognition')
check('the Thesis module returns the thesis and nothing else',
      [j['url'] for j in theses] == ['https://x/thesis'], [j['url'] for j in theses])
check('the Internship module returns the internship and nothing else',
      [j['url'] for j in interns] == ['https://x/intern'], [j['url'] for j in interns])
check('the Job module returns neither',
      not ({'https://x/thesis', 'https://x/intern'} & {j.get('url') for j in kept}),
      [j.get('url') for j in kept])
check('the Thesis module labels its rows for the Type column',
      theses[0]['Category'] == 'Thesis')
check('the Internship module labels its rows',
      interns[0]['Category'] == 'Internship')
# Each module is handed its own copy, so what one writes cannot be read by another. This is
# what makes running them at the same time safe.
originals = [dict(r) for r in rows]
p.find_thesis_postings(originals)
check('a module never writes Category onto the caller\'s rows',
      not [r for r in originals if 'Category' in r],
      [r.get('title') for r in originals if 'Category' in r])
# Duplicate copies of one advert reach a search through several boards.
copies = [job(title='Internship - Experiment Management System CDM Support',
              url='https://x/a', company='Infineon Technologies',
              description='Remote internship. ' + D * 3),
          job(title='Internship - Experiment Management System CDM Support',
              url='https://x/b', company='siehe Beschreibung',
              description='Remote internship. ' + D * 3 + ' Published via EURES.')]
deduped, _ir2 = p.find_internship_postings([dict(r) for r in copies],
                                           search_title='Experiment Management')
check('two copies of one internship come back once', len(deduped) == 1, len(deduped))
check('  ...and it is the copy that names the employer',
      deduped[0]['company'] == 'Infineon Technologies', deduped[0]['company'])
# A generic title shared by two employers is NOT one posting -- measured: 15 such pairs
# across both real corpora, every one of them two different placements.
generic = [job(title='Werkstudent Data & AI', url='https://x/c', company='TGW',
               country='Austria', description=DE_BODY + ' Remote moeglich.'),
           job(title='Werkstudent Data & AI', url='https://x/d', company='Siemens',
               country='Austria',
               description='Ganz andere Aufgabe bei uns im Bereich Energie und Netze, '
                           'mit Fokus auf Messdaten und Auswertung. Remote moeglich.')]
both, _ir3 = p.find_internship_postings([dict(r) for r in generic], search_title='Data')
check('two different placements with the same generic title both survive',
      len(both) == 2, len(both))


section('1.24  each module has its own Claude prompt')
from app.pipeline.thesis import claude as TC  # noqa: E402
from app.pipeline.internship import claude as IC  # noqa: E402
from app.pipeline import claude_screen as JC  # noqa: E402

prompts = {'Job': JC.CLAUDE_SCREEN_SYSTEM_PROMPT,
           'Thesis': TC.THESIS_SYSTEM_PROMPT,
           'Internship': IC.INTERNSHIP_SYSTEM_PROMPT}
check('all three prompts are different text',
      len({v for v in prompts.values()}) == 3)
for name, text in prompts.items():
    check(f'the {name} prompt is substantial', len(text) > 1500, len(text))
# The three answer schemas must differ too -- a verdict reached under one is not
# interchangeable with a verdict reached under another.
check('Thesis and Internship do not share a schema object',
      TC._OUTPUT_SCHEMA is not IC._OUTPUT_SCHEMA)
check('their prompt-version hashes differ', TC._PROMPT_VERSION != IC._PROMPT_VERSION)
# The Claude files must not reach into each other or into the Job module's.
for name, path, forbidden in (
        ('Thesis', 'app/pipeline/thesis/claude.py', ('claude_screen', 'internship')),
        ('Internship', 'app/pipeline/internship/claude.py', ('claude_screen', 'thesis'))):
    leaks = sorted(i for i in _imports(os.path.join(_ROOT, path))
                   if any(f in i for f in forbidden))
    check(f'the {name} Claude pass imports nothing from the others', not leaks, leaks)
# Rule 1 in both is the one that earns the pass its keep: judging an UNSTATED arrangement
# from the nature of the work. The Job prompt must NOT say that -- there, silence already
# means drop and inference would be a licence to invent.
# Whitespace is collapsed first: these phrases are wrapped across lines in the prompts, and
# a test that breaks when a paragraph is re-flowed is testing the formatting, not the rule.
_flat = lambda text: ' '.join(text.split())  # noqa: E731
check('the Thesis prompt tells Claude to judge silence by the work',
      'Silence is not evidence either way' in _flat(TC.THESIS_SYSTEM_PROMPT))
check('the Internship prompt does too',
      'Silence is not evidence either way' in _flat(IC.INTERNSHIP_SYSTEM_PROMPT))
check('the Job prompt still demands a quote before dropping',
      'Quote before you drop' in _flat(JC.CLAUDE_SCREEN_SYSTEM_PROMPT))
# Each schema forces the location question to be answered in words before a verdict.
for name, schema in (('Thesis', TC._OUTPUT_SCHEMA), ('Internship', IC._OUTPUT_SCHEMA)):
    order = list(schema['properties'])
    check(f'{name}: location_basis is decided before the verdict',
          order.index('location_basis') < order.index('verdict'), order)
    check(f'{name}: checked comes first of all', order[0] == 'checked', order)

section('1.25  the Claude pass never loses a listing to a failure')
import json  # noqa: E402


class _FakeMessages:
    """Stands in for the SDK. Returns whatever answers the test sets up, or raises."""

    def __init__(self, answers, error=None, stop_reason='end_turn'):
        self.answers, self.error, self.stop_reason = answers, error, stop_reason
        self.calls = 0
        self.batches = self          # batches are never reached in these tests

    def create(self, **params):
        self.calls += 1
        if self.error:
            raise self.error
        payload = json.dumps({'answers': self.answers})
        block = type('B', (), {'type': 'text', 'text': payload})()
        return type('R', (), {'content': [block], 'stop_reason': self.stop_reason})()


class _FakeClient:
    def __init__(self, *a, **kw):
        self.messages = _FakeMessages(*a, **kw)


t_row = job(title='Master Thesis - Photonics', url='https://x/t1', location='',
            description='Write your thesis with our photonics team in Villach.')
i_row = job(title='Video Editor Intern', url='https://x/i1', location='Gurugram, HR, IN',
            description='Edit our social media videos. Join our Gurugram studio team.')

# A DROP with a reason is applied.
answers = [{'listing': 1, 'checked': 'rule 1: lab work', 'location_basis':
            'silent - work needs a lab or a site', 'verdict': 'DROP', 'rule': 1,
            'reason': 'photonics lab work, cannot be remote', 'match': 20}]
kept = TC.screen(_FakeClient(answers), [t_row])
check('the Thesis pass reads a DROP', kept[id(t_row)][0] is True, kept)
check('  ...and carries the reason', 'photonics' in kept[id(t_row)][1], kept)
check('  ...and the location basis', 'lab' in (kept[id(t_row)][3] or ''), kept)

answers = [{'listing': 1, 'checked': 'rule 2: social media', 'field': 'social media',
            'location_basis': 'silent - work needs a site', 'verdict': 'DROP', 'rule': 2,
            'reason': 'social media, not data work', 'match': 5}]
got = IC.screen(_FakeClient(answers), [i_row])
check('the Internship pass reads a DROP', got[id(i_row)][0] is True, got)
check('  ...and names the field', got[id(i_row)][4] == 'social media', got)

# An answer numbered outside the group is discarded, never applied to a neighbour.
answers = [{'listing': 7, 'checked': '', 'location_basis': 'says remote', 'verdict': 'DROP',
            'rule': 1, 'reason': 'x', 'match': 10}]
check('an answer with a bad listing number is discarded',
      TC.screen(_FakeClient(answers), [t_row]) == {}, 'applied anyway')

def _stub_claude_pass(module, rows, answers, error=None):
    """Run a module's _claude_pass with the SDK swapped out."""
    import types
    fake_sdk = types.SimpleNamespace(Anthropic=lambda api_key=None: _FakeClient(answers,
                                                                                error))
    real = sys.modules.get('anthropic')
    sys.modules['anthropic'] = fake_sdk
    try:
        return module._claude_pass(rows, 'k')
    finally:
        if real is not None:
            sys.modules['anthropic'] = real
        else:
            del sys.modules['anthropic']


from app.pipeline.thesis import finder as TF  # noqa: E402
from app.pipeline.internship import finder as IF  # noqa: E402

row = dict(t_row)
survivors, reasons = _stub_claude_pass(TF, [row], [])       # no answers at all
check('a thesis Claude never answered about survives', len(survivors) == 1, survivors)
check('  ...and is not counted as removed', not reasons, reasons)

row = dict(t_row)
survivors, reasons = _stub_claude_pass(TF, [row], [], error=RuntimeError('network down'))
check('a thesis survives a total API failure', len(survivors) == 1, survivors)

row = dict(i_row)
survivors, reasons = _stub_claude_pass(IF, [row], [], error=RuntimeError('network down'))
check('an internship survives a total API failure', len(survivors) == 1, survivors)

# Part one only decides now. The Match % and its floor moved to part two, the résumé match
# (claude_screen/worth.py) -- so a KEEP is kept whatever score an old answer carries, and
# this part writes no score that could overwrite part two's.
row = dict(t_row)
low = [{'listing': 1, 'checked': '', 'location_basis': 'says remote', 'verdict': 'KEEP',
        'rule': 0, 'reason': '', 'match': 10}]
survivors, reasons = _stub_claude_pass(TF, [row], low)
check('part one keeps a KEEP -- the match floor is part two\'s', len(survivors) == 1, survivors)
check('  ...and removes nothing for a score', not reasons, reasons)
check('  ...and writes no score of its own', TC.MATCH_KEY not in survivors[0], survivors[0])
check('  ...but records a cache key, so a re-run need not pay again',
      survivors[0].get(TC.CACHE_KEY))
row = dict(i_row, _search_title='Video Editor')
survivors, reasons = _stub_claude_pass(IF, [row], [dict(low[0], field='video')])
check('the Internship pass keeps a KEEP whatever the score too', len(survivors) == 1, survivors)
check('neither schema asks part one for a match any more',
      'match' not in TC._OUTPUT_SCHEMA['properties']
      and 'match' not in IC._OUTPUT_SCHEMA['properties']
      and 'match' not in JC._SCREEN_OUTPUT_SCHEMA['properties'])

# Editing a prompt must invalidate every cached verdict. Checked by construction: the hash
# covers the prompt text, so two different prompts cannot produce one key.
before = TC.cache_key(dict(t_row))
check('the cache key changes when the listing changes',
      TC.cache_key(dict(t_row, description='something else entirely')) != before)

# Without a key configured, no module calls Claude at all -- and the keyword result stands.
kept_no_key, _r = p.find_thesis_postings([dict(t_row)], search_title='Photonics')
check('no API key means no Claude call, and the keyword verdict stands',
      len(kept_no_key) == 1, kept_no_key)


section('1.26  one posting in two languages is one posting')
# everox published this once and both copies reached a real Netherlands run, and both were
# shown to Sina as separate internships. Nothing else catches it: the URLs differ, the
# titles differ once each is in its own language, and the bodies share almost no tokens.
pair = [job(title='Student Worker AI & Automation Workflows', company='everox',
            url='https://everox.homerun.co/student-worker-ai-automation-workflows/en_GB/?source=Indeed',
            description='Help us build the future of circular concrete. Are you passionate '
                        'about Artificial Intelligence and automation? Fully remote.'),
        job(title='Werkstudent AI & Automation', company='everox',
            url='https://everox.homerun.co/student-worker-ai-automation-workflows/nl/?source=Indeed',
            description='Help us build the future of circular concrete. Heb jij een passie '
                        'voor Artificial Intelligence en automatisering? Volledig remote.')]
merged, removed = IN.remove_duplicates([dict(r) for r in pair])
check('two language versions of one advert collapse to one', len(merged) == 1, len(merged))
check('  ...and one copy was counted as removed', removed == 1, removed)
check('the Thesis module does the same',
      len(TH.remove_duplicates([dict(r) for r in pair])[0]) == 1)
# The stripping must name real languages. An earlier draft removed ANY two-letter segment,
# which would merge two different postings whose addresses differ in an id or a market code.
different = [job(title='Data Science Intern', url='https://boards.example.com/job/id/111',
                 company='A', description='Remote internship. ' + D),
             job(title='Machine Learning Intern', url='https://boards.example.com/job/id/222',
                 company='B', description='A completely different remote internship at '
                                          'another company entirely, in another sector.')]
check('two different postings under a two-letter path segment stay separate',
      len(IN.remove_duplicates([dict(r) for r in different])[0]) == 2)
check('a listing with no url is never merged on the strength of that',
      len(IN.remove_duplicates([dict(r, url='') for r in different])[0]) == 2)
# The copy that names the employer is the one that survives.
placeheld = [job(title='Internship Data', company='siehe Beschreibung',
                 url='https://europa.eu/eures/x/de/1', description='Remote. ' + D),
             job(title='Internship Data', company='Infineon Technologies',
                 url='https://europa.eu/eures/x/en/1', description='Remote. ' + D)]
survivor = IN.remove_duplicates([dict(r) for r in placeheld])[0]
check('the surviving copy is the one that names the employer',
      len(survivor) == 1 and survivor[0]['company'] == 'Infineon Technologies',
      [r['company'] for r in survivor])

section('1.27  the working-student rule, and honest location reporting')
# A Werkstudent role is a permanent part-time job alongside study in that same city. Sina
# lives in Italy, so he cannot hold one in Rotterdam or Graz however remote-friendly the
# work sounds -- and the whole Netherlands survivor list was made of these.
flat = ' '.join(IC.INTERNSHIP_SYSTEM_PROMPT.split())
check('the Internship prompt has a working-student rule',
      'calls itself a working-student role and does not say the role is remote' in flat)
check('  ...that fires only on a named word, never on an inferred arrangement',
      'This rule fires only when the posting **uses one of these words**' in flat
      and 'An "Intern" or a "Traineeship" is not one of these' in flat)
check('  ...and says a home-office benefit does not count as that statement',
      'A home-office benefit is not that statement' in flat)
check('  ...and has no home-city exception any more: Remote means Remote',
      'remain the exception' not in flat and 'everyday commute' not in flat)
# The three prompts must agree on the shape of rule 1, because a listing dropped for the
# country or for saying nothing is the one failure all three share.
for name, text in (('Job', JC.CLAUDE_SCREEN_SYSTEM_PROMPT),
                   ('Thesis', TC.THESIS_SYSTEM_PROMPT),
                   ('Internship', IC.INTERNSHIP_SYSTEM_PROMPT)):
    one = ' '.join(text.split())
    check(f'{name}: rule 1 is a ladder ending in KEEP',
          '1a.' in one and '1b.' in one and 'is a KEEP' in one)
    check(f'{name}: the employer\'s address is named as not-a-reason',
          'They say where the employer is' in one)
    check(f'{name}: an implied requirement is named as not-a-reason',
          'you are inferring a requirement the posting does not make' in one)
# Both prompts must now be able to say a posting NAMED a place, rather than calling it
# silent. Reporting "silent" for a posting that opens "Location: Amsterdam" is how a wrong
# Log survives a right verdict.
for name, schema in (('Thesis', TC._OUTPUT_SCHEMA), ('Internship', IC._OUTPUT_SCHEMA)):
    values = schema['properties']['location_basis']['enum']
    check(f'{name}: can report that a place was named',
          any('names a place' in v for v in values), values)
    check(f'{name}: can report a home-office benefit',
          any('only as a benefit' in v for v in values), values)
    check(f'{name}: still has both silent values',
          sum(1 for v in values if v.startswith('silent')) == 2, values)
check('Internship: can report a working-student role',
      any('working-student' in v for v in IC._OUTPUT_SCHEMA['properties']
          ['location_basis']['enum']))
# Editing a prompt has to invalidate the cached verdicts, or a re-run would reuse decisions
# made under the old rules. The hash covers prompt AND schema, so both edits above did.
check('the prompt hashes still differ between the two modules',
      TC._PROMPT_VERSION != IC._PROMPT_VERSION)
check('the rule numbering in the Internship schema matches the prompt',
      'rules 1-9' in IC._OUTPUT_SCHEMA['properties']['checked']['description']
      and '(1-9)' in IC._OUTPUT_SCHEMA['properties']['rule']['description'])


section('1.28  a posting in another language that never names English')
# Sina's rule, already carried by the Job module and missing from these two until a real run
# ended with a Randstad traineeship written entirely in Dutch on the list.
EN_BODY = ('We are looking for a student to join our data team and work with us on our '
           'models. You will have the chance to build things that matter for our customers '
           'and you will learn from experienced engineers in a friendly team.')
NL_LONG = ('Voor onze afdeling zoeken wij een enthousiaste kandidaat die met ons meedenkt '
           'over data en klantbeleving. Je werkt samen met collega\'s aan uiteenlopende '
           'vraagstukken en je krijgt veel ruimte om jezelf te ontwikkelen binnen een '
           'informele organisatie waar eigen initiatief wordt gewaardeerd en beloond.')
for mod, title in ((IN, 'Stage Data Scientist'), (TH, 'Afstudeeropdracht Data')):
    name = mod.__name__.rsplit('.', 1)[-1]
    check(f'{name}: an English posting is never silent about English',
          mod.finder.silent_about_english(
              job(title=title, description=EN_BODY, country='Netherlands')) is False)
    check(f'{name}: a Dutch posting that never says Engels is',
          mod.finder.silent_about_english(
              job(title=title, description=NL_LONG, country='Netherlands')) is True)
    check(f'{name}:   ...but not if it says "Engels" in its own language',
          mod.finder.silent_about_english(
              job(title=title, description=NL_LONG + ' Goede kennis van Engels.',
                  country='Netherlands')) is False)
    # The check must read the ORIGINAL text. After translation "Engels" reads as "English",
    # which would make every listing look as though it had mentioned it and the rule would
    # never fire at all.
    translated = job(title='Internship Data', description=NL_LONG.replace('data', 'data'),
                     country='Netherlands')
    translated['description'] = EN_BODY            # what translation left behind
    translated['_original_description'] = NL_LONG  # what the board actually wrote
    check(f'{name}: a translated Dutch posting is still judged on its Dutch original',
          mod.finder.silent_about_english(translated) is True)
    # A source that returns almost no text has not been silent, it had nothing to say.
    check(f'{name}: a title-only listing is never dropped for this',
          mod.finder.silent_about_english(
              job(title=title, description='Data Scientist at Jenoptik AG',
                  country='Germany')) is False)
# The threshold was measured, and the direction that matters is that no English posting is
# ever called foreign -- that mistake deletes something Sina can read.
check('the English-marker floor is the measured one',
      IN.finder._ENGLISH_MARKER_MINIMUM == 8.0, IN.finder._ENGLISH_MARKER_MINIMUM)
# Each module defines the rule in its own file. Checked in the source rather than by
# comparing the compiled objects: re.compile caches by pattern text, so two modules that
# compile the same string get the same object back -- an identity check there would be
# testing re's cache, not whether the two modules share anything.
for label, path in (('Thesis', 'app/pipeline/thesis/finder.py'),
                    ('Internship', 'app/pipeline/internship/finder.py')):
    source = io.open(os.path.join(_ROOT, path), encoding='utf-8').read()
    check(f'{label} defines the English-marker rule in its own file',
          '_ENGLISH_MARKERS = (' in source and '_ENGLISH_MARKER_MINIMUM = ' in source)
# End to end: the rule has to actually remove such a listing from the module's output.
dutch_only = [job(title='Trainee Data', url='https://x/nl-only', country='Netherlands',
                  description=NL_LONG + ' Thuiswerken is mogelijk.')]
kept, reasons = p.find_internship_postings([dict(r) for r in dutch_only], search_title='Data')
check('a Dutch-only internship does not reach the final list', not kept, kept)
check('  ...and the reason says why',
      any('never mentions English' in why for why in reasons), reasons)


section('1.29  master theses only')
# Sina's rule. The Infineon "Bachelor Thesis - Artificial Intelligence in Microcontroller"
# reached a real final list at 72%, and its requirements read "Education: Pursuing a
# Bachelor's degree (at least in the 5th semester)" -- someone he no longer is.
AT_BODY = ('You will work with our team on models and data. Education: Pursuing a '
           "Bachelor's degree, at least in the 5th semester, in a relevant field. "
           'Language Skills: Fluency in English, with German as a plus.')
check('a bachelor thesis is dropped',
      TH.finder.is_bachelor_only(
          job(title='Bachelor Thesis - AI in Microcontroller', country='Austria',
              description=AT_BODY)) is True)
check('  ...and survives() gives the reason',
      TH.survives(job(title='Bachelor Thesis - AI in Microcontroller', country='Austria',
                      description=AT_BODY, _search_title='AI'))[1]
      == 'a bachelor thesis, not a master one')
check('a master thesis is kept',
      TH.finder.is_bachelor_only(
          job(title='Master Thesis - Differentiable Ray Tracing', country='Austria',
              description="You are pursuing a master's degree in Computer Science. "
                          'English language skills. EUR 1,379.60 gross per month.')) is False)
# The half that matters: plenty of adverts take either, and those are his to take.
for title, body, why in [
    ('Bachelor or Master Thesis - Radio Modelling', D, 'both offered in the title'),
    ('Bachelor-/Masterarbeit Datenanalyse',
     'Wir bieten eine Bachelorarbeit oder Masterarbeit in unserem Team an.',
     'both offered, in German'),
    ('Abschlussarbeit', 'This thesis is open to master students. Fully remote.',
     'level only in the body'),
]:
    check(f'a thesis open to either is kept: {why}',
          TH.finder.is_bachelor_only(
              job(title=title, country='Austria', description=body)) is False)
check('a thesis that never names a level is kept',
      TH.finder.is_bachelor_only(
          job(title='Afstudeeropdracht Data', country='Netherlands',
              description='You will build a model with our data team. Remote possible.'))
      is False)
# The prompt has to carry the same rule, because a level is as often stated in a sentence as
# in a keyword.
flat_thesis = ' '.join(TC.THESIS_SYSTEM_PROMPT.split())
check('the Thesis prompt asks for master level only',
      'It is not at his level' in flat_thesis and 'for a bachelor student' in flat_thesis)
check('  ...and keeps a thesis open to either',
      '"Bachelor or Master thesis", "Bachelor-/Masterarbeit" → KEEP' in flat_thesis)
check('  ...and keeps one that never says which level',
      'Silence is not a bachelor thesis' in flat_thesis)
check('the master and bachelor vocabularies cover all 13 languages',
      not [c for c in TH.words.LANGUAGES
           if not TH.words.LANGUAGES[c].get('master')
           or not TH.words.LANGUAGES[c].get('bachelor')])
# Each module records its score under its own key, so the Jobs table has to read all three
# or a judged row arrives with an em dash where its score should be.
_jobs_page = io.open(os.path.join(_ROOT, 'app/ui/jobs_page.py'), encoding='utf-8').read()
for key in ('claude_match', 'thesis_claude_match', 'internship_claude_match'):
    check(f'the Match column reads {key}', f"'{key}'" in _jobs_page)


section('1.30  a page of jobs is not a job')
from app.pipeline import pages as PG  # noqa: E402

# The URL decides. Every one of these was taken from the real Austrian and Dutch corpora,
# and the left column is what a title-only rule got wrong.
for url, single, why in [
    ('http://nl.indeed.com/job/back-end-developer-a64bd8cad308', True, 'Indeed, hex id'),
    ('https://www.karriere.at/jobs/10028125', True, 'karriere, numeric id'),
    ('https://www.wearedevelopers.com/jobs/ext/2698650-aws-solutions-architect', True,
     'id in front of the slug'),
    ('https://remoteOK.com/remote-jobs/remote-ai-engineer-benzinga-1137224', True,
     'remoteOK, id behind it'),
    ('https://arc.dev/remote-jobs/details/experienced-backend-developer-pgs0dchx5x', True,
     'arc.dev, details segment'),
    ('https://europa.eu/eures/portal/jv-se/jv-details/MTczMzcyNTkgNDM', True, 'EURES'),
    ('https://www.karriere.at/jobs/software', False, 'karriere category'),
    ('https://www.karriere.at/jobs/maria-enzersdorf', False, 'karriere by town'),
    ('https://arc.dev/remote-jobs/data-cleaning', False, 'arc.dev category'),
    ('https://arc.dev/en-it/remote-jobs', False, 'arc.dev by country'),
    ('https://eudatajobs.com/search', False, 'a search page'),
    ('https://www.wearedevelopers.com/jobs/ls/austria/vienna/tensorflow', False, 'a filter'),
    ('https://work.turing.com/jobs?search=Data+Scientist', False, 'a saved search'),
    ('https://aiaustria.com/jobs', False, 'a board index'),
]:
    check(f'{"one posting" if single else "a list"}: {why}',
          PG.is_single_posting_url(url) is single, url[:60])

# The digit is the whole trick, and an earlier version that looked only for an 8-character
# trailing token called "engineer" an id.
check('a trailing word is not an id',
      PG.is_single_posting_url('https://x.com/jobs/data-engineer') is False)
check('  ...but a trailing token with a digit is',
      PG.is_single_posting_url('https://x.com/jobs/data-engineer-pgs0dchx5x') is True)

# A title that counts vacancies is evidence; a URL naming one posting outranks it.
check('a counted title flags a page',
      PG.is_listing_page({'url': 'https://x.com/list',
                          'title': 'Software Jobs | aktuell 1.500+ offen'}) is True)
check('  ...but not when the url names one posting',
      PG.is_listing_page({'url': 'https://x.com/jobs/10028125',
                          'title': 'Student Job (f/m/x) - CIB AI & Data Team'}) is False)
kept, removed = PG.remove_listing_pages([
    # Marked emptied, as expand_listing_pages marks a page once it has taken its contents.
    {'url': 'https://www.karriere.at/jobs/software', 'title': 'Software Jobs',
     PG.EMPTIED_KEY: True},
    {'url': 'https://www.karriere.at/jobs/10028125', 'title': 'Data Engineer'},
])
check('remove_listing_pages splits them', len(kept) == 1 and len(removed) == 1)
check('  ...keeping the vacancy', kept[0]['title'] == 'Data Engineer')

# An index page goes whether or not anything could be taken out of it.
#
# It used to be kept when expansion came back empty, on the reasoning that discarding it
# would take whatever it listed with it. Sina's question retired that: what good is a kept
# page that gave up nothing? Measured on the second German corpus, none at all -- of the 88
# that could not be emptied, 76 were dropped by the ordinary filters anyway and every one of
# the 12 that reached Claude was an index page, 61,845 characters of "Data Science Jobs in
# Germany - 2026". Keeping a page saves the vacancies inside it only if keeping it is a route
# to them, and when the page could not be emptied it is not.
#
# What the old rule was really protecting is a genuine vacancy misread as an index -- and
# that is handled in is_single_posting_url, exercised directly below.
never_opened = {'url': 'https://www.navartisglobal.com/data-engineer-jobs-in-austria',
                'title': 'Data Engineer jobs in Austria'}
check('an index page nothing could be taken from is dropped, not kept',
      PG.remove_listing_pages([dict(never_opened)])[0] == [])
check('  ...and so is one that has been emptied',
      PG.remove_listing_pages([dict(never_opened, **{PG.EMPTIED_KEY: True})])[0] == [])
check('an unknown board\'s index page goes too',
      PG.remove_listing_pages([{'url': 'https://unknown-board.example/vacatures',
                                'title': '40 vacancies'}])[0] == [])
# ...and the half that matters: a real vacancy is never caught by any of this, because the
# single-posting test wins outright inside is_listing_page.
check('a real vacancy on an unknown board survives',
      PG.remove_listing_pages([
          {'url': 'https://unknown-board.example/vacatures/senior-data-engineer-amsterdam',
           'title': 'Senior Data Engineer'}])[0] != [])

# A last path segment that reads as a job title, on a board with no numeric ids. Both of
# these are real vacancies that the first version of the rule called index pages.
for url, why in [
    ('https://www.aop-health.com/global_en/careers/jobs/supply-chain-business-excellence-manager',
     'AOP Health, six hyphenated words'),
    ('https://weworkremotely.com/remote-jobs/airbnb-senior-data-scientist',
     'WeWorkRemotely, four'),
]:
    check(f'a title-shaped path is one posting: {why}',
          PG.is_single_posting_url(url) is True, url[:64])
for url, why in [
    ('https://www.karriere.at/jobs/software', 'one word'),
    ('https://arc.dev/remote-jobs/data-cleaning', 'two words'),
    ('https://arc.dev/en-it/remote-jobs/devops', 'a country and a word'),
    # Length alone would have called this one a posting: five hyphenated words, and a
    # category page. The word "jobs" in the slug is what gives it away -- a board names a
    # category after what it lists, a posting after the role.
    ('https://www.navartisglobal.com/data-engineer-jobs-in-austria', 'long, but says "jobs"'),
    ('https://example.com/stellenangebote-data-scientist-in-wien', 'long, says "stellen"'),
]:
    check(f'  ...but a category is not: {why}',
          PG.is_single_posting_url(url) is False, url[:64])

# Opening one up: only posting-shaped links, only one level, never a link already known.
HTML = '''<html><body>
  <a href="/jobs/10028738">A real job</a>
  <a href="/jobs/10026971">Another</a>
  <a href="/jobs/software">Software Jobs category</a>
  <a href="/jobs/engineer">Engineer Jobs category</a>
  <a href="/jobs/10028125">Already known</a>
  <a href="https://elsewhere.com/jobs/10099999">Another site</a>
</body></html>'''
inside = PG.postings_inside(HTML, 'https://www.karriere.at/jobs/software',
                            {'https://www.karriere.at/jobs/10028125'})
check('only posting-shaped links come out', len(inside) == 2, inside)
check('  ...category pages are not followed',
      not [x for x in inside if x.endswith(('software', 'engineer'))], inside)
check('  ...a link the search already has is skipped',
      '10028125' not in ' '.join(inside), inside)
check('  ...and another site is left alone',
      'elsewhere.com' not in ' '.join(inside), inside)
check('a page with nothing inside returns nothing',
      PG.postings_inside('<html><body><a href="/about">About</a></body></html>',
                         'https://x.com/jobs', set()) == [])

section('1.31  a description that is only a menu')
from app.pipeline.enrich import looks_like_chrome_only  # noqa: E402

# arc.dev sent 505 characters of this, and every one of its postings carried the same.
MENU = ('For companies Hire developers Hire designers Hire marketers Hire product managers '
        'Hire project managers Hire assistants How Arc works How much can you save? Case '
        'studies Pricing Resources Remote dev salary explorer Freelance rate explorer')
check('a menu is recognised as carrying no posting',
      looks_like_chrome_only(MENU) is True)
check('an empty description too', looks_like_chrome_only('') is True)
check('  ...and None', looks_like_chrome_only(None) is True)
REAL = ('We are looking for a data scientist to join our team. Your profile: experience '
        'with Python and SQL, a degree in a relevant field, and three years of practice. '
        'We offer a competitive salary and remote work.')
check('a real posting is not', looks_like_chrome_only(REAL) is False)
GERMAN = ('Ihre Aufgaben: Sie entwickeln Modelle. Anforderungen: Erfahrung mit Python, '
          'gute Kenntnisse in SQL. Wir bieten ein attraktives Gehalt.')
check('a German posting is not either', looks_like_chrome_only(GERMAN) is False)
# A long page is left alone whatever its menu, because the posting is in there somewhere.
check('a long page is never called chrome-only',
      looks_like_chrome_only(MENU + ' x' * 3000) is False)

# The replacement guard asks a different question and must not inherit that allowance. A
# LinkedIn posting of 4,344 characters was lost from a real run because a longer page --
# a sign-in wall is easily longer than a job advert -- was allowed to overwrite it on
# length alone.
from app.pipeline.enrich import carries_posting_words  # noqa: E402

check('a long menu still carries no posting words',
      carries_posting_words(MENU + ' x' * 3000) is False)
check('  ...where looks_like_chrome_only would have waved it through',
      looks_like_chrome_only(MENU + ' x' * 3000) is False)
check('a real posting carries them', carries_posting_words(REAL) is True)
check('a German one too', carries_posting_words(GERMAN) is True)
check('an empty string does not', carries_posting_words('') is False)
_enrich_src = io.open(os.path.join(_ROOT, 'app/pipeline/enrich.py'), encoding='utf-8').read()
check('the replacement guard uses it, not the length-forgiving one',
      'and carries_posting_words(text)' in _enrich_src)


section('1.32  a grouped answer schema must declare what it requires')
# The worst fault of the campaign. The Job module's grouped schema declared one property,
# required eight, and forbade the rest -- so every batch answer was {"answers":[{"listing":1}]},
# thirteen tokens with no verdict. A missing verdict reads as "not a DROP", so the entire
# first Claude pass kept everything and scored nothing, silently, on every search.
from app.pipeline.claude_screen.screen import _GROUP_ITEM_SCHEMA as JOB_ITEM  # noqa: E402
from app.pipeline.thesis.claude import _GROUP_ITEM_SCHEMA as TH_ITEM  # noqa: E402
from app.pipeline.internship.claude import _GROUP_ITEM_SCHEMA as IN_ITEM  # noqa: E402

for name, schema in (('Job', JOB_ITEM), ('Thesis', TH_ITEM), ('Internship', IN_ITEM)):
    missing = [k for k in schema['required'] if k not in schema['properties']]
    check(f'{name}: every required field is also declared', not missing, missing)
    check(f'{name}:   ...and the verdict is one of them',
          'verdict' in schema['properties'] and 'verdict' in schema['required'])
    # The score left these schemas on purpose: part one decides, part two -- the résumé
    # match -- scores. Its own schema is checked the same way just below.
    check(f'{name}:   ...and no match score is asked of part one',
          'match' not in schema['properties'] and 'match' not in schema['required'])
    # additionalProperties:False is what turns a missing declaration into silence rather
    # than a loud error, so its presence is exactly what makes the check above necessary.
    check(f'{name}:   ...with additionalProperties closed',
          schema.get('additionalProperties') is False)
check('the Job group schema carries every field of the single-listing one',
      not [k for k in JC._SCREEN_OUTPUT_SCHEMA['properties'] if k not in JOB_ITEM['properties']])


section('1.33  one date choice, three actors that each want something different')
# A two-hour German search lost its entire Indeed leg because "Last 30 days" was sent --
# ordinary for Glassdoor, never valid for Indeed, and the actor's own clear complaint never
# reached the Log. There is one list of ranges now, and these are the guarantees that keep
# an impossible value from being built again.
check('every range produces a LinkedIn value the actor accepts',
      all(p.date_settings_for(l)['linkedin'] in p.LINKEDIN_DATE_OPTIONS.values()
          for l in p.DATE_RANGE_LABELS))
check('  ...an Indeed value it accepts',
      all(p.date_settings_for(l)['indeed'] in p.INDEED_DATE_OPTIONS.values()
          for l in p.DATE_RANGE_LABELS))
check('  ...and a Glassdoor value it accepts',
      all(p.date_settings_for(l)['glassdoor'] in p.GLASSDOOR_DATE_OPTIONS.values()
          for l in p.DATE_RANGE_LABELS))
# Each actor keeps its own type. Indeed's is a NUMBER IN A STRING and Glassdoor's a plain
# integer; swapping them is rejected at the API, not ignored.
sample = p.date_settings_for('Past month')
check('LinkedIn gets a keyword string', isinstance(sample['linkedin'], str))
check('Indeed gets a string', isinstance(sample['indeed'], str), repr(sample['indeed']))
check('Glassdoor gets an int',
      isinstance(sample['glassdoor'], int) and not isinstance(sample['glassdoor'], bool),
      repr(sample['glassdoor']))
# The exact value that caused the failure, and its replacement.
check('"Past month" sends Indeed its maximum of 14 days, not 30',
      p.date_settings_for('Past month')['indeed'] == '14')
check('  ...and says so, rather than searching a different period in silence',
      'Indeed' in p.date_range_note('Past month'))
check('"Any time" sends Glassdoor its maximum of 30',
      p.date_settings_for('Any time')['glassdoor'] == 30)
check('  ...and says so too', 'Glassdoor' in p.date_range_note('Any time'))
# An unknown label must fall back, never pass through to an actor.
check('an unknown range falls back to the default',
      p.date_settings_for('Last 30 days') == p.date_settings_for(p.DEFAULT_DATE_RANGE))
check('the default is one of the offered ranges',
      p.DEFAULT_DATE_RANGE in p.DATE_RANGE_LABELS)
check('every range carries all three platforms',
      not [e for e in p.DATE_RANGES
           if not all(k in e for k in ('linkedin', 'indeed', 'glassdoor', 'label', 'note'))])
# The wizard offers exactly these and nothing else.
_wizard = io.open(os.path.join(_ROOT, 'app/ui/setup_wizard.py'), encoding='utf-8').read()
check('the wizard offers one picker built from that list',
      'addItems(pipeline.DATE_RANGE_LABELS)' in _wizard)
check('  ...and no longer has three separate ones',
      'linkedin_combo' not in _wizard and 'indeed_combo' not in _wizard
      and 'glassdoor_combo' not in _wizard)


# ---------------------------------------------------------------------------------------
section('1.30  index pages that count their vacancies')
# ---------------------------------------------------------------------------------------
# Every title and address here leaked through to Claude on the real Austrian DevOps run,
# because the address heuristic claimed each one as a single posting.
for _title, _url in (
        ('158 Jobs Hainburg an der Donau', 'https://www.karriere.at/jobs/hainburg-an-der-donau'),
        ('Mehr als 1.000 Jobs Kematen an der Krems',
         'https://www.karriere.at/jobs/kematen-an-der-krems'),
        ('Your search returned 22 jobs',
         'https://www.pnet.co.za/cmp/en/moving-heads-personnel-14116/jobs'),
        ('Devops Engineer Jobs und Stellenangebote in Salzburg',
         'https://www.stepstone.at/jobs/devops-engineer/in-salzburg'),
        ('9 results for Platform Engineer jobs in Work From Home within a 30 km radius',
         'https://www.pnet.co.za/jobs/platform-engineer/in-work-from-home'),
        ('Ihre Suche ergab 30 Treffer', 'https://example.at/jobs/suche'),
        ('77 Head of Key Account Management Jobs',
         'https://www.karriere.at/jobs/head-of-key-account-management')):
    check('index page: %s' % _title[:52], p.is_listing_page({'title': _title, 'url': _url}))

# ...and the real vacancies the first two versions of the fix threw away. Each of these was
# measured being lost, and each is why a rule was reverted or narrowed.
for _title, _url, _why in (
        ('Remote AI/ML Engineer for an AI-Driven E-Commerce Platform at Toptal',
         'https://weworkremotely.com/remote-jobs/toptal-ai-ml-engineer-for-an-ai-driven-e-commerce-platform',
         '"-an-" is English here, not part of a town name'),
        ('Senior Forward Deployed AI Engineer (Remote Eligible in Germany)',
         'https://aijobs.ai/job/senior-forward-deployed-ai-engineer-remote-eligible-in-germany',
         '"-in-" likewise'),
        ('Remote Senior Full Stack at Toggl', 'https://weworkremotely.com/remote-jobs/toggl-senior-full-stack',
         'a slug naming no role word is still a posting'),
        ('Corporate Security Engineer',
         'https://superhuman.com/company/careers/jobs?ashby_jid=bc3c8fd3-470d-4a97-8602-dcafd1e72219',
         'the query string names one posting'),
        ('Customer Quality & Supply Chain Specialist',
         'https://experienced-toyota-europe.icims.com/jobs/5612/job?utm_source=indeed_integration',
         'a numeric path segment is an id'),
        ('UI/UX Designer India ~ Intern 3 Months + Full time 3 Positions',
         'https://wellfound.com/jobs/2782523-ui-ux-designer-india-intern-3-months-full-time-3-position',
         '"3 Positions" counts openings in ONE posting')):
    check('real vacancy kept (%s)' % _why, not p.is_listing_page({'title': _title, 'url': _url}),
          _url)
check('a filter parameter holding an ObjectId is not a posting id',
      p.is_listing_page({'title': '13 Fully Remote Data & Analytics Jobs in Austria Matching ...',
                         'url': 'https://meetfrank.com/?category=FULLY_REMOTE'
                                '&speciality=5995b157871fb3a5190aa2ff'}))


# ---------------------------------------------------------------------------------------
section('1.31  postings that have been taken down')
# ---------------------------------------------------------------------------------------
# Real notices from the corpus, each from a posting that was still being collected.
for _text in ('Data Scientist / AI Engineer (d/ m/ f) This job has expired Date Posted: 4 September',
              'This job is no longer available. We are looking for an experienced PL/SQL DevOps',
              'Data Scientist bei Hutchison Drei Austria GmbH ist auf karriere.at leider nicht '
              'mehr verfügbar. Einblicke',
              'Search For You LIVE Job Not Found This job listing has been removed',
              'Apply Shortlist This vacancy has expired This doesn\'t mean the journey ends here',
              'Data Engineer <br>This position is no longer available <br> Data Engineer'):
    check('gone: %s' % _text[:50], p.is_gone({'description': _text}))

# The ways an ordinary live advert says "no longer" or "not available", which must not read
# as the vacancy itself being gone -- and a notice buried deep in a long page is not the
# board's own notice either.
for _text, _why in (
        ('We are looking for a DevOps Engineer. Our legacy system is no longer supported and '
         'you will help replace it.', 'something else is no longer supported'),
        ('DevOps Engineer (m/w/d). Parkplätze sind nicht mehr frei, aber wir zahlen das Ticket.',
         'German "nicht mehr" about parking'),
        ('Platform Engineer. ' + 'Real advert text. ' * 60 + 'This job has expired',
         'the phrase appears only far past the opening')):
    check('live: %s' % _why, not p.is_gone({'description': _text}))
check('a row with no text is not called gone', not p.is_gone({'description': ''}))
_kept, _gone = p.remove_dead_postings([{'description': 'Job Not Found'},
                                       {'description': 'DevOps Engineer, fully remote.'}])
check('remove_dead_postings splits (kept, removed)', len(_kept) == 1 and len(_gone) == 1)


# ---------------------------------------------------------------------------------------
section('1.32  Markdown mirrors put back on their real address')
# ---------------------------------------------------------------------------------------
from app.pipeline.sources_norm import unmirror_markdown_row  # noqa: E402

# The collapsed shape, which is most of them.
_row = unmirror_markdown_row({
    'url': 'https://www.wearedevelopers.com/jobs/ext/2685487-data-scientist.md', 'title': None,
    'description': 'Markdown version of /jobs/ext/2685487-data-scientist. Every page supports '
                   '.md or Accept: text/markdown. Links point to the HTML versions so they work '
                   'for humans too. Agent guide: /agents.md. --- # Data Scientist - Company: '
                   'Sportradar AG - Location: Wien, Austria (Remote available) - Contract: '
                   'Permanent'})
check('the .md is taken off the address',
      _row['url'] == 'https://www.wearedevelopers.com/jobs/ext/2685487-data-scientist', _row['url'])
check('  ...the title is read out of the Markdown', _row['title'] == 'Data Scientist', _row['title'])
check('  ...and the company too', _row['company'] == 'Sportradar AG', _row['company'])

# The shape that keeps its line breaks and has no heading marker -- the first version of the
# fix read only the shape above and recovered 59 titles of 79.
_row = unmirror_markdown_row({
    'url': 'https://www.wearedevelopers.com/jobs/ext/2860552-platform-engineer.md', 'title': '',
    'description': 'Markdown version of /jobs/ext/2860552-platform-engineer. Agent guide: '
                   '/agents.md.\n\nPlatform Engineer\n\nCompany: RED\n\nLocation: Wien'})
check('the line-break shape gives its title too', _row['title'] == 'Platform Engineer',
      _row['title'])

# A mirror of a vacancy that is gone must not be given a title that makes it look live.
_row = unmirror_markdown_row({
    'url': 'https://www.wearedevelopers.com/jobs/ext/1257521-machine-learning-engineer.md',
    'title': None,
    'description': 'Markdown version of /jobs/ext/1257521. Agent guide: /agents.md. --- # Job '
                   'Not Found This job listing has been removed or is no longer available.'})
check('a gone mirror is left untitled', not _row.get('title'), _row.get('title'))
check('  ...but its address is still corrected', not _row['url'].endswith('.md'))

_before = {'url': 'https://www.karriere.at/jobs/10028125', 'title': 'T', 'company': 'C',
           'description': 'd'}
check('an ordinary row is not touched', unmirror_markdown_row(dict(_before)) == _before)
_row = unmirror_markdown_row({'url': 'https://x.com/jobs/1.md', 'title': 'Kept Title',
                              'company': 'Kept Co',
                              'description': 'Agent guide: /agents.md. --- # Other - Company: '
                                             'Other Co - Location: X'})
check('a title the row already has is never overwritten',
      _row['title'] == 'Kept Title' and _row['company'] == 'Kept Co', _row)


section('1.33  what the Oslo run exposed')

# Every one of these is a real row from the Data Engineer / Entry / Remote search over Oslo,
# 1,018 listings. See Test-Campaign-Bugs.md, N.
from app.pipeline.sources_norm import strip_site_name_from_title  # noqa: E402
from app.pipeline.sources_norm import normalize_glassdoor  # noqa: E402

# N-1 · Glassdoor returns `location` as an object, and the whole structure was being stored.
_g = normalize_glassdoor({'jobTitle': 'Data Engineer', 'companyName': 'Kahoot!',
                          'location': {'countryId': 180, 'id': 2918317, 'name': 'Oslo',
                                       'type': 'C'},
                          'link': 'https://www.glassdoor.com/job-listing/j?jl=1',
                          'descriptionText': 'text'})
check('a Glassdoor location object becomes the city', _g['location'] == 'Oslo', _g['location'])
check('  ...a plain string is left as it is',
      normalize_glassdoor({'location': 'Oslo, Norway'})['location'] == 'Oslo, Norway')
check('  ...and a missing one is None',
      normalize_glassdoor({'jobTitle': 'x'})['location'] is None)

# N-2 · A page title ends with the site's own name: 456 of 1,018 rows carried one.
for _title, _url, _want, _why in [
        ('Data Engineer | FINN.no', 'https://www.finn.no/job/ad/1', 'Data Engineer',
         'the board at the end'),
        ('AI Data Engineer at The Agency Fund - Remote | Wellfound',
         'https://wellfound.com/jobs/4656683',
         'AI Data Engineer at The Agency Fund - Remote', 'a bullet-separated title'),
        ('Data Engineer | Jobs | Wellfound', 'https://wellfound.com/jobs/1', 'Data Engineer',
         'the board and its own word for jobs'),
        ('The Hub | Internship Data Engineer | SurplusMap', 'https://thehub.io/jobs/1',
         'Internship Data Engineer | SurplusMap', 'the board at the front'),
        ('Data Engineer - Oslo | arbeidsplassen.no',
         'https://arbeidsplassen.nav.no/stillinger/stilling/x', 'Data Engineer - Oslo',
         'a name that is not quite the host'),
        ('Senior Data Engineer - Microsoft Fabric', 'https://careers.acme.com/1',
         'Senior Data Engineer - Microsoft Fabric', 'the employer keeps its own dash'),
        ('Data Engineer - Jobs', 'https://careers.acme.com/1', 'Data Engineer - Jobs',
         'a generic word alone is never stripped'),
        ('FINN.no', 'https://www.finn.no/job/ad/1', 'FINN.no',
         'a title that is only the site name'),
        ('Data Engineer', 'https://www.finn.no/job/ad/1', 'Data Engineer', 'nothing to strip')]:
    check('title: %s' % _why, strip_site_name_from_title(_title, _url) == _want,
          strip_site_name_from_title(_title, _url))
check('a row with no URL is left alone',
      strip_site_name_from_title('Data Engineer | FINN.no', '') == 'Data Engineer | FINN.no')

# N-4 · A page that answers with the board's own list of other vacancies.
#
# Sina read one of the two survivors and said so plainly: "اینکه فقط لیسته". Opening the
# address settles it -- every old aijobs.net /job/… URL now redirects to foorilla.com/hiring/,
# a general list. The vacancy is gone; the page just never says the word.
from app.pipeline.pages import is_board_index_text  # noqa: E402
from app.pipeline.enrich import looks_like_chrome_only  # noqa: E402

_INDEX_TEXT = ('all Hiring [SE] USD 180K-220K Remote · GST hours [R] [MI] USD 212K Laurel, '
               'Maryland [SE] USD 308K Columbia, Maryland [SE][Full Time] PLN 242K-354K '
               'Kraków [EN][Full Time] PHP 960K-1080K Manila [SE][Full Time] INR 1632K-2600K '
               'Bangalore [EN][Internship] Lisbon [MI][Full Time] USD 115K-235K New York '
               '[SE][Full Time] JPY 8600K JP-Tokyo [Full Time] SGD 74K-108K Singapore ' * 3)
_REAL_POSTING = ('We are looking for a Data Engineer to join our team in Oslo. You will build '
                 'and maintain data pipelines in Python and SQL, work with our analysts, and '
                 'help shape the platform. We offer a competitive salary, and the role can be '
                 'done fully remote. Requirements: 1-2 years of experience, good English.')
check('a board index of other vacancies is recognised', is_board_index_text(_INDEX_TEXT))
check('  ...and so is its own summary line',
      is_board_index_text('16,006 new jobs found (60d) Export as CSV · JSON'))
check('  ...a real posting is not', not is_board_index_text(_REAL_POSTING))
check('  ...nor is an empty description', not is_board_index_text(''))
check('a long index page is no longer excused for being long',
      looks_like_chrome_only(_INDEX_TEXT) is True)
check('  ...while a long real posting still is excused',
      looks_like_chrome_only(_REAL_POSTING * 20) is False)
check('such a page counts as a vacancy that is gone',
      p.is_gone({'description': _INDEX_TEXT, 'url': 'https://aijobs.net/job/x-260582/'}))
check('  ...while a real posting is not gone',
      not p.is_gone({'description': _REAL_POSTING, 'url': 'https://x/1'}))
# End to end: the Filter removes it rather than showing Sina a list.
_index_row = {'title': 'Data Engineer - Oslo, Norway', 'company': '', 'country': 'Norway',
              'url': 'https://aijobs.net/job/data-engineer-oslo-norway-260582/',
              'description': _INDEX_TEXT}
_kept_index = p.reapply_filters([dict(_index_row)], progress_cb=None, anthropic_api_key=None,
                                search_title='Data Engineer', search_level='entry')[0]
check('the Filter removes a page that is only the board\'s list', not _kept_index, _kept_index)
# And the enrichment step never lets such a page REPLACE a description it already has.
check('a board index never overwrites a real description',
      p.enrich.looks_like_chrome_only(_INDEX_TEXT) is True)

# N-5 · The same job from two boards, one of which put the employer in the title.
check('a short tail after a pipe is the employer, not the job',
      p.dedup_title_key('Internship Data Engineer | SurplusMap')
      == p.dedup_title_key('Internship Data Engineer'),
      (p.dedup_title_key('Internship Data Engineer | SurplusMap'),
       p.dedup_title_key('Internship Data Engineer')))
check('  ...and a long one is the job itself',
      p.dedup_title_key('Data Engineer | Build the data foundation for the future of care')
      != p.dedup_title_key('Data Engineer'))
_same_job = [
    {'title': 'Internship Data Engineer', 'company': '', 'country': 'Norway',
     'url': 'https://www.finn.no/job/ad/476486230',
     'description': 'We are looking for an intern to build data pipelines in Python and '
                    'SQL on Google Cloud. Remote position. ' * 8},
    {'title': 'Internship Data Engineer | SurplusMap', 'company': 'SurplusMap',
     'country': 'Norway', 'url': 'https://thehub.io/jobs/67086b0ef14032ef0ac58b6e',
     'description': 'We are looking for an intern to build data pipelines in Python and '
                    'SQL on Google Cloud. Remote position. ' * 8},
]
_merged, _removed_count = p._remove_duplicates_list([dict(r) for r in _same_job])
check('one job published on two boards comes back once', len(_merged) == 1,
      [r['url'] for r in _merged])
# Two different jobs at the same employer must still be two jobs.
_two_jobs = [
    dict(_same_job[1], title='Data Engineer | SurplusMap', url='https://thehub.io/jobs/a',
         description='Build our data platform in Python, SQL and dbt. ' * 10),
    dict(_same_job[1], title='Senior Full Stack Engineer GIS / AI | SurplusMap',
         url='https://thehub.io/jobs/b',
         description='Lead our front end in TypeScript and React, with GIS work. ' * 10),
]
check('  ...but two different jobs at one employer stay two',
      len(p._remove_duplicates_list([dict(r) for r in _two_jobs])[0]) == 2)

# N-3 · "Lead Data Engineer" was the right level for nobody and was kept by everybody.
from app.pipeline.profiles import job_profile as _profile_for  # noqa: E402
for _title, _lead in (('Lead Data Engineer', True), ('Staff Data Engineer', True),
                      ('Tech Lead - Data', True), ('Data Engineer', False),
                      ('Data Engineer, Leading Bank', False),
                      ('Data Engineer at a staffing agency', False)):
    for _level in ('entry', 'mid', 'senior'):
        check('%s: %r is %s' % (_level, _title, 'the wrong level' if _lead else 'kept'),
              _profile_for(_level).is_wrong_level({'title': _title, 'description': ''}) is _lead)
# Junior is untouched, as Sina asked -- its prompt's rule 4 catches these at Claude's stage.
check('Junior is left exactly as it was',
      _profile_for('junior').is_wrong_level({'title': 'Lead Data Engineer',
                                             'description': ''}) is False)


# N-8 · A page that counts vacancies in a language the rule did not know.
for _title, _is_list, _why in [
        ('31 data scientist vacatures in Amsterdam', True, 'Dutch, words between'),
        ('68 wo data scientist vacatures bekijken | 18 september 2026', True, 'Dutch again'),
        ('11 Bürokaufmann Jobs Waidhofen an der Ybbs', True, 'German, words between'),
        ('134 Treffer für Data Engineer Jobs in Frankfurt Am Main', True, 'German hits'),
        ('158 Jobs Hainburg an der Donau', True, 'the shape that started it'),
        ('Ihre Suche ergab 10 Treffer', True, "a company's own list"),
        ('Data Scientist (m/w/d)', False, 'a real advert'),
        ('UI/UX Designer India ~ Intern 3 Months + Full time 3 Positions', False,
         'a number that counts THIS posting\'s openings'),
        ('440 Senior Data Scientist', False, 'a reference number in front of a real title'),
        ('Data Engineer - 2 days per week', False, 'a number about the work')]:
    check('counts vacancies (%s): %r' % (_why, _title[:44]),
          bool(p.pages._COUNTS_VACANCIES.search(_title)) is _is_list)

section('1.34  reading a page from several threads does not kill the process')

# The Amsterdam run died 56 minutes in with no Python error of any kind. Windows recorded
# what Python could not: Faulting module etree.cp38-win_amd64.pyd (lxml), exception
# 0xc0000005. trafilatura parses with lxml, whose C parser is not safe to drive from several
# threads at once -- and enrichment runs it in an 8-thread pool.
#
# This test is unusual and deliberately so: if the lock is ever removed, it does not fail,
# it takes the whole suite down with it. That is exactly what the fault does in production,
# and a green suite next to a dead process is the thing to avoid.
import concurrent.futures as _futures  # noqa: E402

from app.pipeline import enrich as _enrich  # noqa: E402

check('the extractor is serialised behind a lock', hasattr(_enrich, '_EXTRACT_LOCK'))
_PAGE = ('<html><head><title>Data Engineer</title></head><body><nav>Home Jobs About</nav>'
         '<article><p>' + ('We are looking for a Data Engineer in Amsterdam. You will build '
                           'and maintain data pipelines in Python and SQL, and the role is '
                           'fully remote. ' * 40) + '</p></article></body></html>')
with _futures.ThreadPoolExecutor(max_workers=8) as _pool:
    _lengths = list(_pool.map(lambda _n: len(_enrich.readable_text(_PAGE)), range(48)))
check('48 pages read on 8 threads at once', len(_lengths) == 48)
check('  ...and every one of them read the same page the same way',
      len(set(_lengths)) == 1 and _lengths[0] > 200, sorted(set(_lengths))[:4])


section('1.35  a range of years is not always a range of experience (M-7)')

# Measured over all five real corpora before the rule was touched: 272 ranges matched, 208 of
# them beside an experience word, 5 beside an age word, and not one experience range anywhere
# starting at 12 or more. The 5 were the same graduate programme -- "highly motivated
# graduates aged 18 to 28 years" -- dropped as too senior, which is the opposite of what it is.
for _text, _want, _why in [
    ('We are looking for highly motivated graduates aged 18 to 28 years, who want to start '
     'their career abroad.', False, 'an age range on a graduate programme'),
    ('Open to candidates between the ages of 21 to 30 years.', False, 'ages spelled out'),
    ('Wir suchen Absolventen im Alter von 18 bis 28 Jahren.', False, 'German, by Alter'),
    ('Kandidaten met een leeftijd van 18 tot 28 jaar.', False, 'Dutch, by leeftijd'),
    ('You bring 3-5 years of experience in data engineering.', True, 'a real experience range'),
    ('Minimum of 4-6 years in a GTM Operations role.', True, 'a range with no word for it'),
    ('We want someone with 10-15 years of experience.', True, 'a long experience range'),
    ('Our platform will shape the next 20-25 years of the industry.', False,
     'a 12+ range with nothing calling it experience'),
    ('We need 12-15 years of experience leading teams.', True,
     '  ...and the same range when it is called experience'),
]:
    check('%s: %s' % (_why, 'drop' if _want else 'keep'),
          p.is_too_senior(job(description=_text)) is _want, _text[:70])

# The age guard must not swallow a real demand that merely mentions age somewhere far away.
check('an age word in a different paragraph does not rescue a senior posting',
      p.is_too_senior(job(description=(
          'We welcome applicants of any age. ' + 'Filler sentence. ' * 12
          + 'You bring 6-8 years of professional experience.'))) is True)


# ----------------------------------------------------------------------- 1.editorial ----
# A board writing ABOUT work instead of offering any. The third kind of non-vacancy, and the
# one nothing looked for: the index-page rules need a page OF vacancies to fire on, and these
# are single pages on a single topic whose addresses look exactly like a posting's.
#
# Sina found them in the nine listings Claude had marked "apply" on the Germany run.
from app.pipeline.pages import is_editorial_page as _editorial  # noqa: E402


def _is_article(url, title=''):
    return _editorial({'url': url, 'title': title})


# The three he found, and the families they belong to.
for _url, _title in (
        ('https://www.kellerwest.com/career-advice/how-to-become-a-data-scientist-in-germany/',
         'How to become a Data Scientist in Germany'),
        ('https://www.hays.de/en/job-profiles/data-scientist',
         'Data Scientist (m/f/d): Salary, tasks & jobs'),
        ('https://www.helmholtz-hida.de/en/discover-hida/helmholtz-information-data-science/',
         'The Helmholtz Information & Data Science Framework'),
        ('https://www.arbeitnow.com/blog/sick-leave-in-germany', 'Sick leave in Germany'),
        ('https://berlinstartupjobs.com/guide-working-in-berlin/german-wage-tax-calculator/',
         'Wage Tax & Contributions for Employees'),
        ('https://weworkremotely.com/remote-work-hiring-guide', "WWR's Guide to Hiring Remote"),
        ('https://jobinamsterdam.com/blog/job-sector/be-or-become-a-engineering-employee',
         'Be or Become a "Engineering" employee')):
    check('an article, not a vacancy: %s' % _title[:44], _is_article(_url, _title) is True)

# The guard, and it is not optional. Without it the first draft took four real postings, and
# they were the best kind in the corpus -- an employer's own site with no agency in between --
# because German employers file openings under "Über uns / Karriere".
for _url, _title in (
        ('https://www.wwf.de/ueber-uns/stellenangebote/stellenangebot/stelle/data-integration',
         'Data Integration & BI Specialist (m/w/d)'),
        ('https://www.s-kreditpartner.de/ueber-uns/karriere/stellenangebote/werkstudent-data',
         'Werkstudent Data Science'),
        ('https://lzpd.polizei.nrw/artikel/ml-data-scientist-wmd', 'ML Data Scientist (w/m/d)'),
        ('https://www.idg-rlp.de/ueber-uns/karriere', 'Öffentlichkeitsarbeit'),
        ('https://de.linkedin.com/jobs/view/data-scientist-python-remote-at-hire-feed-4467091',
         'Data Scientist - Python (Remote)'),
        ('https://www.stepstone.de/stellenangebote--Data-Scientist-all-gender-Bremen--1433706',
         'Data Scientist (all gender)')):
    check('a real vacancy survives it: %s' % _title[:44], _is_article(_url, _title) is False)

# The specific miss that a looser guard caused: "/job-profiles/" is not the word "job".
check('"/job-profiles/" is a reference page, not a job page',
      _is_article('https://www.hays.de/en/job-profiles/data-scientist') is True)
check('  ...while "/jobs/" really is a job page',
      _is_article('https://example.invalid/blog/jobs/data-scientist-12345') is False)


# ----------------------------------------------------------------------- 1.hybrid ----
# Sina found two listings in a Remote search that plainly say the role is hybrid:
#
#   glassdoor.it/...1010241469625   "BERLIN, DUESSELDORF, HAMBURG, KOELN, HYBRID, MUENCHEN
#                                    ... Hybrides Arbeiten: Ein individueller Mix aus remote
#                                    working, Zeit im Office oder beim Kunden vor Ort"
#   wellfound.com/jobs/3240715      "Location: Hybrid in Chelsea District, NY OR Century City"
#
# Both survived because the word "remote" appears inside the very sentence saying the role is
# hybrid, and rule 2 only drops an on-site term when NO remote term appears anywhere.
#
# That softening is right and must stay: of 2,848 real listings, 562 were being dropped purely
# because "hybrid" sat in the board's own filter menu. So the question this rule asks is not
# "is the word there" but "does the posting COMMIT to office time".
#
# Measured on the Bank before it shipped: 484 of the 4,093 listings that pass the Remote rule,
# 11.8%, with a random sample read by eye -- which is how the two pattern faults below were
# found.
_asks = p.rules.says_office_attendance_is_required

# A commitment to office time. Every one of these is from a real listing in the Bank.
for _probe in (
        'Hybrides Arbeiten: Ein individueller Mix aus remote working, Zeit im Office oder '
        'beim Kunden vor Ort',
        'Location: Hybrid in Chelsea District, NY OR Century City, Los Angeles',
        'Our hybrid model, with 2 recommended office days a week, gives you flexibility',
        'Home Office Policy: 3 days in the office / 2 days remote',
        'Hybrides 3:2 Arbeitsmodell | 3 Tage vor Ort - 2 Tage Homeoffice',
        'Work 40% at the office, 40% from home, and 20% flexibly',
        'Bij KPMG werken we hybride, dus een combinatie van zowel thuis als op kantoor',
        'Wir arbeiten flexibel, hybrid, mobil und vor Ort',
        'Remote/Hybrid/On-Site Policy: 100 % on-site (rare ad-hoc remote only)',
        'colleagues are expected to be in their local office at least three days per week',
        # A share of the week is a commitment even with no "hybrid" word anywhere near it.
        # This probe came verbatim from a real listing and was caught by none of the first
        # three patterns -- the test was right and the patterns were one short.
        'Work 40%% at the office, 40%% from home, and 20%% flexibly',
        'ongeveer 50%% aanwezigheid op kantoor gevraagd',
        'hybride werken: gemiddeld 60%% vanuit huis en 40%% op kantoor',
        # A small number of days AT HOME says what the other days are, and these two moved
        # here from the list of traps below. The reasoning that put them there was that "home
        # office" means working FROM home -- true of the words, but "up to 2 days of home
        # office per week" is three days in an office, and Sina searching Remote does not want
        # it. Every pattern before this read stated OFFICE days; adverts say it the other way
        # round just as often, and 96 Bank listings were passing on that phrasing alone --
        # including the Glovo advert Sina reported.
        'Choose a flexible working model with up to 2 days of home office per week',
        'Bis zu 3 Tage Homeoffice pro Woche moeglich',
        'Hybride werken met minimaal 2 dagen per week thuiswerken',
        'This position may be eligible for remote work for up to 2 days per week',
        # And the perk that let Glovo through: a few weeks a year from anywhere is not remote
        # work, but it fired the fully-remote escape hatch and skipped every check.
        "We have an ''office-first'' culture. The freedom to work from home two days a week, "
        'and the opportunity to work from anywhere for up to three weeks a year!',
        'We are an office-first company and value in-person collaboration',
        # A stated share of the week spent AWAY from the office says what the rest of it is,
        # and the patterns above only read the share spent AT one. Sina reported HDI's "Data
        # Scientist: Advanced Analytics & AI Engineer" arriving as Full Remote on exactly this,
        # with Hanover and Cologne in the advert:
        'Mobile working: our mobile working model (up to 60%% mobile) offers you freedom',
        'Flexible Arbeitszeiten und 20%% mobiles Arbeiten',
        'Die Moeglichkeit des anteiligen mobilen Arbeitens (bis zu 50 %%)',
        'Hybrid working model with up to 40%% remote per week',
        'You may work 80%% home office and 20%% on site',
        # Every stated share below 100 is an office commitment, and that is Sina's call after
        # I argued for sparing the high ones: "آقا Remote باشه دیگه / یعنی چی 70 درصد". The 5%%
        # of a "95%% remote" job is spent at an address -- Hanover, in the advert he reported.
        'A hybrid role with 70%% Remote working',
        'Forward Deployed Engineer, 80%% Remote',
        'Die Taetigkeit ist zu etwa 95 %% remote moeglich, gelegentlich Workshops',
        'This job is 99%% remote with one office day a month'):
    check('office time is required: %s' % _probe[:48], _asks(_probe) is True)
# The escape hatch must still open for a listing that really is remote, however many
# workation perks it lists first.
check('a 100%% remote job with a workation perk is still remote',
      _asks('We are 100%% remote. You may also work from anywhere abroad for up to four '
            'weeks a year.') is False)

# And the traps. Each of these is a real shape from the corpus that must NOT fire -- three of
# them were found firing by the measurement and are why the guards exist.
for _label, _probe in (
        # F-2 in another language: hybrid CLOUD, not a hybrid desk.
        ('hybrid architecture',
         'Du entwickelst Datenfluesse, zunehmend auch in hybriden Architekturen '
         '(On-Premise und Cloud) im Office.'),
        # The board's own control panel, which is what the 562 were.
        ("a board's filter menu",
         'Employment type: Full-time Hybrid Visit employer website Save job Create alert'),
        # A remote option is offered outright, so the hybrid one is not the only one.
        ('hybrid OR fully remote',
         'Standort in Dresden (hybrid) oder remote deutschlandweit in Vollzeit.'),
        ('100%% remote, hybrid teams',
         'This role is 100%% remote, work from anywhere in Europe; hybrid teams welcome.'),
        # The lookbehind that stops the word "office" inside "home office" being read as an
        # office requirement is still there and still needed -- these probes prove the
        # MECHANISM without claiming the listing is remote. A stated number of home days is
        # now judged on its meaning, a few lines above.
        ('home office with no number of days at all',
         'We offer a home office allowance and flexible hours'),
        ('Homeoffice as a benefit, with no rota',
         'Homeoffice und flexible Arbeitszeiten sind bei uns selbstverstaendlich'),
        ('four days at home, which is a remote job with a desk',
         'You may work from home four days a week if you prefer'),
        # Only 100 survives, and the guards for it are load-bearing: this pattern's whole
        # job is to read a share below 100 as an office commitment, so reading 100 that way
        # would invert the rule it belongs to. "10" must not be read out of "100" either.
        ('100%% remote, said with a percentage', 'This role is 100%% remote'),
        ('100%% mobil, in German', 'Bis zu 100 %% mobiles Arbeiten'),
        ('100%% home office', 'We offer 100%% home office for this position'),
        ('100%% of a target bonus',
         'Salary up to 100%% of target; remote work allowance included'),
        # "vor 1 Tag" is how old a NEIGHBOURING job card is. Four of the first sample's
        # catches were a German board's sidebar being read as an office rota.
        ('a neighbouring job card',
         'Mercedes-Benz AG Duesseldorf Teilweise Home-Office vor 1 Tag Duales Studium'),
        ('an English job card',
         'Acme GmbH Berlin Hybrid office 2 days ago Senior Data Scientist'),
        # 100 is deliberately outside the percentage pattern's range: in real postings it
        # is almost always "100%% remote" or "100%% of target bonus", never an office share.
        ('100%% of a bonus', 'Salary up to 100%% of target; the office has a gym'),
        ('a subsidised commute', 'We offer a 100%% subsidised ticket for the office commute'),
        ('says nothing at all', 'We are looking for a data scientist. Python, SQL, ML.'),
        ('empty', '')):
    check('stays quiet: %s' % _label, _asks(_probe) is False, _probe[:60])

# Through the real rule, in both work modes, because the check sits inside it.
_WM2 = p.search_title.WORK_MODE_ROW_KEY
_hybrid_row = {'title': 'Data Scientist', 'country': 'Germany',
               'description': 'Hybrides Arbeiten: Ein individueller Mix aus remote working, '
                              'Zeit im Office oder beim Kunden vor Ort.'}
check('a hybrid role does not survive a Remote search',
      p.rules.passes_work_location_rule(dict(_hybrid_row, **{_WM2: 'remote'})) is False)
check('  ...and a real remote role still does',
      p.rules.passes_work_location_rule(
          dict(_hybrid_row, description='Fully remote, work from anywhere in Europe.',
               **{_WM2: 'remote'})) is True)
check('  ...and a Not Remote search is unaffected by this rule',
      p.rules.passes_work_location_rule(dict(_hybrid_row, **{_WM2: 'not_remote'})) is True)

# A source that returned no text has not been silent -- it had nothing to say. This rule must
# never be what drops those four sources.
check('a thin-description row is not caught by it',
      p.rules.passes_work_location_rule(
          {'title': 'Data Scientist', 'description': 'Hybrid Berlin', 'thin_description': True,
           _WM2: 'remote'}) is True)


# ------------------------------------------------------------------------ 1.language ----
# The rule reads the posting in its own language now. It used to run after every listing had
# been translated to English, and when translation was removed to stop paying DeepL this rule
# was the one left with English-only vocabulary -- and a docstring still promising translated
# text. Measured on the 5,442 real German listings: of the 1,778 that state a German
# requirement in German it caught 13.
#
# Sina found it from the other end. Two REPLY listings reached him asking for
# "Kommunikationsstärke in Deutsch und Englisch", and he asked why the language filter had
# not removed them.
#
# ON 4 OCTOBER HE REVERSED THAT, AND THAT EXACT PHRASE IS NOW A KEEP.
#
# "اگر به صورت ترکیبی میگفت انگلیسی و یه زبان دیگه باید این رو هم قبول بکنه" -- a posting
# that wants English alongside German has offered him a language he reads, and he would
# rather see it and judge the German himself than have it deleted on his behalf. Nine of the
# sixteen probes below named English and have moved to the keep side; the seven that name
# only a language he lacks are the whole of what this rule still deletes.
from app.pipeline.language import requires_language_besides_english as _lang  # noqa: E402


def _wants_another_language(text):
    return _lang({'title': 'Data Scientist', 'description': text})


# A wall: a language he lacks, stated the way a posting in that language really states it,
# with English nowhere beside it.
for _probe in (
        'Sehr gute Deutschkenntnisse in Wort und Schrift',
        'Verhandlungssichere Deutschkenntnisse',
        'Deutschkenntnisse auf Niveau C1',
        'Uitstekende beheersing van de Nederlandse taal',
        'Se requiere español nativo',
        'Flydende dansk i skrift og tale',
        'Gode norskkunnskaper er et krav'):
    check('a wall: %s' % _probe[:52], _wants_another_language(_probe) is True)

# THE PAIRING, IN EVERY LANGUAGE IT WAS CAUGHT IN. All nine asserted True until 4 October.
# Each one is a real posting's phrasing, and each one now reaches Sina.
for _probe in (
        'Fließende Deutsch- und Englischkenntnisse',
        'Gute Deutsch- und Englischkenntnisse',
        'Kommunikationsstärke in Deutsch und Englisch',
        'Auf Deutsch und Englisch kommunizierst du gut und gerne',
        'Deutsch (C1) und Englisch sehr gut in Wort und Schrift',
        'Goede kennis van Nederlands en Engels',
        "Maîtrise du français et de l'anglais",
        'Flytande svenska och engelska',
        'Fluent German and English required'):
    check('the pairing is a keep: %s' % _probe[:52],
          _wants_another_language(_probe) is False)

# ------------------------------------- the country vocabulary, the OTHER language rule ----
# THE SECOND PLACE THIS QUESTION IS ANSWERED, AND IT NEARLY MISSED T-12.
#
# country_rules['other_language_required'] is a flat phrase list per country -- 'fluent
# dutch', 'deutschkenntnisse', 'vloeiend nederlands' -- read by _step_country_rules. It is
# not redundant with the regex rule above: it catches shapes that have no level word for the
# regexes to find ('german required', 'deutsch zwingend', 'nederlands vereist').
#
# It also had no idea English existed. When the pairing became a KEEP the regex rule stopped
# deleting it and THIS list went on deleting it, because "Fluent Dutch and English required"
# contains 'fluent dutch' and nothing looked at the rest of the sentence. Found by measuring
# the real run: 385 listings stopped being deleted by the regex rule and only 10 pairings
# survived to the end. country_language_rule_hit is the same list with the same cancel.


def _country_lang(text):
    return p.country_language_rule_hit(
        {'title': 'Data Scientist', 'description': text, 'country': 'Netherlands'}, None)


for _label, _text, _want in (
    ('the shape that exposed it', 'Fluent Dutch and English required.', False),
    ('  ...and the same words without English', 'Fluent Dutch required.', True),
    ('a phrase the regexes have no level word for', 'Nederlands vereist voor deze functie.',
     True),
    ('  ...paired, so kept', 'Nederlands vereist, Engels voor het team.', False),
    ('German, bare', 'German required for this position.', True),
    ('German, paired', 'German required alongside English for this position.', False),
    # Walked rather than first-hit-only: a posting can name two languages and pair English
    # with only one of them, and the unpaired one is still a wall. Both phrases have to come
    # from the SAME loaded list for this to test the walk -- _country_pattern loads the
    # Dutch-language list only for a posting detected as Dutch, which this one is not.
    ('two demands, only one paired',
     'Fluent Dutch and English for the team. ' + 'x' * 400 + ' German required.', True),
):
    check('country list: %s' % _label, bool(_country_lang(_text)) is _want,
          repr(_country_lang(_text)))

# And the two rules must never disagree on the direction: if the country list deletes, the
# posting is not something the English column would call a pairing.
check('the country list and the English column agree on the shape that exposed it',
      p.english_requirement_of(
          {'title': 'Data Scientist',
           'description': 'Fluent Dutch and English required.'}) == 'English + Other'
      and not _country_lang('Fluent Dutch and English required.'))

# Not a wall. Every one of these was either already guarded or found by reading a random
# thirty of the 2,934 listings the rule removed when it still deleted the pairing.
for _probe in (
        'Fluent English required',
        'We offer German and English language courses free of charge',
        'Clear communication in English (German is a HUGE plus)',
        'Deutschkenntnisse von Vorteil',
        'Nederlands is een pré',
        'C1+ level in either English or Spanish',
        'Professional working proficiency in English or Russian',
        'if the documents are not in German or English',
        # The softener inside the phrase, which the after-the-match check cannot see.
        'Du sprichst fließend Englisch und idealerweise Deutsch',
        'excellent communication skills in English; proficiency in Dutch, '
        'or the willingness to learn',
        'Deutschkenntnisse oder die Bereitschaft, Deutsch zu lernen'):
    check('not a wall: %s' % _probe[:52], _wants_another_language(_probe) is False)

# Italian is deliberately absent from the vocabulary: the owner has only basic Italian and lives in
# Italy, so treating it as a language he lacks deletes the listings closest to him. Adding it while
# extending the list for the other languages was a real regression, caught by this probe.
for _probe in ('Ottima conoscenza della lingua italiana',
               'Madrelingua italiana richiesta',
               'Italiano e inglese fluente',
               'Italian at A2 level is sufficient'):
    check('Italian is never a wall: %s' % _probe[:44],
          _wants_another_language(_probe) is False)

# "Deutschland" is the country, not the language, and it is in almost every German posting.
check('the country name alone is not a language demand',
     _wants_another_language('Wir sind deutschlandweit tätig. Deutschlandticket inklusive.')
     is False)


# ---------------------------------------------------------------------------- 1.geo ----
# The two city tables have to stay in step. geo.CITIES is what the wizard builds Sina's
# checkboxes from; geo.CITY_COUNTRY is what the Not Remote country rule reads to learn which
# country a chosen city belongs to. Today they hold the same seven cities, so a city the app
# offers but the rule does not know cannot be chosen -- and that is only true for as long as
# whoever adds the eighth city remembers to add it twice.
#
# This existed as a caveat in the campaign notes until Sina asked the obvious question: he can
# only tick boxes the app offers, so how would an unknown city ever be selected? It cannot.
# A written warning was the wrong answer to that; this is the right one.
from app.pipeline.geo import CITIES, CITY_COUNTRY, COUNTRY_CITIES  # noqa: E402

_unknown = [c for c in CITIES if c not in CITY_COUNTRY]
check('every city the wizard offers is one the country rule knows', not _unknown, _unknown)
_unoffered = [c for c in CITY_COUNTRY if c not in CITIES]
check('  ...and the rule knows no city the wizard cannot offer', not _unoffered, _unoffered)
_nested = [c for cities in COUNTRY_CITIES.values() for c in cities]
check('  ...and the nested per-country lists hold exactly the same set',
      sorted(_nested) == sorted(CITIES), (sorted(_nested), sorted(CITIES)))
check('  ...each filed under the country the rule would return for it',
      all(CITY_COUNTRY[city] == country
          for country, cities in COUNTRY_CITIES.items() for city in cities))


# ---------------------------------------------------------------------------------------
section('1.x  no city is exempt from the Work Location rule')
# ---------------------------------------------------------------------------------------
# The Milan / Turin exemption (and the whole-word test it needed after it waved 386 listings
# past the Remote rule on "manufacturing") is gone. Sina: "اگر نوشتم Remote دیگه بره کلا دنبال
# Remote حتی اگر Turin یا Milan بود". What is left to assert is the consequence.
import app.pipeline.rules as _rules_mod  # noqa: E402
check('the exemption and its helper no longer exist',
      not hasattr(_rules_mod, 'mentions_milan_or_turin') and not hasattr(_rules_mod, 'MILAN_TURIN_NAMES'))

# And the consequence, through the rule that reads it: a Dutch office job that happens to
# say "sturing" must now be judged on its working arrangement like any other.
from app.pipeline.rules import passes_work_location_rule             # noqa: E402

_dutch_office = {'title': 'Data Engineer',
                 'description': 'Je zorgt voor de kpi-sturing en dataproducten. '
                                'Werklocatie: Utrecht, hybride werken.',
                 'country': 'Netherlands'}
check('a Dutch office job saying "sturing" is no longer exempt from the Remote rule',
      not passes_work_location_rule(dict(_dutch_office)), _dutch_office['description'][:60])
_turin_office = {'title': 'Data Engineer',
                 'description': 'Sede: Torino. Lavoro in sede, non remoto.',
                 'country': 'Italy'}
check('  ...while a Turin office job is still kept, arrangement unasked',
      passes_work_location_rule(dict(_turin_office)), _turin_office['description'])



# ======================================================= 1.wp  LinkedIn's workplace tag ======
section('1.wp  the workplace tag, and the four adverts that were kept as Remote')
# THREE ADVERTS IN A ROW THAT SINA OPENED WERE TAGGED HYBRID ON LINKEDIN AND HAD BEEN KEPT.
# "به جرات میتونم بگم 99 درصد کارهایی که آوردی Hybrid هست / این یه شکست بسیار بزرگه".
# Each is reproduced here from the advert he pasted, with the exact words that let it through,
# because a rule fixed against a paraphrase is a rule fixed against nothing.
from app.pipeline.sources_norm import clean_workplace, normalize_linkedin_pro  # noqa: E402
from app.pipeline.search_title import WORK_MODE_ROW_KEY as _WMK  # noqa: E402


def _wp(**fields):
    row = {'title': 'Data Analyst', 'country': 'Netherlands', 'location': 'Amsterdam',
           'platform': 'linkedin', _WMK: 'remote'}
    row.update(fields)
    return row


# --- the tag itself, spelled however it arrives ---
for _raw, _want in (('Remote', 'Remote'), ('remote', 'Remote'), ('Hybrid', 'Hybrid'),
                    ('On-site', 'On-site'), ('onsite', 'On-site'), ('On site', 'On-site'),
                    ('on_site', 'On-site'), ('', ''), (None, ''), ('Flexible', ''),
                    (True, ''), (float('nan'), '')):
    check('clean_workplace(%r) -> %r' % (_raw, _want), clean_workplace(_raw) == _want)

# --- the tag decides, ahead of every word in the advert ---
_SAYS_REMOTE = 'Working Model: Remote. Location: Netherlands. Strong SQL skills required.'
check('IDPP: the text says Remote and the tag says Hybrid -- the tag wins',
      p.passes_work_location_rule(_wp(description=_SAYS_REMOTE, workplace_type='Hybrid'))
      is False)
check('  ...the same text with no tag is kept, which is why no rule on wording could catch it',
      p.passes_work_location_rule(_wp(description=_SAYS_REMOTE)) is True)
check('  ...an On-site tag drops it too',
      p.passes_work_location_rule(_wp(description=_SAYS_REMOTE, workplace_type='On-site'))
      is False)
check('a Remote tag keeps an advert that never uses the word',
      p.passes_work_location_rule(_wp(description='We build models. Join our team.',
                                      workplace_type='Remote')) is True)
check('  ...and one whose location line would have counted against it',
      p.passes_work_location_rule(_wp(description='Our company is located in Amsterdam. '
                                                  'Build models with us.',
                                      workplace_type='Remote')) is True)
check('  ...but an advert tagged Remote that states office days is contradicting its tag',
      p.passes_work_location_rule(_wp(description='You work two days a week in the office.',
                                      workplace_type='Remote')) is False)
check('  ...and so is one that denies remote work outright',
      p.passes_work_location_rule(_wp(description='No remote work is possible for this role.',
                                      workplace_type='Remote')) is False)
check('Turin is no exception to the tag: a Hybrid advert in Turin is dropped like any other',
      p.passes_work_location_rule(_wp(description='Hybrid role in Turin, three days in the '
                                                  'office.', workplace_type='Hybrid')) is False)
for _tag in ('Hybrid', 'On-site', 'Remote', ''):
    check('a row with tag %r never raises' % _tag,
          p.passes_work_location_rule(_wp(description='x', workplace_type=_tag)) in (True, False))

# --- a Not Remote search reads the tag the other way round ---
_NR = dict(_WMK_VALUE='not_remote')
for _tag, _want in (('Remote', False), ('Hybrid', True), ('On-site', True)):
    check('Not Remote, tagged %s -> %s' % (_tag, 'kept' if _want else 'dropped'),
          p.passes_work_location_rule(_wp(description='x', workplace_type=_tag,
                                          **{_WMK: 'not_remote'})) is _want)

# --- the normaliser for the actor that returns the tag ---
_item = {'job_id': '4467620758', 'job_title': 'Data Analyst', 'company': 'idpp',
         'location': 'Amsterdam Area', 'job_url': 'https://www.linkedin.com/jobs/view/4467620758',
         'description': 'About the job ...', 'work_type': 'Hybrid',
         'posted_at': '2026-09-23 10:24:20', 'job_insights': "['Hybrid', 'Contract']"}
_row = normalize_linkedin_pro(_item)
check('the title is read from job_title', _row['title'] == 'Data Analyst', _row)
check('  ...the link from job_url', _row['url'].endswith('4467620758'), _row)
check('  ...the tag from work_type', _row['workplace_type'] == 'Hybrid', _row)
check('  ...the date, without the time', _row['posted_date'] == '2026-09-23', _row)
check('  ...the employment type out of the insights string', _row['employment_type'] == 'Contract',
      _row)
check('  ...and seniority is None, never invented', _row['seniority_level'] is None, _row)
check('insights as a real list work too',
      normalize_linkedin_pro(dict(_item, job_insights=['Remote', 'Part-time']))[
          'employment_type'] == 'Part-time')
check('a row with no tag and no insights normalises without raising',
      normalize_linkedin_pro({'job_title': 'x'})['workplace_type'] is None)

# --- THE FOUR ADVERTS, as text, with no tag at all ---
_VISIONBI = ('Je werkt over het algemeen in een van de scrum teams bij de klant. De ideale '
             'werkweek betekent voor jou dat je gemiddeld twee dagen op de klant locatie '
             'werkt en de resterende dagen desgewenst vanuit ons kantoor in De Meern of '
             'gewoon remote. Goede beheersing van de Nederlandse (must) en Engelse taal.')
_KLM = ('Je werkt in een productteam. Ontdek de voordelen van bij ons werken: Als je functie '
        'dit toelaat: thuiswerken en tot 8 weken werken vanuit het buitenland (EU en '
        'Caribisch gebied). 25 vakantiedagen en 5 extra vrije dagen. Als je functie dit '
        'toelaat: thuiswerken en tot 8 weken werken vanuit het buitenland.')
_FABRICA = ('Senior Backend Engineer (Go). Creative Fabrica is a subscription platform '
            'serving millions of creators. As a Senior Backend Engineer you will be the '
            'architect of our multimodal generation pipeline. Work with AWS to manage '
            'massive data throughput. We are an equal opportunity employer.')
check('VISIONBI: "twee dagen op de klant locatie" is office time, and the stray "remote" at '
      'the end of that sentence no longer saves it',
      p.passes_work_location_rule(_wp(title='Azure Data Engineer', description=_VISIONBI,
                                      location='De Meern, Utrecht')) is False)
check('KLM: working from home "als je functie dit toelaat" is a perk, not a remote role',
      p.passes_work_location_rule(_wp(title='Business Product Analyst', description=_KLM))
      is False)
check('CREATIVE FABRICA: silence about where the work happens drops (rule 4, reversed)',
      p.passes_work_location_rule(_wp(title='Senior Backend Engineer', description=_FABRICA))
      is False)

# --- the three text shapes, each on its own ---
for _label, _text, _want in (
    ('two days at the client site, in English', 'You will spend two days a week at the client site.', False),
    ('"bij de klant", in Dutch', 'Je werkt twee dagen per week bij de klant. Thuiswerken mag.', False),
    ('spelled-out German', 'Zwei Tage pro Woche im Büro, der Rest remote.', False),
    ('spelled-out Dutch at the office', 'Je werkt drie dagen per week op kantoor, de rest remote.', False),
    ('French', 'Deux jours par semaine au bureau, le reste en remote.', False),
    ('a plain remote role is untouched', 'This is a remote role. Work from home, any day.', True),
    ('a home-office ALLOWANCE is not an office day', 'You get a home office allowance and work from home every day.', True),
    ('up to two days of home office means the rest is in the office (existing rule, kept)',
     'Work up to two days from home office per week.', False),
    ('remote offered plainly, once, beside a hedge elsewhere',
     'This role is fully remote. Als je functie dit toelaat: thuiswerken in het buitenland.', True),
    ('a hedge alone', 'Als je functie dit toelaat: thuiswerken is mogelijk.', False),
    ('"where possible" is a hedge', 'Remote work where possible, otherwise on site.', False),
    ('remote stated without a hedge', 'Thuiswerken is mogelijk, de hele week.', True),
):
    check('text shape: %s' % _label,
          p.passes_work_location_rule(_wp(description=_text)) is _want, _text[:60])


# ============================== 1.gated  the Type column reads the local-language words =======
section('1.gated  Dutch "Stage ..." is an Internship; the guards that stop it going wrong')
# 33 of the 4,325 Bank rows (and 62 of the 279 an Any search returned) were Dutch "Stage ..." titles
# filed Full-Time while the Internship module, reading the same title, called them internships. The
# rule speaks LAST, TITLE only, WHOLE words only, in the languages of the listing's COUNTRY.


def _typed(title, country, **extra):
    row = {'title': title, 'description': '', 'country': country, 'location': country}
    row.update(extra)
    return p.categorize(row)


# --- what it must now get right, across the countries that have their own words ---
for _title, _country, _want in (
        ('Stage Data & AI', 'Netherlands', 'Internship'),
        ('wo stage Data Science & Machine Learning', 'Netherlands', 'Internship'),
        ('hbo/ad-stage E-learning', 'Netherlands', 'Internship'),
        ('Stage Data Analytics - eCommerce', 'Netherlands', 'Internship'),
        ('Stagiair Data Science', 'Netherlands', 'Internship'),
        ('Meewerkstage Data Science', 'Netherlands', 'Internship'),
        ('Stage Data Scientist', 'France', 'Internship'),
        ('Stagiaire Data Scientist', 'France', 'Internship'),
        ('Stage Data Scientist', 'Belgium', 'Internship'),
        ('Tirocinio Data Science', 'Italy', 'Internship'),
        ('Tirocinante Data Scientist', 'Italy', 'Internship'),
        ('Stagista Data Analyst', 'Italy', 'Internship'),
        ('Prácticas Data Science', 'Spain', 'Internship'),
        ('Practicante Data Scientist', 'Spain', 'Internship'),
        ('Estágio Data Science', 'Portugal', 'Internship'),
        ('Praktikplats Data Science', 'Sweden', 'Internship'),
        ('Praktikplads Data Science', 'Denmark', 'Internship'),
        ('Praktikplass Data Science', 'Norway', 'Internship'),
        ('Harjoittelija Data Science', 'Finland', 'Internship'),
        ('Praxissemester Data Science', 'Germany', 'Internship'),
        ('Abschlusspraktikum Data Science', 'Austria', 'Internship'),
        ('Afstudeeropdracht Data Science', 'Netherlands', 'Thesis'),
        ('Diplomarbeit Data Science', 'Germany', 'Thesis'),
        ('Studienarbeit Data Science', 'Austria', 'Thesis'),
        ('Masterthesis Data Science', 'Germany', 'Thesis'),
        ('Tesi di Laurea Data Science', 'Italy', 'Thesis'),
        ('Trabajo Fin de Máster Data Science', 'Spain', 'Thesis'),
        ('Examensarbete Data Science', 'Sweden', 'Thesis'),
        ('Specialeprojekt Data Science', 'Denmark', 'Thesis'),
        ('Lopputyö Data Science', 'Finland', 'Thesis'),
        ("Stage de Fin d'Études Data Science", 'France', 'Thesis')):
    check('%s (%s) -> %s' % (_title, _country, _want), _typed(_title, _country) == _want,
          _typed(_title, _country))

# --- what it must NOT touch: each of these is a guard, and most were a real near-miss ---
for _title, _country, _why in (
        ('Stagecoördinator Opleidingen', 'Netherlands', 'a coordinator -- whole words only, never a prefix'),
        ('Ingénieur Apprentissage Automatique', 'France', '"apprentissage" is Machine Learning'),
        ('Data Scientist Apprentissage Profond', 'France', 'deep learning, not an apprenticeship'),
        ('Trainee BI Consultant', 'Netherlands', 'a graduate programme, not an internship'),
        ('Management Trainee Data', 'Germany', 'the same'),
        ('Stage Manager', 'United Kingdom', 'English "stage" -- a UK row loads English alone'),
        ('Late Stage Data Scientist', 'United States', 'English "stage"'),
        ('Stage Lead Machine Learning', 'Canada', 'English-speaking: Canada loads fr too, see below'),
        ('Senior Data Scientist', 'Netherlands', 'an ordinary job'),
        ('Data Engineer', 'Italy', 'an ordinary job'),
        ('Machine Learning Engineer', 'Spain', 'an ordinary job'),
        ('Dateningenieur', 'Germany', 'an ordinary job'),
        ('Memory Optimisation Engineer', 'France', '"mémoire" is not used on its own'),
        ('Application Specialist', 'Netherlands', 'contains letters of a word list, not a word')):
    if _country == 'Canada':
        continue      # Canada speaks French as well; asserted separately, with the honest answer
    check('stays Full-Time: %s (%s) -- %s' % (_title, _country, _why),
          _typed(_title, _country) == 'Full-Time', _typed(_title, _country))

# Canada loads French too, so "Stage ..." there IS read as an internship. That is the cost of the
# rule being by country, and it is stated rather than hidden: a Canadian "Stage Lead" would be
# mislabelled. Asserted so a change to it is deliberate.
check('Canada loads French, so a bare "Stage" there is read as an internship (known cost)',
      _typed('Stage Lead Machine Learning', 'Canada') == 'Internship')

# --- it speaks last: a row an existing rule already typed is untouched ---
check('an existing rule still wins: a Part-Time Stage is Part-Time',
      _typed('Stage Data Science (part-time)', 'Netherlands') == 'Part-Time')
check('  ...an English Intern in a Dutch city is still found by the old rule',
      _typed('Data Science Intern', 'Netherlands') == 'Internship')
check('  ...a PhD stays a PhD', _typed('PhD Position Data Science', 'Netherlands') == 'PhD')
check('a listing with no title cannot raise', _typed('', 'Netherlands') == 'Full-Time')
check('a row with no country loads every language rather than none, and does not raise',
      p.categorize({'title': 'Stage Data Science', 'description': ''}) in ('Full-Time', 'Internship'))
check('is_category_uncertain agrees: a Stage title is no longer a guess',
      not p.is_category_uncertain({'title': 'Stage Data & AI', 'description': 'x',
                                   'country': 'Netherlands'}))

# --- the words the search sends are what names the Type, except the ones deliberately not used ---
from app.pipeline import rules as _r  # noqa: E402
from app.pipeline.search import queries as _qq  # noqa: E402

_unused = set(_r._TYPE_WORDS_NOT_USED)
_missed = []
for _kind, _table, _want in (('Internship', _qq._LANGUAGE_INTERNSHIP_WORDS, 'Internship'),
                             ('Thesis', _qq._LANGUAGE_THESIS_WORDS, 'Thesis')):
    for _lang, _words in _table.items():
        _country = next((c for c, ls in _r.country_rules.COUNTRY_LANGUAGES.items()
                         if _lang in ls and 'en' != _lang), None)
        if not _country:
            continue
        for _w in _words:
            _bare = _w.strip().strip('"').strip()
            if _bare.lower() in _unused:
                continue
            # Two words are in the internship or thesis list and are typed the other way, on
            # purpose and by rules older than this one: "Afstudeerstage" is a graduation
            # placement, which this column has always called a Thesis (the old `afstudeer\w*`),
            # and "Tirocinio di Tesi" starts with `tirocinio`, which the old rule has always
            # called an Internship. Named here so changing either is a decision, not an accident.
            _expect = {('nl', 'Afstudeerstage'): 'Thesis',
                       ('it', 'Tirocinio di Tesi'): 'Internship'}.get((_lang, _bare), _want)
            if _typed('%s Data Scientist' % _bare, _country) != _expect:
                _missed.append((_lang, _bare, _typed('%s Data Scientist' % _bare, _country)))
check('every searched word that may name a Type does (%d not typed)' % len(_missed),
      not _missed, _missed[:12])
check('the words deliberately not used are exactly the documented ones',
      _unused == {'trainee', 'traineeship', 'traineeprogram', 'traineeohjelma', 'apprentissage',
                  'apprenti', 'apprendista', 'apprendistato', 'mémoire', 'alternance',
                  'alternant'}, sorted(_unused))

# =============================================================== 1.any  the Any work mode
section('1.any  Any keeps every listing, whatever it says about where the work is done')
from app.pipeline.search_title import WORK_MODE_ROW_KEY as _WM  # noqa: E402
from app.pipeline.profiles import job_profile as _jp  # noqa: E402
from app.pipeline.claude_screen.prompt import system_prompt_for as _spf, prompt_version_for as _pvf  # noqa: E402
for _text in ('This is a fully 100% remote position for our team here.',
              'This role is on-site in our Berlin office building.',
              'Hybrid role, three days per week in the office please.',
              'Remote work not available for this particular position.',
              D):
    _r = job(description=_text, **{_WM: 'any'})
    check('Any keeps: %s' % _text[:42], p.passes_work_location_rule(_r))
check('the same on-site text is still dropped in a Remote search',
      not p.passes_work_location_rule(job(description='This role is on-site in our Berlin office building.', location='Berlin',
                                          **{_WM: 'remote'})))
for _lv in ('junior', 'entry', 'mid', 'senior'):
    _a, _n, _rm = (_spf({'_search_level': _lv, _WM: m_}) for m_ in ('any', 'not_remote', 'remote'))
    check('%s: Any has its own prompt, neither Remote nor Not Remote' % _lv,
          _a not in (_n, _rm) and len(_a) > 1000)
    check('  ...with no "role is remote" drop and no "not remote" request',
          'The role is remote.' not in _a and 'A job that is not remote' not in _a
          and 'never a reason to drop' in _a)
    check('  ...and every other rule of Not Remote untouched (rules 2 on are byte-identical)',
          _a[_a.index('2. **'):] == _n[_n.index('2. **'):])
    check('  ...and its own cache version',
          len({_pvf({'_search_level': _lv, _WM: m_}) for m_ in ('any', 'not_remote', 'remote')}) == 3)
from app.pipeline.thesis import claude as _tc, finder as _tf  # noqa: E402
from app.pipeline.internship import claude as _ic, finder as _if  # noqa: E402
for _mod, _kw in ((_tc, _tf), (_ic, _if)):
    _row = {_WM: 'any'}
    check('%s: Any picks its own prompt' % _mod.__name__.split('.')[-2],
          _mod.system_prompt_for(_row) not in (_mod.system_prompt_for({_WM: 'remote'}),
                                              _mod.system_prompt_for({_WM: 'not_remote'})))
    check('  ...and its keyword location rule keeps a remote one',
          _kw.passes_location_rule({_WM: 'any', 'title': 'x', 'description': 'fully remote thesis',
                                    'location': 'Remote'}))
check('a Filter/Search saved before Any existed (not_remote) is still understood',
      p.clean_work_mode('Not Remote') == 'not_remote' and p.clean_work_mode('any') == 'any')

sys.exit(summary('Suite 1 -- rules & helpers'))
