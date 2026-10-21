#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
model_dir="${project_dir}/models"

mkdir -p "${model_dir}"

download_model() {
  local filename="$1"
  local url="$2"
  local minimum_size="$3"
  local expected_sha256="$4"
  local destination="${model_dir}/${filename}"
  local temporary="${destination}.download"

  if [[ -f "${destination}" ]] && [[ "$(stat -c %s "${destination}")" -ge "${minimum_size}" ]]; then
    if echo "${expected_sha256}  ${destination}" | sha256sum --check --status; then
      echo "Model already present and verified: ${filename}"
      return
    fi
    echo "Existing model checksum is invalid; downloading a clean copy: ${filename}"
  fi

  echo "Downloading ${filename}"
  curl --fail --location --retry 3 --connect-timeout 15 --output "${temporary}" "${url}"
  if [[ "$(stat -c %s "${temporary}")" -lt "${minimum_size}" ]]; then
    echo "Downloaded file is unexpectedly small: ${filename}" >&2
    rm -f "${temporary}"
    exit 1
  fi
  if ! echo "${expected_sha256}  ${temporary}" | sha256sum --check --status; then
    echo "Downloaded model checksum does not match the pinned official model: ${filename}" >&2
    rm -f "${temporary}"
    exit 1
  fi
  mv "${temporary}" "${destination}"
}

download_model \
  "face_detection_yunet_2023mar.onnx" \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
  200000 \
  "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

download_model \
  "face_recognition_sface_2021dec.onnx" \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx" \
  30000000 \
  "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"

(
  cd "${model_dir}"
  sha256sum face_detection_yunet_2023mar.onnx face_recognition_sface_2021dec.onnx > MODEL_SHA256SUMS
)

echo "Models ready in ${model_dir}"
cat "${model_dir}/MODEL_SHA256SUMS"
