from types import SimpleNamespace

from app.anti_spoof import evaluate_test, summarize_tests


def test_evaluation_matrix():
    assert evaluate_test("live", "pass") == "live_accepted"
    assert evaluate_test("live", "fail") == "live_rejected"
    assert evaluate_test("print", "fail") == "attack_detected"
    assert evaluate_test("phone_photo", "pass") == "missed_attack"
    assert evaluate_test("phone_video", "inconclusive") == "inconclusive"


def test_summary_excludes_inconclusive_from_rates():
    tests = [
        SimpleNamespace(status="completed", test_type="live", evaluation="live_accepted"),
        SimpleNamespace(status="completed", test_type="live", evaluation="live_rejected"),
        SimpleNamespace(status="completed", test_type="print", evaluation="attack_detected"),
        SimpleNamespace(status="completed", test_type="phone_photo", evaluation="missed_attack"),
        SimpleNamespace(status="completed", test_type="phone_video", evaluation="inconclusive"),
    ]
    report = summarize_tests(tests)
    assert report["outcomes"]["live_accept_rate"] == 0.5
    assert report["outcomes"]["attack_detection_rate"] == 0.5
    assert report["tests"]["inconclusive"] == 1
    assert report["attack_breakdown"]["phone_video"]["inconclusive"] == 1
