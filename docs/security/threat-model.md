# Threat model (as built)

IntentGuard is a research prototype that runs only against a simulated payment provider
(`backend/paysim`). This page states what the code assumes, what it guarantees, which security
controls are implemented, and what is still open. The target security baseline is
[docs/SECURITY.md](../SECURITY.md); section numbers below refer to it.

## The agent is an untrusted caller

The AI agent may be wrong, in ways that are honest or adversarial:

- hallucinated or mis-scaled amounts (x10, rupees read as paise), wrong currency;
- near-miss identifiers (`ORD-2041` / `ORD-2014` / `ORD-2401`), the wrong customer;
- repeats after timeouts; restarts that re-derive the operation with a new request ID;
- several agent instances working the same ticket at once;
- prompt injection in the ticket text that steers the extracted proposal or the investigator.

The protocol does not try to make the agent correct. It makes the agent's output **irrelevant
unless it matches a durable operator authorization**, and it makes the gateway, not the agent,
the only party that submits, retries or reverses anything.

## Actors

| Actor | Trust | How the code treats it |
|---|---|---|
| AI agent | Untrusted | Service principal with no capabilities; a short-lived token scoped to intents or customers; every proposal is checked against the authorization |
| LLM (ticket extractor, investigator) | Untrusted output | Strict output schemas; output that does not parse is rejected, not repaired; investigator recommendations pass a deterministic policy gate |
| Operator, reviewer, admin | Authenticated, role-limited | Email and password, RBAC per endpoint, separation of duties, every action audited |
| Provider responses and webhooks | Webhooks untrusted; provider lookups trusted | Webhooks must be signed and fresh, and are treated as hints: the gateway re-fetches the transaction |
| Network attacker | Untrusted | Local-only deployments in this repository; no TLS (see [Not implemented](#not-implemented)) |

## Isolation

| Boundary | How it is enforced in this repository |
|---|---|
| Credentials | The agent holds only its scoped JWT. It has no provider credentials. The gateway is the only component configured with the provider (`PAYMENT_SERVICE_URL`, or the connection stored with `PUT /admin/providers/paysim`) |
| API surface | With its token an agent can submit proposals for its scoped intents and read them (`GET /intents`, `/intents/{id}`, `/timeline`, `/history`), and call `GET /auth/me`. Every other endpoint is `403 FORBIDDEN` for it. The agent endpoint (`POST /intents/{id}/agent`) runs extraction inside the gateway, is open to humans only, and submits through the same engine path |
| Code path | Only the engine creates or cancels provider transactions (`IntentGuard._execute` and `recover`, including retries), always with parameters from a recorded attempt or a re-read effect. Matching runs and investigator evidence only read |
| LLM | The extractor maps ticket text to proposal fields; the investigator maps an evidence bundle to a classification and one recommended action. Neither has tools, database access or provider access |
| Network | `scripts/start.bat` and the `Makefile` bind the gateway, the provider and the Vite dev server to 127.0.0.1. In Docker all services share one network; the provider (8001) and PostgreSQL (5432) are published on the host's loopback interface only (127.0.0.1). The provider API has no authentication, so isolating an *external* agent process from it would have to come from deployment (network policy, credentials held only by the gateway). That is not demonstrated here |

## Implemented controls

### Authentication (SECURITY.md section 3)

Code: [`backend/gateway_api/security.py`](../../backend/gateway_api/security.py),
[`routers/auth.py`](../../backend/gateway_api/routers/auth.py). Endpoint details:
[../architecture/api.md](../architecture/api.md#authentication).

- **Passwords.** Hashed with argon2id (argon2-cffi `PasswordHasher` defaults); at least 12
  characters when set (`422 WEAK_PASSWORD`). Wrong email and wrong password give the same
  `401 INVALID_CREDENTIALS`. Agent principals have no password and cannot log in.
- **Lockout and rate limits.** 5 consecutive failures lock the account for 900 s
  (`429 ACCOUNT_LOCKED`). Logins are limited to 20 per minute per client IP, and every
  authenticated request to 1200 per minute per principal (`429 RATE_LIMITED`, with `Retry-After`).
- **Access tokens.** JWTs, HS256, with an explicit algorithm allow-list checked on the header
  before verification, so `alg: none` and HS512 are refused. `exp`, `iat`, `iss`, `aud`, `sub` and
  `jti` are required, with 30 s leeway. Lifetime: 15 minutes for users, at most 5 minutes for
  agents.
  - `JWT_SECRET` must be at least 32 bytes or the gateway does not start. If it is empty, a random
    per-process secret is used (development only); `scripts/init_env.py` fills one in.
- **Per-request checks.** Every request re-checks that the user still exists, is active and has the
  token's role, so a role change or deactivation ends existing sessions at once. Agent tokens are
  also checked against `service_tokens`, so an admin can revoke one by `jti`.
- **Refresh tokens.** Opaque, 256-bit, stored only as SHA-256 hashes, rotated on every use.
  - Presenting an already-rotated token revokes the whole family (`401 REFRESH_TOKEN_REUSED`,
    audited as `auth.refresh_reuse_detected`).
  - Lifetime 7 days per token, 30 days per family.
  - Logout revokes the family. A role change, deactivation or password change revokes all of the
    user's refresh tokens.
- **Browser storage** (SECURITY.md 3.4). The refresh token is an `HttpOnly`, `Secure`,
  `SameSite=Strict` cookie scoped to `/api/auth`, and is never put in a response body for a
  browser. A refresh that uses the cookie must carry `X-IntentGuard-CSRF: 1`
  (`403 CSRF_REQUIRED`). The dashboard keeps the access token in memory only.

### Authorization (SECURITY.md section 4)

- **RBAC.** Capabilities per role are fixed in `CAPABILITIES`, and every endpoint checks one with
  `require(...)` on the server. The agent role has no capabilities; agents act only through
  scopes such as `proposals:create:INT-1001` or `intents:read:customer:C-17`.
- **Authority at proposal time.** The authorizing operator is re-checked when a proposal arrives
  (`OPERATOR_NOT_PERMITTED` if deactivated, or no longer permitted the operation or the amount).
- **Separation of duties.** The user who authorized an intent cannot resolve its review case
  (`403 SEPARATION_OF_DUTIES`). This is a policy, on by default.
- **Admin policies.** A kill switch (every new proposal is held for review, with no provider
  call) and a maximum amount (checked at authorization and at proposal time). Both are off by
  default, audited when changed, and survive restarts.

### Input validation (SECURITY.md section 6)

- Every gateway request body is a Pydantic model with `extra="forbid"`: unknown fields are
  `422 VALIDATION_ERROR`, and a body that is not JSON is `400 MALFORMED_REQUEST`.
- Identifiers must match `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$`, and currencies are three letters.
- Amounts are `Decimal`, `> 0`, at most 18 digits, and are converted to minor units exactly. More
  decimals than the currency allows, or an unsupported currency, is `422 INVALID_AMOUNT`, never
  rounded.
- Near-miss identifiers are compared exactly against the authorization.
- Database access goes through SQLAlchemy. The only literal SQL is constant statements with bound
  parameters.

### Webhooks (SECURITY.md section 7)

[`backend/gateway_api/webhooks.py`](../../backend/gateway_api/webhooks.py):

- **Signature.** The `Paysim-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>." + raw body>` header
  is verified on the raw body with a constant-time comparison, before the body is parsed. With no
  secret configured, every event is rejected.
- **Freshness.** The timestamp must be within `WEBHOOK_TOLERANCE_S` (300 s), else
  `400 STALE_EVENT`.
- **Deduplication.** Events are stored once per `(provider, event_id)` (unique constraint).
- **Re-fetch.** The payload is a hint: the gateway re-fetches the transaction from the provider and
  absorbs what the provider says, so replayed, duplicated or out-of-order events cannot set state.
- The webhook secret can be set through the admin API. It is write-only: responses only report
  `webhook_secret_set`.

### LLM controls (SECURITY.md section 8)

- **Extractor.** Its output must be exactly `{operation, customer_id, order_id, amount, currency}`.
  Anything else, or a failed LLM call, is `422 INVALID_AGENT_OUTPUT` and nothing is submitted.
  A valid extraction is still only a proposal, checked like any other.
- **Investigator prompt.** A fixed system prompt; the evidence is passed between `<evidence>`
  delimiters as data, with the ticket truncated to 500 characters and labelled untrusted.
  Provider idempotency keys are not included.
- **Investigator output.** It must have exactly the four keys, use values from the fixed enums,
  and cite only references present in the bundle. Otherwise it is stored as rejected, answered
  with `422 INVALID_INVESTIGATOR_OUTPUT`, and cannot be applied.
- **Policy gate.** `backend/investigator/policy.py` decides from facts computed by code, not by
  the LLM, and confidence scores are not an input. Applying re-builds the evidence and re-runs the
  gate first.
- Investigations are allowed only for intents in an exception state. Every prompt and raw output
  is stored with the investigation.

### Audit trail (SECURITY.md section 9)

- **Hash chain.** `audit_logs` holds one hash chain per intent plus a `system` chain. Each entry's
  hash covers the previous hash and the canonical entry. `UNIQUE(chain_id, prev_hash)` stops a
  chain from forking.
- **Append-only.** Triggers reject `UPDATE` and `DELETE` (SQLite `audit_no_update` and
  `audit_no_delete`; PostgreSQL `audit_no_modify`, calling `audit_logs_append_only()`).
- **Verification.** `GET /api/audit/verify` (reviewer, admin) recomputes every chain and reports
  the first break.
- **What is logged.** Logins, failed logins and refresh-token reuse; decisions, attempts,
  provider observations, state changes, recovery actions and review resolutions; changes to
  users, agent tokens, policies and the provider connection; fault injection; investigations.
- **Redaction.** API output replaces keys such as `idempotency_key`, `password`, `token` and
  `webhook_secret` in audit payloads and review-case details with `"[redacted]"`.

### Secrets and supply chain (SECURITY.md section 10)

- `.env` is gitignored. `.env.example` has names and empty secret values.
  `scripts/init_env.py` generates `JWT_SECRET` and `WEBHOOK_SECRET` locally.
- CI ([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)) runs:
  - gitleaks over the full git history, with an allowlist of two exact fake literals used by
    `backend/tests` ([`.gitleaks.toml`](../../.gitleaks.toml));
  - `pip-audit` on `backend/requirements.txt` and `npm audit --audit-level=high` on the dashboard;
  - a quick benchmark whose safety gate (`scripts/check_bench_safety.py`) fails on any safety
    violation by the full protocol.

### Transport and platform (SECURITY.md section 11)

- **Gateway headers.** `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: DENY` and `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`
  (not on `/docs`, `/redoc` and `/openapi.json`). `Strict-Transport-Security` is sent only when the
  request arrived over HTTPS. Token responses carry `Cache-Control: no-store`.
- **Dashboard headers.** nginx ([`frontend/security-headers.conf`](../../frontend/security-headers.conf))
  sends a CSP with same-origin scripts, fonts and API calls and no inline scripts. `style-src`
  allows `'unsafe-inline'` for inline style attributes. It also sends `nosniff`, `DENY`,
  `no-referrer`, a `Permissions-Policy` and `Cross-Origin-Opener-Policy: same-origin`, and turns
  `server_tokens` off.
- **CORS.** An explicit origin list from `CORS_ORIGINS`, with credentials. No wildcard.
- **Containers.** Both run as non-root: the backend image as user `intentguard` (uid 10001), the
  dashboard on `nginx-unprivileged`, listening on 8080.
- **Local binding.** The Vite dev server binds to 127.0.0.1, and so do the gateway and provider
  when started by `scripts/start.bat` or the `Makefile`.
- **Simulator mode.** Simulator-only endpoints exist only with `SIMULATOR_MODE=true`. Otherwise
  the gateway's `/api/dev/*` and the provider's `/v1/faults` return 404. The code default is
  `false`; `.env.example` and `docker-compose.yml` set it to `true` because they are sandbox
  setups.

## Invariants

| # | Invariant | Enforced by | Checked by |
|---|---|---|---|
| I1 | A proposal executes only if operation, customer, order, currency and amount equal the intent exactly, and the operator is still active and permitted | `checks.binding_findings`, `authority_findings` | `test_protocol_spec.py` (`test_amount_exceeding_authorization_is_blocked`, `test_wrong_order_is_blocked`, `test_revoked_operator_blocks_execution`), `test_intent_binding_off_executes_hallucinated_amount` |
| I2 | At most one live intended effect per intent | Stable key `ig-<intent>-g<n>`; state checks; decide and reserve serialized under the intent lock; partial unique index `uq_one_live_intended_effect` | `test_concurrent_agents_produce_exactly_one_effect` (2, 4, 8 agents), `test_restart_with_new_request_id_cannot_cause_a_second_effect`, property P1 |
| I3 | The live total on an order never exceeds the order value | `EXCEEDS_REMAINING_BALANCE` check across intents; the provider's own balance check | `test_remaining_order_balance_is_enforced_by_the_gateway`, `test_balance_and_ownership_are_enforced_by_the_provider` |
| I4 | An attempt is durable before the provider is called | `_reserve` commits `SUBMITTING` before `_execute` | `test_gateway_crash_is_recovered_on_restart_with_one_effect` (both crash points) |
| I5 | An unknown outcome is never treated as failure; absence counts only after the absence window and a successful search | `_reconcile` | `test_timeout_marks_unknown_and_never_retries_blindly`, `test_absence_window_prevents_premature_retry_under_delayed_visibility`, `test_unknown_states_are_never_reported_as_failed` |
| I6 | `COMPLETED` is reported only when exactly the intended effect is observed at the provider | `_derive` uses the effects ledger only | `test_confirmed_refund_is_verified_and_completed`, properties P3 and P4 |
| I7 | A reversal or cancellation is reported only after the provider shows `CANCELLED` | `recover` reads back after every cancel | `test_incorrect_pending_refund_is_cancelled_and_verified`, `test_incorrect_completed_refund_is_escalated_not_reported_reversed`, `test_cancel_of_pending_refund_is_verified_at_the_provider`, `test_state_aware_recovery_off_claims_reversal_that_never_happened` |
| I8 | Every live unintended effect is either reversed or escalated with its amount | `recover`, review cases with `discrepancy_minor` | Properties P2 and P4 |
| I9 | History cannot be rewritten undetected | Append-only triggers, hash chains, `UNIQUE(chain_id, prev_hash)` | `test_audit_log_is_append_only_and_tamper_evident` (SQLite and PostgreSQL), property P5 |
| I10 | An agent token acts only on the intents or customers it is scoped to, and stops working when revoked | `Principal.scoped_to`, `require_intent_access`, the empty agent capability set, the `service_tokens` check | `test_agent_token_is_scoped_to_its_intent`, `test_customer_scoped_agent_token`, `test_revoked_agent_token_stops_working`, `test_agents_cannot_log_in_and_must_be_scoped` |
| I11 | LLM output changes nothing unless it passes the schema and, for the investigator, the policy gate on current evidence | Strict parsers, `investigator/policy.py`, the re-check in `apply_investigation` | `test_prompt_injection_cannot_produce_an_effect`, `test_retry_is_refused_while_absence_is_unverified`, `test_invalid_output_is_rejected_not_repaired`, `test_malformed_llm_output_is_rejected_not_repaired` |
| I12 | The user who authorized an intent cannot resolve its review case (while the policy is on) | `resolve_review` | `test_separation_of_duties_blocks_the_authorizing_operator`, `test_separation_of_duties_over_http` |
| I13 | A webhook changes nothing without a valid, fresh signature, and a valid one only triggers a re-fetch | `webhooks.verify`, unique event id, `engine.observe` | `test_bad_signature_and_stale_timestamp_are_rejected`, `test_duplicate_and_delayed_deliveries_are_safe`, `test_out_of_order_events_converge_on_the_provider_state` |

The properties P1 to P5 are in
[`backend/tests/test_safety_properties.py`](../../backend/tests/test_safety_properties.py)
(Hypothesis, arbitrary faults, proposals, crashes and restarts). The backend suite runs in CI on
SQLite and on PostgreSQL 16, so the PostgreSQL row locks and the PL/pgSQL audit trigger are
exercised too.

## Assumptions

- **The gateway and its database are trusted.** The audit chain detects rewriting after the fact.
  It does not stop an attacker with database access from appending false events, or from
  rewriting a whole chain consistently: the latest hash is not anchored anywhere outside the
  database.
- **The provider is honest.** The gateway treats the provider's lookups and ledger as ground
  truth. Webhook payloads are not trusted, but the transaction re-fetched from the provider is.
- **Lookup by id is strongly consistent, and search lags by less than the absence window.** The
  absence window is `absence_window_s`, 30 s by default.
  - If search hides a transaction for longer, the gateway can wrongly conclude "verified absent"
    and retry.
  - The code limits the damage. It records `attempt.absence_assumption_violated` when such a
    transaction appears. It watches an intent that completed after more than one attempt, or after
    an attempt error, for `2 x absence_window_s`, and recovers or escalates a late duplicate.
  - The property test includes a 120 s visibility lag to exercise this.
- **Provider idempotency holds.** A repeated key with the same parameters returns the original
  transaction within the key's lifetime (24 h in paysim).
- **One gateway process.** The worker, the rate limiter and the in-process state run in one
  process. Row locks and submission leases are designed for several gateways on one database, but
  that is not tested.
- **Shared secrets stay secret.** `JWT_SECRET` and the webhook secret are known only to the
  gateway (and, for the webhook secret, the provider).

## Not implemented

These are open. Each is either a gap against docs/SECURITY.md or a known weakness of the current
code.

- **MFA** for reviewers and admins, a breach-list password check, and SSO (3.5): not implemented.
- **TLS and HSTS in a real deployment** (11): not implemented. Nothing in the repository
  terminates TLS. The gateway sends HSTS only for HTTPS requests, and the nginx HSTS line is
  commented out until a TLS-terminating proxy exists.
- **A real payment provider**: not implemented. The only provider is the paysim simulator, and no
  real provider credentials are handled anywhere.
- **Provider API authentication**: none. The mock provider accepts any caller that can reach it,
  and its `/v1/ledger` is not gated by `SIMULATOR_MODE`. Docker publishes it, and PostgreSQL with
  the fixed development password from `docker-compose.yml`, on 127.0.0.1 only, so other machines cannot
  reach them; any local process still can.
- **Asymmetric JWT signing** (RS256 or EdDSA, 3.2): not implemented. HS256 with a shared secret
  of at least 32 bytes is used.
- **Immediate revocation of access tokens after a password change**: not implemented. Refresh
  tokens are revoked at once, but an access token already issued stays valid until it expires
  (up to 15 minutes). Role changes and deactivation do take effect on the next request.
- **Rate limiting.**
  - The limiter is in process memory: it resets on restart and is not shared between processes.
  - Only login is limited per client IP. Refresh, logout and the webhook endpoint are not limited.
  - The IP is the TCP peer address, and the Docker setup configures no trusted proxy headers.
    Behind nginx every login therefore appears to come from the proxy, and shares one limit.
- **Account enumeration**: partly prevented. Login always runs the password hash, so timing does not
  depend on whether the email exists, and wrong passwords get one generic message. But a locked
  account answers `429 ACCOUNT_LOCKED` where an unknown email answers `401`.
- **Request size limits in the gateway**: not implemented. Only nginx in Docker limits bodies,
  to 1 MB.
- **Tenancy and row-level security** (5): not implemented. The system is single-tenant.
- **Simulator mode in shipped configurations.** `.env.example` and `docker-compose.yml` enable
  `SIMULATOR_MODE`, and there is no production configuration. With it on, any operator can inject
  faults and read the simulator's full ledger through `GET /api/dev/ledger` (provider idempotency
  keys are redacted there).
- **Operational security** (12): not implemented. There is no alerting, no scheduled audit-chain
  verification, and no external anchoring of the audit hash. `GET /api/metrics/summary` and
  `GET /api/audit/verify` exist for manual checks.
- **Local pre-commit secret scanning** (10): not set up. Secret scanning runs in CI only.
- **Denial of service** beyond the rate limits: not addressed.
