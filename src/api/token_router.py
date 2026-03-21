"""Token economics endpoints for the AgentGraph platform.

Provides token balance, transfer, staking, rewards, and leaderboard
functionality. Token data is stored in each entity's ``onboarding_data``
JSONB column to avoid new DB tables.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_entity
from src.api.rate_limit import rate_limit_reads, rate_limit_writes
from src.database import get_db
from src.models import Entity, TrustScore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tokens", tags=["tokens"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_NAME = "AGNT"
TOKEN_SYMBOL = "AGNT"
TOTAL_SUPPLY = 1_000_000_000  # 1 billion
INITIAL_BALANCE = 100  # new entities start with 100 AGNT
MIN_TRANSFER = 1
MAX_TRANSFER = 1_000_000
MIN_STAKE = 10
TRUST_BOOST_PER_STAKED = 0.001  # +0.1% trust per 1000 staked
REWARD_RATE_PER_STAKED = 0.0001  # 0.01% per staked token per claim cycle

DISTRIBUTION = {
    "community_rewards": 0.40,
    "ecosystem_fund": 0.25,
    "team_and_advisors": 0.15,
    "trust_mining": 0.10,
    "liquidity": 0.10,
}


# ---------------------------------------------------------------------------
# Response / Request schemas
# ---------------------------------------------------------------------------


class TokenInfoResponse(BaseModel):
    name: str
    symbol: str
    total_supply: int
    distribution: dict[str, float]


class BalanceResponse(BaseModel):
    entity_id: str
    balance: float
    staked: float
    available: float
    trust_boost: float


class TransferRequest(BaseModel):
    recipient_id: str
    amount: float = Field(..., gt=0)
    memo: str | None = Field(None, max_length=200)


class TransferResponse(BaseModel):
    transaction_id: str
    sender_id: str
    recipient_id: str
    amount: float
    memo: str | None
    sender_balance: float
    timestamp: str


class StakeRequest(BaseModel):
    amount: float = Field(..., gt=0)


class StakeResponse(BaseModel):
    entity_id: str
    staked: float
    available: float
    trust_boost: float
    timestamp: str


class UnstakeRequest(BaseModel):
    amount: float = Field(..., gt=0)


class UnstakeResponse(BaseModel):
    entity_id: str
    staked: float
    available: float
    trust_boost: float
    timestamp: str


class RewardsResponse(BaseModel):
    entity_id: str
    pending_rewards: float
    staked: float
    last_claimed_at: str | None


class ClaimRewardsResponse(BaseModel):
    entity_id: str
    claimed_amount: float
    new_balance: float
    claimed_at: str


class TransactionRecord(BaseModel):
    transaction_id: str
    type: str
    amount: float
    counterparty_id: str | None = None
    memo: str | None = None
    timestamp: str


class HistoryResponse(BaseModel):
    entity_id: str
    transactions: list[TransactionRecord]
    total: int


class LeaderboardEntry(BaseModel):
    rank: int
    entity_id: str
    display_name: str
    balance: float
    staked: float
    trust_score: float | None


class LeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    total_entities: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_token_data(entity: Entity) -> dict:
    """Extract token data from onboarding_data, initialising defaults."""
    raw = dict(entity.onboarding_data or {})
    td = raw.get("token_data", {})
    return {
        "balance": td.get("balance", INITIAL_BALANCE),
        "staked": td.get("staked", 0.0),
        "transactions": td.get("transactions", []),
        "last_claimed_at": td.get("last_claimed_at"),
    }


def _save_token_data(entity: Entity, token_data: dict) -> None:
    """Persist token data back into onboarding_data (triggers SA change)."""
    data = dict(entity.onboarding_data or {})
    data["token_data"] = token_data
    entity.onboarding_data = data


def _compute_trust_boost(staked: float) -> float:
    return round(staked * TRUST_BOOST_PER_STAKED, 6)


def _compute_pending_rewards(staked: float, last_claimed_at: str | None) -> float:
    """Pending rewards = staked * REWARD_RATE_PER_STAKED per hour since last claim."""
    if staked <= 0:
        return 0.0
    if last_claimed_at is None:
        # First-time: give one full cycle reward
        return round(staked * REWARD_RATE_PER_STAKED, 6)
    claimed_dt = datetime.fromisoformat(last_claimed_at)
    now = datetime.now(timezone.utc)
    hours = max((now - claimed_dt).total_seconds() / 3600.0, 0)
    return round(staked * REWARD_RATE_PER_STAKED * hours, 6)


def _add_transaction(
    token_data: dict,
    *,
    tx_type: str,
    amount: float,
    counterparty_id: str | None = None,
    memo: str | None = None,
) -> str:
    """Append a transaction record and return its id."""
    tx_id = uuid.uuid4().hex
    token_data.setdefault("transactions", []).append({
        "transaction_id": tx_id,
        "type": tx_type,
        "amount": amount,
        "counterparty_id": counterparty_id,
        "memo": memo,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Keep only the last 500 transactions to bound JSONB size
    token_data["transactions"] = token_data["transactions"][-500:]
    return tx_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/info", response_model=TokenInfoResponse)
async def get_token_info(
    _rate: None = Depends(rate_limit_reads),
):
    """Public endpoint returning token supply and distribution info."""
    return TokenInfoResponse(
        name=TOKEN_NAME,
        symbol=TOKEN_SYMBOL,
        total_supply=TOTAL_SUPPLY,
        distribution=DISTRIBUTION,
    )


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    current_entity: Entity = Depends(get_current_entity),
    _rate: None = Depends(rate_limit_reads),
):
    """Get the authenticated entity's token balance."""
    td = _get_token_data(current_entity)
    staked = td["staked"]
    balance = td["balance"]
    return BalanceResponse(
        entity_id=str(current_entity.id),
        balance=balance,
        staked=staked,
        available=round(balance - staked, 6),
        trust_boost=_compute_trust_boost(staked),
    )


