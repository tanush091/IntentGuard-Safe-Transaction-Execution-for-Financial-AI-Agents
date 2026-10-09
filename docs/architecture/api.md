# HTTP APIs (as built)

This page describes the HTTP endpoints exactly as the code serves them. The target contract is
[docs/API.md](../API.md); where the code differs from it, see
[Differences from docs/API.md](#differences-from-docsapimd) at the end.

Sources:

- Gateway: the routers in [`backend/gateway_api/routers/`](../../backend/gateway_api/routers/)
  (`auth.py`, `intents.py`, `recovery.py`, `reviews.py`, `webhooks.py`, `observability.py`,
  `admin.py`, `system.py`), request models in
  [`schemas.py`](../../backend/gateway_api/schemas.py), response shapes in
  [`serializers.py`](../../backend/gateway_api/serializers.py), roles and capabilities in
  [`security.py`](../../backend/gateway_api/security.py).
- Provider simulator: [`backend/provider_api/main.py`](../../backend/provider_api/main.py) on top of
  [`backend/paysim/`](../../backend/paysim/).

## Machine-readable schema

[`docs/api/openapi.json`](../api/openapi.json) is the gateway's OpenAPI schema (43 paths, 49
operations). It is exported from the code by `python scripts/export_openapi.py`. Two CI checks keep
it honest:

- `python scripts/export_openapi.py --check` (backend job in
  [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)) fails when the committed file differs
  from what the code produces.
- `npm run check:contract` ([`frontend/scripts/check-contract.mjs`](../../frontend/scripts/check-contract.mjs),
  frontend job) fails when a route in the dashboard's `ROUTES` table
  ([`frontend/src/api/endpoints.js`](../../frontend/src/api/endpoints.js)) is missing from the schema
  or has a different method.

