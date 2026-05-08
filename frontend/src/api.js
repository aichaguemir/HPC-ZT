// src/api.js
// Axios instance with automatic token injection

import axios from "axios";
import { getToken, removeToken } from "./store/auth";

const API_URL = "http://localhost:8000/api/v1";

const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

// Automatically attach token to every request
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 — token expired
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      removeToken();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// ── Job API ────────────────────────────────────────────────────────────────

export const submitJob = async (formData) => {
  const data = new FormData();
  data.append("file",              formData.file);
  data.append("cores",             formData.cores);
  data.append("memory",            formData.memory);
  data.append("queue",             formData.queue);
  data.append("wall_time_hours",   formData.wall_time_hours);
  data.append("wall_time_minutes", formData.wall_time_minutes);

  const response = await api.post("/jobs/submit", data, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
};

export const listJobs = async () => {
  const response = await api.get("/jobs/");
  return response.data.jobs;
};

export const getJobStatus = async (jobId) => {
  const response = await api.get(`/jobs/${jobId}/status`);
  return response.data;
};

export const getJobOutput = async (jobId) => {
  const response = await api.get(`/jobs/${jobId}/output`);
  return response.data;
};

export const cancelJob = async (jobId) => {
  const response = await api.delete(`/jobs/${jobId}/cancel`);
  return response.data;
};

// ── Admin API ──────────────────────────────────────────────────────────────

export const listUsers = async () => {
  const response = await api.get("/admin/users");
  return response.data.users;
};

export const listPendingUsers = async () => {
  const response = await api.get("/admin/users/pending");
  return response.data.pending;
};

export const approveUser = async (userId) => {
  const response = await api.post(`/admin/users/${userId}/approve`);
  return response.data;
};

export const rejectUser = async (userId) => {
  const response = await api.post(`/admin/users/${userId}/reject`);
  return response.data;
};

export const changeRole = async (userId, newRole) => {
  const response = await api.put(`/admin/users/${userId}/role`, { new_role: newRole });
  return response.data;
};

export const deactivateUser = async (userId) => {
  const response = await api.post(`/admin/users/${userId}/deactivate`);
  return response.data;
};

export const getNodes = async () => {
  const response = await api.get("/admin/nodes");
  return response.data.nodes;
};

export const getAuditLogs = async (limit = 50) => {
  const response = await api.get(`/admin/audit/logs?limit=${limit}`);
  return response.data.logs;
};

export const verifyAuditChain = async () => {
  const response = await api.get("/admin/audit/verify");
  return response.data;
};

export default api;
