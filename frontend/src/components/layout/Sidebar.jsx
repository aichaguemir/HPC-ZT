import { getUser } from "../../store/auth";

export default function Sidebar() {
  const user = getUser();

  return (
    <div className="sidebar">
      <h2>HPC Portal</h2>

      <a href="/">Dashboard</a>
     <a href="/submit">Submit Job</a>
      <a href="/jobs">Job Queue</a>

      {/* admin + researcher */}
      {(user.role === "admin" || user.role === "researcher") && (
        <a href="/nodes">Node Map</a>
      )}

      {/* admin only */}
      {user.role === "admin" && (
        <>
    <a href="/audit">Audit Logs</a>
    <a href="/users">Users</a>
  </>
      )}

      <a href="/profile">Profile</a>
    </div>
  );
}
