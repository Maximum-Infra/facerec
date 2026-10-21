# FaceRec v0.3.0 upgrade

This upgrade adds Phase 3A experimental RGB presentation-attack testing. It preserves the
PostgreSQL volume, employees, templates, events, Phase 2 calibration evidence and live `.env`.
FaceRec remains in shadow mode with no door integration.

## Confirm the Phase 2 checkpoint

The accepted checkpoint created on 2026-08-26 is:

```text
c7072d76cfe3a58f9cc6f1ee746498535b3d1d89166fa1068e7df4c52bb5cbac  .env.phase2-calibrated-060-20260826.bak
0c170b5efb7eea47c94309ab3c0be92677d1168aab374e6d5f0978b47015aa23  facerec-phase2-calibrated-060-20260826.sql
```

Verify before upgrading:

```bash
cd /opt/facerec
sha256sum -c <(cat <<'EOF'
c7072d76cfe3a58f9cc6f1ee746498535b3d1d89166fa1068e7df4c52bb5cbac  .env.phase2-calibrated-060-20260826.bak
0c170b5efb7eea47c94309ab3c0be92677d1168aab374e6d5f0978b47015aa23  facerec-phase2-calibrated-060-20260826.sql
EOF
)
```

## Install

Copy `FaceRec_Phase3_RGB_Lab_0.3.0.tar.gz` to the hypervisor, then:

```bash
cd /opt/facerec
sudo tar -xzf ~/Documents/FaceRec_Phase3_RGB_Lab_0.3.0.tar.gz -C /opt/facerec
sudo chown -R <deploy-user>:<deploy-user> /opt/facerec

grep -q '^ANTI_SPOOF_STEP_TIMEOUT_SECONDS=' .env || cat >> .env <<'EOF'

# Phase 3 experimental RGB challenge
ANTI_SPOOF_STEP_TIMEOUT_SECONDS=12
ANTI_SPOOF_CONFIRM_FRAMES=3
ANTI_SPOOF_TURN_DELTA=0.10
ANTI_SPOOF_CLOSER_RATIO=1.18
ANTI_SPOOF_CONTINUITY_THRESHOLD=0.50
EOF

docker compose up -d --build api worker web
docker compose ps
./scripts/smoke_test.sh
```

The API creates only the new `anti_spoof_tests` table. It does not alter or delete existing tables.

## Verify

```bash
curl -s http://127.0.0.1:8091/api/config | python3 -m json.tool
curl -s http://127.0.0.1:8091/api/anti-spoof/status | python3 -m json.tool
curl -s http://127.0.0.1:8091/api/anti-spoof/report | python3 -m json.tool
docker compose logs --tail=100 api worker
```

Open `http://<HYPERVISOR_IP>:3001` and confirm **RGB presentation-attack lab** appears below
**Calibration evidence**.

## First acceptance sequence

1. Run one live test for Max and confirm `live accepted`.
2. Run a printed-photo test and confirm either `attack detected` or, if it completes, `missed attack`.
3. Repeat with a phone photo and phone video.
4. Confirm normal recognition resumes after each test.
5. Export `/api/anti-spoof/tests.csv` and confirm it contains no image data.

Do not tune the challenge values after a single result. Collect at least three trials per attack type
and three live trials per enrolled volunteer first.
