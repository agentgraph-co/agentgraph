"""Tests for the AIP trust layer (AIP-over-A2A architecture)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, TrustScore
from src.protocol.aip_trust_layer import (
    AIPTrustLayer,
    Attestation,
)


@pytest_asyncio.fixture
async def trusted_agent(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"aip_trusted_{uuid.uuid4().hex[:6]}@test.com",
        display_name="TrustedAgent",
        type="agent",
        is_active=True,
        did_web=f"did:web:agentgraph.co:agents:{eid}",
        framework_source="mcp",
        framework_trust_modifier=0.95,
    )
    db.add(agent)
    ts = TrustScore(id=uuid.uuid4(), entity_id=eid, score=0.90)
    db.add(ts)
    await db.flush()
    return agent


@pytest_asyncio.fixture
async def untrusted_agent(db: AsyncSession) -> Entity:
    eid = uuid.uuid4()
    agent = Entity(
        id=eid,
        email=f"aip_untrusted_{uuid.uuid4().hex[:6]}@test.com",
        display_name="UntrustedAgent",
        type="agent",
        is_active=True,
        did_web=f"did:web:agentgraph.co:agents:{eid}",
        framework_source="openclaw",
        framework_trust_modifier=0.50,
    )
    db.add(agent)
    ts = TrustScore(id=uuid.uuid4(), entity_id=eid, score=0.20)
    db.add(ts)
    await db.flush()
    return agent


class TestAIPTrustLayerOutbound:
    """Tests for process_outbound() — the core trust verification path."""

    @pytest.mark.asyncio
    async def test_high_trust_delegation_allowed(
        self, db: AsyncSession, trusted_agent: Entity, untrusted_agent: Entity,
    ) -> None:
        layer = AIPTrustLayer(db=db)
        envelope = {"type": "delegate_request", "payload": {"task": "summarize"}}

        result = await layer.process_outbound(
            sender_id=str(trusted_agent.id),
            receiver_id=str(untrusted_agent.id),
            a2a_envelope=envelope,
            interaction_type="delegate",
        )

        # 0.90 * 0.95 = 0.855 >= 0.6 threshold
        assert result.allowed is True
        assert "passed" in result.reason
        assert result.attestation is not None
        assert result.enriched_envelope["aip_attestation"]["trust_score"] == 0.90

    @pytest.mark.asyncio
    async def test_low_trust_delegation_denied(
        self, db: AsyncSession, trusted_agent: Entity, untrusted_agent: Entity,
    ) -> None:
        layer = AIPTrustLayer(db=db)
        envelope = {"type": "delegate_request", "payload": {}}

        result = await layer.process_outbound(
            sender_id=str(untrusted_agent.id),
            receiver_id=str(trusted_agent.id),
            a2a_envelope=envelope,
            interaction_type="delegate",
        )

        # 0.20 * 0.50 = 0.10 < 0.6 threshold
        assert result.allowed is False
        assert "failed" in result.reason

    @pytest.mark.asyncio
    async def test_discovery_always_allowed(
        self, db: AsyncSession, untrusted_agent: Entity, trusted_agent: Entity,
    ) -> None:
        layer = AIPTrustLayer(db=db)
        envelope = {"type": "discover_request", "payload": {}}

        result = await layer.process_outbound(
            sender_id=str(untrusted_agent.id),
            receiver_id=str(trusted_agent.id),
            a2a_envelope=envelope,
            interaction_type="discover",
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_custom_threshold_override(
        self, db: AsyncSession, untrusted_agent: Entity, trusted_agent: Entity,
    ) -> None:
        layer = AIPTrustLayer(db=db)
        envelope = {"type": "delegate_request", "payload": {}}

        result = await layer.process_outbound(
            sender_id=str(untrusted_agent.id),
            receiver_id=str(trusted_agent.id),
            a2a_envelope=envelope,
            interaction_type="delegate",
            custom_threshold=0.05,
        )

        # 0.20 * 0.50 = 0.10 >= 0.05 custom threshold
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_financial_high_threshold(
        self, db: AsyncSession, trusted_agent: Entity, untrusted_agent: Entity,
    ) -> None:
        layer = AIPTrustLayer(db=db)
        envelope = {"type": "financial_request", "payload": {}}

        result = await layer.process_outbound(
            sender_id=str(trusted_agent.id),
            receiver_id=str(untrusted_agent.id),
            a2a_envelope=envelope,
            interaction_type="financial",
        )

        # 0.90 * 0.95 = 0.855 >= 0.8 threshold for financial
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_envelope_enrichment(
        self, db: AsyncSession, trusted_agent: Entity, untrusted_agent: Entity,
    ) -> None:
        layer = AIPTrustLayer(db=db)
        envelope = {"type": "delegate_request", "payload": {"task": "x"}}

        result = await layer.process_outbound(
            sender_id=str(trusted_agent.id),
            receiver_id=str(untrusted_agent.id),
            a2a_envelope=envelope,
            interaction_type="delegate",
        )

        # Verify envelope enrichment
        enriched = result.enriched_envelope
        assert "aip_attestation" in enriched
        assert "aip_metadata" in enriched
        assert enriched["aip_metadata"]["trust_passed"] is True
        assert enriched["aip_metadata"]["trust_threshold"] == 0.6
        assert "correlation_id" in enriched["aip_metadata"]

        # Original envelope fields preserved
        assert enriched["type"] == "delegate_request"
        assert enriched["payload"]["task"] == "x"


class TestAIPTrustLayerNoDb:
    """Tests when no database session is available."""

    @pytest.mark.asyncio
    async def test_no_db_denies_non_discovery(self) -> None:
        layer = AIPTrustLayer(db=None)
        envelope = {"type": "delegate_request", "payload": {}}

        result = await layer.process_outbound(
            sender_id=str(uuid.uuid4()),
            receiver_id=str(uuid.uuid4()),
            a2a_envelope=envelope,
            interaction_type="delegate",
        )

        assert result.allowed is False
        assert any("database" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_no_db_allows_discovery(self) -> None:
        layer = AIPTrustLayer(db=None)
        envelope = {"type": "discover_request", "payload": {}}

        result = await layer.process_outbound(
            sender_id=str(uuid.uuid4()),
            receiver_id=str(uuid.uuid4()),
            a2a_envelope=envelope,
            interaction_type="discover",
        )

        assert result.allowed is True


class TestAIPTrustLayerInbound:
    """Tests for verify_inbound() — checking incoming attestations."""

    @pytest.mark.asyncio
    async def test_valid_inbound(self) -> None:
        layer = AIPTrustLayer()
        envelope = {
            "type": "delegate_request",
            "aip_attestation": {"trust_score": 0.9},
            "aip_metadata": {"trust_passed": True},
        }

        assert await layer.verify_inbound(envelope) is True

    @pytest.mark.asyncio
    async def test_invalid_inbound_no_attestation(self) -> None:
        layer = AIPTrustLayer()
        envelope = {"type": "delegate_request"}

        assert await layer.verify_inbound(envelope) is False

    @pytest.mark.asyncio
    async def test_invalid_inbound_failed_trust(self) -> None:
        layer = AIPTrustLayer()
        envelope = {
            "type": "delegate_request",
            "aip_attestation": {"trust_score": 0.1},
            "aip_metadata": {"trust_passed": False},
        }

        assert await layer.verify_inbound(envelope) is False


class TestAttestationModel:
    """Tests for the Attestation data class."""

    def test_to_dict(self) -> None:
        att = Attestation(
            issuer_did="did:web:example.com",
            subject_did="did:web:target.com",
            trust_score=0.85,
            framework_modifier=0.9,
            interaction_type="delegate",
        )
        d = att.to_dict()
        assert d["issuer_did"] == "did:web:example.com"
        assert d["trust_score"] == 0.85
        assert d["framework_modifier"] == 0.9
        assert d["interaction_type"] == "delegate"
        assert "attestation_id" in d
        assert "issued_at" in d

    def test_default_fields(self) -> None:
        att = Attestation(
            issuer_did=None,
            subject_did=None,
            trust_score=None,
            framework_modifier=1.0,
            interaction_type="discover",
        )
        assert att.attestation_id is not None
        assert att.issued_at is not None


class TestTrustLayerCustomThresholds:
    """Tests for custom threshold configuration."""

    @pytest.mark.asyncio
    async def test_custom_thresholds_map(self) -> None:
        custom = {"delegate": 0.99, "discover": 0.0}
        layer = AIPTrustLayer(db=None, thresholds=custom)
        envelope = {"type": "discover_request"}

        result = await layer.process_outbound(
            sender_id=str(uuid.uuid4()),
            receiver_id=str(uuid.uuid4()),
            a2a_envelope=envelope,
            interaction_type="discover",
        )

        assert result.allowed is True
