"""Turn word timestamps into a list of clips to keep.

The order of operations matters, and each step exists because of something that went
wrong without it. Reading this function top to bottom is the fastest way to
understand the library.
"""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple, Optional, Sequence

from .silence import Span, merge, subtract
from .takes import drop_repeated_takes, says_it_twice
from .words import Word, text_of, touching

__all__ = ["Clip", "CutResult", "cut_to_speech"]


class Clip(NamedTuple):
    """A span of the source to keep."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class CutResult(NamedTuple):
    keep: List[Clip]
    """Clips to keep, in order."""
    drop: List[Span]
    """What fell out, in order -- silence, retakes, everything below the thresholds.
    Keep these: putting them on a disabled track lets an editor see what was removed
    instead of trusting you."""
    kept_seconds: float
    source_seconds: float

    def summary(self) -> Dict[str, Any]:
        return {
            "clips": len(self.keep),
            "kept_seconds": round(self.kept_seconds, 3),
            "source_seconds": round(self.source_seconds, 3),
            "removed_seconds": round(self.source_seconds - self.kept_seconds, 3),
            "removed_percent": (
                round(100 * (1 - self.kept_seconds / self.source_seconds), 1)
                if self.source_seconds else 0.0
            ),
            "shortest": round(min((c.duration for c in self.keep), default=0.0), 2),
            "longest": round(max((c.duration for c in self.keep), default=0.0), 2),
        }


def _confidence(words: Sequence[Word], start: float, end: float) -> float:
    """Confidence over a span, weighted by how much of each word falls inside it."""
    total = weighted = 0.0
    for w in words:
        overlap = min(end, w.end) - max(start, w.start)
        if overlap > 0:
            weighted += w.confidence * overlap
            total += overlap
    return (weighted / total) if total else 1.0


def cut_to_speech(
    words: Sequence[Word],
    silences: Sequence[Span] = (),
    *,
    gap: float = 0.30,
    lead: float = 0.10,
    tail: float = 0.20,
    min_clip: float = 0.25,
    min_silence: float = 0.35,
    drop_retakes: bool = True,
    retake_similarity: float = 0.80,
    junk_under: float = 2.5,
    junk_confidence: float = 0.40,
    merge_under: float = 1.2,
    merge_gap: float = 1.2,
    source_seconds: Optional[float] = None,
) -> CutResult:
    """Decide which parts of the recording to keep.

    :param words: word-level timestamps, in order
    :param silences: measured silence spans. Optional but worth supplying -- see
        :mod:`speech_cut.silence` for why word end times are not enough.
    :param gap: a pause at least this long splits one clip into two
    :param lead/tail: breathing room around each clip, never crossing into a
        neighbouring word or a neighbouring clip
    :param min_clip: clips shorter than this are dropped outright
    :param min_silence: **short pauses are kept.** Removing every breath makes speech
        sound machine-gunned; only silence at least this long is cut out.
    :param drop_retakes: remove material the speaker immediately said again
    :param junk_under / junk_confidence: a short clip the recogniser was unsure about
        is almost always a false start or a cough, not speech
    :param merge_under / merge_gap: glue sub-second fragments back to their neighbour.
        A 0.4 s clip is a flash on screen, not an edit.
    :param source_seconds: total media length, for the summary only
    """
    words = list(words)
    if not words:
        return CutResult([], [], 0.0, float(source_seconds or 0.0))

    holes = [s for s in merge(silences) if s[1] - s[0] >= min_silence]

    # 1. Retakes first, before anything measures a span. The removed stretches become
    #    holes exactly like silence -- see drop_repeated_takes on why that is needed.
    if drop_retakes:
        words, retake_holes = drop_repeated_takes(
            words, holes, gap=max(gap, 0.5), similarity=retake_similarity
        )
        holes = merge(holes + retake_holes)
        if not words:
            return CutResult([], holes, 0.0, float(source_seconds or 0.0))

    span = (words[0].start, words[-1].end)

    # 2. Remove the holes, then split wherever what is left is far enough apart.
    pieces: List[List[float]] = []
    for a, b in subtract([span], holes):
        if pieces and a - pieces[-1][1] <= gap:
            pieces[-1][1] = b
        else:
            pieces.append([a, b])

    # 3. A piece with no words in it is silence the map missed. Drop it rather than
    #    leave a held frame on screen.
    pieces = [p for p in pieces if touching(words, p[0], p[1])]

    # 4. Breathing room, fenced in on every side.
    for i, piece in enumerate(pieces):
        previous_end = pieces[i - 1][1] if i else 0.0
        next_start = pieces[i + 1][0] if i + 1 < len(pieces) else float("inf")
        inside = touching(words, piece[0], piece[1])
        piece[0] = max(piece[0] - lead, previous_end, inside[0].start - lead, 0.0)
        # End at the last word, not at the end of the piece: if the silence map missed
        # the pause after the final word, the clip would hold on nothing for seconds.
        piece[1] = min(piece[1] + tail, next_start, inside[-1].end + tail)
        # And never run into the next word -- that is how you get the same word
        # audible at the end of one clip and the start of the next.
        upcoming = next((w.start for w in words if w.start >= piece[1] - tail - 0.01), None)
        if upcoming is not None and upcoming < piece[1]:
            piece[1] = max(piece[0] + 0.05, upcoming - 0.02)
        if piece[1] <= piece[0]:
            piece[1] = piece[0] + 0.05

    # 5. Too short, or short and the recogniser was guessing.
    kept = [
        p for p in pieces
        if p[1] - p[0] >= min_clip
        and not (p[1] - p[0] < junk_under and _confidence(words, p[0], p[1]) < junk_confidence)
    ]

    # 6. Overlaps can appear once spans have been padded; fold them together.
    kept.sort()
    folded: List[List[float]] = []
    for piece in kept:
        if folded and piece[0] < folded[-1][1]:
            folded[-1][1] = max(folded[-1][1], piece[1])
        else:
            folded.append(piece)
    kept = folded

    # 7. A stammer leaves the same word at the end of one clip and the start of the
    #    next. Trim the earlier one. Repeat: some words are stammered more than twice.
    for _ in range(3):
        changed = False
        for before, after in zip(kept, kept[1:]):
            if says_it_twice(touching(words, *before), touching(words, *after)):
                cut_at = touching(words, *before)[-1].start - 0.02
                if cut_at - before[0] >= 0.4:
                    before[1] = cut_at
                    changed = True
        if not changed:
            break

    # 8. Glue fragments back on. Then check 7 again -- gluing can re-create a stammer.
    glued: List[List[float]] = []
    for piece in kept:
        short = (piece[1] - piece[0] < merge_under
                 or (glued and glued[-1][1] - glued[-1][0] < merge_under))
        if glued and short and piece[0] - glued[-1][1] < merge_gap:
            glued[-1][1] = piece[1]
        else:
            glued.append(piece)
    for _ in range(3):
        out: List[List[float]] = []
        changed = False
        for i, piece in enumerate(glued):
            nxt = glued[i + 1] if i + 1 < len(glued) else None
            if nxt and says_it_twice(touching(words, *piece), touching(words, *nxt)):
                cut_at = touching(words, *piece)[-1].start - 0.02
                changed = True
                if cut_at - piece[0] >= 0.4:
                    piece[1] = cut_at
                else:
                    continue  # nothing worth keeping once the repeat is removed
            out.append(piece)
        glued = out
        if not changed:
            break

    clips = [Clip(round(a, 3), round(b, 3)) for a, b in glued]
    total = float(source_seconds) if source_seconds else (words[-1].end if words else 0.0)

    dropped: List[Span] = []
    previous = 0.0
    for clip in clips:
        if clip.start - previous > 0.5:
            dropped.append((round(previous, 3), round(clip.start, 3)))
        previous = clip.end
    if total - previous > 0.5:
        dropped.append((round(previous, 3), round(total, 3)))

    return CutResult(clips, dropped, sum(c.duration for c in clips), total)


def label_for(words: Sequence[Word], clip: Clip, limit: int = 40) -> str:
    """First few words of a clip -- handy as a clip name in an NLE."""
    said = text_of(touching(words, clip.start, clip.end))
    return said[:limit] + ("..." if len(said) > limit else "")
