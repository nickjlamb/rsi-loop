from evaluator.metrics import Confusion, accuracy, balanced_accuracy, confusion


def test_confusion_counts():
    c = confusion([("High Strain", "High Strain"), ("High Strain", "Safe"), ("Safe", "Safe"), ("Safe", "High Strain"), ("Safe", "Safe")])
    assert (c.tp, c.fn, c.tn, c.fp) == (1, 1, 2, 1)
    assert c.accuracy == 3 / 5
    assert c.recall == 1 / 2 and c.specificity == 2 / 3
    assert c.balanced_accuracy == 0.5 * (1 / 2 + 2 / 3)
    assert c.prevalence == 2 / 5


def test_balanced_accuracy_is_not_accuracy_under_imbalance():
    truths = ["Safe"] * 90 + ["High Strain"] * 10
    preds = ["Safe"] * 100
    assert accuracy(truths, preds) == 0.9
    assert balanced_accuracy(truths, preds) == 0.5


def test_empty_class_contributes_half():
    assert Confusion(tp=0, tn=5, fp=0, fn=0).balanced_accuracy == 0.75


def test_invalid_predictions_are_errors_not_negatives():
    c = confusion([("Safe", None), ("High Strain", None), ("Safe", "Safe"), ("High Strain", "High Strain")])
    assert (c.tp, c.tn, c.fp, c.fn, c.err_pos, c.err_neg) == (1, 1, 0, 0, 1, 1)
    assert c.n == 4 and c.accuracy == 0.5 and c.errors == 2
    assert c.recall == 0.5 and c.specificity == 0.5 and c.balanced_accuracy == 0.5
    assert confusion([("Safe", "Fine")]).err_neg == 1
