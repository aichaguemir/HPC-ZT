import React, { useEffect, useState } from "react";

export default function JobQueue() {
  const [jobs, setJobs] = useState([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");

  // pagination
  const [page, setPage] = useState(1);
  const jobsPerPage = 5;

  useEffect(() => {
    const fakeJobs = [
      { id: 1, name: "Job A", cpu: 4, status: "RUNNING", user: "yasmine" },
      { id: 2, name: "Job B", cpu: 2, status: "PENDING", user: "ali" },
      { id: 3, name: "Job C", cpu: 8, status: "FAILED", user: "yasmine" },
      { id: 4, name: "Job D", cpu: 1, status: "RUNNING", user: "ali" },
      { id: 5, name: "Job E", cpu: 16, status: "PENDING", user: "yasmine" },
    ];
    setJobs(fakeJobs);
  }, []);

  const killJob = (id) => {
    const updated = jobs.map(j =>
      j.id === id ? { ...j, status: "failed" } : j
    );

    setJobs(updated);
    localStorage.setItem("jobs", JSON.stringify(updated));
  };

  /* ===== FILTER + SEARCH ===== */
  const filteredJobs = jobs.filter(job => {
    const matchSearch = job.name.toLowerCase().includes(search.toLowerCase());
    const matchFilter = filter === "all" || job.status === filter;
    return matchSearch && matchFilter;
  });

  /* ===== PAGINATION ===== */
  const indexOfLast = page * jobsPerPage;
  const indexOfFirst = indexOfLast - jobsPerPage;
  const currentJobs = filteredJobs.slice(indexOfFirst, indexOfLast);

  const totalPages = Math.ceil(filteredJobs.length / jobsPerPage);

  /* ===== STATUS ICON ===== */
  const getStatusIcon = (status) => {
    if (status === "running") return "🟢";
    if (status === "pending") return "🟡";
    if (status === "failed") return "🔴";
  };

  return (
    <div>
      <h1>Job Queue</h1>

     {/* 🔍 SEARCH + FILTER */}
      <div className="controls">
        <input
          placeholder="Search job..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All</option>
          <option value="running">Running</option>
          <option value="pending">Pending</option>
          <option value="failed">Failed</option>
        </select>
      </div>
      {/* TABLE */}
      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Job Name</th>
              <th>Status</th>
              <th>CPU</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>
            {currentJobs.length === 0 ? (
              <tr>
                <td colSpan="5" style={{ textAlign: "center", padding: 20 }}>
                  No jobs found
                </td>
              </tr>
            ) : (
              currentJobs.map(job => (
                <tr key={job.id}>
                  <td>#{job.id}</td>
                  <td>{job.name}</td>

                  <td>
                    <span className={`badge ${job.status}`}>
                      <span className="icon">
                        {getStatusIcon(job.status)}
                      </span>
                      {job.status}
                    </span>
                  </td>

                  <td>{job.cpu}</td>

                  <td>
                    <button
                      className="btn-danger"
                      onClick={() => killJob(job.id)}
                    >
                      Kill
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>

        </table>
      </div>

      {/* 📄 PAGINATION */}
      <div className="pagination">
        {[...Array(totalPages)].map((_, i) => (
          <div
            key={i}
            className={`page-btn ${page === i + 1 ? "active" : ""}`}
            onClick={() => setPage(i + 1)}
          >
            {i + 1}
          </div>
        ))}
      </div>
    </div>
  );
}
