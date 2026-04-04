import React from "react";
import { useNavigate } from "react-router-dom";

export default function Topbar() {
  const navigate = useNavigate();

  const handleLogout = () => {
    // 1️⃣ هنا تقدر تمسح الـ token أو أي session
    console.log("User logged out");

    // 2️⃣ بعد logout، روح لصفحة login
    navigate("/login");
  };

  return (
    <div className="topbar">
      <h3>Welcome, Yasmine</h3>
      <button className="logout-btn" onClick={handleLogout}>
        Logout
      </button>
    </div>
  );
}
