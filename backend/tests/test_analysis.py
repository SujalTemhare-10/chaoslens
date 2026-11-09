import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.analyzer import analyze, min_break  # noqa: E402
from app.model import parse_requires  # noqa: E402
from app.parser import parse_compose  # noqa: E402

DEMO = open(os.path.join(os.path.dirname(__file__), "..", "..", "demo", "docker-compose.yml")).read()


def test_parse_requires():
    assert parse_requires("auth, db|cache") == [["auth"], ["db", "cache"]]
    assert parse_requires("") == []


def test_parse_demo():
    m = parse_compose(DEMO)
    assert set(m.services) == {"gateway", "api-1", "api-2", "auth", "db", "cache"}
    assert m.services["api-1"].requires == [["auth"], ["db", "cache"]]
    assert m.services["auth"].requires == [["db"]]     # from depends_on
    assert m.entry_services() == ["gateway"]


def test_down_services():
    m = parse_compose(DEMO)
    assert m.down_services({"cache#1"}) == {"cache"}                         # fallback not needed
    assert m.down_services({"api-1#1"}) == {"api-1"}                          # load balancer covers it
    assert m.down_services({"db#1"}) == {"db", "auth", "api-1", "api-2", "gateway"}  # hidden SPOF
    assert m.down_services({"api-1#1", "api-2#1"}) == {"api-1", "api-2", "gateway"}


def test_rho_and_findings():
    m = parse_compose(DEMO)
    r = analyze(m)
    rho = r["rho"]["gateway"]
    assert rho["db#1"]["rho"] == 0
    assert rho["auth#1"]["rho"] == 0
    assert rho["api-1#1"]["rho"] == 1          # api-2 is the only thing left
    assert rho["cache#1"]["rho"] == 1          # cache down -> db alone kills it (it would anyway)
    titles = " ".join(f["title"] for f in r["findings"])
    assert "Fallback for 'db' in 'api-1' is not independent" in titles
    assert 0 <= r["resilience_score"] <= 100


def test_replicas_add_redundancy():
    m = parse_compose("""
services:
  web: {depends_on: [db]}
  db: {deploy: {replicas: 2}}
""")
    assert m.down_services({"db#1"}) == set()
    assert "web" in m.down_services({"db#1", "db#2"})
    assert min_break(m, "web")[0] == 1      # web itself has a single instance


def test_cycle_is_handled():
    m = parse_compose("""
services:
  a: {depends_on: [b]}
  b: {depends_on: [a]}
""")
    assert m.down_services({"a#1"}) == {"a", "b"}


def test_bad_input():
    with pytest.raises(ValueError):
        parse_compose("hello: world")
    with pytest.raises(ValueError):
        parse_compose("services:\n  a: {depends_on: [ghost]}\n")
