"""Resilience report: uses an LLM if one is configured, otherwise a built-in template.

Any OpenAI-compatible endpoint works (OpenAI, Groq, Gemini's OpenAI-compatible API, Ollama):
    LLM_API_KEY=...  LLM_BASE_URL=https://api.openai.com/v1  LLM_MODEL=gpt-4o-mini
"""
from __future__ import annotations

import json
import os

import httpx


def template_report(analysis: dict, history: list[dict]) -> str:
    lines = ["# ChaosLens Resilience Report", "",
             f"**Resilience score:** {analysis['resilience_score']}/100", ""]
    lines.append("## Findings")
    if not analysis["findings"]:
        lines.append("- No single points of failure found up to the analysis depth.")
    for f in analysis["findings"]:
        lines.append(f"- **[{f['severity'].upper()}] {f['title']}** - {f['detail']}")
    lines += ["", "## Fragility per service"]
    for s in analysis["services"]:
        k = s["min_failures_to_break"]
        k_txt = f"{k}" if k is not None else f">{analysis['depth_limit']}"
        lines.append(f"- `{s['name']}`: breaks after {k_txt} failure(s)"
                     + (f" (e.g. {', '.join(s['example_cut'])})" if s["example_cut"] else ""))
    if history:
        ok = sum(1 for h in history if h["matched"])
        lines += ["", "## Live validation",
                  f"- {ok}/{len(history)} chaos experiments matched the model's prediction."]
        for h in history:
            if not h["matched"]:
                lines.append(f"- Mismatch for faults {h['faults']}: predicted {h['predicted_down']}, "
                             f"observed {h['observed_down']} - the declared dependencies may be incomplete.")
    lines += ["", "## Recommendations"]
    recs = set()
    for f in analysis["findings"]:
        for u in f["units"]:
            svc = u.split("#")[0]
            recs.add(f"- Add a replica or an independent fallback for `{svc}`, and make sure the fallback "
                     f"does not share dependencies with `{svc}`.")
    lines += sorted(recs) or ["- Keep running chaos experiments after every architecture change."]
    return "\n".join(lines)


def generate_report(analysis: dict, history: list[dict]) -> dict:
    base = template_report(analysis, history)
    key = os.environ.get("LLM_API_KEY")
    if not key:
        return {"source": "template", "markdown": base}
    url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    summary = {
        "score": analysis["resilience_score"], "findings": analysis["findings"],
        "services": analysis["services"],
        "experiments": [{k: h[k] for k in ("faults", "predicted_down", "observed_down", "matched")}
                        for h in history[:30]],
    }
    prompt = ("You are an SRE. Write a short markdown resilience report for this microservice system: "
              "explain the top risks in plain words, why they matter, and give concrete fixes "
              "(replicas, fallbacks, circuit breakers, health checks). Use only the data given.\n\n"
              + json.dumps(summary))
    try:
        resp = httpx.post(url, timeout=60, headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}]})
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return {"source": f"llm:{model}", "markdown": text}
    except Exception as exc:  # noqa: BLE001
        return {"source": "template", "markdown": base + f"\n\n_(LLM unavailable: {exc})_"}
