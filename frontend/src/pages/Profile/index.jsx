import React, { useState, useEffect } from "react";
import axios from "axios";
import { getToken } from "../../store/auth";

export default function Profile() {
  const [stats, setStats] = useState({ totalJobs: 0, running: 0, completed: 0, failed: 0 });
  const [userInfo, setUserInfo] = useState({ username: "", email: "", role: "" });
  const [loading, setLoading] = useState(true);

  const fetchProfileAndStats = async () => {
    try {
      setLoading(true);
      const token = getToken();
      const headers = { Authorization: `Bearer ${token}` };

    
      const userRes = await axios.get("http://localhost:8000/api/v1/auth/me", { headers });
      setUserInfo(userRes.data);

    
      const jobsRes = await axios.get("http://localhost:8000/api/v1/jobs/", { headers });
      const jobsList = jobsRes.data.jobs || (Array.isArray(jobsRes.data) ? jobsRes.data : []);

      const statusPromises = jobsList.map(job =>
        axios.get(`http://localhost:8000/api/v1/jobs/${job.job_id}/status`, { headers })
          .catch(() => ({ data: { status: 'UNKNOWN' } }))
      );

      const statuses = await Promise.all(statusPromises);

      const newStats = { totalJobs: jobsList.length, running: 0, completed: 0, failed: 0 };
      statuses.forEach((res) => {
        const s = res.data.status?.toUpperCase();
        if (s === "RUN" || s === "RUNNING" || s === "ACTIVE") newStats.running++;
        else if (s === "DONE" || s === "COMPLETED" || s === "FINISHED") newStats.completed++;
        else if (s === "EXIT" || s === "FAILED") newStats.failed++;
      });

      setStats(newStats);
    } catch (err) {
      console.error("Profile Logic Error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfileAndStats();
  }, []);

  if (loading) return <div className="loading-state">Loading Profile...</div>;

  return (
    <div className="profile-container">
      <header className="page-header">
        <h1>User Profile</h1>
      </header>

    
      <section className="user-info-section">
        <div className="card profile-main-card">
          <div className="profile-avatar-large">
            {userInfo.username?.charAt(0).toUpperCase()}
          </div>
          <div className="profile-details">
            <h2>{userInfo.username}</h2>
            <p className="email-text">{userInfo.email}</p>
            <span className={`role-badge ${userInfo.role?.toLowerCase()}`}>
              {userInfo.role}
            </span>
          </div>
        </div>
      </section>

      <h3>Usage Overview</h3>
      
      
      <div className="grid">
        <div className="card stat-card">
          <div className="label">Total Submissions</div>
          <div className="metric-big">{stats.totalJobs}</div>
        </div>
        
        <div className="card stat-card warning">
          <div className="label">In Progress</div>
          <div className="metric-big">{stats.running}</div>
        </div>

        <div className="card stat-card success">
          <div className="label">Successful</div>
          <div className="metric-big">{stats.completed}</div>
        </div>

        <div className="card stat-card danger">
          <div className="label">Failed</div>
          <div className="metric-big">{stats.failed}</div>
        </div>
      </div>
    </div>
  );
}
