import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../../store/auth"; 

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      // 1. عيطي للدالة تاع الـ Login
      const user = await login(username, password);

      // 2. التوجيه (Navigation)
      // ملاحظة: الـ ProtectedRoute في App.jsx هو اللي راح يشوف 
      // إذا يبعثه لـ /mfa-setup (إذا كان جديد) أو للـ Dashboard (/).
      navigate("/");

    } catch (err) {
      // 3. التعامل مع حالة عدم القبول من الأدمين
      if (err.message === "PENDING_APPROVAL") {
        navigate("/pending-approval");
      } else {
        setError(err.message || "Invalid username or password");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>Login</h2>
        
        {error && (
          <p className="error-message" style={{ textAlign: 'center', marginBottom: '15px', color: '#dc2626' }}>
            {error}
          </p>
        )}
        
        <form onSubmit={handleSubmit}>
          <label>Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            style={{ marginBottom: "15px" }}
            required
            placeholder="Enter your username"
          />

          <label>Password</label>
          <div className="password-field" style={{ marginBottom: "20px", position: "relative" }}>
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              style={{ width: "100%" }}
            />
            <span
              className="toggle-eye"
              onClick={() => setShowPassword(!showPassword)}
              style={{
                position: "absolute",
                right: "10px",
                top: "50%",
                transform: "translateY(-50%)",
                cursor: "pointer"
              }}
            >
              {showPassword ? (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
                  <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-5 0-9.27-3.11-11-8a11.07 11.07 0 0 1 4.15-5.82"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="20" height="20">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
              )}
            </span>
          </div>

          <button type="submit" disabled={loading} style={{ width: "100%", padding: "10px" }}>
            {loading ? "Verifying..." : "Login"}
          </button>
        </form>

        <p style={{ marginTop: "15px", textAlign: "center" }}>
          Don't have an account? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  );
}
