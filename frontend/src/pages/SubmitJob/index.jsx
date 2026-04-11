import React, { useState } from "react";
import axios from "axios";
import { getToken } from "../../store/auth";

export default function SubmitJob() {
  const [file, setFile] = useState(null);
  const [cores, setCores] = useState(1);
  const [memory, setMemory] = useState(1024);
  const [queue, setQueue] = useState("low_priority");
  const [wallTimeHours, setWallTimeHours] = useState(1);
  const [wallTimeMinutes, setWallTimeMinutes] = useState(0);
  
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState(""); 

  const handleSubmit = async (e) => {
    e.preventDefault();
    setServerError(""); 

    if (!file) {
      setServerError("Please upload a script file first!");
      return;
    }

    setLoading(true);
    const token = getToken();

    const formData = new FormData();
    formData.append("file", file);
    formData.append("cores", parseInt(cores));
    formData.append("memory", parseInt(memory));
    formData.append("queue", queue);
    formData.append("wall_time_hours", parseInt(wallTimeHours));
    formData.append("wall_time_minutes", parseInt(wallTimeMinutes));

    try {
      const res = await axios.post("http://localhost:8000/api/v1/jobs/submit", formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data",
        },
      });
      alert(`Job submitted! ID: ${res.data.job_id}`);
      setFile(null);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setServerError(typeof detail === 'string' ? detail : (detail?.message || "Submission failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>Submit Job</h1>

      <form className="card" onSubmit={handleSubmit}>
        
     
        {serverError && (
          <div style={{ 
            backgroundColor: "#fff5f5", 
            color: "#dc3545", 
            padding: "10px", 
            borderRadius: "5px", 
            border: "1px solid #dc3545", 
            marginBottom: "15px",
            fontSize: "14px",
            fontWeight: "bold"
          }}>
            {serverError}
          </div>
        )}

        {/* Upload File */}
        <label className="label">Upload Script (.sh, .py)</label>
        <input
          type="file"
          accept=".sh,.py"
          onChange={(e) => {
            setFile(e.target.files[0]);
            setServerError(""); 
          }}
          style={{ 
            border: !file && serverError ? "2px solid #dc3545" : "",
            padding: "8px",
            width: "100%"
          }}
        />
        {file ? (
          <p style={{ marginTop: "5px", color: "#28a745", fontSize: "13px" }}>Selected: {file.name}</p>
        ) : (
          <p style={{ marginTop: "5px", color: "#888", fontSize: "12px" }}>No script selected yet.</p>
        )}

        <hr style={{ margin: "20px 0", border: "0.5px solid #eee" }} />

        {/* Resources */}
        <label className="label">CPU Cores</label>
        <input type="number" min="1" value={cores} onChange={(e) => setCores(e.target.value)} />

        <label className="label">Memory (MB)</label>
        <input type="number" min="512" value={memory} onChange={(e) => setMemory(e.target.value)} />

        <label className="label">Queue (Priority)</label>
        <select value={queue} onChange={(e) => setQueue(e.target.value)}>
          <option value="low_priority">Low Priority</option>
          <option value="medium_priority">Medium Priority</option>
          <option value="high_priority">High Priority</option>
        </select>

        {/* Execution Time separated */}
        <div style={{ marginTop: "15px" }}>
          <label className="label">Wall Time: Hours</label>
          <input 
            type="number" 
            min="0" 
            placeholder="0"
            value={wallTimeHours} 
            onChange={(e) => setWallTimeHours(e.target.value)} 
          />
        </div>

        <div style={{ marginTop: "15px" }}>
          <label className="label">Wall Time: Minutes</label>
          <input 
            type="number" 
            min="0" 
            max="59" 
            placeholder="0"
            value={wallTimeMinutes} 
            onChange={(e) => setWallTimeMinutes(e.target.value)} 
          />
        </div>

        <button className="btn" style={{ marginTop: "30px", width: "100%" }} disabled={loading}>
          {loading ? "Processing..." : "Submit Job to Cluster"}
        </button>
      </form>
    </div>
  );
}
