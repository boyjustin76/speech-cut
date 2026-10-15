"""Optional: trim words that are not in the script.

Only useful if you have a script *and* know roughly where each line lands (from a
forced aligner, or by matching segments yourself). Given the words for one line, this
shaves off whatever the speaker said around it that is not the line: "let me do that
again", a director's note, a repeated opening.

The margin is the whole trick
-----------------------------
The obvious version trims a word whenever doing so raises the similarity to the
script at all. That version eats real speech, because people do not read scripts
word for word. Measured example — the script said "there are three steps", the
speaker said "there are three parts":

    "there are three parts"   vs script   0.571
    "there are three"         vs script   0.600   <- higher, so the word goes

"parts" disappears from the edit, and nothing warns you. Removing genuine junk, by
contrast, moves similarity in jumps of about 0.09. A margin of **0.03** separates the
two: large enough to ignore wording drift, small enough to still strip the junk.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import List, Sequence

from .takes import normalise
from .words import Word

__all__ = ["trim_to_script"]


def trim_to_script(words: Sequence[Word], line: str, margin: float = 0.03) -> List[Word]:
    """Drop words from either end while that clearly improves the match to *line*.

    :param margin: minimum improvement required to remove a word. Raise it if the
        speaker paraphrases heavily; lower it only if you know the delivery is
        verbatim.
    """
    target = normalise(line)
    if not words or not target:
        return list(words)

    lo, hi = 0, len(words)

    def score(a: int, b: int) -> float:
        return SequenceMatcher(
            None, normalise("".join(w.text for w in words[a:b])), target
        ).ratio()

    best = score(lo, hi)
    while hi - lo > 1:
        options = [(score(lo + 1, hi), lo + 1, hi), (score(lo, hi - 1), lo, hi - 1)]
        candidate, new_lo, new_hi = max(options)
        if candidate <= best + margin:
            break
        best, lo, hi = candidate, new_lo, new_hi
    return list(words[lo:hi])
