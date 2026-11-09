import { useState } from "react";
import { api } from "../api.js";
import AnalysisView from "../components/AnalysisView.jsx";

const SAMPLE = `services:
  gateway:
    labels: { chaoslens.requires: "api-1|api-2" }
  api-1:
    labels: { chaoslens.requires: "auth,db|cache" }
  api-2:
    labels: { chaoslens.requires: "auth,db|cache" }
  auth:
    depends_on: [db]
  db: {}
  cache: {}
`;

export default function AnalyzePage() {
  const [text, setText] = useState(SAMPLE);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true); setError("");
    try { setAnalysis(await api.analyze(text)); }
    catch (e) { setError(e.message); setAnalysis(null); }
    finally { setBusy(false); }
  };

  const onFile = async (e) => {
    const file = e.target.files[0];
    if (file) setText(await file.text());
  };

  return (
    <div className="stack">
      <div className="card">
        <h3>Analyze a docker-compose file</h3>
        <p className="muted small">
          Uses <code>depends_on</code> as hard dependencies. Declare alternatives with the label{" "}
          <code>chaoslens.requires: "auth,db|cache"</code> (auth AND (db OR cache)). Replicas count as redundancy.
        </p>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={14} spellCheck={false} />
        <div className="row">
          <button onClick={run} disabled={busy}>{busy ? "Analyzing…" : "Analyze"}</button>
          <label className="file">Upload file<input type="file" accept=".yml,.yaml" onChange={onFile} /></label>
          {error && <span className="error">{error}</span>}
        </div>
      </div>
      {analysis && <AnalysisView analysis={analysis} />}
    </div>
  );
}
