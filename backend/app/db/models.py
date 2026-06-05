from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, text, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from datetime import datetime,timezone

import enum


# ── Python Enums ───────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    student    = "student"
    researcher = "researcher"
    admin      = "admin"

class JobStatus(str, enum.Enum):
    PEND = "PEND"
    RUN  = "RUN"
    DONE = "DONE"
    EXIT = "EXIT"

class AuditAction(str, enum.Enum):
    login          = "login"
    login_failed   = "login_failed"
    logout         = "logout"
    job_submit     = "job_submit"
    job_cancel     = "job_cancel"
    job_flagged    = "job_flagged"
    view_output    = "view_output"
    view_error     = "view_error"
    role_change    = "role_change"
    policy_change  = "policy_change"
    session_revoke = "session_revoke"
    register       = "register"


# ── PostgreSQL Enum types (must match schema.sql exactly) ──────────────────

USER_ROLE_TYPE = PG_ENUM(
    'student', 'researcher', 'admin',
    name='user_role', create_type=True
)

JOB_STATUS_TYPE = PG_ENUM(
    'PEND', 'RUN', 'DONE', 'EXIT',
    name='job_status', create_type=True
)

AUDIT_ACTION_TYPE = PG_ENUM(
    'login', 'login_failed', 'logout',
    'job_submit', 'job_cancel', 'job_flagged',
    'view_output', 'view_error', 'role_change',
    'policy_change', 'session_revoke', 'register',
    name='audit_action', create_type=True
)

REVOKE_REASON_TYPE = PG_ENUM(
    'logout', 'admin_revoke', 'suspicious_activity', 'password_change',
    name='revoke_reason', create_type=True
)


# ── Base ───────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── User ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    user_id         : Mapped[str]      = mapped_column(
                          UUID(as_uuid=False), primary_key=True,
                          server_default=text("gen_random_uuid()"))
    keycloak_id     : Mapped[str]      = mapped_column(String, unique=True, nullable=False)
    username        : Mapped[str]      = mapped_column(String, unique=True, nullable=False)
    email           : Mapped[str]      = mapped_column(String, unique=True, nullable=False)
    role            : Mapped[str]      = mapped_column(
                          USER_ROLE_TYPE, default='student', nullable=False)
    is_active       : Mapped[bool]     = mapped_column(Boolean, default=True, nullable=False)
    is_approved    : Mapped[bool]      = mapped_column(Boolean, default=False, nullable=False)
    requested_role : Mapped[str]       = mapped_column(String, nullable=True)
    email_otp_code      : Mapped[str]      = mapped_column(String, nullable=True)
    email_otp_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    email_otp_verified  : Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)

    failed_attempts : Mapped[int]      = mapped_column(Integer, default=0, nullable=False)
    locked_until    : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at      : Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                             default=datetime.utcnow)
    last_login      : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    jobs     = relationship("Job",      back_populates="user",
                            foreign_keys="Job.user_id")
    sessions = relationship("Session",  back_populates="user",
                            cascade="all, delete-orphan")
    logs     = relationship("AuditLog", back_populates="user")
    document_path: Mapped[str] = mapped_column(String, nullable=True)

# ── Policy ─────────────────────────────────────────────────────────────────

class Policy(Base):
    __tablename__ = "policies"

    policy_id           : Mapped[str]      = mapped_column(
                              UUID(as_uuid=False), primary_key=True,
                              server_default=text("gen_random_uuid()"))
    role                : Mapped[str]      = mapped_column(
                              USER_ROLE_TYPE, unique=True, nullable=False)
    max_cores_per_job   : Mapped[int]      = mapped_column(Integer, nullable=False)
    max_memory_mb       : Mapped[int]      = mapped_column(Integer, nullable=False)
    max_wall_time_hours : Mapped[int]      = mapped_column(Integer, nullable=False)
    max_concurrent_jobs : Mapped[int]      = mapped_column(Integer, nullable=False)
    max_file_size_mb    : Mapped[int]      = mapped_column(Integer, nullable=False)
    max_jobs_per_day    : Mapped[int]      = mapped_column(Integer, nullable=True)
    max_jobs_total      : Mapped[int]      = mapped_column(Integer, nullable=True)
    created_at          : Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=datetime.utcnow)
    updated_at          : Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 nullable=True, onupdate=datetime.utcnow)

    allowed_queues = relationship("PolicyQueue", cascade="all, delete-orphan",
                                  lazy="selectin")


