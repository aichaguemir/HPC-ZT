import React, { useState } from "react";
import api from "../../store/api";

export default function MfaModal({ isOpen, onClose, onSuccess }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleVerify = async () => {
    setLoading(true);
    setError("");
    try {
      await api.post("/auth/mfa/verify-code", { code });
      onSuccess();
    } catch (err) {
      setError(err.response?.data?.detail || "Invalid or expired code");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-card">
        <h3>Two‑Factor Authentication Required</h3>
        <p>Enter the 6‑digit code sent to your email.</p>
        <input
          type="text"
          maxLength="6"
          placeholder="123456"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          style={{ width: "100%", padding: "10px", fontSize: "18px", textAlign: "center", letterSpacing: "4px" }}
        />
        {error && <div style={{ color: "#dc2626", marginTop: "8px" }}>{error}</div>}
        <div style={{ marginTop: "20px", display: "flex", justifyContent: "flex-end", gap: "10px" }}>
          <button onClick={onClose}>Cancel</button>
          <button onClick={handleVerify} disabled={loading}>
            {loading ? "Verifying..." : "Verify"}
          </button>
        </div>
      </div>
    </div>
  );
}
