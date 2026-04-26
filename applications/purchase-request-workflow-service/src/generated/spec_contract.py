"""Auto-generated from spec. Do not edit manually."""

SCHEMA_VERSION = '1.0.0'
CHANGE_ID = 'PURCHASE-MANAGER-APPROVAL'
SERVICE = 'purchase-request-workflow-service'
BASELINE_STAGES = ['requester']
NEW_STAGE_NAME = 'manager'
NEW_STAGE_THRESHOLD = 1000
API_ENDPOINTS = ['POST /purchase-requests', 'GET /purchase-requests/{request_id}', 'POST /purchase-requests/{request_id}/approve']
REJECT_ENDPOINT_ENABLED = False
