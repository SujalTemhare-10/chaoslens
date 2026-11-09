"""System model: services, their instances (units) and their dependency rules.

A service is UP when
  1. at least one of its own instances (units) is alive, AND
  2. every requirement group is satisfied, where a group is an OR-list of
     services ("api-1|api-2" means: api-1 OR api-2 must be up).

Hard dependencies (compose `depends_on`) become single-member groups.
Fallbacks / load balancing are declared with the label
`chaoslens.requires: "auth,db|cache"`  ->  auth AND (db OR cache).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Service:
    name: str
    replicas: int = 1
    requires: list[list[str]] = field(default_factory=list)  # AND of OR-groups

    def units(self) -> list[str]:
        return [f"{self.name}#{i}" for i in range(1, self.replicas + 1)]


@dataclass
class SystemModel:
    services: dict[str, Service]

    # ---------- helpers ----------
    def units(self) -> list[str]:
        return [u for s in self.services.values() for u in s.units()]

    @staticmethod
    def service_of(unit: str) -> str:
        return unit.split("#", 1)[0]

    def dependents(self, name: str) -> list[str]:
        return [s.name for s in self.services.values()
                if any(name in group for group in s.requires)]

    def entry_services(self) -> list[str]:
        """Services nobody depends on: what end users actually hit."""
        entries = [s for s in self.services if not self.dependents(s)]
        return entries or list(self.services)

    def validate(self) -> None:
        for s in self.services.values():
            for group in s.requires:
                for dep in group:
                    if dep not in self.services:
                        raise ValueError(f"Service '{s.name}' requires unknown service '{dep}'")

    # ---------- core evaluation ----------
    def down_services(self, failed_units: set[str] | frozenset[str]) -> set[str]:
        """Which services are DOWN when exactly `failed_units` have failed.

        Start from every service that still has a live instance, then keep
        removing services whose requirements are not met until nothing
        changes (a fixpoint, so dependency cycles are handled too).
        """
        up = {name for name, s in self.services.items()
              if any(u not in failed_units for u in s.units())}
        changed = True
        while changed:
            changed = False
            for name in list(up):
                for group in self.services[name].requires:
                    if not any(dep in up for dep in group):
                        up.discard(name)
                        changed = True
                        break
        return set(self.services) - up

    def to_dict(self) -> dict:
        return {
            "services": [
                {"name": s.name, "replicas": s.replicas, "requires": s.requires,
                 "units": s.units(), "dependents": self.dependents(s.name)}
                for s in self.services.values()
            ],
            "entry_services": self.entry_services(),
        }


def parse_requires(text: str) -> list[list[str]]:
    """'auth, db|cache'  ->  [['auth'], ['db', 'cache']]"""
    groups = []
    for part in text.split(","):
        alts = [a.strip() for a in part.split("|") if a.strip()]
        if alts:
            groups.append(alts)
    return groups
