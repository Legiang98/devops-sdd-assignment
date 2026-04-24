#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <IMAGE_REPOSITORY> <IMAGE_TAG>"
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_REPOSITORY="$1"
IMAGE_TAG="$2"
SERVICE_MANIFEST_DIR="$ROOT/devops/k8s/expense-workflow"
OUT_FILE="$SERVICE_MANIFEST_DIR/image-tag.yaml"
DEPLOYMENT_FILE="$SERVICE_MANIFEST_DIR/deployment.yaml"

cat > "$OUT_FILE" <<YAML
# Auto-updated by CI pipeline.
image:
  repository: ${IMAGE_REPOSITORY}
  tag: ${IMAGE_TAG}
YAML

echo "Updated GitOps image tag: ${OUT_FILE} -> ${IMAGE_REPOSITORY}:${IMAGE_TAG}"

python3 - "$DEPLOYMENT_FILE" "${IMAGE_REPOSITORY}:${IMAGE_TAG}" <<'PY'
from pathlib import Path
import re
import sys

deployment_path = Path(sys.argv[1])
full_image = sys.argv[2]
text = deployment_path.read_text(encoding="utf-8")

updated, count = re.subn(
    r"(^\s*image:\s*).*$",
    rf"\1{full_image}",
    text,
    count=1,
    flags=re.MULTILINE,
)
if count == 0:
    raise SystemExit("Could not find 'image:' field in deployment manifest")

deployment_path.write_text(updated, encoding="utf-8")
print(f"Updated deployment image in {deployment_path} -> {full_image}")
PY
