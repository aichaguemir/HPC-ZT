import axios from 'axios';

// إذا راكي دايرة الـ Base URL في بلاصة وحدة أخرى، تقدري تنحي هاد السطر
const API_URL = 'http://localhost:8000/auth'; 

const mfaService = {
    
    // 1. تجيب معلومات الـ Setup (الـ QR والـ Secret)
    getMfaSetup: async () => {
        try {
            const response = await axios.get(`${API_URL}/totp/setup`);
            return response.data;
        } catch (error) {
            throw error.response?.data?.detail || "Error loading MFA setup";
        }
    },

    // 2. تأكد الـ Setup لأول مرة (Confirm)
    confirmMfaSetup: async (code) => {
        try {
            const response = await axios.post(`${API_URL}/totp/confirm-setup`, { code });
            return response.data;
        } catch (error) {
            throw error.response?.data?.detail || "Invalid setup code";
        }
    },

    // 3. التحقق الروتيني (Verify) قبل العمليات الحساسة
    verifyMfa: async (code) => {
        try {
            const response = await axios.post(`${API_URL}/totp/verify`, { code });
            return response.data; // يرجع { "verified": true, ... }
        } catch (error) {
            throw error.response?.data?.detail || "Verification failed";
        }
    }
};

export default mfaService;
