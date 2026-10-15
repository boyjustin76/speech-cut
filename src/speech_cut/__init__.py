"""Cut video to what was actually said, using word-level timestamps.

    from speech_cut import Word, cut_to_speech, from_whisper

    words = from_whisper(json.load(open("transcript.json")))
    result = cut_to_speech(words, silences)

    for clip in result.keep:
        print(clip.start, clip.end)

No dependencies. Bring your own transcript.
"""

from .cut import Clip, CutResult, cut_to_speech, label_for
from .silence import from_word_gaps, merge, subtract
from .takes import drop_repeated_takes, says_it_twice, split_into_takes
from .words import Word, from_whisper, text_of, touching

__version__ = "0.1.0"
__all__ = [
    "Word",
    "from_whisper",
    "text_of",
    "touching",
    "Clip",
    "CutResult",
    "cut_to_speech",
    "label_for",
    "from_word_gaps",
    "merge",
    "subtract",
    "split_into_takes",
    "drop_repeated_takes",
    "says_it_twice",
    "__version__",
]
