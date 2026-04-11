import React, { useState, useEffect } from "react";
import api from "../../store/api"; 


/**
 * Profile Component with Automatic Refresh
 * Displays user info and live HPC job statistics.
 */
export default function Profile() {
  const [stats, setStats] = useState({ totalJobs: 0, running: 0, completed: 0, failed: 0 });
  const [userInfo, setUserInfo] = useState({ username: "", email: "", role: "" });
  const [loading, setLoading] = useState(true);

  /**
   * Main function to fetch user data and calculate job statistics.
   * @param {boolean} isInitial - If true, displays the loading spinner.
   */
  const fetchProfileAndStats = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      // 1. Fetch user identity (No need for refresh on this one usually, but we keep it sync)
      const userRes = await api.get("/auth/me");
      setUserInfo(userRes.data);

      // 2. Fetch all jobs for stats calculation
      const jobsRes = await api.get("/jobs/");
      const jobsList = jobsRes.data.jobs || (Array.isArray(jobsRes.data) ? jobsRes.data : []);

      // 3. Fetch statuses in parallel for better performance
      const statusPromises = jobsList.map(job =>
        api.get(`/jobs/${job.job_id}/status`)
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
      console.error("Profile Refresh Error:", err);
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  useEffect(() => {
    // Initial data fetch
    fetchProfileAndStats(true);

    // Set up interval for automatic background refresh (every 30 seconds)
    const interval = setInterval(() => {
      fetchProfileAndStats(false);
    }, 30000);

    // Cleanup interval on component unmount
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="loading-state">Synchronizing Profile & Stats...</div>;

  return (
    <div className="profile-container">
      <header className="page-header">
        <h1>User Profile</h1>
      </header>

      <section className="user-info-section">
        <div className="card profile-main-card">
          <div className="profile-avatar-large">
            {userInfo.username?.charAt(0).toUpperCase() || "?"}
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

      <div className="stats-header">
        <h3>HPC Usage Overview</h3>
        <small style={{ color: '#94a3b8' }}>(Auto-updates every 30s)</small>
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
