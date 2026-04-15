import axios from "axios";
import { getToken, removeToken, refreshToken } from "../store/auth"; 

const api = axios.create({
  baseURL: "http://localhost:8000/api/v1", 
});


api.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);


api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

   
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true; 

      const refreshed = await refreshToken();
      
      if (refreshed) {
        const token = getToken();
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return api(originalRequest);
      }

    
      removeToken();
      window.location.href = "/login";
    }

  
    if (error.response?.status === 403) {
       console.warn("Access denied: Redirecting to MFA if necessary...");
       
     
       if (!window.location.pathname.includes("/mfa-setup")) {
           window.location.href = "/mfa-setup";
       }
    }

    return Promise.reject(error);
  }
);

export default api;
