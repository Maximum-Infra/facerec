from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import (
    AntiSpoofTest,
    AuditLog,
    CalibrationAttempt,
    CalibrationSession,
    RecognitionEvent,
    RetentionPolicy,
)


DEFAULT_POLICY = {
    "enabled": True,
    "recognition_event_days": 30,
    "calibration_days": 180,
    "anti_spoof_days": 180,
}


def get_or_create_policy(db: Session) -> RetentionPolicy:
    policy = db.get(RetentionPolicy, 1)
    if policy is None:
        policy = RetentionPolicy(id=1, **DEFAULT_POLICY)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


def record_audit(
    db: Session,
    action: str,
    target_type: str,
    *,
    actor: str = "local-dashboard",
    target_id: str | int | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=(actor or "local-dashboard")[:120],
        action=action,
        target_type=target_type,
        target_id=str(target_id)[:120] if target_id is not None else None,
        details=details,
    )
    db.add(entry)
    return entry


def run_retention(db: Session, *, actor: str, force: bool = False) -> dict:
    policy = get_or_create_policy(db)
    now = datetime.now(timezone.utc)
    counts = {"recognition_events": 0, "calibration_sessions": 0, "anti_spoof_tests": 0}

    if policy.enabled or force:
        event_cutoff = now - timedelta(days=policy.recognition_event_days)
        event_ids = list(db.scalars(select(RecognitionEvent.id).where(RecognitionEvent.created_at < event_cutoff)))
        if event_ids:
            db.execute(
                update(CalibrationAttempt)
                .where(CalibrationAttempt.event_id.in_(event_ids))
                .values(event_id=None)
            )
            counts["recognition_events"] = db.execute(
                delete(RecognitionEvent).where(RecognitionEvent.id.in_(event_ids))
            ).rowcount or 0

        calibration_cutoff = now - timedelta(days=policy.calibration_days)
        session_ids = list(
            db.scalars(
                select(CalibrationSession.id).where(
                    CalibrationSession.status != "active",
                    CalibrationSession.completed_at.is_not(None),
                    CalibrationSession.completed_at < calibration_cutoff,
                )
            )
        )
        if session_ids:
            db.execute(delete(CalibrationAttempt).where(CalibrationAttempt.session_id.in_(session_ids)))
            counts["calibration_sessions"] = db.execute(
                delete(CalibrationSession).where(CalibrationSession.id.in_(session_ids))
            ).rowcount or 0

        spoof_cutoff = now - timedelta(days=policy.anti_spoof_days)
        counts["anti_spoof_tests"] = db.execute(
            delete(AntiSpoofTest).where(
                AntiSpoofTest.status != "active",
                AntiSpoofTest.completed_at.is_not(None),
                AntiSpoofTest.completed_at < spoof_cutoff,
            )
        ).rowcount or 0

    policy.last_run_at = now
    record_audit(
        db,
        "retention.run",
        "evidence",
        actor=actor,
        details={"force": force, "policy_enabled": policy.enabled, "deleted": counts},
    )
    db.commit()
    return {"ran_at": now, "enabled": policy.enabled, "deleted": counts}
