// Dependency graph drawn as layered SVG: entry services on top, leaves at the bottom.
// Solid arrow = hard dependency, dashed arrow = one of several alternatives (OR group).

function layers(services) {
  const byName = Object.fromEntries(services.map((s) => [s.name, s]));
  const depth = {};
  const visit = (name, d, seen) => {
    if (seen.has(name)) return;
    depth[name] = Math.max(depth[name] ?? 0, d);
    const next = new Set(seen).add(name);
    for (const group of byName[name].requires) for (const dep of group) visit(dep, d + 1, next);
  };
  services.filter((s) => s.dependents.length === 0).forEach((s) => visit(s.name, 0, new Set()));
  services.forEach((s) => { if (depth[s.name] === undefined) visit(s.name, 0, new Set()); });
  const rows = [];
  for (const s of services) (rows[depth[s.name]] ||= []).push(s.name);
  return rows.filter(Boolean);
}

export default function Graph({ model, status, highlight = [] }) {
  status = status || {};
  const services = model.services;
  const rows = layers(services);
  const W = 720, rowH = 96, nodeW = 116, nodeH = 40;
  const H = rows.length * rowH + 10;
  const pos = {};
  rows.forEach((row, r) => {
    row.forEach((name, i) => {
      pos[name] = { x: ((i + 1) * W) / (row.length + 1), y: r * rowH + 30 };
    });
  });

  const edges = [];
  for (const s of services) {
    for (const group of s.requires) {
      for (const dep of group) edges.push({ from: s.name, to: dep, alt: group.length > 1 });
    }
  }

  const color = (name) => {
    if (status[name] === "down") return "var(--bad)";
    if (status[name] === "predicted") return "var(--warn)";
    if (highlight.includes(name)) return "var(--warn)";
    if (status[name] === "up") return "var(--good)";
    return "var(--node)";
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="graph" role="img" aria-label="Service dependency graph">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)" />
        </marker>
      </defs>
      {edges.map((e, i) => {
        const a = pos[e.from], b = pos[e.to];
        if (!a || !b) return null;
        return (
          <line key={i} x1={a.x} y1={a.y + nodeH / 2} x2={b.x} y2={b.y - nodeH / 2 - 2}
            stroke="var(--muted)" strokeWidth="1.5" strokeDasharray={e.alt ? "5 4" : "none"}
            markerEnd="url(#arrow)" />
        );
      })}
      {services.map((s) => {
        const p = pos[s.name];
        return (
          <g key={s.name} transform={`translate(${p.x - nodeW / 2}, ${p.y - nodeH / 2})`}>
            <rect width={nodeW} height={nodeH} rx="8" fill="var(--panel2)" stroke={color(s.name)} strokeWidth="2.5" />
            <text x={nodeW / 2} y={nodeH / 2 + 1} textAnchor="middle" dominantBaseline="middle" className="node-label">
              {s.name}{s.replicas > 1 ? ` ×${s.replicas}` : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
