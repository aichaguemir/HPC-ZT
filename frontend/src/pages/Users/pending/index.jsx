import React, { useState, useEffect } from "react";
import axios from "axios";
import { getToken } from "../../../store/auth";

/**
 * PendingUsers Component
 * Handles the approval and rejection of new user registration requests.
 */
export default function PendingUsers() {
  const [pendingUsers, setPendingUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  // 1. Fetch pending requests from the API
  const fetchPending = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const res = await axios.get("http://localhost:8000/api/v1/admin/users/pending", {
        headers: { Authorization: `Bearer ${token}` }
      });

      console.log("Data from server:", res.data);  
      
     
      const actualData = res.data.pending || (Array.isArray(res.data) ? res.data : []);

      setPendingUsers(actualData);
    } catch (err) {
      console.error("Fetch error:", err);
      setPendingUsers([]);
    } finally {
      setLoading(false);
    }
  };

  // 2. Handle Admin Action (Approve/Reject)
  const handleAction = async (userId, action) => {
 
    if (action === "reject" && !window.confirm("Are you sure you want to delete this registration request?")) {
        return;
    }

    try {
      const token = getToken();
    
      await axios.post(`http://localhost:8000/api/v1/admin/users/${userId}/${action}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      alert(`User successfully ${action}ed.`);
      fetchPending(); 
    } catch (err) {
      console.error(`Error during ${action}:`, err);
      alert(`System Error: Could not ${action} user.`);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  if (loading) return <div className="loading-state">Loading Pending Requests...</div>;

  return (
    <div className="audit-page">
      <h1 className="audit-title">Pending Access Requests</h1>
      
      <div className="table-card">
        <table className="audit-table">
          <thead>
            <tr>
              <th>User Info</th>
              <th>Email</th>
              <th>Requested Role</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pendingUsers.length > 0 ? (
              pendingUsers.map(user => (
                <tr key={user.user_id}>
                  <td>
                    <div className="username-text">{user.username}</div>
                    <small style={{color: '#94a3b8', fontSize: '10px'}}>{user.user_id}</small>
                  </td>
                  <td>
                    <div className="email-subtext-dark">{user.email}</div>
                  </td>
                  <td>

                    <span className="tag-role-large">
                        {user.requested_role || 'student'}
                    </span>
                  </td>
                  <td>
                    <div className="action-buttons-group">
                      <button 
                        className="verify-btn" 
                        onClick={() => handleAction(user.user_id, "approve")}
                      >
                        Approve
                      </button>
                      <button 
                        className="revoke-card-btn" 
                        onClick={() => handleAction(user.user_id, "reject")}
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="4" style={{ textAlign: "center", padding: "40px", color: "#64748b" }}>
                  All caught up! No pending registration requests.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
