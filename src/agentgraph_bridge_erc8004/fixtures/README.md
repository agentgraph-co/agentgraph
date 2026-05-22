# ERC-8004 Bridge Fixtures

3 mainnet-shaped snapshot fixtures for offline reproduction of the normalizer's
verification path. Each fixture contains:

- **`entry.json`** — Raw `ERC8004Entry` shape as returned by the registry contract
- **`envelope.json`** — Parsed CTEF envelope from the entry's `data` field (pre-signature)
- **`jwks.json`** — JWKS the provider DID resolves to
- **`expected_normalized.json`** — Expected `NormalizedAttestation` output

To regenerate signatures, use `scripts/regen_fixture_signatures.py` (signs each
envelope with a deterministic Ed25519 key derived from the fixture name).

Fixtures are **shape examples**, not signed real attestations from production
EIP-8004 contracts (those don't exist yet on mainnet — task #88 will swap these
out with real snapshots once the canonical EIP-8004 deployment is verified).

## Fixtures

| File | claim_type | Provider | Purpose |
|---|---|---|---|
| `identity_basic.json` | identity | did:web:registrar.example.com | Minimal identity attestation, ~150 bytes data field |
| `authority_tier_upgrade.json` | authority | did:web:trust.arkforge.tech | ArkForge tier_upgrade_proof shape, composes with row #8 of v0.3.3 matrix |
| `continuity_behavioral.json` | continuity | did:web:dominion-observatory.sgdata.workers.dev | Dominion-shaped behavioral evidence, composes with row #5 of v0.3.3 matrix |

## Reproduction

```python
import json
from agentgraph_bridge_erc8004 import ERC8004Entry, normalize

with open("fixtures/identity_basic/entry.json") as f:
    entry_data = json.load(f)
entry = ERC8004Entry(**entry_data)

# Mock the JWKS fetch with the fixture's JWKS
import httpx
def handler(req):
    return httpx.Response(200, json=json.load(open("fixtures/identity_basic/jwks.json")))
client = httpx.Client(transport=httpx.MockTransport(handler))

result = normalize(entry, http_client=client)
assert result.is_admissible
```
