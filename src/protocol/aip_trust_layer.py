"""AIP Trust Layer — AgentGraph's trust/attestation layer on top of A2A.

Architecture Separation of Concerns
====================================

**A2A (Google Agent-to-Agent Protocol)** provides:
- Transport-level agent-to-agent communication
- Agent cards, capability discovery, task lifecycle
- Message routing and delegation mechanics
- Framework-agnostic interoperability

**AIP (AgentGraph Identity Protocol)** provides:
- Trust verification before interactions proceed
- Attestation injection into A2A message envelopes
- Audit logging of every cross-agent interaction
- DID-based identity resolution
- Trust-threshold enforcement per interaction type
- Framework trust modifiers (penalise unverified frameworks)

AIP does NOT duplicate A2A's transport.  Instead, it wraps A2A
interactions with a trust/identity/accountability layer:

    Agent A ─── A2A envelope ───► [AIP Trust Layer] ───► Agent B
                                  │
                                  ├─ verify_identities()
                                  ├─ check_trust_threshold()
                                  ├─ inject_attestation()
                                  └─ log_audit_trail()

Usage::

    from src.protocol.aip_trust_layer import AIPTrustLayer

    layer = AIPTrustLayer(db=session)
    result = await layer.process_outbound(
        sender_id="...",
        receiver_id="...",
        a2a_envelope={"type": "delegate_request", ...},
        interaction_type="delegate",
    )
    if result.allowed:
        # forward result.enriched_envelope via A2A transport
        ...
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trust thresholds (shared with a2a_middleware for backward-compat)
# ---------------------------------------------------------------------------

DEFAULT_TRUST_THRESHOLDS: dict[str, float] = {
    "delegate": 0.6,
    "negotiate": 0.5,
    "collaborate": 0.4,
    "discover": 0.0,
    "capability_exchange": 0.1,
    "data_transfer": 0.7,
    "financial": 0.8,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Attestation:
    """A trust attestation attached to an A2A interaction."""

    issuer_did: str | None
    subject_did: str | None
    trust_score: float | None
    framework_modifier: float
    interaction_type: str
    issued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    attestation_id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "issuer_did": self.issuer_did,
            "subject_did": self.subject_did,
            "trust_score": self.trust_score,
            "framework_modifier": self.framework_modifier,
            "interaction_type": self.interaction_type,
            "issued_at": self.issued_at,
        }


@dataclass
class TrustLayerResult:
    """Result of running an A2A envelope through the AIP trust layer."""

    allowed: bool
    reason: str
    enriched_envelope: dict[str, Any]
    attestation: Attestation | None = None
    warnings: list[str] = field(default_factory=list)
    correlation_id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )


# ---------------------------------------------------------------------------
# AIP Trust Layer
# ---------------------------------------------------------------------------


class AIPTrustLayer:
    """Trust/attestation layer that wraps A2A interactions.

    This is the primary entry point for the AIP-over-A2A architecture.
    It verifies identities, checks trust thresholds, injects attestations
    into A2A envelopes, and logs audit events.

    Args:
        db: An optional async database session.  If None, trust checks
            default to deny (except discovery).
        thresholds: Optional override mapping of interaction_type -> min score.
    """

    def __init__(
        self,
        db: Any = None,
        thresholds: dict[str, float] | None = None,
    ) -> None:
        self._db = db
        self._thresholds = thresholds or DEFAULT_TRUST_THRESHOLDS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_outbound(
        self,
        sender_id: str,
        receiver_id: str,
        a2a_envelope: dict[str, Any],
        interaction_type: str,
        custom_threshold: float | None = None,
    ) -> TrustLayerResult:
        """Run trust verification on an outbound A2A message.

        1. Resolve sender/receiver trust scores and DIDs.
        2. Enforce trust threshold for the interaction type.
        3. Inject an ``aip_attestation`` section into the envelope.
        4. Log audit trail.

        Returns a ``TrustLayerResult`` indicating whether the message
        should be forwarded.
        """
        threshold = custom_threshold or self._thresholds.get(
            interaction_type, 0.5
        )
        correlation_id = str(uuid.uuid4())
        warnings: list[str] = []

        sender_score, sender_did, sender_modifier = await self._resolve(
            sender_id, warnings, "sender"
        )
        receiver_score, receiver_did, _ = await self._resolve(
            receiver_id, warnings, "receiver"
        )

        effective_score = (sender_score or 0.0) * sender_modifier
        passes = effective_score >= threshold

        # Without DB and non-discovery, deny
        if self._db is None and interaction_type != "discover":
            passes = False
            if not any("database" in w.lower() for w in warnings):
                warnings.append(
                    "No database session — trust verification unavailable"
                )

        attestation = Attestation(
            issuer_did=sender_did,
            subject_did=receiver_did,
            trust_score=sender_score,
            framework_modifier=sender_modifier,
            interaction_type=interaction_type,
        )

        # Inject attestation into envelope
        enriched = dict(a2a_envelope)
        enriched["aip_attestation"] = attestation.to_dict()
        enriched.setdefault("aip_metadata", {})
        enriched["aip_metadata"]["correlation_id"] = correlation_id
        enriched["aip_metadata"]["trust_threshold"] = threshold
        enriched["aip_metadata"]["trust_passed"] = passes

        if passes:
            reason = (
                f"AIP trust check passed: sender score "
                f"{sender_score or 0:.2f} x modifier {sender_modifier:.2f} "
                f"= {effective_score:.2f} >= {threshold:.2f} "
                f"for '{interaction_type}'"
            )
        else:
            reason = (
                f"AIP trust check failed: sender score "
                f"{sender_score or 0:.2f} x modifier {sender_modifier:.2f} "
                f"= {effective_score:.2f} < {threshold:.2f} "
                f"for '{interaction_type}'"
            )

        result = TrustLayerResult(
            allowed=passes,
            reason=reason,
            enriched_envelope=enriched,
            attestation=attestation,
            warnings=warnings,
            correlation_id=correlation_id,
        )

        await self._log_audit(result, sender_id, receiver_id)

        return result

    async def verify_inbound(
        self,
        a2a_envelope: dict[str, Any],
    ) -> bool:
        """Verify trust attestation on an inbound A2A message.

        Returns True if the envelope contains a valid AIP attestation
        that passed its trust threshold.
        """
        attestation_data = a2a_envelope.get("aip_attestation")
        if attestation_data is None:
            return False
        metadata = a2a_envelope.get("aip_metadata", {})
        return bool(metadata.get("trust_passed", False))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve(
        self,
        entity_id: str,
        warnings: list[str],
        role: str,
    ) -> tuple[float | None, str | None, float]:
        """Resolve trust score, DID, and framework modifier."""
        if self._db is None:
            warnings.append(
                f"No database session — cannot resolve {role} trust"
            )
            return None, None, 1.0

        try:
            from sqlalchemy import select

            from src.models import Entity, TrustScore

            entity = await self._db.get(Entity, uuid.UUID(entity_id))
            if entity is None:
                warnings.append(f"{role.capitalize()} entity not found")
                return None, None, 1.0

            score_row = await self._db.scalar(
                select(TrustScore.score).where(
                    TrustScore.entity_id == entity.id
                )
            )
            modifier = entity.framework_trust_modifier or 1.0
            if score_row is None:
                warnings.append(
                    f"{role.capitalize()} has no trust score record"
                )
            return score_row, entity.did_web, modifier
        except Exception:
            logger.exception("Failed to resolve %s trust", role)
            warnings.append(f"Trust resolution failed for {role}")
            return None, None, 1.0

    async def _log_audit(
        self,
        result: TrustLayerResult,
        sender_id: str,
        receiver_id: str,
    ) -> None:
        """Log to audit trail and application logger."""
        level = "ALLOWED" if result.allowed else "DENIED"
        logger.info(
            "AIP trust layer: %s — %s (correlation=%s)",
            level,
            result.reason,
            result.correlation_id,
        )

        if self._db is None:
            return

        try:
            from src.audit import log_action

            await log_action(
                self._db,
                action="aip.trust_layer_check",
                entity_id=uuid.UUID(sender_id),
                resource_type="a2a_interaction",
                resource_id=uuid.UUID(result.correlation_id),
                details={
                    "receiver_id": receiver_id,
                    "interaction_type": (
                        result.attestation.interaction_type
                        if result.attestation
                        else "unknown"
                    ),
                    "allowed": result.allowed,
                    "reason": result.reason,
                    "warnings": result.warnings,
                    "attestation_id": (
                        result.attestation.attestation_id
                        if result.attestation
                        else None
                    ),
                },
            )
        except Exception:
            logger.exception("Failed to log AIP audit event")
