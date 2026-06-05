import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../../store/api";

export default function Register() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    username: "",
    firstName: "",
    lastName: "",
    email: "",
    password: "",
    confirmPassword: "",
    requestedRole: "student",
  });

  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [document, setDocument] = useState(null);

  const validateEmail     = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  const hasNumbers        = (v) => /\d/.test(v);
  const isComplexPassword = (v) => /[a-zA-Z]/.test(v) && /[0-9]/.test(v);

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setFieldErrors({ ...fieldErrors, [e.target.name]: "" });
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file && file.type !== "application/pdf") {
      setFieldErrors((prev) => ({ ...prev, document: "Only PDF files are accepted." }));
      setDocument(null);
      e.target.value = "";
      return;
    }
    setDocument(file);
    setFieldErrors((prev) => ({ ...prev, document: "" }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errors = {};

    if (!form.firstName.trim())          errors.firstName = "First name is required.";
    else if (hasNumbers(form.firstName)) errors.firstName = "Names cannot contain numbers.";

    if (!form.lastName.trim())           errors.lastName = "Last name is required.";
    else if (hasNumbers(form.lastName))  errors.lastName = "Names cannot contain numbers.";

    if (!form.username.trim())           errors.username = "Username is required.";
    if (!validateEmail(form.email))      errors.email = "Invalid email format.";

    if (!isComplexPassword(form.password))
      errors.password = "Password must include letters and numbers.";

    if (form.password !== form.confirmPassword)
      errors.confirmPassword = "Passwords do not match.";

    if (!document)
      errors.document = form.requestedRole === "student"
        ? "Attestation de scolarité (PDF) is required."
        : "Carte de chercheur (PDF) is required.";

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setLoading(true);
    try {
      const data = new FormData();
      data.append("username",       form.username);
      data.append("email",          form.email);
      data.append("password",       form.password);
      data.append("first_name",     form.firstName);
      data.append("last_name",      form.lastName);
      data.append("requested_role", form.requestedRole);
      data.append("document",       document);

      await api.post("/auth/register", data, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      navigate("/pending-approval");
    } catch (err) {
      console.error("Registration error:", err);
      const detail = err.response?.data?.detail;
      if (typeof detail === "string") {
        const d = detail.toLowerCase();
        if      (d.includes("email"))    setFieldErrors({ email: "Email already exists." });
        else if (d.includes("username")) setFieldErrors({ username: "Username already taken." });
        else                             setFieldErrors({ general: detail });
      } else {
        setFieldErrors({ general: "Registration failed. Please try again." });
      }
    } finally {
      setLoading(false);
    }
  };

  const EyeIcon = ({ visible }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"
      viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {visible ? (
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24M1 1l22 22" />
      ) : (
        <>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </>
      )}
    </svg>
  );

  const inp = (field, extra = {}) => ({
    width: "100%",
    padding: "11px 12px",
    borderRadius: "8px",
    border: `${fieldErrors[field] ? "2px" : "1px"} solid ${fieldErrors[field] ? "#dc2626" : "#d1d5db"}`,
    outline: "none",
    fontSize: "14px",
    background: "white",
    transition: "border-color 0.2s",
    ...extra,
  });

  const RequiredStar = () => (
    <span style={{ color: "#dc2626", marginLeft: 3 }}>*</span>
  );

  const FieldLabel = ({ text }) => (
    <label style={{ display: "block", marginBottom: 5, fontSize: 13, fontWeight: 500 }}>
      {text}<RequiredStar />
    </label>
  );

  const FieldError = ({ field }) =>
    fieldErrors[field] ? (
      <span style={{ color: "#dc2626", fontSize: 12, display: "block", marginTop: 4 }}>
        {fieldErrors[field]}
      </span>
    ) : null;

  return (
    <div className="auth-container">
      <div className="auth-card" style={{ maxWidth: 520 }}>
        <h2 style={{ textAlign: "center", marginBottom: 6, fontWeight: 700 }}>
          Create Account
        </h2>
        <p style={{ textAlign: "center", fontSize: 12, color: "#94a3b8", marginBottom: 24 }}>
          Fields marked <span style={{ color: "#dc2626" }}>*</span> are required
        </p>

        {fieldErrors.general && (
          <div style={{
            marginBottom: 16, padding: "10px 14px", borderRadius: 8,
            background: "#fff5f5", border: "1px solid #dc2626",
            color: "#dc2626", fontSize: 13, textAlign: "center",
          }}>
            {fieldErrors.general}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>

          {/* First + Last name */}
          <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
            <div style={{ flex: 1 }}>
              <FieldLabel text="First Name" />
              <input
                name="firstName"
                value={form.firstName}
                onChange={handleChange}
                style={inp("firstName")}
                placeholder="Yasmine"
              />
              <FieldError field="firstName" />
            </div>
            <div style={{ flex: 1 }}>
              <FieldLabel text="Last Name" />
              <input
                name="lastName"
                value={form.lastName}
                onChange={handleChange}
                style={inp("lastName")}
                placeholder="Grele"
              />
              <FieldError field="lastName" />
            </div>
          </div>

          {/* Username */}
          <div style={{ marginBottom: 14 }}>
            <FieldLabel text="Username" />
            <input
              name="username"
              value={form.username}
              onChange={handleChange}
              style={inp("username")}
              placeholder="yasmine_g"
            />
            <FieldError field="username" />
          </div>

          {/* Role */}
          <div style={{ marginBottom: 14 }}>
            <FieldLabel text="Register as" />
            <select
              name="requestedRole"
              value={form.requestedRole}
              onChange={(e) => {
                handleChange(e);
                setDocument(null);
                setFieldErrors((prev) => ({ ...prev, document: "" }));
              }}
              style={inp("requestedRole")}
            >
              <option value="student">Student (Standard Access)</option>
              <option value="researcher">Researcher (HPC Access)</option>
            </select>
          </div>

          {/* Document upload */}
          <div style={{ marginBottom: 14 }}>
            <FieldLabel
              text={
                form.requestedRole === "student"
                  ? "Attestation de scolarité (PDF)"
                  : "Carte de chercheur (PDF)"
              }
            />
            <div style={{
              border: `${fieldErrors.document ? "2px" : "1px"} dashed ${fieldErrors.document ? "#dc2626" : "#d1d5db"}`,
              borderRadius: 8,
              padding: "14px 16px",
              background: fieldErrors.document ? "#fff5f5" : "#f8fafc",
              cursor: "pointer",
              transition: "border-color 0.2s",
            }}>
              <input
                type="file"
                accept="application/pdf"
                onChange={handleFileChange}
                style={{ display: "none" }}
                id="doc-upload"
              />
              <label htmlFor="doc-upload" style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{
                  background: "#eff6ff", color: "#2563eb",
                  padding: "6px 14px", borderRadius: 6,
                  fontSize: 13, fontWeight: 600, whiteSpace: "nowrap",
                }}>
                  Choose file
                </span>
                <span style={{ fontSize: 13, color: document ? "#0f172a" : "#94a3b8" }}>
                  {document ? document.name : "No file chosen — PDF only"}
                </span>
              </label>
            </div>
            {document && (
              <div style={{
                marginTop: 6, display: "flex", alignItems: "center",
                gap: 6, fontSize: 12, color: "#16a34a",
              }}>
                <span>✓</span>
                <span>{document.name} ({(document.size / 1024).toFixed(0)} KB)</span>
                <button
                  type="button"
                  onClick={() => { setDocument(null); document.getElementById("doc-upload").value = ""; }}
                  style={{ marginLeft: "auto", background: "none", border: "none", color: "#dc2626", cursor: "pointer", fontSize: 12 }}
                >
                  Remove
                </button>
              </div>
            )}
            <FieldError field="document" />
          </div>

          {/* Email */}
          <div style={{ marginBottom: 14 }}>
            <FieldLabel text="Email Address" />
            <input
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              style={inp("email")}
              placeholder="yasmine@univ.dz"
            />
            <FieldError field="email" />
          </div>

          {/* Password */}
          <div style={{ marginBottom: 14 }}>
            <FieldLabel text="Password" />
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                name="password"
                value={form.password}
                onChange={handleChange}
                style={inp("password", { paddingRight: 42 })}
                placeholder="••••••••"
              />
              <span
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: "absolute", right: 12, top: "50%",
                  transform: "translateY(-50%)", cursor: "pointer",
                  display: "flex", color: fieldErrors.password ? "#dc2626" : "#2563eb",
                }}
              >
                <EyeIcon visible={showPassword} />
              </span>
            </div>
            <FieldError field="password" />
          </div>

          {/* Confirm password */}
          <div style={{ marginBottom: 22 }}>
            <FieldLabel text="Confirm Password" />
            <div style={{ position: "relative" }}>
              <input
                type={showConfirmPassword ? "text" : "password"}
                name="confirmPassword"
                value={form.confirmPassword}
                onChange={handleChange}
                style={inp("confirmPassword", { paddingRight: 42 })}
                placeholder="••••••••"
              />
              <span
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                style={{
                  position: "absolute", right: 12, top: "50%",
                  transform: "translateY(-50%)", cursor: "pointer",
                  display: "flex", color: fieldErrors.confirmPassword ? "#dc2626" : "#2563eb",
                }}
              >
                <EyeIcon visible={showConfirmPassword} />
              </span>
            </div>
            <FieldError field="confirmPassword" />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%", padding: "12px",
              background: loading ? "#93c5fd" : "#2563eb",
              color: "white", border: "none", borderRadius: 8,
              fontWeight: 700, fontSize: 15,
              cursor: loading ? "not-allowed" : "pointer",
              transition: "background 0.2s",
            }}
          >
            {loading ? "Creating account..." : "Register"}
          </button>
        </form>

        <p style={{ marginTop: 20, textAlign: "center", fontSize: 14, color: "#6b7280" }}>
          Already have an account?{" "}
          <Link to="/login" style={{ color: "#2563eb", fontWeight: 600, textDecoration: "none" }}>
            Login
          </Link>
        </p>
      </div>
    </div>
  );
}
