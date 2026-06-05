import React, { useState, useEffect } from "react";
import api from "../../store/api";

export default function Profile() {
  const [stats, setStats] = useState({ totalJobs: 0, running: 0, completed: 0, failed: 0 });
  const [userInfo, setUserInfo] = useState({ username: "", email: "", role: "" });
  const [loading, setLoading] = useState(true);

  const fetchProfileAndStats = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const [userRes, jobsRes] = await Promise.all([
        api.get("/auth/me"),
        api.get("/jobs/"),
      ]);

      setUserInfo(userRes.data);

      const jobsList = jobsRes.data.jobs || (Array.isArray(jobsRes.data) ? jobsRes.data : []);

      // hsseb stats men el status li kayn deja f jobs list
      // machi ndir request jdid l kol job — haka nkhaffo el load
      const newStats = { totalJobs: jobsList.length, running: 0, completed: 0, failed: 0 };

      jobsList.forEach((job) => {
        const s = job.status?.toUpperCase();
        if      (s === "RUN"  || s === "RUNNING" || s === "ACTIVE")    newStats.running++;
        else if (s === "DONE" || s === "COMPLETED" || s === "FINISHED") newStats.completed++;
        else if (s === "EXIT" || s === "FAILED")                        newStats.failed++;
      });

      setStats(newStats);
    } catch (err) {
      console.error("Profile Refresh Error:", err);
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfileAndStats(true);
    const interval = setInterval(() => fetchProfileAndStats(false), 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="loading-state">Synchronizing Profile & Stats...</div>;

  const initials = userInfo.username?.charAt(0).toUpperCase() || "?";

  return (
    <div className="profile-container">

      {/* ── Header ── */}
      <header className="page-header" style={{ marginBottom: 24 }}>
        <h1>User Profile</h1>
      </header>

      {/* ── User card ── */}
      <section className="user-info-section" style={{ marginBottom: 32 }}>
        <div className="card profile-main-card">
          <div className="profile-avatar-large">{initials}</div>
          <div className="profile-details">
            <h2>{userInfo.username}</h2>
            <p className="email-text">{userInfo.email}</p>
            <span className={`role-badge ${userInfo.role?.toLowerCase()}`}>
              {userInfo.role}
            </span>
          </div>
        </div>
      </section>

      {/* ── Stats ── */}
      <div className="stats-header" style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>HPC Usage Overview</h3>
        <small style={{ color: "#94a3b8" }}>Auto-updates every 30s</small>
      </div>

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
