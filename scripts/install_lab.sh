#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
cd "${project_dir}"

command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
docker compose version >/dev/null

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created .env from the confirmed Minrray lab settings"
fi

"${script_dir}/download_models.sh"
docker compose config --quiet
docker compose up -d --build

echo "Waiting for FaceRec API"
for _ in $(seq 1 40); do
  if curl --fail --silent --output /dev/null http://127.0.0.1:8091/api/health; then
    break
  fi
  sleep 2
done

docker compose ps
host_address="$(hostname -I | awk '{print $1}')"
echo "FaceRec UI: http://${host_address}:3001"
echo "FaceRec API: http://${host_address}:8091/api/health"
