"""Experiment runner: predict -> inject -> observe -> compare -> restore.

Runs in a background thread. Only one experiment touches Docker at a time
(RUN_LOCK), so faults from two experiments never overlap.
"""
from __future__ import annotations

import itertools
import threading
import time
import uuid

from . import db
from .chaos import DockerController
from .parser import model_from_containers

RUN_LOCK = threading.Lock()
EXPERIMENTS: dict[str, dict] = {}
CAMPAIGNS: dict[str, dict] = {}

POLL_S = 1.0
SETTLE_MIN_S = 8.0      # give health checks time to notice the fault
STABLE_POLLS = 5        # state must stay identical this many polls in a row
OBSERVE_TIMEOUT_S = 45.0
RESTORE_TIMEOUT_S = 60.0


def _log(exp: dict, msg: str, **data) -> None:
    exp["events"].append({"t": round(time.time() - exp["started"], 2), "msg": msg, **data})


def wait_all_up(ctl: DockerController, project: str, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        obs = ctl.observe(project)
        if obs["services"] and all(obs["services"].values()):
            return True
        time.sleep(POLL_S)
    return False


def _run(exp: dict, ctl: DockerController) -> None:
    project, faults, fault_type = exp["project"], exp["faults"], exp["fault_type"]
    try:
        exp["status"] = "running"
        model = model_from_containers(ctl.containers(project))
        predicted = sorted(model.down_services(set(faults)))
        exp["predicted_down"] = predicted
        _log(exp, f"Predicted down: {predicted or 'nothing'}")

        _log(exp, "Checking baseline (all services healthy)...")
        if not wait_all_up(ctl, project, RESTORE_TIMEOUT_S):
            raise RuntimeError("System is not healthy before the experiment; aborting")

        for unit in faults:
            ctl.inject(project, unit, fault_type)
            _log(exp, f"Injected '{fault_type}' into {unit}")

        # observe until the state is stable
        history, start = [], time.time()
        while True:
            obs = ctl.observe(project)
            down = sorted(s for s, up in obs["services"].items() if not up)
            history.append(down)
            exp["live"] = obs
            elapsed = time.time() - start
            stable = len(history) >= STABLE_POLLS and all(h == down for h in history[-STABLE_POLLS:])
            if (elapsed >= SETTLE_MIN_S and stable) or elapsed >= OBSERVE_TIMEOUT_S:
                break
            time.sleep(POLL_S)

        exp["observed_down"] = down
        exp["matched"] = set(down) == set(predicted)
        services = sorted(model.services)
        exp["comparison"] = [{"service": s, "predicted_down": s in predicted, "observed_down": s in down}
                             for s in services]
        _log(exp, f"Observed down: {down or 'nothing'}  ->  "
                  f"{'prediction CONFIRMED' if exp['matched'] else 'prediction MISMATCH'}")
    except Exception as exc:  # noqa: BLE001 - surface any failure to the user
        exp["status"] = "error"
        exp["error"] = str(exc)
        _log(exp, f"Error: {exc}")
    finally:
        _log(exp, "Restoring faulted containers...")
        for unit in exp["faults"]:
            try:
                ctl.restore(project, unit)
            except Exception:  # noqa: BLE001
                pass
        recovered = wait_all_up(ctl, project, RESTORE_TIMEOUT_S)
        _log(exp, "System recovered" if recovered else "Warning: system did not fully recover in time")
        exp["duration_s"] = round(time.time() - exp["started"], 1)
        if exp["status"] != "error":
            exp["status"] = "done"
            db.save(exp)


def new_experiment(project: str, faults: list[str], fault_type: str, campaign_id: str | None = None) -> dict:
    exp = {
        "id": uuid.uuid4().hex[:10], "project": project, "faults": faults, "fault_type": fault_type,
        "campaign_id": campaign_id, "status": "queued", "events": [], "started": time.time(),
        "predicted_down": [], "observed_down": [], "matched": False, "comparison": [], "duration_s": 0,
    }
    EXPERIMENTS[exp["id"]] = exp
    return exp


def start_experiment(project: str, faults: list[str], fault_type: str) -> dict:
    exp = new_experiment(project, faults, fault_type)
    ctl = DockerController()

    def job():
        with RUN_LOCK:
            exp["started"] = time.time()
            _run(exp, ctl)

    threading.Thread(target=job, daemon=True).start()
    return exp


def start_campaign(project: str, fault_type: str, include_pairs: bool) -> dict:
    """Run every single-unit fault (and optionally every pair) and score the predictions."""
    ctl = DockerController()
    units = [c["unit"] for c in ctl.containers(project)]
    plans = [[u] for u in units]
    if include_pairs:
        plans += [list(p) for p in itertools.combinations(units, 2)]
    camp = {"id": uuid.uuid4().hex[:10], "project": project, "fault_type": fault_type,
            "status": "running", "total": len(plans), "done": 0, "confirmed": 0, "experiments": []}
    CAMPAIGNS[camp["id"]] = camp

    def job():
        with RUN_LOCK:
            for faults in plans:
                exp = new_experiment(project, faults, fault_type, campaign_id=camp["id"])
                camp["experiments"].append(exp["id"])
                _run(exp, ctl)
                camp["done"] += 1
                camp["confirmed"] += int(exp["status"] == "done" and exp["matched"])
            camp["status"] = "done"

    threading.Thread(target=job, daemon=True).start()
    return camp


def public(exp: dict) -> dict:
    return {k: v for k, v in exp.items() if k != "started"}
