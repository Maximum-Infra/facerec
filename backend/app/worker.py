import os
import threading
import time
from collections import Counter, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Generator

import cv2
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .actions import ActionDispatcher
from .config import get_settings
from .vision import FaceObservation, VisionEngine, identity_ranking

settings = get_settings()


class EnrollmentStart(BaseModel):
    employee_id: int
    employee_name: str


class AntiSpoofStart(BaseModel):
    test_id: int
    test_type: str
    subject_label: str
    expected_employee_id: int | None = None
    expected_employee_name: str | None = None
    sequence: list[str]


class RecognitionRuntime:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.preview_jpeg: bytes | None = None
        self.preview_version = 0
        self.templates: dict[int, dict] = {}
        self.recent_matches: deque[int | None] = deque(maxlen=5)
        self.last_event_by_key: dict[str, float] = {}
        self.active_event_key: str | None = None
        self.last_template_refresh = 0.0
        self.last_sample_at = 0.0
        self.enrollment: dict | None = None
        self.anti_spoof: dict | None = None
        self.action_dispatcher = ActionDispatcher(
            enabled=settings.action_webhook_enabled,
            url=settings.action_webhook_url,
            token=settings.action_webhook_token,
            timeout_seconds=settings.action_webhook_timeout_seconds,
        )
        self.status = {
            "state": "starting",
            "camera_connected": False,
            "model_ready": False,
            "last_frame_at": None,
            "processed_fps": 0.0,
            "template_count": 0,
            "employee_count": 0,
            "message": "Starting recognition worker",
            "error": None,
        }

    def start(self) -> None:
        self.action_dispatcher.start()
        self.thread = threading.Thread(target=self.run, name="facerec-recognition", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=8)
        self.action_dispatcher.stop()

    def snapshot_status(self) -> dict:
        with self.lock:
            result = dict(self.status)
            result["enrollment"] = self.enrollment_public()
            result["anti_spoof"] = self.anti_spoof_public()
            result["action_webhook"] = self.action_dispatcher.snapshot()
            return result

    def enrollment_public(self) -> dict:
        if not self.enrollment:
            return {"active": False, "captured": 0, "required": settings.enrollment_samples}
        return {
            "active": True,
            "employee_id": self.enrollment["employee_id"],
            "employee_name": self.enrollment["employee_name"],
            "captured": len(self.enrollment["embeddings"]),
            "required": settings.enrollment_samples,
            "message": self.enrollment["message"],
        }

    def start_enrollment(self, payload: EnrollmentStart) -> dict:
        with self.lock:
            if not self.status["model_ready"] or not self.status["camera_connected"]:
                raise HTTPException(status_code=409, detail="Camera and models must be ready")
            if self.enrollment:
                raise HTTPException(status_code=409, detail="Another enrollment is already active")
            if self.anti_spoof:
                raise HTTPException(status_code=409, detail="An anti-spoof challenge is active")
            self.enrollment = {
                "employee_id": payload.employee_id,
                "employee_name": payload.employee_name,
                "embeddings": [],
                "quality_scores": [],
                "message": "Look directly at the camera",
            }
            self.recent_matches.clear()
            self.active_event_key = None
            self.last_sample_at = 0.0
            return self.enrollment_public()

    def cancel_enrollment(self) -> dict:
        with self.lock:
            self.enrollment = None
            self.status["message"] = "Enrollment cancelled"
            return self.enrollment_public()

    def anti_spoof_public(self) -> dict:
        challenge = self.anti_spoof
        if not challenge:
            return {"active": False}
        sequence = challenge["sequence"]
        index = challenge["step_index"]
        return {
            "active": True,
            "test_id": challenge["test_id"],
            "test_type": challenge["test_type"],
            "subject_label": challenge["subject_label"],
            "expected_employee_name": challenge["expected_employee_name"],
            "sequence": sequence,
            "current_step_index": index,
            "current_step": sequence[index] if index < len(sequence) else None,
            "completed_steps": list(challenge["completed_steps"]),
            "confirmations": challenge["confirmations"],
            "required_confirmations": settings.anti_spoof_confirm_frames,
            "prompt": challenge["prompt"],
            "elapsed_seconds": round(time.monotonic() - challenge["started_at"], 1),
            "finishing": challenge["pending_completion"] is not None,
        }

    def start_anti_spoof(self, payload: AntiSpoofStart) -> dict:
        allowed_steps = {"center", "turn_left", "turn_right", "center_again", "move_closer"}
        if not payload.sequence or any(step not in allowed_steps for step in payload.sequence):
            raise HTTPException(status_code=422, detail="Invalid anti-spoof challenge sequence")
        with self.lock:
            if not self.status["model_ready"] or not self.status["camera_connected"]:
                raise HTTPException(status_code=409, detail="Camera and models must be ready")
            if self.enrollment:
                raise HTTPException(status_code=409, detail="Finish enrollment before testing")
            if self.anti_spoof:
                raise HTTPException(status_code=409, detail="Another anti-spoof challenge is active")
            now = time.monotonic()
            self.anti_spoof = {
                "test_id": payload.test_id,
                "test_type": payload.test_type,
                "subject_label": payload.subject_label,
                "expected_employee_id": payload.expected_employee_id,
                "expected_employee_name": payload.expected_employee_name,
                "sequence": payload.sequence,
                "step_index": 0,
                "confirmations": 0,
                "completed_steps": [],
                "started_at": now,
                "step_started_at": now,
                "prompt": self.challenge_prompt(payload.sequence[0]),
                "baseline_embedding": None,
                "baseline_width": None,
                "baseline_pose": None,
                "continuity_min": 1.0,
                "wrong_identity_frames": 0,
                "metrics": {"steps": []},
                "pending_completion": None,
                "last_delivery_attempt": 0.0,
            }
            self.recent_matches.clear()
            self.active_event_key = None
            self.status["message"] = self.anti_spoof["prompt"]
            return self.anti_spoof_public()

    def cancel_anti_spoof(self) -> dict:
        with self.lock:
            self.anti_spoof = None
            self.status["message"] = "Anti-spoof test cancelled"
            return {"active": False}

    def run(self) -> None:
        try:
            vision = VisionEngine(
                settings.yunet_model,
                settings.sface_model,
                settings.detection_score_threshold,
                settings.min_face_width,
                settings.min_blur_score,
            )
        except Exception as exc:
            with self.lock:
                self.status.update(state="error", error=str(exc), message="Model initialization failed")
            return

        with self.lock:
            self.status.update(model_ready=True, state="connecting", message="Connecting to camera")

        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;{settings.rtsp_transport}|stimeout;5000000"
        )
        self.refresh_templates(force=True)
        interval = 1.0 / max(0.5, settings.inference_fps)

        while not self.stop_event.is_set():
            capture = cv2.VideoCapture(settings.rtsp_url, cv2.CAP_FFMPEG)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not capture.isOpened():
                self.camera_failure("Unable to open RTSP stream")
                capture.release()
                self.stop_event.wait(2)
                continue

            with self.lock:
                self.status.update(
                    camera_connected=True, state="running", error=None, message="Camera connected"
                )

            last_processed = 0.0
            fps_window_start = time.monotonic()
            processed_frames = 0
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok or frame is None:
                    self.camera_failure("RTSP frame read failed; reconnecting")
                    break

                now = time.monotonic()
                if now - last_processed < interval:
                    continue
                last_processed = now

                frame = self.resize_for_processing(frame)
                self.process_frame(vision, frame, now)
                processed_frames += 1
                elapsed = now - fps_window_start
                if elapsed >= 2.0:
                    with self.lock:
                        self.status["processed_fps"] = round(processed_frames / elapsed, 1)
                    processed_frames = 0
                    fps_window_start = now

                self.refresh_templates()
            capture.release()
            self.stop_event.wait(1)

    @staticmethod
    def resize_for_processing(frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        if width <= settings.process_width:
            return frame
        scale = settings.process_width / width
        return cv2.resize(frame, (settings.process_width, int(height * scale)))

    def camera_failure(self, message: str) -> None:
        with self.lock:
            self.status.update(
                camera_connected=False, state="reconnecting", message=message, error=message
            )

    def process_frame(self, vision: VisionEngine, frame: np.ndarray, now: float) -> None:
        try:
            observations = vision.detect(frame)
            guidance = vision.quality_message(observations)
            best_name = None
            best_score = None
            candidate_employee = None
            runner_up_score = None
            score_margin = None

            with self.lock:
                enrollment_active = self.enrollment is not None
                anti_spoof_active = self.anti_spoof is not None

            if anti_spoof_active:
                guidance, best_name, best_score = self.process_anti_spoof(
                    vision, frame, observations, guidance, now
                )
            elif enrollment_active:
                guidance = self.process_enrollment(vision, frame, observations, guidance, now)
            elif guidance == "Ready" and self.templates:
                probe = vision.embedding(frame, observations[0])
                candidate_employee, best_score, runner_up_score, score_margin = identity_ranking(
                    probe, self.templates
                )
                employee = candidate_employee
                if best_score < settings.match_threshold or score_margin < settings.match_margin:
                    employee = None
                candidate = employee["id"] if employee else None
                self.recent_matches.append(candidate)
                stable_id = self.stable_match()
                if stable_id is not None and stable_id == candidate:
                    matched = self.templates.get(stable_id)
                    if matched:
                        best_name = matched["name"]
                        guidance = f"Recognized: {best_name}"
                        self.emit_event(
                            "recognized",
                            matched["id"],
                            matched["name"],
                            best_score,
                            guidance,
                            candidate_employee,
                            runner_up_score,
                            score_margin,
                            observations[0],
                        )
                elif len(self.recent_matches) == self.recent_matches.maxlen and all(
                    item is None for item in list(self.recent_matches)[-3:]
                ):
                    guidance = "Unknown"
                    self.emit_event(
                        "unknown",
                        None,
                        None,
                        best_score,
                        guidance,
                        candidate_employee,
                        runner_up_score,
                        score_margin,
                        observations[0],
                    )
            elif guidance == "Ready":
                # Detection can be ready before anyone has been enrolled. Do not
                # create meaningless zero-score unknown events in that state.
                self.recent_matches.clear()
            else:
                self.recent_matches.clear()
                if guidance == "No face":
                    # A new face arrival may create one new decision event.
                    self.active_event_key = None

            annotated = self.annotate(frame, observations, guidance, best_name, best_score)
            ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
            with self.lock:
                if ok:
                    self.preview_jpeg = jpeg.tobytes()
                    self.preview_version += 1
                self.status.update(
                    last_frame_at=datetime.now(timezone.utc).isoformat(), message=guidance
                )
                if not self.anti_spoof or self.anti_spoof["pending_completion"] is None:
                    self.status["error"] = None
        except Exception as exc:
            with self.lock:
                self.status.update(message="Frame processing error", error=str(exc))

    @staticmethod
    def challenge_prompt(step: str) -> str:
        return {
            "center": "Challenge: face forward",
            "turn_left": "Challenge: turn toward your left shoulder",
            "turn_right": "Challenge: turn toward your right shoulder",
            "center_again": "Challenge: face forward again",
            "move_closer": "Challenge: move closer",
        }[step]

    @staticmethod
    def pose_offset(observation: FaceObservation) -> float:
        # YuNet: right eye, left eye and nose x coordinates follow the bounding box.
        right_eye_x = float(observation.face[4])
        left_eye_x = float(observation.face[6])
        nose_x = float(observation.face[8])
        eye_distance = max(abs(left_eye_x - right_eye_x), 1.0)
        return (nose_x - ((right_eye_x + left_eye_x) / 2.0)) / eye_distance

    def process_anti_spoof(
        self,
        vision: VisionEngine,
        frame: np.ndarray,
        observations: list[FaceObservation],
        guidance: str,
        now: float,
    ) -> tuple[str, str | None, float | None]:
        with self.lock:
            challenge = self.anti_spoof
        if challenge is None:
            return guidance, None, None

        if challenge["pending_completion"] is not None:
            self.deliver_anti_spoof_completion(now)
            with self.lock:
                current = self.anti_spoof
            return (
                current["prompt"] if current else "Challenge result saved",
                None,
                None,
            )

        step = challenge["sequence"][challenge["step_index"]]
        if now - challenge["step_started_at"] > settings.anti_spoof_step_timeout_seconds:
            self.finish_anti_spoof(
                "fail",
                f"Timed out during {step.replace('_', ' ')}",
                now,
            )
            return "Challenge failed: step timed out", None, None

        if guidance != "Ready":
            with self.lock:
                if self.anti_spoof:
                    self.anti_spoof["confirmations"] = 0
                    self.anti_spoof["prompt"] = f"Challenge: {guidance.lower()}"
            return f"Challenge: {guidance}", None, None

        observation = observations[0]
        probe = vision.embedding(frame, observation)
        candidate, score, runner_up, margin = identity_ranking(probe, self.templates)
        accepted = (
            candidate
            if candidate
            and score >= settings.match_threshold
            and margin >= settings.match_margin
            else None
        )
        best_name = candidate["name"] if candidate else None

        baseline = challenge["baseline_embedding"]
        continuity = float(np.dot(probe, baseline)) if baseline is not None else 1.0
        if baseline is not None:
            with self.lock:
                if self.anti_spoof:
                    self.anti_spoof["continuity_min"] = min(
                        self.anti_spoof["continuity_min"], continuity
                    )
            if continuity < settings.anti_spoof_continuity_threshold:
                with self.lock:
                    if self.anti_spoof:
                        self.anti_spoof["wrong_identity_frames"] += 1
                        wrong_frames = self.anti_spoof["wrong_identity_frames"]
                    else:
                        wrong_frames = 0
                if wrong_frames >= settings.anti_spoof_confirm_frames:
                    self.finish_anti_spoof("fail", "Face continuity was lost", now)
                    return "Challenge failed: face changed", best_name, score
                return "Challenge: keep the same face in view", best_name, score
            with self.lock:
                if self.anti_spoof:
                    self.anti_spoof["wrong_identity_frames"] = 0

        expected_id = challenge["expected_employee_id"]
        if (
            expected_id is not None
            and baseline is None
            and (accepted is None or accepted["id"] != expected_id)
        ):
            with self.lock:
                if self.anti_spoof:
                    self.anti_spoof["confirmations"] = 0
                    self.anti_spoof["prompt"] = "Challenge: expected identity not confirmed"
            return "Challenge: expected identity not confirmed", best_name, score

        pose = self.pose_offset(observation)
        baseline_pose = challenge["baseline_pose"]
        baseline_width = challenge["baseline_width"]
        condition = False
        measurement = {}
        if step == "center":
            condition = abs(pose) <= 0.28
            measurement = {"pose_offset": round(pose, 4), "face_width": observation.width}
        elif step == "turn_left":
            delta = pose - float(baseline_pose)
            condition = delta >= settings.anti_spoof_turn_delta
            measurement = {"pose_delta": round(delta, 4)}
        elif step == "turn_right":
            delta = pose - float(baseline_pose)
            condition = delta <= -settings.anti_spoof_turn_delta
            measurement = {"pose_delta": round(delta, 4)}
        elif step == "center_again":
            delta = pose - float(baseline_pose)
            condition = abs(delta) <= settings.anti_spoof_turn_delta
            measurement = {"pose_delta": round(delta, 4)}
        elif step == "move_closer":
            ratio = observation.width / max(float(baseline_width), 1.0)
            condition = ratio >= settings.anti_spoof_closer_ratio
            measurement = {"face_width": observation.width, "width_ratio": round(ratio, 4)}

        with self.lock:
            if not self.anti_spoof:
                return guidance, best_name, score
            self.anti_spoof["confirmations"] = (
                self.anti_spoof["confirmations"] + 1 if condition else 0
            )
            confirmations = self.anti_spoof["confirmations"]
            self.anti_spoof["prompt"] = self.challenge_prompt(step)

        if confirmations < settings.anti_spoof_confirm_frames:
            return self.challenge_prompt(step), best_name, score

        elapsed = round(now - challenge["step_started_at"], 2)
        with self.lock:
            if not self.anti_spoof:
                return guidance, best_name, score
            current = self.anti_spoof
            if step == "center":
                current["baseline_embedding"] = probe.copy()
                current["baseline_width"] = observation.width
                current["baseline_pose"] = pose
                current["metrics"].update(
                    baseline_face_width=observation.width,
                    baseline_pose_offset=round(pose, 4),
                    initial_candidate=best_name,
                    initial_similarity=round(score, 4),
                    initial_runner_up=round(runner_up, 4),
                    initial_margin=round(margin, 4),
                )
            current["metrics"]["steps"].append(
                {"step": step, "elapsed_seconds": elapsed, **measurement}
            )
            current["completed_steps"].append(step)
            current["step_index"] += 1
            current["confirmations"] = 0
            current["step_started_at"] = now
            complete = current["step_index"] >= len(current["sequence"])
            if not complete:
                current["prompt"] = self.challenge_prompt(
                    current["sequence"][current["step_index"]]
                )

        if complete:
            self.finish_anti_spoof("pass", "Completed the randomized RGB motion challenge", now)
            return "Challenge passed (experimental RGB)", best_name, score
        return self.anti_spoof_public()["prompt"], best_name, score

    def finish_anti_spoof(self, outcome: str, reason: str, now: float) -> None:
        with self.lock:
            if not self.anti_spoof or self.anti_spoof["pending_completion"] is not None:
                return
            challenge = self.anti_spoof
            metrics = dict(challenge["metrics"])
            metrics.update(
                completed_steps=list(challenge["completed_steps"]),
                required_steps=list(challenge["sequence"]),
                continuity_min=round(float(challenge["continuity_min"]), 4),
                configured_match_threshold=settings.match_threshold,
                configured_match_margin=settings.match_margin,
                confirm_frames=settings.anti_spoof_confirm_frames,
            )
            challenge["pending_completion"] = {
                "test_id": challenge["test_id"],
                "outcome": outcome,
                "reason": reason,
                "duration_seconds": round(now - challenge["started_at"], 2),
                "metrics": metrics,
            }
            challenge["prompt"] = f"Saving result: {reason}"
        self.deliver_anti_spoof_completion(now, force=True)

    def deliver_anti_spoof_completion(self, now: float, force: bool = False) -> None:
        with self.lock:
            challenge = self.anti_spoof
            if not challenge or challenge["pending_completion"] is None:
                return
            if not force and now - challenge["last_delivery_attempt"] < 1.0:
                return
            challenge["last_delivery_attempt"] = now
            payload = challenge["pending_completion"]
        try:
            response = self.api_request(
                "POST", "/api/internal/anti-spoof/complete", json=payload, timeout=5.0
            )
            response.raise_for_status()
            with self.lock:
                self.anti_spoof = None
                self.status["message"] = payload["reason"]
                self.status["error"] = None
        except Exception as exc:
            with self.lock:
                if self.anti_spoof:
                    self.anti_spoof["prompt"] = "Saving challenge result; retrying"
                self.status["error"] = f"Challenge result write failed: {exc}"

    def process_enrollment(
        self,
        vision: VisionEngine,
        frame: np.ndarray,
        observations: list[FaceObservation],
        guidance: str,
        now: float,
    ) -> str:
        with self.lock:
            enrollment = self.enrollment
        if enrollment is None:
            return guidance
        if guidance != "Ready":
            with self.lock:
                if self.enrollment:
                    self.enrollment["message"] = guidance
            return guidance
        if now - self.last_sample_at < 0.65:
            return f"Hold position · {len(enrollment['embeddings'])}/{settings.enrollment_samples}"

        embedding = vision.embedding(frame, observations[0])
        existing = enrollment["embeddings"]
        if existing and max(float(np.dot(embedding, sample)) for sample in existing) > 0.9995:
            return "Move your head slightly"

        with self.lock:
            if not self.enrollment:
                return "Enrollment cancelled"
            self.enrollment["embeddings"].append(embedding)
            self.enrollment["quality_scores"].append(observations[0].blur_score)
            captured = len(self.enrollment["embeddings"])
            self.enrollment["message"] = f"Captured {captured}/{settings.enrollment_samples}"
        self.last_sample_at = now

        if captured >= settings.enrollment_samples:
            self.complete_enrollment()
            return "Enrollment complete"
        if captured < settings.enrollment_samples // 3:
            return f"Look directly · {captured}/{settings.enrollment_samples}"
        if captured < (settings.enrollment_samples * 2) // 3:
            return f"Turn slightly left · {captured}/{settings.enrollment_samples}"
        return f"Turn slightly right · {captured}/{settings.enrollment_samples}"

    def complete_enrollment(self) -> None:
        with self.lock:
            if not self.enrollment:
                return
            payload = {
                "employee_id": self.enrollment["employee_id"],
                "embeddings": [sample.tolist() for sample in self.enrollment["embeddings"]],
                "quality_scores": self.enrollment["quality_scores"],
            }
        try:
            response = self.api_request(
                "POST", "/api/internal/enrollments/complete", json=payload, timeout=15.0
            )
            response.raise_for_status()
            with self.lock:
                self.enrollment = None
                self.status["message"] = "Enrollment complete"
            self.refresh_templates(force=True)
        except Exception as exc:
            with self.lock:
                if self.enrollment:
                    self.enrollment["message"] = f"Could not save enrollment: {exc}"
                self.status["error"] = str(exc)

    def stable_match(self) -> int | None:
        candidates = [item for item in self.recent_matches if item is not None]
        if len(candidates) < 3:
            return None
        employee_id, count = Counter(candidates).most_common(1)[0]
        return employee_id if count >= 3 else None

    def refresh_templates(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_template_refresh < settings.template_refresh_seconds:
            return
        self.last_template_refresh = now
        try:
            response = self.api_request("GET", "/api/internal/templates", timeout=5.0)
            response.raise_for_status()
            loaded: dict[int, dict] = {}
            for employee in response.json().get("employees", []):
                samples = []
                for raw in employee.get("embeddings", []):
                    sample = np.asarray(raw, dtype=np.float32)
                    norm = float(np.linalg.norm(sample))
                    if norm > 1e-8:
                        samples.append(sample / norm)
                if samples:
                    loaded[int(employee["id"])] = {
                        "id": int(employee["id"]),
                        "name": employee["name"],
                        "embeddings": samples,
                    }
            self.templates = loaded
            with self.lock:
                self.status.update(
                    template_count=sum(len(item["embeddings"]) for item in loaded.values()),
                    employee_count=len(loaded),
                )
        except Exception as exc:
            with self.lock:
                self.status["error"] = f"Template refresh failed: {exc}"

    @staticmethod
    def api_request(method: str, path: str, **kwargs) -> httpx.Response:
        with httpx.Client(
            base_url=settings.api_internal_url,
            headers={"X-Internal-Token": settings.internal_token},
        ) as client:
            return client.request(method, path, **kwargs)

    def emit_event(
        self,
        event_type: str,
        employee_id: int | None,
        employee_name: str | None,
        similarity: float | None,
        guidance: str,
        candidate_employee: dict | None,
        runner_up_similarity: float | None,
        score_margin: float | None,
        observation: FaceObservation,
    ) -> None:
        key = f"{event_type}:{employee_id or 'unknown'}"
        now = time.monotonic()
        if self.active_event_key == key:
            return
        if now - self.last_event_by_key.get(key, 0.0) < settings.event_cooldown_seconds:
            return
        payload = {
            "event_type": event_type,
            "employee_id": employee_id,
            "employee_name": employee_name,
            "similarity": round(float(similarity), 4) if similarity is not None else None,
            "guidance": guidance,
            "candidate_employee_id": candidate_employee["id"] if candidate_employee else None,
            "candidate_employee_name": candidate_employee["name"] if candidate_employee else None,
            "runner_up_similarity": (
                round(float(runner_up_similarity), 4)
                if runner_up_similarity is not None
                else None
            ),
            "score_margin": round(float(score_margin), 4) if score_margin is not None else None,
            "detection_confidence": round(float(observation.confidence), 4),
            "face_width": observation.width,
            "blur_score": round(float(observation.blur_score), 2),
        }
        try:
            response = self.api_request("POST", "/api/internal/events", json=payload, timeout=3.0)
            response.raise_for_status()
            event_id = response.json().get("event_id")
            self.last_event_by_key[key] = now
            self.active_event_key = key
            self.action_dispatcher.enqueue(
                {
                    "event_type": event_type,
                    "event_id": event_id,
                    "employee_id": employee_id,
                    "employee": employee_name,
                    "similarity": payload["similarity"],
                    "guidance": guidance,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        except Exception as exc:
            with self.lock:
                self.status["error"] = f"Event write failed: {exc}"

    @staticmethod
    def annotate(
        frame: np.ndarray,
        observations: list[FaceObservation],
        guidance: str,
        best_name: str | None,
        best_score: float | None,
    ) -> np.ndarray:
        output = frame.copy()
        ready = guidance == "Ready" or guidance.startswith("Recognized") or "Enrollment" in guidance
        color = (66, 211, 146) if ready else (74, 158, 255)
        for face in observations:
            cv2.rectangle(
                output,
                (face.x, face.y),
                (face.x + face.width, face.y + face.height),
                color,
                2,
            )
            label = best_name or f"face {face.confidence:.2f}"
            if best_score is not None:
                label += f" | {best_score:.3f}"
            cv2.putText(
                output,
                label,
                (face.x, max(24, face.y - 9)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                color,
                2,
                cv2.LINE_AA,
            )
        cv2.rectangle(output, (0, 0), (output.shape[1], 52), (18, 24, 35), -1)
        cv2.putText(
            output,
            guidance,
            (18, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.78,
            (240, 245, 250),
            2,
            cv2.LINE_AA,
        )
        return output

    def mjpeg(self) -> Generator[bytes, None, None]:
        last_version = -1
        while not self.stop_event.is_set():
            with self.lock:
                jpeg = self.preview_jpeg
                version = self.preview_version
            if jpeg and version != last_version:
                last_version = version
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            else:
                time.sleep(0.05)


runtime = RecognitionRuntime()


@asynccontextmanager
async def lifespan(_: FastAPI):
    runtime.start()
    yield
    runtime.stop()


app = FastAPI(title="FaceRec Recognition Worker", version="0.4.2", lifespan=lifespan)


@app.get("/health")
def health(response: Response):
    state = runtime.snapshot_status()
    if not state["model_ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if state["model_ready"] else "starting",
        "camera_connected": state["camera_connected"],
        "model_ready": state["model_ready"],
    }


@app.get("/status")
def worker_status():
    return runtime.snapshot_status()


@app.get("/stream.mjpg")
def stream():
    return StreamingResponse(
        runtime.mjpeg(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@app.post("/enrollments/start")
def start_enrollment(payload: EnrollmentStart):
    return runtime.start_enrollment(payload)


@app.get("/enrollments/status")
def enrollment_status():
    return runtime.enrollment_public()


@app.post("/enrollments/cancel")
def cancel_enrollment():
    return runtime.cancel_enrollment()


@app.post("/anti-spoof/start")
def start_anti_spoof(payload: AntiSpoofStart):
    return runtime.start_anti_spoof(payload)


@app.get("/anti-spoof/status")
def anti_spoof_status():
    return runtime.anti_spoof_public()


@app.post("/anti-spoof/cancel")
def cancel_anti_spoof():
    return runtime.cancel_anti_spoof()
