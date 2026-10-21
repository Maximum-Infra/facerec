from contextlib import asynccontextmanager
import asyncio
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
import secrets

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .database import SessionLocal, get_db, init_database
from .calibration import classify_attempt, summarize_attempts
from .anti_spoof import evaluate_test, summarize_tests
from .models import (
    AntiSpoofTest,
    CalibrationAttempt,
    CalibrationSession,
    Employee,
    FaceTemplate,
    RecognitionEvent,
    AuditLog,
    RetentionPolicy,
)
from .retention import get_or_create_policy, record_audit, run_retention
from .schemas import (
    AntiSpoofComplete,
    AntiSpoofTestCreate,
    AntiSpoofTestOut,
    CalibrationAttemptCreate,
    CalibrationAttemptOut,
    CalibrationSessionCreate,
    CalibrationSessionOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    EnrollmentComplete,
    RecognitionEventIn,
    RecognitionEventOut,
    AuditLogOut,
    RetentionPolicyOut,
    RetentionPolicyUpdate,
)

settings = get_settings()


async def retention_loop():
    while True:
        try:
            with SessionLocal() as db:
                run_retention(db, actor="system-retention")
        except Exception:
            # A cleanup failure must never stop recognition/API service availability.
            pass
        await asyncio.sleep(max(60, settings.retention_check_seconds))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    retention_task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        retention_task.cancel()
        try:
            await retention_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="FaceRec API", version="0.4.2", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def employee_out(employee: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=employee.id,
        name=employee.name,
        active=employee.active,
        created_at=employee.created_at,
        enrolled_at=employee.enrolled_at,
        template_count=len(employee.templates),
    )


def calibration_session_out(session: CalibrationSession) -> CalibrationSessionOut:
    attempts = list(session.attempts)
    armed = next((attempt for attempt in attempts if attempt.status == "armed"), None)
    return CalibrationSessionOut(
        id=session.id,
        name=session.name,
        notes=session.notes,
        status=session.status,
        match_threshold=session.match_threshold,
        match_margin=session.match_margin,
        detection_threshold=session.detection_threshold,
        min_face_width=session.min_face_width,
        started_at=session.started_at,
        completed_at=session.completed_at,
        attempt_count=len(attempts),
        captured_count=sum(attempt.status == "captured" for attempt in attempts),
        armed_attempt=armed,
    )


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    if x_internal_token != settings.internal_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


def operator_name(x_operator: str = Header(default="local-dashboard")) -> str:
    return (x_operator.strip() or "local-dashboard")[:120]


def retention_policy_out(policy: RetentionPolicy) -> RetentionPolicyOut:
    next_run = None
    if policy.enabled:
        base = policy.last_run_at or policy.updated_at
        next_run = base + timedelta(seconds=max(60, settings.retention_check_seconds))
    return RetentionPolicyOut(
        enabled=policy.enabled,
        recognition_event_days=policy.recognition_event_days,
        calibration_days=policy.calibration_days,
        anti_spoof_days=policy.anti_spoof_days,
        updated_at=policy.updated_at,
        last_run_at=policy.last_run_at,
        next_run_at=next_run,
    )


