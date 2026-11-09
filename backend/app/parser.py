"""Build a SystemModel from a docker-compose file or from running containers."""
from __future__ import annotations

import yaml

from .model import Service, SystemModel, parse_requires


def _labels(raw) -> dict[str, str]:
    """Compose labels can be a dict or a list of 'key=value' strings."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    out = {}
    for item in raw:
        key, _, value = str(item).partition("=")
        out[key.strip()] = value.strip()
    return out


def _depends_on(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, dict):
        return list(raw.keys())
    return [str(d) for d in raw]


def build_service(name: str, labels: dict[str, str], depends: list[str], replicas: int) -> Service:
    if labels.get("chaoslens.requires"):
        requires = parse_requires(labels["chaoslens.requires"])
    else:
        requires = [[d] for d in depends]
    return Service(name=name, replicas=max(1, replicas), requires=requires)


def parse_compose(text: str) -> SystemModel:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict) or not data["services"]:
        raise ValueError("No 'services' section found in the compose file")

    services: dict[str, Service] = {}
    for name, spec in data["services"].items():
        spec = spec or {}
        deploy = spec.get("deploy") or {}
        replicas = int(deploy.get("replicas") or spec.get("scale") or 1)
        services[name] = build_service(name, _labels(spec.get("labels")),
                                       _depends_on(spec.get("depends_on")), replicas)
    model = SystemModel(services)
    model.validate()
    return model


def model_from_containers(containers: list[dict]) -> SystemModel:
    """Rebuild the model from live containers.

    Compose copies service labels onto each container and records
    depends_on in 'com.docker.compose.depends_on' ("db:service_started:true,...").
    """
    services: dict[str, Service] = {}
    counts: dict[str, int] = {}
    for c in containers:
        counts[c["service"]] = counts.get(c["service"], 0) + 1
    for c in containers:
        name = c["service"]
        if name in services:
            continue
        labels = c["labels"]
        raw = labels.get("com.docker.compose.depends_on", "")
        depends = [d.split(":")[0] for d in raw.split(",") if d.strip()]
        services[name] = build_service(name, labels, depends, counts[name])
    model = SystemModel(services)
    # drop requirements on services that are not part of this project
    for s in model.services.values():
        s.requires = [[d for d in g if d in services] for g in s.requires]
        s.requires = [g for g in s.requires if g]
    return model
