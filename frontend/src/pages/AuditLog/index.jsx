import React, { useState, useEffect } from "react";
import api from "../../store/api";

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);

  const fetchLogs = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const response = await api.get("/admin/audit/logs");
      const data = response.data;
      setLogs(data.logs || (Array.isArray(data) ? data : []));
    } catch (err) {
      console.error("Audit Fetch Error:", err);
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  const handleVerifyChain = async () => {
    setVerifying(true);
    setVerificationResult(null);
    try {
      await api.get("/admin/audit/verify");
      setVerificationResult({ type: "success", text: "Audit Chain Integrity Verified." });
    } catch (err) {
      setVerificationResult({ type: "error", text: "Security Alert: Log Integrity Compromised!" });
    } finally {
      setVerifying(false);
    }
  };

  const handleUserIps = async (userId, username) => {
    if (!userId) return;
    try {
      const response = await api.get(`/admin/users/${userId}/ips`);
      const ipList = response.data.ips?.map(item => item.ip).join(", ") || "No records found";
      alert(`IP History for ${username || userId}:\n${ipList}`);
    } catch (err) {
      alert("Error fetching IP addresses.");
    }
  };

  useEffect(() => {
    fetchLogs(true);
    const interval = setInterval(() => fetchLogs(false), 30000);
    return () => clearInterval(interval);
  }, []);

  const filtered = Array.isArray(logs) ? logs.filter(log =>
    log.action?.toLowerCase().includes(search.toLowerCase()) ||
    log.username?.toLowerCase().includes(search.toLowerCase()) ||
    log.user_id?.toLowerCase().includes(search.toLowerCase()) ||
    log.ip_address?.includes(search)
  ) : [];

  if (loading) return <div className="audit-container">Loading Security logs...</div>;

  return (
    <div className="audit-container">
      <div className="audit-header">
        <h1 className="audit-title">Security Audit Logs</h1>
        <button className="verify-btn" onClick={handleVerifyChain} disabled={verifying}>
          {verifying ? "Verifying..." : "Verify Audit Integrity"}
        </button>
      </div>

      {verificationResult && (
        <div className={`alert-box ${verificationResult.type}`}>
          {verificationResult.text}
        </div>
      )}

      <div className="search-container">
        <input
          className="audit-search-input"
          type="text"
          placeholder="Search logs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="table-card">
        <table className="audit-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Username</th>
              <th>Action</th>
              <th>IP Address</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length > 0 ? (
              filtered.map((log, index) => (
                <tr key={log.log_id || index}>
                  <td style={{ color: "#718096" }}>
                    {log.timestamp ? new Date(log.timestamp).toLocaleString() : "N/A"}
                  </td>
                  <td>
                    <button
                      className="user-link"
                      onClick={() => handleUserIps(log.user_id, log.username)}
                    >
                      {log.username || "System"}
                    </button>
                  </td>
                  <td>
                    <span className="tag tag-action">{log.action}</span>
                  </td>
                  <td className="ip-text">
                    <code>{log.ip_address || "N/A"}</code>
                  </td>
                  <td>
                    <span className={`tag ${log.result?.toLowerCase() === "success" ? "tag-success" : "tag-error"}`}>
                      {log.result?.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="5" style={{ textAlign: "center", padding: "40px" }}>
                  No audit records found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
