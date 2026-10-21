from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    templates: Mapped[list["FaceTemplate"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    employee: Mapped[Employee] = relationship(back_populates="templates")


class RecognitionEvent(Base):
    __tablename__ = "recognition_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    employee_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    guidance: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class CalibrationSession(Base):
    __tablename__ = "calibration_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    match_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    match_margin: Mapped[float] = mapped_column(Float, nullable=False)
    detection_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    min_face_width: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[list["CalibrationAttempt"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class CalibrationAttempt(Base):
    __tablename__ = "calibration_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("calibration_sessions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="armed", nullable=False, index=True)
    expected_type: Mapped[str] = mapped_column(String(20), nullable=False)
    expected_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    expected_employee_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    subject_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pose: Mapped[str] = mapped_column(String(30), nullable=False)
    distance: Mapped[str] = mapped_column(String(30), nullable=False)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("recognition_events.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    observed_event_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    observed_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    observed_employee_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    candidate_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    candidate_employee_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    runner_up_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    face_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blur_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    armed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session: Mapped[CalibrationSession] = relationship(back_populates="attempts")


class AntiSpoofTest(Base):
    __tablename__ = "anti_spoof_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject_label: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    expected_employee_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    challenge_sequence: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    observed_outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    evaluation: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class RetentionPolicy(Base):
    __tablename__ = "retention_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    recognition_event_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    calibration_days: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    anti_spoof_days: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
