import React, { useState, useEffect } from "react";
import api from "../../store/api"; 


/**
 * UserManagement Component
 * Comprehensive management of HPC portal users.
 */
export default function UserManagement() {
  // --- State Management ---
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [newRole, setNewRole] = useState("");

  /**
   * 1. Fetch Users from Backend
   */
  const fetchUsers = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const response = await api.get("/admin/users");
      console.log("Backend Raw Response:", response.data); // Debugging line

      // Extract users array safely
      const data = response.data;
      const allUsers = Array.isArray(data) ? data : (data.users || []);
      
      // Filter approved users. Note: Check if your backend uses 'is_approved' or 'is_active'
      const approvedUsers = allUsers.filter(u => u.is_approved === true || u.status === "approved");
      
      setUsers(approvedUsers);
      setError(null);
    } catch (err) {
      console.error("Fetch Error:", err);
      setError("Connection to HPC Admin Node failed.");
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers(true);
    const interval = setInterval(() => fetchUsers(false), 30000);
    return () => clearInterval(interval);
  }, []);

  /**
   * 2. Toggle Account Access (Deactivate/Reactivate)
   */
  const handleToggleActive = async (user) => {
    // IMPORTANT: Check if your backend uses 'user_id' or 'id'
    const uid = user.user_id || user.id; 
    const action = user.is_active ? "deactivate" : "reactivate";
    
    try {
      await api.post(`/admin/users/${uid}/${action}`);
      fetchUsers(); 
    } catch (err) {
      console.error("Toggle Error:", err.response);
      alert(`Failed to ${action} user.`);
    }
  };

  /**
   * 3. Role Modification Logic
   */
  const openRoleModal = (user) => {
    setSelectedUser(user);
    setNewRole(user.role);
    setIsModalOpen(true);
  };

  const handleRoleChange = async (userId, selectedRole) => {
    try {
      // Sending 'new_role' as expected by the backend payload
      await api.put(`/admin/users/${userId}/role`, { new_role: selectedRole });
      
      alert("Role updated successfully!");
      setIsModalOpen(false); 
      fetchUsers();          
    } catch (err) {
      alert("Role update failed. Check console for details.");
    }
  };

  /**
   * 4. Revoke Access (Delete)
   */
  const handleRevoke = async (userId) => {
    if (!window.confirm("CRITICAL: Permanently revoke this user's access?")) return;
    try {
      await api.post(`/admin/users/${userId}/revoke`);
      fetchUsers();
    } catch (err) {
      alert("Revocation failed.");
    }
  };

  // 5. Filter users based on search input
  const filteredUsers = users.filter((u) =>
    u.username?.toLowerCase().includes(search.toLowerCase()) ||
    u.email?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <div className="loading">Syncing User Directory...</div>;

  return (
    <div className="audit-page">
      <div className="audit-header">
        <h1 className="audit-title">User Management</h1>
        <div className="search-container">
          <input
            type="text"
            className="audit-search-input"
            placeholder="Search users..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="table-card">
        <table className="audit-table">
          <thead>
            <tr>
              <th>User Identity</th>
              <th>System Role</th>
              <th>Access Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.length > 0 ? (
              filteredUsers.map((user) => (
                <tr key={user.user_id || user.id}>
                  <td>
                    <div className="username-text">{user.username}</div>
                    <div className="email-subtext-dark">{user.email}</div>
                  </td>
                  <td><span className="tag-role-large">{user.role}</span></td>
                  <td>
                    <span className={`status-badge ${user.is_active ? "approved" : "pending"}`}>
                      {user.is_active ? "Active" : "Disabled"}
                    </span>
                  </td>
                  <td>
                    <div className="action-buttons-group">
                      <button className="verify-btn" onClick={() => handleToggleActive(user)}>
                        {user.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                      <button className="change-role-btn" onClick={() => openRoleModal(user)}>
                        Role
                      </button>
                      <button className="revoke-card-btn" onClick={() => handleRevoke(user.user_id || user.id)}>
                        Revoke
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr><td colSpan="4" style={{textAlign:"center", padding:"30px"}}>No approved users found.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Role Modal */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <h3>Change Role: {selectedUser?.username}</h3>
            <select 
              className="modal-select" 
              value={newRole} 
              onChange={(e) => setNewRole(e.target.value)}
            >
              <option value="student">Student</option>
              <option value="researcher">Researcher</option>
              <option value="admin">Admin</option>
            </select>
            <div className="modal-footer">
              <button onClick={() => setIsModalOpen(false)}>Cancel</button>
              <button 
                className="save-btn" 
                onClick={() => handleRoleChange(selectedUser.user_id || selectedUser.id, newRole)}
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
