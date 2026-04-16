import React from "react";
import { Navigate } from "react-router-dom";
import { getUser, isAuthenticated } from "../store/auth";

export default function ProtectedRoute({ children, allowedRoles }) {
  const user = getUser();
  const isAuth = isAuthenticated();


  if (!isAuth || !user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

 
  return children;
}
