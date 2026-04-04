import React, { useState } from "react";

export default function SubmitJob() {
  const [jobName, setJobName] = useState("");
  const [cpu, setCpu] = useState(1);
  const [priority, setPriority] = useState("medium");
  const [time, setTime] = useState("");
  const [file, setFile] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!jobName || !time || !file) {
      alert("Please fill all fields!");
      return;
    }

    const newJob = {
      id: Date.now(),
      name: jobName,
      cpu,
      priority,
      time,
      fileName: file.name,
      status: "PENDING"
    };

    console.log("Job submitted:", newJob);

    alert("Job submitted successfully!");

    // reset
    setJobName("");
    setCpu(1);
    setPriority("medium");
    setTime("");
    setFile(null);
  };

  return (
    <div>
      <h1>Submit Job</h1>

      <form className="card" onSubmit={handleSubmit}>

        {/* Job Name */}
        <label className="label">Job Name</label>
        <input
          type="text"
          placeholder="Enter job name"
          value={jobName}
          onChange={(e) => setJobName(e.target.value)}
        />

        {/* CPU */}
        <label className="label">CPU Cores</label>
        <input
          type="number"
          min="1"
          value={cpu}
          onChange={(e) => setCpu(e.target.value)}
        />

        {/* Priority */}
        <label className="label">Priority</label>
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>

        {/* Time */}
        <label className="label">Execution Time (minutes)</label>
        <input
          type="number"
          placeholder="e.g. 60"
          value={time}
          onChange={(e) => setTime(e.target.value)}
        />

        {/* Upload */}
        <label className="label">Upload Script (.sh)</label>
        <input
          type="file"
          accept=".sh,.py"
          onChange={(e) => setFile(e.target.files[0])}
        />

        {/* File preview */}
        {file && (
          <p style={{ marginTop: "10px", color: "var(--muted)" }}>
             {file.name}
          </p>
        )}

        {/* Button */}
        <button className="btn" style={{ marginTop: "20px" }}>
          Submit Job
        </button>

      </form>
    </div>
  );
}
