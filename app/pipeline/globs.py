# -*- coding: utf-8 -*-
"""Turning a set of URLs into the glob shapes that would match them.

Pure string work. Nothing here knows what a job posting is -- it is handed URLs, finds the
prefixes they share, and proposes glob patterns general enough to still match a posting this
particular page happened not to link to. Deciding which proposal is right is site discovery's
job, and it happens next door.

Lifted out of pattern_discovery.py, where 133 lines of prefix arithmetic sat between the code
that opens a page and the code that saves what it learned.
"""
from __future__ import annotations

import collections
import re
from urllib.parse import urlsplit


_GLOB_REGEX_CACHE: dict = {}


def _glob_regex(glob: str):
    """A glob compiled with the SAME meaning Apify's includeUrlGlobs gives it.

    fnmatch was used here originally, and its `*` crosses `/`. Apify's does not: there,
    `*` matches within one path segment and `**` spans segments. While every generated
    glob ended in `/**` the difference never showed, but it becomes decisive as soon as a
    segment-precise glob is generated -- and those are exactly what separates
    arbeitnow.com's postings at /jobs/companies/<company>/<slug> from its city index at
    /jobs/locations/<city>. Matching locally by fnmatch's rules would verify a pattern
    that then behaves differently in the crawler that consumes it.
    """
    compiled = _GLOB_REGEX_CACHE.get(glob)
    if compiled is None:
        out, index = [], 0
        while index < len(glob):
            char = glob[index]
            if char == '*':
                if glob[index + 1:index + 2] == '*':
                    out.append('.*')
                    index += 2
                else:
                    out.append('[^/]*')
                    index += 1
            else:
                out.append(re.escape(char))
                index += 1
        compiled = re.compile('^' + ''.join(out) + '$')
        _GLOB_REGEX_CACHE[glob] = compiled
    return compiled


def _glob_match(url: str, glob: str) -> bool:
    return bool(_glob_regex(glob).match(url))


def _glob_for(url: str) -> str | None:
    """The `<scheme>://<host>/<first-segment>/**` glob a URL belongs to."""
    parts = urlsplit(url)
    segments = [s for s in parts.path.split('/') if s]
    if len(segments) < 2:
        return None
    return '%s://%s/%s/**' % (parts.scheme, parts.netloc, segments[0])


# How many leading path segments a proposed glob may pin down. Two is enough for every
# real shape seen -- /jobs/companies/<company>/<slug> pins "jobs" and "companies" -- and
# stopping there keeps a glob from being fitted so tightly to one page's links that it
# stops matching the rest of the site.
_MAX_GLOB_PREFIX_SEGMENTS = 2

# Every proposal costs up to two page fetches to verify, so the list is bounded. Reaching
# this many means the candidates have no consistent shape, and none of the tail proposals
# would have been trustworthy anyway.
_MAX_GLOB_PROPOSALS = 8


# How long a path segment may be and still be treated as a folder name rather than one
# posting's slug. Measured against the real cases: "companies" (9), "jobfinder" (9), "en"
# (2), "jobsuche" (8) are all namespaces; the segment that produced jobs.sap.com's broken
# pattern was 83 characters of job title. Nothing real sits between.
_MAX_NAMESPACE_SEGMENT_CHARS = 30

# What fraction of the sampled candidates must share a path prefix before it is worth
# pinning that prefix in a glob. A namespace every posting sits under clears this easily;
# a category name that a handful happen to share does not, which is the difference between
# a pattern and a list.
_MIN_PREFIX_SHARE = 0.25

# How many candidates must share a two-segment prefix before it is pinned. Two is enough
# evidence for a top-level segment and not enough for a deeper one, where two matches is
# most often the same posting reached by two URLs.
_MIN_DEEP_PREFIX_SHARE = 3

# How many candidate URLs to read when working out which globs to propose. See
# _candidate_globs: shapes repeat, so this is a sample rather than a limit on what the
# resulting glob may match.
_GLOB_PROPOSAL_SAMPLE = 300

