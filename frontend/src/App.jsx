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
  
  // Checking authentication status from the store
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
          {/* 1. SHARED ROUTES: Accessible by Student, Researcher, Admin */}
          <Route index element={<Dashboard />} />
          <Route path="profile" element={<Profile />} />
          <Route path="jobs" element={<JobQueue />} />
          <Route path="submit" element={<SubmitJob />} />

          {/* 2. ELEVATED ROUTES: Restricted to Admins and Researchers only */}
          <Route
            path="nodes"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <NodeMap />
              </ProtectedRoute>
            }
          />

          {/* 3. ADMIN ONLY ROUTES: Access Management, Logs, and Approval queue */}
          <Route
            path="audit"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <AuditLog />
              </ProtectedRoute>
            }
          />
          <Route
            path="users"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <Users />
              </ProtectedRoute>
            }
          />
          {/* NEW: Admin page to approve new user registrations */}
          <Route
            path="pending"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <PendingRequests />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* --- CATCH-ALL ROUTE --- */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
