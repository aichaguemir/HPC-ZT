import React, { useState } from 'react';
import axios from 'axios';

const MfaVerifyModal = ({ isOpen, onSuccess, onCancel }) => {
    const [code, setCode] = useState('');
    const [error, setError] = useState('');

    const handleVerify = async (e) => {
        e.preventDefault();
        try {
            const res = await axios.post('/auth/totp/verify', { code: code });
            if (res.data.verified) {
                onSuccess(); // رجعي لـ Component الأب بلي راهو verified
            }
        } catch (err) {
            setError("Invalid code.");
        }
    };

    if (!isOpen) return null;

    return (
        <div className="modal-overlay" style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div className="modal-content" style={{ background: '#fff', padding: '30px', borderRadius: '8px', textAlign: 'center' }}>
                <h3>MFA Verification Required</h3>
                <p>Open your authenticator app and enter the code:</p>
                <form onSubmit={handleVerify}>
                    <input 
                        type="text" 
                        value={code} 
                        onChange={(e) => setCode(e.target.value)}
                        maxLength="6"
                        style={{ padding: '10px', width: '100px', fontSize: '18px' }}
                        autoFocus
                    />
                    <div style={{ marginTop: '20px' }}>
                        <button type="submit">Verify</button>
                        <button type="button" onClick={onCancel} style={{ marginLeft: '10px' }}>Cancel</button>
                    </div>
                </form>
                {error && <p style={{ color: 'red' }}>{error}</p>}
            </div>
        </div>
    );
};

export default MfaVerifyModal;
