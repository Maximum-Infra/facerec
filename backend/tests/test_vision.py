import numpy as np
import pytest

from app.vision import VisionEngine, best_identity, identity_ranking


def test_best_identity_requires_threshold_and_margin():
    probe = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    templates = {
        1: {"id": 1, "name": "Alice", "embeddings": [np.array([0.9, 0.1, 0.0])]},
        2: {"id": 2, "name": "Bob", "embeddings": [np.array([0.5, 0.5, 0.0])]},
    }
    employee, score, score_margin = best_identity(probe, templates, threshold=0.6, margin=0.1)
    assert employee["name"] == "Alice"
    assert score == pytest.approx(0.9)
    assert score_margin == pytest.approx(0.4)


def test_best_identity_rejects_ambiguous_match():
    probe = np.array([1.0, 0.0], dtype=np.float32)
    templates = {
        1: {"id": 1, "name": "Alice", "embeddings": [np.array([0.8, 0.2])]},
        2: {"id": 2, "name": "Bob", "embeddings": [np.array([0.77, 0.23])]},
    }
    employee, score, score_margin = best_identity(probe, templates, threshold=0.6, margin=0.05)
    assert employee is None
    assert score == pytest.approx(0.8)
    assert score_margin < 0.05


def test_blur_score_handles_empty_roi():
    assert VisionEngine.blur_score(np.array([], dtype=np.uint8)) == 0.0


def test_identity_ranking_keeps_raw_candidate_for_rejected_probe():
    probe = np.array([1.0, 0.0], dtype=np.float32)
    templates = {
        1: {"id": 1, "name": "Alice", "embeddings": [np.array([0.42, 0.58])]},
        2: {"id": 2, "name": "Bob", "embeddings": [np.array([0.30, 0.70])]},
    }
    employee, best, runner_up, score_margin = identity_ranking(probe, templates)
    assert employee["name"] == "Alice"
    assert best == pytest.approx(0.42)
    assert runner_up == pytest.approx(0.30)
    assert score_margin == pytest.approx(0.12)
