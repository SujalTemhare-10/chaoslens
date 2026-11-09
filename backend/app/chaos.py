"""Talks to the Docker Engine: lists compose projects, injects faults, observes health."""
from __future__ import annotations

import os

import docker
from docker.errors import DockerException, NotFound

PROJECT = "com.docker.compose.project"
SERVICE = "com.docker.compose.service"
NUMBER = "com.docker.compose.container-number"

FAULTS = ("stop", "pause")
# never let ChaosLens inject faults into itself
SELF_PROJECT = os.environ.get("CHAOSLENS_SELF_PROJECT", "chaoslens")


class DockerController:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                self._client = docker.from_env()
                self._client.ping()
            except DockerException as exc:
                self._client = None
                raise RuntimeError(f"Cannot reach Docker: {exc}") from exc
        return self._client

    # ---------- discovery ----------
    def projects(self) -> list[dict]:
        found: dict[str, set] = {}
        for c in self.client.containers.list(all=True, filters={"label": PROJECT}):
            if c.labels[PROJECT] == SELF_PROJECT:
                continue
            found.setdefault(c.labels[PROJECT], set()).add(c.labels.get(SERVICE, "?"))
        return [{"name": p, "services": sorted(s)} for p, s in sorted(found.items())]

    def containers(self, project: str) -> list[dict]:
        if project == SELF_PROJECT:
            return []
        out = []
        for c in self.client.containers.list(all=True, filters={"label": f"{PROJECT}={project}"}):
            service = c.labels.get(SERVICE, c.name)
            number = c.labels.get(NUMBER, "1")
            state = c.attrs.get("State", {})
            out.append({
                "id": c.id,
                "name": c.name,
                "service": service,
                "unit": f"{service}#{number}",
                "status": state.get("Status"),               # running / exited / paused
                "health": (state.get("Health") or {}).get("Status"),  # healthy / unhealthy / starting / None
                "labels": c.labels,
            })
        return sorted(out, key=lambda x: x["unit"])

    # ---------- observation ----------
    @staticmethod
    def unit_alive(c: dict) -> bool:
        if c["status"] != "running":
            return False
        return c["health"] in (None, "healthy")

    def observe(self, project: str) -> dict:
        """Observed state per service: up if at least one instance is alive."""
        services: dict[str, bool] = {}
        units = {}
        for c in self.containers(project):
            alive = self.unit_alive(c)
            units[c["unit"]] = {"status": c["status"], "health": c["health"], "alive": alive}
            services[c["service"]] = services.get(c["service"], False) or alive
        return {"services": services, "units": units}

    # ---------- fault injection ----------
    def _container(self, project: str, unit: str):
        for c in self.containers(project):
            if c["unit"] == unit:
                return self.client.containers.get(c["id"])
        raise NotFound(f"No container for unit {unit} in project {project}")

    def inject(self, project: str, unit: str, fault: str) -> None:
        c = self._container(project, unit)
        if fault == "stop":
            c.stop(timeout=2)
        elif fault == "pause":
            c.pause()
        else:
            raise ValueError(f"Unknown fault '{fault}'")

    def restore(self, project: str, unit: str) -> None:
        c = self._container(project, unit)
        c.reload()
        status = c.attrs["State"]["Status"]
        if status == "paused":
            c.unpause()
        elif status != "running":
            c.start()
