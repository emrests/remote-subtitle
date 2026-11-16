from rsub.speaker import split_speakers


def test_single():
    assert split_speakers("Arthur: Hello my friend!") == [("Arthur", "Hello my friend!")]


def test_no_speaker():
    assert split_speakers("We need to move.") == [(None, "We need to move.")]


def test_four_words_is_not_a_name():
    assert split_speakers("Dutch van der Linde: Arthur!") == [(None, "Dutch van der Linde: Arthur!")]


def test_three_words():
    assert split_speakers("Uncle Bob Jr: Hey") == [("Uncle Bob Jr", "Hey")]


def test_two_speakers():
    assert split_speakers("Arthur: Ready? Sadie: Always.") == [("Arthur", "Ready?"), ("Sadie", "Always.")]


def test_text_before_first_speaker():
    assert split_speakers("...and then. Arthur: Go!") == [(None, "...and then."), ("Arthur", "Go!")]


def test_not_speakers():
    assert split_speakers("WARNING: Low health") == [(None, "WARNING: Low health")]
    assert split_speakers("Meet me at 10:30 tonight") == [(None, "Meet me at 10:30 tonight")]


def test_empty():
    assert split_speakers("") == []
