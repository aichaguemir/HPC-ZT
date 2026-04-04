import React from "react";

export default function Dashboard() {

  // fake user stats
  const stats = {
    totalJobs: 12,
    running: 3,
    completed: 7,
    failed: 2
  };

  // fake recent jobs
  const jobs = [
    { id: 101, name: "ML Training", status: "RUNNING" },
    { id: 102, name: "MPI Simulation", status: "COMPLETED" },
    { id: 103, name: "Data Analysis", status: "FAILED" },
    { id: 104, name: "Test Job", status: "RUNNING" },
    { id: 105, name: "AI Model", status: "COMPLETED" }
  ];

  return (
    <div>
      <h1>My Dashboard</h1>

      {/* ===== STATS ===== */}
      <div className="grid">

        <div className="card">
          <div className="label">Total Jobs</div>
          <div className="metric-big">{stats.totalJobs}</div>
        </div>

        <div className="card">
          <div className="label">Running</div>
          <div className="metric-big" style={{color: "var(--warning)"}}>
            {stats.running}
          </div>
        </div>

        <div className="card">
          <div className="label">Completed</div>
          <div className="metric-big" style={{color: "var(--success)"}}>
            {stats.completed}
          </div>
        </div>

        <div className="card">
          <div className="label">Failed</div>
          <div className="metric-big" style={{color: "var(--danger)"}}>
            {stats.failed}
          </div>
        </div>

      </div>

      {/* ===== RECENT JOBS ===== */}
      <div className="table-container" style={{marginTop: "30px"}}>
        <h3>Recent Jobs</h3>

        <table className="table">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Name</th>
              <th>Status</th>
            </tr>
          </thead>

          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{job.id}</td>
                <td>{job.name}</td>
                <td>
                  <span className={`status ${job.status.toLowerCase()}`}>
                    {job.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </div>
  );
}
