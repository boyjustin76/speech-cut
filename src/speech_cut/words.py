"""The input type: one spoken word with a start and an end.

Everything in this library is a function over a list of :class:`Word`. Where those
words come from is your business -- Whisper, WhisperX, Deepgram, AssemblyAI, a forced
aligner, or a CSV you typed by hand. :func:`from_whisper` is provided because that is
what most people have.

A note on word end times
------------------------
ASR systems routinely stretch a word's ``end`` to meet the next word's ``start``, so
the last word before a pause can appear to run for the whole pause. We measured 1.2 s
of invented duration on a single word, and 6.9 s on one where the speaker paused and
repeated themselves.

This matters because "cut at the end of the last word" then leaves seconds of silence
in the clip. It is why :mod:`speech_cut.silence` exists and why a silence map, when
you can supply one, makes the cuts noticeably tighter.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, NamedTuple

__all__ = ["Word", "from_whisper", "text_of", "touching", "span_of"]


class Word(NamedTuple):
    """One word on the timeline. Times are seconds from the start of the media."""

    start: float
    end: float
    text: str
    confidence: float = 1.0

    @property
    def duration(self) -> float:
        return self.end - self.start


def from_whisper(segments: Iterable[Dict[str, Any]]) -> List[Word]:
    """Read ``faster-whisper`` / ``openai-whisper`` style JSON into :class:`Word` objects.

    Accepts the common shapes: a list of segments each holding ``words``, where a word
    is ``{"word"|"w": str, "start"|"s": float, "end"|"e": float,
    "probability"|"p": float}``. Words without usable times are skipped rather than
    guessed at.
    """
    out: List[Word] = []
    for segment in segments:
        for w in segment.get("words") or []:
            start = w.get("start", w.get("s"))
            end = w.get("end", w.get("e"))
            if start is None or end is None:
                continue
            text = str(w.get("word", w.get("w", ""))).strip()
            if not text:
                continue
            confidence = w.get("probability", w.get("p", 1.0))
            out.append(Word(float(start), float(end), text, float(confidence)))
    out.sort()
    return out


def text_of(words: Iterable[Word], joiner: str = " ") -> str:
    """Readable text for a run of words."""
    return joiner.join(w.text for w in words).strip()


def touching(words: Iterable[Word], start: float, end: float,
             slack: float = 0.02) -> List[Word]:
    """Words that overlap ``[start, end]`` at all.

    Use this when asking "would the viewer hear any of this word?" -- even a 0.2 s
    sliver of a word is audible as a stutter.
    """
    return [w for w in words if w.end > start + slack and w.start < end - slack]


def span_of(words: List[Word]) -> tuple:
    """``(first start, last end)`` for a non-empty run of words."""
    return (words[0].start, words[-1].end)
