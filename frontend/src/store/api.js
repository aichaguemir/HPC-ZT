import axios from "axios";
import { getToken, removeToken, refreshToken } from "./auth";

const API_URL = "/api/v1";

const api = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request Interceptor
api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => Promise.reject(error));

// Response Interceptor
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshed = await refreshToken();
        if (refreshed) {
          const newToken = getToken();
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          if (originalRequest.data instanceof FormData) {
            delete originalRequest.headers["Content-Type"];
          }
          return api(originalRequest);
        }
      } catch (refreshError) {
        console.error("Refresh token failed", refreshError);
      }
      removeToken();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
