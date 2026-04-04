import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import AppShell from "./components/layout/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";

import Dashboard from "./pages/Dashboard/index";
import SubmitJob from "./pages/SubmitJob/index";
import JobQueue from "./pages/JobQueue/index";
import NodeMap from "./pages/NodeMap/index";
import Profile from "./pages/Profile/index";
import Login from "./pages/Login/index";
import Register from "./pages/Register/index";
import AuditLog from "./pages/AuditLog/index";
import Users from "./pages/Users/index";
// fake auth
const fakeAuth = {
  isAuthenticated: true
};

export default function App() {
  return (
    <BrowserRouter>
      <Routes>

        {/* PUBLIC */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* PROTECTED LAYOUT */}
        <Route
          path="/"
          element={
            fakeAuth.isAuthenticated ? (
              <AppShell />
            ) : (
              <Navigate to="/login" />
            )
          }
        >

          {/* Dashboard */}
          <Route index element={<Dashboard />} />

          {/* Submit Job */}
          <Route path="submit" element={<SubmitJob />} />

          {/* Job Queue */}
          <Route path="jobs" element={<JobQueue />} />

          {/* Node Map (admin + researcher) */}
          <Route
            path="nodes"
            element={
              <ProtectedRoute allowedRoles={["admin", "researcher"]}>
                <NodeMap />
              </ProtectedRoute>
            }
          />

          {/* Audit Logs (admin only) */}
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

          {/* Profile */}
          <Route path="profile" element={<Profile />} />

        </Route>

      </Routes>
    </BrowserRouter>
  );
}
