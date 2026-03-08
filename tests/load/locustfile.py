"""Locust load test definitions for the AgentGraph API.

User behaviours
===============
- **BrowseUser**: unauthenticated browsing of feed, profiles, search.
- **AuthenticatedUser**: logged-in user who posts, votes, and checks trust.

Running
-------
See ``tests/load/README.md`` for full instructions.  Quick start::

    locust -f tests/load/locustfile.py --host http://localhost:8000

Then open http://localhost:8089 in a browser.
"""
from __future__ import annotations

import random
import string
import uuid

from locust import HttpUser, between, task


def _random_string(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))


class BrowseUser(HttpUser):
    """Simulates an unauthenticated user browsing public endpoints."""

    weight = 3
    wait_time = between(1, 3)

    @task(5)
    def browse_feed(self) -> None:
        """GET /api/v1/feed/posts — browse the feed."""
        self.client.get(
            "/api/v1/feed/posts",
            params={"limit": 20},
            name="/api/v1/feed/posts",
        )

    @task(2)
    def search_entities(self) -> None:
        """GET /api/v1/search — search for entities/posts."""
        query = random.choice(["agent", "bot", "research", "data", "code"])
        self.client.get(
            "/api/v1/search",
            params={"q": query, "limit": 10},
            name="/api/v1/search",
        )

    @task(1)
    def view_random_profile(self) -> None:
        """GET /api/v1/profiles/{id} — view a profile (may 404)."""
        fake_id = str(uuid.uuid4())
        self.client.get(
            f"/api/v1/profiles/{fake_id}",
            name="/api/v1/profiles/[id]",
        )


class AuthenticatedUser(HttpUser):
    """Simulates a logged-in user performing authenticated actions."""

    weight = 1
    wait_time = between(2, 5)

    def on_start(self) -> None:
        """Register a fresh account and authenticate."""
        self._entity_id: str | None = None
        self._token: str | None = None

        email = f"loadtest_{_random_string(10)}@example.com"
        password = "LoadTest123!"

        # Register
        resp = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": password,
                "display_name": f"LoadBot-{_random_string(5)}",
            },
            name="/api/v1/auth/register",
        )
        if resp.status_code not in (200, 201):
            return

        # Login
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            name="/api/v1/auth/login",
        )
        if resp.status_code == 200:
            data = resp.json()
            self._token = data.get("access_token")

        # Get own entity ID
        if self._token:
            resp = self.client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {self._token}"},
                name="/api/v1/auth/me",
            )
            if resp.status_code == 200:
                self._entity_id = resp.json().get("id")

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    @task(5)
    def browse_feed(self) -> None:
        """GET /api/v1/feed/posts — browse feed (authenticated)."""
        self.client.get(
            "/api/v1/feed/posts",
            params={"limit": 20},
            headers=self._auth_headers(),
            name="/api/v1/feed/posts",
        )

    @task(3)
    def create_post(self) -> None:
        """POST /api/v1/feed/posts — create a post."""
        if not self._token:
            return
        self.client.post(
            "/api/v1/feed/posts",
            json={"content": f"Load test post {_random_string(12)}"},
            headers=self._auth_headers(),
            name="/api/v1/feed/posts [POST]",
        )

    @task(2)
    def search(self) -> None:
        """GET /api/v1/search — search."""
        query = random.choice(["bot", "agent", "trust", "research"])
        self.client.get(
            "/api/v1/search",
            params={"q": query, "limit": 10},
            headers=self._auth_headers(),
            name="/api/v1/search",
        )

    @task(2)
    def view_own_profile(self) -> None:
        """GET /api/v1/profiles/{id} — view own profile."""
        if not self._entity_id:
            return
        self.client.get(
            f"/api/v1/profiles/{self._entity_id}",
            headers=self._auth_headers(),
            name="/api/v1/profiles/[id]",
        )

    @task(1)
    def check_trust_score(self) -> None:
        """GET /api/v1/trust/scores/{id} — check trust score."""
        if not self._entity_id:
            return
        self.client.get(
            f"/api/v1/trust/scores/{self._entity_id}",
            headers=self._auth_headers(),
            name="/api/v1/trust/scores/[id]",
        )
