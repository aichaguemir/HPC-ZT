import { Navigate } from "react-router-dom";
import { getUser } from "../store/auth";

export default function ProtectedRoute({ children, allowedRoles }) {
  const user = getUser();

  if (!allowedRoles.includes(user.role)) {
    return <Navigate to="/" />;
  }

  return children;
}