# ── PolicyQueue ────────────────────────────────────────────────────────────

class PolicyQueue(Base):
    __tablename__ = "policy_queues"

    policy_id  : Mapped[str] = mapped_column(
                     UUID(as_uuid=False),
                     ForeignKey("policies.policy_id", ondelete="CASCADE"),
                     primary_key=True)
    queue_name : Mapped[str] = mapped_column(String, primary_key=True, nullable=False)


# ── Job ────────────────────────────────────────────────────────────────────

class Job(Base):
    __tablename__ = "jobs"

    job_id          : Mapped[str]      = mapped_column(String, primary_key=True)
    unique_id       : Mapped[str]      = mapped_column(
                          UUID(as_uuid=False), unique=True, nullable=False)
    user_id         : Mapped[str]      = mapped_column(
                          UUID(as_uuid=False),
                          ForeignKey("users.user_id"), nullable=False)
    status          : Mapped[str]      = mapped_column(
                          JOB_STATUS_TYPE, default='PEND', nullable=False)
    queue           : Mapped[str]      = mapped_column(String, nullable=False)
    cores           : Mapped[int]      = mapped_column(Integer, nullable=False)
    memory          : Mapped[int]      = mapped_column(Integer, nullable=False)
    wall_time       : Mapped[str]      = mapped_column(String, nullable=False)
    script_filename : Mapped[str]      = mapped_column(String, nullable=True)
    output_file     : Mapped[str]      = mapped_column(String, nullable=True)
    error_file      : Mapped[str]      = mapped_column(String, nullable=True)
    node_used       : Mapped[str]      = mapped_column(String, nullable=True)
    exit_code       : Mapped[int]      = mapped_column(Integer, nullable=True)
    error_message   : Mapped[str]      = mapped_column(String, nullable=True)
    cancelled_by    : Mapped[str]      = mapped_column(
                          UUID(as_uuid=False),
                          ForeignKey("users.user_id"), nullable=True)

    policy_id_at_submission    : Mapped[str] = mapped_column(
                                     UUID(as_uuid=False),
                                     ForeignKey("policies.policy_id"),
                                     nullable=False)
    policy_role_at_submission  : Mapped[str] = mapped_column(String, nullable=False)
    cores_limit_at_submission  : Mapped[int] = mapped_column(Integer, nullable=False)
    memory_limit_at_submission : Mapped[int] = mapped_column(Integer, nullable=False)

    is_flagged  : Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)
    flag_reason : Mapped[str]      = mapped_column(String, nullable=True)
    flagged_at  : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    submitted_at : Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                          default=datetime.utcnow)
    updated_at   : Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                          nullable=True, onupdate=datetime.utcnow)
    finished_at  : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    user      = relationship("User",   back_populates="jobs",
                             foreign_keys=[user_id])
    cancelled = relationship("User",   foreign_keys=[cancelled_by])
    policy    = relationship("Policy", foreign_keys=[policy_id_at_submission])
    logs      = relationship("AuditLog", back_populates="job")


# ── Session ────────────────────────────────────────────────────────────────

class Session(Base):
    __tablename__ = "sessions"

    session_id    : Mapped[str]      = mapped_column(
                        UUID(as_uuid=False), primary_key=True,
                        server_default=text("gen_random_uuid()"))
    user_id       : Mapped[str]      = mapped_column(
                        UUID(as_uuid=False),
                        ForeignKey("users.user_id", ondelete="CASCADE"),
                        nullable=False)
    token_hash    : Mapped[str]      = mapped_column(String, unique=True, nullable=False)
    device_id     : Mapped[str]      = mapped_column(String, nullable=True)
    device_info   : Mapped[dict]     = mapped_column(JSONB, nullable=True)
    ip_address    : Mapped[str]      = mapped_column(String, nullable=True)
    created_at    : Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                           default=datetime.utcnow)
    expires_at    : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at    : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason : Mapped[str]      = mapped_column(REVOKE_REASON_TYPE, nullable=True)
    risk_score:     Mapped[float]    = mapped_column(Float, default=0.0)
    peak_risk:      Mapped[float]    = mapped_column(Float, default=0.0)
    totp_verified_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="sessions")


