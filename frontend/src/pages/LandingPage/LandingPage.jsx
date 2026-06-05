import React, { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import "./LandingPage.css";
import { getToken } from '../../store/auth';
const BASE_URL = import.meta.env.VITE_API_URL || "https://localhost/api/v1";


const jobTypes = [
  {
    icon: "ti-file-code",
    type: "serial",
    title: "Serial job",
    desc: "Single-process execution on one core. Ideal for sequential scripts, data preprocessing, and lightweight ML training that does not require parallelism.",
    tags: ["1–16 cores", "Python / bash", "All roles"],
    tagClass: "tag-blue",
  },
  {
    icon: "ti-topology-star-3",
    type: "mpi",
    title: "MPI job",
    desc: "Distributed multi-process execution across all 22 nodes using MPI4Py. Designed for large-scale parallel workloads — up to 352 cores simultaneously.",
    tags: ["Up to 352 cores", "MPI4Py 3.0.3", "Researcher / admin"],
    tagClass: "tag-amber",
  },
];

const features = [
  {
    icon: "ti-shield-lock",
    title: "Zero-Trust security",
    desc: "Every job submission passes through CARTA risk evaluation. High-risk sessions trigger MFA step-up authentication. All actions are audit-logged with cryptographic chaining.",
  },
  {
    icon: "ti-chart-bar",
    title: "IBM LSF 9.1 scheduling",
    desc: "Jobs are queued and dispatched via IBM Load Sharing Facility. Supports serial and MPI workloads with role-based quotas and live output streaming via bsub / bjobs / bkill.",
  },
  {
    icon: "ti-users",
    title: "Role-based access",
    desc: "Three access tiers — student, researcher, admin — each with defined core, memory, and queue limits enforced at submission time via policy rules.",
  },
  {
    icon: "ti-alert-triangle",
    title: "scikit-learn & NumPy only",
    desc: "PyTorch and TensorFlow cannot run on this cluster (requires glibc 2.14+, system has glibc 2.12). We use scikit-learn 0.23.2 and NumPy 1.19.2 with OpenBLAS instead.",
  },
];

const sysInfo = [
  { icon: "ti-terminal",    label: "Scheduler",  value: "IBM LSF 9.1" },
  { icon: "ti-brand-linux", label: "OS",         value: "RHEL 6.4 (glibc 2.12)" },
  { icon: "ti-shield",      label: "Security",   value: "Zero-Trust MFA" },
  { icon: "ti-key",         label: "Auth",       value: "Keycloak + OIDC" },
  { icon: "ti-lock",        label: "Transport",  value: "mTLS (nginx)" },
  { icon: "ti-network",     label: "Network",    value: "Gigabit Ethernet" },
  { icon: "ti-server",      label: "MPI",        value: "IBM Platform MPI 9.1" },
];

const software = [
  { label: "Python 3.8.5",        cls: "tag-blue" },
  { label: "Anaconda",            cls: "tag-blue" },
  { label: "NumPy 1.19.2",        cls: "tag-teal" },
  { label: "scikit-learn 0.23.2", cls: "tag-teal" },
  { label: "MPI4Py 3.0.3",        cls: "tag-amber" },
  { label: "OpenBLAS",            cls: "tag-teal" },
  { label: "FastAPI",             cls: "tag-blue" },
  { label: "PostgreSQL",          cls: "tag-blue" },
];

const nodes = [
  { icon: "ti-server-2",    cls: "av-blue",  title: "hpcadmin1",       role: "Management node",    specs: "Login, job submission, admin — 16 cores, 452 GB disk" },
  { icon: "ti-server-2",    cls: "av-amber", title: "hpcadmin2",       role: "Backup management",  specs: "Backup management — 16 cores, 29 GB RAM" },
  { icon: "ti-cpu",         cls: "av-teal",  title: "compute001–030",  role: "Compute nodes",      specs: "22 online / 30 total — 16 cores, 18 GB RAM each" },
  { icon: "ti-database",    cls: "av-blue",  title: "NFS /home",       role: "Shared storage",     specs: "2 TB total — shared across all nodes" },
];

const roles = [
  { icon: "ti-school",       cls: "av-blue",  title: "Students",    desc: "Submit serial jobs, access standard queues, run Python scripts. Limited to 4 cores and 4 GB RAM per job." },
  { icon: "ti-microscope",   cls: "av-teal",  title: "Researchers", desc: "Full serial and MPI access across 22 nodes, priority queues, up to 352 cores. Requires admin approval." },
  { icon: "ti-shield-check", cls: "av-amber", title: "Admins",      desc: "Unlimited access, policy management, audit log review, node monitoring, and user approval." },
];

const team = [
  { initials: "GY",  name: "Grele Yasmine",      cls: "av-blue" },
  { initials: "GA",  name: "Guemir Aicha",       cls: "av-teal" },
  { initials: "ZFZ", name: "Zinai Fatima Zahra", cls: "av-amber" },
];

// ── Floating Chat Widget ──────────────────────────────────────────────────────
function ChatWidget() {
  const [open, setOpen]       = useState(false);
  const [step, setStep]       = useState("form"); // "form" | "sent"
  const [name, setName]       = useState("");
  const [email, setEmail]     = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError]     = useState("");
  const bottomRef             = useRef(null);

  useEffect(() => {
    if (open && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [open]);

  const handleSend = async () => {
    if (!name.trim() || !email.trim() || !message.trim()) {
      setError("Please fill in all fields.");
      return;
    }
    setSending(true);
    setError("");
    try {
      const res = await fetch(`${BASE_URL}/messages/contact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, message }),
      });
      if (!res.ok) throw new Error("Server error");
      setStep("sent");
    } catch {
      setError("Failed to send message. Please try again.");
    } finally {
      setSending(false);
    }
  };

  const handleReset = () => {
    setStep("form");
    setName("");
    setEmail("");
    setMessage("");
    setError("");
  };

  return (
    <>
      {/* ── Chat bubble button ── */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          position: "fixed",
          bottom: 28,
          right: 28,
          width: 54,
          height: 54,
          borderRadius: "50%",
          background: "#2563eb",
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 4px 16px rgba(37,99,235,0.35)",
          zIndex: 9999,
          transition: "background 0.15s",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "#1d4ed8")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "#2563eb")}
        aria-label="Contact admin"
      >
        <i
          className={`ti ${open ? "ti-x" : "ti-message-circle"}`}
          style={{ fontSize: 24, color: "white" }}
          aria-hidden="true"
        />
      </button>

      {/* ── Chat panel ── */}
      {open && (
        <div
          style={{
            position: "fixed",
            bottom: 92,
            right: 28,
            width: 320,
            background: "#fff",
            borderRadius: 14,
            boxShadow: "0 8px 32px rgba(0,0,0,0.15)",
            zIndex: 9998,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            border: "1px solid #e2e8f0",
          }}
        >
          {/* Header */}
          <div style={{
            background: "#2563eb",
            padding: "14px 18px",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}>
            <div style={{
              width: 36,
              height: 36,
              borderRadius: "50%",
              background: "rgba(255,255,255,0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}>
              <i className="ti ti-shield-check" style={{ fontSize: 18, color: "white" }} aria-hidden="true" />
            </div>
            <div>
              <div style={{ color: "white", fontWeight: 700, fontSize: 14 }}>HPC</div>
              <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 11 }}>Contact Admin</div>
            </div>
          </div>

          {/* Body */}
          <div style={{ padding: "16px 18px 18px", flex: 1 }}>
            {step === "form" ? (
              <>
                <p style={{ fontSize: 13, color: "#475569", marginBottom: 14, lineHeight: 1.5 }}>
                  Have a question or need access? Send a message to the admin team.
                </p>

                <div style={{ marginBottom: 10 }}>
                  <label style={{ fontSize: 12, color: "#64748b", display: "block", marginBottom: 4 }}>Name</label>
                  <input
                    type="text"
                    placeholder="Your name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid #e2e8f0",
                      fontSize: 13,
                      outline: "none",
                      boxSizing: "border-box",
                      color: "#0f172a",
                    }}
                  />
                </div>

                <div style={{ marginBottom: 10 }}>
                  <label style={{ fontSize: 12, color: "#64748b", display: "block", marginBottom: 4 }}>Email</label>
                  <input
                    type="email"
                    placeholder="your@email.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid #e2e8f0",
                      fontSize: 13,
                      outline: "none",
                      boxSizing: "border-box",
                      color: "#0f172a",
                    }}
                  />
                </div>

                <div style={{ marginBottom: 12 }}>
                  <label style={{ fontSize: 12, color: "#64748b", display: "block", marginBottom: 4 }}>Message</label>
                  <textarea
                    placeholder="Describe your request or issue..."
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={4}
                    style={{
                      width: "100%",
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid #e2e8f0",
                      fontSize: 13,
                      outline: "none",
                      resize: "none",
                      boxSizing: "border-box",
                      color: "#0f172a",
                      fontFamily: "inherit",
                    }}
                  />
                </div>

                {error && (
                  <p style={{ fontSize: 12, color: "#dc2626", marginBottom: 10 }}>{error}</p>
                )}

                <button
                  onClick={handleSend}
                  disabled={sending}
                  style={{
                    width: "100%",
                    padding: "9px",
                    borderRadius: 8,
                    border: "none",
                    background: sending ? "#93c5fd" : "#2563eb",
                    color: "white",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: sending ? "not-allowed" : "pointer",
                    transition: "background 0.15s",
                  }}
                >
                  {sending ? "Sending..." : "Send Message"}
                </button>
              </>
            ) : (
              <div style={{ textAlign: "center", padding: "16px 0" }}>
                <div style={{
                  width: 52,
                  height: 52,
                  borderRadius: "50%",
                  background: "#f0fdf4",
                  border: "1px solid #bbf7d0",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  margin: "0 auto 14px",
                }}>
                  <i className="ti ti-check" style={{ fontSize: 26, color: "#16a34a" }} aria-hidden="true" />
                </div>
                <p style={{ fontWeight: 700, fontSize: 14, color: "#0f172a", marginBottom: 6 }}>
                  Message sent!
                </p>
                <p style={{ fontSize: 13, color: "#64748b", lineHeight: 1.5, marginBottom: 16 }}>
                  The admin team will review your message and get back to you shortly.
                </p>
                <button
                  onClick={handleReset}
                  style={{
                    padding: "7px 20px",
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                    background: "#f8fafc",
                    color: "#2563eb",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Send another
                </button>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
      )}
    </>
  );
}
// ─────────────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  const [clusterStats, setClusterStats] = useState(null);

  useEffect(() => {
  const token = getToken();  
  
  fetch(`/api/v1/jobs/cluster/public-state`)
    .then((res) => {
      if (!res.ok) throw new Error("Failed");
      return res.json();
    })
    .then((data) => setClusterStats(data))
    .catch(() => setClusterStats(null));
}, []);

  const activeNodes = clusterStats?.active_nodes  ?? "22";
  const totalNodes  = clusterStats?.total_nodes   ?? "30";
  const totalCores  = clusterStats?.total_cores   ?? "352";
  const freeCores   = clusterStats?.free_cores    ?? "—";
  const utilization = clusterStats?.utilization   ?? "—";

  return (
    <div className="lp-root">

      {/* ── Navbar ── */}
      <nav className="lp-nav">
        <div className="lp-logo">
          <i className="ti ti-shield-lock" aria-hidden="true" />
          HPC Portal
        </div>
        <div className="lp-nav-btns">
          <Link to="/login"    className="btn-ghost">Login</Link>
          <Link to="/register" className="btn-solid">Register</Link>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="lp-hero">
        <div className="lp-badge">
          <i className="ti ti-lock" aria-hidden="true" />
          Zero-Trust · IBM LSF 9.1 · RHEL 6.4
        </div>
        <h1>Welcome to <span className="lp-accent">HPC</span></h1>
        <p>
          A secure high-performance computing platform interconnected via Gigabit Ethernet. Train ML models, run distributed MPI jobs,
          and monitor your cluster in real time — with MFA-enforced Zero-Trust access control.
        </p>
        <div className="lp-hero-btns">
          <Link to="/register" className="btn-primary">
            <i className="ti ti-user-plus" aria-hidden="true" />
            Create account
          </Link>
          <Link to="/login" className="btn-secondary">
            <i className="ti ti-login" aria-hidden="true" />
            Sign in
          </Link>
        </div>
      </section>

      {/* ── Stats (live) ── */}
      <div className="lp-stats">
        <div className="lp-stat">
          <i className="ti ti-server lp-stat-icon" aria-hidden="true" />
          <div className="lp-stat-num lp-stat-accent">
            {activeNodes} <span style={{ fontSize: 16, fontWeight: 500, color: "#64748b" }}>/ {totalNodes}</span>
          </div>
          <div className="lp-stat-lbl">Active nodes</div>
        </div>
        <div className="lp-stat">
          <i className="ti ti-cpu lp-stat-icon" aria-hidden="true" />
          <div className="lp-stat-num">{totalCores}</div>
          <div className="lp-stat-lbl">Total cores</div>
        </div>
        <div className="lp-stat">
          <i className="ti ti-database lp-stat-icon" aria-hidden="true" />
          <div className="lp-stat-num">18 GB</div>
          <div className="lp-stat-lbl">RAM per node</div>
        </div>
        <div className="lp-stat">
          <i className="ti ti-device-floppy lp-stat-icon" aria-hidden="true" />
          <div className="lp-stat-num">2 TB</div>
          <div className="lp-stat-lbl">NFS storage</div>
        </div>
        <div className="lp-stat">
          <i className="ti ti-activity lp-stat-icon" aria-hidden="true" />
          <div className="lp-stat-num lp-stat-accent">{utilization}</div>
          <div className="lp-stat-lbl">Cluster utilization</div>
        </div>
        <div className="lp-stat">
          <i className="ti ti-plug lp-stat-icon" aria-hidden="true" />
          <div className="lp-stat-num">{freeCores}</div>
          <div className="lp-stat-lbl">Free cores</div>
        </div>
      </div>

      <hr className="lp-divider" />

      {/* ── About / Intro ── */}
      <section className="lp-section">
        <div className="lp-section-hdr">
          <i className="ti ti-info-circle" aria-hidden="true" />
          <h2>Introduction to the HPC Cluster</h2>
        </div>
        <div className="lp-intro-card">
          <p>
            This platform gives access to our High-Performance Computing cluster designed for
            machine learning benchmarking and distributed scientific computing. The cluster is managed by{" "}
            <strong>IBM Platform HPC 4.1.1.1</strong> with the{" "}
            <strong>LSF (Load Sharing Facility)</strong> job scheduler, and nodes are interconnected via{" "}
            <strong>Gigabit Ethernet</strong>.
          </p>
          <p style={{ marginTop: 12 }}>
            Currently <strong style={{ color: "#2563eb" }}>{activeNodes} compute nodes</strong> are online
            out of {totalNodes} total, providing{" "}
            <strong style={{ color: "#2563eb" }}>{totalCores} CPU cores</strong> of available capacity.
            Node availability may vary depending on maintenance and cluster load.
          </p>
          <p style={{ marginTop: 12 }}>
            The cluster supports training of neural networks on datasets like CIFAR-10 and comparing
            performance across configurations: single-node CPU (8 and 16 cores) and distributed CPU
            across multiple nodes. Note: PyTorch and TensorFlow are <strong>not supported</strong> —
            the system runs <strong>glibc 2.12</strong> while these frameworks require glibc 2.14+.
            Use scikit-learn and NumPy+mpi4py instead.
          </p>
        </div>
      </section>

      <hr className="lp-divider" />

      {/* ── Architecture ── */}
      <section className="lp-section">
        <div className="lp-section-hdr">
          <i className="ti ti-layout-grid" aria-hidden="true" />
          <h2>Architecture overview</h2>
        </div>
        <div className="lp-arch-grid">
          {nodes.map((n) => (
            <div className="lp-arch-card" key={n.title}>
              <div className={`lp-who-icon ${n.cls}`} style={{ marginBottom: 12 }}>
                <i className={`ti ${n.icon}`} aria-hidden="true" />
              </div>
              <h3>{n.title}</h3>
              <span className="lp-arch-role">{n.role}</span>
              <p>{n.specs}</p>
            </div>
          ))}
        </div>
      </section>

      <hr className="lp-divider" />

      {/* ── Job types ── */}
      <section className="lp-section">
        <div className="lp-section-hdr">
          <i className="ti ti-list" aria-hidden="true" />
          <h2>Job types</h2>
        </div>
        <div className="lp-job-grid">
          {jobTypes.map((j) => (
            <div className="lp-job-card" key={j.type}>
              <div className="lp-job-hdr">
                <div className={`lp-job-icon lp-job-icon--${j.type}`}>
                  <i className={`ti ${j.icon}`} aria-hidden="true" />
                </div>
                <h3>{j.title}</h3>
              </div>
              <p>{j.desc}</p>
              <div className="lp-tags">
                {j.tags.map((t) => (
                  <span className={`lp-tag ${j.tagClass}`} key={t}>{t}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <hr className="lp-divider" />

      {/* ── Platform features ── */}
      <section className="lp-section">
        <div className="lp-section-hdr">
          <i className="ti ti-sparkles" aria-hidden="true" />
          <h2>Platform features</h2>
        </div>
        <div className="lp-feat-grid">
          {features.map((f) => (
            <div className="lp-feat-card" key={f.title}>
              <i className={`ti ${f.icon} lp-feat-icon`} aria-hidden="true" />
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <hr className="lp-divider" />

      {/* ── System architecture ── */}
      <section className="lp-section">
        <div className="lp-section-hdr">
          <i className="ti ti-settings" aria-hidden="true" />
          <h2>System architecture</h2>
        </div>
        <div className="lp-sys-grid">
          <div className="lp-feat-card">
            <div className="lp-sys-list">
              {sysInfo.map((s) => (
                <div className="lp-sys-row" key={s.label}>
                  <i className={`ti ${s.icon}`} aria-hidden="true" />
                  <span className="lp-sys-lbl">{s.label}</span>
                  <span className="lp-sys-val">{s.value}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="lp-feat-card">
            <p className="lp-soft-title">Available software</p>
            <div className="lp-tags" style={{ marginTop: 10, gap: 8 }}>
              {software.map((s) => (
                <span className={`lp-tag ${s.cls}`} key={s.label}>{s.label}</span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <hr className="lp-divider" />

      {/* ── Who can use it ── */}
      <section className="lp-section">
        <div className="lp-section-hdr">
          <i className="ti ti-user-check" aria-hidden="true" />
          <h2>Who can use this platform?</h2>
        </div>
        <div className="lp-who-grid">
          {roles.map((r) => (
            <div className="lp-who-card" key={r.title}>
              <div className={`lp-who-icon ${r.cls}`}>
                <i className={`ti ${r.icon}`} aria-hidden="true" />
              </div>
              <div>
                <h3>{r.title}</h3>
                <p>{r.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <hr className="lp-divider" />

      {/* ── Team ── */}
      <section className="lp-section">
        <div className="lp-section-hdr">
          <i className="ti ti-code" aria-hidden="true" />
          <h2>Development team</h2>
        </div>
        <div className="lp-team">
          {team.map((m) => (
            <div className="lp-team-card" key={m.name}>
              <div className={`lp-avatar ${m.cls}`}>{m.initials}</div>
              <h3>{m.name}</h3>
              <p>Developer</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="lp-footer">
        Zero-Trust HPC Portal — Grele Yasmine · Guemir Aicha · Zinai Fatima Zahra
      </footer>

      {/* ── Floating Chat Widget ── */}
      <ChatWidget />

    </div>
  );
}
