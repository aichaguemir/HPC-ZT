import React, { useState, useEffect } from 'react';
import mfaService from './mfaService'; 
import { refreshUserProfile } from '../../store/auth'; 
import './MfaSetup.css';

const MfaSetup = ({ onStepComplete }) => {
    const [qrCode, setQrCode] = useState('');
    const [secret, setSecret] = useState('');
    const [code, setCode] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const getSetupData = async () => {
            try {
             
                const data = await mfaService.getMfaSetup();
                
                if (data.already_configured) {
                    if (onStepComplete) onStepComplete(); 
                } else {
                    setQrCode(data.qr_code);
                    setSecret(data.secret);
                }
            } catch (err) {
                console.error("MFA Fetch Error:", err);
                setError("Connection error. Make sure Backend is running on Port 8000.");
            } finally {
                setLoading(false);
            }
        };
        getSetupData();
    }, [onStepComplete]);

    const handleActivate = async (e) => {
        e.preventDefault();
        setError('');
        try {
            // تفعيل الـ MFA
            await mfaService.confirmMfaSetup(code);
            
            // تحديث البروفايل في الـ Storage باش totp_enabled تولي true
            await refreshUserProfile();
            
            alert("MFA Activated Successfully!");
            if (onStepComplete) onStepComplete(); 
        } catch (err) {
            setError(err.response?.data?.detail || "Invalid code. Please try again.");
        }
    };

    if (loading) return <div className="mfa-container">Loading secure setup...</div>;

    return (
        <div className="mfa-container">
            <div className="mfa-card">
                <div className="mfa-header">
                    <h2 className="mfa-title">Secure Your Account</h2>
                    <div className="mfa-badge">MFA Required</div>
                </div>

                <div className="mfa-step">
                    <p className="mfa-step-text"><strong>1. Scan the QR code</strong> using Google Authenticator</p>
                    <div className="mfa-qr-container">
                        {qrCode && <img src={qrCode} alt="TOTP QR" className="mfa-qr-image" />}
                    </div>
                    <div className="mfa-secret-box">
                        <span className="mfa-secret-label">Manual Secret:</span>
                        <code className="mfa-secret-code">{secret}</code>
                    </div>
                </div>

                <hr className="mfa-divider" />

                <div className="mfa-step">
                    <p className="mfa-step-text"><strong>2. Enter the 6-digit code</strong> from your app</p>
                    <form onSubmit={handleActivate} className="mfa-form">
                        <input 
                            type="text" 
                            value={code} 
                            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} // أرقام فقط
                            placeholder="000000"
                            maxLength="6"
                            className="mfa-input"
                            required
                        />
                        <button type="submit" className="mfa-button">
                            Verify & Activate
                        </button>
                    </form>
                </div>
                {error && <div className="mfa-error-banner">{error}</div>}
            </div>
        </div>
    );
};

export default MfaSetup;
