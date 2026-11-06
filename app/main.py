from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from app.gateway import ComintyGateway
from app.models import ApprovalRequest, CreateCaseRequest
from app.pipeline import BudgetExceeded, DossierService

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
REQUIRED_ENV = (
    "COMINTY_API_KEY", "COMINTY_USER_ID", "AGENT_ID_INTAKE",
    "AGENT_ID_VERIFIER", "AGENT_ID_ACTION",
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(gateway=None, repo_root: Path = ROOT, max_runs: int | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        load_dotenv()
        missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
        active_gateway = gateway if gateway is not None else ComintyGateway()
        try:
            if hasattr(active_gateway, "open"):
                await active_gateway.open()
            app.state.service = DossierService(active_gateway, repo_root, max_runs)
            yield
        finally:
            if hasattr(active_gateway, "close"):
                await active_gateway.close()

    app = FastAPI(title="Dossier", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError):
        del _request
        message = exc.errors()[0]["msg"] if exc.errors() else "Invalid request"
        return JSONResponse({"error": f"Invalid request: {message}"}, status_code=400)

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html")

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/api/demo-cases")
    async def demo_cases(request: Request):
        return {"demo_cases": request.app.state.service.demo_cases()}

    @app.post("/api/cases")
    async def create_case(payload: CreateCaseRequest, request: Request):
        service: DossierService = request.app.state.service
        try:
            needed = service.estimate_create_runs(payload.demo_case_id)
        except (ValueError, FileNotFoundError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        try:
            case_id = await service.create_case(payload.demo_case_id, reservation=needed)
            return {"case_id": case_id}
        except BudgetExceeded:
            return JSONResponse({"error": "Run budget exhausted"}, status_code=429)
        except (ValueError, FileNotFoundError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/api/cases/{case_id}")
    async def get_case(case_id: str, request: Request):
        case = request.app.state.service.case_view(case_id)
        if case is None:
            return JSONResponse({"error": "Case not found"}, status_code=404)
        return case

    @app.post("/api/cases/{case_id}/approve")
    async def approve(case_id: str, payload: ApprovalRequest, request: Request):
        if not payload.reviewed:
            return JSONResponse({"error": "Review the findings before approval"}, status_code=400)
        ok, error = await request.app.state.service.approve(case_id)
        if not ok:
            status = 404 if error == "Case not found" else (
                429 if error == "Run budget exhausted" else 409
            )
            return JSONResponse({"error": error}, status_code=status)
        return {"status": "ACTION_RUNNING"}

    @app.post("/api/cases/{case_id}/reject")
    async def reject(case_id: str, request: Request):
        ok, error = await request.app.state.service.reject(case_id)
        if not ok:
            return JSONResponse({"error": error},
                                status_code=404 if error == "Case not found" else 409)
        return {"status": "REJECTED"}

    @app.get("/api/audit")
    async def audit(request: Request):
        return request.app.state.service.audit_view()

    @app.get("/api/eval/latest")
    async def eval_latest():
        path = repo_root / "data" / "eval" / "latest.json"
        if not path.is_file():
            return {"status": "idle"}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return JSONResponse({"error": "Evaluation result could not be read"}, status_code=500)

    return app


app = create_app()