@router.post("/transfer", response_model=TransferResponse)
async def transfer_tokens(
    body: TransferRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_writes),
):
    """Transfer tokens from the authenticated entity to another entity."""
    if body.amount < MIN_TRANSFER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum transfer amount is {MIN_TRANSFER}.",
        )
    if body.amount > MAX_TRANSFER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum transfer amount is {MAX_TRANSFER}.",
        )

    # Validate recipient
    try:
        recipient_uuid = uuid.UUID(body.recipient_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid recipient_id format.",
        )

    if recipient_uuid == current_entity.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer tokens to yourself.",
        )

    recipient = await db.scalar(
        select(Entity).where(
            Entity.id == recipient_uuid,
            Entity.is_active.is_(True),
        )
    )
    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found or inactive.",
        )

    # Sender balance check
    sender_td = _get_token_data(current_entity)
    available = sender_td["balance"] - sender_td["staked"]
    if body.amount > available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient available balance. Available: {available}",
        )

    # Deduct from sender
    sender_td["balance"] = round(sender_td["balance"] - body.amount, 6)
    tx_id = _add_transaction(
        sender_td,
        tx_type="transfer_out",
        amount=body.amount,
        counterparty_id=str(recipient.id),
        memo=body.memo,
    )
    _save_token_data(current_entity, sender_td)

    # Credit recipient
    recipient_td = _get_token_data(recipient)
    recipient_td["balance"] = round(recipient_td["balance"] + body.amount, 6)
    _add_transaction(
        recipient_td,
        tx_type="transfer_in",
        amount=body.amount,
        counterparty_id=str(current_entity.id),
        memo=body.memo,
    )
    _save_token_data(recipient, recipient_td)

    await db.flush()
    await db.refresh(current_entity)
    await db.refresh(recipient)

    now_iso = datetime.now(timezone.utc).isoformat()
    return TransferResponse(
        transaction_id=tx_id,
        sender_id=str(current_entity.id),
        recipient_id=str(recipient.id),
        amount=body.amount,
        memo=body.memo,
        sender_balance=sender_td["balance"],
        timestamp=now_iso,
    )


@router.post("/stake", response_model=StakeResponse)
async def stake_tokens(
    body: StakeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_writes),
):
    """Stake tokens to boost trust score. Staked tokens are locked."""
    if body.amount < MIN_STAKE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum stake amount is {MIN_STAKE}.",
        )

    td = _get_token_data(current_entity)
    available = td["balance"] - td["staked"]
    if body.amount > available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient available balance. Available: {available}",
        )

    td["staked"] = round(td["staked"] + body.amount, 6)
    _add_transaction(td, tx_type="stake", amount=body.amount)
    _save_token_data(current_entity, td)

    await db.flush()
    await db.refresh(current_entity)

    now_iso = datetime.now(timezone.utc).isoformat()
    new_staked = td["staked"]
    return StakeResponse(
        entity_id=str(current_entity.id),
        staked=new_staked,
        available=round(td["balance"] - new_staked, 6),
        trust_boost=_compute_trust_boost(new_staked),
        timestamp=now_iso,
    )


