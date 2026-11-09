"""Resilience analysis.

Key idea (recovery independence degree, rho):
    rho(S, f) = the minimum number of ADDITIONAL unit failures needed to take
                service S down, given that unit f has already failed.

    rho = 0  -> f alone kills S            (single point of failure)
    rho = 1  -> one more failure kills S   (S's recovery depends on one thing)
    higher   -> S's recovery mechanisms are more independent of f

We find it by trying failure sets of growing size (0, 1, 2, ...), which is
exact and fast for systems of compose size (tens of containers).
"""
from __future__ import annotations

from itertools import combinations

from .model import SystemModel

MAX_DEPTH = 3


def min_break(model: SystemModel, target: str, given: frozenset[str] = frozenset(),
              limit: int = MAX_DEPTH) -> tuple[int | None, list[str]]:
    """Smallest extra failure set (beyond `given`) that takes `target` down.

    Returns (size, example_set) or (None, []) if nothing up to `limit` works.
    """
    candidates = [u for u in model.units() if u not in given]
    for k in range(0, limit + 1):
        for extra in combinations(candidates, k):
            if target in model.down_services(given | set(extra)):
                return k, list(extra)
    return None, []


def analyze(model: SystemModel) -> dict:
    units = model.units()
    limit = MAX_DEPTH if len(units) <= 40 else 2

    # 1. Blast radius: what goes down when one unit fails alone
    blast = {u: sorted(model.down_services({u})) for u in units}

    # 2. Per service: how many failures it takes to break it + its SPOFs
    services = []
    for name, svc in model.services.items():
        k, cut = min_break(model, name, limit=limit)
        external_spofs = [u for u in units
                          if model.service_of(u) != name and name in blast[u]]
        services.append({
            "name": name,
            "replicas": svc.replicas,
            "requires": svc.requires,
            "min_failures_to_break": k,
            "example_cut": cut,
            "external_spofs": external_spofs,
        })

    # 3. Recovery independence degree for the entry services
    rho = {}
    for entry in model.entry_services():
        rho[entry] = {}
        for u in units:
            k, cut = min_break(model, entry, frozenset({u}), limit=limit)
            rho[entry][u] = {"rho": k, "extra_failures": cut}

    findings = _findings(model, blast, services, rho)
    score = _score(model, services, rho)
    return {
        "model": model.to_dict(),
        "units": units,
        "blast_radius": blast,
        "services": services,
        "rho": rho,
        "findings": findings,
        "resilience_score": score,
        "depth_limit": limit,
    }


def _findings(model, blast, services, rho) -> list[dict]:
    out = []
    by_name = {s["name"]: s for s in services}

    # Hidden SPOFs: a fallback exists on paper, yet one failure still kills the service
    for name, svc in model.services.items():
        for group in svc.requires:
            if len(group) < 2:
                continue
            for dep in group:
                killers = [u for u in by_name[name]["external_spofs"]
                           if model.service_of(u) == dep]
                for u in killers:
                    out.append({
                        "severity": "critical",
                        "title": f"Fallback for '{dep}' in '{name}' is not independent",
                        "detail": (f"'{name}' lists {' | '.join(group)} as alternatives, but the failure of "
                                   f"{u} alone still takes '{name}' down through another dependency path. "
                                   "The recovery mechanism shares a failure point with what it protects."),
                        "units": [u],
                    })

    # Plain SPOFs for entry services
    for entry in model.entry_services():
        for u, info in rho[entry].items():
            if info["rho"] == 0 and model.service_of(u) != entry:
                if any(u in f["units"] for f in out):
                    continue
                out.append({
                    "severity": "high",
                    "title": f"{u} is a single point of failure for '{entry}'",
                    "detail": f"If {u} fails, these services go down: {', '.join(blast[u])}.",
                    "units": [u],
                })

    # Fragile recovery: one extra failure is enough after any single failure
    for entry in model.entry_services():
        fragile = [u for u, info in rho[entry].items() if info["rho"] == 1]
        if fragile:
            out.append({
                "severity": "medium",
                "title": f"'{entry}' has thin redundancy",
                "detail": (f"After any one of {', '.join(fragile)} fails, a single additional failure "
                           f"takes '{entry}' down."),
                "units": fragile,
            })
    return out


def _score(model, services, rho) -> int:
    """0-100. Rewards units whose failure leaves entry services standing."""
    total, safe = 0, 0
    for entry, row in rho.items():
        for u, info in row.items():
            if model.service_of(u) == entry:
                continue
            total += 1
            r = info["rho"]
            safe += 1.0 if r is None else min(r, 3) / 3
    return round(100 * safe / total) if total else 100
