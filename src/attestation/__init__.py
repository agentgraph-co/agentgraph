"""Attestation schemas for cross-issuer interop.

Distinct from ``src/api/*_attestation_router.py`` which emit AgentGraph's
native attestation shapes. Modules in this package produce attestations
in cross-vendor interop shapes (APS-composed slot, CTEF envelope, etc.)
while keeping scoring rubric and gate weighting private to scanner code.
"""
