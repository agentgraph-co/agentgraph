# AgentGraph Partner Webhook Contract

**Status:** v1.0 — stable
**Last updated:** 2026-04-20
**Applies to:** any partner receiving outbound scan-change events from AgentGraph

---

## Overview

When a security scan score changes for a repo AgentGraph is watching, we POST a signed event to every registered callback URL. This document is the canonical contract for partners integrating with that stream.

Two signature schemes are available; partners may verify either one (or both):

| Scheme | Where | Verification material | Use when |
|---|---|---|---|
| **JWS (Ed25519)** | `body.jws` | Our public JWKS at `https://agentgraph.co/.well-known/jwks.json` | You want asymmetric verification and have no pre-shared secret |
| **HMAC-SHA256** | `X-Partner-Signature` header | Shared secret exchanged at subscription time | You want symmetric verification (matches MoltBridge / VeroQ Shield / MolTrust partner contract) |

Every outbound POST carries both. You can verify whichever matches your infrastructure.

---

## Subscription

Partners (or AgentGraph on a partner's behalf) register a callback URL:

```http
POST https://agentgraph.co/api/v1/gateway/webhook/subscribe
Content-Type: application/json

{
  "repo": "owner/repo",
  "callback_url": "https://partner.example.com/webhooks/inbound/a2a",
  "provider": "moltbridge",
  "signing_secret": "<optional HMAC shared secret>"
}
```

- `callback_url` **must** be HTTPS.
- `signing_secret` is optional. If provided, outbound POSTs carry `X-Partner-Signature`.
- The subscribe response **never** echoes `signing_secret`.
- Secrets should be exchanged out-of-band (age-encrypted email, GPG, Keybase, Signal) — never in clear request bodies when possible.

---

## Event Shape

```json
{
  "type": "scan-change",
  "repo": "owner/repo",
  "new_score": 82,
  "old_score": 71,
  "changed_at": "2026-04-20T22:00:00+00:00",
  "jws": "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXUyJ9..<signature>"
}
```

- `type` is always `"scan-change"` for this event family. Legacy consumers may accept the alias `"ScanScoreChanged"` (kept inside the JWS payload for backwards compatibility).
- `repo` is the canonical `owner/repo` string scanned.
- `new_score` is always present; `old_score` is `null` on first scan.
- `changed_at` is ISO-8601 UTC.
- `jws` is a detached-payload-style JWS over the canonicalized event body (see below).

**Canonical body bytes for HMAC:** JSON serialized with `separators=(",", ":")` and `sort_keys=true`. Byte-for-byte stable. Compute HMAC over these exact bytes.

---

## Headers

Every outbound POST carries:

| Header | Value | Notes |
|---|---|---|
| `Content-Type` | `application/json` | |
| `User-Agent` | `AgentGraph-Webhook/1.0` | |
| `X-AgentGraph-Event` | `scan-change` | Event-type alias for routing |
| `X-Partner-Signature` | `sha256=<hex>` | **Only if** subscription registered with `signing_secret` |
| `X-Partner-Timestamp` | ISO-8601 UTC | **Only if** `X-Partner-Signature` is present. Verify within ±5 minutes. |

---

## Verification

### HMAC-SHA256 (symmetric)

```python
import hmac, hashlib, json
from datetime import datetime, timezone, timedelta

def verify(raw_body: bytes, signature_header: str, timestamp_header: str, secret: str) -> bool:
    # 1. Timestamp window (±5 min)
    ts = datetime.fromisoformat(timestamp_header)
    if abs((datetime.now(timezone.utc) - ts)) > timedelta(minutes=5):
        return False

    # 2. Recompute HMAC over the raw body bytes
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    # 3. Constant-time compare
    return hmac.compare_digest(expected, signature_header)
```

```javascript
// Node.js
import crypto from "crypto";

export function verify(rawBody, signatureHeader, timestampHeader, secret) {
  const ts = new Date(timestampHeader);
  if (Math.abs(Date.now() - ts.getTime()) > 5 * 60 * 1000) return false;

  const expected = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(rawBody)
    .digest("hex");

  return crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signatureHeader)
  );
}
```

```go
// Go
package webhook

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "subtle"
    "time"
)

func Verify(rawBody []byte, signatureHeader, timestampHeader, secret string) bool {
    ts, err := time.Parse(time.RFC3339, timestampHeader)
    if err != nil || time.Since(ts).Abs() > 5*time.Minute {
        return false
    }
    h := hmac.New(sha256.New, []byte(secret))
    h.Write(rawBody)
    expected := "sha256=" + hex.EncodeToString(h.Sum(nil))
    return subtle.ConstantTimeCompare([]byte(expected), []byte(signatureHeader)) == 1
}
```

### JWS (asymmetric, Ed25519)

Fetch `https://agentgraph.co/.well-known/jwks.json`, cache keys by `kid`, verify the JWS in `body.jws` per RFC 7515. JWKS rotates; handle `kid` mismatch by re-fetching.

---

## Test Vectors

Canonical known-good examples live in [`test-vectors.json`](./test-vectors.json). Use them to unit-test your receiver before wiring live traffic.

---

## Replay & Idempotency

- Timestamps have a ±5 minute window — reject outside that band.
- Events are **at-least-once**. Use `(repo, changed_at)` as an idempotency key if you persist them.
- We do not retry on non-2xx responses today. A 2xx within 10s is considered delivered.

---

## Error Handling on the Sender Side

If a partner endpoint 5xx's or times out, we log and drop. Partners seeking reliable delivery can:
1. Implement a queue behind their callback URL (we respond to the POST, queue handles retries internally).
2. Poll `GET /api/v1/public/scan/{owner}/{repo}` on a cadence as a reconciliation path.

---

## Security Notes

- **Secret rotation:** re-subscribe with a new `signing_secret`. The subscription is deduplicated by `(callback_url, provider)`; the latest `signing_secret` wins.
- **Clock skew:** partners should synchronize via NTP; outside ±5 minutes, verification fails.
- **HTTPS only:** `callback_url` must be HTTPS; we reject `http://`.
- **No PII:** event bodies contain repo identifiers and scan scores only. No tokens, user data, or scan findings themselves — those live behind the authenticated API.

---

## Contact

- Spec questions: kenne@agentgraph.co
- Partner onboarding: post on [A2A Discussion #1720](https://github.com/a2aproject/A2A/discussions/1720) or email above
- Signing secret exchange: age-encrypted or GPG-wrapped blob to the email above
