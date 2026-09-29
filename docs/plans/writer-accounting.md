# Durable writer accounting

Plan: implement idempotent outer reservations and lookup before integrating writer crash recovery; count subordinate API calls once toward the global limit; preserve actual overrun bills and attempt denominators. Isolated branch: codex/official-writer.

The Store API adds an opt-in idempotent request key, rejecting conflicting amounts. Existing model calls retain their semantics. Writer child events use stable IDs for deduplication; costs/tokens are billed only through the parent. Tests cover duplicate child receipts, budget enforcement, reserve interruption and identical settlement replay. The parent lifecycle and accounting module follow in a separate focused commit.

Independent reviewer workflow_audit approved the idempotent-reservation and durable-settlement mechanism; root reviews inherited subordinate-count integration separately.
