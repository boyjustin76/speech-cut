"""Retakes: the speaker fluffed a line, stopped, and said it again. Keep the later one.

This is the part volume-based cutters cannot do. A silence detector sees two bursts of
speech separated by a pause and keeps both, so your edit says the same sentence twice.
Deciding which one to drop needs to know *what was said*, which is why this library
takes a transcript instead of an audio level.

The rule is simple and it is what a human editor does: **within one attempt at a line,
if two consecutive chunks say nearly the same thing, keep the later one.**

Three things make it harder than it sounds, all of them measured on real footage:

1. **Word times do not separate the takes.** Recognisers stretch a word's end to meet
   the next word, so the last word of take A and the first word of take B are often
   flush against each other even when there is a 0.8 s pause between them. Splitting
   on word gaps alone finds nothing. We split on *silence that straddles the junction*
   as well.

2. **The repeat is usually a tail, not a whole chunk.** A speaker who gets three
   clauses in and stumbles repeats only the third. So the earlier chunk still holds
   good material and must be trimmed from the end, not discarded.

3. **Neighbouring lines can look like retakes.** "Enter long when the dot turns teal"
   and "enter short when the dot turns magenta" are mostly the same words in the same
   order. This is the failure mode to fear, because dropping one deletes content the
   speaker meant to keep.

Where the default threshold comes from
--------------------------------------
Measured on two unscripted-but-prompted recordings, 13 and 16 minutes, 216 chunks
total. Every adjacent pair was scored and then read by a human:

===================================  ==========================================
real retakes                         1.00, 1.00, 0.98, 0.98, 0.96   (recording A)
                                     1.00, 1.00, 0.91, 0.84, 0.83, 0.81  (B)
parallel clauses -- must NOT drop    0.72, 0.63, 0.62
===================================  ==========================================

So ``0.80`` sits in the gap: above every false positive we saw, below every
confident retake. Partial retakes do score lower (0.78 down to 0.53 in recording B,
where the speaker repeated half a line or added words), and the default misses those.
Lowering the threshold to catch them starts eating parallel clauses. Pick your side
with ``similarity``; there is no value that gets both.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List, Sequence, Tuple

from .silence import Span
from .words import Word

__all__ = ["normalise", "split_into_takes", "drop_repeated_takes", "says_it_twice"]

_NOT_WORD = re.compile(r"[^0-9A-Za-zÀ-ɏͰ-῿぀-퟿]+")


def normalise(text: str) -> str:
    """Letters and digits only, for comparison. Punctuation and spacing are noise here."""
    return _NOT_WORD.sub("", str(text)).lower()


def split_into_takes(
    words: Sequence[Word],
    silences: Sequence[Span] = (),
    gap: float = 0.5,
) -> List[List[Word]]:
    """Break a run of words wherever the speaker stopped.

    A break happens when the gap between two words is at least *gap*, **or** when a
    silence span straddles the junction between them. The second condition is the one
    that matters: see note 1 in the module docstring.
    """
    if not words:
        return []
    chunks: List[List[Word]] = []
    current: List[Word] = []
    for i, word in enumerate(words):
        current.append(word)
        if i + 1 == len(words):
            break
        nxt = words[i + 1]
        midpoint = (word.end + nxt.start) / 2.0
        quiet = any(a < midpoint < b for a, b in silences)
        if nxt.start - word.end >= gap or quiet:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def drop_repeated_takes(
    words: Sequence[Word],
    silences: Sequence[Span] = (),
    gap: float = 0.5,
    similarity: float = 0.80,
) -> Tuple[List[Word], List[Span]]:
    """Remove material that the speaker immediately said again.

    :returns: ``(kept_words, removed_spans)``.

    **Use the removed spans.** Dropping words from the list is not enough: callers
    build a clip from "first word start" to "last word end", so a hole in the middle
    stays in the clip unless it is subtracted as well. Treat the returned spans
    exactly like silence.
    """
    chunks = split_into_takes(words, silences, gap)
    kept: List[Word] = []
    removed: List[Span] = []
    for i, chunk in enumerate(chunks):
        later = normalise("".join(w.text for w in chunks[i + 1])) if i + 1 < len(chunks) else ""
        if later:
            # Walk backwards from the end of this chunk, growing a tail, and find the
            # longest tail that still looks like the next chunk.
            #
            # The tail must *begin with the same word* the next chunk begins with.
            # Someone redoing a line restarts it from a word boundary, so the repeat
            # and the original open identically. Parallel clauses do not: "Enter at
            # the close ... magenta" and "Exit at the close ... teal" differ in
            # exactly the first word, and that one check separates them even though
            # the rest is word-for-word the same.
            opening = normalise(chunks[i + 1][0].text)
            tail, best, count = "", 0.0, 0
            for j in range(len(chunk) - 1, -1, -1):
                tail = normalise(chunk[j].text) + tail
                if len(tail) > len(later) * 1.6:
                    break
                if normalise(chunk[j].text) != opening:
                    continue
                score = SequenceMatcher(None, tail, later).ratio()
                if score > best:
                    best, count = score, len(chunk) - j
            if best >= similarity and count:
                removed.append((chunk[len(chunk) - count].start, chunk[-1].end))
                chunk = chunk[: len(chunk) - count]
        kept += chunk
    return kept, removed


def says_it_twice(before: Sequence[Word], after: Sequence[Word]) -> bool:
    """Does the end of one clip repeat the start of the next?

    Looks identical in two opposite situations, and the difference matters:

    * **Said twice.** A stammer or a splice between takes. There are *two* words.
      Trim the first one away.
    * **One word split across a cut.** There is *one* word, overlapping both clips.
      Trimming it deletes that word from the edit entirely.

    Matching text cannot tell them apart; word identity can. That is the whole
    function: if both clips point at the same word object, nobody said anything twice.
    """
    if not before or not after:
        return False
    last, first = before[-1], after[0]
    if last is first:
        return False
    return bool(normalise(last.text)) and normalise(last.text) == normalise(first.text)
