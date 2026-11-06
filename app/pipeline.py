from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.models import ActionDraft, Facts, Findings, parse_reply

log = logging.getLogger("dossier")
DOCS = ("lease", "rib", "enrollment", "permit")
TRANSITIONS = {
    "CREATED": {"INTAKE_RUNNING", "FAILED"},
    "INTAKE_RUNNING": {"VERIFY_RUNNING", "FAILED"},
    "VERIFY_RUNNING": {"AWAITING_APPROVAL", "FAILED"},
    "AWAITING_APPROVAL": {"ACTION_RUNNING", "REJECTED", "FAILED"},
    "ACTION_RUNNING": {"DONE", "FAILED"},
    "DONE": set(), "REJECTED": set(), "FAILED": set(),
}


class BudgetExceeded(Exception):
    pass


class DossierService:
    def __init__(self, gateway: Any, repo_root: Path, max_runs: int | None = None):
        self.gateway = gateway
        self.repo_root = repo_root
        self.data_root = repo_root / "data"
        self.state_path = self.data_root / "state.json"
        self.cache_path = self.data_root / "cache.json"
        self.max_runs = max_runs if max_runs is not None else int(os.getenv("DOSSIER_MAX_RUNS", "40"))
        self.prompt_version = os.getenv("PROMPT_VERSION", "v1")
        self.agent_ids = {
            "intake": os.getenv("AGENT_ID_INTAKE", ""),
            "verifier": os.getenv("AGENT_ID_VERIFIER", ""),
            "action": os.getenv("AGENT_ID_ACTION", ""),
        }
        self._lock = asyncio.Lock()
        self._case_locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self._reservations: dict[str, int] = {}
        self._reserved_runs = 0
        self._pending_intake: dict[str, int] = {}
        self._case_intake_keys: dict[str, str] = {}
        self._cache_locks: dict[str, asyncio.Lock] = {}
        self.data_root.mkdir(parents=True, exist_ok=True)
        if self.state_path.exists():
            saved = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.cases = saved.get("cases", {})
            self.audit = saved.get("audit", [])
            self.runs_used = saved.get("runs_used", 0)
        else:
            self.cases, self.audit, self.runs_used = {}, [], 0
        if self.cache_path.exists():
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        else:
            self.cache = {}

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _persist(self) -> None:
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps({
            "cases": self.cases, "audit": self.audit, "runs_used": self.runs_used,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    def _persist_cache(self) -> None:
        temp = self.cache_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.cache_path)

    def _event(self, kind: str, case_id: str | None = None, **data: object) -> None:
        event = {"timestamp": self.now(), "type": kind, "case_id": case_id, **data}
        self.audit.append(event)
        self._persist()
        log.info(json.dumps({"event": kind, "case_id": case_id, **data}, ensure_ascii=False))

    def transition(self, case_id: str, state: str) -> None:
        case = self.cases[case_id]
        old = case["state"]
        if state not in TRANSITIONS[old]:
            log.error(json.dumps({"event": "illegal_transition", "case_id": case_id,
                                  "from_state": old, "to_state": state}))
            raise ValueError(f"Illegal state transition: {old} -> {state}")
        case["state"] = state
        self._event("transition", case_id, from_state=old, to_state=state)

    def demo_cases(self) -> list[str]:
        root = self.data_root / "synthetic" / "cases"
        return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []

    def files_for(self, demo_case_id: str) -> dict[str, Path]:
        if demo_case_id not in self.demo_cases():
            raise ValueError("Unknown demo case")
        base = self.data_root / "synthetic" / "cases" / demo_case_id
        result = {doc: base / f"{doc}.pdf" for doc in DOCS}
        if any(not path.is_file() for path in result.values()):
            raise FileNotFoundError("Demo case is missing one or more required PDFs")
        return result

    def _key(self, agent_id: str, message: str, files: list[Path]) -> str:
        hashes = sorted(hashlib.sha256(path.read_bytes()).hexdigest() for path in files)
        raw = agent_id + self.prompt_version + message + "".join(hashes)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _agent_key(self, role: str, message: str, files: list[Path]) -> str:
        return self._key(self.agent_ids[role], message, files)

    def estimate_create_runs(self, demo_case_id: str) -> int:
        paths = self.files_for(demo_case_id)
        message = f"case_id: {demo_case_id}. Extract all fields from the attached documents."
        intake_key = self._agent_key("intake", message, list(paths.values()))
        if self._pending_intake.get(intake_key):
            return 0
        if intake_key not in self.cache:
            return 2
        try:
            facts = parse_reply(self.cache[intake_key], Facts)
            verifier_message = json.dumps(facts.model_dump(), ensure_ascii=False)
            return int(self._agent_key("verifier", verifier_message, []) not in self.cache)
        except Exception as exc:
            log.warning(json.dumps({"event": "cache_preflight_parse_failed",
                                    "error_type": type(exc).__name__}))
            return 2

    async def create_case(self, demo_case_id: str, reservation: int = 0) -> str:
        paths = self.files_for(demo_case_id)
        message = f"case_id: {demo_case_id}. Extract all fields from the attached documents."
        intake_key = self._agent_key("intake", message, list(paths.values()))
        case_id = str(uuid.uuid4())
        async with self._lock:
            if self.runs_used + self._reserved_runs + reservation > self.max_runs:
                raise BudgetExceeded("Run budget exhausted")
            self.cases[case_id] = {
                "case_id": case_id, "demo_case_id": demo_case_id, "state": "CREATED",
                "facts": None, "findings": None, "artifacts": None, "error": None,
                "runs": 0, "usage": None, "created_at": self.now(),
            }
            self._reservations[case_id] = reservation
            self._reserved_runs += reservation
            self._pending_intake[intake_key] = self._pending_intake.get(intake_key, 0) + 1
            self._case_intake_keys[case_id] = intake_key
            self._persist()
        self._event("case_created", case_id, demo_case_id=demo_case_id)
        task = asyncio.create_task(self.run_to_approval(case_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return case_id

    async def _invoke(
        self, case_id: str, role: str, message: str, files: list[Path],
        previous_run: object | None = None,
    ) -> tuple[str, object | None]:
        agent_id = self.agent_ids[role]
        key = self._key(agent_id, message, files)
        lock = self._cache_locks.setdefault(key, asyncio.Lock())
        async with lock:
            return await self._invoke_locked(case_id, agent_id, message, files, previous_run, key)

    async def _invoke_locked(
        self, case_id: str, agent_id: str, message: str, files: list[Path],
        previous_run: object | None, key: str,
    ) -> tuple[str, object | None]:
        async with self._lock:
            if key in self.cache:
                self._event("cache_hit", case_id, agent_id=agent_id, input_hash=key)
                return self.cache[key], None

        used = 0

        async def reserve() -> None:
            nonlocal used
            async with self._lock:
                held = self._reservations.get(case_id, 0)
                if held:
                    self._reservations[case_id] = held - 1
                    self._reserved_runs -= 1
                elif self.runs_used + self._reserved_runs >= self.max_runs:
                    raise BudgetExceeded("Run budget exhausted")
                self.runs_used += 1
                self.cases[case_id]["runs"] += 1
                used += 1
                self._persist()

        started = time.perf_counter()
        output = ""
        failure_type = None
        try:
            output, run = await asyncio.wait_for(
                self.gateway.call(agent_id, message, files, previous_run, reserve),
                timeout=120,
            )
            return output, run
        except Exception as exc:
            failure_type = type(exc).__name__
            raise
        finally:
            if used:
                elapsed = time.perf_counter() - started
                self._event("agent_call", case_id, agent_id=agent_id, input_hash=key,
                            output_hash=hashlib.sha256(output.encode()).hexdigest() if output else None,
                            latency_s=round(elapsed, 4), runs=used,
                            success=failure_type is None, error_type=failure_type)
                if output:
                    async with self._lock:
                        self.cache[key] = output
                        self._persist_cache()

    def _validation_failure(self, case_id: str, role: str, exc: Exception) -> None:
        self._event("validation_failure", case_id, agent=role, error_type=type(exc).__name__)

    async def _release_reservation(self, case_id: str) -> None:
        async with self._lock:
            unused = self._reservations.pop(case_id, 0)
            self._reserved_runs -= unused

    async def _validated(
        self, case_id: str, role: str, message: str, files: list[Path],
        model: type[BaseModel], previous_run: object | None = None,
        expected_case_id: str | None = None,
    ) -> tuple[BaseModel, object | None]:
        def parse(text: str) -> BaseModel:
            value = parse_reply(text, model)
            if expected_case_id is not None and isinstance(value, Facts) and value.case_id != expected_case_id:
                raise ValueError("Intake returned the wrong case_id")
            return value

        text, run = await self._invoke(case_id, role, message, files, previous_run)
        try:
            return parse(text), run
        except Exception as first:
            self._validation_failure(case_id, role, first)
            self._event("retry", case_id, agent=role, attempt=1)
            repair = f"{message}\nYour previous reply was invalid: {first}. Reply with valid JSON only."
            text, repaired_run = await self._invoke(case_id, role, repair, files, run)
            try:
                return parse(text), repaired_run or run
            except Exception as second:
                self._validation_failure(case_id, role, second)
                raise ValueError(f"{role.title()} reply failed validation after one repair") from second

    async def run_to_approval(self, case_id: str) -> None:
        lock = self._case_locks.setdefault(case_id, asyncio.Lock())
        async with lock:
            case = self.cases[case_id]
            if case["state"] != "CREATED":
                return
            try:
                paths = self.files_for(case["demo_case_id"])
                self.transition(case_id, "INTAKE_RUNNING")
                message = f"case_id: {case['demo_case_id']}. Extract all fields from the attached documents."
                facts_model, intake_run = await self._validated(
                    case_id, "intake", message, list(paths.values()), Facts,
                    expected_case_id=case["demo_case_id"],
                )
                facts = facts_model
                found = {doc.doc_id for doc in facts.documents}
                missing = [doc for doc in DOCS if doc not in found]
                if missing:
                    self._validation_failure(
                        case_id, "intake", ValueError("Required documents were omitted")
                    )
                repair_failures = []
                for doc_id in missing:
                    self._event("retry", case_id, agent="intake", document=doc_id, attempt=1)
                    repair_message = (
                        f"case_id: {case['demo_case_id']}. Extract only document {doc_id} "
                        "from the previous attachments."
                    )
                    repaired_text, repaired_run = await self._invoke(
                        case_id, "intake", repair_message, [paths[doc_id]], intake_run
                    )
                    try:
                        repaired = parse_reply(repaired_text, Facts)
                    except Exception as exc:
                        self._validation_failure(case_id, "intake", exc)
                        repair_failures.append(doc_id)
                        continue
                    intake_run = repaired_run or intake_run
                    repaired_doc = next(
                        (doc for doc in repaired.documents if doc.doc_id == doc_id), None
                    )
                    if repaired.case_id != facts.case_id or repaired_doc is None:
                        self._validation_failure(case_id, "intake", ValueError("Document repair was incomplete"))
                        repair_failures.append(doc_id)
                        continue
                    fact_docs = {doc.doc_id: doc for doc in facts.documents}
                    fact_docs[doc_id] = repaired_doc
                    facts = Facts(case_id=facts.case_id, documents=list(fact_docs.values()))
                if repair_failures or {doc.doc_id for doc in facts.documents} != set(DOCS):
                    raise ValueError("Intake did not return all four required documents")
                case["facts"] = facts.model_dump()
                self._persist()
                self.transition(case_id, "VERIFY_RUNNING")
                verifier_message = json.dumps(facts.model_dump(), ensure_ascii=False)
                findings_model, _ = await self._validated(
                    case_id, "verifier", verifier_message, [], Findings
                )
                findings = findings_model
                case["findings"] = findings.model_dump()
                self._persist()
                self.transition(case_id, "AWAITING_APPROVAL")
            except Exception as exc:
                case["error"] = self._safe_error(exc, "Pipeline")
                if case["state"] not in {"DONE", "REJECTED", "FAILED"}:
                    self.transition(case_id, "FAILED")
                self._event("pipeline_failed", case_id, error_type=type(exc).__name__)
            finally:
                await self._release_reservation(case_id)
                async with self._lock:
                    intake_key = self._case_intake_keys.pop(case_id, None)
                    if intake_key is not None:
                        pending = self._pending_intake.get(intake_key, 0)
                        if pending <= 1:
                            self._pending_intake.pop(intake_key, None)
                        else:
                            self._pending_intake[intake_key] = pending - 1

    async def approve(self, case_id: str) -> tuple[bool, str]:
        case = self.cases.get(case_id)
        if not case:
            return False, "Case not found"
        async with self._lock:
            case = self.cases[case_id]
            if case["state"] != "AWAITING_APPROVAL":
                return False, "Case is not awaiting approval"
            action_message = json.dumps({
                "facts": case["facts"], "findings": case["findings"],
            }, ensure_ascii=False)
            cached = self._key(self.agent_ids["action"], action_message, []) in self.cache
            reservation = 0 if cached else 1
            if self.runs_used + self._reserved_runs + reservation > self.max_runs:
                return False, "Run budget exhausted"
            self._reservations[case_id] = reservation
            self._reserved_runs += reservation
            self.transition(case_id, "ACTION_RUNNING")
            self._event("approved", case_id)
            task = asyncio.create_task(self.run_action(case_id, action_message))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return True, ""

    async def run_action(self, case_id: str, message: str) -> None:
        async with self._case_locks.setdefault(case_id, asyncio.Lock()):
            if self.cases[case_id]["state"] != "ACTION_RUNNING":
                return
            try:
                action, _ = await self._validated(
                    case_id, "action", message, [], ActionDraft
                )
                self.cases[case_id]["artifacts"] = action.model_dump()
                self._persist()
                self.transition(case_id, "DONE")
            except Exception as exc:
                self.cases[case_id]["error"] = self._safe_error(exc, "Action")
                self.transition(case_id, "FAILED")
                self._event("action_failed", case_id, error_type=type(exc).__name__)
            finally:
                await self._release_reservation(case_id)

    @staticmethod
    def _safe_error(exc: Exception, stage: str) -> str:
        if isinstance(exc, BudgetExceeded):
            return "Run budget exhausted."
        if isinstance(exc, TimeoutError):
            return f"{stage} agent call timed out after 120 seconds."
        if isinstance(exc, FileNotFoundError):
            return f"{stage} failed because required files are unavailable."
        if isinstance(exc, (ValueError,)):
            return f"{stage} validation failed: {type(exc).__name__}."
        return f"{stage} agent call failed: {type(exc).__name__}."

    async def reject(self, case_id: str) -> tuple[bool, str]:
        if case_id not in self.cases:
            return False, "Case not found"
        async with self._lock:
            if self.cases[case_id]["state"] != "AWAITING_APPROVAL":
                return False, "Case is not awaiting approval"
            self.transition(case_id, "REJECTED")
            self._event("rejected", case_id)
            return True, ""

    def case_view(self, case_id: str) -> dict | None:
        return self.cases.get(case_id)

    def audit_view(self) -> dict:
        hits = sum(event["type"] == "cache_hit" for event in self.audit)
        return {"events": self.audit, "summary": {
            "runs_used": self.runs_used, "runs_cap": self.max_runs, "cache_hits": hits,
        }}