async def worker_request(method: str, path: str, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.request(method, f"{settings.worker_url}{path}", **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Worker rejected request"
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Recognition worker unavailable: {exc}") from exc


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "app": settings.app_name, "mode": settings.app_mode, "database": "ok"}


@app.get("/api/config")
def public_config():
    return {
        "app_name": settings.app_name,
        "mode": settings.app_mode,
        "match_threshold": settings.match_threshold,
        "match_margin": settings.match_margin,
        "enrollment_samples": settings.enrollment_samples,
        "door_integration": False,
        "continuous_recording": False,
        "action_webhook_enabled": settings.action_webhook_enabled,
        "retention_check_seconds": settings.retention_check_seconds,
        "anti_spoof_mode": "experimental_rgb_challenge",
        "anti_spoof": {
            "step_timeout_seconds": settings.anti_spoof_step_timeout_seconds,
            "confirm_frames": settings.anti_spoof_confirm_frames,
            "turn_delta": settings.anti_spoof_turn_delta,
            "closer_ratio": settings.anti_spoof_closer_ratio,
            "continuity_threshold": settings.anti_spoof_continuity_threshold,
        },
    }


@app.get("/api/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db)):
    employees = db.scalars(
        select(Employee).options(selectinload(Employee.templates)).order_by(Employee.name)
    ).all()
    return [employee_out(employee) for employee in employees]


@app.post("/api/employees", response_model=EmployeeOut, status_code=201)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    actor: str = Depends(operator_name),
):
    employee = Employee(name=payload.name.strip())
    db.add(employee)
    try:
        db.flush()
        record_audit(db, "employee.create", "employee", actor=actor, target_id=employee.id, details={"name": employee.name})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An employee with this name already exists") from exc
    db.refresh(employee)
    employee.templates = []
    return employee_out(employee)


@app.patch("/api/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    actor: str = Depends(operator_name),
):
    employee = db.scalar(
        select(Employee).options(selectinload(Employee.templates)).where(Employee.id == employee_id)
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    before = {"name": employee.name, "active": employee.active}
    if payload.name is not None:
        employee.name = payload.name.strip()
    if payload.active is not None:
        employee.active = payload.active
    try:
        record_audit(
            db, "employee.update", "employee", actor=actor, target_id=employee.id,
            details={"before": before, "after": {"name": employee.name, "active": employee.active}},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An employee with this name already exists") from exc
    db.refresh(employee)
    return employee_out(employee)


@app.delete("/api/employees/{employee_id}", status_code=204)
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    actor: str = Depends(operator_name),
):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    details = {"name": employee.name, "template_count": len(employee.templates)}
    record_audit(db, "employee.delete", "employee", actor=actor, target_id=employee.id, details=details)
    db.delete(employee)
    db.commit()


@app.post("/api/employees/{employee_id}/enroll")
async def start_enrollment(employee_id: int, db: Session = Depends(get_db)):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not employee.active:
        raise HTTPException(status_code=409, detail="Employee is disabled")
    return await worker_request(
        "POST", "/enrollments/start", json={"employee_id": employee.id, "employee_name": employee.name}
    )


@app.get("/api/enrollment/status")
async def enrollment_status():
    return await worker_request("GET", "/enrollments/status")


@app.post("/api/enrollment/cancel")
async def cancel_enrollment():
    return await worker_request("POST", "/enrollments/cancel")


@app.get("/api/worker/status")
async def worker_status():
    return await worker_request("GET", "/status")


@app.get("/api/anti-spoof/status")
async def anti_spoof_status(db: Session = Depends(get_db)):
    worker_state = await worker_request("GET", "/anti-spoof/status")
    if worker_state.get("active"):
        return worker_state
    active = db.scalar(
        select(AntiSpoofTest)
        .where(AntiSpoofTest.status == "active")
        .order_by(AntiSpoofTest.started_at.desc())
    )
    if not active:
        return worker_state
    return {
        "active": True,
        "stale": True,
        "test_id": active.id,
        "test_type": active.test_type,
        "subject_label": active.subject_label,
        "expected_employee_name": active.expected_employee_name,
        "sequence": active.challenge_sequence,
        "current_step_index": 0,
        "current_step": active.challenge_sequence[0],
        "completed_steps": [],
        "confirmations": 0,
        "required_confirmations": settings.anti_spoof_confirm_frames,
        "prompt": "Worker restarted; cancel this inconclusive test",
        "elapsed_seconds": round(
            max(0.0, (datetime.now(timezone.utc) - active.started_at).total_seconds()), 1
        ),
        "finishing": False,
    }


@app.get("/api/anti-spoof/tests", response_model=list[AntiSpoofTestOut])
def list_anti_spoof_tests(
    limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)
):
    return db.scalars(
        select(AntiSpoofTest).order_by(AntiSpoofTest.started_at.desc()).limit(limit)
    ).all()


@app.delete("/api/anti-spoof/tests", status_code=204)
def clear_anti_spoof_tests(
    db: Session = Depends(get_db), actor: str = Depends(operator_name)
):
    active = db.scalar(select(AntiSpoofTest).where(AntiSpoofTest.status == "active"))
    if active:
        raise HTTPException(status_code=409, detail="Cancel the active anti-spoof test first")
    count = db.scalar(select(func.count()).select_from(AntiSpoofTest)) or 0
    db.execute(delete(AntiSpoofTest))
    record_audit(db, "evidence.clear", "anti_spoof_tests", actor=actor, details={"deleted": count})
    db.commit()


@app.post("/api/anti-spoof/tests", response_model=AntiSpoofTestOut, status_code=201)
async def start_anti_spoof_test(payload: AntiSpoofTestCreate, db: Session = Depends(get_db)):
    active = db.scalar(select(AntiSpoofTest).where(AntiSpoofTest.status == "active"))
    if active:
        raise HTTPException(status_code=409, detail="Complete or cancel the active anti-spoof test")
    armed_calibration = db.scalar(
        select(CalibrationAttempt).where(CalibrationAttempt.status == "armed")
    )
    if armed_calibration:
        raise HTTPException(status_code=409, detail="Cancel or capture the armed calibration attempt")

    employee = None
    if payload.test_type == "live":
        if payload.expected_employee_id is None:
            raise HTTPException(status_code=422, detail="A live test requires an enrolled employee")
        employee = db.get(Employee, payload.expected_employee_id)
        if not employee or not employee.active or employee.enrolled_at is None:
            raise HTTPException(status_code=409, detail="Expected employee must be active and enrolled")
    elif payload.expected_employee_id is not None:
        raise HTTPException(status_code=422, detail="Attack tests cannot expect an employee match")

    subject_label = (
        employee.name
        if employee
        else (payload.subject_label or payload.test_type.replace("_", " ")).strip()
    )
    sequence = ["center", secrets.choice(["turn_left", "turn_right"]), "center_again", "move_closer"]
    test = AntiSpoofTest(
        test_type=payload.test_type,
        subject_label=subject_label,
        expected_employee_id=employee.id if employee else None,
        expected_employee_name=employee.name if employee else None,
        status="active",
        challenge_sequence=sequence,
    )
    db.add(test)
    db.commit()
    db.refresh(test)
    try:
        await worker_request(
            "POST",
            "/anti-spoof/start",
            json={
                "test_id": test.id,
                "test_type": test.test_type,
                "subject_label": test.subject_label,
                "expected_employee_id": test.expected_employee_id,
                "expected_employee_name": test.expected_employee_name,
                "sequence": test.challenge_sequence,
            },
        )
    except HTTPException:
        db.delete(test)
        db.commit()
        raise
    return test


@app.post("/api/anti-spoof/cancel", response_model=AntiSpoofTestOut)
async def cancel_anti_spoof_test(db: Session = Depends(get_db)):
    test = db.scalar(
        select(AntiSpoofTest)
        .where(AntiSpoofTest.status == "active")
        .order_by(AntiSpoofTest.started_at.desc())
    )
    if not test:
        raise HTTPException(status_code=404, detail="No active anti-spoof test")
    await worker_request("POST", "/anti-spoof/cancel")
    now = datetime.now(timezone.utc)
    test.status = "cancelled"
    test.observed_outcome = "inconclusive"
    test.evaluation = "inconclusive"
    test.reason = "Cancelled by operator"
    test.completed_at = now
    test.duration_seconds = max(0.0, (now - test.started_at).total_seconds())
    db.commit()
    db.refresh(test)
    return test


@app.get("/api/anti-spoof/report")
def anti_spoof_report(db: Session = Depends(get_db)):
    tests = db.scalars(select(AntiSpoofTest).order_by(AntiSpoofTest.started_at)).all()
    return summarize_tests(list(tests))


@app.get("/api/anti-spoof/tests.csv")
def anti_spoof_tests_csv(db: Session = Depends(get_db)):
    tests = db.scalars(select(AntiSpoofTest).order_by(AntiSpoofTest.started_at)).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "test_id", "test_type", "subject_label", "expected_identity", "status",
            "challenge_sequence", "observed_outcome", "evaluation", "reason",
            "duration_seconds", "started_at", "completed_at", "metrics",
        ]
    )
    for test in tests:
        writer.writerow(
            [
                test.id, test.test_type, test.subject_label, test.expected_employee_name or "",
                test.status, " > ".join(test.challenge_sequence), test.observed_outcome or "",
                test.evaluation or "", test.reason or "", test.duration_seconds,
                test.started_at.isoformat(), test.completed_at.isoformat() if test.completed_at else "",
                test.metrics or {},
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="facerec-anti-spoof-tests.csv"'},
    )


@app.get("/api/events", response_model=list[RecognitionEventOut])
def list_events(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)):
    return db.scalars(
        select(RecognitionEvent).order_by(RecognitionEvent.created_at.desc()).limit(limit)
    ).all()


