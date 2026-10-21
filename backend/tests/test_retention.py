from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AntiSpoofTest, AuditLog, CalibrationAttempt, CalibrationSession, RecognitionEvent
from app.retention import get_or_create_policy, run_retention


def test_retention_removes_only_expired_inactive_evidence():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    old = datetime.now(timezone.utc) - timedelta(days=400)
    recent = datetime.now(timezone.utc) - timedelta(days=1)

    with Session() as db:
        policy = get_or_create_policy(db)
        policy.recognition_event_days = 30
        policy.calibration_days = 180
        policy.anti_spoof_days = 180

        old_event = RecognitionEvent(event_type="unknown", created_at=old)
        recent_event = RecognitionEvent(event_type="unknown", created_at=recent)
        completed_session = CalibrationSession(
            name="old", status="completed", match_threshold=.7, match_margin=.04,
            detection_threshold=.85, min_face_width=120, started_at=old, completed_at=old,
        )
        active_session = CalibrationSession(
            name="active", status="active", match_threshold=.7, match_margin=.04,
            detection_threshold=.85, min_face_width=120, started_at=old,
        )
        old_spoof = AntiSpoofTest(
            test_type="print", subject_label="old", status="completed",
            challenge_sequence=["center"], started_at=old, completed_at=old,
        )
        active_spoof = AntiSpoofTest(
            test_type="live", subject_label="active", status="active",
            challenge_sequence=["center"], started_at=old,
        )
        db.add_all([old_event, recent_event, completed_session, active_session, old_spoof, active_spoof])
        db.flush()
        db.add(CalibrationAttempt(
            session_id=completed_session.id, status="captured", expected_type="impostor",
            subject_label="test", pose="front", distance="normal", event_id=old_event.id,
            armed_at=old, captured_at=old,
        ))
        db.commit()

        result = run_retention(db, actor="pytest")

        assert result["deleted"] == {
            "recognition_events": 1,
            "calibration_sessions": 1,
            "anti_spoof_tests": 1,
        }
        assert db.scalar(select(func.count()).select_from(RecognitionEvent)) == 1
        assert db.scalar(select(func.count()).select_from(CalibrationSession)) == 1
        assert db.scalar(select(func.count()).select_from(CalibrationAttempt)) == 0
        assert db.scalar(select(func.count()).select_from(AntiSpoofTest)) == 1
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "retention.run"))
        assert audit.actor == "pytest"
        assert audit.details["deleted"]["recognition_events"] == 1
