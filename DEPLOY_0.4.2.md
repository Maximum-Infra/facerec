# FaceRec v0.4.2 — Raspberry Pi lab sound actions

This release adds an optional non-blocking notification webhook for stable `recognized` and `unknown` events. It does not authorize or open a door, does not use GPIO, and does not change recognition thresholds, anti-spoof behavior, retention data, the database schema or the VPN-safe Docker network.

## Required Pi files

```text
/home/pi/Audio/facerec-wave.wav
/home/pi/Audio/facerec-wrong.wav
/home/pi/.node-red/environment
```

Import `integrations/node-red/facerec-event-flow.json` into Node-RED and deploy it. The flow exposes authenticated `POST /facerec/event` and accepts only requests from `<HYPERVISOR_IP>` or Pi-local diagnostics.

## Deploy FaceRec

Before extraction, copy the Node-RED token to the hypervisor over SSH:

```bash
cd /opt/facerec

scp \
  pi@<PI_IP>:/home/pi/.node-red/facerec-webhook-token.txt \
  .facerec-webhook-token

chmod 600 .facerec-webhook-token
cp -a .env .env.before-v0.4.2-20260909.bak
```

Extract the release without replacing `.env`:

```bash
sudo tar -xzf ~/Documents/FaceRec_Phase4B_Actions_0.4.2.tar.gz \
  -C /opt/facerec

sudo chown -R <deploy-user>:<deploy-user> /opt/facerec
```

Add the protected receiver configuration:

```bash
cd /opt/facerec

touch .env
sed -i '/^ACTION_WEBHOOK_/d' .env

ACTION_WEBHOOK_TOKEN_VALUE="$(cat .facerec-webhook-token)"

printf '\nACTION_WEBHOOK_ENABLED=true\n' >> .env
printf 'ACTION_WEBHOOK_URL=http://<PI_IP>:1880/facerec/event\n' >> .env
printf 'ACTION_WEBHOOK_TOKEN=%s\n' "$ACTION_WEBHOOK_TOKEN_VALUE" >> .env
printf 'ACTION_WEBHOOK_TIMEOUT_SECONDS=8\n' >> .env

unset ACTION_WEBHOOK_TOKEN_VALUE
chmod 600 .env .facerec-webhook-token
```

Build and recreate only FaceRec application containers. The database container and network remain running:

```bash
docker compose build api worker web
docker compose up -d --no-deps --force-recreate api

for attempt in {1..30}; do
  curl -fsS http://127.0.0.1:8091/api/health >/dev/null && break
  sleep 2
done

docker compose up -d --no-deps --force-recreate worker web

for attempt in {1..30}; do
  curl -fsS http://127.0.0.1:8091/api/worker/status >/dev/null && break
  sleep 2
done

docker compose ps api worker web
./scripts/smoke_test.sh
```

Verify the dispatcher without revealing the token:

```bash
curl -s http://127.0.0.1:8091/api/config | python3 -m json.tool

curl -s http://127.0.0.1:8091/api/worker/status |
  python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["action_webhook"], indent=2))'
```

Expected before the first recognition:

```json
{
  "enabled": true,
  "state": "running",
  "url": "http://<PI_IP>:1880/facerec/event",
  "queued": 0,
  "last_success_at": null,
  "last_suppressed_at": null,
  "last_error": null
}
```

After a recognized or unknown event, `last_success_at` should be populated. If Node-RED is unavailable, FaceRec recognition continues and `last_error` records delivery status.
