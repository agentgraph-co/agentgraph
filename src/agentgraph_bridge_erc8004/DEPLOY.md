# ERC-8004 Bridge — Production Deployment

End-to-end deploy guide for the `agentgraph_bridge_erc8004` package in prod.

## Prerequisites

1. **`ETH_RPC_URL`** — Alchemy or Quicknode HTTPS endpoint to Ethereum mainnet.
   Free tier sufficient (300M Alchemy CU/month vs. our ~100 calls/day).
   Already deployed in prod (`.env.production`) as of 2026-05-22.

2. **EIP-8004 contract addresses** — currently placeholder zeros pending the
   canonical EIP-8004 mainnet deployment. Once verified, set:
   ```
   ERC8004_IDENTITY_ADDRESS=0x...
   ERC8004_REPUTATION_ADDRESS=0x...
   ERC8004_VALIDATION_ADDRESS=0x...
   ```
   Until these land, the bridge is functionally inert in prod (any
   read attempt against `0x000...000` returns `RegistryReadError`).
   Composite trust score behavior unchanged (the lazy import in
   `src/trust/score.py::_external_score_with_attestations` only fires
   when caller passes attestations, which the sync job won't do
   until real addresses exist).

3. **`pip install agentgraph[erc8004]`** — pulls `web3 + eth-account`.
   Not a hard dep on the main backend; only required when the bridge
   is actually loaded.

## One-liner deploy (after EIP-8004 addresses land)

```bash
ssh -i ~/.ssh/agentgraph-key.pem ec2-user@98.94.217.37
cd ~/agentgraph
cat >> .env.production <<EOF

# ERC-8004 (filled in 2026-MM-DD when EIP-8004 mainnet deploy verified)
ERC8004_IDENTITY_ADDRESS=<real-address>
ERC8004_REPUTATION_ADDRESS=<real-address>
ERC8004_VALIDATION_ADDRESS=<real-address>
EOF

# Sync source dep + recreate backend
git pull
PG_PW=$(grep '^POSTGRES_PASSWORD=' .env.secrets | cut -d= -f2-)
RD_PW=$(grep '^REDIS_PASSWORD=' .env.secrets | cut -d= -f2-)
sudo POSTGRES_PASSWORD="$PG_PW" REDIS_PASSWORD="$RD_PW" \
  docker-compose -f docker-compose.prod.yml up -d --no-deps --force-recreate backend

# Smoke test
sudo docker exec agentgraph-backend-1 python3 -c "
from agentgraph_bridge_erc8004 import make_reader_from_env
r = make_reader_from_env()
print('reachable:', r.is_reachable())
print('identity_count:', r.entry_count(__import__('agentgraph_bridge_erc8004').ERC8004Registry.IDENTITY))
"
```

## Background sync job (post EIP-8004 deploy)

The trust score recompute job runs every cycle. Fetching ERC-8004 attestations
live on every recompute would burn RPC quota + slow the job. Instead:

1. Cron a separate job (~ every hour) that scans the 3 registries for new
   entries since last sync watermark
2. Normalize each entry via `attestation_normalizer.normalize()`
3. Cache verified attestations in a new `erc8004_attestations` table keyed
   on `subject_did` + `source_urn`
4. Trust recompute reads from the cache (synchronous, fast) and passes
   into `_external_score_with_attestations()`

Schema (proposal — not yet migrated):
```sql
CREATE TABLE erc8004_attestations (
  source_urn TEXT PRIMARY KEY,         -- urn:erc8004:{registry}:{entry_id}
  subject_did TEXT NOT NULL,
  provider_did TEXT NOT NULL,
  claim_type TEXT NOT NULL,            -- {identity, transport, authority, continuity}
  claim_subtype TEXT,
  payload JSONB NOT NULL,
  signature_verified BOOLEAN NOT NULL,
  registry_signature_verified BOOLEAN NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ,
  last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_erc8004_subject ON erc8004_attestations(subject_did);
```

The sync job is task #88 follow-on; not blocking v0.3.2 publish.

## Failure modes + observability

- **RPC unreachable** — `RegistryReadError` from reader, log warning, skip
  this sync cycle. No trust score impact (cache stays).
- **JWKS fetch fails** — `NormalizationError` from normalizer, log warning,
  attestation dropped from this sync. Not retried until next sync window.
- **Signature mismatch** — `NormalizationError`. SIGNAL-WORTHY: attestation
  was rejected, log at ERROR + emit metric `erc8004.signature_mismatch_total`.
- **Address not yet deployed** — `RegistryReadError` (contract returns
  empty bytes for non-existent contracts). Expected until EIP-8004
  mainnet addresses land; suppress to DEBUG-level log.

## Health check endpoint

The bridge surfaces `is_reachable()` for liveness probes:

```python
from agentgraph_bridge_erc8004 import make_reader_from_env
reader = make_reader_from_env()
healthy = reader.is_reachable()  # True if RPC responds AND chain_id matches
```

Wire into the FastAPI healthcheck under `/health/erc8004` if needed.
Optional — the bridge has no critical-path dependency.

## Cost (Alchemy free tier)

| Operation | CU cost | Volume | Monthly CU |
|---|---|---|---|
| `eth_blockNumber` (per is_reachable) | 16 | 1/hr | ~12K |
| `getEntry(uint256)` (per attestation sync) | 16 | ~50/day | ~24K |
| `EntrySubmitted` event scan | 16/block × ~50 blocks | 1/hr | ~600K |
| **Total estimated monthly CU** | | | **~640K** |

Vs. Alchemy free tier limit of 300M CU/month. **0.2% utilization.** No cost
concern; comfortable headroom for 100x growth in attestation volume.

## Rollback

The bridge is opt-in. To disable entirely:
1. Unset `ERC8004_IDENTITY_ADDRESS` / `_REPUTATION_ADDRESS` / `_VALIDATION_ADDRESS`
2. Restart backend
3. Trust recompute reverts to community-signal-only external scoring

No data migration required — the bridge writes to its own cache table
which can be left in place or `DROP TABLE` cleanly.
