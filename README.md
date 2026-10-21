# FaceRec

FaceRec is a standalone, local face-recognition lab application for the confirmed Minrray RTSP camera. It uses OpenCV YuNet for detection and SFace for face embeddings. The current Phase 4B build identifies enrolled volunteers, records decisions, collects structured calibration evidence, runs experimental RGB presentation-attack challenges, applies evidence-retention controls and can deliver authenticated lab-notification webhooks. It has no code path capable of opening a door.

## Confirmed lab target

- Host: Ubuntu 22.04 x86_64 hypervisor
- Install path: `/opt/facerec`
- Camera: Minrray at `<CAMERA_IP>`
- Stream: `rtsp://<CAMERA_USER>:<CAMERA_PASSWORD>@<CAMERA_IP>:554/live/av0`
- Video: H.264, 1920×1080, 15 FPS
- Web UI: port `3001`
- API: port `8091`

## Included Phase 1 capabilities

- Direct RTSP-over-TCP pull with automatic reconnect
- In-memory frame processing; no continuous video recording
- Browser MJPEG preview with face boxes and guidance
- `No face`, `Multiple faces`, `Move closer`, `Hold still`, `Ready`, `Unknown`, and `Recognized` states
- Employee create, enable/disable, delete and re-enroll
- Guided 15-sample enrollment with multiple poses
- Normalized SFace templates stored in PostgreSQL
- 1:N matching against active employees
- Match threshold plus runner-up margin
- Three-frame temporal consistency before a recognized event
- One event per continuous face appearance, event cooldown and latest-50 history
- No unknown-event generation before the first employee is enrolled
- Container and camera/model health status
- Docker resource limits and restart policies
- No audio processing, raw face-image storage, or door action

## Included Phase 2A capabilities

- Structured calibration sessions in the dashboard
- Labeled genuine and impostor attempts
- Front, left and right pose labels plus near, normal and far distance labels
- Automatic capture of the next stable recognition decision
- Raw closest candidate, runner-up score, margin, face width, detection and blur evidence
- True accept, false reject, wrong identity, true reject and false accept classification
- Aggregate and per-user false-reject measurements
- False-accept measurements when impostor attempts exist
- Threshold recommendation only when at least three genuine and three impostor scores exist
- CSV evidence export without face images

## Included Phase 3A capabilities

- Randomized face-forward, head-turn, re-center and move-closer challenge sequence
- Multi-frame temporal confirmation for every challenge step
- Face-embedding continuity checks across the complete sequence
- Expected-identity verification at the start of a live-person baseline
- Labeled live, print, phone-photo and phone-video presentation-attack tests
- Live accepted/rejected, attack detected/missed and inconclusive classifications
- Aggregate live-accept and attack-detection measurements plus CSV export
- Numerical evidence only; no challenge images or video are retained
- Confirmed Clear actions for calibration evidence, RGB challenge evidence and recognition events

This is an experimental RGB motion challenge. It is useful for measuring obvious presentation attacks in this lab, but it is not production-grade liveness and must not be used to authorize access.

## Included Phase 4A capabilities

- Automatic age-based retention for recognition events, completed calibration sessions and completed RGB tests
- Independent retention periods with safe defaults of 30, 180 and 180 days
- Hourly cleanup and a confirmed manual **Run now** action
- Active tests, employees and face templates excluded from automatic retention
- Audit records for employee create/update/delete, evidence clears and retention administration
- Read-only recent audit trail in the dashboard

The current audit actor is `local-dashboard`; strong user attribution requires the authentication/roles work planned for the next Phase 4 increment.

## Included Phase 4B capability

- An optional authenticated webhook is queued only after a stable recognition event is committed.
- `recognized` and `unknown` events include the database event ID and numerical decision metadata.
- Delivery runs on a separate bounded queue and cannot pause camera processing.
- Receiver timeouts and failures do not remove recognition events or change recognition decisions.
- The bundled Node-RED flow accepts only the FaceRec host or Pi-local tests, requires a secret token, rate-limits actions and maps event types to two fixed sound files.
- This integration is a lab notification only. It does not use RGB anti-spoof results as authorization and cannot control a door, relay or GPIO.

FaceRec v0.4.1 pins its Docker-only bridge to `198.18.254.0/28`. This reserved, non-routed range is intentionally outside the office LAN and known VPN networks. Do not remove the network's subnet-pinning config block or return the network to Docker automatic addressing.

## Architecture

```text
Minrray RTSP -> facerec-worker -> annotated in-memory MJPEG preview
                         |     -> recognition decisions -> queued webhook
                         v
                    facerec-api <-> facerec-db
                         ^
                         |
                    facerec-web
```

