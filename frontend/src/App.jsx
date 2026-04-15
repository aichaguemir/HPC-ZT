import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

// Layout and Security components
import AppShell from "./components/layout/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";

// Auth logic
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

// MFA Components (حسب المسار اللي بعثتيه لي)
import MfaSetup from "./components/mfa/MfaSetup";

/**
 * Main Application Component
 */
export default function App() {
  const isAuth = isAuthenticated();

  return (
    <BrowserRouter>
      <Routes>
        {/* --- 1. PUBLIC ROUTES (Accessible without login) --- */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/pending-approval" element={<PendingApproval />} />

        {/* --- 2. MFA SETUP ROUTE --- */}
     
        <Route 
          path="/mfa-setup" 
          element={
            <ProtectedRoute>
               <MfaSetup />
            </ProtectedRoute>
          } 
        />

        {/* --- 3. PROTECTED ROUTES (داخل AppShell والـ Sidebar) --- */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          {/* Shared Routes: Student, Researcher, Admin */}
          <Route index element={<Dashboard />} />
          <Route path="profile" element={<Profile />} />
          <Route path="jobs" element={<JobQueue />} />
          <Route path="submit" element={<SubmitJob />} />

          {/* Elevated Routes: Restricted to Admins/Researchers */}
          <Route
            path="nodes"
            element={
              <ProtectedRoute allowedRoles={["admin", "researcher"]}>
                <NodeMap />
              </ProtectedRoute>
            }
          />

          {/* Admin Only Routes: Access Management, Logs */}
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
          <Route
            path="pending"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <PendingRequests />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* --- 4. CATCH-ALL (Redirect to Login) --- */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
