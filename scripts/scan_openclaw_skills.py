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
    # Official / core
    {"full_name": "openclaw/openclaw", "framework": "openclaw", "desc": "Main OpenClaw framework"},
    {"full_name": "openclaw/clawhub", "framework": "openclaw", "desc": "Official skill registry"},
    # Popular individual skills
    {"full_name": "clawdbrunner/skill-agent-browser", "framework": "openclaw", "desc": "Browser automation for AI agents"},
    {"full_name": "daxiangnaoyang/self-improving-agent", "framework": "openclaw", "desc": "Agent self-evaluation and learning"},
    {"full_name": "kepano/obsidian-skills", "framework": "openclaw", "desc": "Obsidian vault search and notes"},
    {"full_name": "mvanhorn/last30days-skill", "framework": "openclaw", "desc": "Multi-source research (Reddit, X, YouTube)"},
    {"full_name": "win4r/OpenClaw-Skill", "framework": "openclaw", "desc": "OpenClaw skill collection"},
    {"full_name": "austindixson/mulch", "framework": "openclaw", "desc": "Self-improvement skill"},
    {"full_name": "Decodo/decodo-openclaw-skill", "framework": "openclaw", "desc": "Web scraping via Decodo API"},
    {"full_name": "WJZ-P/gemini-skill", "framework": "openclaw", "desc": "Gemini drawing MCP and skill"},
    {"full_name": "ckckck/UltimateSearchSkill", "framework": "openclaw", "desc": "Dual-engine web search"},
    # High-risk categories
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
    # Ecosystem tools
    {"full_name": "agentkernel/openclaw-desktop", "framework": "openclaw", "desc": "Windows desktop installer"},
    {"full_name": "pinchbench/skill", "framework": "openclaw", "desc": "Benchmarking for coding agents"},
    # Curated collections (smaller ones that are actual skill repos)
    {"full_name": "mergisi/awesome-openclaw-agents", "framework": "openclaw", "desc": "Production-ready agent templates"},
    {"full_name": "SamurAIGPT/awesome-openclaw", "framework": "openclaw", "desc": "Curated resources and tools"},
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
        "target": "OpenClaw Skills Marketplace (top 25)",
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
