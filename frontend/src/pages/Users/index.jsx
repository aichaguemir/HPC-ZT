import React, { useState, useEffect } from "react";
import axios from "axios";
import { getToken } from "../../store/auth";


/**
 * UserManagement Component
 * Handles administrative tasks: listing approved users, searching, 
 * toggling account status, updating roles, and revoking access.
 */
export default function UserManagement() {
  // --- State Management ---
  const [users, setUsers] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  // Modal States for Role Modification
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [newRole, setNewRole] = useState("");

  /**
   * 1. Fetch Users
   * Retrieves all users and filters for those already approved.
   */
  const fetchUsers = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const response = await axios.get("http://localhost:8000/api/v1/admin/users", {
        headers: { Authorization: `Bearer ${token}` }
      });

      // Handle different possible API response structures
      const allUsers = Array.isArray(response.data) ? response.data : (response.data.users || []);
      
      // Filter: Only show users who are already part of the system
      const approvedUsers = allUsers.filter(u => u.is_approved === true);
      
      setUsers(approvedUsers);
      setError(null);
    } catch (err) {
      console.error("Fetch Error:", err);
      setError("Failed to load user directory. Please check backend connection.");
    } finally {
      setLoading(false);
    }
  };

  // Load data on component mount
  useEffect(() => {
    fetchUsers();
  }, []);

  /**
   * 2. Toggle Account Status
   * Uses POST for both deactivate and reactivate actions as required by Backend.
   */
  const handleToggleActive = async (user) => {
    const action = user.is_active ? "deactivate" : "reactivate";
    try {
      const token = getToken();
      await axios.post(`http://localhost:8000/api/v1/admin/users/${user.user_id}/${action}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchUsers(); // Refresh UI
    } catch (err) {
      alert(`Operation failed: Could not ${action} user.`);
    }
  };

  /**
   * 3. Role Management Logic
   */
  const openRoleModal = (user) => {
    setSelectedUser(user);
    setNewRole(user.role);
    setIsModalOpen(true);
  };

const handleRoleChange = async (userId, selectedRole) => {
    try {
      const token = getToken();
      
     
      const payload = {
        new_role: selectedRole 
      };

      await axios.put(
        `http://localhost:8000/api/v1/admin/users/${userId}/role`,
        payload,
        {
          headers: { Authorization: `Bearer ${token}` }
        }
      );

      alert("Role updated successfully!");
      setIsModalOpen(false); 
      fetchUsers();         
    } catch (err) {
      console.error("Error updating role:", err.response?.data);
     
      const errorMsg = err.response?.data?.detail;
      alert("Error: " + (Array.isArray(errorMsg) ? errorMsg[0].msg : errorMsg || "Could not update role"));
    }
  };
  /**
   * 4. Revoke Access
   * Permanently removes a user from the HPC portal.
   */
  const handleRevoke = async (userId) => {
    if (!window.confirm("CRITICAL: Are you sure? This will permanently revoke access.")) return;
    try {
      const token = getToken();
      await axios.post(`http://localhost:8000/api/v1/admin/users/${userId}/revoke`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      fetchUsers();
    } catch (err) {
      alert("Error: Access revocation failed.");
    }
  };

  // 5. Search Filter Logic
  const filteredUsers = users.filter((u) =>
    u.username?.toLowerCase().includes(search.toLowerCase()) ||
    u.role?.toLowerCase().includes(search.toLowerCase()) ||
    u.email?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <div className="loading-container">Synchronizing with HPC Admin Node...</div>;

  return (
    <div className="audit-page">
      {/* Page Header and Search Section */}
      <div className="audit-header">
        <h1 className="audit-title">User Management</h1>
        <div className="search-container">
          <input
            type="text"
            className="audit-search-input"
            placeholder="Search by name, role, or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Users Table */}
      <div className="table-card">
        <table className="audit-table">
          <thead>
            <tr>
              <th>User Details</th>
              <th>System Role</th>
              <th>Status</th>
              <th>Administrative Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map((user) => (
              <tr key={user.user_id}>
                <td>
                  <div className="username-text">{user.username}</div>
                  <div className="email-subtext-dark">{user.email}</div>
                </td>
                <td>
                  <span className="tag-role-large">{user.role}</span>
                </td>
                <td>
                  <span className={`status-badge ${user.is_active ? "approved" : "pending"}`}>
                    <span className="dot"></span>
                    {user.is_active ? "Active" : "Disabled"}
                  </span>
                </td>
                <td>
                  {/* Action Buttons with defined gap in CSS */}
                  <div className="action-buttons-group">
                    <button className="verify-btn" onClick={() => handleToggleActive(user)}>
                      {user.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                    <button className="change-role-btn" onClick={() => openRoleModal(user)}>
                      Change Role
                    </button>
                    <button className="revoke-card-btn" onClick={() => handleRevoke(user.user_id)}>
                      Revoke
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pop-up Modal for Role Changes */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <h3 className="modal-title">Update Permissions</h3>
            <p>Assigning new role to: <strong>{selectedUser?.username}</strong></p>
            
            <select 
              className="modal-select" 
              value={newRole} 
              onChange={(e) => setNewRole(e.target.value)}
            >
              <option value="researcher">Researcher</option>
              <option value="student">Student</option>
            </select>

            <div className="modal-footer">
              <button className="cancel-btn" onClick={() => setIsModalOpen(false)}>Cancel</button>
              <button 
  onClick={() => handleRoleChange(selectedUser.user_id, newRole)}
  style={{
    backgroundColor: "#3b82f6", 
    color: "white",
    padding: "10px 20px",
    borderRadius: "6px",
    border: "none",
    cursor: "pointer",
    fontWeight: "500",
    transition: "background-color 0.2s"
  }}
  onMouseOver={(e) => e.target.style.backgroundColor = "#2563eb"} 
  onMouseOut={(e) => e.target.style.backgroundColor = "#3b82f6"}
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
