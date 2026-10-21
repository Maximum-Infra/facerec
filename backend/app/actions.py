import queue
import threading
from datetime import datetime, timezone
from typing import Callable

import httpx


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActionDispatcher:
    """Deliver recognition actions without blocking the camera processing thread."""

    def __init__(
        self,
        enabled: bool,
        url: str,
        token: str,
        timeout_seconds: float,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self.enabled = enabled
        self.url = url.strip()
        self.token = token.strip()
        self.timeout_seconds = max(1.0, timeout_seconds)
        self.client_factory = client_factory
        self.events: queue.Queue[dict] = queue.Queue(maxsize=32)
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock = threading.RLock()
        self.status = {
            "enabled": enabled,
            "state": "disabled" if not enabled else "starting",
            "url": self.url or None,
            "queued": 0,
            "last_success_at": None,
            "last_suppressed_at": None,
            "last_error": None,
        }

    def start(self) -> None:
        if not self.enabled:
            return
        if not self.url or not self.token:
            with self.lock:
                self.status.update(
                    state="misconfigured",
                    last_error="Webhook URL and token are required when actions are enabled",
                )
            return
        if not self.url.startswith(("http://", "https://")):
            with self.lock:
                self.status.update(
                    state="misconfigured",
                    last_error="Webhook URL must use http:// or https://",
                )
            return
        self.thread = threading.Thread(
            target=self._run,
            name="facerec-actions",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=self.timeout_seconds + 2.0)

    def snapshot(self) -> dict:
        with self.lock:
            result = dict(self.status)
            result["queued"] = self.events.qsize()
            return result

    def enqueue(self, event: dict) -> bool:
        if not self.enabled or self.status["state"] == "misconfigured":
            return False
        if event.get("event_type") not in {"recognized", "unknown"}:
            return False
        try:
            self.events.put_nowait(dict(event))
            with self.lock:
                self.status["queued"] = self.events.qsize()
            return True
        except queue.Full:
            with self.lock:
                self.status["last_error"] = "Action queue is full; newest event was dropped"
            return False

    def _run(self) -> None:
        with self.lock:
            self.status["state"] = "running"
            self.status["last_error"] = None
        while not self.stop_event.is_set():
            try:
                event = self.events.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._deliver_with_retry(event)
            finally:
                self.events.task_done()
                with self.lock:
                    self.status["queued"] = self.events.qsize()

    def _deliver_with_retry(self, event: dict) -> None:
        for attempt in range(1, 4):
            try:
                with self.client_factory(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        self.url,
                        headers={"X-FaceRec-Token": self.token},
                        json=event,
                    )
                if response.status_code == 429:
                    with self.lock:
                        self.status.update(
                            last_suppressed_at=utcnow_iso(),
                            last_error=None,
                        )
                    return
                response.raise_for_status()
                with self.lock:
                    self.status.update(
                        last_success_at=utcnow_iso(),
                        last_error=None,
                    )
                return
            except httpx.HTTPStatusError as exc:
                # Authentication and other client errors will not improve on retry.
                if 400 <= exc.response.status_code < 500:
                    with self.lock:
                        self.status["last_error"] = (
                            f"Webhook rejected event with HTTP {exc.response.status_code}"
                        )
                    return
                error = f"Webhook HTTP error: {exc.response.status_code}"
            except httpx.HTTPError as exc:
                error = f"Webhook delivery failed: {exc}"
            except Exception as exc:
                error = f"Webhook delivery failed: {exc}"

            if attempt < 3 and not self.stop_event.wait(0.5 * attempt):
                continue
            with self.lock:
                self.status["last_error"] = error
            return
