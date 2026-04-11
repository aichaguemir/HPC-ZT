import React from "react";
import { useNavigate } from "react-router-dom";
import { getUser } from "../../store/auth"; 

/**
 * Topbar Component
 * Displays current session info and logout functionality.
 */
export default function Topbar() {
  const navigate = useNavigate();
  

  const user = getUser(); 

  const handleLogout = () => {
    // Clear tokens/session (Optional: add your clearToken function here)
    localStorage.removeItem("token"); 
    console.log("User logged out");
    navigate("/login");
  };

  return (
    <div className="topbar">

      <h3>Welcome, {user?.username || "Guest"}</h3> 
      
      <button className="logout-btn" onClick={handleLogout}>
        Logout
      </button>
    </div>
  );
}
