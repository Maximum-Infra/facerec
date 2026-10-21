from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class EmployeeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    active: bool | None = None


class EmployeeOut(BaseModel):
    id: int
    name: str
    active: bool
    created_at: datetime
    enrolled_at: datetime | None
    template_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class EnrollmentComplete(BaseModel):
    employee_id: int
    embeddings: list[list[float]] = Field(min_length=3, max_length=50)
    quality_scores: list[float] = Field(default_factory=list)


class RecognitionEventIn(BaseModel):
    event_type: str = Field(pattern="^(recognized|unknown)$")
    employee_id: int | None = None
    employee_name: str | None = None
    similarity: float | None = None
    guidance: str | None = None
    candidate_employee_id: int | None = None
    candidate_employee_name: str | None = None
    runner_up_similarity: float | None = None
    score_margin: float | None = None
    detection_confidence: float | None = None
    face_width: int | None = None
    blur_score: float | None = None


class RecognitionEventOut(RecognitionEventIn):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CalibrationSessionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class CalibrationAttemptCreate(BaseModel):
    expected_type: str = Field(pattern="^(genuine|impostor)$")
    expected_employee_id: int | None = None
    subject_label: str | None = Field(default=None, max_length=120)
    pose: str = Field(pattern="^(front|left|right)$")
    distance: str = Field(pattern="^(near|normal|far)$")


class CalibrationAttemptOut(BaseModel):
    id: int
    session_id: int
    status: str
    expected_type: str
    expected_employee_id: int | None
    expected_employee_name: str | None
    subject_label: str | None
    pose: str
    distance: str
    event_id: int | None
    observed_event_type: str | None
    observed_employee_id: int | None
    observed_employee_name: str | None
    candidate_employee_id: int | None
    candidate_employee_name: str | None
    similarity: float | None
    runner_up_similarity: float | None
    score_margin: float | None
    detection_confidence: float | None
    face_width: int | None
    blur_score: float | None
    result: str | None
    armed_at: datetime
    captured_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CalibrationSessionOut(BaseModel):
    id: int
    name: str
    notes: str | None
    status: str
    match_threshold: float
    match_margin: float
    detection_threshold: float
    min_face_width: int
    started_at: datetime
    completed_at: datetime | None
    attempt_count: int = 0
    captured_count: int = 0
    armed_attempt: CalibrationAttemptOut | None = None

    model_config = ConfigDict(from_attributes=True)


class AntiSpoofTestCreate(BaseModel):
    test_type: str = Field(pattern="^(live|print|phone_photo|phone_video)$")
    expected_employee_id: int | None = None
    subject_label: str | None = Field(default=None, max_length=120)


class AntiSpoofTestOut(BaseModel):
    id: int
    test_type: str
    subject_label: str
    expected_employee_id: int | None
    expected_employee_name: str | None
    status: str
    challenge_sequence: list[str]
    observed_outcome: str | None
    evaluation: str | None
    reason: str | None
    metrics: dict | None
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None

    model_config = ConfigDict(from_attributes=True)


class AntiSpoofComplete(BaseModel):
    test_id: int
    outcome: str = Field(pattern="^(pass|fail|inconclusive)$")
    reason: str = Field(min_length=2, max_length=240)
    duration_seconds: float = Field(ge=0)
    metrics: dict = Field(default_factory=dict)


class RetentionPolicyUpdate(BaseModel):
    enabled: bool
    recognition_event_days: int = Field(ge=1, le=3650)
    calibration_days: int = Field(ge=1, le=3650)
    anti_spoof_days: int = Field(ge=1, le=3650)


class RetentionPolicyOut(RetentionPolicyUpdate):
    updated_at: datetime
    last_run_at: datetime | None
    next_run_at: datetime | None


class AuditLogOut(BaseModel):
    id: int
    actor: str
    action: str
    target_type: str
    target_id: str | None
    details: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
