from rsub.cleanup import clean


def test_corrects_one_letter_ocr_errors():
    assert clean("Of couxse I will.", set())[0] == "Of course I will."
    assert clean("Get to t cliff edg", set())[0] == "Get to t cliff edge"


def test_scores():
    assert clean("We got this. We're safe.", set())[1] == 1.0
    assert 0.6 <= clean("Get to t cliff edg", set())[1] < 1.0


def test_garbage_scores_low():
    for g in ("Get t he Cli j 2LIÇJ3", "e!jîî", "2LİÇJ3", "lşğ ıüç"):
        assert clean(g, set())[1] < 0.6, g


def test_names_untouched():
    text, score = clean("Tell Dutch and Hosea to meet me in Valentine.", set())
    assert text == "Tell Dutch and Hosea to meet me in Valentine." and score == 1.0
    assert clean("Mierda, we're high up here.", set())[0] == "Mierda, we're high up here."
    assert clean("Hosea knows.", {"Hosea"})[0] == "Hosea knows."


def test_slang_and_contractions_known():
    assert clean("Ain't gonna happen, compadre. I reckon not.", set())[1] == 1.0


def test_keeps_ocr_box_attributes():
    from rsub.ocr import OcrText
    t = OcrText("Of couxse.")
    t.box, t.lines = (1, 2, 3, 4), 1
    out, _ = clean(t, set())
    assert out == "Of course." and out.box == (1, 2, 3, 4) and out.lines == 1
