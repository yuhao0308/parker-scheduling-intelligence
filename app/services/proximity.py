"""Zip-code based proximity estimation.

Uses pgeocode for zip code centroid distance calculation.
Returns a normalized score: closer = higher score.
"""

from __future__ import annotations

import pgeocode


# Lazy-loaded distance calculator
_dist: pgeocode.GeoDistance | None = None


def _get_distance_calculator() -> pgeocode.GeoDistance:
    global _dist
    if _dist is None:
        _dist = pgeocode.GeoDistance("US")
    return _dist


def estimate_distance_miles(candidate_zip: str, facility_zip: str) -> float:
    """Estimate distance in miles between two US zip codes.

    Returns distance in miles, or a large default if either zip is unknown.
    """
    dist = _get_distance_calculator()
    km = dist.query_postal_code(candidate_zip, facility_zip)

    if km != km:  # NaN check
        return 50.0  # default penalty for unknown zips

    return km * 0.621371  # km to miles


def proximity_score(distance_miles: float, max_distance: float = 30.0) -> float:
    """Convert distance to a 0–1 score. Closer = higher.

    Staff beyond max_distance get 0. Staff at facility get 1.
    """
    if distance_miles <= 0:
        return 1.0
    return max(0.0, 1.0 - distance_miles / max_distance)
