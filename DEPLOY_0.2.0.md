# FaceRec v0.2.0 upgrade

This upgrade adds Phase 2 calibration sessions and preserves the existing PostgreSQL volume,
employees, templates, recognition events and live `.env` configuration.

## Back up the current checkpoint

```bash
cd /opt/facerec

cp -a .env .env.phase1-calibrated-20260826.bak
docker compose exec -T db pg_dump -U facerec -d facerec \
  > facerec-phase1-before-v0.2.0.sql
```

## Install the source package

Copy `FaceRec_Phase2_Calibration_0.2.0.tar.gz` to the hypervisor, then:

```bash
cd /opt/facerec

sudo tar -xzf ~/Documents/FaceRec_Phase2_Calibration_0.2.0.tar.gz \
  -C /opt/facerec
sudo chown -R <deploy-user>:<deploy-user> /opt/facerec

docker compose up -d --build api worker web
docker compose ps
./scripts/smoke_test.sh
```

The API creates the two new calibration tables during startup. It does not alter or delete the
existing employee, template or recognition-event tables.

## Verify Phase 2

```bash
curl -s http://127.0.0.1:8091/api/health | python3 -m json.tool
curl -s 'http://127.0.0.1:8091/api/calibration/sessions?limit=1' \
  | python3 -m json.tool
curl -s http://127.0.0.1:8091/api/worker/status | python3 -m json.tool
```

Open `http://<HYPERVISOR_IP>:3001` and confirm that **Calibration evidence** appears below the live
scanner and employee panels.

## Use a second volunteer as an impostor participant

1. Start a calibration session.
2. Confirm the scanner shows **No face**.
3. Disable a second enrolled volunteer with their employee toggle. Do not delete them.
4. Wait up to 10 seconds for **Templates loaded** to change from 60 to 45.
5. Choose **Unknown / disabled**, enter `Volunteer B disabled`, select pose and distance, and arm the attempt.
6. The volunteer enters once, receives a decision, and leaves until **No face** returns.
7. Repeat at least three attempts so an impostor score distribution exists.
8. Re-enable the volunteer and wait for **Templates loaded** to return to 60.

Deleting the volunteer removes their 15 templates. Disabling them preserves the templates for immediate restoration.