# ── AuditLog ───────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id     : Mapped[str]      = mapped_column(
                     UUID(as_uuid=False), primary_key=True,
                     server_default=text("gen_random_uuid()"))
    user_id    : Mapped[str]      = mapped_column(
                     UUID(as_uuid=False),
                     ForeignKey("users.user_id", ondelete="SET NULL"),
                     nullable=True)
    job_id     : Mapped[str]      = mapped_column(
                     String,
                     ForeignKey("jobs.job_id", ondelete="SET NULL"),
                     nullable=True)
    action     : Mapped[str]      = mapped_column(AUDIT_ACTION_TYPE, nullable=False)
    ip_address : Mapped[str]      = mapped_column(String, nullable=True)
    detail     : Mapped[dict]     = mapped_column(JSONB, nullable=True) 
    result     : Mapped[str]      = mapped_column(String, nullable=True)
    chain_hash : Mapped[str]      = mapped_column(String, nullable=True)
    prev_hash  : Mapped[str]      = mapped_column(String, nullable=True)
    timestamp  : Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                        default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="logs")
    job  = relationship("Job",  back_populates="logs")
    
class UserKnownIP(Base):
    __tablename__ = "user_known_ips"

    id         : Mapped[str]      = mapped_column(
                     UUID(as_uuid=False), primary_key=True,
                     server_default=text("gen_random_uuid()"))
    user_id    : Mapped[str]      = mapped_column(
                     UUID(as_uuid=False),
                     ForeignKey("users.user_id", ondelete="CASCADE"),
                     nullable=False)
    ip_address : Mapped[str]      = mapped_column(String(45), nullable=False)
    first_seen : Mapped[datetime] = mapped_column(
                     DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen  : Mapped[datetime] = mapped_column(
                     DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    verified   : Mapped[bool]     = mapped_column(Boolean, default=False)    
    
    
    
    


class UserKnownDevice(Base):
    __tablename__ = "user_known_devices"

    id          : Mapped[str]      = mapped_column(
                      UUID(as_uuid=False), primary_key=True,
                      server_default=text("gen_random_uuid()"))
    user_id     : Mapped[str]      = mapped_column(
                      UUID(as_uuid=False),
                      ForeignKey("users.user_id", ondelete="CASCADE"),
                      nullable=False)
    fingerprint : Mapped[str]      = mapped_column(String(64), nullable=False)
    device_type : Mapped[str]      = mapped_column(String(20), nullable=True)
    platform    : Mapped[str]      = mapped_column(String(50), nullable=True)
    timezone    : Mapped[str]      = mapped_column(String(50), nullable=True)
    verified    : Mapped[bool]     = mapped_column(Boolean, default=False)
    first_seen  : Mapped[datetime] = mapped_column(
                      DateTime(timezone=True),
                      default=lambda: datetime.now(timezone.utc))
    last_seen   : Mapped[datetime] = mapped_column(
                      DateTime(timezone=True),
                      default=lambda: datetime.now(timezone.utc),
                      onupdate=lambda: datetime.now(timezone.utc))
    
    
 # ── Message ────────────────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    message_id  : Mapped[str]      = mapped_column(
                      UUID(as_uuid=False), primary_key=True,
                      server_default=text("gen_random_uuid()"))
    sender_id   : Mapped[str]      = mapped_column(
                      UUID(as_uuid=False),
                      ForeignKey("users.user_id", ondelete="CASCADE"),
                      nullable=False)
    receiver_id : Mapped[str]      = mapped_column(
                      UUID(as_uuid=False),
                      ForeignKey("users.user_id", ondelete="CASCADE"),
                      nullable=False)
    content     : Mapped[str]      = mapped_column(String, nullable=False)
    is_read     : Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)
    created_at  : Mapped[datetime] = mapped_column(
                      DateTime(timezone=True),
                      default=lambda: datetime.now(timezone.utc))

    sender   = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
