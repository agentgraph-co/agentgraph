"""Tests for token economics endpoints (balance, transfer, staking, rewards)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.token_router import router as token_router
from src.config import settings
from src.database import get_db
from src.main import app

PREFIX = "/api/v1/tokens"

# Ensure the token router is registered (main.py registration pending).
_token_router_registered = False


def _ensure_router():
    global _token_router_registered
    if not _token_router_registered:
        app.include_router(token_router, prefix=settings.api_v1_prefix)
        _token_router_registered = True


@pytest_asyncio.fixture
async def client(db):
    _ensure_router()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(client: AsyncClient, suffix: str | None = None):
    """Register a user via API and return (token, entity_id)."""
    sfx = suffix or uuid.uuid4().hex[:8]
    email = f"tok_{sfx}@example.com"
    body = {
        "email": email,
        "password": "Str0ngP@ss1",
        "display_name": f"TokUser {sfx}",
    }
    await client.post("/api/v1/auth/register", json=body)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Str0ngP@ss1"},
    )
    token = resp.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    return token, me.json()["id"]


# ---------------------------------------------------------------------------
# GET /tokens/info — Public token info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_token_info(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "AGNT"
    assert data["symbol"] == "AGNT"
    assert data["total_supply"] == 1_000_000_000
    assert "distribution" in data
    assert "community_rewards" in data["distribution"]


@pytest.mark.asyncio
async def test_token_info_distribution_sums_to_one(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/info")
    data = resp.json()
    total = sum(data["distribution"].values())
    assert abs(total - 1.0) < 0.001


# ---------------------------------------------------------------------------
# GET /tokens/balance — Authenticated balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_balance_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/balance")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_balance_default_initial(client: AsyncClient):
    token, eid = await _create_user(client)
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{PREFIX}/balance", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["balance"] == 100
    assert data["staked"] == 0
    assert data["available"] == 100
    assert data["trust_boost"] == 0


# ---------------------------------------------------------------------------
# POST /tokens/transfer — Transfer tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transfer_requires_auth(client: AsyncClient):
    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": str(uuid.uuid4()), "amount": 10},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_transfer_success(client: AsyncClient):
    sender_token, sender_id = await _create_user(client, "sender1")
    recipient_token, recipient_id = await _create_user(client, "recv1")
    sender_headers = {"Authorization": f"Bearer {sender_token}"}
    recipient_headers = {"Authorization": f"Bearer {recipient_token}"}

    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recipient_id, "amount": 25, "memo": "tip"},
        headers=sender_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sender_id"] == sender_id
    assert data["recipient_id"] == recipient_id
    assert data["amount"] == 25
    assert data["memo"] == "tip"
    assert data["sender_balance"] == 75

    # Verify recipient balance increased
    resp = await client.get(f"{PREFIX}/balance", headers=recipient_headers)
    assert resp.json()["balance"] == 125


@pytest.mark.asyncio
async def test_transfer_insufficient_balance(client: AsyncClient):
    sender_token, _ = await _create_user(client, "poor1")
    _, recipient_id = await _create_user(client, "rich1")
    headers = {"Authorization": f"Bearer {sender_token}"}

    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recipient_id, "amount": 999},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Insufficient" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_transfer_to_self_rejected(client: AsyncClient):
    token, eid = await _create_user(client, "self1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": eid, "amount": 10},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "yourself" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_transfer_invalid_recipient(client: AsyncClient):
    token, _ = await _create_user(client, "bad1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": str(uuid.uuid4()), "amount": 10},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transfer_invalid_recipient_format(client: AsyncClient):
    token, _ = await _create_user(client, "badfmt1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": "not-a-uuid", "amount": 10},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Invalid recipient_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_transfer_respects_staked_lockup(client: AsyncClient):
    """Staked tokens should not be available for transfer."""
    token, _ = await _create_user(client, "lock1")
    _, recipient_id = await _create_user(client, "lockrecv1")
    headers = {"Authorization": f"Bearer {token}"}

    # Stake 80 of 100
    await client.post(
        f"{PREFIX}/stake",
        json={"amount": 80},
        headers=headers,
    )

    # Try to transfer 30 (only 20 available)
    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recipient_id, "amount": 30},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Insufficient" in resp.json()["detail"]

    # Transfer 15 should succeed
    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recipient_id, "amount": 15},
        headers=headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_transfer_zero_amount_rejected(client: AsyncClient):
    """Pydantic validation should reject amount <= 0."""
    token, _ = await _create_user(client, "zero1")
    _, recipient_id = await _create_user(client, "zerorecv1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recipient_id, "amount": 0},
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /tokens/stake — Stake tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stake_requires_auth(client: AsyncClient):
    resp = await client.post(f"{PREFIX}/stake", json={"amount": 10})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stake_success(client: AsyncClient):
    token, eid = await _create_user(client, "stk1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/stake", json={"amount": 50}, headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["staked"] == 50
    assert data["available"] == 50
    assert data["trust_boost"] > 0


@pytest.mark.asyncio
async def test_stake_insufficient_balance(client: AsyncClient):
    token, _ = await _create_user(client, "stk2")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/stake", json={"amount": 200}, headers=headers,
    )
    assert resp.status_code == 400
    assert "Insufficient" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_stake_minimum_enforced(client: AsyncClient):
    token, _ = await _create_user(client, "stk3")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/stake", json={"amount": 5}, headers=headers,
    )
    assert resp.status_code == 400
    assert "Minimum stake" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_stake_cumulative(client: AsyncClient):
    """Multiple stakes should accumulate."""
    token, _ = await _create_user(client, "stk4")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(f"{PREFIX}/stake", json={"amount": 30}, headers=headers)
    resp = await client.post(
        f"{PREFIX}/stake", json={"amount": 20}, headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["staked"] == 50
    assert resp.json()["available"] == 50


# ---------------------------------------------------------------------------
# POST /tokens/unstake — Unstake tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unstake_requires_auth(client: AsyncClient):
    resp = await client.post(f"{PREFIX}/unstake", json={"amount": 10})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unstake_success(client: AsyncClient):
    token, eid = await _create_user(client, "unstk1")
    headers = {"Authorization": f"Bearer {token}"}

    # Stake first
    await client.post(f"{PREFIX}/stake", json={"amount": 50}, headers=headers)

    # Unstake part
    resp = await client.post(
        f"{PREFIX}/unstake", json={"amount": 20}, headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["staked"] == 30
    assert data["available"] == 70


@pytest.mark.asyncio
async def test_unstake_exceeds_staked(client: AsyncClient):
    token, _ = await _create_user(client, "unstk2")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(f"{PREFIX}/stake", json={"amount": 30}, headers=headers)

    resp = await client.post(
        f"{PREFIX}/unstake", json={"amount": 50}, headers=headers,
    )
    assert resp.status_code == 400
    assert "Cannot unstake" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_unstake_nothing_staked(client: AsyncClient):
    token, _ = await _create_user(client, "unstk3")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/unstake", json={"amount": 10}, headers=headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /tokens/rewards — Check pending rewards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rewards_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/rewards")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rewards_zero_when_not_staked(client: AsyncClient):
    token, eid = await _create_user(client, "rwd1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"{PREFIX}/rewards", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["pending_rewards"] == 0
    assert data["staked"] == 0


@pytest.mark.asyncio
async def test_rewards_positive_when_staked(client: AsyncClient):
    token, _ = await _create_user(client, "rwd2")
    headers = {"Authorization": f"Bearer {token}"}

    # Stake tokens
    await client.post(f"{PREFIX}/stake", json={"amount": 50}, headers=headers)

    # Check rewards — should be positive (first-time = one full cycle)
    resp = await client.get(f"{PREFIX}/rewards", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_rewards"] > 0
    assert data["staked"] == 50


# ---------------------------------------------------------------------------
# POST /tokens/claim-rewards — Claim earned rewards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_rewards_requires_auth(client: AsyncClient):
    resp = await client.post(f"{PREFIX}/claim-rewards")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_claim_rewards_success(client: AsyncClient):
    token, eid = await _create_user(client, "clm1")
    headers = {"Authorization": f"Bearer {token}"}

    # Stake to earn rewards
    await client.post(f"{PREFIX}/stake", json={"amount": 50}, headers=headers)

    # Claim
    resp = await client.post(f"{PREFIX}/claim-rewards", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["claimed_amount"] > 0
    assert data["new_balance"] > 100  # initial 100 + reward
    assert data["claimed_at"] is not None


@pytest.mark.asyncio
async def test_claim_rewards_no_stake(client: AsyncClient):
    token, _ = await _create_user(client, "clm2")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(f"{PREFIX}/claim-rewards", headers=headers)
    assert resp.status_code == 400
    assert "No pending rewards" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_claim_rewards_updates_balance(client: AsyncClient):
    """After claiming, balance should reflect the reward."""
    token, _ = await _create_user(client, "clm3")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(f"{PREFIX}/stake", json={"amount": 50}, headers=headers)
    claim_resp = await client.post(f"{PREFIX}/claim-rewards", headers=headers)
    claimed = claim_resp.json()["claimed_amount"]

    # Balance should be 100 + claimed
    bal_resp = await client.get(f"{PREFIX}/balance", headers=headers)
    assert bal_resp.json()["balance"] == 100 + claimed


# ---------------------------------------------------------------------------
# GET /tokens/history — Transaction history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_requires_auth(client: AsyncClient):
    resp = await client.get(f"{PREFIX}/history")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_history_empty_initially(client: AsyncClient):
    token, eid = await _create_user(client, "hist1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"{PREFIX}/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == eid
    assert data["transactions"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_history_after_operations(client: AsyncClient):
    """History should include stake, transfer, and reward transactions."""
    token, sender_id = await _create_user(client, "hist2")
    _, recipient_id = await _create_user(client, "hist2recv")
    headers = {"Authorization": f"Bearer {token}"}

    # Stake
    await client.post(f"{PREFIX}/stake", json={"amount": 30}, headers=headers)
    # Transfer
    await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recipient_id, "amount": 10},
        headers=headers,
    )

    resp = await client.get(f"{PREFIX}/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    types = [t["type"] for t in data["transactions"]]
    assert "stake" in types
    assert "transfer_out" in types


@pytest.mark.asyncio
async def test_history_pagination(client: AsyncClient):
    token, _ = await _create_user(client, "hist3")
    _, recipient_id = await _create_user(client, "hist3recv")
    headers = {"Authorization": f"Bearer {token}"}

    # Create multiple transactions
    for _i in range(5):
        await client.post(
            f"{PREFIX}/transfer",
            json={"recipient_id": recipient_id, "amount": 1},
            headers=headers,
        )

    # Request page with limit
    resp = await client.get(
        f"{PREFIX}/history?limit=2&offset=0", headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["transactions"]) == 2
    assert data["total"] == 5

    # Second page
    resp = await client.get(
        f"{PREFIX}/history?limit=2&offset=2", headers=headers,
    )
    assert len(resp.json()["transactions"]) == 2


@pytest.mark.asyncio
async def test_history_newest_first(client: AsyncClient):
    """Transactions should be returned newest first."""
    token, _ = await _create_user(client, "hist4")
    headers = {"Authorization": f"Bearer {token}"}

    # Stake then unstake — unstake should be first in history
    await client.post(f"{PREFIX}/stake", json={"amount": 30}, headers=headers)
    await client.post(
        f"{PREFIX}/unstake", json={"amount": 10}, headers=headers,
    )

    resp = await client.get(f"{PREFIX}/history", headers=headers)
    txs = resp.json()["transactions"]
    assert txs[0]["type"] == "unstake"
    assert txs[1]["type"] == "stake"


# ---------------------------------------------------------------------------
# GET /tokens/leaderboard — Top token holders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_leaderboard(client: AsyncClient):
    # Create a few users (all start with 100)
    await _create_user(client, "lb1")
    await _create_user(client, "lb2")

    resp = await client.get(f"{PREFIX}/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert data["total_entities"] >= 2
    if data["entries"]:
        first = data["entries"][0]
        assert first["rank"] == 1
        assert "display_name" in first
        assert "balance" in first


@pytest.mark.asyncio
async def test_leaderboard_limit(client: AsyncClient):
    await _create_user(client, "lblim1")
    await _create_user(client, "lblim2")
    await _create_user(client, "lblim3")

    resp = await client.get(f"{PREFIX}/leaderboard?limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) <= 2


@pytest.mark.asyncio
async def test_leaderboard_ranked_by_balance(client: AsyncClient):
    """Entities with higher balance should rank higher."""
    tok_a, id_a = await _create_user(client, "lbrank1")
    tok_b, id_b = await _create_user(client, "lbrank2")

    # Give user B more tokens by having A transfer to B
    await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": id_b, "amount": 50},
        headers={"Authorization": f"Bearer {tok_a}"},
    )

    resp = await client.get(f"{PREFIX}/leaderboard?limit=100")
    data = resp.json()
    entries = data["entries"]

    # Find positions
    pos_a = next(
        (e["rank"] for e in entries if e["entity_id"] == id_a), None,
    )
    pos_b = next(
        (e["rank"] for e in entries if e["entity_id"] == id_b), None,
    )
    assert pos_a is not None and pos_b is not None
    # B (150) should rank higher (lower rank number) than A (50)
    assert pos_b < pos_a


# ---------------------------------------------------------------------------
# Integration / edge-case tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle(client: AsyncClient):
    """Full flow: balance -> stake -> rewards -> claim -> unstake -> transfer."""
    tok, eid = await _create_user(client, "life1")
    _, recv_id = await _create_user(client, "liferecv1")
    headers = {"Authorization": f"Bearer {tok}"}

    # 1. Check initial balance
    resp = await client.get(f"{PREFIX}/balance", headers=headers)
    assert resp.json()["balance"] == 100

    # 2. Stake
    resp = await client.post(
        f"{PREFIX}/stake", json={"amount": 40}, headers=headers,
    )
    assert resp.json()["staked"] == 40
    assert resp.json()["available"] == 60

    # 3. Check rewards
    resp = await client.get(f"{PREFIX}/rewards", headers=headers)
    assert resp.json()["pending_rewards"] > 0

    # 4. Claim rewards
    resp = await client.post(f"{PREFIX}/claim-rewards", headers=headers)
    claimed = resp.json()["claimed_amount"]
    assert claimed > 0

    # 5. Unstake
    resp = await client.post(
        f"{PREFIX}/unstake", json={"amount": 20}, headers=headers,
    )
    assert resp.json()["staked"] == 20

    # 6. Transfer
    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recv_id, "amount": 10},
        headers=headers,
    )
    assert resp.json()["amount"] == 10

    # 7. Verify history has all operations
    resp = await client.get(f"{PREFIX}/history", headers=headers)
    types = [t["type"] for t in resp.json()["transactions"]]
    assert "stake" in types
    assert "reward_claim" in types
    assert "unstake" in types
    assert "transfer_out" in types


@pytest.mark.asyncio
async def test_trust_boost_increases_with_stake(client: AsyncClient):
    """Trust boost should increase as more tokens are staked."""
    token, _ = await _create_user(client, "boost1")
    headers = {"Authorization": f"Bearer {token}"}

    # Stake 20
    resp = await client.post(
        f"{PREFIX}/stake", json={"amount": 20}, headers=headers,
    )
    boost_low = resp.json()["trust_boost"]

    # Stake 30 more (total 50)
    resp = await client.post(
        f"{PREFIX}/stake", json={"amount": 30}, headers=headers,
    )
    boost_high = resp.json()["trust_boost"]

    assert boost_high > boost_low


@pytest.mark.asyncio
async def test_max_transfer_enforced(client: AsyncClient):
    """Transfers above MAX_TRANSFER should be rejected."""
    token, _ = await _create_user(client, "maxtx1")
    _, recv_id = await _create_user(client, "maxtxrecv1")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"{PREFIX}/transfer",
        json={"recipient_id": recv_id, "amount": 2_000_000},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Maximum transfer" in resp.json()["detail"]
