import React, { useState } from "react";

const initialUsers = [
  { id: 1, username: "yasmine", role: "researcher", jobs: 12 },
  { id: 2, username: "ali", role: "student", jobs: 5 },
  { id: 3, username: "admin", role: "admin", jobs: 30 },
  { id: 4, username: "sara", role: "researcher", jobs: 9 },
];

export default function Users() {
  const [users, setUsers] = useState(initialUsers);
  const [search, setSearch] = useState("");

  // 🔍 filter
  const filteredUsers = users.filter(
    (u) =>
      u.username.toLowerCase().includes(search.toLowerCase()) ||
      u.role.toLowerCase().includes(search.toLowerCase())
  );

  // ❌ delete user
  const handleDelete = (id) => {
    const confirmDelete = window.confirm("Are you sure you want to delete this user?");
    if (!confirmDelete) return;

    setUsers(users.filter((u) => u.id !== id));
  };

  return (
    <div>
      <h1>Users Management</h1>

      {/* SEARCH */}
      <div className="search-box" style={{ marginBottom: "20px" }}>
        
 <input
          type="text"
          placeholder="Search job..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

      </div>

      {/* TABLE */}
      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Role</th>
              <th>Jobs</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {filteredUsers.map((user) => (
              <tr key={user.id}>
                <td>{user.username}</td>

                <td>
                  <span className={`role ${user.role}`}>
                    {user.role}
                  </span>
                </td>

                <td>{user.jobs}</td>

                <td>
                  <button
                    className="btn btn-danger"
                    onClick={() => handleDelete(user.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}

            {filteredUsers.length === 0 && (
              <tr>
                <td colSpan="4" style={{ textAlign: "center", padding: "20px" }}>
                  No users found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
