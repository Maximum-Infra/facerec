import time

import httpx

from app.actions import ActionDispatcher


class FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://actions.test/facerec/event")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("rejected", request=request, response=response)


class FakeClient:
    calls: list[dict] = []
    status_code = 200

    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self.status_code)


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached before timeout")


def test_disabled_dispatcher_does_not_queue() -> None:
    dispatcher = ActionDispatcher(False, "", "", 1.0)
    dispatcher.start()
    assert dispatcher.enqueue({"event_type": "recognized"}) is False
    assert dispatcher.snapshot()["state"] == "disabled"


def test_enabled_dispatcher_requires_url_and_token() -> None:
    dispatcher = ActionDispatcher(True, "", "", 1.0)
    dispatcher.start()
    assert dispatcher.snapshot()["state"] == "misconfigured"
    assert dispatcher.enqueue({"event_type": "unknown"}) is False


def test_dispatches_recognition_event_with_token() -> None:
    FakeClient.calls = []
    FakeClient.status_code = 200
    dispatcher = ActionDispatcher(
        True,
        "http://actions.test/facerec/event",
        "secret-token",
        1.0,
        client_factory=FakeClient,
    )
    dispatcher.start()
    try:
        event = {"event_type": "recognized", "event_id": 42, "employee": "Max"}
        assert dispatcher.enqueue(event) is True
        wait_until(lambda: len(FakeClient.calls) == 1)
        call = FakeClient.calls[0]
        assert call["headers"] == {"X-FaceRec-Token": "secret-token"}
        assert call["json"] == event
        wait_until(lambda: dispatcher.snapshot()["last_success_at"] is not None)
        assert "token" not in dispatcher.snapshot()
    finally:
        dispatcher.stop()


def test_cooldown_response_is_recorded_as_suppressed_not_retried() -> None:
    FakeClient.calls = []
    FakeClient.status_code = 429
    dispatcher = ActionDispatcher(
        True,
        "http://actions.test/facerec/event",
        "secret-token",
        1.0,
        client_factory=FakeClient,
    )
    dispatcher.start()
    try:
        assert dispatcher.enqueue({"event_type": "unknown", "event_id": 43}) is True
        wait_until(lambda: dispatcher.snapshot()["last_suppressed_at"] is not None)
        assert len(FakeClient.calls) == 1
        assert dispatcher.snapshot()["last_error"] is None
    finally:
        dispatcher.stop()
