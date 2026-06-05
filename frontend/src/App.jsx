import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";
import { isAuthenticated, isMfaVerified, getUser } from "./store/auth";
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
import LandingPage from "./pages/LandingPage/LandingPage";
import MFA from "./pages/MFA/index";
import UserMessages from "./pages/Messages/UserMessages";
import AdminMessages from "./pages/Messages/AdminMessages";

function DashboardGuard() {
  const isAuth = isAuthenticated();
  const mfaOk  = isMfaVerified();
  if (!isAuth) return <Navigate to="/login" replace />;
  if (!mfaOk)  return <Navigate to="/mfa" replace />;
  return <AppShell />;
}

function MessagesPage() {
  const user = getUser();
  return user?.role === "admin" ? <AdminMessages /> : <UserMessages />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/pending-approval" element={<PendingApproval />} />
        <Route path="/mfa" element={<MFA />} />

        <Route path="/dashboard" element={<DashboardGuard />}>
          <Route index element={<Dashboard />} />
          <Route path="profile" element={<Profile />} />
          <Route path="jobs" element={<JobQueue />} />
          <Route path="submit" element={<SubmitJob />} />
          <Route path="messages" element={<MessagesPage />} />

          <Route element={<ProtectedRoute allowedRoles={["admin"]} />}>
            <Route path="nodes" element={<NodeMap />} />
            <Route path="audit" element={<AuditLog />} />
            <Route path="users" element={<Users />} />
            <Route path="pending" element={<PendingRequests />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
