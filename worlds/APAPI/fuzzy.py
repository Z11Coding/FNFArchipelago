from __future__ import annotations

"""APAPI fuzzy matching helper – generic "Did you mean?" for any iterable of strings."""

from typing import Iterable, Optional

from Utils import get_fuzzy_results


def did_you_mean(
    input_text: str,
    candidates: Iterable[str],
    limit: int = 100,
    cutoff: int = 70,
) -> Optional[str]:
    """Return a 'Did you mean "X"?' suggestion if a close match exists.

    Generic – works with any iterable of strings (location names, item names, etc.),
    unlike the fixed OptionError messages. Does not resolve the error, just
    suggests.
    """
    if not input_text or not candidates:
        return None
    # Filter to unique strings, ignore empty
    cand_list = [c for c in candidates if isinstance(c, str) and c.strip()]
    if not cand_list:
        return None
    try:
        results = get_fuzzy_results(input_text, cand_list, limit=limit)
        if not results:
            return None
        best, score = results[0]
        if score >= cutoff and best != input_text:
            return f'Did you mean "{best}"? (confidence: {score})'
        return None
    except Exception:
        return None


def format_did_you_mean(
    input_text: str,
    candidates: Iterable[str],
    limit: int = 100,
    cutoff: int = 70,
) -> str:
    """Return ' Did you mean "X"?' or ''."""
    suggestion = did_you_mean(input_text, candidates, limit, cutoff)
    return f" {suggestion}" if suggestion else ""


__all__ = ["did_you_mean", "format_did_you_mean"]
