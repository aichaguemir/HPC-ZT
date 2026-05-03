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

  // --- Validation Helpers ---
  const validateEmail = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const hasNumbers = (str) => /\d/.test(str);
  const isComplexPassword = (pass) => /[a-zA-Z]/.test(pass) && /[0-9]/.test(pass);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setFieldErrors({ ...fieldErrors, [e.target.name]: "" });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errors = {};

    // Logic Validations
    if (hasNumbers(form.firstName)) errors.firstName = "Names cannot contain numbers.";
    if (hasNumbers(form.lastName)) errors.lastName = "Names cannot contain numbers.";
    if (!validateEmail(form.email)) errors.email = "Invalid email format (missing @ or .).";
    if (!isComplexPassword(form.password)) errors.password = "Password must include letters and numbers.";
    if (form.password !== form.confirmPassword) errors.confirmPassword = "Passwords do not match!";

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setLoading(true);
    try {
   
      const response = await axios.post("https://localhost:8000/api/v1/auth/register", {
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
        if (lowerDetail.includes("email")) setFieldErrors({ email: "Email already exists." });
        else if (lowerDetail.includes("username")) setFieldErrors({ username: "Username taken." });
        else setFieldErrors({ general: errorDetail });
      } else {
        setFieldErrors({ general: "Registration failed. Check your connection or data." });
      }
    } finally {
      setLoading(false);
    }
  };

  const getInputStyle = (fieldName) => ({
    borderColor: fieldErrors[fieldName] ? "#dc2626" : "#d1d5db",
    borderWidth: fieldErrors[fieldName] ? "2px" : "1px",
    padding: "12px",
    borderRadius: "8px",
    flex: 1,
    borderStyle: "solid",
    outline: "none"
  });

  return (
    <div className="auth-container" style={{ padding: "50px", display: "flex", justifyContent: "center" }}>
      <div className="auth-card" style={{ background: "white", padding: "40px", borderRadius: "12px", boxShadow: "0 10px 25px rgba(0,0,0,0.05)", width: "100%", maxWidth: "500px" }}>
        <h2 style={{ textAlign: "center", marginBottom: "30px", fontWeight: "bold" }}>Create Account</h2>
        
        {fieldErrors.general && (
          <p className="status failed" style={{ textAlign: 'center', marginBottom: '15px', color: '#dc2626', background: '#fff5f5', padding: '10px', borderRadius: '8px', border: '1px solid #dc2626', fontSize: '14px'}}>
            {fieldErrors.general}
          </p>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div style={{ display: "flex", gap: "10px", marginBottom: "12px" }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>First Name</label>
              <input name="firstName" value={form.firstName} onChange={handleChange} style={getInputStyle("firstName")} required />
              {fieldErrors.firstName && <span className="error-message" style={{ color: "#dc2626", fontSize: "12px", display: "block", marginTop: "4px" }}>{fieldErrors.firstName}</span>}
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>Last Name</label>
              <input name="lastName" value={form.lastName} onChange={handleChange} style={getInputStyle("lastName")} required />
              {fieldErrors.lastName && <span className="error-message" style={{ color: "#dc2626", fontSize: "12px", display: "block", marginTop: "4px" }}>{fieldErrors.lastName}</span>}
            </div>
          </div>

          <div style={{ marginBottom: "12px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>Username</label>
            <input name="username" value={form.username} onChange={handleChange} style={getInputStyle("username")} required />
            {fieldErrors.username && <span className="error-message" style={{ color: "#dc2626", fontSize: "12px", display: "block", marginTop: "4px" }}>{fieldErrors.username}</span>}
          </div>

          <div style={{ marginBottom: "12px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>Register as</label>
            <select name="requestedRole" value={form.requestedRole} onChange={handleChange} 
              style={{ borderColor: "#d1d5db", borderWidth: "1px", width: '100%', padding: '12px', borderRadius: '8px', background: 'white', borderStyle: "solid"}}>
              <option value="student">Student (Standard Access)</option>
              <option value="researcher">Researcher (HPC Access)</option>
            </select>
          </div>

          <div style={{ marginBottom: "15px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>Email Address</label>
            <input type="email" name="email" value={form.email} onChange={handleChange} style={getInputStyle("email")} required />
            {fieldErrors.email && <span className="error-message" style={{ color: "#dc2626", fontSize: "12px", display: "block", marginTop: "4px" }}>{fieldErrors.email}</span>}
          </div>

          <div style={{ marginBottom: "12px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>Password</label>
            <div className="password-field-container" style={{ display: "flex", alignItems: "center", position: "relative" }}>
              <input 
                type={showPassword ? "text" : "password"} 
                name="password" 
                value={form.password} 
                onChange={handleChange} 
                style={{...getInputStyle("password"), paddingRight: "45px", width: "100%"}}
                required 
              />
              <span className="toggle-eye" onClick={() => setShowPassword(!showPassword)} 
                style={{ 
                  position: "absolute", 
                  right: "12px", 
                  display: "flex", 
                  cursor: "pointer", 
                  color: fieldErrors.password ? "#dc2626" : "#2563eb",
                  transition: "color 0.2s"
                }}>
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {showPassword ? (
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22" />
                  ) : (
                    <>
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </>
                  )}
                </svg>
              </span>
            </div>
            {fieldErrors.password && <span className="error-message" style={{ color: "#dc2626", fontSize: "12px", display: "block", marginTop: "4px" }}>{fieldErrors.password}</span>}
          </div>

          <div style={{ marginBottom: "12px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "14px" }}>Confirm Password</label>
            <div className="password-field-container" style={{ display: "flex", alignItems: "center", position: "relative" }}>
              <input 
                type={showConfirmPassword ? "text" : "password"} 
                name="confirmPassword" 
                value={form.confirmPassword} 
                onChange={handleChange} 
                style={{...getInputStyle("confirmPassword"), paddingRight: "45px", width: "100%"}}
                required 
              />
              <span className="toggle-eye" onClick={() => setShowConfirmPassword(!showConfirmPassword)} 
                style={{ 
                  position: "absolute", 
                  right: "12px", 
                  display: "flex",
                  cursor: "pointer", 
                  color: fieldErrors.confirmPassword ? "#dc2626" : "#2563eb",
                  transition: "color 0.2s"
                }}>
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {showConfirmPassword ? (
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22" />
                  ) : (
                    <>
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </>
                  )}
                </svg>
              </span>
            </div>
            {fieldErrors.confirmPassword && <span className="error-message" style={{ color: "#dc2626", fontSize: "12px", display: "block", marginTop: "4px" }}>{fieldErrors.confirmPassword}</span>}
          </div>

          <button type="submit" disabled={loading} style={{marginTop: "20px", width: "100%", background: "#2563eb", color: "white", padding: "12px", borderRadius: "8px", border: "none", cursor: "pointer", fontWeight: "bold"}}>
            {loading ? "Creating..." : "Register"}
          </button>
        </form>

        <p style={{ marginTop: "20px", textAlign: "center", fontSize: "14px", color: "#6b7280" }}>
          Already have an account? <Link to="/login" style={{color: "#2563eb", fontWeight: "bold", textDecoration: "none"}}>Login</Link>
        </p>
      </div>
    </div>
  );
}
