#!/usr/bin/env bash
set -euo pipefail

web_url="${FACEREC_WEB_URL:-http://127.0.0.1:3001}"
api_url="${FACEREC_API_URL:-http://127.0.0.1:8091}"

echo "Checking API health"
curl --fail --silent --show-error "${api_url}/api/health" | python3 -m json.tool

echo "Checking employee API"
curl --fail --silent --show-error "${api_url}/api/employees" | python3 -m json.tool

echo "Checking recognition worker and action dispatcher"
curl --fail --silent --show-error "${api_url}/api/worker/status" | python3 -m json.tool

echo "Checking calibration API"
curl --fail --silent --show-error "${api_url}/api/calibration/sessions?limit=1" | python3 -m json.tool

echo "Checking RGB anti-spoof evidence API"
curl --fail --silent --show-error "${api_url}/api/anti-spoof/report" | python3 -m json.tool
curl --fail --silent --show-error "${api_url}/api/anti-spoof/status" | python3 -m json.tool

echo "Checking retention and audit APIs"
curl --fail --silent --show-error "${api_url}/api/admin/retention" | python3 -m json.tool
curl --fail --silent --show-error "${api_url}/api/admin/audit?limit=3" | python3 -m json.tool

echo "Checking web UI"
curl --fail --silent --show-error --output /dev/null "${web_url}/"

echo "Checking MJPEG response"
set +e
curl --fail --silent --show-error --max-time 4 --output /dev/null "${web_url}/stream/live.mjpg"
stream_result=$?
set -e
if [[ "${stream_result}" -ne 0 ]] && [[ "${stream_result}" -ne 28 ]]; then
  exit "${stream_result}"
fi

echo "FaceRec smoke test passed"
