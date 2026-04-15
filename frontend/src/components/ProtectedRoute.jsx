import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getUser, isAuthenticated } from "../store/auth";

export default function ProtectedRoute({ children, allowedRoles }) {
  const user = getUser();
  const isAuth = isAuthenticated();
  const location = useLocation();


  if (!isAuth || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  
  console.log(`[Guard] User: ${user.username} | MFA: ${user.totp_enabled} | Path: ${location.pathname}`);


  const needsMfaSetup = user.is_active && (user.totp_enabled === false || user.totp_enabled === undefined);

  if (needsMfaSetup) {
  
    if (location.pathname !== "/mfa-setup") {
      return <Navigate to="/mfa-setup" replace />;
    }
  }


  if (user.totp_enabled === true && location.pathname === "/mfa-setup") {
    return <Navigate to="/" replace />;
  }


  if (allowedRoles && !allowedRoles.includes(user.role)) {
 
    console.warn(`[Guard] Access Denied for role: ${user.role}`);
    return <Navigate to="/" replace />;
  }


  return children;
}
