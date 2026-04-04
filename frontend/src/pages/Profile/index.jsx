import React from "react";

export default function Profile() {

  // fake user (بعد تربطيه مع Keycloak تبدليه)
  const user = {
    username: "yasmine",
    email: "yasmine@gmail.com",
    role: "researcher"
  };

  // stats تاع user
  const stats = {
    total: 12,
    running: 3,
    completed: 7,
    failed: 2
  };

  return (
    <div>

      <h1>My Profile</h1>

      {/* ===== USER INFO ===== */}
      <div className="card" style={{marginBottom: "20px"}}>
        <h3>User Information</h3>

        <p><strong>Username:</strong> {user.username}</p>
        <p><strong>Email:</strong> {user.email}</p>

        <p>
          <strong>Role:</strong>
          <span className={`role ${user.role}`}>
            {user.role}
          </span>
        </p>
      </div>

      {/* ===== STATS ===== */}
      <div className="grid">

        <div className="card">
          <div className="label">Total Jobs</div>
          <div className="metric-big">{stats.total}</div>
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

    </div>
  );
}
