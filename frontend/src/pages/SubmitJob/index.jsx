import React, { useState, useEffect } from "react";
import api from "../../store/api";
import SerialForm from "./SerialForm";
import MPIForm from "./MPIForm";
import "./styles.css";

export default function SubmitJob() {
  const [jobType, setJobType] = useState("serial");
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPolicy = async () => {
      try {
        const res = await api.get("/jobs/my-policy");
        console.log("allowed_queues:", res.data.allowed_queues);
        setPolicy(res.data);
      } catch {
        setPolicy({
          max_cores: 4,
          max_memory_mb: 2048,
          allowed_queues: [{ queue_name: "normal" }],
        });
      } finally {
        setLoading(false);
      }
    };
    fetchPolicy();
  }, []);

  if (loading)
    return (
      <div className="submit-page">
        <p className="loading-text">Loading configuration…</p>
      </div>
    );

  return (
    <div className="submit-page">
      <div className="page-header">
        <h1>Submit new job</h1>
        <p>Configure and dispatch your compute job to the cluster</p>
      </div>

      <div className="seg-control">
        <button
          className={`seg-btn ${jobType === "serial" ? "active" : ""}`}
          onClick={() => setJobType("serial")}
        >
          <i className="ti ti-file-code" aria-hidden="true" />
          Serial job
        </button>
        <button
          className={`seg-btn ${jobType === "mpi" ? "active" : ""}`}
          onClick={() => setJobType("mpi")}
        >
          <i className="ti ti-topology-star-3" aria-hidden="true" />
          MPI job
        </button>
      </div>

      <div className="form-card">
        {jobType === "serial" ? (
          <SerialForm policy={policy} />
        ) : (
          <MPIForm policy={policy} />
        )}
      </div>
    </div>
  );
}
