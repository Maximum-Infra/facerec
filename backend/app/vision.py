from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class FaceObservation:
    face: np.ndarray
    x: int
    y: int
    width: int
    height: int
    confidence: float
    blur_score: float


class VisionEngine:
    """YuNet detection and SFace embedding without retaining source images."""

    def __init__(
        self,
        yunet_model: Path,
        sface_model: Path,
        detection_threshold: float,
        min_face_width: int,
        min_blur_score: float,
    ) -> None:
        for model_path in (yunet_model, sface_model):
            if not model_path.is_file():
                raise FileNotFoundError(f"Required model is missing: {model_path}")

        self.detector = cv2.FaceDetectorYN.create(
            str(yunet_model), "", (320, 320), detection_threshold, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(sface_model), "")
        self.min_face_width = min_face_width
        self.min_blur_score = min_blur_score

    def detect(self, frame: np.ndarray) -> list[FaceObservation]:
        height, width = frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(frame)
        if faces is None:
            return []

        observations: list[FaceObservation] = []
        for face in faces:
            x, y, box_width, box_height = (int(value) for value in face[:4])
            x1, y1 = max(0, x), max(0, y)
            x2, y2 = min(width, x + box_width), min(height, y + box_height)
            roi = frame[y1:y2, x1:x2]
            blur = self.blur_score(roi)
            observations.append(
                FaceObservation(
                    face=face,
                    x=x1,
                    y=y1,
                    width=max(0, x2 - x1),
                    height=max(0, y2 - y1),
                    confidence=float(face[-1]),
                    blur_score=blur,
                )
            )
        return observations

    @staticmethod
    def blur_score(face_roi: np.ndarray) -> float:
        if face_roi.size == 0:
            return 0.0
        gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def quality_message(self, observations: list[FaceObservation]) -> str:
        if not observations:
            return "No face"
        if len(observations) > 1:
            return "Multiple faces"
        face = observations[0]
        if face.width < self.min_face_width:
            return "Move closer"
        if face.blur_score < self.min_blur_score:
            return "Hold still"
        return "Ready"

    def embedding(self, frame: np.ndarray, observation: FaceObservation) -> np.ndarray:
        aligned = self.recognizer.alignCrop(frame, observation.face)
        feature = self.recognizer.feature(aligned).flatten().astype(np.float32)
        norm = float(np.linalg.norm(feature))
        if norm <= 1e-8:
            raise ValueError("SFace returned an empty embedding")
        return feature / norm


def identity_ranking(
    probe: np.ndarray, templates: dict[int, dict]
) -> tuple[dict | None, float, float, float]:
    """Return raw best candidate, top score, runner-up score and score margin."""
    scores: list[tuple[float, dict]] = []
    for employee in templates.values():
        employee_scores = [float(np.dot(probe, sample)) for sample in employee["embeddings"]]
        if employee_scores:
            scores.append((max(employee_scores), employee))
    scores.sort(key=lambda item: item[0], reverse=True)
    if not scores:
        return None, 0.0, 0.0, 0.0

    best_score, employee = scores[0]
    second_score = scores[1][0] if len(scores) > 1 else -1.0
    score_margin = best_score - second_score
    return employee, best_score, second_score, score_margin


def best_identity(
    probe: np.ndarray, templates: dict[int, dict], threshold: float, margin: float
) -> tuple[dict | None, float, float]:
    """Return accepted employee, best score and margin over the second identity."""
    employee, best_score, _, score_margin = identity_ranking(probe, templates)
    if employee is None:
        return None, best_score, score_margin
    if best_score < threshold or score_margin < margin:
        return None, best_score, score_margin
    return employee, best_score, score_margin
