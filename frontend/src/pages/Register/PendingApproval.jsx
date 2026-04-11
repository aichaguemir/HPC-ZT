import React from "react";
import { Link } from "react-router-dom";

export default function PendingApproval() {
  return (
    <div className="pending-container">
      <div className="pending-card">
        
        <h2>Registration Submitted</h2>
        
        <div className="status-tag-pending">
          Status: Pending Admin Approval
        </div>
        
        <p className="pending-description">
          Your account request for the <strong>Secure HPC Portal</strong> has been received. 
          For security reasons, an administrator must verify your identity and requested role 
          before access is granted.
        </p>

        <div className="next-steps-box">
          <strong>What happens next?</strong>
          <ul className="next-steps-list">
            <li>Admin reviews your registration.</li>
            <li>Role permissions are assigned.</li>
            <li>You will receive notification upon activation.</li>
          </ul>
        </div>

        <Link to="/login" className="btn-return-login">
          Return to Login
        </Link>
      </div>
    </div>
  );
}
