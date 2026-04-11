import React, { useEffect, useState } from "react";
import api from "../../store/api"; // Unified API instance with Silent Refresh
import "./NodeMap.css";

/**
 * NodeMap Component
 * Visualizes the HPC cluster infrastructure.
 * Corrects core counting by only summing Online nodes.
 */
export default function NodeMap() {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  /**
   * Fetches cluster node data from the backend.
   * @param {boolean} isManual - Controls the manual refresh spinner.
   */
  const fetchNodes = async (isManual = false) => {
    try {
      if (isManual) setRefreshing(true);
      
      const res = await api.get("/admin/nodes");
      // Safety: always ensure we have an array
      const nodesData = res.data.nodes || [];
      setNodes(nodesData);
    } catch (err) {
      console.error("Cluster Monitoring Error:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Initial load and auto-refresh every 30 seconds
  useEffect(() => {
    fetchNodes();
    const interval = setInterval(() => fetchNodes(false), 30000);
    return () => clearInterval(interval);
  }, []);

  // --- Logic for Cluster Metrics (Excluding Offline Nodes) ---
  
  // 1. All nodes count
  const totalNodesCount = nodes.length;

  // 2. Filter for Online nodes only (status === "ok")
  const onlineNodesList = nodes.filter(n => n.status === "ok");
  const activeNodesCount = onlineNodesList.length;

  // 3. Total Cores calculation (Summing only Online nodes to reach 368)
  const totalCores = onlineNodesList.reduce((sum, n) => sum + parseInt(n.max_cpus || 0), 0);

  // 4. Active workload
  const totalRunningJobs = onlineNodesList.reduce((sum, n) => sum + parseInt(n.running_jobs || 0), 0);

  // 5. Overall Cluster Utilization
  const clusterUtilization = totalCores > 0 ? ((totalRunningJobs / totalCores) * 100).toFixed(1) : 0;

  if (loading) return <div className="loading-state">Scanning HPC Cluster Nodes...</div>;

  return (
    <div className="node-map-container">
      {/* Header Section */}
      <div className="header-actions" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <div>
          <h1>HPC Cluster Overview</h1>
          <p className="subtext">Live monitoring of compute infrastructure</p>
        </div>
        <button 
          onClick={() => fetchNodes(true)} 
          className={`btn-refresh-pro ${refreshing ? "spinning" : ""}`}
          disabled={refreshing}
        >
          {refreshing ? "Synchronizing..." : "Refresh Status"}
        </button>
      </div>

      {/* Statistics Cards Grid */}
      <div className="grid">
        <div className="card">
          <div className="label">Compute Nodes</div>
          <div className="metric-big">{activeNodesCount} / {totalNodesCount}</div>
          <div className="sub-label">Nodes Online</div>
        </div>
        
        <div className="card">
          <div className="label">Total Cores</div>
          <div className="metric-big">{totalCores}</div>
          <div className="sub-label">Available Capacity</div>
        </div>
        
        <div className="card">
          <div className="label">Active Jobs</div>
          <div className="metric-big">{totalRunningJobs}</div>
          <div className="sub-label">Workload Threads</div>
        </div>
        
        <div className="card">
          <div className="label">Utilization</div>
          <div className="metric-big">{clusterUtilization}%</div>
          <div className="sub-label">Current Usage Rate</div>
        </div>
      </div>

      {/* Individual Node Tiles */}
      <div className="node-grid">
        {nodes.map((node) => (
          <div key={node.host} className={`node-tile ${node.status === "ok" ? "ok" : "unavail"}`}>
            <div className="node-header">
              <strong>{node.host}</strong>
              <div className="status-indicator">
                <span className={`dot ${node.status === "ok" ? "bg-success" : "bg-danger"}`}></span>
                <span className={node.status === "ok" ? "text-success" : "text-danger"}>
                  {node.status === "ok" ? "Online" : "Unavailable"}
                </span>
              </div>
            </div>
            
            <div className="node-details">
              <div className="detail-row">
                <span>Total Cores:</span>
                <span>{node.max_cpus}</span>
              </div>
              <div className="detail-row">
                <span>Active Tasks:</span>
                <span>{node.running_jobs}</span>
              </div>
            </div>

            {/* Visual Load Bar */}
            <div className="usage-section">
              <div className="usage-label">Node Load: {node.utilization}</div>
              <div className="usage-bar-bg">
                <div 
                  className="usage-bar-fill" 
                  style={{ width: node.utilization }}
                ></div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
