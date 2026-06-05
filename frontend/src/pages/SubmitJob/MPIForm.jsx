import React, { useState } from "react";
import { getToken, refreshToken } from "../../store/auth";

const memoryOptions = [
  { value: 100,   label: "100 MB (Minimum)" },
  { value: 512,   label: "512 MB (Small job)" },
  { value: 1024,  label: "1024 MB (1 GB)" },
  { value: 2048,  label: "2048 MB (2 GB)" },
  { value: 4096,  label: "4096 MB " },
  { value: 8192,  label: "8192 MB " },
  { value: 16000, label: "16000 MB " },
  { value: 31900, label: "31900 MB " },
];

export default function MPIForm({ policy }) {
  const queues = (policy.allowed_queues || []).map((q) =>
    typeof q === "string" ? q : q.queue_name
  );

  const [formData, setFormData] = useState({
    file: null,
    name: "",
    cores: 16,
    memory: 8192,
    mpi_processes: 8,
    mpi_ptile: 4,
    queue: queues[0] || "",
    wall_time_hours: 2,
    wall_time_minutes: 0,
  });
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const set = (key, val) => setFormData((p) => ({ ...p, [key]: val }));

  const ptileValid =
    formData.mpi_processes > 0 &&
    formData.mpi_ptile > 0 &&
    formData.mpi_processes % formData.mpi_ptile === 0;

  const nodesNeeded = ptileValid
    ? Math.ceil(formData.mpi_processes / formData.mpi_ptile)
    : "—";

  const wallTime = `${String(formData.wall_time_hours).padStart(2, "0")}:${String(
    formData.wall_time_minutes
  ).padStart(2, "0")}`;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = {};
    if (!formData.name.trim()) errs.name = true;
    if (!formData.file) errs.file = true;
    if (!ptileValid) errs.ptile = true;
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setSubmitting(true);

    const data = new FormData();
    data.append("file", formData.file);
    data.append("job_type", "mpi");
    data.append("cores", formData.cores);
    data.append("memory", formData.memory);
    data.append("queue", formData.queue);
    data.append("wall_time_hours", formData.wall_time_hours);
    data.append("wall_time_minutes", formData.wall_time_minutes);
    data.append("mpi_processes", formData.mpi_processes);
    data.append("mpi_ptile", formData.mpi_ptile);

    try {
      await refreshToken();
      const token = getToken();

      const res = await fetch("/api/v1/jobs/submit", {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: data,
      });

      if (!res.ok) {
        const err = await res.json();
        const detail = err.detail;
        const msg = typeof detail === "string"
          ? detail
          : Array.isArray(detail)
          ? detail.map(d => d.msg).join(", ")
          : JSON.stringify(detail);
        throw new Error(msg);
      }

      alert("MPI job submitted successfully!");
    } catch (err) {
      alert(err.message || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="job-form" noValidate>

      <p className="sec-title">Script</p>

      <div className={`field ${errors.file ? "has-err" : ""}`}>
        <label><i className="ti ti-upload" aria-hidden="true" /> Python script</label>
        <input
          type="file"
          accept=".py"
          onChange={(e) => set("file", e.target.files[0])}
        />
        <span className="err-msg">Script required</span>
      </div>

      <div className={`field ${errors.name ? "has-err" : ""}`}>
        <label>Job name</label>
        <input
          type="text"
          placeholder="e.g. mpi-run-01"
          value={formData.name}
          onChange={(e) => set("name", e.target.value)}
        />
        <span className="err-msg">Name required</span>
      </div>

      <hr className="divider" />

      <p className="sec-title">Resources</p>
      <div className="grid-2">
        <div className="field">
          <label>CPU cores (total)</label>
          <input
            type="number"
            min={1}
            max={policy.max_cores}
            value={formData.cores}
            onChange={(e) => set("cores", +e.target.value)}
          />
          <span className="hint">across all nodes</span>
        </div>
        <div className="field">
          <label>Memory</label>
          <select
            value={formData.memory}
            onChange={(e) => set("memory", +e.target.value)}
          >
            {memoryOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <hr className="divider" />

      <p className="sec-title">MPI parameters</p>
      <div className="grid-2">
        <div className="field">
          <label>MPI processes</label>
          <input
            type="number"
            min={2}
            value={formData.mpi_processes}
            onChange={(e) => set("mpi_processes", +e.target.value)}
          />
          <span className="hint">total ranks</span>
        </div>
        <div className={`field ${errors.ptile ? "has-err" : ""}`}>
          <label>Ptile (per host)</label>
          <input
            type="number"
            min={1}
            value={formData.mpi_ptile}
            onChange={(e) => set("mpi_ptile", +e.target.value)}
          />
          <span className="hint">must divide processes evenly</span>
          <span className="err-msg">Must divide processes evenly</span>
        </div>
      </div>

      {!ptileValid && formData.mpi_processes > 0 && formData.mpi_ptile > 0 && (
        <p className="ptile-warn">
          <i className="ti ti-alert-triangle" aria-hidden="true" />
          {formData.mpi_processes} ÷ {formData.mpi_ptile} is not a whole number
        </p>
      )}

      <hr className="divider" />

      <p className="sec-title">Queue &amp; wall time</p>

      <div className="field">
        <label>Queue</label>
        <select
          value={formData.queue}
          onChange={(e) => set("queue", e.target.value)}
        >
          {queues.length === 0 && (
            <option value="" disabled>No queues available</option>
          )}
          {queues.map((q) => (
            <option key={q} value={q}>{q}</option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>Wall time</label>
        <div className="time-wrap">
          <input
            type="number"
            min={0}
            max={72}
            value={formData.wall_time_hours}
            onChange={(e) => set("wall_time_hours", +e.target.value)}
            placeholder="HH"
          />
          <span className="time-sep">h</span>
          <input
            type="number"
            min={0}
            max={59}
            value={formData.wall_time_minutes}
            onChange={(e) => set("wall_time_minutes", +e.target.value)}
            placeholder="MM"
          />
          <span className="time-sep">m</span>
        </div>
      </div>

      <div className="summary">
        <div className="sum-row"><span>Type</span><span className="badge badge-mpi"><i className="ti ti-topology-star-3" aria-hidden="true" />MPI</span></div>
        <div className="sum-row"><span>Name</span><span>{formData.name || "—"}</span></div>
        <div className="sum-row"><span>Cores</span><span>{formData.cores}</span></div>
        <div className="sum-row"><span>Memory</span><span>{memoryOptions.find(o => o.value === formData.memory)?.label || "—"}</span></div>
        <div className="sum-row"><span>Processes</span><span>{formData.mpi_processes}</span></div>
        <div className="sum-row"><span>Ptile</span><span>{formData.mpi_ptile}</span></div>
        <div className="sum-row"><span>Nodes needed</span><span>{nodesNeeded}</span></div>
        <div className="sum-row"><span>Queue</span><span>{formData.queue || "—"}</span></div>
        <div className="sum-row"><span>Wall time</span><span>{wallTime}</span></div>
        <div className="sum-row"><span>Script</span><span>{formData.file?.name || "no file selected"}</span></div>
      </div>

      <button type="submit" className="submit-btn" disabled={submitting}>
        <i className="ti ti-send" aria-hidden="true" />
        {submitting ? "Submitting…" : "Submit MPI job"}
      </button>
    </form>
  );
}
