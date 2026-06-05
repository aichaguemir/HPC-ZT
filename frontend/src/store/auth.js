const KEYCLOAK_URL    = "https://localhost:8443";
const KEYCLOAK_REALM  = "HPC-Project";
const KEYCLOAK_CLIENT = "hpc-backend";
const API_URL         = "https://localhost/api/v1";

export const saveToken = (token) => sessionStorage.setItem("access_token", token);
export const getToken = () => sessionStorage.getItem("access_token");
export const saveRefreshToken = (token) => sessionStorage.setItem("refresh_token", token);
export const getRefreshToken = () => sessionStorage.getItem("refresh_token");

export const removeToken = () => {
  sessionStorage.removeItem("access_token");
  sessionStorage.removeItem("refresh_token");
  sessionStorage.removeItem("user");
  sessionStorage.removeItem("mfa_verified");
  localStorage.removeItem("mfa_verified");
};

export const saveUser = (user) => sessionStorage.setItem("user", JSON.stringify(user));
export const getUser = () => {
  const user = sessionStorage.getItem("user");
  return user ? JSON.parse(user) : null;
};
export const isAuthenticated = () => !!getToken();
export const completeMfa = () => sessionStorage.setItem("mfa_verified", "true");
export const isMfaVerified = () => sessionStorage.getItem("mfa_verified") === "true";

// ── Login ──────────────────────────────────────────────────────────────────

export const login = async (username, password) => {
  const params = new URLSearchParams();
  params.append("client_id",  KEYCLOAK_CLIENT);
  params.append("username",   username);
  params.append("password",   password);
  params.append("grant_type", "password");

  const response = await fetch(
    `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`,
    {
      method:  "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body:    params,
    }
  );

  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.error_description || "Invalid credentials");
  }

  const data = await response.json();
  saveToken(data.access_token);
  if (data.refresh_token) saveRefreshToken(data.refresh_token);
  sessionStorage.removeItem("mfa_verified");

  const meResponse = await fetch(`${API_URL}/auth/me`, {
    headers: { "Authorization": `Bearer ${data.access_token}` }
  });

  if (meResponse.status === 403) {
    removeToken();
    throw new Error("PENDING_APPROVAL");
  }

  if (!meResponse.ok) {
    removeToken();
    throw new Error("Could not fetch user profile");
  }

  const user = await meResponse.json();
  saveUser(user);

  if (!user.email_otp_verified) {
    throw new Error("MFA_REQUIRED");
  } else {
    completeMfa();
    return user;
  }
};
// ── Refresh Token ──────────────────────────────────────────────────────────

export const refreshToken = async () => {
  const refresh = getRefreshToken();
  if (!refresh) return false;

  try {
    const params = new URLSearchParams();
    params.append("client_id",     KEYCLOAK_CLIENT);
    params.append("grant_type",    "refresh_token");
    params.append("refresh_token", refresh);

    const response = await fetch(
      `${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`,
      {
        method:  "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body:    params,
      }
    );

    if (!response.ok) return false;

    const data = await response.json();
    saveToken(data.access_token);
    if (data.refresh_token) saveRefreshToken(data.refresh_token);
    return true;
  } catch (err) {
    console.error("Refresh Token Error:", err);
    return false;
  }
};

// ── USERS & LOGS ───────────────────────────────────────────────────────────

export const getAllUsers = async () => {
  const token = getToken();
  const response = await fetch(`${API_URL}/admin/users`, {
    headers: { "Authorization": `Bearer ${token}` }
  });
  if (!response.ok) throw new Error("Failed to fetch users");
  return await response.json();
};

export const getSystemLogs = async () => {
  const token = getToken();
  const response = await fetch(`${API_URL}/admin/logs`, {
    headers: { "Authorization": `Bearer ${token}` }
  });
  if (!response.ok) throw new Error("Failed to fetch logs");
  return await response.json();
};

// ── Register ───────────────────────────────────────────────────────────────

export const register = async (formData) => {
  const response = await fetch(`${API_URL}/auth/register`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      username:       formData.username,
      email:          formData.email,
      password:       formData.password,
      requested_role: formData.requested_role || "student",
      first_name:     formData.firstName || "",
      last_name:      formData.lastName  || "",
    }),
  });

  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Registration failed");
  return data;
};

// ── Logout ─────────────────────────────────────────────────────────────────

export const logout = async () => {
  const token = getToken();
  if (token) {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method:  "POST",
        headers: { "Authorization": `Bearer ${token}` }
      });
    } catch (e) {
      // ignore
    }
  }
  removeToken();
  window.location.href = "/login";
};
