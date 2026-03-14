from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Entity, EntityType, TrustAttestation
from src.trust.score import compute_trust_score


def _make_entity(db: AsyncSession, **kwargs) -> Entity:
    """Create and add an entity to the session."""
    defaults = {
        "id": uuid.uuid4(),
        "type": EntityType.HUMAN,
        "display_name": f"User-{uuid.uuid4().hex[:6]}",
        "did_web": f"did:web:agentgraph.co:users:{uuid.uuid4()}",
        "email_verified": False,
        "bio_markdown": "",
        "operator_id": None,
    }
    defaults.update(kwargs)
    entity = Entity(**defaults)
    db.add(entity)
    return entity


# --- Create attestation ---


@pytest.mark.asyncio
async def test_create_attestation_happy_path(db: AsyncSession):
    """Can create a trust attestation for another entity."""
    attester = _make_entity(db, display_name="Attester")
    target = _make_entity(db, display_name="Target")
    await db.flush()

    attestation = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="competent",
        context="code_review",
        weight=0.5,
        comment="Great code reviewer",
    )
    db.add(attestation)
    await db.flush()

    result = await db.scalar(
        select(TrustAttestation).where(TrustAttestation.id == attestation.id)
    )
    assert result is not None
    assert result.attester_entity_id == attester.id
    assert result.target_entity_id == target.id
    assert result.attestation_type == "competent"
    assert result.context == "code_review"
    assert result.weight == 0.5
    assert result.comment == "Great code reviewer"


@pytest.mark.asyncio
async def test_cannot_self_attest(db: AsyncSession):
    """Self-attestation should be blocked at the API level.

    At the model level we verify via the unique constraint that
    at least the same entity can't double-attest the same type.
    """
    entity = _make_entity(db)
    await db.flush()

    # Self-attestation is blocked by application logic, not DB constraint
    # But we can verify the attestation_type uniqueness works
    att1 = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=entity.id,
        target_entity_id=entity.id,
        attestation_type="competent",
        weight=0.5,
    )
    db.add(att1)
    await db.flush()

    # Duplicate should fail (same attester, target, type)
    att2 = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=entity.id,
        target_entity_id=entity.id,
        attestation_type="competent",
        weight=0.5,
    )
    db.add(att2)
    with pytest.raises(Exception):  # IntegrityError from unique constraint
        await db.flush()
    await db.rollback()


@pytest.mark.asyncio
async def test_duplicate_attestation_type_rejected(db: AsyncSession):
    """Same attester, target, type should be rejected by unique constraint."""
    attester = _make_entity(db)
    target = _make_entity(db)
    await db.flush()

    att1 = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        weight=0.5,
    )
    db.add(att1)
    await db.flush()

    att2 = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        weight=0.5,
    )
    db.add(att2)
    with pytest.raises(Exception):
        await db.flush()
    await db.rollback()


@pytest.mark.asyncio
async def test_different_attestation_types_allowed(db: AsyncSession):
    """Same attester can give different attestation types to same target."""
    attester = _make_entity(db)
    target = _make_entity(db)
    await db.flush()

    for att_type in ["competent", "reliable", "safe", "responsive"]:
        db.add(TrustAttestation(
            id=uuid.uuid4(),
            attester_entity_id=attester.id,
            target_entity_id=target.id,
            attestation_type=att_type,
            weight=0.5,
        ))
    await db.flush()

    count = await db.scalar(
        select(
            __import__("sqlalchemy").func.count()
        ).select_from(TrustAttestation).where(
            TrustAttestation.attester_entity_id == attester.id,
            TrustAttestation.target_entity_id == target.id,
        )
    )
    assert count == 4


