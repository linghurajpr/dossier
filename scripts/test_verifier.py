"""Re-run ONLY the Verifier on saved Facts. Usage: python scripts/test_verifier.py case_a"""
import asyncio, json, os, sys
from pathlib import Path
from cominty_sdk import AsyncCominty
from test_agents import call, parse

ROOT = Path(__file__).resolve().parent.parent

async def main(case_id: str) -> None:
    facts = json.loads((ROOT / f"data/test_runs/{case_id}_facts.json").read_text())
    async with AsyncCominty() as client:
        text, secs = await call(client, os.environ["AGENT_ID_VERIFIER"], json.dumps(facts, ensure_ascii=False))
    findings = parse("verifier", text)
    print(f"Verifier replied in {secs:.1f}s")
    for item in findings.get("findings", []):
        print(f"  [{item['severity']}] {item['rule']}: {item['message']}")
    print("  findings:", len(findings.get("findings", [])), "| ready_to_submit:", findings.get("ready_to_submit"))

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "case_a"))