def _candidate_globs(urls: list[str]) -> list[str]:
    """Every glob worth proposing for a group of job-card links, most general first.

    A single `/<first-segment>/**` is right for most job boards and wrong for the ones
    that keep more than one kind of page under that segment. startup.jobs puts both its
    postings and its category pages under /roles/, and arbeitnow.com puts postings under
    /jobs/companies/ and city indexes under /jobs/locations/ -- one glob shape cannot
    express either distinction, so several are offered and the collateral check in
    _verify_and_build decides which survives.

    Ordered general-to-specific deliberately: the broadest glob that does not sweep in
    non-job links is the one that will still match postings this page happened not to show.
    """
    proposals: list[str] = []
    seen: set = set()

    def add(glob):
        if glob not in seen:
            seen.add(glob)
            proposals.append(glob)

    # A sample, not the whole list. URL shapes repeat -- a few hundred links show every
    # shape a site uses -- while the sitemap route can hand this 37,859 URLs at once, and
    # scanning all of them against a growing proposal list took the run from seconds to
    # minutes. Deduplicating through a set rather than a list scan is the other half of it.
    shaped = []
    for url in urls[:_GLOB_PROPOSAL_SAMPLE]:
        parts = urlsplit(url)
        segments = [s for s in parts.path.split('/') if s]
        if len(segments) >= 2:
            shaped.append(('%s://%s' % (parts.scheme, parts.netloc), segments))
    if not shaped:
        return []

    # A prefix is only worth pinning if the candidates SHARE it. Pinning whatever each URL
    # happened to have there instead produced one glob per value: startup.jobs' sitemap
    # yielded 60 of them -- /roles/onboarding-manager/**, /roles/tax-analyst/**, one per
    # category -- which is not a pattern, it is a list, and verifying 60 globs meant opening
    # 120 pages. A real namespace like arbeitnow's /jobs/companies/ is shared by most of the
    # group and survives this easily.
    # Two is the floor, not three: a listing page showing only two postings is a real case,
    # and _verify_and_build already refuses any glob covering fewer than two candidates. The
    # percentage is what does the work on a large set -- 300 sitemap URLs need 75 sharing a
    # prefix before it is pinned, which is what stops one glob per category.
    minimum_share = max(2, int(len(shaped) * _MIN_PREFIX_SHARE))

    def frequent_prefixes(length):
        counts: collections.Counter = collections.Counter()
        depths: dict = collections.defaultdict(collections.Counter)
        for root, segments in shaped:
            if len(segments) <= length:
                continue
            # A prefix beyond the first segment is only worth pinning if it is a
            # NAMESPACE -- "companies", "jobfinder", "en" -- not one posting's own slug.
            # Both are "shared" when two candidate URLs happen to sit under the same job,
            # which is how jobs.sap.com came to have this saved as its permanent pattern:
            #
            #   /job/Walldorf-Working-Student-%28fmd%29-Cloud-Delivery-Architecture-...-69190/**
            #
            # It carries a wildcard, so the no-wildcard guard let it through, and it
            # matches exactly one job for the rest of that site's life. The two are easy
            # to tell apart by length: a namespace is a word, a slug is a sentence.
            if length >= 2 and any(len(segment) > _MAX_NAMESPACE_SEGMENT_CHARS
                                   for segment in segments[1:length]):
                continue
            key = (root, '/'.join(segments[:length]))
            counts[key] += 1
            depths[key][len(segments)] += 1
        # A deeper prefix has to be shared more widely than a top-level one: pinning the
        # first segment on two candidates is a reasonable guess, pinning two segments on
        # two candidates is usually just the same posting seen twice.
        floor = minimum_share if length < 2 else max(minimum_share, _MIN_DEEP_PREFIX_SHARE)
        return [(key, depths[key]) for key, count in counts.most_common()
                if count >= floor]

    # General first: one segment pinned, everything below it.
    for (root, prefix), _depths in frequent_prefixes(1):
        add('%s/%s/**' % (root, prefix))
    # Then more specific: a longer shared prefix, and the depth those candidates actually
    # have -- which is what separates /jobs/companies/*/* from /jobs/locations/<city>.
    for length in range(1, _MAX_GLOB_PREFIX_SEGMENTS + 1):
        for (root, prefix), depths in frequent_prefixes(length):
            add('%s/%s/**' % (root, prefix))
            for depth, count in depths.most_common(2):
                if count < minimum_share or depth <= length:
                    # depth == length leaves an empty tail, which produces a glob with no
                    # wildcard at all -- a single fixed URL. A real run saved exactly that
                    # for jobs.sap.com: the full address of one Walldorf working-student
                    # posting, saved as if it were a pattern, matching that one job and
                    # nothing else for the rest of the site's life.
                    continue
                tail = '/'.join(['*'] * (depth - length))
                add('%s/%s/%s' % (root, prefix, tail))
    # Nothing without a wildcard ever leaves here, whatever the loops above did.
    return [glob for glob in proposals if '*' in glob][:_MAX_GLOB_PROPOSALS]
