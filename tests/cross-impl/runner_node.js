#!/usr/bin/env node
// JCS RFC 8785 cross-implementation runner -- JavaScript (canonicalize@3.0.0)
// Verifies 53 substrate vectors across 5 fixture files byte-for-byte.
// Usage: npm install canonicalize && node runner_node.js
const canonicalize = require("canonicalize");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const FIXTURES = path.join(__dirname, "fixtures");

function jcsHash(obj) {
  const canon = Buffer.from(canonicalize(obj), "utf8");
  return crypto.createHash("sha256").update(canon).digest("hex");
}
function jcsBytesB64(obj) {
  return Buffer.from(canonicalize(obj), "utf8").toString("base64");
}

let passed = 0, failed = 0;

// Files with mandate_body -> expected_jcs_bytes_b64
for (const fname of ["ap2-omh-v0.json", "per_chain_envelope_v0.json"]) {
  const data = JSON.parse(fs.readFileSync(path.join(FIXTURES, fname)));
  const vectors = data.vectors;
  for (const v of vectors) {
    const vid = v.vector_id || v.id || "?";
    const got = jcsBytesB64(v.mandate_body);
    const ok = got === v.expected_jcs_bytes_b64;
    passed += ok ? 1 : 0; failed += ok ? 0 : 1;
    console.log(`${fname} ${vid}: ${ok ? "PASS" : "FAIL"}`);
  }
}

// privacy_class: attestation_body -> expected_jcs_bytes_b64
for (const fname of ["privacy_class_v0.1.json"]) {
  const data = JSON.parse(fs.readFileSync(path.join(FIXTURES, fname)));
  const vectors = data.vectors;
  for (const v of vectors) {
    const vid = v.vector_id || v.id || "?";
    const got = jcsBytesB64(v.attestation_body);
    const ok = got === v.expected_jcs_bytes_b64;
    passed += ok ? 1 : 0; failed += ok ? 0 : 1;
    console.log(`${fname} ${vid}: ${ok ? "PASS" : "FAIL"}`);
  }
}

// aps_vectors: input -> canonical_sha256
for (const fname of ["aps_vectors.json"]) {
  const data = JSON.parse(fs.readFileSync(path.join(FIXTURES, fname)));
  const vectors = data.vectors;
  for (const v of vectors) {
    const vid = v.name || v.vector_id || v.id || "?";
    const got = jcsHash(v.input);
    const ok = got === v.canonical_sha256;
    passed += ok ? 1 : 0; failed += ok ? 0 : 1;
    console.log(`${fname} ${vid}: ${ok ? "PASS" : "FAIL"}`);
  }
}

// ctef_vectors: flat top-level dict, input_object -> canonical_sha256
for (const fname of ["ctef_vectors.json"]) {
  const data = JSON.parse(fs.readFileSync(path.join(FIXTURES, fname)));
  for (const [vid, v] of Object.entries(data)) {
    if (!v || typeof v !== "object" || !v.input_object) continue;
    const got = jcsHash(v.input_object);
    const ok = got === v.canonical_sha256;
    passed += ok ? 1 : 0; failed += ok ? 0 : 1;
    console.log(`${fname} ${vid}: ${ok ? "PASS" : "FAIL"}`);
  }
}

console.log(`\nJS canonicalize@3.0.0: ${passed}/${passed + failed} PASS`);
