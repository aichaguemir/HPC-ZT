
import React, { useState } from "react";

const logsData = [
  { id: 1, user: "yasmine", action: "Submit Job", status: "SUCCESS", time: "10:30" },
  { id: 2, user: "ali", action: "Kill Job", status: "WARNING", time: "10:45" },
  { id: 3, user: "admin", action: "Delete User", status: "ERROR", time: "11:00" },
];

export default function AuditLog() {
  const [search, setSearch] = useState("");

  const filtered = logsData.filter(
    (log) =>
      log.user.toLowerCase().includes(search.toLowerCase()) ||
      log.action.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <h1>Audit Logs</h1>

      {/* SEARCH */}
      <div className="search-box" style={{ marginBottom: "20px" }}>
        <input
          type="text"
          placeholder="Search logs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* TABLE */}
      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>User</th>
              <th>Action</th>
              <th>Status</th>
              <th>Time</th>
            </tr>
          </thead>

          <tbody>
            {filtered.map((log) => (
              <tr key={log.id}>
                <td>{log.user}</td>
                <td>{log.action}</td>
                <td>
                  <span className={`tag ${log.status.toLowerCase()}`}>
                    {log.status}
                  </span>
                </td>
                <td>{log.time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
