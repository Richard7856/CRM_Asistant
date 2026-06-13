"""
Compliance module (P0.7 — LFPDPPP).

Implements the data-subject rights that block selling to regulated clients (HDI):
- Right to be forgotten: erase a whole tenant (ordered delete + certificate)
  or anonymize a single user.
- Right of access / portability: export a tenant's or a user's data.
- Data classification registry: the single source of truth for what is PII,
  which also feeds the future LLM sensitivity router (Track L / L2).

Retention policy + automated cleanup worker is a fast-follow (P0.7b).
Encrypted backups are ops and live in P0.8.
"""
