import React, { useEffect, useState } from "react";
import axios from "axios";
import { getToken } from "../../store/auth"; 
import "./NodeMap.css";

export default function NodeMap() {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);

  
  const fetchNodes = async () => {
    try {
      const token = getToken();
      const res = await axios.get("http://localhost:8000/api/v1/admin/nodes", {
        headers: { Authorization: `Bearer ${token}` }
      });
      
  
      setNodes(res.data.nodes || []);
    } catch (err) {
      console.error("Error fetching nodes:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
   
    const interval = setInterval(fetchNodes, 30000);
    return () => clearInterval(interval);
  }, []);

  
  const totalNodes = nodes.length;
  const activeNodes = nodes.filter(n => n.status === "ok").length;
  const totalCores = nodes.reduce((sum, n) => sum + parseInt(n.max || 0), 0);
  const totalRunningJobs = nodes.reduce((sum, n) => sum + parseInt(n.running || 0), 0);

  if (loading) return <div className="loading-state">Scanning HPC Cluster...</div>;

  return (
    <div className="node-map-container">
      <h1>HPC Cluster Overview</h1>

      {/* ===== STATS (Dynamic Now!) ===== */}
      <div className="grid">
        <div className="card">
          <div className="label">Compute Nodes</div>
          <div className="metric-big">{activeNodes} / {totalNodes}</div>
          <div className="sub-label">Nodes Online</div>
        </div>

        <div className="card">
          <div className="label">Total Cores</div>
          <div className="metric-big">{totalCores}</div>
          <div className="sub-label">Available Across Cluster</div>
        </div>

        <div className="card">
          <div className="label">Active Jobs</div>
          <div className="metric-big">{totalRunningJobs}</div>
          <div className="sub-label">Currently Running</div>
        </div>

        <div className="card">
          <div className="label">Resource Utilization</div>
          <div className="metric-big">
            {totalCores > 0 ? ((totalRunningJobs / totalCores) * 100).toFixed(1) : 0}%
          </div>
          <div className="sub-label">Core Usage Rate</div>
        </div>
      </div>

      {/* ===== NODE GRID ===== */}
      <div className="node-grid">
        {nodes.map((node) => (
          <div
            key={node.host}
            className={`node-tile ${node.status === "ok" ? "ok" : "unavail"}`}
          >
            <strong>{node.host}</strong>

            <div className="status-indicator">
              <span className={`dot ${node.status === "ok" ? "bg-success" : "bg-danger"}`}></span>
              <span style={{ color: node.status === "ok" ? "var(--success)" : "var(--danger)" }}>
                {node.status}
              </span>
            </div>

            <div className="node-details">
              <p>Cores: {node.max}</p>
              <p>Running: {node.running}</p>
            </div>
            
            {/* ProgressBar بسيط يوضح استهلاك الـ Cores في كل Node */}
            <div className="usage-bar-bg">
              <div 
                className="usage-bar-fill" 
                style={{ width: `${(node.running / node.max) * 100}%` }}
              ></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

