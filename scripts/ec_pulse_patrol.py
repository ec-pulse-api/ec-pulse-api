#!/usr/bin/env python3
"""EC Pulse self-contained repository patrol.

This is the no-credential patrol layer. It diagnoses concrete repository
conditions and performs only allowlisted mechanical repairs. An LLM may be
used by the runtime patrol separately, but GitHub patrol never depends on it.
"""
from __future__ import annotations
import json, re, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RESULTS=[]; REPAIRS=[]

def check(name, ok, detail):
    RESULTS.append({"name":name,"ok":bool(ok),"detail":detail})

def repair(name, detail):
    REPAIRS.append({"name":name,"detail":detail})

def run(*args):
    p=subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
    return p.returncode,p.stdout,p.stderr

def main():
    gitignore=ROOT/".gitignore"
    content=gitignore.read_text() if gitignore.exists() else ""
    required=[".env.*","!.env.example"]
    missing=[x for x in required if x not in content.splitlines()]
    if missing:
        lines=content.splitlines()
        lines.extend(missing)
        gitignore.write_text("\n".join(dict.fromkeys(lines)).rstrip()+"\n")
        repair("gitignore","restored: "+", ".join(missing))
        content=gitignore.read_text()
    check("gitignore", all(x in content.splitlines() for x in required), "secret env ignored; example retained")

    server=ROOT/"plugins/ec-pulse/server.py"
    if server.exists():
        s=server.read_text()
        tools=re.findall(r'^\s*_tool\("([^"]+)"',s,re.M)
        check("mcp-tools",len(tools)==12 and len(set(tools))==12,f"{len(tools)} unique MCP tools")
        check("api-key-source","EC_PULSE_API_KEY" in s and "print(" not in s,"API key is environment-sourced without print")
        check("url-safety","getaddrinfo" in s and "is_private" in s,"DNS/private destination checks present")
    else:
        check("mcp-server",False,"server.py missing")

    marketplace=ROOT/".claude-plugin/marketplace.json"
    mcp=ROOT/"plugins/ec-pulse/.mcp.json"
    check("marketplace",marketplace.exists() and "./plugins/ec-pulse" in marketplace.read_text(),"root marketplace points to plugin")
    check("mcp-manifest",mcp.exists() and "CLAUDE_PLUGIN_ROOT" in mcp.read_text(),"portable plugin-local MCP manifest")

    legal=[]
    for p in [ROOT/"docs/legal/privacy-policy.md",ROOT/"docs/legal/terms-of-service.md",ROOT/"docs/legal/billing-and-cancellation.md",ROOT/"docs/legal/commercial-transactions.md"]:
        if p.exists() and re.search(r"［[^］]+］",p.read_text()):
            legal.append(str(p.relative_to(ROOT)))
    check("legal-placeholders",not legal,"unresolved placeholders: "+", ".join(legal) if legal else "none")

    code,out,err=run("git","grep","-nE",r"(sk_live_[A-Za-z0-9]|whsec_[A-Za-z0-9]|-----BEGIN .*PRIVATE KEY-----)","--","*.py","*.md","*.json","*.yml","*.yaml",":!scripts/ec_pulse_patrol.py")
    check("secret-scan",code!=0,"no high-confidence tracked secret pattern" if code!=0 else "secret pattern found")

    py_files=list((ROOT/"plugins/ec-pulse").rglob("*.py"))
    failures=[]
    for p in py_files:
        code,_,err=run(sys.executable,"-m","py_compile",str(p))
        if code: failures.append(str(p.relative_to(ROOT)))
    check("python-compile",not failures,"compile failures: "+", ".join(failures) if failures else "none")

    tests=ROOT/"plugins/ec-pulse/tests"
    if tests.exists():
        code,out,err=run(sys.executable,"-m","unittest","discover","-s",str(tests),"-v")
        check("plugin-tests",code==0,"plugin tests pass" if code==0 else "plugin tests failed")
    else:
        check("plugin-tests",False,"test directory missing")

    failed=[x for x in RESULTS if not x["ok"]]
    report={"agent":"ec-pulse-patrol-ai","engine":"self-contained","mode":"observe-repair-report","status":"PASS" if not failed else "FAIL","findings":RESULTS,"repairs":REPAIRS,"failures":failed}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
