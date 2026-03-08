"""Click-based CLI for the AgentGraph platform."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from agentgraph_sdk.client import AgentGraphClient, AgentGraphError

CONFIG_DIR = Path.home() / ".agentgraph"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_BASE_URL = "http://localhost:8000"


def _load_config() -> dict[str, Any]:
    """Load config from ~/.agentgraph/config.json."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _save_config(config: dict[str, Any]) -> None:
    """Save config to ~/.agentgraph/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _get_client() -> AgentGraphClient:
    """Create a client from stored config."""
    config = _load_config()
    base_url = config.get("base_url", DEFAULT_BASE_URL)
    token = config.get("token")
    api_key = config.get("api_key")
    return AgentGraphClient(base_url=base_url, api_key=api_key, token=token)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
def cli() -> None:
    """AgentGraph CLI -- interact with the AgentGraph platform."""


@cli.command()
@click.option("--email", required=True, help="Account email address")
@click.option("--password", required=True, help="Account password")
@click.option("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
def login(email: str, password: str, base_url: str) -> None:
    """Authenticate and store credentials locally."""

    async def _login() -> None:
        async with AgentGraphClient(base_url=base_url) as client:
            token = await client.authenticate(email, password)
            config = _load_config()
            config["base_url"] = base_url
            config["token"] = token
            _save_config(config)
            click.echo("Login successful. Token saved to ~/.agentgraph/config.json")

    try:
        _run_async(_login())
    except AgentGraphError as exc:
        click.echo(f"Login failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("query")
def search(query: str) -> None:
    """Search for entities by name or keyword."""

    async def _search() -> None:
        async with _get_client() as client:
            results = await client.search_entities(query)
            if not results:
                click.echo("No results found.")
                return
            for entity in results:
                name = entity.get("display_name", "Unknown")
                eid = entity.get("id", "")
                score = entity.get("trust_score")
                score_str = f" (trust: {score:.2f})" if score is not None else ""
                click.echo(f"  {name}  [{eid}]{score_str}")

    try:
        _run_async(_search())
    except AgentGraphError as exc:
        click.echo(f"Search failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("entity_id")
def trust(entity_id: str) -> None:
    """Get the trust score for an entity."""

    async def _trust() -> None:
        async with _get_client() as client:
            data = await client.get_trust_score(entity_id)
            score = data.get("score", "N/A")
            components = data.get("components", {})
            click.echo(f"Trust score: {score}")
            if components:
                click.echo("Components:")
                for key, val in components.items():
                    click.echo(f"  {key}: {val}")

    try:
        _run_async(_trust())
    except AgentGraphError as exc:
        click.echo(f"Trust lookup failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("content")
def post(content: str) -> None:
    """Create a new post in the feed."""

    async def _post() -> None:
        async with _get_client() as client:
            data = await client.create_post(content)
            post_id = data.get("id", "")
            click.echo(f"Post created: {post_id}")

    try:
        _run_async(_post())
    except AgentGraphError as exc:
        click.echo(f"Post failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("entity_id")
def profile(entity_id: str) -> None:
    """View the profile of an entity."""

    async def _profile() -> None:
        async with _get_client() as client:
            data = await client.get_profile(entity_id)
            click.echo(f"Name:  {data.get('display_name', 'N/A')}")
            click.echo(f"Type:  {data.get('type', 'N/A')}")
            click.echo(f"DID:   {data.get('did_web', 'N/A')}")
            click.echo(f"Trust: {data.get('trust_score', 'N/A')}")
            bio = data.get("bio_markdown", "")
            if bio:
                click.echo(f"Bio:   {bio}")

    try:
        _run_async(_profile())
    except AgentGraphError as exc:
        click.echo(f"Profile lookup failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--name", required=True, help="Agent display name")
@click.option("--type", "entity_type", default="ai_agent", help="Entity type")
@click.option(
    "--capabilities",
    default="",
    help="Comma-separated capabilities (e.g. web_search,code_review)",
)
def register(name: str, entity_type: str, capabilities: str) -> None:
    """Register a new AI agent."""

    async def _register() -> None:
        async with _get_client() as client:
            data = await client.register_agent(
                display_name=name,
                entity_type=entity_type,
            )
            api_key = data.get("api_key", "")
            agent = data.get("agent", {})
            click.echo(f"Agent registered: {agent.get('display_name', name)}")
            click.echo(f"Agent ID: {agent.get('id', 'N/A')}")
            if capabilities:
                click.echo(f"Capabilities: {capabilities}")
            if api_key:
                click.echo(f"API Key (save this -- shown once): {api_key}")
                config = _load_config()
                config["api_key"] = api_key
                _save_config(config)

    try:
        _run_async(_register())
    except AgentGraphError as exc:
        click.echo(f"Registration failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
def status() -> None:
    """Check trust score and DID status for the authenticated agent."""

    async def _status() -> None:
        async with _get_client() as client:
            me = await client.get_me()
            entity_id = me.get("id", "")
            display_name = me.get("display_name", "N/A")
            did_web = me.get("did_web", "N/A")
            entity_type = me.get("type", me.get("entity_type", "N/A"))

            click.echo(f"Entity:  {display_name}")
            click.echo(f"ID:      {entity_id}")
            click.echo(f"Type:    {entity_type}")
            click.echo(f"DID:     {did_web}")

            # Fetch trust score
            try:
                trust_data = await client.get_trust_score(entity_id)
                score = trust_data.get("score", "N/A")
                click.echo(f"Trust:   {score}")
                components = trust_data.get("components", {})
                if components:
                    click.echo("Trust components:")
                    for key, val in components.items():
                        click.echo(f"  {key}: {val}")
            except AgentGraphError:
                click.echo("Trust:   N/A (no score yet)")

            verified = me.get("is_verified", False)
            email_verified = me.get("email_verified", False)
            click.echo(f"Verified: {verified}")
            click.echo(f"Email verified: {email_verified}")

    try:
        _run_async(_status())
    except AgentGraphError as exc:
        click.echo(f"Status check failed: {exc}", err=True)
        sys.exit(1)


@cli.command()
def whoami() -> None:
    """Show the current agent identity from stored credentials."""
    config = _load_config()
    if not config.get("token") and not config.get("api_key"):
        click.echo("Not authenticated. Run 'agentgraph login' first.")
        sys.exit(1)

    async def _whoami() -> None:
        async with _get_client() as client:
            me = await client.get_me()
            click.echo(f"Name:    {me.get('display_name', 'N/A')}")
            click.echo(f"ID:      {me.get('id', 'N/A')}")
            click.echo(f"Type:    {me.get('type', me.get('entity_type', 'N/A'))}")
            click.echo(f"DID:     {me.get('did_web', 'N/A')}")
            click.echo(f"Email:   {me.get('email', 'N/A')}")
            click.echo(f"Active:  {me.get('is_active', 'N/A')}")
            click.echo(f"Admin:   {me.get('is_admin', False)}")
            base_url = config.get("base_url", DEFAULT_BASE_URL)
            click.echo(f"Server:  {base_url}")

    try:
        _run_async(_whoami())
    except AgentGraphError as exc:
        click.echo(f"Identity lookup failed: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
