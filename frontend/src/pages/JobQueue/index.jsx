import React, { useEffect, useState, useCallback } from "react";
import api from "../../store/api";

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
      const res = await api.get("/jobs/");
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
      const res = await api.get(`/jobs/${jobId}/status`);
      setJobs(prev =>
        prev.map(j => j.job_id === jobId ? { ...j, status: res.data.status } : j)
      );
    } catch (err) {
      console.error(`Status check failed for #${jobId}`);
    }
  };

  const cleanLogText = (text) => {
    if (!text) return "No content available.";
    return text
      .split("\n")
      .filter(line => {
        const l = line.trim();
        return !l.startsWith("Read file <") && !l.startsWith("PS:") && l !== "";
      })
      .join("\n");
  };

  const fetchJobOutput = async (jobId) => {
    try {
      setSelectedJobId(jobId);
      const res = await api.get(`/jobs/${jobId}/output`);
      setCurrentOutput(cleanLogText(res.data.output));
      setShowModal(true);
    } catch (err) {
      alert("Could not retrieve job output.");
    }
  };

  const downloadJobOutput = async (jobId) => {
    try {
      const res = await api.get(`/jobs/${jobId}/output`);
      const cleaned = cleanLogText(res.data.output);
      const blob = new Blob([cleaned], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `job_${jobId}_output.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("Could not download job output.");
    }
  };

  const fetchJobError = async (jobId) => {
    try {
      const res = await api.get(`/jobs/${jobId}/error`);
      const cleanedError = cleanLogText(res.data.error);
      alert(`Job #${jobId} Error Log:\n\n${cleanedError}`);
    } catch (err) {
      alert("Could not retrieve error logs.");
    }
  };

  const cancelJob = async (id) => {
    if (!window.confirm(`Are you sure you want to cancel job #${id}?`)) return;
    try {
      await api.delete(`/jobs/${id}/cancel`);
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
    let cls = "status-badge ";
    if      (s === "RUN"  || s === "ACTIVE")                      cls += "badge-active";
    else if (s === "PEND" || s === "SUBMITTED" || s === "QUEUED") cls += "badge-pending";
    else if (s === "DONE" || s === "FINISHED")                    cls += "badge-done";
    else if (s === "EXIT" || s === "FAILED")                      cls += "badge-exit";
    else                                                           cls += "badge-pending";
    return (
      <div className={cls}>
        <span className="badge-dot" />
        <span>{s}</span>
      </div>
    );
  };

  const filteredJobs = (jobs || []).filter(job => {
    const matchSearch = String(job.job_id).includes(search);
    const matchFilter = filter === "all" || job.status.toLowerCase() === filter.toLowerCase();
    return matchSearch && matchFilter;
  });

  const currentJobs = filteredJobs.slice((page - 1) * jobsPerPage, page * jobsPerPage);
  const totalPages  = Math.ceil(filteredJobs.length / jobsPerPage);

  const isDone = (status) => status === "DONE" || status === "FINISHED";

  return (
    <div className="job-queue-wrapper">

      {/* ── Header ── */}
      <div className="header-actions" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <h1>HPC Job Monitor</h1>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {error && <span style={{ color: "#dc2626", fontWeight: 600, fontSize: 13 }}>{error}</span>}
          <button onClick={fetchJobs} className="btn-refresh-pro" disabled={loading}>
            {loading ? "Syncing..." : "Refresh Status"}
          </button>
        </div>
      </div>

      {/* ── Controls ── */}
      <div className="controls" style={{ marginBottom: 16 }}>
        <input
          className="search-input"
          placeholder="Filter by Job ID..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
        />
        <select
          className="filter-select"
          value={filter}
          onChange={(e) => { setFilter(e.target.value); setPage(1); }}
        >
          <option value="all">All Jobs</option>
          <option value="run">Running</option>
          <option value="pend">Pending</option>
          <option value="done">Done</option>
          <option value="exit">Failed / Exit</option>
        </select>
      </div>

      {/* ── Loading ── */}
      {loading && (
        <div style={{ textAlign: "center", padding: "40px", color: "#64748b" }}>
          Syncing with HPC cluster...
        </div>
      )}

      {/* ── Table ── */}
      {!loading && (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Status</th>
                <th>Queue</th>
                <th>Cores</th>
                <th>Submitted</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {currentJobs.length === 0 ? (
                <tr>
                  <td colSpan="6" style={{ textAlign: "center", padding: "40px", color: "#64748b" }}>
                    No jobs found.
                  </td>
                </tr>
              ) : (
                currentJobs.map(job => (
                  <tr key={job.job_id}>
                    <td style={{ fontWeight: 600 }}>#{job.job_id}</td>
                    <td>{renderStatus(job.status)}</td>
                    <td><span className="queue-tag">{job.queue}</span></td>
                    <td>{job.cores} <small style={{ color: "#94a3b8" }}>CPUs</small></td>
                    <td style={{ color: "#64748b", fontSize: 13 }}>
                      {job.submitted ? new Date(job.submitted).toLocaleString() : "—"}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 8 }}>
                        {(job.status === "RUN" || job.status === "PEND") && (
                          <button className="btn-cancel-pro" onClick={() => cancelJob(job.job_id)}>
                            Cancel
                          </button>
                        )}
                        {(job.status === "EXIT" || job.status === "FAILED") && (
                          <button className="btn-error-pro" onClick={() => fetchJobError(job.job_id)}>
                            View Error
                          </button>
                        )}
                        {isDone(job.status) && (
                          <>
                            <button
                              className="no-action clickable"
                              onClick={() => fetchJobOutput(job.job_id)}
                            >
                              View Output
                            </button>
                            <button
                              className="btn-download-pro"
                              onClick={() => downloadJobOutput(job.job_id)}
                              title="Download output as .txt"
                            >
                              ⬇ Download
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="pagination">
          {[...Array(totalPages)].map((_, i) => (
            <button
              key={i}
              className={`page-node ${page === i + 1 ? "active" : ""}`}
              onClick={() => setPage(i + 1)}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}

      {/* ── Output Modal ── */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Output Log — Job #{selectedJobId}</h3>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button
                  className="btn-download-pro"
                  onClick={() => downloadJobOutput(selectedJobId)}
                  title="Download output as .txt"
                >
                  ⬇ Download
                </button>
                <button className="close-btn" onClick={() => setShowModal(false)}>×</button>
              </div>
            </div>
            <div className="modal-body">
              <pre>{currentOutput}</pre>
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowModal(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
