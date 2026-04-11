import React, { useState, useEffect } from "react";
import api from "../../../store/api"; // Updated to use your smart API instance


/**
 * PendingUsers Component
 * Handles the approval and rejection of new user registration requests.
 * Uses the centralized API instance for automatic token management.
 */
export default function PendingUsers() {
  const [pendingUsers, setPendingUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  /**
   * 1. Fetch pending requests from the API
   * @param {boolean} isInitial - Controls the full-page loading state
   */
  const fetchPending = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      // Automatic token handling via api.js
      const res = await api.get("/admin/users/pending");

      console.log("Pending Users Data:", res.data);
      
      // Support both { pending: [] } structure and direct array [] structure
      const actualData = res.data.pending || (Array.isArray(res.data) ? res.data : []);

      setPendingUsers(actualData);
    } catch (err) {
      console.error("Fetch error:", err);
      setPendingUsers([]);
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  /**
   * 2. Handle Admin Action (Approve/Reject)
   * @param {string} userId - The unique ID of the user
   * @param {string} action - 'approve' or 'reject'
   */
  const handleAction = async (userId, action) => {
    // Confirmation for rejection to prevent accidental deletions
    if (action === "reject" && !window.confirm("Are you sure you want to delete this registration request?")) {
      return;
    }

    try {
      // POST request to trigger approval/rejection logic on the backend
      await api.post(`/admin/users/${userId}/${action}`);
      
      alert(`User request successfully ${action}ed.`);
      fetchPending(false); // Refresh the list after action
    } catch (err) {
      console.error(`Error during ${action}:`, err);
      alert(`System Error: Could not ${action} user request.`);
    }
  };

  // Initial load and background sync every 30 seconds
  useEffect(() => {
    fetchPending(true);
    
    const interval = setInterval(() => {
      fetchPending(false);
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="loading-state">Synchronizing Pending Requests...</div>;

  return (
    <div className="audit-page">
      <h1 className="audit-title">Pending Access Requests</h1>
      
      <div className="table-card">
        <table className="audit-table">
          <thead>
            <tr>
              <th>User Info</th>
              <th>Email Address</th>
              <th>Requested Role</th>
              <th>Administrative Actions</th>
            </tr>
          </thead>
          <tbody>
            {pendingUsers.length > 0 ? (
              pendingUsers.map(user => (
                <tr key={user.user_id || user.id}>
                  <td>
                    <div className="username-text">{user.username}</div>
                    <small style={{ color: '#94a3b8', fontSize: '10px' }}>
                        ID: {user.user_id || user.id}
                    </small>
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
                        onClick={() => handleAction(user.user_id || user.id, "approve")}
                      >
                        Approve
                      </button>
                      <button 
                        className="revoke-card-btn" 
                        onClick={() => handleAction(user.user_id || user.id, "reject")}
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