The worker is the only component that reads the camera. The database stores employees, numerical embeddings and event metadata. The React UI reaches the API and worker through Nginx.

## Install on the hypervisor

Copy or extract this project as `/opt/facerec`, then run:

```bash
cd /opt/facerec
sudo chown -R <deploy-user>:<deploy-user> /opt/facerec
./scripts/install_lab.sh
```

The installer will:

1. Create `.env` from the known lab configuration if it does not exist.
2. Download the two official OpenCV Zoo models.
3. Record model SHA-256 hashes in `models/MODEL_SHA256SUMS`.
4. validate the Compose configuration.
5. Build and start the independent `facerec` Compose project.

Open:

```text
http://<hypervisor-IP>:3001
```

Use whichever hypervisor address your laptop normally reaches. The confirmed Wi-Fi address during the initial lab was `<HYPERVISOR_IP>`. The camera route itself is separately confirmed through `enp0s31f6` via `<CAMERA_ROUTE_IP>`.

## First lab workflow

1. Confirm the top pills show **Camera online** and **Models ready**.
2. Aim the camera so one complete face is near the center and at least about 280 pixels wide in the original 1080p stream.
3. Add the first volunteer by name.
4. Click **Enroll**.
5. Follow the overlay: look forward, slightly left and slightly right until 15 samples are captured.
6. Step away and approach again to test recognition.
7. Repeat for the other 2–3 volunteers.
8. Use **Calibration evidence** to start a session and arm deliberate genuine and impostor attempts.

The similarity value is a lab measurement, not a confidence percentage. Do not lower the threshold simply to eliminate inconvenience; review both genuine and impostor scores first.

## Operations

```bash
cd /opt/facerec

# Container status
docker compose ps

# Follow logs
docker compose logs -f --tail=150

# Worker logs only
docker compose logs -f --tail=150 worker

# API and UI smoke test
./scripts/smoke_test.sh

# Restart only FaceRec
docker compose restart

# Stop FaceRec without deleting its database
docker compose down

# Rebuild after code changes
docker compose up -d --build
```

Useful endpoints:

```text
http://<hypervisor-IP>:8091/api/health
http://<hypervisor-IP>:8091/api/worker/status
http://<hypervisor-IP>:8091/docs
```

## Configuration

Lab tuning is in `.env`:

| Variable | Default | Meaning |
|---|---:|---|
| `MATCH_THRESHOLD` | `0.60` | Calibrated minimum cosine similarity |
| `MATCH_MARGIN` | `0.04` | Required lead over second identity |
| `DETECTION_SCORE_THRESHOLD` | `0.85` | YuNet detection threshold |
| `MIN_FACE_WIDTH` | `120` | Calibrated minimum pixels after 960px processing resize |
| `MIN_BLUR_SCORE` | `55` | Minimum Laplacian sharpness |
| `INFERENCE_FPS` | `5` | Frames processed per second |
| `ENROLLMENT_SAMPLES` | `15` | Templates captured per employee |
| `EVENT_COOLDOWN_SECONDS` | `4` | Duplicate event suppression |
| `ANTI_SPOOF_STEP_TIMEOUT_SECONDS` | `12` | Maximum time for one challenge movement |
| `ANTI_SPOOF_CONFIRM_FRAMES` | `3` | Consecutive frames required per movement |
| `ANTI_SPOOF_TURN_DELTA` | `0.10` | Normalized landmark displacement for a turn |
| `ANTI_SPOOF_CLOSER_RATIO` | `1.18` | Required face-width increase for move closer |
| `ANTI_SPOOF_CONTINUITY_THRESHOLD` | `0.50` | Minimum same-face similarity through a challenge |
| `RETENTION_CHECK_SECONDS` | `3600` | Automatic retention check interval; minimum runtime value is 60 seconds |
| `ACTION_WEBHOOK_ENABLED` | `false` | Enable queued lab event notification delivery |
| `ACTION_WEBHOOK_URL` | empty | Protected receiver URL, such as the Pi Node-RED event endpoint |
| `ACTION_WEBHOOK_TOKEN` | empty | Shared secret sent only in the `X-FaceRec-Token` request header |
| `ACTION_WEBHOOK_TIMEOUT_SECONDS` | `8` | Per-attempt receiver timeout; delivery never blocks recognition |

After changing `.env`:

```bash
docker compose up -d --force-recreate api worker
```

## Phase 4B Node-RED sound notification

The importable flow is `integrations/node-red/facerec-event-flow.json`. Its fixed mappings are:

