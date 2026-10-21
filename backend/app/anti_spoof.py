from collections import Counter


ATTACK_TYPES = {"print", "phone_photo", "phone_video"}


def evaluate_test(test_type: str, outcome: str) -> str:
    if outcome == "inconclusive":
        return "inconclusive"
    if test_type == "live":
        return "live_accepted" if outcome == "pass" else "live_rejected"
    return "missed_attack" if outcome == "pass" else "attack_detected"


def summarize_tests(tests: list) -> dict:
    completed = [test for test in tests if test.status == "completed"]
    evaluations = Counter(test.evaluation for test in completed if test.evaluation)
    attacks = [test for test in completed if test.test_type in ATTACK_TYPES]
    live = [test for test in completed if test.test_type == "live"]
    attack_decisions = [test for test in attacks if test.evaluation != "inconclusive"]
    live_decisions = [test for test in live if test.evaluation != "inconclusive"]

    breakdown = {}
    for test_type in ("print", "phone_photo", "phone_video"):
        group = [test for test in attacks if test.test_type == test_type]
        breakdown[test_type] = {
            "total": len(group),
            "detected": sum(test.evaluation == "attack_detected" for test in group),
            "missed": sum(test.evaluation == "missed_attack" for test in group),
            "inconclusive": sum(test.evaluation == "inconclusive" for test in group),
        }

    return {
        "tests": {
            "total": len(tests),
            "completed": len(completed),
            "live": len(live),
            "attacks": len(attacks),
            "inconclusive": evaluations["inconclusive"],
        },
        "outcomes": {
            "live_accepted": evaluations["live_accepted"],
            "live_rejected": evaluations["live_rejected"],
            "attack_detected": evaluations["attack_detected"],
            "missed_attack": evaluations["missed_attack"],
            "live_accept_rate": (
                round(evaluations["live_accepted"] / len(live_decisions), 4)
                if live_decisions else None
            ),
            "attack_detection_rate": (
                round(evaluations["attack_detected"] / len(attack_decisions), 4)
                if attack_decisions else None
            ),
        },
        "attack_breakdown": breakdown,
        "limitations": [
            "RGB motion challenges are experimental and are not production-grade liveness.",
            "A pass never opens a door; FaceRec remains in shadow mode.",
            "No face images or video are retained as test evidence.",
        ],
    }
