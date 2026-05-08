--
-- PostgreSQL database dump
--

\restrict wjqXwpgWKv9wxcWiviiltfbHmtdevPTp78XhQ22QXbVdi8Z3FpTIEUc4ZBzXCoC

-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: audit_action; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.audit_action AS ENUM (
    'login',
    'login_failed',
    'logout',
    'job_submit',
    'job_cancel',
    'job_flagged',
    'view_output',
    'view_error',
    'role_change',
    'policy_change',
    'session_revoke',
    'register'
);


--
-- Name: job_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.job_status AS ENUM (
    'PEND',
    'RUN',
    'DONE',
    'EXIT'
);


--
-- Name: revoke_reason; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.revoke_reason AS ENUM (
    'logout',
    'admin_revoke',
    'suspicious_activity',
    'password_change'
);


--
-- Name: user_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_role AS ENUM (
    'student',
    'researcher',
    'admin'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    log_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    job_id text,
    action public.audit_action NOT NULL,
    ip_address text,
    detail jsonb,
    "timestamp" timestamp with time zone DEFAULT now(),
    result text,
    chain_hash text,
    prev_hash text
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    job_id text NOT NULL,
    unique_id uuid NOT NULL,
    user_id uuid,
    status public.job_status DEFAULT 'PEND'::public.job_status,
    queue text NOT NULL,
    cores integer NOT NULL,
    memory integer NOT NULL,
    wall_time text NOT NULL,
    script_filename text,
    output_file text,
    error_file text,
    node_used text,
    exit_code integer,
    error_message text,
    cancelled_by uuid,
    policy_id_at_submission uuid,
    policy_role_at_submission text,
    cores_limit_at_submission integer,
    memory_limit_at_submission integer,
    is_flagged boolean DEFAULT false,
    flag_reason text,
    flagged_at timestamp with time zone,
    submitted_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    finished_at timestamp with time zone
);


--
-- Name: policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policies (
    policy_id uuid DEFAULT gen_random_uuid() NOT NULL,
    role public.user_role NOT NULL,
    max_cores_per_job integer NOT NULL,
    max_memory_mb integer NOT NULL,
    max_wall_time_hours integer NOT NULL,
    max_concurrent_jobs integer NOT NULL,
    max_file_size_mb integer NOT NULL,
    max_jobs_per_day integer,
    max_jobs_total integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);


--
-- Name: policy_queues; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policy_queues (
    policy_id uuid NOT NULL,
    queue_name text NOT NULL
);


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    session_id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    token_hash text NOT NULL,
    device_id text,
    device_info jsonb,
    ip_address text,
    created_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    revoke_reason public.revoke_reason,
    risk_score integer DEFAULT 0,
    peak_risk integer DEFAULT 0
);


--
-- Name: user_known_ips; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_known_ips (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    ip_address character varying(45) NOT NULL,
    first_seen timestamp with time zone DEFAULT now(),
    last_seen timestamp with time zone DEFAULT now(),
    verified boolean DEFAULT false
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    user_id uuid DEFAULT gen_random_uuid() NOT NULL,
    keycloak_id text NOT NULL,
    username text NOT NULL,
    email text NOT NULL,
    role public.user_role DEFAULT 'student'::public.user_role NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    failed_attempts integer DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    last_login timestamp with time zone,
    is_approved boolean DEFAULT false,
    requested_role text DEFAULT 'student'::text
);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (log_id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (job_id);


--
-- Name: jobs jobs_unique_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_unique_id_key UNIQUE (unique_id);


--
-- Name: policies policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_pkey PRIMARY KEY (policy_id);


--
-- Name: policies policies_role_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_role_key UNIQUE (role);


--
-- Name: policy_queues policy_queues_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_queues
    ADD CONSTRAINT policy_queues_pkey PRIMARY KEY (policy_id, queue_name);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (session_id);


--
-- Name: sessions sessions_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_token_hash_key UNIQUE (token_hash);


--
-- Name: user_known_ips user_known_ips_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_known_ips
    ADD CONSTRAINT user_known_ips_pkey PRIMARY KEY (id);


--
-- Name: user_known_ips user_known_ips_user_id_ip_address_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_known_ips
    ADD CONSTRAINT user_known_ips_user_id_ip_address_key UNIQUE (user_id, ip_address);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_keycloak_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_keycloak_id_key UNIQUE (keycloak_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: audit_log audit_log_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(job_id) ON DELETE SET NULL;


--
-- Name: audit_log audit_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- Name: jobs jobs_cancelled_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_cancelled_by_fkey FOREIGN KEY (cancelled_by) REFERENCES public.users(user_id);


--
-- Name: jobs jobs_policy_id_at_submission_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_policy_id_at_submission_fkey FOREIGN KEY (policy_id_at_submission) REFERENCES public.policies(policy_id);


--
-- Name: jobs jobs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- Name: policy_queues policy_queues_policy_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policy_queues
    ADD CONSTRAINT policy_queues_policy_id_fkey FOREIGN KEY (policy_id) REFERENCES public.policies(policy_id) ON DELETE CASCADE;


--
-- Name: sessions sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: user_known_ips user_known_ips_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_known_ips
    ADD CONSTRAINT user_known_ips_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict wjqXwpgWKv9wxcWiviiltfbHmtdevPTp78XhQ22QXbVdi8Z3FpTIEUc4ZBzXCoC