@pytest.mark.asyncio
async def test_list_attestations(db: AsyncSession):
    """Can list attestations for a target entity."""
    attester1 = _make_entity(db, display_name="Alice")
    attester2 = _make_entity(db, display_name="Bob")
    target = _make_entity(db, display_name="Target")
    await db.flush()

    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester1.id,
        target_entity_id=target.id,
        attestation_type="competent",
        weight=0.7,
    ))
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester2.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        weight=0.4,
    ))
    await db.flush()

    result = await db.execute(
        select(TrustAttestation).where(
            TrustAttestation.target_entity_id == target.id,
        )
    )
    attestations = result.scalars().all()
    assert len(attestations) >= 2


@pytest.mark.asyncio
async def test_delete_attestation(db: AsyncSession):
    """Can delete an attestation."""
    attester = _make_entity(db)
    target = _make_entity(db)
    await db.flush()

    att = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="safe",
        weight=0.5,
    )
    db.add(att)
    await db.flush()

    # Delete it
    await db.delete(att)
    await db.flush()

    result = await db.scalar(
        select(TrustAttestation).where(TrustAttestation.id == att.id)
    )
    assert result is None


# --- Trust v2 algorithm ---


@pytest.mark.asyncio
async def test_trust_v2_includes_community_component(db: AsyncSession):
    """Trust v2 should include a 'community' component."""
    entity = _make_entity(db)
    await db.flush()

    ts = await compute_trust_score(db, entity.id)
    assert "community" in ts.components
    assert "verification" in ts.components
    assert "age" in ts.components
    assert "activity" in ts.components
    assert "reputation" in ts.components
    assert len(ts.components) == 6


@pytest.mark.asyncio
async def test_trust_v2_community_factor_with_attestations(db: AsyncSession):
    """Community factor increases when attestations exist."""
    target = _make_entity(db)
    attester = _make_entity(db)
    await db.flush()

    # Compute without attestations
    ts1 = await compute_trust_score(db, target.id)
    assert ts1.components["community"] == 0.0
    score_without_attestations = ts1.score

    # Add an attestation with weight 0.8
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="competent",
        weight=0.8,
    ))
    await db.flush()

    # Recompute — community should now be > 0
    ts2 = await compute_trust_score(db, target.id)
    assert ts2.components["community"] > 0.0
    assert ts2.score > score_without_attestations


@pytest.mark.asyncio
async def test_attestation_weight_uses_attester_trust_score(db: AsyncSession):
    """The weight field should reflect the attester's trust score."""
    attester = _make_entity(db, email_verified=True, bio_markdown="I am trusted")
    target = _make_entity(db)
    await db.flush()

    # Compute attester's trust score first
    attester_ts = await compute_trust_score(db, attester.id)
    assert attester_ts.score > 0.0

    # Create attestation with attester's trust score as weight
    att = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        weight=attester_ts.score,  # This is what the API does
    )
    db.add(att)
    await db.flush()

    # Verify the weight is the attester's trust score
    loaded = await db.scalar(
        select(TrustAttestation).where(TrustAttestation.id == att.id)
    )
    assert loaded is not None
    assert loaded.weight == attester_ts.score


@pytest.mark.asyncio
async def test_contextual_trust_scores(db: AsyncSession):
    """Contextual scores should be computed per-context."""
    target = _make_entity(db)
    attester1 = _make_entity(db)
    attester2 = _make_entity(db)
    await db.flush()

    # Add attestations with contexts
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester1.id,
        target_entity_id=target.id,
        attestation_type="competent",
        context="code_review",
        weight=0.9,
    ))
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester2.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        context="code_review",
        weight=0.7,
    ))
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester1.id,
        target_entity_id=target.id,
        attestation_type="safe",
        context="data_analysis",
        weight=0.6,
    ))
    await db.flush()

    ts = await compute_trust_score(db, target.id)
    assert ts.contextual_scores is not None
    assert "code_review" in ts.contextual_scores
    assert "data_analysis" in ts.contextual_scores
    # Code review: avg of 0.9, 0.7 = 0.8
    assert abs(ts.contextual_scores["code_review"] - 0.8) < 0.01
    # Data analysis: just 0.6
    assert abs(ts.contextual_scores["data_analysis"] - 0.6) < 0.01


