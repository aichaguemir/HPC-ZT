import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../../store/api";
import { completeMfa } from "../../store/auth";
export default function MFA() {
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSendCode = async () => {
    setLoading(true);
    setError("");
    try {
      await api.post("/auth/mfa/send-code");
      setMessage("Code sent to your email. Check MailHog at http://localhost:8025");
    } catch (err) {
      setError("Failed to send code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!code.trim()) {
      setError("Please enter the verification code");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.post("/auth/mfa/verify-code", { code });
      completeMfa();
      window.location.href = "/dashboard"
    } catch (err) {
      setError("Invalid or expired code. Please request a new one.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>Verify Your Identity</h2>
        <p style={{ color: "#64748b", fontSize: 14 }}>
          A verification code has been sent to your email.
        </p>

        {message && (
          <div style={{
            padding: "10px",
            background: "#f0fdf4",
            color: "#166534",
            borderRadius: "8px",
            marginBottom: "15px",
            fontSize: 13,
          }}>
            {message}
          </div>
        )}

        {error && (
          <div style={{
            padding: "10px",
            background: "#fef2f2",
            color: "#991b1b",
            borderRadius: "8px",
            marginBottom: "15px",
            fontSize: 13,
          }}>
            {error}
          </div>
        )}

        <button
          onClick={handleSendCode}
          disabled={loading}
          style={{
            width: "100%",
            padding: "10px",
            background: "#2563eb",
            color: "white",
            border: "none",
            borderRadius: "8px",
            fontWeight: "600",
            cursor: "pointer",
            marginBottom: "15px",
          }}
        >
          {loading ? "Sending..." : "Send Code"}
        </button>

        <input
          type="text"
          placeholder="Enter 6-digit code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          style={{
            width: "100%",
            padding: "10px",
            marginBottom: "15px",
            borderRadius: "8px",
            border: "1px solid #d1d5db",
          }}
        />

        <button
          onClick={handleVerify}
          disabled={loading}
          style={{
            width: "100%",
            padding: "10px",
            background: "#16a34a",
            color: "white",
            border: "none",
            borderRadius: "8px",
            fontWeight: "600",
            cursor: "pointer",
          }}
        >
          {loading ? "Verifying..." : "Verify Code"}
        </button>
      </div>
    </div>
  );
}
