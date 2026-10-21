import pytest

from netgaf.evaluation import binary_metrics


def test_metrics_against_known_confusion_matrix():
    scores = [0.9, 0.8, 0.7, 0.1]
    metrics = binary_metrics([1, 0, 1, 0], scores, 0.75)
    assert (metrics["tp"], metrics["fp"], metrics["tn"], metrics["fn"]) == (1, 1, 1, 1)
    assert metrics["precision"] == metrics["recall"] == metrics["f1"] == metrics["fpr"] == 0.5
    assert metrics["average_precision"] == pytest.approx((1 + 2 / 3) / 2)
    assert metrics["pr_auc"] == pytest.approx(19 / 24)


def test_score_ties_and_undefined_metrics():
    metrics = binary_metrics([1, 0, 1, 0], [1, 1, 1, 1], 1)
    assert metrics["tp"] == 0
    assert metrics["average_precision"] == 0.5
    assert metrics["precision"] is None
    assert metrics["recall"] == 0
    normal_only = binary_metrics([0, 0], [0.2, 0.3], 0.5)
    assert normal_only["recall"] is None
    assert normal_only["pr_auc"] is None


def test_nonbinary_labels_are_rejected():
    with pytest.raises(ValueError):
        binary_metrics([0, 3], [0.1, 0.8], 0.5)
