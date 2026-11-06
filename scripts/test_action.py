"""Run ONLY the Action agent on saved Facts + Findings. Usage: python scripts/test_action.py case_a"""
import asyncio, json, os, sys
from pathlib import Path
from cominty_sdk import AsyncCominty
from test_agents import call, parse

ROOT = Path(__file__).resolve().parent.parent

async def main(case_id: str) -> None:
    facts = json.loads((ROOT / f"data/test_runs/{case_id}_facts.json").read_text())
    findings = json.loads((ROOT / f"data/test_runs/{case_id}_findings.json").read_text())
    message = json.dumps({"facts": facts, "findings": findings}, ensure_ascii=False)
    async with AsyncCominty() as client:
        text, secs = await call(client, os.environ["AGENT_ID_ACTION"], message)
    out = parse("action", text)
    (ROOT / f"data/test_runs/{case_id}_action.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"Action replied in {secs:.1f}s")
    print("SUBJECT:", out["email"]["subject"])
    print("BODY:\n" + out["email"]["body_fr"])
    print("NOTES:", out.get("notes_for_staff"))
    print("FORM:", json.dumps(out.get("form"), ensure_ascii=False))

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "case_a"))
