# Spends real credits: about 5 runs.
import asyncio
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample.pdf"
ATTR_NAMES = ("approve", "resume", "status", "cancel", "usage", "tokens", "cost")
TITLES = (
    "Auth + basic run", "Event shape", "File upload", "Structured output",
    "Multi-file message", "Memory", "Approval API", "Usage data", "Latency",
)


def public_names(value: object) -> list[str]:
    return [name for name in dir(value) if not name.startswith("_")]


def print_attributes(value: object) -> None:
    attrs = {}
    for name in public_names(value):
        try:
            attrs[name] = repr(getattr(value, name))
        except Exception as exc:
            attrs[name] = f"<{type(exc).__name__}: {exc}>"
    print(f"{type(value).__name__} attributes: {attrs}")


async def probe(index: int, client, state: dict, counts: dict):
    async def start(message: str, file_ids: list[str] | None = None):
        counts["chat.start"] += 1
        return await client.chat.start(
            agent_id="__cominty_agents::agent.chat", message=message,
            file_ids=file_ids or [], max_steps=2,
        )

    if index == 1:
        text = await (await start("ping")).text()
        return "PASS", f"basic run completed; text={text!r}"
    if index == 2:
        run = await start("Report a brief status.")
        state["run"] = run
        async for event in run:
            state["events"].append(event)
            print(f"Event type: {type(event).__name__}")
            print_attributes(event)
        state["reply"] = await run.result()
        print(f"dir(run): {public_names(run)}; dir(reply): {public_names(state['reply'])}")
        return "PASS", f"iterated {len(state['events'])} event(s) and read reply"
    if index == 3:
        uploaded = await client.chat.upload_file(SAMPLE)
        text = await (await start("What is the document title and the rent amount? Answer in one line.",
                                  [uploaded.id])).text()
        return "PASS", f"uploaded {SAMPLE.name}; text={text!r}"
    if index == 4:
        text = await (await start('Answer ONLY with JSON {"ok": true, "n": 3} and no prose.')).text()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            wrapped = text.strip().startswith("```") or not text.strip().startswith("{")
            form = "wrapped in prose or code fences" if wrapped else "not valid JSON"
            return "FAIL", f"{type(exc).__name__}: {exc}; response is {form}: {text!r}"
        if parsed != {"ok": True, "n": 3}: return "FAIL", f"JSON parsed directly but differs from requested object: {parsed!r}"
        return "PASS", f"json.loads(text) worked directly: {text!r}"
    if index == 5:
        first = await client.chat.upload_file(SAMPLE)
        second = await client.chat.upload_file(SAMPLE.read_bytes(), filename="sample-copy.pdf")
        run = await start("What are the document title and rent amount in the attached files?",
                          [first.id, second.id])
        return "PASS", f"uploaded two files and sent both IDs; text={await run.text()!r}"
    if index == 6:
        path = f"recon/{time.time_ns()}.txt"
        await client.memory.create(path=path, namespace="dossier-recon",
                                   purpose="Cominty SDK recon probe",
                                   content="recon memory round-trip")
        return "PASS", f"memory round-trip at {path}; value={await client.memory.get(path, namespace='dossier-recon')!r}"
    if index == 7:
        objects = [(key, state[key]) for key in ("run", "reply") if key in state]
        if not objects: return "MISSING", "run/reply objects unavailable"
        found = [f"{label}.{name}" for label, obj in objects
                 for name in ATTR_NAMES if hasattr(obj, name)]
        print(f"Approval/status attributes present: {found or 'none'}")
        return ("PASS" if found else "MISSING", f"present: {', '.join(found) if found else 'none'}")
    if index == 8:
        objects = list(state["events"]) + ([state["reply"]] if "reply" in state else [])
        matches = []
        for obj in objects:
            for name in dir(obj):
                if any(term in name.lower() for term in ("token", "cost", "usage")):
                    try:
                        value = repr(getattr(obj, name))
                    except Exception as exc:
                        value = f"<{type(exc).__name__}: {exc}>"
                    matches.append(f"{type(obj).__name__}.{name}={value}")
        print(f"Usage-related attributes: {matches or 'none'}")
        return ("PASS" if matches else "MISSING",
                f"found {len(matches)} usage-related attribute(s)")
    latencies = state["latencies"]
    if 1 not in latencies or 3 not in latencies: return "MISSING", "probe 1 or 3 latency unavailable"
    return "PASS", f"probe 1: {latencies[1]:.3f}s; probe 3: {latencies[3]:.3f}s"


async def main() -> None:
    records, counts = [], {"chat.start": 0, "chat.send": 0}
    state = {"events": [], "latencies": {}}

    def report(index: int, status: str, detail: str) -> None:
        title = TITLES[index - 1]
        records.append((index, title, status, detail))
        print(f"{status} [{index}] {title}: {detail}")

    try:
        from cominty_sdk import AsyncCominty
        async with AsyncCominty() as client:
            for index in range(1, 10):
                started = time.perf_counter() if index in (1, 3) else None
                try:
                    status, detail = await probe(index, client, state, counts)
                except Exception as exc:
                    status, detail = "FAIL", f"{type(exc).__name__}: {exc}"
                if started is not None:
                    elapsed = time.perf_counter() - started
                    state["latencies"][index] = elapsed
                    detail += f" (elapsed {elapsed:.3f}s)"
                report(index, status, detail)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        print(f"FAIL [client setup/cleanup]: {error}")
        if not records: report(1, "FAIL", error)
        for index in range(len(records) + 1, 10): report(index, "MISSING", "client unavailable")

    print(f"Total chat.start/chat.send calls: {counts['chat.start']}/{counts['chat.send']} ({sum(counts.values())} total)")
    lines = ["# Cominty SDK recon summary", ""]
    lines.extend(f"- **{status} [{i}] {title}:** {detail}"
                 for i, title, status, detail in records)
    lines.extend(["", f"- **chat.start calls:** {counts['chat.start']}",
                  f"- **chat.send calls:** {counts['chat.send']}",
                  f"- **total calls:** {sum(counts.values())}", ""])
    try:
        output = ROOT / "docs" / "recon.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines), encoding="utf-8")
        print(f"Summary written to {output}")
    except Exception as exc:
        print(f"FAIL [summary write]: {type(exc).__name__}: {exc}")

if __name__ == "__main__":
    asyncio.run(main())