| FaceRec event | Pi sound |
|---|---|
| `recognized` | `/home/pi/Audio/facerec-wave.wav` |
| `unknown` | `/home/pi/Audio/facerec-wrong.wav` |

The flow does not accept a command or file path from the request. Its source allowlist contains the confirmed FaceRec host `<HYPERVISOR_IP>` plus Pi-local addresses for diagnostics. The Pi loads `FACEREC_WEBHOOK_TOKEN` from `/home/pi/.node-red/environment`; FaceRec loads the same value as `ACTION_WEBHOOK_TOKEN` from `/opt/facerec/.env`.

## Data behavior

- Raw camera frames are processed in RAM and discarded.
- The browser receives only the current annotated MJPEG stream.
- The database volume is `facerec-db`.
- Deleting an employee deletes their templates.
- Normal events store time, decision, employee name/ID when recognized, similarity and guidance.
- The current lab templates are not yet encrypted at rest. Production security hardening is intentionally a later phase.

## Phase 2 calibration workflow

1. Start a calibration session in the dashboard.
2. Ensure the camera currently shows **No face**.
3. Choose an enrolled employee, pose and distance, then click **Arm next attempt**.
4. Have that employee enter once and leave until **No face** appears again.
   If the subject remains in a valid test position but FaceRec never produces a final decision, use **Record no decision** so the false reject is not lost.
5. Repeat across employees, poses and distances.
6. For an impostor test, disable an enrolled employee instead of deleting them.
7. Wait for **Templates loaded** to decrease by that employee's template count.
8. Select **Unknown / disabled**, enter a subject label, arm the attempt and perform the pass.
9. Re-enable the employee and wait for their templates to reload.
10. Complete the session and export its CSV.

Disabling preserves the employee's templates. Deleting permanently removes them and requires re-enrollment. The report never applies a suggested threshold automatically.

## Phase 3 RGB challenge workflow

1. Ensure no face is visible and the camera/models indicators are green.
2. In **RGB presentation-attack lab**, choose **Live person** and an enrolled employee.
3. Start the challenge and follow the randomized prompts until the result is saved.
4. Repeat a minimum of three live tests per volunteer across normal entrance variation.
5. Select **Printed photo**, **Phone photo** or **Phone video**, label the medium and start a new challenge.
6. Move only the attack medium in response to prompts; do not introduce a live face into frame.
7. Record at least three tests per attack type, review missed attacks explicitly and export the CSV.

An attack timing out on a required movement is recorded as **attack detected**. An attack completing every step is a **missed attack**, not proof of liveness. Operator cancellation is inconclusive.

## Evidence cleanup

Each evidence panel has its own confirmed **Clear** action:

- **Calibration evidence** removes calibration sessions and attempts only.
- **RGB presentation-attack lab** removes RGB challenge tests only.
- **Recognition events** removes recognition history only; copied calibration measurements remain.

Employees, face templates and configuration are never removed by these actions. Cleanup is blocked
while the relevant workflow is active.

## Phase 4 retention and audit

The **Administration & privacy** panel controls the saved database retention policy. Defaults are:

- Recognition events: 30 days
- Completed calibration evidence: 180 days
- Completed RGB challenge evidence: 180 days

Automatic cleanup runs hourly. **Run now** applies the saved age limits immediately, even when automatic cleanup is disabled. It is blocked if calibration or RGB work is active. Audit entries have no dashboard/API clear operation. PostgreSQL can reuse the deleted row space.

## Troubleshooting

Camera offline:

```bash
ip route get <CAMERA_IP>
nc -vz -w3 <CAMERA_IP> 554
docker compose exec worker python -c "import socket; print(socket.create_connection(('<CAMERA_IP>', 554), 3))"
docker compose logs --tail=100 worker
```

Models unavailable:

```bash
./scripts/download_models.sh
ls -lh models/*.onnx
docker compose restart worker
```

Recognition poor or always `Move closer`:

- Center the expected standing position.
- Reduce ceiling/background dominance.
- Ensure the full face is visible and reasonably frontal.
- Use stable lighting.
- Review the displayed blur/position guidance before adjusting thresholds.

## Phase 1 acceptance checklist

- [ ] All four containers are healthy.
- [ ] Worker reconnects after a temporary camera interruption.
- [ ] UI preview shows face boxes and guidance.
- [ ] Three or four employees can be enrolled.
- [ ] Re-enrollment replaces prior templates.
- [ ] Disabled employees stop matching after the template refresh interval.
- [ ] Known and unknown events appear without stored images.
- [ ] No door electronics are connected.
