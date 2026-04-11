import React, { useState, useEffect } from "react";
import axios from "axios";
import { getToken } from "../../store/auth";


export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);

  
  const fetchLogs = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const response = await axios.get("http://localhost:8000/api/v1/admin/audit/logs", {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      const data = response.data;
      if (data && Array.isArray(data.logs)) {
        setLogs(data.logs);
      } else if (Array.isArray(data)) {
        setLogs(data);
      } else {
        setLogs([]);
      }
    } catch (err) {
      console.error("Error fetching logs:", err);
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  
  const handleVerifyChain = async () => {
    setVerifying(true);
    setVerificationResult(null);
    try {
      const token = getToken();
      await axios.get("http://localhost:8000/api/v1/admin/audit/verify", {
        headers: { Authorization: `Bearer ${token}` }
      });
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
      const token = getToken();
      const response = await axios.get(`http://localhost:8000/api/v1/admin/users/${userId}/ips`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const ipList = response.data.ips?.map(item => item.ip).join(", ") || "No records found";
      alert(`IP History for ${username || userId}:\n${ipList}`);
    } catch (err) {
      alert("Error fetching IP addresses.");
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

 
  const filtered = Array.isArray(logs) ? logs.filter(log => 
    log.action?.toLowerCase().includes(search.toLowerCase()) ||
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
          placeholder="Search by action, user ID or IP..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="table-card">
        <table className="audit-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>User ID</th>
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
                    <button className="user-link" onClick={() => handleUserIps(log.user_id, log.username)}>
                      {log.username || (log.user_id ? log.user_id.substring(0, 8) : "System")}
                    </button>
                  </td>
                  <td>
                    <span className="tag tag-action">{log.action}</span>
                  </td>
                  <td className="ip-text"><code>{log.ip_address || "N/A"}</code></td>
                  <td>
                    <span className={`tag ${log.result?.toLowerCase() === "success" ? "tag-success" : "tag-error"}`}>
                      {log.result?.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="5" style={{ textAlign: "center", padding: "40px", color: "#a0aec0" }}>
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
