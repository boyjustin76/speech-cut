"""Script matching, and the margin that keeps it from eating real speech."""

from speech_cut import Word
from speech_cut.script import trim_to_script


def w(start, end, text):
    return Word(start, end, text, 0.99)


def test_trailing_junk_is_removed():
    """'sorry, again' is not in the script and should not be in the edit."""
    words = [w(0, 1, "there"), w(1, 2, "are"), w(2, 3, "three"), w(3, 4, "steps"),
             w(4.1, 4.4, "sorry"), w(4.4, 5.0, "again")]
    assert [x.text for x in trim_to_script(words, "there are three steps")] == [
        "there", "are", "three", "steps"
    ]


def test_a_repeated_opening_is_removed():
    words = [w(0, 1, "today"), w(1, 2, "we"),
             w(2.5, 3.5, "today"), w(3.5, 4.5, "we"), w(4.5, 5.5, "begin")]
    out = trim_to_script(words, "today we begin")
    assert out[-1].text == "begin"
    assert len(out) <= 4


def test_a_paraphrased_word_is_kept():
    """The measured failure the margin exists for: script says 'steps', speaker says
    'parts'. Dropping it raises similarity 0.571 -> 0.600, and the word vanishes."""
    words = [w(0, 1, "there"), w(1, 2, "are"), w(2, 3, "three"), w(3, 4, "parts")]
    assert [x.text for x in trim_to_script(words, "there are three steps")] == [
        "there", "are", "three", "parts"
    ]


def test_an_exact_match_is_left_alone():
    words = [w(0, 1, "hello"), w(1, 2, "world")]
    assert trim_to_script(words, "hello world") == words


def test_empty_inputs_are_safe():
    assert trim_to_script([], "anything") == []
    assert trim_to_script([w(0, 1, "x")], "") == [w(0, 1, "x")]
