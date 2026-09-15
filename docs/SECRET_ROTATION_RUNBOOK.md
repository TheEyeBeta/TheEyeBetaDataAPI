# Secret rotation runbook — DataAPI JWT signing secrets

Zero-downtime rotation for DataAPI-issued JWTs (service + delegated tokens) and
for symmetric user-JWT validation. Service **client credentials**
(`iam.service_client_secrets` / `SERVICE_CLIENTS_JSON`) are a separate
credential type — rotate those with `scripts/provision_db_service_client.py` /
`scripts/rotate_secrets.py`, not this procedure.

Related inventory: [`IAM_CONSUMER_INVENTORY.md`](IAM_CONSUMER_INVENTORY.md).

## Secrets involved

| Env var | Role |
|---|---|
| `JWT_SECRET` | Backwards-compatible alias for the **current** DataAPI signing secret |
| `JWT_SIGNING_SECRET_CURRENT` | Preferred current signing secret (used for all new service/delegated tokens) |
| `JWT_SIGNING_SECRET_PREVIOUS` | Optional verify-only secret during overlap window |
| `USER_JWT_SECRET` | Current symmetric secret for inbound user JWTs |
| `USER_JWT_SECRET_PREVIOUS` | Optional verify-only previous user secret |

Signing always uses **current only**. Verification tries **current, then previous**.

Default max access-token TTL to wait before clearing `PREVIOUS`:

- Service tokens: `SERVICE_TOKEN_EXPIRES_MINUTES` (default **60**)
- Delegated tokens: `DELEGATED_TOKEN_EXPIRES_MINUTES` (default **5**)
- User JWTs: issuer-controlled — use the longest live TTL you know (see inventory open questions)

## A) Rotate DataAPI signing secret (`JWT_SECRET` / service + delegated)

### 1. Generate a new secret

```bash
openssl rand -hex 32
```

### 2. Overlap window (no forced logouts)

On the host `.env` (mode `600`):

1. Set `JWT_SIGNING_SECRET_PREVIOUS` to the **current** live signing secret
   (whatever `JWT_SIGNING_SECRET_CURRENT` or `JWT_SECRET` is today).
2. Set `JWT_SIGNING_SECRET_CURRENT` to the **new** secret from step 1.
3. Keep `JWT_SECRET` equal to the **new** secret as well (alias for tools that
   still only know `JWT_SECRET`), **or** leave `JWT_SECRET` as the old value
   only if `JWT_SIGNING_SECRET_CURRENT` is set — prefer aligning both to the new
   value once `PREVIOUS` holds the old one.
4. Restart:

```bash
systemctl --user restart theeyebeta-dataapi
curl -fsS http://127.0.0.1:7000/health
```

Tokens minted before the restart still verify via `PREVIOUS`. New tokens are
signed only with `CURRENT`.

### 3. Wait one full max-token TTL

Wait at least `SERVICE_TOKEN_EXPIRES_MINUTES` (and
`DELEGATED_TOKEN_EXPIRES_MINUTES` if Lens is in use). Prefer the larger of the
two (usually 60 minutes).

### 4. Clear previous

1. Remove `JWT_SIGNING_SECRET_PREVIOUS` (or set it empty).
2. Confirm `JWT_SIGNING_SECRET_CURRENT` and `JWT_SECRET` both hold the new value.
3. Restart and re-check `/health`.
4. Smoke: issue a service token and call a read endpoint
   (`scripts/verify_remote_access.sh` or the README curl examples).

## B) Rotate `USER_JWT_SECRET` (symmetric user JWTs)

Same pattern with `USER_JWT_SECRET` / `USER_JWT_SECRET_PREVIOUS`.

1. Generate with `openssl rand -hex 32`.
2. Set `USER_JWT_SECRET_PREVIOUS` = old `USER_JWT_SECRET`.
3. Set `USER_JWT_SECRET` = new value.
4. Restart; wait one full **user-token** TTL (IdP / issuer controlled).
5. Clear `USER_JWT_SECRET_PREVIOUS`; restart; smoke a user-authenticated call.

If production uses JWKS (`USER_JWT_JWKS_URL`), rotate keys at the IdP instead —
previous/current env secrets do not apply to the JWKS path.

## C) Local / staging dry-run checklist

Before production:

1. Point a non-prod `.env` at a disposable signing secret pair.
2. Issue a service token; confirm `decode` works.
3. Perform steps A.2–A.4 against that environment.
4. Confirm a token minted **before** the CURRENT swap still works during the
   overlap, and fails after `PREVIOUS` is cleared.
5. Confirm a token minted **after** the CURRENT swap works throughout.

Automated coverage: `tests/test_secret_rotation.py`.

## D) Do not

- Clear `PREVIOUS` before the TTL window ends (forces 401s on live tokens).
- Commit `.env` or `.env.bak.*`.
- Reuse Prod migration codewords or other-repo secrets here.
- Touch `/admin/*` gateway config as part of JWT rotation.
