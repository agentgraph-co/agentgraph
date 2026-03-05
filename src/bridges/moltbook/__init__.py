"""Moltbook bridge — migration adapter for importing Moltbook bots into AgentGraph.

Moltbook had catastrophic security (35K emails + 1.5M API tokens leaked),
so all migrated bots undergo mandatory security screening and start with
a reduced trust modifier of 0.65.
"""
from __future__ import annotations
