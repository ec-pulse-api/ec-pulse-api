#!/usr/bin/env python3
"""EC Pulse repository patrol and safe self-repair engine.

Only mechanical, low-risk repairs are automatic. Business/legal/security facts are
never invented. The script emits a machine-readable summary for GitHub Actions.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def git(*args: str) -> tuple[int, str, str]:
    p = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()

    findings: list[dict] = []
    repairs: list[str] = []

    def finding(status: str, name: str, detail: str) -> None:
        findings.append({"status": status, "name": name, "detail": detail})

    server = read(ROOT / "plugins/ec-pulse/server.py")
    if server is None:
        finding("FAIL", "plugin-server", "plugins/ec-pulse/server.py is missing")
    else:
        tool_names = re.findall(r'^\s*_tool\("([^"]+)"', server, re.M)
        if len(tool_names) != 12 or len(set(tool_names)) != 12:
            finding("FAIL", "plugin-tools", f"expected 12 unique MCP tools, found {len(tool_names)}")
        else:
            finding("PASS", "plugin-tools", "12 unique MCP tools detected")

    gitignore_path = ROOT / ".gitignore"
    gitignore = read(gitignore_path)
    if gitignore is None:
        finding("FAIL", "gitignore", ".gitignore is missing")
    else:
        lines = gitignore.splitlines()
        missing = [x for x in (".env.*", "!.env.example") if x not in lines]
        if missing and args.repair:
            for item in missing:
                lines.append(item)
            write(gitignore_path, "\n".join(lines).rstrip() + "\n")
            repairs.append("Restored .gitignore secret-env rules: " + ", ".join(missing))
            missing = []
        if missing:
            finding("FAIL", "gitignore", "missing required rules: " + ", ".join(missing))
        else:
            finding("PASS", "gitignore", ".env.* excluded while .env.example remains trackable")

    readme_path = ROOT / "plugins/ec-pulse/README.md"
    readme = read(readme_path)
    if server and readme:
        tool_count = len(re.findall(r'^\s*_tool\("', server, re.M))
        updated, count = re.subn(r"- \d+ MCP tools", f"- {tool_count} MCP tools", readme, count=1)
        if count and updated != readme and args.repair:
            write(readme_path, updated)
            repairs.append(f"Synchronized plugin README MCP tool count to {tool_count}")
            readme = updated
        if re.search(rf"- {tool_count} MCP tools", readme):
            finding("PASS", "plugin-readme", "MCP tool count matches server")
        else:
            finding("FAIL", "plugin-readme", "MCP tool count is stale or missing")

    mcp = read(ROOT / "plugins/ec-pulse/.mcp.json")
    marketplace = read(ROOT / ".claude-plugin/marketplace.json")
    if not mcp or not marketplace:
        finding("FAIL", "plugin-manifests", "required plugin manifest is missing")
    else:
        if "${CLAUDE_PLUGIN_ROOT}" not in mcp:
            finding("FAIL", "plugin-mcp-path", "plugin-local .mcp.json does not use CLAUDE_PLUGIN_ROOT")
        else:
            finding("PASS", "plugin-mcp-path", "MCP manifest uses portable plugin root")
        if '"source": "./plugins/ec-pulse"' not in marketplace:
            finding("FAIL", "marketplace", "marketplace source does not point to plugins/ec-pulse")
        else:
            finding("PASS", "marketplace", "marketplace source points to plugins/ec-pulse")

    legal_paths = [
        ROOT / "docs/legal/privacy-policy.md",
        ROOT / "docs/legal/terms-of-service.md",
        ROOT / "docs/legal/billing-and-cancellation.md",
        ROOT / "docs/legal/commercial-transactions.md",
    ]
    legal_placeholders = []
    for path in legal_paths:
        content = read(path)
        if content is None:
            legal_placeholders.append(str(path.relative_to(ROOT)) + " missing")
        elif re.search(r"［[^］]+］", content):
            legal_placeholders.append(str(path.relative_to(ROOT)))
    if legal_placeholders:
        finding("BLOCKED", "legal", "placeholders remain; no business/legal facts will be invented: " + ", ".join(legal_placeholders))
    else:
        finding("PASS", "legal", "no unresolved Japanese bracket placeholders detected")

    code, stdout, _ = git(
        "grep", "-nE",
        r"(sk_live_[A-Za-z0-9]|whsec_[A-Za-z0-9]|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)",
        "--", "*.py", "*.md", "*.json", "*.yml", "*.yaml", "*.env*",
    )
    if code == 0:
        finding("FAIL", "secret-scan", "high-confidence secret pattern found in tracked text")
        if args.repair:
            print(stdout)
    else:
        finding("PASS", "secret-scan", "no high-confidence tracked secret pattern found")

    main_py = read(ROOT / "app/main.py")
    vercel = read(ROOT / "vercel.json")
    service = read(ROOT / "app/services/patrol.py")
    if main_py and 'app.get("/api/cron/patrol")' in main_py and "secrets.compare_digest" in main_py and "CRON_SECRET" in main_py:
        finding("PASS", "runtime-patrol", "protected /api/cron/patrol endpoint is wired")
    else:
        finding("FAIL", "runtime-patrol", "protected runtime patrol endpoint wiring is incomplete")
    if vercel and '"/api/cron/patrol"' in vercel and '"schedule"' in vercel:
        finding("PASS", "vercel-cron", "Vercel cron is configured for patrol")
    else:
        finding("FAIL", "vercel-cron", "Vercel patrol cron is not configured")
    if service and '"agent": "patrol-ai"' in service and "observe-repair-report" in service:
        finding("PASS", "patrol-engine", "runtime patrol engine reports and performs bounded repairs")
    else:
        finding("FAIL", "patrol-engine", "runtime patrol engine is missing expected reporting/repair contract")

    failures = [f for f in findings if f["status"] == "FAIL"]
    blocked = [f for f in findings if f["status"] == "BLOCKED"]
    status = "PASS" if not failures else "FAIL"
    report = {
        "agent": "ec-pulse-patrol-ai",
        "mode": "observe-repair-report",
        "status": status,
        "failures": failures,
        "blocked": blocked,
        "repairs": repairs,
        "findings": findings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
