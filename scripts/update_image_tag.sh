#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <SERVICE_MANIFEST_DIR> <IMAGE_REPOSITORY> <IMAGE_TAG>"
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_MANIFEST_DIR="$ROOT/$1"
IMAGE_REPOSITORY="$2"
IMAGE_TAG="$3"
OUT_FILE="$SERVICE_MANIFEST_DIR/image-tag.yaml"
DEPLOYMENT_FILE="$SERVICE_MANIFEST_DIR/deployment.yaml"
POST_DEPLOY_JOB_FILE="$SERVICE_MANIFEST_DIR/post-deploy-evaluation-job.yaml"

if [ ! -f "$DEPLOYMENT_FILE" ]; then
  echo "Deployment manifest not found: $DEPLOYMENT_FILE"
  exit 1
fi

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

if [ -f "$POST_DEPLOY_JOB_FILE" ]; then
  python3 - "$POST_DEPLOY_JOB_FILE" "$IMAGE_TAG" <<'PY'
from pathlib import Path
import re
import sys

job_path = Path(sys.argv[1])
image_tag = sys.argv[2]
text = job_path.read_text(encoding="utf-8")

text, current_count = re.subn(
    r'(\n\s*-\s*name:\s*CURRENT_VERSION\s*\n\s*value:\s*).*$',
    rf'\g<1>{image_tag}',
    text,
    count=1,
    flags=re.MULTILINE,
)
if current_count == 0:
    raise SystemExit("Could not find CURRENT_VERSION env in post-deploy job manifest")

text, change_count = re.subn(
    r'(\n\s*-\s*name:\s*CHANGE_ID\s*\n\s*value:\s*).*$',
    rf'\g<1>{image_tag}',
    text,
    count=1,
    flags=re.MULTILINE,
)
if change_count == 0:
    raise SystemExit("Could not find CHANGE_ID env in post-deploy job manifest")

annotation_pattern = r'(\n\s*argocd\.argoproj\.io/hook-delete-policy:\s*BeforeHookCreation,HookSucceeded\s*\n)'
annotation_line = f'    devops.ssd/change-id: {image_tag}\n'

if "devops.ssd/change-id:" in text:
    text, annotation_count = re.subn(
        r'(^\s*devops\.ssd/change-id:\s*).*$',
        rf'\g<1>{image_tag}',
        text,
        count=1,
        flags=re.MULTILINE,
    )
else:
    text, annotation_count = re.subn(
        annotation_pattern,
        rf'\g<1>{annotation_line}',
        text,
        count=1,
        flags=re.MULTILINE,
    )
if annotation_count == 0:
    raise SystemExit("Could not update devops.ssd/change-id annotation in post-deploy job manifest")

job_path.write_text(text, encoding="utf-8")
print(f"Updated post-deploy job in {job_path} -> change-id/current-version {image_tag}")
PY
fi
