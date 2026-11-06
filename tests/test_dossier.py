import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import ActionDraft, AgentReplyError, Facts, Findings, parse_reply


class FakeGateway:
    def __init__(self, delay=0):
        self.calls = []
        self.file_batches = []
        self.delay = delay

    async def call(self, agent_id, message, files, previous_run, before_call):
        self.file_batches.append(len(files))
        del previous_run
        await before_call()
        if self.delay:
            import asyncio
            await asyncio.sleep(self.delay)
        self.calls.append(agent_id)
        if agent_id == "fake-intake":
            case_id = message.split("case_id: ", 1)[1].split(".", 1)[0]
            value = {"case_id": case_id, "documents": [
                {"doc_id": doc, "fields": {"name": {
                    "value": "Demo Person", "confidence": 0.99,
                    "source": {"page": 1, "quote": "Demo Person"},
                }}} for doc in ("lease", "rib", "enrollment", "permit")
            ]}
            return json.dumps(value), object()
        if agent_id == "fake-verifier":
            return json.dumps({"findings": [], "missing_documents": [], "ready_to_submit": True}), None
        return json.dumps({"form": {"status": "draft"}, "email": {
            "to_role": "student", "subject": "Brouillon", "body_fr": "Projet",
        }, "notes_for_staff": []}), None


def test_parser_prose_before_json():
    parsed = parse_reply('Réponse préparée : {"findings":[],"missing_documents":[],"ready_to_submit":true}', Findings)
    assert parsed.findings == []


def test_parser_fenced_json():
    parsed = parse_reply('```json\n{"case_id":"x","documents":[]}\n```', Facts)
    assert parsed.case_id == "x"


def test_parser_rejects_missing_json():
    with pytest.raises(AgentReplyError, match="no JSON"):
        parse_reply("Aucun objet ici.", ActionDraft)


def setup_environment(monkeypatch, root: Path):
    for key, value in {
        "COMINTY_API_KEY": "test-key", "COMINTY_USER_ID": "test-user",
        "AGENT_ID_INTAKE": "fake-intake", "AGENT_ID_VERIFIER": "fake-verifier",
        "AGENT_ID_ACTION": "fake-action",
    }.items():
        monkeypatch.setenv(key, value)
    case_dir = root / "data/synthetic/cases/demo"
    case_dir.mkdir(parents=True)
    for doc in ("lease", "rib", "enrollment", "permit"):
        (case_dir / f"{doc}.pdf").write_bytes(f"fake-{doc}".encode())


def wait_state(client, case_id, expected):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/cases/{case_id}")
        if response.json()["state"] == expected:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"Case did not reach {expected}")


def test_happy_path_and_approve_once(tmp_path, monkeypatch):
    setup_environment(monkeypatch, tmp_path)
    gateway = FakeGateway()
    app = create_app(gateway, tmp_path, max_runs=10)
    with TestClient(app) as client:
        case_id = client.post("/api/cases", json={"demo_case_id": "demo"}).json()["case_id"]
        case = wait_state(client, case_id, "AWAITING_APPROVAL")
        assert len(case["facts"]["documents"]) == 4
        assert gateway.file_batches[:2] == [4, 0]
        assert client.post(f"/api/cases/{case_id}/approve", json={"reviewed": True}).status_code == 200
        assert client.post(f"/api/cases/{case_id}/approve", json={"reviewed": True}).status_code == 409
        wait_state(client, case_id, "DONE")
        assert gateway.calls.count("fake-action") == 1


def test_approve_before_approval_is_conflict(tmp_path, monkeypatch):
    setup_environment(monkeypatch, tmp_path)
    app = create_app(FakeGateway(delay=0.1), tmp_path, max_runs=10)
    with TestClient(app) as client:
        case_id = client.post("/api/cases", json={"demo_case_id": "demo"}).json()["case_id"]
        response = client.post(f"/api/cases/{case_id}/approve", json={"reviewed": True})
        assert response.status_code == 409


def test_reject_never_runs_action(tmp_path, monkeypatch):
    setup_environment(monkeypatch, tmp_path)
    gateway = FakeGateway()
    with TestClient(create_app(gateway, tmp_path, max_runs=10)) as client:
        case_id = client.post("/api/cases", json={"demo_case_id": "demo"}).json()["case_id"]
        wait_state(client, case_id, "AWAITING_APPROVAL")
        assert client.post(f"/api/cases/{case_id}/reject").status_code == 200
        assert client.get(f"/api/cases/{case_id}").json()["state"] == "REJECTED"
        assert "fake-action" not in gateway.calls


def test_budget_exhaustion_returns_429_without_call(tmp_path, monkeypatch):
    setup_environment(monkeypatch, tmp_path)
    gateway = FakeGateway()
    with TestClient(create_app(gateway, tmp_path, max_runs=0)) as client:
        response = client.post("/api/cases", json={"demo_case_id": "demo"})
        assert response.status_code == 429
        assert response.json() == {"error": "Run budget exhausted"}
        assert gateway.calls == []


def test_cache_hit_spends_no_runs(tmp_path, monkeypatch):
    setup_environment(monkeypatch, tmp_path)
    gateway = FakeGateway(delay=0.02)
    with TestClient(create_app(gateway, tmp_path, max_runs=2)) as client:
        first = client.post("/api/cases", json={"demo_case_id": "demo"}).json()["case_id"]
        second = client.post("/api/cases", json={"demo_case_id": "demo"}).json()["case_id"]
        wait_state(client, first, "AWAITING_APPROVAL")
        wait_state(client, second, "AWAITING_APPROVAL")
        audit = client.get("/api/audit").json()["summary"]
        assert audit["runs_used"] == 2 and len(gateway.calls) == 2
        assert audit["cache_hits"] >= 2
