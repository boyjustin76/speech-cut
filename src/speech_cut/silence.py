"""Silence as a list of spans, and the set arithmetic for removing it.

Why a silence map at all, when words already have end times?

Because ASR word end times are not where the sound stops. Recognisers stretch the
last word before a pause to meet the next word, so "cut at the end of the last word"
can leave seconds of room tone in the clip. Two measurements from real recordings:

* a word written as 1.9 s long whose audio ended after 0.7 s
* a word written as 6.9 s long, where the speaker had actually stopped, paused, and
  said the line again

Supply a silence map and cuts land where the sound stops. Supply nothing and
:func:`from_word_gaps` approximates one from the gaps between words, which is better
than nothing and costs no dependencies.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from .words import Word

__all__ = ["Span", "subtract", "merge", "from_word_gaps", "covers"]

Span = Tuple[float, float]


def merge(spans: Iterable[Span], bridge: float = 0.0) -> List[Span]:
    """Sort spans and join overlapping ones (and ones closer than *bridge*)."""
    ordered = sorted((float(a), float(b)) for a, b in spans if b > a)
    out: List[Span] = []
    for a, b in ordered:
        if out and a - out[-1][1] <= bridge:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def subtract(spans: Sequence[Span], holes: Sequence[Span]) -> List[Span]:
    """Remove *holes* from *spans*, returning what is left.

    >>> subtract([(0.0, 10.0)], [(3.0, 4.0)])
    [(0.0, 3.0), (4.0, 10.0)]
    """
    out: List[Span] = []
    for start, end in spans:
        pieces = [(start, end)]
        for hole_start, hole_end in holes:
            nxt: List[Span] = []
            for a, b in pieces:
                if hole_end <= a or hole_start >= b:
                    nxt.append((a, b))
                    continue
                if hole_start > a:
                    nxt.append((a, min(hole_start, b)))
                if hole_end < b:
                    nxt.append((max(hole_end, a), b))
            pieces = nxt
        out += [(a, b) for a, b in pieces if b > a]
    return out


def covers(spans: Sequence[Span], start: float, end: float) -> float:
    """Total length of *spans* falling inside ``[start, end]``."""
    return sum(max(0.0, min(end, b) - max(start, a)) for a, b in spans)


def from_word_gaps(words: Sequence[Word], at_least: float = 0.35) -> List[Span]:
    """Approximate a silence map from the gaps between words.

    A fallback for when you have no audio to measure. It cannot see the silence that
    an over-long word is hiding -- which is exactly the case a real silence map
    catches -- so prefer measuring the audio when you can.
    """
    out: List[Span] = []
    for earlier, later in zip(words, words[1:]):
        if later.start - earlier.end >= at_least:
            out.append((earlier.end, later.start))
    return out
