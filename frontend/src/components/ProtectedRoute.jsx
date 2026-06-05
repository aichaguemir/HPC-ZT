import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { getUser, isAuthenticated, isMfaVerified } from "../store/auth";

export default function ProtectedRoute({ allowedRoles }) {
  const user = getUser();
  const isAuth = isAuthenticated();

  if (!isAuth || !user) {
    return <Navigate to="/login" replace />;
  }

  if (!isMfaVerified()) {
    return <Navigate to="/mfa" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
