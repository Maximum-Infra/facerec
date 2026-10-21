from collections import defaultdict
from statistics import mean, median
from typing import Iterable


def classify_attempt(
    expected_type: str,
    expected_employee_id: int | None,
    observed_event_type: str,
    observed_employee_id: int | None,
) -> str:
    if expected_type == "impostor":
        return "true_reject" if observed_event_type in {"unknown", "no_decision"} else "false_accept"
    if observed_event_type in {"unknown", "no_decision"}:
        return "false_reject"
    if observed_employee_id == expected_employee_id:
        return "true_accept"
    return "wrong_identity"


def _score_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "minimum": None, "maximum": None, "mean": None, "median": None}
    return {
        "count": len(values),
        "minimum": round(min(values), 4),
        "maximum": round(max(values), 4),
        "mean": round(mean(values), 4),
        "median": round(median(values), 4),
    }


def summarize_attempts(attempts: Iterable, current_threshold: float) -> dict:
    captured = [attempt for attempt in attempts if attempt.status == "captured"]
    genuine = [attempt for attempt in captured if attempt.expected_type == "genuine"]
    impostor = [attempt for attempt in captured if attempt.expected_type == "impostor"]

    true_accepts = sum(attempt.result == "true_accept" for attempt in genuine)
    false_rejects = sum(attempt.result in {"false_reject", "wrong_identity"} for attempt in genuine)
    wrong_identities = sum(attempt.result == "wrong_identity" for attempt in genuine)
    true_rejects = sum(attempt.result == "true_reject" for attempt in impostor)
    false_accepts = sum(attempt.result == "false_accept" for attempt in impostor)

    genuine_scores = [float(a.similarity) for a in genuine if a.similarity is not None]
    impostor_scores = [float(a.similarity) for a in impostor if a.similarity is not None]
    recommendation = {
        "ready": False,
        "threshold": None,
        "reason": "At least 3 genuine and 3 impostor attempts are required.",
    }
    if len(genuine_scores) >= 3 and len(impostor_scores) >= 3:
        min_genuine = min(genuine_scores)
        max_impostor = max(impostor_scores)
        if max_impostor < min_genuine:
            recommendation = {
                "ready": True,
                "threshold": round((max_impostor + min_genuine) / 2, 4),
                "reason": "Midpoint between the highest impostor and lowest genuine score.",
            }
        else:
            recommendation = {
                "ready": False,
                "threshold": None,
                "reason": "Genuine and impostor scores overlap; collect more evidence or improve capture conditions.",
            }

    per_user: dict[str, dict] = defaultdict(lambda: {"attempts": 0, "accepted": 0, "rejected": 0})
    for attempt in genuine:
        name = attempt.expected_employee_name or "Deleted employee"
        per_user[name]["attempts"] += 1
        if attempt.result == "true_accept":
            per_user[name]["accepted"] += 1
        else:
            per_user[name]["rejected"] += 1
    for values in per_user.values():
        values["false_reject_rate"] = round(values["rejected"] / values["attempts"], 4)

    return {
        "attempts": {
            "total": len(captured),
            "genuine": len(genuine),
            "impostor": len(impostor),
            "armed": sum(attempt.status == "armed" for attempt in attempts),
            "cancelled": sum(attempt.status == "cancelled" for attempt in attempts),
        },
        "outcomes": {
            "true_accepts": true_accepts,
            "false_rejects": false_rejects,
            "wrong_identities": wrong_identities,
            "true_rejects": true_rejects,
            "false_accepts": false_accepts,
            "false_reject_rate": round(false_rejects / len(genuine), 4) if genuine else None,
            "false_accept_rate": round(false_accepts / len(impostor), 4) if impostor else None,
        },
        "scores": {
            "genuine": _score_stats(genuine_scores),
            "impostor": _score_stats(impostor_scores),
        },
        "per_user": dict(sorted(per_user.items())),
        "current_threshold": current_threshold,
        "recommendation": recommendation,
    }
