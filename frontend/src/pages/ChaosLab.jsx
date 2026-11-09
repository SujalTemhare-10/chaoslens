import { useEffect, useRef, useState } from "react";
import { api, streamExperiment } from "../api.js";
import AnalysisView from "../components/AnalysisView.jsx";
import Graph from "../components/Graph.jsx";

export default function ChaosLab({ project }) {
  const [detail, setDetail] = useState(null);
  const [selected, setSelected] = useState([]);
  const [faultType, setFaultType] = useState("stop");
  const [exp, setExp] = useState(null);
  const [events, setEvents] = useState([]);
  const [live, setLive] = useState(null);
  const [campaign, setCampaign] = useState(null);
  const [pairs, setPairs] = useState(false);
  const [error, setError] = useState("");
  const stopStream = useRef(null);

  const load = async () => {
    try { setDetail(await api.project(project)); setError(""); }
    catch (e) { setError(e.message); }
  };

  useEffect(() => { setDetail(null); setExp(null); setEvents([]); setCampaign(null); load(); }, [project]);
  useEffect(() => () => stopStream.current?.(), []);

  // poll a running campaign
  useEffect(() => {
    if (!campaign || campaign.status === "done") return;
    const t = setInterval(async () => setCampaign(await api.campaign(campaign.id)), 2000);
    return () => clearInterval(t);
  }, [campaign]);

  const toggle = (u) => setSelected((s) => (s.includes(u) ? s.filter((x) => x !== u) : [...s, u]));

  const run = async () => {
    setError(""); setEvents([]); setLive(null);
    try {
      const started = await api.runExperiment({ project, faults: selected, fault_type: faultType });
      setExp(started);
      stopStream.current?.();
      stopStream.current = streamExperiment(started.id, (msg) => {
        if (msg.events?.length) setEvents((ev) => [...ev, ...msg.events]);
        if (msg.live) setLive(msg.live);
        if (msg.final) { setExp(msg.final); load(); }
      });
    } catch (e) { setError(e.message); }
  };

  const runCampaign = async () => {
    setError("");
    try { setCampaign(await api.runCampaign({ project, fault_type: faultType, include_pairs: pairs })); }
    catch (e) { setError(e.message); }
  };

  if (error && !detail) return <div className="card error">{error}</div>;
  if (!detail) return <div className="card muted">Loading project…</div>;

  // status for the live graph
  const status = {};
  const observed = live?.services || detail.observed.services;
  for (const [s, up] of Object.entries(observed)) status[s] = up ? "up" : "down";
  const running = exp && !["done", "error"].includes(exp.status);
  if (running && exp.predicted_down) for (const s of exp.predicted_down) if (status[s] === "up") status[s] = "predicted";

  return (
    <div className="stack">
      <div className="grid2">
        <div className="card">
          <h3>Live system: {project}</h3>
          <Graph model={detail.analysis.model} status={status} />
          <p className="muted small">Green = healthy, red = down, orange = predicted to go down.</p>
        </div>
        <div className="card">
          <h3>Inject a fault</h3>
          <div className="units">
            {detail.containers.map((c) => (
              <label key={c.unit} className={`unit ${selected.includes(c.unit) ? "on" : ""}`}>
                <input type="checkbox" checked={selected.includes(c.unit)} onChange={() => toggle(c.unit)} />
                <code>{c.unit}</code>
                <span className="muted small">{c.health || c.status}</span>
              </label>
            ))}
          </div>
          <div className="row">
            <select value={faultType} onChange={(e) => setFaultType(e.target.value)}>
              <option value="stop">Stop container (crash)</option>
              <option value="pause">Pause container (hang)</option>
            </select>
            <button onClick={run} disabled={!selected.length || running}>
              {running ? "Running…" : "Run experiment"}
            </button>
          </div>
          {error && <p className="error">{error}</p>}
          {exp && (
            <div className="log">
              {events.map((e, i) => <div key={i}><span className="muted">{e.t.toFixed(1)}s</span> {e.msg}</div>)}
            </div>
          )}
          {exp?.status === "done" && (
            <div className={`verdict ${exp.matched ? "good" : "bad"}`}>
              {exp.matched ? "✔ Prediction confirmed" : "✘ Prediction mismatch"} — {exp.duration_s}s
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3>Validation campaign</h3>
        <p className="muted small">Runs every single-container fault (optionally every pair) and checks each prediction.</p>
        <div className="row">
          <label><input type="checkbox" checked={pairs} onChange={(e) => setPairs(e.target.checked)} /> include pairs</label>
          <button onClick={runCampaign} disabled={campaign && campaign.status !== "done"}>Run campaign</button>
        </div>
        {campaign && (
          <>
            <div className="progress"><div style={{ width: `${(100 * campaign.done) / campaign.total}%` }} /></div>
            <p>{campaign.done}/{campaign.total} experiments · {campaign.confirmed} predictions confirmed</p>
            {campaign.results?.length > 0 && (
              <table>
                <thead><tr><th>Faults</th><th>Predicted down</th><th>Observed down</th><th>Result</th></tr></thead>
                <tbody>
                  {campaign.results.map((r) => (
                    <tr key={r.id}>
                      <td><code>{r.faults.join(" + ")}</code></td>
                      <td>{r.predicted_down.join(", ") || "—"}</td>
                      <td>{r.status === "done" ? r.observed_down.join(", ") || "—" : r.status}</td>
                      <td>{r.status === "done" && <span className={`pill ${r.matched ? "good" : "bad"}`}>{r.matched ? "match" : "mismatch"}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>

      <AnalysisView analysis={detail.analysis} status={null} />
    </div>
  );
}
