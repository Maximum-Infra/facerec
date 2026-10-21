# FaceRec delivery phases

## Phase 1 — Recognition lab (complete)

Standalone RTSP recognition, enrollment, shadow decisions, event history, health status and deployment tooling for 3–4 volunteers.

## Phase 2 — Calibration and evidence (complete)

- Export labeled attempt data without face images.
- Collect genuine and impostor score distributions.
- Calculate threshold and margin from the installed camera position.
- Add per-user and aggregate false-reject measurements.
- Add structured test sessions and a calibration report.

### Phase 2A delivered

- Arm labeled genuine or impostor attempts from the dashboard.
- Label pose and entrance distance for each attempt.
- Capture the next stable decision automatically without storing images.
- Preserve raw candidate, runner-up, margin, detection confidence, face width and blur score.
- Classify true accept, false reject, wrong identity, true reject and false accept outcomes.
- Show per-session FRR/FAR summaries and export attempts to CSV.
- Recommend a threshold only after at least three genuine and three impostor scores exist.

## Phase 3 — RGB lab anti-spoofing (complete)

- Add challenge flow and temporal checks.
- Test print, phone-photo and phone-video presentation attacks.
- Record spoof-test outcomes.
- Keep system in shadow mode; do not claim production-grade liveness.

### Phase 3A delivered

- Run a randomized forward, left/right turn, re-center and move-closer sequence.
- Require stable motion across multiple processed frames.
- Check that the same face remains present throughout the sequence.
- Require the expected enrolled identity at the start of live-person tests.
- Label live, print, phone-photo and phone-video tests independently.
- Classify live accepted/rejected, attack detected/missed and inconclusive outcomes.
- Store only numerical timing, pose, distance and identity-continuity evidence.
- Export the full test history to CSV and show aggregate attack-detection results.
- Keep the feature experimental, isolated from recognition events and incapable of door action.
- Add isolated, confirmed cleanup controls for calibration, RGB challenge and recognition evidence.

## Phase 4 — Administration and privacy hardening

- Authentication, roles and audit log.
- Template encryption and key management.
- Retention controls, backup/restore and offboarding workflow.
- Camera/network isolation and secret rotation.

### Phase 4A delivered in v0.4.0

- Configurable automatic retention for recognition, calibration and RGB evidence.
- Hourly cleanup plus an operator-controlled **Run now** action.
- Active calibration and RGB tests are always excluded from cleanup.
- Employees and face templates are outside the retention deletion scope.
- Audit entries for employee administration, manual clears and retention changes/runs.
- Read-only audit trail in the dashboard; there is no audit-clear API or UI action.
- v0.4.1 pins the FaceRec bridge to `198.18.254.0/28`, preventing Docker from selecting office VPN ranges such as `172.20.0.0/16`.

### Phase 4B delivered in v0.4.2

- Optional authenticated event webhook after durable recognition-event creation.
- Non-blocking bounded delivery queue with finite timeout and retry handling.
- Separate recognized/unknown lab notification actions in a source-restricted Node-RED flow.
- Fixed sound commands only; no request-controlled shell arguments or GPIO/door action.
- Recognition continues normally if the Raspberry Pi or Node-RED is unavailable.

## Phase 5 — Production liveness hardware

- Integrate and validate RGB+IR/depth camera or licensed liveness SDK.
- Fail closed on missing/invalid liveness data.
- Repeat calibration and presentation-attack testing.

## Phase 6 — Access-controller integration

- Integrate through a professional access controller, never direct lock power/GPIO.
- Preserve independent emergency egress, exit button and mechanical/badge fallback.
- Add shadow-to-live change control, monitoring, rollback and operational runbooks.
