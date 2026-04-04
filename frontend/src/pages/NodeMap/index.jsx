import React, { useEffect, useState } from "react";
import "./NodeMap.css";

export default function NodeMap() {
  const [nodes, setNodes] = useState([]);

  // Fake data (من الصورة)
  useEffect(() => {
    const data = [
      { name: "compute000", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute001", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute002", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute003", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute004", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute005", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute006", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute007", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute008", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute009", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute010", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute011", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute012", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute013", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute014", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute015", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute016", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute017", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute018", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute019", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute020", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute021", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute022", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute023", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute024", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute025", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute026", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute027", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute028", status: "ok", maxCores: 16, njobs: 0 },
    { name: "compute029", status: "unavail", maxCores: 1, njobs: 0 },
    { name: "compute030", status: "ok", maxCores: 16, njobs: 0 },
    { name: "hpcadmin1", status: "ok", maxCores: 16, njobs: 0 },
    { name: "hpcadmin2", status: "ok", maxCores: 16, njobs: 0 }
    ];

    setNodes(data);
  }, []);

  return (
    <div className="node-map-container">

      <h1>HPC Cluster Overview</h1>

      {/* ===== STATS ===== */}
      <div className="grid">

        <div className="card">
          <div className="label">Compute Nodes</div>
          <div className="metric-big">22 / 33</div>
        </div>

        <div className="card">
          <div className="label">Total Cores</div>
          <div className="metric-big">352</div>
        </div>

        <div className="card">
          <div className="label">RAM per Node</div>
          <div className="metric-big">18 GB</div>
        </div>

        <div className="card">
          <div className="label">Network</div>
          <div className="metric-big">Gigabit</div>
        </div>

      </div>

      {/* ===== NODE GRID ===== */}
      <div className="node-grid">
        {nodes.map((node) => (
          <div
            key={node.name}
            className={`node-tile ${node.status}`}
            title={`Name: ${node.name} | Status: ${node.status} | Cores: ${node.maxCores} | Jobs: ${node.njobs}`}
          >
            <strong>{node.name}</strong>

            <p style={{color: node.status === "ok" ? "var(--success)" : "var(--danger)"}}>
              ● {node.status}
            </p>

            <p>Cores: {node.maxCores}</p>
            <p>Jobs: {node.njobs}</p>
          </div>
        ))}
      </div>

    </div>
  );
}
