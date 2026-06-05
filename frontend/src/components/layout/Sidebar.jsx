import React from "react";
import { Link, useLocation } from "react-router-dom";
import { getUser } from "../../store/auth";

export default function Sidebar() {
  const user = getUser();
  const { pathname } = useLocation();
  const isActive = (path) => pathname === path ? "active" : "";

  return (
    <div className="sidebar">
      <h2>HPC Portal</h2>
      <Link to="/dashboard"        className={isActive("/dashboard")}>Dashboard</Link>
      <Link to="/dashboard/submit" className={isActive("/dashboard/submit")}>Submit Job</Link>
      <Link to="/dashboard/jobs"   className={isActive("/dashboard/jobs")}>Job Queue</Link>

      {user?.role !== "admin" && (
        <Link to="/dashboard/messages" className={isActive("/dashboard/messages")}>Messages</Link>
      )}

      {user?.role === "admin" && (
        <>
          <Link to="/dashboard/nodes"    className={isActive("/dashboard/nodes")}>Node Map</Link>
          <Link to="/dashboard/audit"    className={isActive("/dashboard/audit")}>Audit Logs</Link>
          <Link to="/dashboard/users"    className={isActive("/dashboard/users")}>User Management</Link>
          <Link to="/dashboard/pending"  className={isActive("/dashboard/pending")}>Pending Requests</Link>
          <Link to="/dashboard/messages" className={isActive("/dashboard/messages")}>Messages</Link>
        </>
      )}

      <Link to="/dashboard/profile" className={isActive("/dashboard/profile")}>Profile</Link>
    </div>
  );
}
