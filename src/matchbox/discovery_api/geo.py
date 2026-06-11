"""Deterministic India-eligibility geo predicate. SSOT; no DB, no I/O, no LLM.

The user can only work in India (in-country, or remote *from* India). The
scorer treats location as a soft 10%-weight signal, so a great-fit foreign role
still bands "strong" -- this hard, no-LLM predicate is what the Today's-roles
"India-eligible only" filter uses to set those roles aside. By the user's rule a
remote role qualifies only when India is actually named; a bare
"Worldwide"/"Anywhere" does not.
"""

from __future__ import annotations

import re

# Country-column values (exact, after normalize) that mean India. Adzuna sends the
# ISO-ish "in"; ATS pollers leave the column NULL and fold the country into the
# location string instead, so the text match below carries those.
_INDIA_COUNTRY = {"in", "ind", "india", "bharat"}

# The country word -- word-bounded so "Indiana"/"Indianapolis" never match (the
# 'n'/'a' that follows defeats the boundary). "Indian"/"Indians" do count.
_INDIA_WORD = re.compile(r"\b(?:indian?s?|bharat)\b", re.I)

# Major Indian metros. Matched in the location/remote-scope always, and in the JD
# body too when the country is unknown -- many India roles state the city only in
# the JD ("Location: Bengaluru/Hyderabad/..."). An explicit foreign country blocks
# the JD-body match, so a US role that name-drops a Bangalore office is not pulled
# in. Curated and tunable; a few names are shared with non-India places (e.g.
# Delhi, Ontario) but the filter only *sets a role aside* -- visible, never lost.
_INDIA_CITIES = (
    "bengaluru",
    "bangalore",
    "mumbai",
    "delhi",
    "gurgaon",
    "gurugram",
    "noida",
    "hyderabad",
    "pune",
    "chennai",
    "kolkata",
    "ahmedabad",
    "jaipur",
    "kochi",
    "cochin",
    "indore",
    "chandigarh",
    "coimbatore",
    "nagpur",
    "mysuru",
    "mysore",
    "trivandrum",
    "thiruvananthapuram",
    "visakhapatnam",
    "vadodara",
    "surat",
    "lucknow",
)
_INDIA_CITY_RE = re.compile(r"\b(?:" + "|".join(_INDIA_CITIES) + r")\b", re.I)


def india_eligible(
    *,
    country: str | None,
    location: str | None,
    remote_scope: str | None,
    jd_text: str | None,
) -> bool:
    """Deterministic 'can this role be worked from India' test. No LLM.

    True when the role is in India or names India (or a major Indian city) as a
    place a candidate may sit. A bare 'Worldwide'/'Anywhere' remote does NOT pass.

    * country in {in, ind, india, bharat}                  -> True
    * 'India'/an Indian city in location or remote_scope   -> True
    * ...or in the JD body, when the country is unknown
      (many India roles state the city only in the JD)     -> True
    * an explicit foreign country blocks the JD-body match, so a role that merely
      name-drops an India office is not pulled in.
    """
    c = (country or "").strip().lower()
    if c in _INDIA_COUNTRY:
        return True
    # An explicit foreign country is authoritative: only the stated location or
    # remote scope can still make it India. Unknown country -> the JD body counts.
    haystack = (
        " ".join(p for p in (location, remote_scope) if p)
        if c
        else " ".join(p for p in (location, remote_scope, jd_text) if p)
    )
    return bool(_INDIA_WORD.search(haystack) or _INDIA_CITY_RE.search(haystack))