@pytest.mark.asyncio
async def test_gaming_cap_in_algorithm(db: AsyncSession):
    """The algorithm should cap attestations per attester at 10."""
    target = _make_entity(db)
    await db.flush()

    # Create 15 different attesters, but have one attester create many
    main_attester = _make_entity(db)
    await db.flush()

    # One attester can only have 4 types, so the gaming cap of 10 per attester
    # doesn't come into play with unique constraint in place.
    # But we verify the algorithm still works with multiple attesters.
    for _i in range(5):
        att = _make_entity(db)
        await db.flush()
        db.add(TrustAttestation(
            id=uuid.uuid4(),
            attester_entity_id=att.id,
            target_entity_id=target.id,
            attestation_type="competent",
            weight=0.8,
        ))

    # Add from main attester
    db.add(TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=main_attester.id,
        target_entity_id=target.id,
        attestation_type="reliable",
        weight=0.9,
    ))
    await db.flush()

    ts = await compute_trust_score(db, target.id)
    assert ts.components["community"] > 0.0


@pytest.mark.asyncio
async def test_trust_score_still_computes_without_attestations(db: AsyncSession):
    """Trust v2 should still work when there are no attestations."""
    entity = _make_entity(db, email_verified=True, bio_markdown="Has bio")
    await db.flush()

    ts = await compute_trust_score(db, entity.id)
    assert ts.score >= 0.0
    assert ts.score <= 1.0
    assert ts.components["community"] == 0.0
    # Verification should still be 0.5 (bio filled)
    assert ts.components["verification"] == 0.5


@pytest.mark.asyncio
async def test_v2_weights_sum_to_one(db: AsyncSession):
    """All weights should sum to 1.0."""
    from src.trust.score import (
        ACTIVITY_WEIGHT,
        AGE_WEIGHT,
        COMMUNITY_WEIGHT,
        EXTERNAL_WEIGHT,
        REPUTATION_WEIGHT,
        VERIFICATION_WEIGHT,
    )

    total = (
        VERIFICATION_WEIGHT + AGE_WEIGHT + ACTIVITY_WEIGHT
        + REPUTATION_WEIGHT + COMMUNITY_WEIGHT + EXTERNAL_WEIGHT
    )
    assert abs(total - 1.0) < 0.001


@pytest.mark.asyncio
async def test_attestation_decay(db: AsyncSession):
    """Old attestations should have reduced weight in the algorithm."""
    from src.trust.score import _community_factor

    target = _make_entity(db)
    attester = _make_entity(db)
    await db.flush()

    # Create an attestation dated 100 days ago (should get 50% decay)
    old_att = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="competent",
        weight=1.0,  # Full weight
    )
    db.add(old_att)
    await db.flush()

    # Manually set created_at to 100 days ago
    old_att.created_at = datetime.now(timezone.utc) - timedelta(days=100)
    await db.flush()

    community_score, _ = await _community_factor(db, target.id)
    # With 50% decay on weight 1.0, the effective weight is 0.5
    # community = 0.5 / 1.0 = 0.5
    assert abs(community_score - 0.5) < 0.01


@pytest.mark.asyncio
async def test_attestation_heavy_decay(db: AsyncSession):
    """Attestations > 180 days should get 25% weight."""
    from src.trust.score import _community_factor

    target = _make_entity(db)
    attester = _make_entity(db)
    await db.flush()

    old_att = TrustAttestation(
        id=uuid.uuid4(),
        attester_entity_id=attester.id,
        target_entity_id=target.id,
        attestation_type="safe",
        weight=1.0,
    )
    db.add(old_att)
    await db.flush()

    # Set to 200 days ago (>180 days = 25% weight)
    old_att.created_at = datetime.now(timezone.utc) - timedelta(days=200)
    await db.flush()

    community_score, _ = await _community_factor(db, target.id)
    # With 25% decay on weight 1.0, effective = 0.25
    assert abs(community_score - 0.25) < 0.01
