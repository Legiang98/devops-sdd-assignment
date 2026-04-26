"""Auto-generated from spec. Do not edit manually."""

SCHEMA_VERSION = '1.0.0'
CHANGE_ID = 'INV-FINANCE-APPROVAL'
SERVICE = 'invoice-workflow-service'
BASELINE_STAGES = ['system']
NEW_STAGE_NAME = 'finance'
NEW_STAGE_THRESHOLD = 5000
API_ENDPOINTS = ['POST /invoices', 'GET /invoices/{invoice_id}', 'POST /invoices/{invoice_id}/approve']
REJECT_ENDPOINT_ENABLED = False
