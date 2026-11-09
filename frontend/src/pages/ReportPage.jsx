import { useEffect, useState } from "react";
import { api } from "../api.js";

// Minimal markdown renderer: headings, bullets, bold, inline code.
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    return part;
  });
}

function Markdown({ text }) {
  return (
    <div className="md">
      {text.split("\n").map((line, i) => {
        if (line.startsWith("### ")) return <h4 key={i}>{inline(line.slice(4))}</h4>;
        if (line.startsWith("## ")) return <h3 key={i}>{inline(line.slice(3))}</h3>;
        if (line.startsWith("# ")) return <h2 key={i}>{inline(line.slice(2))}</h2>;
        if (/^\s*[-*] /.test(line)) return <li key={i}>{inline(line.replace(/^\s*[-*] /, ""))}</li>;
        if (!line.trim()) return <br key={i} />;
        return <p key={i}>{inline(line)}</p>;
      })}
    </div>
  );
}

export default function ReportPage({ project }) {
  const [history, setHistory] = useState([]);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setReport(null);
    api.history(project).then(setHistory).catch((e) => setError(e.message));
  }, [project]);

  const generate = async () => {
    setBusy(true); setError("");
    try { setReport(await api.report(project)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const ok = history.filter((h) => h.matched).length;
  return (
    <div className="stack">
      <div className="card">
        <div className="row spread">
          <h3>Resilience report</h3>
          <button onClick={generate} disabled={busy}>{busy ? "Generating…" : "Generate report"}</button>
        </div>
        {error && <p className="error">{error}</p>}
        {report ? (
          <>
            <p className="muted small">Source: {report.source}</p>
            <Markdown text={report.markdown} />
          </>
        ) : <p className="muted">Creates a report from the analysis and every experiment run on this project.</p>}
      </div>
      <div className="card">
        <h3>Experiment history</h3>
        <p>{history.length} experiments · {ok} predictions confirmed</p>
        <table>
          <thead><tr><th>When</th><th>Fault</th><th>Units</th><th>Observed down</th><th>Result</th></tr></thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id}>
                <td className="small">{h.created_at}</td>
                <td>{h.fault_type}</td>
                <td><code>{h.faults.join(" + ")}</code></td>
                <td>{h.observed_down.join(", ") || "—"}</td>
                <td><span className={`pill ${h.matched ? "good" : "bad"}`}>{h.matched ? "match" : "mismatch"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
