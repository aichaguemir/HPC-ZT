import React, { useState, useEffect } from "react";
import axios from "axios";
import { getToken } from "../../store/auth";

export default function Dashboard() {
  const [stats, setStats] = useState({ totalJobs: 0, running: 0, completed: 0, failed: 0 });
  const [recentJobs, setRecentJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  const mapStatus = (status) => {
    const s = status?.toUpperCase() || "UNKNOWN";
    if (s === "RUN" || s === "RUNNING" || s === "ACTIVE") return "running";
    if (s === "DONE" || s === "COMPLETED" || s === "FINISHED") return "completed";
    if (s === "EXIT" || s === "FAILED") return "failed";
    if (s === "PEND" || s === "PENDING") return "pending";
    return "unknown";
  };

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const token = getToken();
      
   
      const jobsRes = await axios.get("http://localhost:8000/api/v1/jobs/", {
        headers: { Authorization: `Bearer ${token}` }
      });

      const jobsList = jobsRes.data.jobs || (Array.isArray(jobsRes.data) ? jobsRes.data : []);
      
     
      const statusPromises = jobsList.map(job => 
        axios.get(`http://localhost:8000/api/v1/jobs/${job.job_id}/status`, {
          headers: { Authorization: `Bearer ${token}` }
        }).catch(() => ({ data: { status: 'UNKNOWN' } })) 
      );

      const statuses = await Promise.all(statusPromises);

    
      const newStats = { totalJobs: jobsList.length, running: 0, completed: 0, failed: 0 };
      
      statuses.forEach((res, index) => {
        const s = res.data.status?.toUpperCase();
        if (s === "RUN" || s === "RUNNING") newStats.running++;
        else if (s === "DONE" || s === "COMPLETED") newStats.completed++;
        else if (s === "EXIT" || s === "FAILED") newStats.failed++;
        
       
        jobsList[index].status = res.data.status;
      });

      setStats(newStats);
      setRecentJobs(jobsList.slice(0, 5)); 

    } catch (err) {
      console.error("Dashboard Fetch Error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  if (loading) return <div className="loading-state">Loading Dashboard...</div>;

  return (
    <div className="dashboard-wrapper">
      <h1>My Dashboard</h1>

      <div className="grid">
        <div className="card"><div className="label">Total Jobs</div><div className="metric-big">{stats.totalJobs}</div></div>
        <div className="card"><div className="label">Running</div><div className="metric-big" style={{ color: "#d97706" }}>{stats.running}</div></div>
        <div className="card"><div className="label">Completed</div><div className="metric-big" style={{ color: "#16a34a" }}>{stats.completed}</div></div>
        <div className="card"><div className="label">Failed</div><div className="metric-big" style={{ color: "#dc2626" }}>{stats.failed}</div></div>
      </div>

      <div className="table-container" style={{ marginTop: "40px" }}>
        <h3>Recent Activity</h3>
        <table className="table">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Status</th>
              <th>Name</th>
            </tr>
          </thead>
          <tbody>
            {recentJobs.map((job) => (
              <tr key={job.job_id}>
                <td>#{job.job_id}</td>
                <td><span className={`status ${mapStatus(job.status)}`}>{job.status}</span></td>
                <td>{job.name || "N/A"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
