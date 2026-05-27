# ERC-8004 Activation Notes (2026-05-27)

Status of making the bridge read **real** ERC-8004 mainnet data. Branch: `feat/erc8004-activation`.

## TL;DR

The Day-2/3 bridge shipped against an **inferred ABI** and a **wrong consumption model**. Real mainnet contracts are now wired + live-verified. The reader reads real agents. The normalizer + score_ingest still need rework for the corrected model before live trust signals flow.

## The model correction (the important part)

| | Day-2 assumption (WRONG) | Real ERC-8004 mainnet v2.0.0 |
|---|---|---|
| Identity entry | `getEntry(uint256) -> (submitter, subjectDid, data, timestamp, exists)` | **ERC-721 token.** `ownerOf`, `getAgentWallet`, `tokenURI`, `getMetadata(id,key)` |
| CTEF attestation | embedded in registry `data` bytes | **NOT in registry.** Registry is a pointer layer; `tokenURI` → off-chain registration file → CTEF attestation (if any) lives there |
| Reputation | (not modeled) | `giveFeedback` / `readFeedback` / `getSummary` → numeric score signals, not CTEF envelopes |
| Validation | (not modeled) | `validationRequest` / `validationResponse` / `getValidationStatus` — **not deployed on mainnet yet** |

Consumption model is now: **registry (on-chain pointer) → tokenURI → off-chain registration file → CTEF attestation**.

## What's DONE on this branch

- ✅ Real ABIs pulled from `github.com/erc-8004/erc-8004-contracts`, validated against the live contract (`name()="AgentIdentity"`, `symbol()="AGENT"`, `getVersion()="2.0.0"`). Stored at `abi/erc8004_v2/{Identity,Reputation,Validation}Registry.json`.
- ✅ Real mainnet addresses in `config.py`, verified live via `eth_getCode`:
  - Identity `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`
  - Reputation `0x8004BAa17C55a88189AE136b182e5fdA19dE9b63`
  - Validation — placeholder zero (not on mainnet yet)
- ✅ `identity_registry.py` — `IdentityRegistryReader` matching the real ERC-721 interface + `AgentRecord` model. **Live-verified**: read agents 1/2/3 from mainnet (owner + wallet resolved; tokenURI empty for those early registrations).

## What's LEFT (the rest of activation)

1. **Reputation reader** — `reputation_registry.py`: `getSummary(agentId, ...)` + `readAllFeedback(...)` → map to a behavioral-trust signal. This is the highest-value trust input (numeric feedback scores).
2. **Normalizer rework** — `attestation_normalizer.py` currently expects embedded CTEF bytes in `entry.data`. New flow: fetch `registration_uri` → parse registration file → extract CTEF attestation (if present) → verify. If no CTEF attestation in the file, the agent still has an identity record but no composable attestation (that's a valid state).
3. **score_ingest wiring** — feed Reputation summary + any CTEF attestation into the composite trust score `EXTERNAL` slot. The existing `score_ingest.py` discrimination-tuple logic mostly holds; the input shape changes.
4. **Sync job + cache table** — hourly cron: enumerate registry → read agent records + reputation → cache in `erc8004_attestations` (schema in DEPLOY.md). Trust recompute reads the cache.
5. **Old `registry_reader.py` (getEntry model) is SUPERSEDED** — left in place so the 67 existing tests don't break on this branch; reconcile/remove on review. `identity_registry.py` is the correct path.

## Deploy gating

Do NOT deploy to prod until the normalizer rework + a mocked test suite for `identity_registry.py` land and Kenne reviews. The reader is read-only and mainnet-verified, but the end-to-end trust-signal path isn't complete. **Do not claim "live ERC-8004 trust scoring" until items 1-4 ship.**

## Announcement honesty

Today (2026-05-27): "AgentGraph has an ERC-8004 bridge; reads live mainnet agent identity records." TRUE.
NOT yet: "live ERC-8004 trust scoring feeding the composite score." Needs items 1-4.
