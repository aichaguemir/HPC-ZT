import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

// Layout and Security components
import AppShell from "./components/layout/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";

// Auth logic from your store
import { isAuthenticated } from "./store/auth";

// Page Components
import Dashboard from "./pages/Dashboard/index";
import SubmitJob from "./pages/SubmitJob/index";
import JobQueue from "./pages/JobQueue/index";
import NodeMap from "./pages/NodeMap/index";
import Profile from "./pages/Profile/index";
import Login from "./pages/Login/index";
import Register from "./pages/Register/index";
import PendingApproval from "./pages/Register/PendingApproval"; 
import AuditLog from "./pages/AuditLog/index";
import Users from "./pages/Users/index";
import PendingRequests from "./pages/Users/pending/index";

/**
 * Main Application Component
 * Handles Global Routing and Authentication Guards
 */
export default function App() {
  const isAuth = isAuthenticated();

  return (
    <BrowserRouter>
      <Routes>
        {/* --- PUBLIC ROUTES --- */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/pending-approval" element={<PendingApproval />} />

        {/* --- PROTECTED ROUTES (WITH LAYOUT) --- */}
        <Route
          path="/"
          element={
            isAuth ? (
              <AppShell />
            ) : (
              <Navigate to="/login" replace />
            )
          }
        >
          {/* 1. SHARED ROUTES: Accessible by any authenticated user */}
          <Route index element={<Dashboard />} />
          <Route path="profile" element={<Profile />} />
          <Route path="jobs" element={<JobQueue />} />
          <Route path="submit" element={<SubmitJob />} />

          {/* 2. ADMIN & ELEVATED ROUTES: Protected via specific roles */}
          <Route element={<ProtectedRoute allowedRoles={["admin"]} />}>
            <Route path="nodes" element={<NodeMap />} />
            <Route path="audit" element={<AuditLog />} />
            <Route path="users" element={<Users />} />
            <Route path="pending" element={<PendingRequests />} />
          </Route>
        </Route>

        {/* --- CATCH-ALL ROUTE --- */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
