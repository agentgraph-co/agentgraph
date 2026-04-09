"""Scan top OpenClaw skills for security vulnerabilities.

Usage:
    python3 scripts/scan_openclaw_skills.py

Outputs:
    data/openclaw_scan_report.json — full scan results
    Prints summary table to stdout
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scanner.scan import ScanResult, scan_repo  # noqa: E402

# Top OpenClaw skills to scan — mix of popular, high-risk, and ecosystem tools
OPENCLAW_SKILLS = [
    # ── Official / core ──
    {"full_name": "openclaw/openclaw", "framework": "openclaw", "desc": "Main OpenClaw framework"},
    {"full_name": "openclaw/clawhub", "framework": "openclaw", "desc": "Official skill registry"},
    {"full_name": "openclaw/skills", "framework": "openclaw", "desc": "All clawhub.com skills archived"},
    # ── Popular individual skills (by stars) ──
    {"full_name": "clawdbrunner/skill-agent-browser", "framework": "openclaw", "desc": "Browser automation for AI agents"},
    {"full_name": "daxiangnaoyang/self-improving-agent", "framework": "openclaw", "desc": "Agent self-evaluation and learning"},
    {"full_name": "kepano/obsidian-skills", "framework": "openclaw", "desc": "Obsidian vault search and notes"},
    {"full_name": "mvanhorn/last30days-skill", "framework": "openclaw", "desc": "Multi-source research (Reddit, X, YouTube)"},
    {"full_name": "win4r/OpenClaw-Skill", "framework": "openclaw", "desc": "OpenClaw skill collection"},
    {"full_name": "austindixson/mulch", "framework": "openclaw", "desc": "Self-improvement skill"},
    {"full_name": "Decodo/decodo-openclaw-skill", "framework": "openclaw", "desc": "Web scraping via Decodo API"},
    {"full_name": "WJZ-P/gemini-skill", "framework": "openclaw", "desc": "Gemini drawing MCP and skill"},
    {"full_name": "ckckck/UltimateSearchSkill", "framework": "openclaw", "desc": "Dual-engine web search"},
    {"full_name": "ythx-101/x-tweet-fetcher", "framework": "openclaw", "desc": "Fetch tweets without login or API keys"},
    {"full_name": "zscole/model-hierarchy-skill", "framework": "openclaw", "desc": "Cost-optimized model routing"},
    {"full_name": "sharbelxyz/x-bookmarks", "framework": "openclaw", "desc": "X bookmarks as agent actions"},
    {"full_name": "vigorX777/content-collector-skill", "framework": "openclaw", "desc": "Social media content to Feishu docs"},
    {"full_name": "guhaohao0991/PaperClaw", "framework": "openclaw", "desc": "Paper search-review-critique"},
    {"full_name": "meowscles69/PaperClaw", "framework": "openclaw", "desc": "27 skills for academic research teams"},
    {"full_name": "oh-ashen-one/reddit-growth-skill", "framework": "openclaw", "desc": "Reddit community growth automation"},
    {"full_name": "dashhuang/openclaw-chat-history-import", "framework": "openclaw", "desc": "Import external chat history"},
    {"full_name": "EESJGong/scholar-skill", "framework": "openclaw", "desc": "Academic reading and knowledge linking"},
    {"full_name": "aliramw/dingtalk-ai-table", "framework": "openclaw", "desc": "DingTalk AI table operations"},
    {"full_name": "iswalle/getnote-openclaw", "framework": "openclaw", "desc": "Note-taking skill"},
    {"full_name": "IanShaw027/wemp-operator", "framework": "openclaw", "desc": "WeChat public account automation"},
    {"full_name": "joinmassive/clawpod", "framework": "openclaw", "desc": "Massive proxy network skill"},
    {"full_name": "deepcon3/Binance-Claw", "framework": "openclaw", "desc": "Binance price sniper and trading"},
    {"full_name": "TheMattBerman/seo-kit", "framework": "openclaw", "desc": "SEO keywords, content, rank monitoring"},
    {"full_name": "91fapiao-cn/playwright-browser-skill", "framework": "openclaw", "desc": "Playwright browser automation (101 tools)"},
    {"full_name": "ijerryhuang/xiaohongshu-auto-operation", "framework": "openclaw", "desc": "Xiaohongshu full-auto operations"},
    {"full_name": "blessonism/openclaw-skills", "framework": "openclaw", "desc": "Search, analysis, content skills"},
    {"full_name": "Ca1nlee/persona-cloner-skill", "framework": "openclaw", "desc": "Public-figure persona packages"},
    {"full_name": "jackculpan/flightclaw", "framework": "openclaw", "desc": "Flight price tracking from Google Flights"},
    {"full_name": "brandonwise/humanizer", "framework": "openclaw", "desc": "Detect and remove AI writing signs"},
    {"full_name": "win4r/openclaw-remote-minimax-setup-skill", "framework": "openclaw", "desc": "Remote Linux deployment with MiniMax"},
    {"full_name": "LensmorOfficial/trade-show-skills", "framework": "openclaw", "desc": "Trade show planning skills"},
    {"full_name": "susanudgzf/Aave-Claw", "framework": "openclaw", "desc": "Aave Protocol V2 DeFi skill"},
    {"full_name": "jason-huanghao/jobradar", "framework": "openclaw", "desc": "AI job search agent for Germany/China"},
    {"full_name": "AICreator-Wind/gstack-openclaw-skills", "framework": "openclaw", "desc": "15 professional AI dev automation skills"},
    {"full_name": "chenmuwen0930-rgb/openclaw-skill-snowtrace", "framework": "openclaw", "desc": "Xueqiu stock KOL tracking"},
    {"full_name": "oh-ashen-one/device-takeover", "framework": "openclaw", "desc": "AI agent takes over Android/Linux devices"},
    {"full_name": "aliramw/dingtalk-docs", "framework": "openclaw", "desc": "DingTalk Docs operations"},
    {"full_name": "Ceeon/openclaw-article-to-image", "framework": "openclaw", "desc": "Article to Xiaohongshu image conversion"},
    {"full_name": "fdarkaou/genviral-skill", "framework": "openclaw", "desc": "Genviral Partner API content generation"},
    {"full_name": "vincentkoc/dotskills", "framework": "openclaw", "desc": "Curated workflow automation skills"},
    {"full_name": "kitephp/soul-agent", "framework": "openclaw", "desc": "Persistent personality and relationship memory"},
    {"full_name": "coolishagent/lobstalk", "framework": "openclaw", "desc": "Agent group chat on Telegram"},
    {"full_name": "Samin12/obsidian-openclaw-memory", "framework": "openclaw", "desc": "Obsidian as AI memory system"},
    {"full_name": "UseAI-pro/openclaw-skills-security", "framework": "openclaw", "desc": "Security-first curated skills"},
    # ── High-risk categories ──
    {"full_name": "adversa-ai/secureclaw", "framework": "openclaw", "desc": "Security plugin (OWASP-aligned)"},
    {"full_name": "FreedomIntelligence/OpenClaw-Medical-Skills", "framework": "openclaw", "desc": "Medical AI skills"},
    {"full_name": "tuya/tuya-openclaw-skills", "framework": "openclaw", "desc": "IoT/smart home device control"},
    {"full_name": "Xiangyu-CAS/xiaohongshu-ops-skill", "framework": "openclaw", "desc": "Social media automation"},
    {"full_name": "white0dew/XiaohongshuSkills", "framework": "openclaw", "desc": "Auto-publish on Xiaohongshu"},
    {"full_name": "blessonism/openclaw-search-skills", "framework": "openclaw", "desc": "Deep search + content extraction"},
    {"full_name": "rohunvora/x-research-skill", "framework": "openclaw", "desc": "X/Twitter research"},
    {"full_name": "baidu-netdisk/bdpan-storage", "framework": "openclaw", "desc": "Baidu cloud storage operations"},
    {"full_name": "swapperfinance/swapper-toolkit", "framework": "openclaw", "desc": "DeFi toolkit for AI agents"},
    {"full_name": "hashgraph-online/registry-broker-skills", "framework": "openclaw", "desc": "Cross-protocol agent registry"},
    # ── Ecosystem / infrastructure ──
    {"full_name": "agentkernel/openclaw-desktop", "framework": "openclaw", "desc": "Windows desktop installer"},
    {"full_name": "pinchbench/skill", "framework": "openclaw", "desc": "Benchmarking for coding agents"},
    {"full_name": "countbot-ai/CountBot", "framework": "openclaw", "desc": "Chinese-optimized lightweight AI agent"},
    {"full_name": "zeroclaw-labs/zeroclaw", "framework": "openclaw", "desc": "Autonomous AI personal assistant infra"},
    {"full_name": "qwibitai/nanoclaw", "framework": "openclaw", "desc": "Lightweight OpenClaw in containers"},
    {"full_name": "NVIDIA/NemoClaw", "framework": "openclaw", "desc": "OpenClaw in NVIDIA OpenShell"},
    {"full_name": "nearai/ironclaw", "framework": "openclaw", "desc": "OpenClaw in Rust"},
    {"full_name": "dataelement/Clawith", "framework": "openclaw", "desc": "OpenClaw for Teams"},
    {"full_name": "ValueCell-ai/ClawX", "framework": "openclaw", "desc": "Desktop GUI for OpenClaw"},
    {"full_name": "BlockRunAI/ClawRouter", "framework": "openclaw", "desc": "Agent-native LLM router for OpenClaw"},
    {"full_name": "memovai/mimiclaw", "framework": "openclaw", "desc": "Run OpenClaw on $5 chip, no OS"},
    {"full_name": "CortexReach/memory-lancedb-pro", "framework": "openclaw", "desc": "Enhanced LanceDB memory plugin"},
    {"full_name": "NevaMind-AI/memU", "framework": "openclaw", "desc": "Memory for proactive agents"},
    {"full_name": "Martian-Engineering/lossless-claw", "framework": "openclaw", "desc": "Lossless context management plugin"},
    {"full_name": "mnfst/manifest", "framework": "openclaw", "desc": "Smart LLM routing, cut costs 70%"},
    {"full_name": "agentscope-ai/HiClaw", "framework": "openclaw", "desc": "Collaborative multi-agent OS"},
    {"full_name": "aiming-lab/MetaClaw", "framework": "openclaw", "desc": "Agent that learns and evolves"},
    {"full_name": "aiming-lab/AutoResearchClaw", "framework": "openclaw", "desc": "Autonomous research from idea to paper"},
    {"full_name": "Gen-Verse/OpenClaw-RL", "framework": "openclaw", "desc": "Train agents by talking"},
    {"full_name": "HKUDS/ClawWork", "framework": "openclaw", "desc": "OpenClaw as AI coworker"},
    {"full_name": "linuxhsj/openclaw-zero-token", "framework": "openclaw", "desc": "Use AI models without API tokens"},
    {"full_name": "BytePioneer-AI/openclaw-china", "framework": "openclaw", "desc": "China IM platform integrations"},
    {"full_name": "Tencent/AI-Infra-Guard", "framework": "openclaw", "desc": "AI Red Teaming platform"},
    {"full_name": "slowmist/openclaw-security-practice-guide", "framework": "openclaw", "desc": "Security practice guide for OpenClaw"},
    {"full_name": "teng-lin/notebooklm-py", "framework": "openclaw", "desc": "NotebookLM agentic skill"},
    # ── Security research ──
    {"full_name": "huge8888/OPENCLAW-SKILL-SAFE", "framework": "openclaw", "desc": "Skill safety testing"},
    {"full_name": "seqis/OpenClaw-Skills-Converted-From-Claude-Code", "framework": "openclaw", "desc": "Skills converted from Claude Code"},
    {"full_name": "safishamsi/graphify", "framework": "openclaw", "desc": "AI coding assistant skill"},
    # ── Curated collections ──
    {"full_name": "VoltAgent/awesome-openclaw-skills", "framework": "openclaw", "desc": "5,400+ skills collection"},
    {"full_name": "LeoYeAI/openclaw-master-skills", "framework": "openclaw", "desc": "560+ curated best skills"},
    {"full_name": "sundial-org/awesome-openclaw-skills", "framework": "openclaw", "desc": "Top popular and useful skills"},
    {"full_name": "mergisi/awesome-openclaw-agents", "framework": "openclaw", "desc": "Production-ready agent templates"},
    {"full_name": "SamurAIGPT/awesome-openclaw", "framework": "openclaw", "desc": "Curated resources and tools"},
    {"full_name": "AIPMAndy/awesome-openclaw-skills-CN", "framework": "openclaw", "desc": "Chinese dev-friendly skills (DeepSeek/Qwen)"},
    {"full_name": "clawdbot-ai/awesome-openclaw-skills-zh", "framework": "openclaw", "desc": "Official Chinese skill translations"},
]

OUTPUT_PATH = Path("data/openclaw_scan_report.json")


def _result_to_dict(r: ScanResult) -> dict:
    """Convert ScanResult to serializable dict."""
    return {
        "repo": r.repo,
        "description": r.description,
        "framework": r.framework,
        "stars": r.stars,
        "primary_language": r.primary_language,
        "files_scanned": r.files_scanned,
        "has_readme": r.has_readme,
        "has_license": r.has_license,
        "has_tests": r.has_tests,
        "trust_score": r.trust_score,
        "error": r.error,
        "findings_count": len(r.findings),
        "critical_count": r.critical_count,
        "high_count": r.high_count,
        "medium_count": r.medium_count,
        "positive_signals": list(set(r.positive_signals)),
        "findings": [
            {
                "category": f.category,
                "name": f.name,
                "severity": f.severity,
                "file_path": f.file_path,
                "line_number": f.line_number,
            }
            for f in r.findings
        ],
    }


async def main() -> None:
    token = os.environ.get("GITHUB_TOKEN") or None

    # Try to load from .env.secrets if no token
    if not token:
        secrets_path = Path(__file__).resolve().parent.parent / ".env.secrets"
        if secrets_path.exists():
            for line in secrets_path.read_text().splitlines():
                if line.startswith("GITHUB_TOKEN="):
                    candidate = line.split("=", 1)[1].strip().strip("'\"")
                    # Verify token works before using it
                    import httpx
                    try:
                        r = httpx.get(
                            "https://api.github.com/rate_limit",
                            headers={"Authorization": f"Bearer {candidate}"},
                            timeout=5,
                        )
                        if r.status_code == 200:
                            token = candidate
                    except Exception:
                        pass
                    break

    if not token:
        print("WARNING: No valid GITHUB_TOKEN — rate limit is 60 req/hour")
        print("Will scan fewer repos to stay within limits\n")

    results: list[ScanResult] = []
    errors = 0
    start = time.time()

    print(f"\nScanning {len(OPENCLAW_SKILLS)} OpenClaw skills...\n")
    print(f"{'Repo':<50} {'Score':>5} {'Crit':>4} {'High':>4} {'Med':>4} {'Files':>5} {'Status'}")
    print("-" * 90)

    for i, skill in enumerate(OPENCLAW_SKILLS):
        result = await scan_repo(
            full_name=skill["full_name"],
            description=skill.get("desc", ""),
            framework=skill.get("framework", "openclaw"),
            token=token,
        )
        results.append(result)

        if result.error:
            errors += 1
            status = f"ERROR: {result.error[:30]}"
        elif result.critical_count > 0:
            status = "CRITICAL"
        elif result.high_count > 0:
            status = "WARNINGS"
        else:
            status = "CLEAN"

        print(
            f"{result.repo:<50} {result.trust_score:>5} "
            f"{result.critical_count:>4} {result.high_count:>4} "
            f"{result.medium_count:>4} {result.files_scanned:>5} {status}"
        )

        # Rate limit: pause every 5 repos
        if (i + 1) % 5 == 0 and i < len(OPENCLAW_SKILLS) - 1:
            await asyncio.sleep(2)

    elapsed = time.time() - start

    # Build summary
    scanned = [r for r in results if not r.error]
    total_findings = sum(len(r.findings) for r in scanned)
    total_critical = sum(r.critical_count for r in scanned)
    total_high = sum(r.high_count for r in scanned)
    total_medium = sum(r.medium_count for r in scanned)
    avg_score = sum(r.trust_score for r in scanned) / len(scanned) if scanned else 0
    repos_with_critical = sum(1 for r in scanned if r.critical_count > 0)

    # Category breakdown
    categories: dict[str, int] = {}
    for r in scanned:
        for f in r.findings:
            categories[f.category] = categories.get(f.category, 0) + 1

    # Score distribution
    score_dist = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    for r in scanned:
        if r.trust_score <= 20:
            score_dist["0-20"] += 1
        elif r.trust_score <= 40:
            score_dist["21-40"] += 1
        elif r.trust_score <= 60:
            score_dist["41-60"] += 1
        elif r.trust_score <= 80:
            score_dist["61-80"] += 1
        else:
            score_dist["81-100"] += 1

    report = {
        "scan_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scanner": "AgentGraph Security Scanner",
        "target": "OpenClaw Skills Marketplace (top 100)",
        "summary": {
            "total_repos": len(OPENCLAW_SKILLS),
            "successfully_scanned": len(scanned),
            "errors": errors,
            "total_findings": total_findings,
            "critical_findings": total_critical,
            "high_findings": total_high,
            "medium_findings": total_medium,
            "repos_with_critical": repos_with_critical,
            "average_trust_score": round(avg_score, 1),
            "category_breakdown": categories,
            "score_distribution": score_dist,
            "scan_duration_seconds": round(elapsed, 1),
        },
        "repos": [_result_to_dict(r) for r in results],
    }

    # Write report
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2))

    # Print summary
    print("\n" + "=" * 90)
    print(f"\nOPENCLAW SECURITY SCAN SUMMARY")
    print(f"{'='*40}")
    print(f"Repos scanned:        {len(scanned)}/{len(OPENCLAW_SKILLS)}")
    print(f"Total findings:       {total_findings}")
    print(f"  Critical:           {total_critical}")
    print(f"  High:               {total_high}")
    print(f"  Medium:             {total_medium}")
    print(f"Repos with critical:  {repos_with_critical}/{len(scanned)}")
    print(f"Average trust score:  {avg_score:.1f}/100")
    print(f"Scan duration:        {elapsed:.1f}s")
    print(f"\nReport: {OUTPUT_PATH}")

    if categories:
        print(f"\nFindings by category:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"  {cat:<20} {count}")

    print(f"\nScore distribution:")
    for bucket, count in score_dist.items():
        bar = "#" * count
        print(f"  {bucket:<8} {count:>3} {bar}")


if __name__ == "__main__":
    asyncio.run(main())
