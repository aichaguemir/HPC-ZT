// src/components/mfa/mfaService.js

import api from "../../api"; 

const mfaService = {
  getMfaSetup: async () => {
    try {
  
      const res = await api.get("/auth/totp/setup");
      return res.data;
    } catch (error) {
      console.error("SERVICE ERROR:", error.response);
      throw error;
    }
  },

  confirmMfaSetup: async (code) => {
   
    const res = await api.post("/auth/totp/confirm-setup", { code });
    return res.data;
  }
  useEffect(() => {
  const fetchQR = async () => {
    try {
      const data = await mfaService.getMfaSetup();
    
      setQrCode(data.qr_code); 
      setSecret(data.secret);
    } catch (err) {
    
      console.log("Error details:", err.response?.data);
      setError("Failed to load QR Code. Verify Backend CORS settings.");
    }
  };
  fetchQR();
}, []);
};

export default mfaService;
