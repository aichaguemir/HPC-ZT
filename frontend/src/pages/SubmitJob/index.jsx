
import React, { useState } from "react";
import api from "../../store/api";
import MfaModal from "./MfaModal";

export default function SubmitJob() {
  const [file, setFile] = useState(null);
  const [jobType, setJobType] = useState("serial");
  const [cores, setCores] = useState(1);
  const [memory, setMemory] = useState(1024);
  const [queue, setQueue] = useState("low_priority");
  const [wallTimeHours, setWallTimeHours] = useState(1);
  const [wallTimeMinutes, setWallTimeMinutes] = useState(0);
  const [mpiProcesses, setMpiProcesses] = useState(2);
  const [mpiPtile, setMpiPtile] = useState(1);
  const [loading, setLoading] = useState(false);
  const [serverError, setServerError] = useState("");
  const [showMfaModal, setShowMfaModal] = useState(false);
  const [pendingFormData, setPendingFormData] = useState(null);

  const memoryOptions = [
    { value: 100, label: "100 MB (Minimum)" },
    { value: 512, label: "512 MB (Small Job)" },
    { value: 1024, label: "1024 MB (1 GB)" },
    { value: 2048, label: "2048 MB (2 GB)" },
    { value: 4096, label: "4096 MB (Max for Student)" },
    { value: 8192, label: "8192 MB (Researcher Only)" },
    { value: 16000, label: "16000 MB (Researcher Only)" },
    { value: 31900, label: "31900 MB (Admin/Researcher Max)" },
  ];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setServerError("");
    if (!file) {
      setServerError("Please upload a script file first!");
      return;
    }

    if (jobType === "mpi") {
      if (mpiProcesses < 2) {
        setServerError("MPI requires at least 2 processes.");
        return;
      }
      if (mpiPtile < 1) {
        setServerError("Processes per node (ptile) must be at least 1.");
        return;
      }
      if (mpiProcesses % mpiPtile !== 0) {
        setServerError(`Total processes (${mpiProcesses}) must be divisible by processes per node (${mpiPtile}).`);
        return;
      }
    }

    setLoading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("memory", parseInt(memory));
    formData.append("queue", queue);
    formData.append("wall_time_hours", parseInt(wallTimeHours));
    formData.append("wall_time_minutes", parseInt(wallTimeMinutes));
    formData.append("job_type", jobType);

    if (jobType === "serial") {
      formData.append("cores", parseInt(cores));
    } else {
      formData.append("cores", parseInt(mpiProcesses));
      formData.append("mpi_processes", parseInt(mpiProcesses));
      formData.append("mpi_ptile", parseInt(mpiPtile));
    }

    try {
      const res = await api.post("/jobs/submit", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      alert(`Job submitted! ID: ${res.data.job_id}`);
      setFile(null);
      setPendingFormData(null);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && detail.code === "mfa_required") {
        const clone = new FormData();
        clone.append("file", file);
        if (jobType === "serial") clone.append("cores", parseInt(cores));
        else {
          clone.append("cores", parseInt(mpiProcesses));
          clone.append("mpi_processes", parseInt(mpiProcesses));
          clone.append("mpi_ptile", parseInt(mpiPtile));
        }
        clone.append("memory", parseInt(memory));
        clone.append("queue", queue);
        clone.append("wall_time_hours", parseInt(wallTimeHours));
        clone.append("wall_time_minutes", parseInt(wallTimeMinutes));
        clone.append("job_type", jobType);
        setPendingFormData(clone);
        await api.post("/auth/mfa/send-code");
        setShowMfaModal(true);
        return;
      }
      setServerError(typeof detail === 'string' ? detail : (detail?.message || "Submission failed"));
    } finally {
      setLoading(false);
    }
  };

  const onMfaSuccess = async () => {
    setShowMfaModal(false);
    setLoading(true);
    try {
      const res = await api.post("/jobs/submit", pendingFormData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      alert(`Job submitted! ID: ${res.data.job_id}`);
      setFile(null);
      setPendingFormData(null);
    } catch (err) {
      setServerError("Submission failed after MFA verification.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1>Submit Job</h1>
      <form className="card" onSubmit={handleSubmit}>
        {serverError && (
          <div style={{ backgroundColor: "#fff5f5", color: "#dc3545", padding: "10px", borderRadius: "5px", marginBottom: "15px" }}>
            {serverError}
          </div>
        )}

        <label className="label">Upload Script (.sh, .py)</label>
        <input type="file" accept=".sh,.py" onChange={(e) => { setFile(e.target.files[0]); setServerError(""); }} />
        {file && <p style={{ marginTop: "5px", color: "#28a745", fontSize: "13px" }}>Selected: {file.name}</p>}

        <hr style={{ margin: "20px 0" }} />

        <label className="label">Job Type</label>
        <select value={jobType} onChange={(e) => setJobType(e.target.value)}>
          <option value="serial">Serial / Multicore</option>
          <option value="mpi">MPI (Multi‑node)</option>
        </select>

        {jobType === "serial" && (
          <>
            <label className="label">CPU Cores (1 - 16)</label>
            <input type="number" min="1" max="16" value={cores} onChange={(e) => setCores(e.target.value)} />
          </>
        )}

        {jobType === "mpi" && (
          <>
            <label className="label">Total MPI Processes (ranks)</label>
            <input type="number" min="2" step="1" value={mpiProcesses} onChange={(e) => setMpiProcesses(e.target.value)} />
            <label className="label">Processes per Node (ptile)</label>
            <input type="number" min="1" step="1" value={mpiPtile} onChange={(e) => setMpiPtile(e.target.value)} />
            <p style={{ fontSize: "12px", color: "#666", marginTop: "-10px" }}>
              Total processes must be divisible by ptile. Each node runs ptile ranks.
            </p>
          </>
        )}

        <label className="label">Memory (RAM)</label>
        <select value={memory} onChange={(e) => setMemory(e.target.value)}>
          {memoryOptions.map((opt) => (<option key={opt.value} value={opt.value}>{opt.label}</option>))}
        </select>

        <label className="label">Queue (Priority)</label>
        <select value={queue} onChange={(e) => setQueue(e.target.value)}>
          <option value="low_priority">Low Priority</option>
          <option value="medium_priority">Medium Priority</option>
          <option value="high_priority">High Priority</option>
        </select>

        <div style={{ marginTop: "15px" }}>
          <label className="label">Wall Time: Hours</label>
          <input type="number" min="0" value={wallTimeHours} onChange={(e) => setWallTimeHours(e.target.value)} />
        </div>
        <div style={{ marginTop: "15px" }}>
          <label className="label">Wall Time: Minutes</label>
          <input type="number" min="0" max="59" value={wallTimeMinutes} onChange={(e) => setWallTimeMinutes(e.target.value)} />
        </div>

        <button className="btn" style={{ marginTop: "30px", width: "100%" }} disabled={loading}>
          {loading ? "Processing..." : "Submit Job to Cluster"}
        </button>
      </form>

      <MfaModal isOpen={showMfaModal} onClose={() => setShowMfaModal(false)} onSuccess={onMfaSuccess} />
    </div>
  );
}
