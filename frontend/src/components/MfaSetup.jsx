import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import mfaService from './mfaService';
import { refreshUserProfile } from '../../store/auth';

const MfaSetup = () => {
    const [qrCode, setQrCode] = useState('');
    const [secret, setSecret] = useState('');
    const [code, setCode] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        const fetchSetup = async () => {
            try {
                // نعيطو للـ Service لي راهو يضرب في الـ Port 8000
                const data = await mfaService.getMfaSetup();
                
                if (data.already_configured) {
                    navigate("/");
                } else {
                    setQrCode(data.qr_code);
                    setSecret(data.secret);
                }
            } catch (err) {
                console.error("MFA Error:", err);
                setError("Mfa setup error. Check backend connection on Port 8000.");
            } finally {
                setLoading(false);
            }
        };
        fetchSetup();
    }, [navigate]);

    const handleActivate = async (e) => {
        e.preventDefault();
        setError('');
        try {
            await mfaService.confirmMfaSetup(code);
         
            await refreshUserProfile(); 
            alert("MFA Activated successfully!");
            navigate("/");
        } catch (err) {
            setError(err.response?.data?.detail || "Invalid code. Try again.");
        }
    };

    if (loading) return <div style={{textAlign: 'center', marginTop: '50px'}}>Loading...</div>;

    return (
        <div style={{ maxWidth: '450px', margin: '50px auto', textAlign: 'center', padding: '20px', border: '1px solid #ddd', borderRadius: '10px' }}>
            <h2>Secure Your Account</h2>
            <p>1. Scan the QR code using Google Authenticator</p>
            
            {qrCode && (
                <div style={{ margin: '20px 0' }}>
                    <img src={qrCode} alt="MFA QR Code" style={{ border: '2px solid #eee', width: '200px' }} />
                </div>
            )}
            
            <div style={{ marginBottom: '15px' }}>
                <small>Manual Secret: <code>{secret}</code></small>
            </div>

            <p>2. Enter the 6-digit code from your app</p>
            <form onSubmit={handleActivate}>
                <input 
                    type="text" 
                    value={code} 
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="000000"
                    maxLength="6"
                    style={{ fontSize: '20px', textAlign: 'center', padding: '10px', width: '150px' }}
                    required
                />
                <br /><br />
                <button type="submit" style={{ padding: '10px 20px', backgroundColor: '#2563eb', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}>
                    Verify & Activate
                </button>
            </form>
            {error && <p style={{ color: 'red', marginTop: '15px' }}>{error}</p>}
        </div>
    );
};

export default MfaSetup;
