from types import SimpleNamespace

from app.calibration import classify_attempt, summarize_attempts


def attempt(expected_type, result, score, employee="Alice", status="captured"):
    return SimpleNamespace(
        status=status,
        expected_type=expected_type,
        result=result,
        similarity=score,
        expected_employee_name=employee,
    )


def test_classify_calibration_outcomes():
    assert classify_attempt("genuine", 1, "recognized", 1) == "true_accept"
    assert classify_attempt("genuine", 1, "unknown", None) == "false_reject"
    assert classify_attempt("genuine", 1, "recognized", 2) == "wrong_identity"
    assert classify_attempt("impostor", None, "unknown", None) == "true_reject"
    assert classify_attempt("impostor", None, "no_decision", None) == "true_reject"
    assert classify_attempt("impostor", None, "recognized", 2) == "false_accept"
    assert classify_attempt("genuine", 1, "no_decision", None) == "false_reject"


def test_report_recommends_separated_threshold():
    attempts = [
        attempt("genuine", "true_accept", 0.72),
        attempt("genuine", "true_accept", 0.75),
        attempt("genuine", "true_accept", 0.81),
        attempt("impostor", "true_reject", 0.28, "Unknown"),
        attempt("impostor", "true_reject", 0.32, "Unknown"),
        attempt("impostor", "true_reject", 0.36, "Unknown"),
    ]
    report = summarize_attempts(attempts, 0.45)
    assert report["outcomes"]["false_reject_rate"] == 0
    assert report["outcomes"]["false_accept_rate"] == 0
    assert report["recommendation"]["ready"] is True
    assert report["recommendation"]["threshold"] == 0.54
