import Graph from "./Graph.jsx";

const sevClass = { critical: "bad", high: "warn", medium: "info" };

export function Findings({ findings }) {
  if (!findings.length) return <p className="muted">No weak points found up to the analysis depth.</p>;
  return (
    <ul className="findings">
      {findings.map((f, i) => (
        <li key={i}>
          <span className={`pill ${sevClass[f.severity]}`}>{f.severity}</span>
          <div>
            <strong>{f.title}</strong>
            <p>{f.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function RhoTable({ analysis }) {
  const entries = Object.keys(analysis.rho);
  return (
    <table>
      <thead>
        <tr>
          <th>If this fails…</th>
          <th>Blast radius</th>
          {entries.map((e) => <th key={e}>ρ for {e}</th>)}
        </tr>
      </thead>
      <tbody>
        {analysis.units.map((u) => (
          <tr key={u}>
            <td><code>{u}</code></td>
            <td>{analysis.blast_radius[u].join(", ")}</td>
            {entries.map((e) => {
              const r = analysis.rho[e][u].rho;
              const cls = r === 0 ? "bad" : r === 1 ? "warn" : "good";
              return <td key={e}><span className={`pill ${cls}`}>{r ?? `>${analysis.depth_limit}`}</span></td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function AnalysisView({ analysis, status }) {
  const spofServices = analysis.findings
    .filter((f) => f.severity !== "medium")
    .flatMap((f) => f.units.map((u) => u.split("#")[0]));
  return (
    <div className="stack">
      <div className="grid2">
        <div className="card">
          <h3>Dependency graph</h3>
          <Graph model={analysis.model} status={status} highlight={status ? [] : spofServices} />
          <p className="muted small">Dashed arrows are alternatives (fallback / load balancing). Orange = risky.</p>
        </div>
        <div className="card">
          <div className="score">
            <span className="score-num">{analysis.resilience_score}</span>
            <span className="muted">/100 resilience score</span>
          </div>
          <h3>Findings</h3>
          <Findings findings={analysis.findings} />
        </div>
      </div>
      <div className="card">
        <h3>Recovery independence (ρ)</h3>
        <p className="muted small">
          ρ = extra failures needed to take the service down after this unit fails. 0 = single point of failure.
        </p>
        <RhoTable analysis={analysis} />
      </div>
    </div>
  );
}
