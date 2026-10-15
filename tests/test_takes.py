"""Retake detection -- the part that volume-based cutters cannot do.

Every case here came off real footage. Where a number appears in an assertion, it was
measured, not chosen.
"""

from speech_cut import Word, drop_repeated_takes, says_it_twice, split_into_takes


def w(start, end, text, confidence=0.99):
    return Word(start, end, text, confidence)


def test_a_pause_splits_takes():
    words = [w(0, 1, "one"), w(1, 2, "two"), w(5, 6, "three")]
    assert [[x.text for x in t] for t in split_into_takes(words, [], gap=0.5)] == [
        ["one", "two"],
        ["three"],
    ]


def test_silence_splits_takes_even_when_word_times_touch():
    """The case that defeats gap-based splitting.

    Recognisers stretch a word's end to meet the next word, so take A's last word and
    take B's first word are flush against each other across a real 0.8 s pause.
    """
    words = [w(10.0, 11.0, "stopped"), w(11.0, 12.0, "restarted")]
    assert len(split_into_takes(words, [], gap=0.5)) == 1  # no gap to find
    assert len(split_into_takes(words, [(10.8, 11.6)], gap=0.5)) == 2


def test_the_later_take_is_the_one_kept():
    words = [
        w(10.0, 11.0, "enter"), w(11.0, 12.0, "at"), w(12.0, 13.0, "the"),
        w(15.0, 16.0, "enter"), w(16.0, 17.0, "at"), w(17.0, 18.0, "the"),
    ]
    kept, holes = drop_repeated_takes(words, [])
    assert [x.start for x in kept] == [15.0, 16.0, 17.0]
    assert holes == [(10.0, 13.0)]


def test_removed_spans_are_returned_as_holes():
    """Dropping words is not enough: a clip spans first-start to last-end, so a hole
    left in the middle stays in the edit unless the caller subtracts it."""
    words = [
        w(1.0, 2.0, "intro"), w(2.0, 3.0, "line"),
        w(5.0, 6.0, "line"),
    ]
    kept, holes = drop_repeated_takes(words, [])
    assert holes, "the removed stretch must be reported, not silently dropped"
    assert holes[0][0] >= 1.0 and holes[0][1] <= 3.0


def test_only_the_repeated_tail_is_removed():
    """A speaker who stumbles three clauses in repeats only the third clause.
    The earlier chunk still holds good material."""
    words = [
        w(0.0, 1.0, "first"), w(1.0, 2.0, "clause"),
        w(2.0, 3.0, "second"), w(3.0, 4.0, "clause"),
        w(6.0, 7.0, "second"), w(7.0, 8.0, "clause"),
    ]
    kept, holes = drop_repeated_takes(words, [])
    assert [x.text for x in kept] == ["first", "clause", "second", "clause"]
    assert holes == [(2.0, 4.0)]


def test_parallel_clauses_are_not_retakes():
    """The failure mode to fear. Measured at 0.72, 0.63 and 0.62 similarity on real
    footage -- and here, near-identical except for the first and last word."""
    words = [
        w(0.0, 1.0, "enter"), w(1.0, 2.0, "when"), w(2.0, 3.0, "it"),
        w(3.0, 4.0, "turns"), w(4.0, 5.0, "magenta"),
        w(7.0, 8.0, "exit"), w(8.0, 9.0, "when"), w(9.0, 10.0, "it"),
        w(10.0, 11.0, "turns"), w(11.0, 12.0, "teal"),
    ]
    kept, holes = drop_repeated_takes(words, [])
    assert holes == [], "dropping one of these deletes content the speaker meant"
    assert len(kept) == 10


def test_a_retake_must_open_with_the_same_word():
    """What separates a retake from a parallel clause: someone redoing a line
    restarts it, so both start identically."""
    same_opening = [
        w(0.0, 1.0, "enter"), w(1.0, 2.0, "now"),
        w(4.0, 5.0, "enter"), w(5.0, 6.0, "now"),
    ]
    assert drop_repeated_takes(same_opening, [])[1] == [(0.0, 2.0)]

    different_opening = [
        w(0.0, 1.0, "enter"), w(1.0, 2.0, "now"),
        w(4.0, 5.0, "exit"), w(5.0, 6.0, "now"),
    ]
    assert drop_repeated_takes(different_opening, [])[1] == []


def test_punctuation_and_case_do_not_matter():
    words = [w(0.0, 1.0, "Ready?"), w(3.0, 4.0, "ready")]
    assert drop_repeated_takes(words, [])[1] == [(0.0, 1.0)]


def test_retake_detection_can_be_tuned_off():
    words = [w(0.0, 1.0, "line"), w(3.0, 4.0, "line")]
    assert drop_repeated_takes(words, [], similarity=1.01)[1] == []


# -- says_it_twice ---------------------------------------------------------------

def test_a_stammer_at_a_splice_is_two_words():
    first, second = w(10.0, 10.6, "the"), w(10.8, 11.4, "the")
    assert says_it_twice([first], [second])


def test_one_word_straddling_a_cut_is_not_a_stammer():
    """Trimming here would delete the word from the edit entirely. Matching text
    cannot tell the two cases apart; word identity can."""
    straddling = w(105.80, 106.86, "likewise")
    assert not says_it_twice([straddling], [straddling])


def test_different_words_are_not_a_stammer():
    assert not says_it_twice([w(0, 1, "the")], [w(1, 2, "indicator")])


def test_empty_sides_are_safe():
    assert not says_it_twice([], [w(0, 1, "x")])
    assert not says_it_twice([w(0, 1, "x")], [])