@app.delete("/api/events", status_code=204)
def clear_events(db: Session = Depends(get_db), actor: str = Depends(operator_name)):
    armed = db.scalar(select(CalibrationAttempt).where(CalibrationAttempt.status == "armed"))
    if armed:
        raise HTTPException(status_code=409, detail="Cancel or capture the armed calibration attempt")
    # Calibration evidence keeps its copied numerical result when source events are cleared.
    db.execute(update(CalibrationAttempt).values(event_id=None))
    count = db.scalar(select(func.count()).select_from(RecognitionEvent)) or 0
    db.execute(delete(RecognitionEvent))
    record_audit(db, "evidence.clear", "recognition_events", actor=actor, details={"deleted": count})
    db.commit()


@app.get("/api/calibration/sessions", response_model=list[CalibrationSessionOut])
def list_calibration_sessions(
    limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)
):
    sessions = db.scalars(
        select(CalibrationSession)
        .options(selectinload(CalibrationSession.attempts))
        .order_by(CalibrationSession.started_at.desc())
        .limit(limit)
    ).all()
    return [calibration_session_out(session) for session in sessions]


@app.delete("/api/calibration/sessions", status_code=204)
def clear_calibration_sessions(
    db: Session = Depends(get_db), actor: str = Depends(operator_name)
):
    active = db.scalar(select(CalibrationSession).where(CalibrationSession.status == "active"))
    if active:
        raise HTTPException(status_code=409, detail="Complete the active calibration session first")
    count = db.scalar(select(func.count()).select_from(CalibrationSession)) or 0
    db.execute(delete(CalibrationAttempt))
    db.execute(delete(CalibrationSession))
    record_audit(db, "evidence.clear", "calibration_sessions", actor=actor, details={"deleted": count})
    db.commit()


