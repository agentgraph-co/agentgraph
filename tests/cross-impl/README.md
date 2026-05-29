# JCS Cross-Implementation Substrate Runners

53-vector conformance suite for the AlgoVoi JCS RFC 8785 canonicalisation substrate,
validated byte-for-byte across 5 reference implementations.

## Implementations

| Language   | Package                            | Authors                                  | Version |
|------------|------------------------------------|------------------------------------------|---------|
| Python     | `rfc8785`                          | Trail of Bits (William Woodruff)         | 0.1.4   |
| JavaScript | `canonicalize`                     | Samuel Erdtman + Anders Rundgren         | 3.0.0   |
| Go         | `gowebpki/jcs`                     | Web PKI WG                               | v1.0.1  |
| Java       | `cyberphone/json-canonicalization` | Anders Rundgren (RFC 8785 author)        | --      |

A fifth implementation (Rust `serde_jcs` by seritalien) has been validated externally
against the same vector set. A Rust runner is not included here because a reliable
local Rust build environment is not guaranteed on all platforms.

## Running

**Python** (requires Python 3.8+):
```
pip install rfc8785
python runner_python.py
```

**JavaScript** (requires Node 16+):
```
npm install canonicalize
node runner_node.js
```

**Go** (requires Go 1.21+):
```
go run runner_go.go
```
The `go.mod` and `go.sum` in this directory pin `gowebpki/jcs@v1.0.1`.

**Java** (requires Java 11+):

```
mkdir -p lib/org/webpki/jcs
# Copy DoubleCoreSerializer.java, JsonCanonicalizer.java, NumberToJSON.java
# from https://github.com/cyberphone/json-canonicalization src/org/webpki/jcs/
javac lib/org/webpki/jcs/*.java -d lib/
javac -cp lib JcsRunner.java
java -cp .:lib JcsRunner
```

## Fixture summary

| File                         | Vectors | Body key           | Expected key              |
|------------------------------|---------|--------------------|---------------------------|
| `ap2-omh-v0.json`            | 7       | `mandate_body`     | `expected_jcs_bytes_b64`  |
| `per_chain_envelope_v0.json` | 19      | `mandate_body`     | `expected_jcs_bytes_b64`  |
| `privacy_class_v0.1.json`    | 13      | `attestation_body` | `expected_jcs_bytes_b64`  |
| `aps_vectors.json`           | 10      | `input`            | `canonical_sha256`        |
| `ctef_vectors.json`          | 4       | `input_object`     | `canonical_sha256`        |

**Total: 53 vectors.**

## Vector sources

Authored by chopmob-cloud (AlgoVoi), Apache 2.0:

- AP2 OMH v0: https://gist.github.com/chopmob-cloud/1dca25fd6107db4b7a30bed5dbf2ded8
- CTEF + APS v1: https://gist.github.com/chopmob-cloud/5f35eaa527d292bf3ddc52f8725a85c9
- privacy_class v0.1: https://gist.github.com/chopmob-cloud/30bcbc717c86493f737feb92c415ba07
- per_chain_envelope v0: https://gist.github.com/chopmob-cloud/e1bf4c9efde6f0e94b77c238cb33d78d

In-tree mirror (pending merge): x402-foundation/x402#2412

## Relation to the cross-extension matrix

These runners reproduce the in-tree substrate for row #3 (`urn:x402:audit-chain`) of the
v0.3.3 cross-extension fixture matrix. All 5 implementations produce byte-identical JCS
output for all 53 vectors. See `docs/standards/v0.3.3-working-doc.md` for the full matrix.
