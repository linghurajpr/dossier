from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from app.gateway import ComintyGateway
from app.pipeline import DossierService

ROOT = Path(__file__).resolve().parents[1]


def normalize(value: object) -> str:
    text = str(value).strip().casefold()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    french_months = {
        "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
        "juin": 6, "juillet": 7, "aout": 8, "septembre": 9,
        "octobre": 10, "novembre": 11, "decembre": 12,
    }
    date_match = re.fullmatch(r"(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", text)
    if date_match:
        month = normalize(date_match.group(2))
        if month in french_months:
            return f"{int(date_match.group(3)):04d}-{french_months[month]:02d}-{int(date_match.group(1)):02d}"
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("€", "").replace("eur", "").replace(" ", "").replace(",", ".")
    try:
        return format(Decimal(text).normalize(), "f")
    except InvalidOperation:
        return " ".join(text.split())


def flatten_fields(fields: dict) -> list[tuple[str, str, object]]:
    return [(doc, key, value) for doc, values in fields.items()
            for key, value in values.items()]


async def evaluate() -> dict:
    load_dotenv()
    ground_truth = ROOT / "data" / "synthetic" / "ground_truth"
    records = [json.loads(path.read_text(encoding="utf-8"))
               for path in sorted(ground_truth.glob("*.json"))]
    gateway = ComintyGateway()
    await gateway.open()
    service = DossierService(gateway, ROOT)
    cases, elapsed_values = [], []
    try:
        for truth in records:
            before_runs = service.runs_used
            started = perf_counter()
            case_id = await service.create_case(truth["case_id"])
            while service.case_view(case_id)["state"] in {
                "CREATED", "INTAKE_RUNNING", "VERIFY_RUNNING",
            }:
                await asyncio.sleep(0.1)
            elapsed = perf_counter() - started
            elapsed_values.append(elapsed)
            result = service.case_view(case_id)
            facts = result.get("facts") or {}
            extracted = {
                doc["doc_id"]: doc.get("fields", {})
                for doc in facts.get("documents", [])
            }
            results = []
            for doc_id, field, expected in flatten_fields(truth["fields"]):
                record = extracted.get(doc_id, {}).get(field, {})
                got = record.get("value") if isinstance(record, dict) else None
                results.append({
                    "doc_id": doc_id, "field": field, "expected": expected,
                    "got": got,
                    "correct": result["state"] == "AWAITING_APPROVAL"
                    and got is not None and normalize(got) == normalize(expected),
                })
            got_rules = sorted({
                item["rule"] for item in (result.get("findings") or {}).get("findings", [])
            })
            cases.append({
                "case_id": truth["case_id"], "status": result["state"],
                "field_results": results,
                "findings_expected": truth["expected_findings"],
                "findings_got": got_rules,
                "_runs": service.runs_used - before_runs,
                "_latency": elapsed,
            })
    finally:
        await gateway.close()

    field_results = [row for case in cases for row in case["field_results"]]
    expected_count = sum(len(truth["expected_findings"]) for truth in records)
    found_count = sum(
        sum(item["rule"] in case["findings_got"] for item in truth["expected_findings"])
        for truth, case in zip(records, cases)
    )
    recall = found_count / expected_count if expected_count else 1.0
    false_positives = sum(
        sum(rule not in {item["rule"] for item in truth["expected_findings"]}
            or rule in truth["must_not_flag"] for rule in case["findings_got"])
        for truth, case in zip(records, cases)
    )
    payload = {
        "status": "done", "created_at": datetime.now().astimezone().isoformat(),
        "n_cases": len(cases),
        "disclaimer": "Small evaluation on synthetic data; indicative only.",
        "variants": [{
            "variant": "default", "model_label": "(see Cominty dashboard)",
            "field_accuracy": (
                sum(row["correct"] for row in field_results) / len(field_results)
                if field_results else 0.0
            ),
            "recall": recall, "false_positives": false_positives,
            "runs": sum(case["_runs"] for case in cases),
            "avg_latency_s": sum(elapsed_values) / len(elapsed_values) if elapsed_values else 0.0,
            "cost_per_dossier_eur": None,
            "cost_note": "read from Cominty usage dashboard",
        }],
        "cases": [{
            key: value for key, value in case.items() if not key.startswith("_")
        } for case in cases],
    }
    output = ROOT / "data" / "eval" / "latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    variant = payload["variants"][0]
    print("case_id | status | field_accuracy | findings")
    for case in cases:
        total = len(case["field_results"])
        correct = sum(row["correct"] for row in case["field_results"])
        print(f"{case['case_id']} | {case['status']} | {correct}/{total} | {case['findings_got']}")
    print(f"Overall field accuracy {variant['field_accuracy']:.1%}; recall {recall:.1%}; "
          f"false positives {false_positives}; runs {variant['runs']}")
    return payload


if __name__ == "__main__":
    asyncio.run(evaluate())
