# FaceRec v0.4.0 — Phase 4A retention and audit

This release preserves the existing `.env`, PostgreSQL volume, employees, templates and Phase 3 evidence. PostgreSQL creates the new `retention_policy` and `audit_log` tables when the API starts.

## Before deployment

```bash
cd /opt/facerec

cp -a .env .env.phase3-accepted-070-20260831.bak

docker compose exec -T db pg_dump -U facerec -d facerec \
  > facerec-phase3-accepted-070-20260831.sql

sha256sum \
  .env.phase3-accepted-070-20260831.bak \
  facerec-phase3-accepted-070-20260831.sql
```

## Deploy

After copying `FaceRec_Phase4_Admin_Privacy_0.4.0.tar.gz` to `~/Documents`:

```bash
cd /opt/facerec

sudo tar -xzf ~/Documents/FaceRec_Phase4_Admin_Privacy_0.4.0.tar.gz \
  -C /opt/facerec

sudo chown -R <deploy-user>:<deploy-user> /opt/facerec

docker compose build api worker web

# Recreate the complete FaceRec network cleanly. Do not add -v;
# the facerec-db volume and all database content are preserved.
docker compose down --remove-orphans
docker compose up -d db api

for attempt in {1..30}; do
  curl -fsS http://127.0.0.1:8091/api/health >/dev/null && break
  sleep 2
done

docker compose up -d worker web

docker compose ps
./scripts/smoke_test.sh
```

## Verify

```bash
curl -s http://127.0.0.1:8091/api/config | python3 -m json.tool
curl -s http://127.0.0.1:8091/api/admin/retention | python3 -m json.tool
curl -s 'http://127.0.0.1:8091/api/admin/audit?limit=10' | python3 -m json.tool
docker compose logs --since=10m --tail=150 api worker
```

Confirm `match_threshold` remains `0.7`. In the dashboard, verify the new **Administration & privacy** panel shows automatic retention and the audit trail. Do not click **Run now** until the displayed retention periods are acceptable.
