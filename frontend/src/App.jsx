import { useEffect, useState } from "react";
import { api } from "./api.js";
import AnalyzePage from "./pages/AnalyzePage.jsx";
import ChaosLab from "./pages/ChaosLab.jsx";
import ReportPage from "./pages/ReportPage.jsx";

export default function App() {
  const [tab, setTab] = useState("lab");
  const [health, setHealth] = useState(null);
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState("");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }));
    api.projects()
      .then((p) => { setProjects(p); if (p.length) setProject(p[0].name); })
      .catch(() => setProjects([]));
  }, []);

  const needsProject = tab !== "analyze";
  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="logo">◎</span> ChaosLens
          <span className="muted small">predict failures, then prove them</span>
        </div>
        <nav>
          {[["lab", "Chaos Lab"], ["analyze", "Analyze compose"], ["report", "Report & history"]].map(([k, label]) => (
            <button key={k} className={tab === k ? "tab active" : "tab"} onClick={() => setTab(k)}>{label}</button>
          ))}
        </nav>
        <div className="row">
          {needsProject && (
            <select value={project} onChange={(e) => setProject(e.target.value)} disabled={!projects.length}>
              {projects.length ? projects.map((p) => <option key={p.name}>{p.name}</option>) : <option>no projects</option>}
            </select>
          )}
          <span className={`dot ${health?.docker ? "good" : "bad"}`} title="Docker connection" />
        </div>
      </header>
      <main>
        {tab === "analyze" && <AnalyzePage />}
        {needsProject && !project && (
          <div className="card">
            <h3>No running compose project found</h3>
            <p className="muted">Start the demo with <code>docker compose -f demo/docker-compose.yml up -d --build</code> and refresh.</p>
          </div>
        )}
        {tab === "lab" && project && <ChaosLab project={project} />}
        {tab === "report" && project && <ReportPage project={project} />}
      </main>
    </div>
  );
}
