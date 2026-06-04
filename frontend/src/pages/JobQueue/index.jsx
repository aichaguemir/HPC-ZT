import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { getToken } from "../../store/auth";

export default function JobQueue() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");

  const [showModal, setShowModal] = useState(false);
  const [currentOutput, setCurrentOutput] = useState("");
  const [selectedJobId, setSelectedJobId] = useState(null);

  const [page, setPage] = useState(1);
  const jobsPerPage = 5;

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const token = getToken();
     
      const res = await axios.get("https://localhost/api/v1/jobs/", {
        headers: { Authorization: `Bearer ${token}` }
      });

      console.log("Jobs fetched from API:", res.data);

      const jobsList = res.data.jobs || [];
      setJobs(jobsList);

      jobsList.forEach(job => {
        if (job.status === "PEND" || job.status === "RUN") {
          updateSingleJobStatus(job.job_id);
        }
      });
    } catch (err) {
      console.error("Fetch Error:", err);
      setError("Failed to sync with HPC cluster.");
    } finally {
      setLoading(false);
    }
  }, []);

  const updateSingleJobStatus = async (jobId) => {
    try {
      const token = getToken();
    
      const res = await axios.get(`https://localhost/api/v1/jobs/${jobId}/status`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setJobs(prevJobs =>
        prevJobs.map(j => (j.job_id === jobId ? { ...j, status: res.data.status } : j))
      );
    } catch (err) {
      console.error(`Status check failed for #${jobId}`);
    }
  };

  const cleanLogText = (text) => {
    if (!text) return "No content available.";
    return text
      .split('\n')
      .filter(line => {
        const l = line.trim();
        return !l.startsWith("Read file <") && !l.startsWith("PS:") && l !== "";
      })
      .join('\n');
  };

  const fetchJobOutput = async (jobId) => {
    try {
      setSelectedJobId(jobId);
      const token = getToken();
      
      const res = await axios.get(`https://localhost/api/v1/jobs/${jobId}/output`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      setCurrentOutput(cleanLogText(res.data.output));
      setShowModal(true);
    } catch (err) {
      alert("Could not retrieve job output.");
    }
  };

  const fetchJobError = async (jobId) => {
    try {
      const token = getToken();
   
      const res = await axios.get(`https://localhost/api/v1/jobs/${jobId}/error`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      const cleanedError = cleanLogText(res.data.error);
      alert(`Job #${jobId} Error Log:\n\n${cleanedError}`);
    } catch (err) {
      alert("Could not retrieve error logs.");
    }
  };

  const cancelJob = async (id) => {
    if (!window.confirm(`Are you sure you want to cancel job #${id}?`)) return;
    try {
      const token = getToken();
     
      await axios.delete(`https://localhost/api/v1/jobs/${id}/cancel`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      alert("Cancellation request sent.");
      fetchJobs();
    } catch (err) {
      alert("Error cancelling job.");
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 30000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const renderStatus = (status) => {
    const s = status?.toUpperCase() || "UNKNOWN";
    let statusClass = "status-badge ";
    if (s === "RUN" || s === "ACTIVE") statusClass += "badge-active";
    else if (s === "PEND" || s === "SUBMITTED" || s === "QUEUED") statusClass += "badge-pending";
    else if (s === "DONE" || s === "FINISHED") statusClass += "badge-done";
    else if (s === "EXIT" || s === "FAILED") statusClass += "badge-exit";
    else statusClass += "badge-unknown";

    return (
      <div className={statusClass}>
        <span className="badge-dot"></span>
        <span className="badge-text">{s}</span>
      </div>
    );
  };

  const filteredJobs = jobs.filter(job => {
    const matchSearch = String(job.job_id).includes(search);
    const matchFilter = filter === "all" || job.status.toLowerCase() === filter.toLowerCase();
    return matchSearch && matchFilter;
  });

  const currentJobs = filteredJobs.slice((page - 1) * jobsPerPage, page * jobsPerPage);
  const totalPages = Math.ceil(filteredJobs.length / jobsPerPage);

  return (
    <div className="job-queue-wrapper">
      <div className="header-actions">
        <h1>HPC Job Monitor</h1>

        {error && <span style={{ color: "#dc2626", marginRight: "15px", fontWeight: "bold" }}>{error}</span>}
        <button onClick={fetchJobs} className="btn-refresh-pro">
          {loading ? "Syncing..." : "Refresh Status"}
        </button>
      </div>

      <div className="controls">
        <input
          className="search-input"
          placeholder="Filter by Job ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select className="filter-select" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All Jobs</option>
          <option value="run">Running</option>
          <option value="pend">Pending</option>
          <option value="exit">Finished/Failed</option>
        </select>
      </div>

      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Status</th>
              <th>Queue</th>
              <th>Cores</th>
              <th>Submitted Date</th>
              <th>Management</th>
            </tr>
          </thead>
          <tbody>
            {currentJobs.length === 0 ? (
              <tr><td colSpan="6" className="no-data">No jobs found.</td></tr>
            ) : (
              currentJobs.map(job => (
                <tr key={job.job_id}>
                  <td className="job-id-cell">#{job.job_id}</td>
                  <td>{renderStatus(job.status)}</td>
                  <td><span className="queue-tag">{job.queue}</span></td>
                  <td>{job.cores} <small>CPUs</small></td>
                  <td className="date-cell">{new Date(job.submitted).toLocaleString()}</td>
                  <td>
                    <div style={{ display: "flex", gap: "8px" }}>
                      {(job.status === "RUN" || job.status === "PEND") && (
                        <button className="btn-cancel-pro" onClick={() => cancelJob(job.job_id)}>Cancel</button>
                      )}
                      {(job.status === "EXIT" || job.status === "FAILED") && (
                        <button className="btn-error-pro" onClick={() => fetchJobError(job.job_id)}>View Error</button>
                      )}
                      {(job.status === "DONE" || job.status === "FINISHED") && (
                        <button className="no-action clickable" onClick={() => fetchJobOutput(job.job_id)}>View Output</button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          {[...Array(totalPages)].map((_, i) => (
            <button key={i} className={`page-node ${page === i + 1 ? "active" : ""}`} onClick={() => setPage(i + 1)}>{i + 1}</button>
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Output Log - Job #{selectedJobId}</h3>
              <button className="close-btn" onClick={() => setShowModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <pre style={{ backgroundColor: "#1a202c", color: "#cbd5e0", padding: "15px", borderRadius: "8px", overflowX: "auto" }}>
                {currentOutput}
              </pre>
            </div>
            <div className="modal-footer"><button onClick={() => setShowModal(false)}>Close</button></div>
          </div>
        </div>
      )}
    </div>
  );
}
