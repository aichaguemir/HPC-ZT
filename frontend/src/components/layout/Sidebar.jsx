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
      <a href="/">Dashboard</a>
      <a href="/submit">Submit Job</a>
      <a href="/jobs">Job Queue</a>

      {/* Navigation for Admin and Researcher only */}
      {(user.role === "admin" ) && (
        <a href="/nodes">Node Map</a>
      )}

      {/* Administrative links - Protected: Admin only */}
      {user.role === "admin" && (
        <>
          <a href="/audit">Audit Logs</a>
          <a href="/users">User Management</a>
          {/* New link for pending user approvals */}
          <a href="/pending">Pending Requests</a> 
        </>
      )}

      <a href="/profile">Profile</a>
    </div>
  );
}
