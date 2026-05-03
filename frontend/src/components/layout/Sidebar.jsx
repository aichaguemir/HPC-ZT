import React from "react";
import { Link } from "react-router-dom"; 
import { getUser } from "../../store/auth";

/**
 * Sidebar Component
 * Dynamically renders navigation links based on user roles.
 */
export default function Sidebar() {
  const user = getUser();

  return (
    <div className="sidebar">
      <h2>HPC Portal</h2>

      {/* Basic links for all users */}
     
      <Link to="/">Dashboard</Link>
      <Link to="/submit">Submit Job</Link>
      <Link to="/jobs">Job Queue</Link>

      {/* Navigation for Admin only */}
      {user?.role === "admin" && (
        <Link to="/nodes">Node Map</Link>
      )}

      {/* Administrative links - Protected: Admin only */}
      {user?.role === "admin" && (
        <>
          <Link to="/audit">Audit Logs</Link>
          <Link to="/users">User Management</Link>
          {/* New link for pending user approvals */}
          <Link to="/pending">Pending Requests</Link> 
        </>
      )}

      <Link to="/profile">Profile</Link>
    </div>
  );
}
