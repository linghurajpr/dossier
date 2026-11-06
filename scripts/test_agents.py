"""Manual agent test: Intake (4 PDFs, one message) -> Verifier. Spends ~2 runs per case."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from cominty_sdk import AsyncCominty

DOCS = ["lease", "rib", "enrollment", "permit"]
ROOT = Path(__file__).resolve().parent.parent


def clean(text: str) -> str:
    """Return the JSON object inside a reply: fenced block if present, else first '{' to last '}'."""
    t = text.strip()
    if "```" in t:
        for block in t.split("```")[1::2]:
            block = block.strip()
            if block.lower().startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                return block
    start, end = t.find("{"), t.rfind("}")
    return t[start:end + 1] if start != -1 and end > start else t


def parse(label: str, text: str) -> dict:
    try:
        return json.loads(clean(text))
    except json.JSONDecodeError as exc:
        print(f"FAIL {label}: not valid JSON ({exc}). First 600 chars of reply:\n{text[:600]}")
        sys.exit(1)


async def call(client, agent_id: str, message: str, file_ids=None):
    kwargs = {"agent_id": agent_id, "message": message}
    if file_ids:
        kwargs["file_ids"] = file_ids
    t0 = time.perf_counter()
    run = await client.chat.start(**kwargs)
    text = await run.text()
    return text, time.perf_counter() - t0


async def main(case_id: str) -> None:
    intake_id = os.environ["AGENT_ID_INTAKE"]
    verifier_id = os.environ["AGENT_ID_VERIFIER"]
    case_dir = ROOT / "data/synthetic/cases" / case_id
    out_dir = ROOT / "data/test_runs"

    async with AsyncCominty() as client:
        file_ids = []
        for doc in DOCS:
            f = await client.chat.upload_file(case_dir / f"{doc}.pdf")
            file_ids.append(f.id)

        text, secs = await call(
            client, intake_id,
            f"case_id: {case_id}. Extract all fields from the attached documents.", file_ids,
        )
        print(f"Intake replied in {secs:.1f}s, raw starts with: {text.strip()[:1]!r}")
        facts = parse("intake", text)
        (out_dir / f"{case_id}_facts.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False))

        found = {d["doc_id"]: d["fields"] for d in facts.get("documents", [])}
        print("Documents found:", sorted(found), "| missing:", sorted(set(DOCS) - set(found)))
        for doc_id, fields in found.items():
            filled = sum(1 for v in fields.values() if v.get("value") is not None)
            print(f"  {doc_id}: {filled}/{len(fields)} fields filled")
        print("  lease address:", found.get("lease", {}).get("property_address", {}).get("value"))
        print("  rib address:  ", found.get("rib", {}).get("holder_address", {}).get("value"))

        text, secs = await call(client, verifier_id, json.dumps(facts, ensure_ascii=False))
        print(f"\nVerifier replied in {secs:.1f}s")
        findings = parse("verifier", text)
        (out_dir / f"{case_id}_findings.json").write_text(json.dumps(findings, indent=2, ensure_ascii=False))
        for item in findings.get("findings", []):
            print(f"  [{item['severity']}] {item['rule']}: {item['message']}")
        print("  ready_to_submit:", findings.get("ready_to_submit"))

    truth = json.loads((ROOT / "data/synthetic/ground_truth" / f"{case_id}.json").read_text())
    print("\nExpected findings:", truth.get("expected_findings"), "| must not flag:", truth.get("must_not_flag"))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "case_a"))
