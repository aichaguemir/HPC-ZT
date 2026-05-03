import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { getUser, isAuthenticated } from "../store/auth";

/**
 * ProtectedRoute Component
 * Guards routes by checking authentication and user roles.
 */
export default function ProtectedRoute({ allowedRoles }) {
  const user = getUser();
  const isAuth = isAuthenticated();

  // If not authenticated, redirect to the login page
  if (!isAuth || !user) {
    return <Navigate to="/login" replace />;
  }

  // If the user's role is not authorized, redirect back to the home page
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  // If authorized, render the child routes
  return <Outlet />;
}
