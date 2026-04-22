"""Bluesky feed generator HTTP endpoints.

Serves the three required endpoints for a Bluesky feed generator:
1. /.well-known/did.json  — DID document for the feed service
2. /xrpc/app.bsky.feed.describeFeedGenerator — feed declaration
3. /xrpc/app.bsky.feed.getFeedSkeleton — the actual feed content
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bluesky-feed"])

# Feed configuration — set via env vars
FEED_GENERATOR_DID = f"did:web:{settings.domain}"  # e.g. did:web:agentgraph.co
FEED_PUBLISHER_DID = getattr(settings, "bluesky_did", "")  # The account DID
FEED_RKEY = "ai-agent-news"
FEED_URI = f"at://{FEED_PUBLISHER_DID}/app.bsky.feed.generator/{FEED_RKEY}"

# Redis key (matches subscriber.py)
FEED_KEY = "bluesky:feed:ai-agent-news"


@router.get("/.well-known/did.json")
async def did_document() -> JSONResponse:
    """Serve the DID document for did:web:<domain>.

    In addition to the Bluesky feed-generator service entry, this document
    publishes the Ed25519 verification key used to sign AgentGraph
    attestations (JWS, CTEF outer envelope) and the ``#gateway-reverify``
    service endpoint referenced as ``aud`` in CTEF envelopes.

    The verification key material is served byte-identical at
    ``/.well-known/jwks.json``; this document binds it into DID-Core form
    so ``did:web:<domain>#agentgraph-security-v1`` resolves for verifiers.
    """
    # Lazy import to avoid a circular dependency with src.signing at module load.
    from src.signing import get_jwk

    pub_jwk = get_jwk()  # {kty, crv, x, kid, use, alg}
    did = FEED_GENERATOR_DID  # did:web:<domain>
    signing_vm_id = f"{did}#{pub_jwk['kid']}"

    return JSONResponse(
        content={
            "@context": [
                "https://www.w3.org/ns/did/v1",
                "https://w3id.org/security/suites/jws-2020/v1",
            ],
            "id": did,
            "verificationMethod": [
                {
                    "id": signing_vm_id,
                    "type": "JsonWebKey2020",
                    "controller": did,
                    "publicKeyJwk": pub_jwk,
                }
            ],
            "assertionMethod": [signing_vm_id],
            "authentication": [signing_vm_id],
            "service": [
                {
                    "id": f"{did}#bsky_fg",
                    "type": "BskyFeedGenerator",
                    "serviceEndpoint": f"https://{settings.domain}",
                },
                {
                    "id": f"{did}#gateway-reverify",
                    "type": "TrustGatewayReverify",
                    "serviceEndpoint": (
                        f"https://{settings.domain}/api/v1/gateway/re-verify"
                    ),
                },
                {
                    "id": f"{did}#jwks",
                    "type": "JsonWebKeySet",
                    "serviceEndpoint": (
                        f"https://{settings.domain}/.well-known/jwks.json"
                    ),
                },
            ],
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/xrpc/app.bsky.feed.describeFeedGenerator")
async def describe_feed_generator() -> JSONResponse:
    """Declare which feeds this service hosts."""
    return JSONResponse(
        content={
            "did": FEED_GENERATOR_DID,
            "feeds": [{"uri": FEED_URI}],
        },
    )


@router.get("/xrpc/app.bsky.feed.getFeedSkeleton")
async def get_feed_skeleton(
    feed: str = Query(..., description="AT-URI of the requested feed"),
    cursor: str | None = Query(None, description="Pagination cursor"),
    limit: int = Query(30, ge=1, le=100, description="Number of posts"),
) -> JSONResponse:
    """Return the feed skeleton — a list of post AT-URIs sorted by recency.

    Bluesky's AppView hydrates these URIs into full posts.
    """
    # Validate feed URI
    if feed != FEED_URI:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown feed: {feed}",
        )

    from src.redis_client import get_redis

    r = get_redis()

    # Parse cursor (format: timestamp_us as string)
    max_score = "+inf"
    if cursor and cursor != "eof":
        try:
            max_score = f"({cursor}"  # exclusive — don't re-include the cursor item
        except (ValueError, TypeError):
            raise HTTPException(400, "Invalid cursor")

    # Fetch posts from Redis sorted set (newest first)
    results = await r.zrevrangebyscore(
        FEED_KEY,
        max_score,
        "-inf",
        start=0,
        num=limit + 1,  # fetch one extra to know if there's more
        withscores=True,
    )

    feed_items = []
    next_cursor = None

    for i, (uri_bytes, score) in enumerate(results):
        if i >= limit:
            # There are more results — set cursor
            next_cursor = str(int(score))
            break
        uri = uri_bytes.decode() if isinstance(uri_bytes, bytes) else uri_bytes
        feed_items.append({"post": uri})

    response: dict = {"feed": feed_items}
    if next_cursor:
        response["cursor"] = next_cursor

    return JSONResponse(
        content=response,
        headers={"Cache-Control": "public, max-age=30"},
    )
