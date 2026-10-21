# FaceRec v0.3.1 cleanup-controls patch

This patch adds isolated **Clear** buttons for calibration evidence, RGB presentation-attack
evidence and recognition events. It does not modify `.env`, employees, templates or the database
volume. The live `MATCH_THRESHOLD=0.70` experiment remains unchanged.

## Install

Copy `FaceRec_Phase3_RGB_Lab_0.3.1.tar.gz` to the hypervisor, then:

```bash
cd /opt/facerec

sudo tar -xzf ~/Documents/FaceRec_Phase3_RGB_Lab_0.3.1.tar.gz -C /opt/facerec
sudo chown -R <deploy-user>:<deploy-user> /opt/facerec

docker compose build api web
docker compose up -d --no-deps api

for attempt in {1..30}; do
  curl -fsS http://127.0.0.1:8091/api/health >/dev/null && break
  sleep 2
done

docker compose up -d --no-deps web

# Recreate (do not rebuild) the worker so the live MATCH_THRESHOLD=0.70 is loaded.
docker compose up -d --no-deps --force-recreate worker

for attempt in {1..30}; do
  curl -fsS http://127.0.0.1:8091/api/worker/status 2>/dev/null |
    python3 -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("model_ready") else 1)' \
    && break
  sleep 2
done

docker compose ps api worker web
./scripts/smoke_test.sh
```

Only the API and web images need rebuilding. The worker is recreated once without rebuilding so
it loads the changed `.env`; expect a brief camera-stream interruption while it reconnects.

## Verify

```bash
curl -s http://127.0.0.1:8091/api/config | python3 -m json.tool
```

Confirm `match_threshold` is `0.7`, refresh `http://<HYPERVISOR_IP>:3001`, and verify each of these
panels has a **Clear** button:

1. Calibration evidence
2. RGB presentation-attack lab
3. Recognition events

Each action asks for confirmation. Clear the three existing datasets before starting the new
0.70 test series. Do not clear an active session or challenge.