@router.post("/unstake", response_model=UnstakeResponse)
async def unstake_tokens(
    body: StakeRequest,
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_writes),
):
    """Unstake (unlock) previously staked tokens."""
    td = _get_token_data(current_entity)
    if body.amount > td["staked"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot unstake more than current stake ({td['staked']}).",
        )

    td["staked"] = round(td["staked"] - body.amount, 6)
    _add_transaction(td, tx_type="unstake", amount=body.amount)
    _save_token_data(current_entity, td)

    await db.flush()
    await db.refresh(current_entity)

    now_iso = datetime.now(timezone.utc).isoformat()
    new_staked = td["staked"]
    return UnstakeResponse(
        entity_id=str(current_entity.id),
        staked=new_staked,
        available=round(td["balance"] - new_staked, 6),
        trust_boost=_compute_trust_boost(new_staked),
        timestamp=now_iso,
    )


@router.get("/rewards", response_model=RewardsResponse)
async def get_rewards(
    current_entity: Entity = Depends(get_current_entity),
    _rate: None = Depends(rate_limit_reads),
):
    """Check pending staking rewards for the authenticated entity."""
    td = _get_token_data(current_entity)
    pending = _compute_pending_rewards(td["staked"], td["last_claimed_at"])
    return RewardsResponse(
        entity_id=str(current_entity.id),
        pending_rewards=pending,
        staked=td["staked"],
        last_claimed_at=td["last_claimed_at"],
    )


@router.post("/claim-rewards", response_model=ClaimRewardsResponse)
async def claim_rewards(
    current_entity: Entity = Depends(get_current_entity),
    db: AsyncSession = Depends(get_db),
    _rate: None = Depends(rate_limit_writes),
):
    """Claim earned staking rewards and add them to balance."""
    td = _get_token_data(current_entity)
    pending = _compute_pending_rewards(td["staked"], td["last_claimed_at"])

    if pending <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending rewards to claim.",
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    td["balance"] = round(td["balance"] + pending, 6)
    td["last_claimed_at"] = now_iso
    _add_transaction(td, tx_type="reward_claim", amount=pending)
    _save_token_data(current_entity, td)

    await db.flush()
    await db.refresh(current_entity)

    return ClaimRewardsResponse(
        entity_id=str(current_entity.id),
        claimed_amount=pending,
        new_balance=td["balance"],
        claimed_at=now_iso,
    )


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    current_entity: Entity = Depends(get_current_entity),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _rate: None = Depends(rate_limit_reads),
):
    """Get token transaction history for the authenticated entity."""
    td = _get_token_data(current_entity)
    all_txs = td.get("transactions", [])
    # Return newest first
    all_txs_sorted = list(reversed(all_txs))
    page = all_txs_sorted[offset:offset + limit]

    records = [
        TransactionRecord(
            transaction_id=tx["transaction_id"],
            type=tx["type"],
            amount=tx["amount"],
            counterparty_id=tx.get("counterparty_id"),
            memo=tx.get("memo"),
            timestamp=tx["timestamp"],
        )
        for tx in page
    ]
    return HistoryResponse(
        entity_id=str(current_entity.id),
        transactions=records,
        total=len(all_txs),
    )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    _rate: None = Depends(rate_limit_reads),
):
    """Get the top token holders, ranked by total balance."""
    # Fetch all active entities — filter/sort in Python because
    # JSONB extraction ordering is not trivially indexed.
    _not_moltbook = or_(Entity.source_type.is_(None), Entity.source_type != "moltbook")
    result = await db.execute(
        select(Entity).where(Entity.is_active.is_(True), _not_moltbook)
    )
    entities = result.scalars().all()

    scored: list[dict] = []
    for ent in entities:
        td = _get_token_data(ent)
        bal = td["balance"]
        staked = td["staked"]
        # Include entities that have a non-default balance or any stake
        scored.append({
            "entity": ent,
            "balance": bal,
            "staked": staked,
        })

    # Sort by total balance descending
    scored.sort(key=lambda x: x["balance"], reverse=True)
    top = scored[:limit]

    # Fetch trust scores for the top entries
    entity_ids = [s["entity"].id for s in top]
    ts_result = await db.execute(
        select(TrustScore).where(TrustScore.entity_id.in_(entity_ids))
    ) if entity_ids else None
    trust_map: dict = {}
    if ts_result is not None:
        for ts in ts_result.scalars().all():
            trust_map[ts.entity_id] = ts.score

    entries = [
        LeaderboardEntry(
            rank=idx + 1,
            entity_id=str(s["entity"].id),
            display_name=s["entity"].display_name,
            balance=s["balance"],
            staked=s["staked"],
            trust_score=trust_map.get(s["entity"].id),
        )
        for idx, s in enumerate(top)
    ]
    return LeaderboardResponse(
        entries=entries,
        total_entities=len(scored),
    )
