"""
Data retention registry (P0.7b).

Defines WHICH tables can be purged by time-based retention and on WHICH timestamp
column. Core data (users, agents, tasks, knowledge, credentials) is deliberately
NOT here — that data leaves only through erase-tenant / erase-user, never through
automatic age-based deletion. Only operational logs are eligible.

Retention is OPT-IN: a table is purged for a tenant only when that tenant has an
enabled RetentionPolicy for it. No policy → kept forever (current behavior). This
is the safe default for a compliance product — we never surprise-delete a
regulated client's audit trail.
"""

# table_name → the timestamp column the cutoff is measured against.
RETENTION_ELIGIBLE: dict[str, str] = {
    "audit_log": "occurred_at",
    "activity_logs": "occurred_at",
    "agent_interactions": "occurred_at",
    "notifications": "created_at",
    "approval_requests": "requested_at",
}

# Recommended retention windows (days). NOT applied automatically — surfaced to the
# admin as guidance. audit_log is long for banking/insurance compliance; operational
# logs are shorter.
RECOMMENDED_RETENTION_DAYS: dict[str, int] = {
    "audit_log": 2555,          # ~7 years
    "activity_logs": 180,
    "agent_interactions": 180,
    "notifications": 90,
    "approval_requests": 365,
}

# Floor to stop a fat-fingered "0 days" from wiping a table on the next worker run.
MIN_RETENTION_DAYS = 1
