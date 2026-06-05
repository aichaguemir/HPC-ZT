import React, { useState, useEffect } from "react";
import api from "../../../store/api";

export default function PendingUsers() {
  const [pendingUsers, setPendingUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [pdfBlobUrl, setPdfBlobUrl] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const fetchPending = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const res = await api.get("/admin/users/pending");
      const data = res.data.pending || (Array.isArray(res.data) ? res.data : []);
      setPendingUsers(data);
    } catch (err) {
      console.error("Fetch error:", err);
      setPendingUsers([]);
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  const handleAction = async (userId, action) => {
    if (action === "reject" && !window.confirm("Are you sure you want to reject this request?")) return;
    try {
      await api.post(`/admin/users/${userId}/${action}`);
      alert(`User request successfully ${action}d.`);
      fetchPending(false);
    } catch (err) {
      console.error(`Error during ${action}:`, err);
      alert(`Could not ${action} user request.`);
    }
  };

  const handleViewDoc = async (user) => {
  if (!user.document_url) return;
  setShowModal(true);
  setPdfLoading(true);
  setPdfBlobUrl(null);
  setSelectedDoc({
    username: user.username,
    role: user.requested_role || "student",
    rawUrl: user.document_url,
  });

  try {
    const res = await fetch(user.document_url, { credentials: "include" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    setPdfBlobUrl(blobUrl);
  } catch (err) {
    console.error("Failed to load PDF:", err);
    setPdfBlobUrl(null);
  } finally {
    setPdfLoading(false);
  }
};

  useEffect(() => {
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    };
  }, [pdfBlobUrl]);

  const handleCloseModal = () => {
    setShowModal(false);
    setSelectedDoc(null);
    if (pdfBlobUrl) {
      URL.revokeObjectURL(pdfBlobUrl);
      setPdfBlobUrl(null);
    }
  };

  useEffect(() => {
    fetchPending(true);
    const interval = setInterval(() => fetchPending(false), 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return (
    <div style={{ padding: 30, color: "#64748b" }}>
      Synchronizing Pending Requests...
    </div>
  );

  const roleColor = (role) => {
    if (role === "researcher") return { background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe" };
    return { background: "#f0fdf4", color: "#16a34a", border: "1px solid #bbf7d0" };
  };

  return (
    <div className="audit-page">
      <h1 className="audit-title">Pending Access Requests</h1>

      <div className="table-card">
        <table className="audit-table">
          <thead>
            <tr>
              <th>User Info</th>
              <th>Email</th>
              <th>Requested Role</th>
              <th>Document</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pendingUsers.length > 0 ? (
              pendingUsers.map((user) => (
                <tr key={user.user_id || user.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: "#0f172a", fontSize: 14 }}>
                      {user.username}
                    </div>
                    <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                      {user.first_name} {user.last_name}
                    </div>
                    <div style={{ fontSize: 10, color: "#cbd5e1", marginTop: 1 }}>
                      ID: {user.user_id || user.id}
                    </div>
                  </td>
                  <td style={{ fontSize: 13, color: "#334155" }}>{user.email}</td>
                  <td>
                    <span style={{
                      display: "inline-block",
                      padding: "4px 12px",
                      borderRadius: 20,
                      fontSize: 12,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      ...roleColor(user.requested_role),
                    }}>
                      {user.requested_role || "student"}
                    </span>
                  </td>
                  <td>
                    <button
                      onClick={() => handleViewDoc(user)}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "6px 14px",
                        borderRadius: 8,
                        border: "1px solid #e2e8f0",
                        background: "#f8fafc",
                        color: "#2563eb",
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: "pointer",
                        transition: "all 0.15s",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = "#eff6ff";
                        e.currentTarget.style.borderColor = "#2563eb";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = "#f8fafc";
                        e.currentTarget.style.borderColor = "#e2e8f0";
                      }}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14"
                        viewBox="0 0 24 24" fill="none" stroke="currentColor"
                        strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                      View PDF
                    </button>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        onClick={() => handleAction(user.user_id || user.id, "approve")}
                        style={{
                          padding: "7px 16px", borderRadius: 8, border: "none",
                          background: "#2563eb", color: "white", fontSize: 13,
                          fontWeight: 600, cursor: "pointer",
                        }}
                        onMouseEnter={(e) => e.currentTarget.style.background = "#1d4ed8"}
                        onMouseLeave={(e) => e.currentTarget.style.background = "#2563eb"}
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleAction(user.user_id || user.id, "reject")}
                        style={{
                          padding: "7px 16px", borderRadius: 8,
                          border: "1px solid #fecaca", background: "#fff5f5",
                          color: "#dc2626", fontSize: 13, fontWeight: 600, cursor: "pointer",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = "#dc2626";
                          e.currentTarget.style.color = "white";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = "#fff5f5";
                          e.currentTarget.style.color = "#dc2626";
                        }}
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="5" style={{ textAlign: "center", padding: "48px", color: "#64748b" }}>
                  All caught up — no pending registration requests.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Document modal ── */}
      {showModal && selectedDoc && (
        <div
          style={{
            position: "fixed", inset: 0,
            background: "rgba(15,23,42,0.7)",
            backdropFilter: "blur(4px)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 9999,
          }}
          onClick={handleCloseModal}
        >
          <div
            style={{
              background: "#fff", borderRadius: 14, width: "90%",
              maxWidth: 860, maxHeight: "90vh",
              display: "flex", flexDirection: "column",
              boxShadow: "0 25px 50px rgba(0,0,0,0.25)", overflow: "hidden",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div style={{
              padding: "16px 24px", borderBottom: "1px solid #e2e8f0",
              display: "flex", justifyContent: "space-between", alignItems: "center",
              background: "#f8fafc",
            }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>
                  Document — {selectedDoc.username}
                </div>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                  {selectedDoc.role === "student" ? "Attestation de scolarité" : "Carte de chercheur"}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {pdfBlobUrl && (
                  <a
                    href={pdfBlobUrl}
                    download={`document-${selectedDoc.username}.pdf`}
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 6,
                      padding: "7px 14px", borderRadius: 8, background: "#eff6ff",
                      color: "#2563eb", fontSize: 13, fontWeight: 600,
                      textDecoration: "none", border: "1px solid #bfdbfe",
                    }}
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14"
                      viewBox="0 0 24 24" fill="none" stroke="currentColor"
                      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download
                  </a>
                )}
                <button
                  onClick={handleCloseModal}
                  style={{
                    width: 32, height: 32, borderRadius: "50%", border: "none",
                    background: "#f1f5f9", color: "#64748b", fontSize: 20,
                    cursor: "pointer", display: "flex", alignItems: "center",
                    justifyContent: "center", fontWeight: 300,
                  }}
                >×</button>
              </div>
            </div>

            {/* Body */}
            <div style={{ flex: 1, overflow: "hidden", background: "#1e293b" }}>
              {pdfLoading ? (
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "center",
                  height: "70vh", color: "#94a3b8", fontSize: 14, gap: 10,
                }}>
                  Loading document...
                </div>
              ) : pdfBlobUrl ? (
                <iframe
                  src={pdfBlobUrl}
                  style={{ width: "100%", height: "70vh", border: "none" }}
                  title="User Document"
                />
              ) : (
                <div style={{
                  display: "flex", flexDirection: "column", alignItems: "center",
                  justifyContent: "center", height: "70vh", gap: 12, color: "#94a3b8",
                }}>
                  <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"
                    viewBox="0 0 24 24" fill="none" stroke="#475569"
                    strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                  <p style={{ fontSize: 14, margin: 0 }}>Failed to load document.</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div style={{
              padding: "14px 24px", borderTop: "1px solid #e2e8f0",
              background: "#f8fafc", display: "flex", justifyContent: "flex-end",
            }}>
              <button
                onClick={handleCloseModal}
                style={{
                  padding: "8px 24px", borderRadius: 8, border: "none",
                  background: "#2563eb", color: "white", fontSize: 13,
                  fontWeight: 600, cursor: "pointer",
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
