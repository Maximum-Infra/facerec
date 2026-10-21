from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FaceRec"
    app_mode: str = "LAB"
    database_url: str = "sqlite:///./facerec.db"
    worker_url: str = "http://worker:8092"
    api_internal_url: str = "http://api:8091"
    internal_token: str = "change-me-internal-token"

    rtsp_url: str = ""
    rtsp_transport: str = "tcp"
    yunet_model: Path = Path("/app/models/face_detection_yunet_2023mar.onnx")
    sface_model: Path = Path("/app/models/face_recognition_sface_2021dec.onnx")

    match_threshold: float = 0.60
    match_margin: float = 0.04
    detection_score_threshold: float = 0.85
    min_face_width: int = 120
    min_blur_score: float = 55.0
    process_width: int = 960
    inference_fps: float = 5.0
    enrollment_samples: int = 15
    event_cooldown_seconds: float = 4.0
    template_refresh_seconds: float = 10.0
    anti_spoof_step_timeout_seconds: float = 12.0
    anti_spoof_confirm_frames: int = 3
    anti_spoof_turn_delta: float = 0.10
    anti_spoof_closer_ratio: float = 1.18
    anti_spoof_continuity_threshold: float = 0.50
    retention_check_seconds: int = 3600
    action_webhook_enabled: bool = False
    action_webhook_url: str = ""
    action_webhook_token: str = ""
    action_webhook_timeout_seconds: float = 8.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
