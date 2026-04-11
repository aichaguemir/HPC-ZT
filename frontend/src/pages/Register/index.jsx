import React, { useState } from "react";
import axios from "axios";
import { useNavigate, Link } from "react-router-dom";

export default function Register() {
  const navigate = useNavigate();
  
  const [form, setForm] = useState({
    username: "",
    firstName: "",
    lastName: "",
    email: "",
    password: "",
    confirmPassword: "",
    requestedRole: "student"
  });

  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setFieldErrors({ ...fieldErrors, [e.target.name]: "" });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setFieldErrors({});

    if (form.password !== form.confirmPassword) {
      setFieldErrors({ confirmPassword: "Passwords do not match!" });
      setLoading(false);
      return;
    }

    try {
      const response = await axios.post("http://localhost:8000/api/v1/auth/register", {
        username: form.username,
        email: form.email,
        password: form.password,
        first_name: form.firstName,
        last_name: form.lastName,
        requested_role: form.requestedRole
      });

      if (response.status === 201 || response.status === 200 || response.status === 202) {
        navigate("/pending-approval");
      }
    } catch (err) {
      const errorDetail = err.response?.data?.detail;
      if (typeof errorDetail === "string") {
        const lowerDetail = errorDetail.toLowerCase();
        if (lowerDetail.includes("email")) {
          setFieldErrors({ email: "This email is already registered." });
        } else if (lowerDetail.includes("username")) {
          setFieldErrors({ username: "Username is already taken." });
        } else {
          setFieldErrors({ general: errorDetail });
        }
      }
    } finally {
      setLoading(false);
    }
  };

  
  const getInputStyle = (fieldName) => ({
    borderColor: fieldErrors[fieldName] ? "#dc2626" : "#d1d5db",
    marginBottom: fieldErrors[fieldName] ? "4px" : "12px"
  });

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h2>Create Account</h2>
        
        {fieldErrors.general && (
          <p className="status failed" style={{textAlign: 'center', marginBottom: '15px'}}>
            {fieldErrors.general}
          </p>
        )}

        <form onSubmit={handleSubmit}>
          {/* First & Last Name */}
          <div style={{ display: "flex", gap: "10px" }}>
            <div style={{ flex: 1, marginBottom: "12px" }}>
              <label>First Name</label>
              <input name="firstName" value={form.firstName} onChange={handleChange} style={getInputStyle("firstName")} required />
            </div>
            <div style={{ flex: 1, marginBottom: "12px" }}>
              <label>Last Name</label>
              <input name="lastName" value={form.lastName} onChange={handleChange} style={getInputStyle("lastName")} required />
            </div>
          </div>

          {/* Username */}
          <div style={{ marginBottom: "12px" }}>
            <label>Username</label>
            <input name="username" value={form.username} onChange={handleChange} style={getInputStyle("username")} required />
            {fieldErrors.username && <span className="error-message">{fieldErrors.username}</span>}
          </div>

          {/* Role */}
          <div style={{ marginBottom: "12px" }}>
            <label>Register as</label>
            <select name="requestedRole" value={form.requestedRole} onChange={handleChange} 
              style={{...getInputStyle("requestedRole"), width: '100%', padding: '10px', borderRadius: '8px', background: 'white'}}>
              <option value="student">Student (Standard Access)</option>
              <option value="researcher">Researcher (HPC Access)</option>
            </select>
          </div>

          {/* Email - هنا المشكل لي كان عندك */}
          <div style={{ marginBottom: "15px" }}>
            <label>Email</label>
            <input type="email" name="email" value={form.email} onChange={handleChange} style={getInputStyle("email")} required />
            {fieldErrors.email && <span className="error-message">{fieldErrors.email}</span>}
          </div>

          {/* Password */}
          <div style={{ marginBottom: "12px", marginTop: fieldErrors.email ? "10px" : "0" }}>
            <label>Password</label>
            <div className="password-field">
              <input 
                type={showPassword ? "text" : "password"} 
                name="password" 
                value={form.password} 
                onChange={handleChange} 
                style={getInputStyle("password")} 
                required 
              />
              <span className="toggle-eye" onClick={() => setShowPassword(!showPassword)}>
                {/* SVG icon */}
              </span>
            </div>
          </div>

          {/* Confirm Password */}
          <div style={{ marginBottom: "12px" }}>
            <label>Confirm Password</label>
            <div className="password-field">
              <input 
                type={showConfirmPassword ? "text" : "password"} 
                name="confirmPassword" 
                value={form.confirmPassword} 
                onChange={handleChange} 
                style={getInputStyle("confirmPassword")} 
                required 
              />
              <span className="toggle-eye" onClick={() => setShowConfirmPassword(!showConfirmPassword)}>
                {/* SVG icon */}
              </span>
            </div>
            {fieldErrors.confirmPassword && <span className="error-message">{fieldErrors.confirmPassword}</span>}
          </div>

          <button type="submit" disabled={loading} style={{marginTop: "10px"}}>
            {loading ? "Checking..." : "Register"}
          </button>
        </form>

        <p style={{ marginTop: "15px" }}>
          Already have an account? <Link to="/login">Login</Link>
        </p>
      </div>
    </div>
  );
}