@app.post("/api/calibration/sessions", response_model=CalibrationSessionOut, status_code=201)
def create_calibration_session(payload: CalibrationSessionCreate, db: Session = Depends(get_db)):
    active = db.scalar(select(CalibrationSession).where(CalibrationSession.status == "active"))
    if active:
        raise HTTPException(status_code=409, detail="Complete the active calibration session first")
    session = CalibrationSession(
        name=payload.name.strip(),
        notes=payload.notes.strip() if payload.notes else None,
        status="active",
        match_threshold=settings.match_threshold,
        match_margin=settings.match_margin,
        detection_threshold=settings.detection_score_threshold,
        min_face_width=settings.min_face_width,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    session.attempts = []
    return calibration_session_out(session)


@app.get("/api/calibration/sessions/active", response_model=CalibrationSessionOut | None)
def active_calibration_session(db: Session = Depends(get_db)):
    session = db.scalar(
        select(CalibrationSession)
        .options(selectinload(CalibrationSession.attempts))
        .where(CalibrationSession.status == "active")
    )
    return calibration_session_out(session) if session else None


@app.get("/api/calibration/sessions/{session_id}")
def calibration_session_detail(session_id: int, db: Session = Depends(get_db)):
    session = db.scalar(
        select(CalibrationSession)
        .options(selectinload(CalibrationSession.attempts))
        .where(CalibrationSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    result = calibration_session_out(session).model_dump()
    result["attempts"] = [
        CalibrationAttemptOut.model_validate(attempt).model_dump() for attempt in reversed(session.attempts)
    ]
    result["report"] = summarize_attempts(session.attempts, session.match_threshold)
    return result


@app.post(
    "/api/calibration/sessions/{session_id}/attempts",
    response_model=CalibrationAttemptOut,
    status_code=201,
)
def arm_calibration_attempt(
    session_id: int, payload: CalibrationAttemptCreate, db: Session = Depends(get_db)
):
    session = db.get(CalibrationSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Calibration session is completed")
    anti_spoof = db.scalar(select(AntiSpoofTest).where(AntiSpoofTest.status == "active"))
    if anti_spoof:
        raise HTTPException(status_code=409, detail="Complete or cancel the active anti-spoof test")
    armed = db.scalar(
        select(CalibrationAttempt).where(
            CalibrationAttempt.session_id == session_id, CalibrationAttempt.status == "armed"
        )
    )
    if armed:
        raise HTTPException(status_code=409, detail="A calibration attempt is already armed")

    employee = None
    if payload.expected_type == "genuine":
        if payload.expected_employee_id is None:
            raise HTTPException(status_code=422, detail="A genuine attempt requires an employee")
        employee = db.get(Employee, payload.expected_employee_id)
        if not employee or not employee.active or employee.enrolled_at is None:
            raise HTTPException(status_code=409, detail="Expected employee must be active and enrolled")
    elif payload.expected_employee_id is not None:
        raise HTTPException(status_code=422, detail="An impostor attempt cannot expect an employee match")

    attempt = CalibrationAttempt(
        session_id=session.id,
        expected_type=payload.expected_type,
        expected_employee_id=employee.id if employee else None,
        expected_employee_name=employee.name if employee else None,
        subject_label=(
            payload.subject_label.strip()
            if payload.subject_label
            else (employee.name if employee else "Unknown participant")
        ),
        pose=payload.pose,
        distance=payload.distance,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@app.post("/api/calibration/attempts/{attempt_id}/cancel", response_model=CalibrationAttemptOut)
def cancel_calibration_attempt(attempt_id: int, db: Session = Depends(get_db)):
    attempt = db.get(CalibrationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Calibration attempt not found")
    if attempt.status != "armed":
        raise HTTPException(status_code=409, detail="Only an armed attempt can be cancelled")
    attempt.status = "cancelled"
    db.commit()
    db.refresh(attempt)
    return attempt


@app.post("/api/calibration/attempts/{attempt_id}/no-decision", response_model=CalibrationAttemptOut)
def capture_calibration_no_decision(attempt_id: int, db: Session = Depends(get_db)):
    attempt = db.get(CalibrationAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Calibration attempt not found")
    if attempt.status != "armed":
        raise HTTPException(status_code=409, detail="Only an armed attempt can record no decision")
    attempt.status = "captured"
    attempt.observed_event_type = "no_decision"
    attempt.result = classify_attempt(
        attempt.expected_type, attempt.expected_employee_id, "no_decision", None
    )
    attempt.captured_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(attempt)
    return attempt


@app.post("/api/calibration/sessions/{session_id}/complete", response_model=CalibrationSessionOut)
def complete_calibration_session(session_id: int, db: Session = Depends(get_db)):
    session = db.scalar(
        select(CalibrationSession)
        .options(selectinload(CalibrationSession.attempts))
        .where(CalibrationSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    if any(attempt.status == "armed" for attempt in session.attempts):
        raise HTTPException(status_code=409, detail="Cancel or capture the armed attempt first")
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    db.commit()
    return calibration_session_out(session)


@app.get("/api/calibration/sessions/{session_id}/report")
def calibration_report(session_id: int, db: Session = Depends(get_db)):
    session = db.scalar(
        select(CalibrationSession)
        .options(selectinload(CalibrationSession.attempts))
        .where(CalibrationSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    return summarize_attempts(session.attempts, session.match_threshold)


@app.get("/api/calibration/sessions/{session_id}/attempts.csv")
def calibration_attempts_csv(session_id: int, db: Session = Depends(get_db)):
    session = db.scalar(
        select(CalibrationSession)
        .options(selectinload(CalibrationSession.attempts))
        .where(CalibrationSession.id == session_id)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Calibration session not found")
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "attempt_id", "status", "expected_type", "expected_identity", "subject_label",
            "pose", "distance", "observed_decision", "observed_identity", "raw_candidate",
            "similarity", "runner_up_similarity", "score_margin", "detection_confidence",
            "face_width", "blur_score", "result", "armed_at", "captured_at",
        ]
    )
    for attempt in session.attempts:
        writer.writerow(
            [
                attempt.id, attempt.status, attempt.expected_type,
                attempt.expected_employee_name or "", attempt.subject_label or "", attempt.pose,
                attempt.distance, attempt.observed_event_type or "",
                attempt.observed_employee_name or "", attempt.candidate_employee_name or "",
                attempt.similarity, attempt.runner_up_similarity, attempt.score_margin,
                attempt.detection_confidence, attempt.face_width, attempt.blur_score,
                attempt.result or "", attempt.armed_at.isoformat(),
                attempt.captured_at.isoformat() if attempt.captured_at else "",
            ]
        )
    filename = f"facerec-calibration-session-{session.id}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    employee_count = db.scalar(select(func.count()).select_from(Employee)) or 0
    enrolled_count = db.scalar(
        select(func.count()).select_from(Employee).where(Employee.enrolled_at.is_not(None))
    ) or 0
    event_count = db.scalar(select(func.count()).select_from(RecognitionEvent)) or 0
    return {"employees": employee_count, "enrolled": enrolled_count, "events": event_count}


@app.get("/api/admin/retention", response_model=RetentionPolicyOut)
def get_retention_policy(db: Session = Depends(get_db)):
    return retention_policy_out(get_or_create_policy(db))


@app.put("/api/admin/retention", response_model=RetentionPolicyOut)
def update_retention_policy(
    payload: RetentionPolicyUpdate,
    db: Session = Depends(get_db),
    actor: str = Depends(operator_name),
):
    policy = get_or_create_policy(db)
    before = {
        "enabled": policy.enabled,
        "recognition_event_days": policy.recognition_event_days,
        "calibration_days": policy.calibration_days,
        "anti_spoof_days": policy.anti_spoof_days,
    }
    policy.enabled = payload.enabled
    policy.recognition_event_days = payload.recognition_event_days
    policy.calibration_days = payload.calibration_days
    policy.anti_spoof_days = payload.anti_spoof_days
    policy.updated_at = datetime.now(timezone.utc)
    after = payload.model_dump()
    record_audit(db, "retention.update", "retention_policy", actor=actor, target_id=1, details={"before": before, "after": after})
    db.commit()
    db.refresh(policy)
    return retention_policy_out(policy)


@app.post("/api/admin/retention/run")
def run_retention_now(
    db: Session = Depends(get_db), actor: str = Depends(operator_name)
):
    active_calibration = db.scalar(select(CalibrationSession.id).where(CalibrationSession.status == "active"))
    active_spoof = db.scalar(select(AntiSpoofTest.id).where(AntiSpoofTest.status == "active"))
    if active_calibration or active_spoof:
        raise HTTPException(status_code=409, detail="Complete active calibration and RGB tests before cleanup")
    return run_retention(db, actor=actor, force=True)


@app.get("/api/admin/audit", response_model=list[AuditLogOut])
def list_audit_log(
    limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)
):
    return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()


@app.get("/api/internal/templates", dependencies=[Depends(require_internal_token)])
def internal_templates(db: Session = Depends(get_db)):
    employees = db.scalars(
        select(Employee)
        .options(selectinload(Employee.templates))
        .where(Employee.active.is_(True), Employee.enrolled_at.is_not(None))
    ).all()
    return {
        "employees": [
            {
                "id": employee.id,
                "name": employee.name,
                "embeddings": [template.embedding for template in employee.templates],
            }
            for employee in employees
        ]
    }


@app.post(
    "/api/internal/enrollments/complete",
    dependencies=[Depends(require_internal_token)],
)
def complete_enrollment(payload: EnrollmentComplete, db: Session = Depends(get_db)):
    employee = db.get(Employee, payload.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    dimensions = {len(embedding) for embedding in payload.embeddings}
    if len(dimensions) != 1 or next(iter(dimensions), 0) < 64:
        raise HTTPException(status_code=422, detail="Invalid embedding dimensions")

    db.execute(delete(FaceTemplate).where(FaceTemplate.employee_id == employee.id))
    for index, embedding in enumerate(payload.embeddings):
        quality = payload.quality_scores[index] if index < len(payload.quality_scores) else None
        db.add(FaceTemplate(employee_id=employee.id, embedding=embedding, quality=quality))
    employee.enrolled_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "completed", "employee_id": employee.id, "templates": len(payload.embeddings)}


@app.post(
    "/api/internal/events",
    dependencies=[Depends(require_internal_token)],
    status_code=201,
)
def create_event(payload: RecognitionEventIn, db: Session = Depends(get_db)):
    event = RecognitionEvent(
        event_type=payload.event_type,
        employee_id=payload.employee_id,
        employee_name=payload.employee_name,
        similarity=payload.similarity,
        guidance=payload.guidance,
    )
    db.add(event)
    db.flush()

    session = db.scalar(select(CalibrationSession).where(CalibrationSession.status == "active"))
    if session:
        attempt = db.scalar(
            select(CalibrationAttempt)
            .where(
                CalibrationAttempt.session_id == session.id,
                CalibrationAttempt.status == "armed",
            )
            .order_by(CalibrationAttempt.armed_at)
            .limit(1)
        )
        if attempt:
            attempt.status = "captured"
            attempt.event_id = event.id
            attempt.observed_event_type = payload.event_type
            attempt.observed_employee_id = payload.employee_id
            attempt.observed_employee_name = payload.employee_name
            attempt.candidate_employee_id = payload.candidate_employee_id
            attempt.candidate_employee_name = payload.candidate_employee_name
            attempt.similarity = payload.similarity
            attempt.runner_up_similarity = payload.runner_up_similarity
            attempt.score_margin = payload.score_margin
            attempt.detection_confidence = payload.detection_confidence
            attempt.face_width = payload.face_width
            attempt.blur_score = payload.blur_score
            attempt.result = classify_attempt(
                attempt.expected_type,
                attempt.expected_employee_id,
                payload.event_type,
                payload.employee_id,
            )
            attempt.captured_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return {"status": "recorded", "event_id": event.id}


@app.post(
    "/api/internal/anti-spoof/complete",
    dependencies=[Depends(require_internal_token)],
)
def complete_anti_spoof_test(payload: AntiSpoofComplete, db: Session = Depends(get_db)):
    test = db.get(AntiSpoofTest, payload.test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Anti-spoof test not found")
    if test.status != "active":
        # Worker completion delivery is idempotent so a retry cannot duplicate evidence.
        return {"status": test.status, "test_id": test.id, "evaluation": test.evaluation}
    test.status = "completed"
    test.observed_outcome = payload.outcome
    test.evaluation = evaluate_test(test.test_type, payload.outcome)
    test.reason = payload.reason
    test.metrics = payload.metrics
    test.duration_seconds = round(payload.duration_seconds, 2)
    test.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "completed", "test_id": test.id, "evaluation": test.evaluation}