The schema is reliable for paths, methods, query parameters and request bodies. It does not
describe authentication, the error envelope or response bodies; see
[What the OpenAPI schema does not say](#what-the-openapi-schema-does-not-say).

The running gateway also serves the schema and interactive docs at its root (not under `/api`):
http://127.0.0.1:8000/openapi.json, `/docs` and `/redoc`. The provider serves
http://127.0.0.1:8001/docs.

## Gateway API (port 8000)

### Conventions

- Every endpoint is under `/api`. `GET /health` is also served at the root (not in the schema) for
  launch scripts and container health checks.
- JSON bodies. Amounts are decimal strings in major units with an explicit currency (`"1500.00"`,
  `"INR"`). Internally everything is stored as integer minor units
  ([`backend/intentguard/money.py`](../../backend/intentguard/money.py)). Accepted currencies: INR,
  USD, EUR, GBP, JPY. An amount with more decimals than the currency has, or an unsupported
  currency, is `422 INVALID_AMOUNT`; nothing is rounded.
- Timestamps are ISO-8601 UTC with milliseconds: `2026-10-09T19:36:55.339Z`.
- Identifiers carry a prefix: `INT-1001`, `PRP-n` (proposal), `DEC-n` (decision), `ATT-001`,
  `EFF-n`, `RC-n` (review case), `INV-n`, `WH-n` (webhook event), `RUN-n`, `MM-n` (mismatch). Path
  parameters for review cases, investigations and mismatches accept the prefixed form or the bare
  number.
- A gateway decision (`ALLOW`, `REJECT`, `DUPLICATE`, `HOLD_FOR_REVIEW`) is an HTTP 200 body, never
  an error.
- The provider idempotency key (`ig-<intent>-g<generation>`) is never returned by the intent,
  history, timeline, audit or review endpoints. In audit payloads and review-case details, any key
  named `idempotency_key`, `password`, `password_hash`, `token`, `refresh_token` or `webhook_secret`
  is replaced by `"[redacted]"`. The one exception is the simulator-only `GET /dev/ledger`, which
  returns raw provider transactions.
- Every response carries `X-Request-ID`: the client's `X-Request-ID` (truncated to 64 characters)
  or a generated `req_<16 hex>`. The same value is the `request_id` of an error.
- CORS allows the origins in `CORS_ORIGINS` with credentials, the methods GET, POST, PUT, PATCH,
  DELETE and the headers `Authorization`, `Content-Type`, `Idempotency-Key`, `X-IntentGuard-CSRF`,
  `X-Request-ID`.

### Authentication

Every endpoint needs `Authorization: Bearer <access token>` except `POST /auth/login`,
`POST /auth/refresh`, `POST /auth/logout`, `POST /webhooks/{provider}` (signature), `GET /health`
and `GET /ready`.

**Access tokens** are JWTs signed with HS256 (`JWT_SECRET`, at least 32 bytes; the gateway refuses
to start with a shorter one). Claims: `iss` (`intentguard`), `aud` (`intentguard-api`), `sub`,
`role`, `scope` (list), `iat`, `exp`, `jti`, `typ` (`user` or `agent`). Decoding:

- the header's `alg` must be on the allow-list (`HS256`), checked before verification;
- `exp`, `iat`, `iss`, `aud`, `sub` and `jti` are required; 30 s clock leeway;
- on every request the user must still exist, be active and have the token's role; an agent
  token's `jti` must be in `service_tokens` and not revoked.

Users get 900 s tokens (`ACCESS_TOKEN_TTL_S`). For users the role decides what is allowed (the
`scope` claim lists the role's capabilities for information); for agents the token's scopes
decide. Failures: `401 UNAUTHENTICATED` (no bearer token, with `WWW-Authenticate: Bearer`),
`401 INVALID_TOKEN`, `401 TOKEN_EXPIRED`.

**Login.** `POST /auth/login` with `{email, password}`.

- Wrong email or wrong password: `401 INVALID_CREDENTIALS`, same message for both.
- Agent principals cannot log in.
- After `LOGIN_MAX_FAILURES` (5) consecutive failures the account is locked for `LOGIN_LOCKOUT_S`
  (900 s): `429 ACCOUNT_LOCKED` with `Retry-After`.
- Logins are rate limited to `LOGIN_RATE_LIMIT_PER_MINUTE` (20) per client IP:
  `429 RATE_LIMITED` with `Retry-After`.
- Response: `{access_token, token_type: "bearer", expires_in: 900, user: {id, email, name, role}}`
  with `Cache-Control: no-store`.

**Refresh tokens** are opaque 256-bit random strings, stored as SHA-256 hashes. Each is valid for
`REFRESH_TOKEN_TTL_S` (7 days) and a token family for at most `REFRESH_TOKEN_ABSOLUTE_S` (30 days).
Every use rotates the token. Presenting a token that was already rotated returns
`401 REFRESH_TOKEN_REUSED` and revokes the whole family (audited as `auth.refresh_reuse_detected`).
An unknown, revoked or expired token, or one whose user is inactive, is `401 INVALID_REFRESH_TOKEN`.

Login and refresh always set the cookie `ig_refresh` (`HttpOnly`, `SameSite=Strict`,
`Path=/api/auth`, `Max-Age` 604800, `Secure` unless `COOKIE_SECURE=false`). Whether the token also
appears in the body depends on the mode:

| Mode | Login request | Refresh request | Refresh token in the response body |
|---|---|---|---|
| Browser (cookie) | header `X-IntentGuard-CSRF: 1` | no body (or `refresh_token: null`), cookie, header `X-IntentGuard-CSRF: 1` | Never |
| API client (body) | no CSRF header | body `{"refresh_token": "..."}` | Yes |

A refresh that relies on the cookie without the CSRF header is `403 CSRF_REQUIRED`. The dashboard
uses cookie mode and keeps the access token in memory only
([`frontend/src/api/client.js`](../../frontend/src/api/client.js)).

**Logout.** `POST /auth/logout` revokes the family of the refresh token given in the body or the
cookie, deletes the cookie and returns 204. It needs no access token.

**Rate limit.** Every authenticated request counts against `RATE_LIMIT_PER_MINUTE` (1200) for its
principal: `429 RATE_LIMITED` with `Retry-After`. The limiter is a sliding one-minute window in
process memory.

### Roles, capabilities and agent scopes

`CAPABILITIES` in [`security.py`](../../backend/gateway_api/security.py). Each endpoint checks one
capability with `require(...)`. In the tables below, *operator+* means operator, reviewer and admin;
*reviewer+* means reviewer and admin.

| Capability | operator | reviewer | admin | agent |
|---|:-:|:-:|:-:|:-:|
| `intents:read`, `authorizations:create`, `proposals:create`, `agent:run`, `reconcile`, `cancel` | yes | yes | yes | no |
| `exceptions:read`, `exceptions:investigate`, `investigations:apply` | yes | yes | yes | no |
| `reviews:read`, `audit:read`, `metrics:read`, `orders:read`, `reconciliation:read` | yes | yes | yes | no |
| `dev` (simulator-only endpoints) | yes | yes | yes | no |
| `reviews:resolve`, `audit:verify`, `reconciliation:run`, `mismatches:resolve` | no | yes | yes | no |
| `admin` | no | no | yes | no |

The agent role has no capabilities. An agent acts only through the scopes in its service token,
issued by an admin (`POST /admin/service-tokens`):

- `proposals:create:<intent_id>` and `intents:read:<intent_id>`, or
- `proposals:create:customer:<customer_id>` and `intents:read:customer:<customer_id>`.

With those, an agent can call `POST /intents/{id}/proposals`, `GET /intents/{id}`,
`GET /intents/{id}/timeline`, `GET /intents/{id}/history` for scoped intents, `GET /intents`
(filtered to scoped intents) and `GET /auth/me`. Anything outside its scope is `403 FORBIDDEN`;
every endpoint guarded by `require(...)` is `403 FORBIDDEN` for an agent. Agent tokens live at most
`AGENT_TOKEN_MAX_TTL_S` (300 s) and can be revoked by `jti`. When an agent submits a proposal, its
`agent_id` is the token's subject, whatever the body says.

### Errors

Every error uses one envelope ([`errors.py`](../../backend/gateway_api/errors.py)):

```json
{"error": {"code": "VALIDATION_ERROR", "message": "request validation failed",
           "details": {"errors": [{"loc": ["body", "order_id"], "msg": "Field required", "type": "missing"}]},
           "request_id": "req_7b90d1b6b2ce4c3e"}}
```

| HTTP | Codes |
|---|---|
| 400 | `MALFORMED_REQUEST` (body is not valid JSON), `INVALID_CURSOR`, `INVALID_IDEMPOTENCY_KEY`, `INVALID_SIGNATURE`, `STALE_EVENT`, `MALFORMED_EVENT` |
| 401 | `UNAUTHENTICATED`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS`, `INVALID_REFRESH_TOKEN`, `REFRESH_TOKEN_REUSED` |
| 403 | `FORBIDDEN`, `CSRF_REQUIRED`, `SEPARATION_OF_DUTIES` |
| 404 | `NOT_FOUND` (unknown resource or path; every `/dev/*` path when `SIMULATOR_MODE` is off; an unknown webhook provider) |
| 405 | `METHOD_NOT_ALLOWED` |
| 409 | `STATE_CONFLICT`, `ILLEGAL_TRANSITION`, `ATTEMPT_IN_PROGRESS`, `NOT_CANCELLABLE`, `NO_VERIFIED_EFFECT`, `ALREADY_RESOLVED`, `ALREADY_APPLIED`, `ALREADY_EXISTS`, `NOT_AN_EXCEPTION`, `POLICY_REFUSED` |
| 422 | `VALIDATION_ERROR` (schema failures, unknown fields, bad `limit`, `window` or timestamp), `INVALID_AMOUNT`, `IDEMPOTENCY_KEY_REUSE`, `WEAK_PASSWORD`, `NO_TICKET`, `EXTRACTION_FAILED`, `INVALID_AGENT_OUTPUT`, `INVALID_INVESTIGATOR_OUTPUT`; authorization refusals from `POST /authorizations`: `OPERATOR_NOT_PERMITTED`, `OPERATOR_LIMIT_EXCEEDED`, `POLICY_LIMIT_EXCEEDED`, `ORDER_NOT_FOUND`, `CUSTOMER_MISMATCH`, `CURRENCY_MISMATCH`, `INVALID_AMOUNT` |
| 429 | `RATE_LIMITED`, `ACCOUNT_LOCKED` (both with `Retry-After` and `details.retry_after_s`) |
| 500 | `INTERNAL_ERROR`, `SCHEMA_MISMATCH` (the database was created by an earlier schema version) |
| 502 | `PROVIDER_ERROR` (simulator-only endpoints in `http` provider mode, when the provider answers 5xx; a provider 4xx is passed through with its status and this code) |
| 503 | `PROVIDER_UNAVAILABLE` (simulator-only endpoints in `http` provider mode, when the provider cannot be reached) |

A provider problem during a proposal, cancel or reconciliation is never an HTTP error: the call
returns 200 (or 202) and the intent state says what is known (`UNKNOWN`, `RECONCILING`,
`ESCALATED`, ...). `GET /ready` reports an unreachable dependency with its own 503 body, not the
envelope.

### Pagination

Lists that can grow use keyset pagination ([`pagination.py`](../../backend/gateway_api/pagination.py)):
`?limit=<1..200>&cursor=<opaque>`, default limit 50, newest first. The response is
`{"items": [...], "next_cursor": "<opaque>" | null}`. A limit outside 1..200 is
`422 VALIDATION_ERROR`; a cursor that does not decode is `400 INVALID_CURSOR`.

Paginated: `GET /intents`, `/exceptions`, `/reconciliation/runs`, `/reconciliation/mismatches`,
`/review-cases`, `/audit`, `/admin/users`. `GET /orders` and `GET /admin/service-tokens` return the
same shape with `next_cursor` always `null` (service tokens: the latest 200).

### Client `Idempotency-Key`

[`idempotency.py`](../../backend/gateway_api/idempotency.py). These POSTs accept an optional
`Idempotency-Key` header (1 to 128 characters, else `400 INVALID_IDEMPOTENCY_KEY`):
`/authorizations`, `/intents/{id}/cancel`, `/intents/{id}/proposals`, `/intents/{id}/agent`,
`/exceptions/{id}/investigate`, `/investigations/{id}/apply`, `/review-cases/{id}/resolve`.

- Keys are scoped per principal. The stored fingerprint is a hash of the path and the body.
- Same key, same path and body: the stored status and body are returned with
  `Idempotent-Replay: true`, and the handler does not run again.
- Same key, different path or body: `422 IDEMPOTENCY_KEY_REUSE`.
- Only successful responses are stored. Two concurrent requests with the same new key can both
  run; the second response is not stored.

This protects the API call only. Money safety does not depend on it: the provider idempotency key
is derived by the gateway from the intent and is never chosen by a client.

### Strict request bodies

Every gateway request model inherits `Strict` (`extra="forbid"`), so an unknown field is
`422 VALIDATION_ERROR`. Other limits in [`schemas.py`](../../backend/gateway_api/schemas.py):

- customer, order and user ids match `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$`; currency is three
  letters;
- amounts are decimals `> 0` (`>= 0` for user limits and the policy maximum) with at most 18
  digits;
- `ticket_text` up to 5000 characters, `rationale` and `note` up to 2000, passwords up to 1024. A
  password set through the admin API must have at least 12 characters (`422 WEAK_PASSWORD`).

Path and query parameters are not pattern-checked; an unknown id is simply `404 NOT_FOUND`.

### Endpoints

All paths are relative to `/api`.

#### Auth

| Method | Path | Access | Status | Purpose |
|---|---|---|---|---|
| POST | `/auth/login` | none (rate limited) | 200 | Email and password to access token and refresh token. Body `{email, password}` |
| POST | `/auth/refresh` | a refresh token | 200 | Rotate the refresh token, issue a new access token. Body `{refresh_token?}` |
| POST | `/auth/logout` | none | 204 | Revoke the refresh token's family and clear the cookie. Body `{refresh_token?}` |
| GET | `/auth/me` | any token, agents included | 200 | `{id, name, role, kind, scopes}` |

#### Authorizations and intents

| Method | Path | Access | Status | Purpose |
|---|---|---|---|---|
| POST | `/authorizations` | `authorizations:create` (operator+) | 201 | Create the operator authorization and its intent. The authenticated user is the authorizing operator |
| GET | `/intents` | `intents:read` (operator+); agents see scoped intents only | 200 | List intents; filters `state`, `customer_id`, `order_id`, `operation`, `created_from`, `created_to` (ISO-8601) |
| GET | `/intents/{intent_id}` | `intents:read` or agent scope | 200 | Intent with attempts, effects, proposals and their decisions, `open_review_case_id`, `verified` |
| GET | `/intents/{intent_id}/timeline` | `intents:read` or agent scope | 200 | Human-readable events from the intent's audit chain |
| GET | `/intents/{intent_id}/history` | `intents:read` or agent scope | 200 | Raw rows: proposals with decisions, attempts, effects, review cases, investigations, webhook events |
| POST | `/intents/{intent_id}/cancel` | `cancel` (operator+) | 202 | Cancel the intent; a pending effect is cancelled at the provider and verified first |
| POST | `/intents/{intent_id}/proposals` | `proposals:create` (operator+) or agent scope | 200 | The agent boundary: submit a structured proposal and get the gateway's decision |
| POST | `/intents/{intent_id}/agent` | `agent:run` (operator+) | 200 | Extract a proposal from the ticket text, then submit it through the same path |

`POST /authorizations` body (`AuthorizationIn`): `customer_id`, `order_id`, `operation`
(`REFUND` default, or `PAYMENT_AUTHORIZATION`), `authorized_amount`, `currency` (`INR` default),
`ticket_text?`, `metadata` (object). Response: `{intent_id, state, approval_status, created_at}`.
The engine refuses the authorization with a 422 when the operator is inactive or not permitted the
operation (`OPERATOR_NOT_PERMITTED`), the amount exceeds the operator's limit
(`OPERATOR_LIMIT_EXCEEDED`) or the admin policy maximum (`POLICY_LIMIT_EXCEEDED`), the order is
unknown (`ORDER_NOT_FOUND`), belongs to another customer (`CUSTOMER_MISMATCH`) or has another
currency (`CURRENCY_MISMATCH`), or the amount is not within `0 < amount <= order value`
(`INVALID_AMOUNT`).

`POST /intents/{intent_id}/proposals` body (`ProposalIn`): `request_id?` (recorded; not used for
idempotency), `agent_id?`, `operation`, `customer_id`, `order_id`, `amount`, `currency` (`INR`
default), `rationale`. Response:

```json
{"intent_id": "INT-1001", "proposal_id": "PRP-1", "decision": "REJECT",
 "reason": "AMOUNT_EXCEEDS_AUTHORIZATION",
 "reasons": ["AMOUNT_EXCEEDS_AUTHORIZATION", "EXCEEDS_REMAINING_BALANCE"],
 "findings": [{"check": "AMOUNT_EXCEEDS_AUTHORIZATION",
               "detail": "amount_minor: authorized 150000, proposed 1500000", "decision": "REJECT"},
              {"check": "EXCEEDS_REMAINING_BALANCE",
               "detail": "order value 500000, already used 0, proposed 1500000", "decision": "REJECT"}],
 "state": "AUTHORIZED", "attempt_id": null, "provider_transaction_id": null, "verified": false}
```

- `reason` is the first finding's check, or `null`; `findings` lists every check that fired.
- On `ALLOW` the attempt is executed and read back inside the request. `state` is then `EXECUTING`
  while the provider still reports the effect `PENDING` (the standalone provider settles after
  `PAYSIM_SETTLE_DELAY_S`, 3 s by default), `COMPLETED` once it has settled, `UNKNOWN` when the
  outcome is not known yet, `RECONCILING` after a definitive provider rejection, and `ESCALATED`
  when a wrong effect could not be reversed.
- On `DUPLICATE`, `provider_transaction_id` is the existing intended effect.
- `verified` is true when the state is `COMPLETED`, `EXECUTING` or `CANCELLED`. A state such as
  `UNKNOWN` with `verified: false` means "being verified", not "failed".

The checks behind the decision are listed in [overview.md](overview.md#gateway-checks).

`POST /intents/{intent_id}/agent` body (`AgentRunIn`): `ticket_text?`; without it the intent's
stored ticket is used (`422 NO_TICKET` if there is none).

- The extractor is the offline rule extractor, or an LLM when `LLM_PROVIDER` is `openai`, `ollama`
  or `gemini`.
- The extracted proposal is submitted with `agent_id` `support-agent`. The response is the proposal
  response plus
  `extraction: {source: "rules" | "llm", model, proposal: {operation, customer_id, order_id, amount, currency}}`.
- Rule extraction failure: `422 EXTRACTION_FAILED`. LLM output that is off-schema, or an LLM call
  that fails: `422 INVALID_AGENT_OUTPUT`. Nothing is submitted in either case, and the output is
  never repaired.

`POST /intents/{intent_id}/cancel` body (`CancelIn`, optional): `{note}`. The note is accepted but
not stored. The call runs synchronously despite the 202 and returns `{intent_id, state}`:

- `AUTHORIZED` or `RECONCILING`: `CANCELLED` at once.
- `EXECUTING` or `COMPLETED` with cancellable live effects (a pending refund, or a pending or
  completed authorization hold): `CANCEL_REQUESTED`, then a provider cancel and a read-back. The
  intent becomes `CANCELLED` only after the provider shows the effect `CANCELLED`. If the provider
  refuses, the intent is `ESCALATED` with a `CANCEL_REJECTED` review case. If the outcome of the
  cancel cannot be read, the intent stays `CANCEL_REQUESTED` and the worker retries, escalating
  with `CANCEL_UNVERIFIED` after `max_cancel_tries` (3).
- `IN_FLIGHT` or `UNKNOWN`: `409 ATTEMPT_IN_PROGRESS`.
- A completed refund: `409 NOT_CANCELLABLE`.
- Any other state: `409 STATE_CONFLICT`.

#### Reconciliation, exceptions and the investigator

| Method | Path | Access | Status | Purpose |
|---|---|---|---|---|
| POST | `/attempts/{attempt_id}/reconcile` | `reconcile` (operator+) | 200 | Run one reconciliation pass for the attempt's intent now |
| GET | `/reconciliation/runs` | `reconciliation:read` (operator+) | 200 | Worker and matching runs; filter `kind` (`WORKER`, `MATCHING`) |
| POST | `/reconciliation/runs` | `reconciliation:run` (reviewer+) | 202 | Start a matching run over all orders |
| GET | `/reconciliation/mismatches` | `reconciliation:read` (operator+) | 200 | Mismatches from matching runs and webhooks; filters `kind`, `status` (default `OPEN`, empty for all) |
| POST | `/reconciliation/mismatches/{mismatch_id}/resolve` | `mismatches:resolve` (reviewer+) | 200 | Mark a mismatch handled. Body `{note}`. `409 ALREADY_RESOLVED` |
| GET | `/exceptions` | `exceptions:read` (operator+) | 200 | Intents in `UNKNOWN`, `RECONCILING`, `DISCREPANCY`, `CANCEL_REQUESTED`, `ESCALATED`, most recently updated first, each with `latest_investigation` |
| POST | `/exceptions/{intent_id}/investigate` | `exceptions:investigate` (operator+) | 200 | Run the investigator (advisory) and store the result. No body |
| GET | `/investigations/{investigation_id}` | `exceptions:read` (operator+) | 200 | One investigation, including `prompt` and `raw_output` |
| POST | `/investigations/{investigation_id}/apply` | `investigations:apply` (operator+) | 200 | Apply a recommendation if the policy gate permits it now |

`POST /attempts/{attempt_id}/reconcile` returns
`{attempt_id, intent_id, outcome, intent_state, attempt_status, evidence[], next_action}`.
`evidence` lists provider lookups (`provider_lookup`, with the transaction's status) and, when an
order search ran, a `provider_search` item. `outcome` is decided in this order:

| `outcome` | When |
|---|---|
| `NOT_RECONCILABLE` | The intent is not in `IN_FLIGHT`, `UNKNOWN`, `EXECUTING`, `DISCREPANCY`, `CANCEL_REQUESTED` or `COMPLETED`; nothing ran |
| `PROVIDER_UNREACHABLE` | A provider lookup or search failed |
| `DISCREPANCY` | The intent is now `DISCREPANCY` |
| `EFFECT_FOUND` | The attempt is `SUCCEEDED` |
| `ABSENT_CONFIRMED` | The attempt is `RECONCILED`: verified absent after the absence window |
| `REJECTED_BY_PROVIDER` | The attempt is `FAILED` (definitive rejection) |
| `ABSENT_PENDING_WINDOW` | Anything else: not found yet, still inside the absence window. This is not evidence of no effect |

`next_action` is `CONTROLLED_RETRY` when the intent is `RECONCILING` and a retry is allowed now
(absence verified, attempt budget left), `HOLD_FOR_REVIEW` when it is `ESCALATED`, else `NONE`.

`POST /reconciliation/runs` records a `MATCHING` run and returns `{run_id, status: "started"}`; the
work happens in a background task. With `?wait=true` (not declared in the schema; the dashboard
uses it) the run happens inside the request and the response is
`{run_id, status: "finished", examined, mismatches_found, errors}`, still with status 202. A
matching run ([`backend/gateway_api/reconciliation.py`](../../backend/gateway_api/reconciliation.py))
compares the provider's listings for every order with the gateway's effects and records mismatches:

- `MISSING`: a live provider transaction no intent accounts for, or a ledger effect the provider
  does not know;
- `DUPLICATE`: more than one live transaction matching one intent;
- `AMOUNT`, `ORDER`, `CUSTOMER`: a live effect that differs from its intent in that field.

It skips intents still in `IN_FLIGHT` or `UNKNOWN`, never changes money or intent state and never
resolves a mismatch. The background worker records a `WORKER` run for every pass that processed at
least one intent. Run items: `{run_id, kind, triggered_by, started_at, finished_at, examined,
resolved, escalated, errors, mismatches_found}`.

`POST /exceptions/{intent_id}/investigate` builds an evidence bundle, asks the classifier (offline
rules by default, an LLM when `LLM_PROVIDER` is set) for
`{classification, summary, evidence_refs, recommended_action}`, and runs the deterministic policy
gate ([`backend/investigator/policy.py`](../../backend/investigator/policy.py)).

- Only intents in an exception state can be investigated: `409 NOT_AN_EXCEPTION`.
- Output that is off-schema is stored with `valid_output: false` and answered with
  `422 INVALID_INVESTIGATOR_OUTPUT`, with `details.investigation_id`.
- The investigation shape: `{investigation_id, intent_id, intent_state, valid_output,
  classification, summary, evidence_refs, recommended_action, policy_verdict: {permitted, rule},
  model, tokens: {in, out}, created_by, created_at, applied}`.

`POST /investigations/{investigation_id}/apply` re-builds the evidence and re-checks the gate on the
current state before doing anything, then runs the action through the engine. Response:
`{investigation_id, action, rule, intent_state}`. A second apply is `409 ALREADY_APPLIED`; rejected
output, or a gate that no longer permits the action, is `409 POLICY_REFUSED`.

#### Review queue

| Method | Path | Access | Status | Purpose |
|---|---|---|---|---|
| GET | `/review-cases` | `reviews:read` (operator+) | 200 | Review cases, newest first; filter `status` (default `OPEN`, empty for all) |
| GET | `/review-cases/{case_id}` | `reviews:read` (operator+) | 200 | One case with the intent summary, effects, investigations and the intent's audit entries |
| POST | `/review-cases/{case_id}/resolve` | `reviews:resolve` (reviewer+) | 200 | Resolve a case; the resolution is appended to the audit log |

Resolve body (`ResolveIn`): `{resolution, note}`. Response
`{case_id, status: "RESOLVED", resolution, intent_state}`.

| `resolution` | Effect |
|---|---|
| `ACCEPTED_AS_IS` | The intended effect stands. Needs a verified intended effect, else `409 NO_VERIFIED_EFFECT` |
| `CONFIRMED_NO_EFFECT` | Unresolved attempts become `RECONCILED`, which allows a controlled retry |
| `REFUND_RECOVERED_OUT_OF_BAND` | Live unintended effects (all live effects if a cancel was requested) are marked remediated; the key generation advances |
| `WRITTEN_OFF` | All open cases of the intent are resolved and the intent becomes `CLOSED` |
| `OTHER` | The case is resolved and the engine re-derives the intent state |

Errors: `409 ALREADY_RESOLVED`. With the `separation_of_duties` policy on (the default), the user
who authorized the intent gets `403 SEPARATION_OF_DUTIES`.

#### Webhooks

| Method | Path | Access | Status | Purpose |
|---|---|---|---|---|
| POST | `/webhooks/{provider}` | signature, no JWT; `provider` must be `paysim` | 200 | Receive a provider event: verify, deduplicate, then re-fetch in the background |

See [Webhook signatures](#webhook-signatures).

#### Audit, metrics and experiments

| Method | Path | Access | Status | Purpose |
|---|---|---|---|---|
| GET | `/audit` | `audit:read` (operator+) | 200 | Audit entries, newest first; filters `intent_id`, `actor`, `kind`, `from`, `to` |
| GET | `/audit/verify` | `audit:verify` (reviewer+) | 200 | Recompute every hash chain: `{valid, entries_checked, chains, first_break}` |
| GET | `/metrics/summary` | `metrics:read` (operator+) | 200 | Live counts and rates over `window` = `1h`, `24h` (default), `7d`, `30d` or `all` |
| GET | `/experiments/latest` | `metrics:read` (operator+) | 200 | `RESULTS_DIR/latest/summary.json` as written by the benchmark; `404` if there is none |

Audit entries: `{seq, ts, chain_id, intent_id, actor, kind, payload, prev_hash, hash}`, with the
payload redacted as described under Conventions. `first_break` is `null` or `{seq, chain_id}`. The
metrics body includes `intents` (total, completed, blocked, unknown, escalated, by_state),
`decisions`, `duplicates_suppressed`, `auto_resolved_rate`, `human_intervention_rate`,
`median_time_to_verified_s`, `live_unintended_effects`, `open_reviews` and a `definitions` object
that states how each rate is computed.

#### Admin

All admin endpoints need the `admin` capability (admin role only), except `GET /orders`.

| Method | Path | Status | Purpose |
|---|---|---|---|
| GET | `/admin/users` | 200 | Users and agent service principals (paginated) |
| POST | `/admin/users` | 201 | Create a user. Humans need `email` and a password of at least 12 characters; agents must not have a password. `409 ALREADY_EXISTS` |
| PATCH | `/admin/users/{user_id}` | 200 | Change name, role, active, password, permitted operations or limit. A role change, deactivation or password change revokes the user's refresh tokens |
| GET | `/admin/service-tokens` | 200 | The latest 200 issued agent tokens, without token values |
| POST | `/admin/service-tokens` | 201 | Issue an agent token; the value is returned only here |
| DELETE | `/admin/service-tokens/{jti}` | 200 | Revoke an agent token: `{jti, revoked: true}` |
| GET | `/admin/policies` | 200 | Current policies and the full `ProtocolConfig` |
| PUT | `/admin/policies` | 200 | Change policies; applied at once, stored, audited |
| GET | `/admin/providers` | 200 | The provider connection; the webhook secret is reported only as `webhook_secret_set` |
| PUT | `/admin/providers/{name}` | 200 | Update `base_url`, `timeout_s` or `webhook_secret` (write-only, 16 to 256 characters). Only `paysim` exists |
| POST | `/admin/orders` | 201 | Create or update a merchant order and register it with the provider |
| GET | `/orders` | 200 | The merchant's orders. Needs `orders:read` (operator+) |

`POST /admin/service-tokens` body (`ServiceTokenIn`): `principal_id`, `intent_ids[]`,
`customer_ids[]`, `ttl_s` (default 300, at least 30).

- The TTL is capped at `AGENT_TOKEN_MAX_TTL_S` (300 s).
- The principal must be an active user with role `agent`.
- At least one intent or customer is required, and every listed intent must exist (else
  `422 VALIDATION_ERROR`).
- Response: `{token, token_type, jti, scopes, expires_at, expires_in}`.

`PUT /admin/policies` body (`PoliciesIn`, every field optional):

| Field | Meaning |
|---|---|
| `kill_switch` | Hold every new proposal for review |
| `max_amount` / `clear_max_amount` | Largest amount any intent may move; checked at authorization and again at proposal time |
| `separation_of_duties` | Default on |
| `attempt_budget` | 1 to 20 |
| `absence_window_s` | 0 to 86400 |
| `unknown_review_after_s` | 1 to 604800 |

Policies are stored in the `policies` table and re-applied when the gateway starts.

#### Health

| Method | Path | Access | Status | Purpose |
|---|---|---|---|---|
| GET | `/health` | none | 200 | Liveness: `{status: "ok", service: "intentguard-gateway"}` |
| GET | `/ready` | none | 200 or 503 | `{status: "ready" or "not_ready", database, provider}`: a `SELECT 1` and the provider's `/health` |

#### Simulator-only endpoints

These exist only when the gateway runs with `SIMULATOR_MODE=true` (default `false` in
`settings.py`; `.env.example` and `docker-compose.yml` set it to `true`). Otherwise every `/dev/*`
path is `404 NOT_FOUND` with a message naming `SIMULATOR_MODE`. When enabled they also need the
`dev` capability (operator+).

| Method | Path | Status | Purpose |
|---|---|---|---|
| GET | `/dev/faults` | 200 | Queued provider faults |
| POST | `/dev/faults` | 201 | Inject a fault. Body `{kind, order_id?, times (-1 to 100, default 1), params}`; audited |
| DELETE | `/dev/faults` | 200 | Clear all faults |
| GET | `/dev/ledger` | 200 | Provider ground truth: every transaction regardless of search visibility; filter `order_id` |
| POST | `/dev/orders` | 201 | Create a fresh demo order `ORD-9xxxxxxx` (body `{customer_id = "C-17", amount = "20000", currency = "INR"}`), registered with the gateway and the provider |
| POST | `/dev/worker/tick` | 200 | Run one worker pass now: `{processed}` |

With `PAYMENT_PROVIDER=inprocess` they act on the embedded simulator. With `http` they call the
provider's `/v1/faults` and `/v1/ledger` (so the provider must also run with
`SIMULATOR_MODE=true` for faults).

### Webhook signatures

The provider signs each event with a shared secret:

```
Paysim-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256(secret, "<t>." + raw body)>
```

[`backend/gateway_api/webhooks.py`](../../backend/gateway_api/webhooks.py) handles
`POST /webhooks/paysim` in this order:

1. The secret is the one set with `PUT /admin/providers/paysim`, else `WEBHOOK_SECRET`. With no
   secret, every event is rejected (`400 INVALID_SIGNATURE`).
2. A missing or malformed header, or a signature that does not match the raw body (constant-time
   comparison), is `400 INVALID_SIGNATURE`. This happens before the body is parsed.
3. A timestamp more than `WEBHOOK_TOLERANCE_S` (300 s) from the gateway's clock is
   `400 STALE_EVENT`.
4. A body without `id`, `type` and `data.object.id` is `400 MALFORMED_EVENT`.
5. The event is stored once per `(provider, event_id)` (unique constraint). A repeat delivery only
   increments `deliveries` and returns `{"status": "duplicate", "event_id": ...}`; a new event
   returns `{"status": "accepted", "event_id": ...}`.
6. A new event is processed in a background task. The gateway re-fetches the transaction from the
   provider and absorbs what the provider says now, for the intent named in the event's
   `metadata.intent_id`. The payload is a hint; delivery order does not matter. A live transaction
   for no known intent, or for a `CANCELLED` or `CLOSED` intent, is recorded as a `MISSING`
   mismatch. The outcome is stored on the event (`absorbed`, `unknown_intent`,
   `unsupported_object`, `terminal_intent`, `terminal_intent_live_effect`, or
   `provider_unreachable: ...`).

Event body as sent by paysim:

```json
{"id": "evt_<tx id>_<status>", "type": "refund.completed", "created": 1791574615.4, "sequence": 2,
 "data": {"object": {"id": "rf_...", "kind": "REFUND", "status": "COMPLETED", "metadata": {"intent_id": "INT-1001"}}}}
```

The object is the full provider transaction (shortened above).

## Provider simulator API (port 8001)

A mock payment provider over [`paysim`](../../backend/paysim/simulator.py). It never connects to
real accounts. Amounts are integers in minor units. **It has no authentication.** Request models
are not strict (unknown fields are ignored), and request validation errors use FastAPI's default
`{"detail": [...]}`.

| Method | Path | Status | Purpose |
|---|---|---|---|
| GET | `/health` | 200 | `{status, service: "mock-payment-provider", simulation: true, simulator_mode, webhooks}` plus call counters `create_calls`, `executions`, `lookups`, `cancels` |
| POST | `/v1/orders` | 201 | Register an order: `{order_id, customer_id, currency = "INR", amount_minor > 0}` |
| POST | `/v1/refunds` | 201 | Create a refund. Body `{order_id, customer_id, amount_minor, currency = "INR", metadata = {}}`, header `Idempotency-Key`. Created `PENDING`; settles to `COMPLETED` after `PAYSIM_SETTLE_DELAY_S` (default 3) |
| GET | `/v1/refunds?order_id=` | 200 | Search by order. Eventually consistent: a transaction appears only after its `visible_at` |
| GET | `/v1/refunds/{tx_id}` | 200 | Lookup by id. Strongly consistent; 404 if the id is not a refund |
| POST | `/v1/refunds/{tx_id}/cancel` | 200 | Cancel. Only a `PENDING` refund can be cancelled; cancelling a `CANCELLED` one returns it unchanged |
| POST | `/v1/authorizations` | 201 | Create an authorization hold (same body and header as refunds) |
| GET | `/v1/authorizations?order_id=` | 200 | Search by order (eventually consistent) |
| GET | `/v1/authorizations/{tx_id}` | 200 | Lookup by id |
| POST | `/v1/authorizations/{tx_id}/void` | 200 | Void a hold while `PENDING` or `COMPLETED` (authorized) |
| GET | `/v1/faults` | 200 | Queued faults. `SIMULATOR_MODE=true` only, else 404 |
| POST | `/v1/faults` | 201 | Queue a fault `{kind, order_id?, times = 1, params = {}}`. `SIMULATOR_MODE=true` only |
| DELETE | `/v1/faults` | 200 | Clear all faults. `SIMULATOR_MODE=true` only |
| GET | `/v1/ledger?order_id=` | 200 | Ground truth: every transaction regardless of search visibility. Not gated by `SIMULATOR_MODE` |

Transactions are returned as `{id, kind, order_id, customer_id, amount_minor, currency, status,
idempotency_key, metadata, created_at, settles_at, visible_at, cancelled_at}` (epoch seconds). Ids
start with `rf_` (refunds) or `au_` (authorizations). State is persisted to `PAYSIM_STATE_PATH`
(default `paysim_state.json`), so the provider survives restarts.

**Idempotency.** A create whose `Idempotency-Key` was seen before returns the original transaction
if the kind, order, customer, amount and currency match, and is rejected with
`idempotency_key_reuse` if they differ. Keys expire after 24 h. The gateway always sends
`ig-<intent>-g<generation>`.

**Balance and ownership.** A create is rejected when the order is unknown, belongs to another
customer, has another currency, or when live (`PENDING` or `COMPLETED`) transactions of the same
kind on the order plus the new amount would exceed the order amount.

**Errors** use `{"detail": {"code", "message"}}`. How the gateway's HTTP adapter
([`backend/intentguard/providers/http.py`](../../backend/intentguard/providers/http.py)) and the
engine treat them:

| Status | Codes | On create | On cancel |
|---|---|---|---|
| 504 | `timeout` (timeout before execution, or response lost after execution) | Attempt `UNKNOWN`: reconcile | Retried; review case `CANCEL_UNVERIFIED` after `max_cancel_tries` (3) |
| 503 | `unavailable` (outage, lookup outage) | Attempt `UNKNOWN` | As 504 |
| 404 | `not_found`, `order_not_found` | Attempt `FAILED` (definitive) | Review case `CANCEL_REJECTED` |
| 409 | `not_cancellable`, `cancellation_failed` | (not returned by create) | Review case `CANCEL_REJECTED` |
| 422 | `customer_mismatch`, `currency_mismatch`, `invalid_amount`, `insufficient_balance`, `idempotency_key_reuse` | Attempt `FAILED` (definitive) | Review case `CANCEL_REJECTED` |

A network error or client timeout in the adapter is treated like a 504. On reads (lookup, search),
any error is a failed lookup: nothing is concluded from it.

### Faults

`kind` values are `paysim.FaultKind`. A fault applies to `order_id` (or to any order if omitted),
fires `times` times (`-1` = never consumed), and is consumed when it fires.

| Kind | Applies to | Effect | `params` |
|---|---|---|---|
| `OUTAGE` | create | 503, nothing executed | |
| `TIMEOUT_BEFORE_EXECUTION` | create | 504, nothing executed | |
| `TIMEOUT_AFTER_EXECUTION` | create | Executes (or replays), then 504 | |
| `DELAYED_STATUS` | create (fresh execution) | Settles after a longer delay | `settle_delay_s` (default 60) |
| `DELAYED_VISIBILITY` | create (fresh execution) | Hidden from search for a while | `lag_s` (default 20) |
| `CORRUPT_AMOUNT` | create (fresh execution) | Settled amount = requested amount x `factor` | `factor` (default 10) |
| `FAILED_CANCELLATION` | cancel / void | 409 `cancellation_failed`, even when cancellation would be allowed | |
| `LOOKUP_OUTAGE` | get / search | 503 | |
| `WEBHOOK_DUPLICATE` | webhook delivery | The next event for the order is delivered twice | |
| `WEBHOOK_DELAY` | webhook delivery | The next event for the order is delivered late, so later events can arrive first | `delay_s` (default 10) |

### Webhook emitter

When `PAYSIM_WEBHOOK_URL` and a secret (`PAYSIM_WEBHOOK_SECRET`, else `WEBHOOK_SECRET`) are both
set, a background thread ([`backend/paysim/webhooks.py`](../../backend/paysim/webhooks.py)) checks
the transactions every 0.5 s and emits one signed event per status change. Event ids are
deterministic (`evt_<tx id>_<status>`), so a re-emitted event is a duplicate the receiver must
deduplicate. A delivery that does not get a 2xx is retried with back-off (1, 2, 4, ... s), up to 6
tries.

## What the OpenAPI schema does not say

[`docs/api/openapi.json`](../api/openapi.json) is generated by FastAPI from the route definitions.
It does not contain:

- a security scheme (bearer tokens, the refresh cookie, the webhook signature);
- the headers `Idempotency-Key`, `X-IntentGuard-CSRF`, `X-Request-ID`, `Paysim-Signature`;
- the `wait` query parameter of `POST /reconciliation/runs`;
- the error envelope. Most operations list a 422 response with FastAPI's default
  `HTTPValidationError` schema (`{"detail": [...]}`), which the gateway never returns; the actual
  422 body is the envelope. No other error status is listed;
- response body schemas (handlers return plain objects);
- the root `GET /health`.

## Differences from docs/API.md

docs/API.md was corrected against this page during the rebuild (error codes by status, 502/503
only on `/dev/*`, cancel response, schema gaps), and three code issues found here were fixed
(commit 67d44e1): the login timing difference for unknown emails, the provider idempotency key in
`GET /dev/ledger` (now redacted), and Docker publishing the provider and PostgreSQL on all
interfaces (now 127.0.0.1). What remains:

- **Mock provider isolation.** docs/API.md says the provider is reachable only from the gateway
  network. It has no authentication; `scripts/start.bat`, the `Makefile` and `docker-compose.yml`
  bind it to 127.0.0.1, so any local process can call it. Its `/v1/ledger` is not gated by
  `SIMULATOR_MODE`.
- **OpenAPI.** The schema matches paths, methods and request bodies, but not the auth, error or
  response details listed under [What the OpenAPI schema does not say](#what-the-openapi-schema-does-not-say);
  docs/API.md is authoritative for those.
