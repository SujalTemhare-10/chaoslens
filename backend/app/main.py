"""ChaosLens API."""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .analyzer import analyze
from .chaos import FAULTS, DockerController
from .experiments import CAMPAIGNS, EXPERIMENTS, RUN_LOCK, public, start_campaign, start_experiment
from .parser import model_from_containers, parse_compose
from .report import generate_report

app = FastAPI(title="ChaosLens", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
ctl = DockerController()
db.init()


class AnalyzeIn(BaseModel):
    compose: str = Field(..., min_length=1)


class ExperimentIn(BaseModel):
    project: str
    faults: list[str] = Field(..., min_length=1)
    fault_type: str = "stop"


class CampaignIn(BaseModel):
    project: str
    fault_type: str = "stop"
    include_pairs: bool = False


def _docker():
    try:
        return ctl.client
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/health")
def health():
    try:
        ctl.client
        docker_ok = True
    except RuntimeError:
        docker_ok = False
    return {"ok": True, "docker": docker_ok, "busy": RUN_LOCK.locked()}


@app.post("/api/analyze")
def analyze_compose(body: AnalyzeIn):
    try:
        model = parse_compose(body.compose)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return analyze(model)


@app.get("/api/projects")
def projects():
    _docker()
    return ctl.projects()


@app.get("/api/projects/{project}")
def project_detail(project: str):
    _docker()
    containers = ctl.containers(project)
    if not containers:
        raise HTTPException(404, f"No containers found for project '{project}'")
    model = model_from_containers(containers)
    return {
        "project": project,
        "analysis": analyze(model),
        "observed": ctl.observe(project),
        "containers": [{k: c[k] for k in ("name", "service", "unit", "status", "health")} for c in containers],
    }


@app.post("/api/experiments")
def create_experiment(body: ExperimentIn):
    if body.fault_type not in FAULTS:
        raise HTTPException(400, f"fault_type must be one of {FAULTS}")
    _docker()
    units = {c["unit"] for c in ctl.containers(body.project)}
    unknown = [f for f in body.faults if f not in units]
    if unknown:
        raise HTTPException(400, f"Unknown units: {unknown}")
    return public(start_experiment(body.project, body.faults, body.fault_type))


@app.get("/api/experiments")
def list_experiments(project: str | None = None):
    return db.history(project)


@app.get("/api/experiments/{exp_id}")
def get_experiment(exp_id: str):
    if exp_id not in EXPERIMENTS:
        raise HTTPException(404, "Experiment not found")
    return public(EXPERIMENTS[exp_id])


@app.websocket("/api/experiments/{exp_id}/stream")
async def stream_experiment(ws: WebSocket, exp_id: str):
    """Pushes new log events and live state until the experiment ends."""
    await ws.accept()
    sent = 0
    try:
        while True:
            exp = EXPERIMENTS.get(exp_id)
            if not exp:
                await ws.send_json({"error": "not found"})
                break
            events = exp["events"][sent:]
            sent += len(events)
            await ws.send_json({"events": events, "status": exp["status"], "live": exp.get("live")})
            if exp["status"] in ("done", "error") and sent == len(exp["events"]):
                await ws.send_json({"final": public(exp)})
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
    await ws.close()


@app.post("/api/campaigns")
def create_campaign(body: CampaignIn):
    if body.fault_type not in FAULTS:
        raise HTTPException(400, f"fault_type must be one of {FAULTS}")
    _docker()
    return start_campaign(body.project, body.fault_type, body.include_pairs)


@app.get("/api/campaigns/{camp_id}")
def get_campaign(camp_id: str):
    if camp_id not in CAMPAIGNS:
        raise HTTPException(404, "Campaign not found")
    camp = CAMPAIGNS[camp_id]
    exps = [public(EXPERIMENTS[e]) for e in camp["experiments"] if e in EXPERIMENTS]
    return {**camp, "results": [{k: e[k] for k in ("id", "faults", "status", "predicted_down",
                                                     "observed_down", "matched")} for e in exps]}


@app.get("/api/projects/{project}/report")
def report(project: str):
    _docker()
    containers = ctl.containers(project)
    if not containers:
        raise HTTPException(404, f"No containers found for project '{project}'")
    analysis = analyze(model_from_containers(containers))
    return generate_report(analysis, db.history(project))


# ---- serve the built dashboard (frontend/dist copied to ./static) ----
STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(STATIC):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC, "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return FileResponse(os.path.join(STATIC, "index.html"))
