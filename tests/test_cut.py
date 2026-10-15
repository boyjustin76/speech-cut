"""The end-to-end decision: words in, clips out.

Each test names the symptom it prevents. Those symptoms all happened.
"""

import json
import pathlib

import pytest

from speech_cut import Word, cut_to_speech, from_whisper, label_for, subtract

EXAMPLES = pathlib.Path(__file__).resolve().parents[1] / "examples"


def w(start, end, text, confidence=0.99):
    return Word(start, end, text, confidence)


@pytest.fixture()
def sample():
    words = from_whisper(json.loads((EXAMPLES / "transcript.sample.json").read_text("utf-8")))
    silences = [
        tuple(s) for s in
        json.loads((EXAMPLES / "silences.sample.json").read_text("utf-8"))["silences"]
    ]
    return words, silences


def test_the_quickstart_works(sample):
    """The README's first command. If this breaks, nobody gets past the front page."""
    words, silences = sample
    result = cut_to_speech(words, silences, source_seconds=36.8)
    assert len(result.keep) == 4
    assert result.summary()["removed_percent"] > 40


def test_the_false_start_is_dropped(sample):
    """'Uh so' -- short and the recogniser was unsure. Always a cough, never content."""
    words, silences = sample
    result = cut_to_speech(words, silences)
    assert not any(c.start < 10.5 < c.end for c in result.keep)


def test_the_flubbed_take_goes_and_the_clean_one_stays(sample):
    """The headline feature. A volume-based cutter keeps both."""
    words, silences = sample
    result = cut_to_speech(words, silences)
    kept_text = " ".join(label_for(words, c, limit=200) for c in result.keep)
    assert kept_text.count("Enter at the close") == 1
    assert "magenta" in kept_text


def test_the_parallel_clause_survives(sample):
    words, silences = sample
    result = cut_to_speech(words, silences)
    assert any("Exit at the close" in label_for(words, c, limit=200) for c in result.keep)


def test_no_clip_holds_on_silence(sample):
    """A clip must not run past its last word -- otherwise an over-long word end
    leaves seconds of room tone on screen."""
    words, silences = sample
    result = cut_to_speech(words, silences, tail=0.2)
    for clip in result.keep:
        inside = [x for x in words if x.end > clip.start and x.start < clip.end]
        assert inside, "every clip must contain speech"
        assert clip.end <= inside[-1].end + 0.2 + 1e-6


def test_short_pauses_are_kept():
    """Removing every breath makes speech sound machine-gunned."""
    words = [w(0.0, 1.0, "one"), w(1.2, 2.2, "two")]
    result = cut_to_speech(words, [(1.0, 1.2)], min_silence=0.35)
    assert len(result.keep) == 1


def test_long_pauses_are_cut():
    words = [w(0.0, 1.0, "one"), w(3.0, 4.0, "two")]
    result = cut_to_speech(words, [(1.0, 3.0)], min_silence=0.35, min_clip=0.2)
    assert len(result.keep) == 2


def test_no_clip_is_a_sub_second_flash():
    """A 0.4 s clip is a flash on screen, not an edit. Fragments get glued back on."""
    words = [w(0.0, 0.3, "a"), w(0.6, 2.0, "proper"), w(2.0, 3.4, "sentence")]
    result = cut_to_speech(words, [(0.3, 0.6)], min_silence=0.2)
    assert all(c.duration >= 1.0 for c in result.keep)


def test_clips_are_in_order_and_do_not_overlap(sample):
    words, silences = sample
    result = cut_to_speech(words, silences)
    for earlier, later in zip(result.keep, result.keep[1:]):
        assert earlier.end <= later.start


def test_dropped_spans_account_for_the_rest(sample):
    """The removed material is reported so an editor can review it, not just trust us."""
    words, silences = sample
    result = cut_to_speech(words, silences, source_seconds=36.8)
    assert result.drop
    left = subtract([(0.0, 36.8)], [(c.start, c.end) for c in result.keep])
    assert sum(b - a for a, b in left) == pytest.approx(
        sum(b - a for a, b in result.drop), abs=1.0
    )


def test_empty_input_is_not_a_crash():
    result = cut_to_speech([], [])
    assert result.keep == [] and result.kept_seconds == 0.0


def test_works_with_no_silence_map(sample):
    """Degraded but functional: gaps between words stand in for a measured map."""
    words, _ = sample
    result = cut_to_speech(words, [])
    assert result.keep
