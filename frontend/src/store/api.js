import axios from "axios";
import { getToken, removeToken, refreshToken } from "./store/auth";


const api = axios.create({
  baseURL: "http://localhost:8000/api/v1",
});


api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});


api.interceptors.response.use(
  (response) => response, 
  async (error) => {
    const originalRequest = error.config;

  
    if (error.response?.status === 401 && !originalRequest._retry) {
      
  
      if (originalRequest.url.includes("openid-connect/token")) {
        return Promise.reject(error);
      }

      originalRequest._retry = true; 

      try {
        const refreshed = await refreshToken();

        if (refreshed) {
          const newToken = getToken();
       
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          
         
          return api(originalRequest);
        }
      } catch (refreshError) {
     
        console.error("Refresh failed:", refreshError);
        removeToken();
        window.location.href = "/login";
        return Promise.reject(refreshError);
      }
    }

  
    if (error.response?.status === 401) {
      removeToken();
      window.location.href = "/login";
    }

    return Promise.reject(error);
  }
);

export default api;
