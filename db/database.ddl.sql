-- Job Scheduling Service Database Schema

-- Organizations table for multi-tenancy
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    domain VARCHAR(100) NOT NULL,
    identifier VARCHAR(100) NOT NULL,
    configuration JSONB DEFAULT '{}',
    username VARCHAR(100) NOT NULL,
    password VARCHAR(100) NOT NULL,
    environment VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Users table for authentication and ownership
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Job templates/definitions
CREATE TABLE job_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(100) NOT NULL,
    description TEXT,
    script_type VARCHAR(20) DEFAULT 'predefined', -- 'predefined', 'python', 'bash', 'javascript'
    script_content TEXT, -- For future user-provided scripts
    script_path VARCHAR(255), -- Path to predefined script file
    parameters_schema JSONB, -- JSON schema for job parameters validation
    is_active BOOLEAN DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Job instances - each scheduled job
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(100) NOT NULL,
    template_id UUID REFERENCES job_templates(id),
    created_by UUID REFERENCES users(id),
    organization_id UUID REFERENCES organizations(id),
    
    -- Job parameters
    parameters JSONB DEFAULT '{}',
    
    -- Status tracking
    status VARCHAR(20) DEFAULT 'running', -- 'pending', 'running', 'completed', 'failed', 'cancelled', 'paused'
    
    -- Scheduling information
    trigger_type VARCHAR(20) NOT NULL, -- 'manual', 'frequency', 'cron'
    
    -- For frequency-based triggers
    frequency_interval INTEGER, -- in seconds, minutes, hours, days
    frequency_unit VARCHAR(10), -- 'seconds', 'minutes', 'hours', 'days'
    frequency_count INTEGER, -- number of times to run (NULL for unlimited)
    frequency_end_time TIMESTAMP, -- when to stop running
    
    -- For cron-based triggers (future enhancement)
    cron_expression VARCHAR(100),
    timeout_seconds INTEGER DEFAULT 300,
    max_retries INTEGER DEFAULT 3,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT valid_trigger_type CHECK (trigger_type IN ('manual', 'frequency', 'cron')),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled', 'paused')),
    CONSTRAINT valid_frequency_unit CHECK (frequency_unit IN ('seconds', 'minutes', 'hours', 'days') OR frequency_unit IS NULL)
);

-- Job execution history
CREATE TABLE job_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    
    -- Execution details
    status VARCHAR(20) NOT NULL, -- 'running', 'completed', 'failed', 'timeout', 'cancelled'
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    
    -- Results and logs
    result JSONB,
    error_message TEXT,
    
    -- Retry information
    retry_count INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_execution_status CHECK (status IN ('running', 'completed', 'failed', 'timeout', 'cancelled'))
);

-- Job notifications
CREATE TABLE job_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    notification_type VARCHAR(20) NOT NULL, -- 'email', 'webhook', 'slack', etc.
    trigger_on VARCHAR(20) NOT NULL, -- 'success', 'failure', 'both'
    configuration JSONB NOT NULL, -- Configuration for the notification type
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_notification_type CHECK (notification_type IN ('email', 'webhook', 'slack')),
    CONSTRAINT valid_trigger_on CHECK (trigger_on IN ('success', 'failure', 'both'))
);

-- InformaticaJobRuns table
CREATE TABLE informatica_job_runs (
    id VARCHAR(100) PRIMARY KEY,
    organization_id VARCHAR(100) NOT NULL,
    status VARCHAR(100) NOT NULL,
    sync_perfomed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

-- InformaticaJobLogs table
CREATE TABLE informatica_jobs_logs (
    id VARCHAR(100) PRIMARY KEY,
    job_run_id VARCHAR(100) REFERENCES informatica_job_runs(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    
    -- Core activity log entry fields
    type VARCHAR(100),
    object_id VARCHAR(100),
    object_name VARCHAR(100),
    run_id INTEGER,
    
    -- Timestamps
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    start_time_utc TIMESTAMP,
    end_time_utc TIMESTAMP,
    
    -- State and status
    state INTEGER,
    ui_state INTEGER,
    
    -- Row processing statistics
    failed_source_rows INTEGER DEFAULT 0,
    success_source_rows INTEGER DEFAULT 0,
    failed_target_rows INTEGER DEFAULT 0,
    success_target_rows INTEGER DEFAULT 0,
    
    -- Execution context
    started_by VARCHAR(255),
    run_context_type VARCHAR(100),
    
    -- Agent and runtime information
    agent_id VARCHAR(100),
    runtime_environment_id VARCHAR(100),
    
    -- Error handling
    error_msg TEXT,
    stop_on_error BOOLEAN DEFAULT FALSE,
    has_stop_on_error_record BOOLEAN DEFAULT FALSE,
    is_stopped BOOLEAN DEFAULT FALSE,
    
    -- Context and external references
    context_external_id VARCHAR(100),
    
    -- Additional metadata
    total_success_rows INTEGER DEFAULT 0,
    total_failed_rows INTEGER DEFAULT 0,
    
    -- Nested data structures
    entries JSONB,
    sub_task_entries JSONB,
    transformation_entries JSONB,
    log_entry_item_attrs JSONB,
    session_variables JSONB,
    
    -- Unique constraint to prevent duplicate logs within same organization
    CONSTRAINT uq_informatica_jobs_logs_object_run_org UNIQUE (object_id, run_id, organization_id)
);

CREATE TABLE user_organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member', -- 'admin', 'member', 'viewer'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique user-organization combinations
    UNIQUE(user_id, organization_id),
    
    -- Constraints
    CONSTRAINT valid_role CHECK (role IN ('admin', 'member', 'viewer'))
);

CREATE INDEX idx_user_organizations_user_id ON user_organizations(user_id);
CREATE INDEX idx_user_organizations_organization_id ON user_organizations(organization_id);
CREATE INDEX idx_user_organizations_role ON user_organizations(role);
CREATE INDEX idx_user_organizations_active ON user_organizations(is_active);
CREATE INDEX idx_user_organizations_user_id_organization_id ON user_organizations(user_id, organization_id);


-- Indexes for performance

-- Indexes for informatica_job_runs
CREATE INDEX idx_informatica_job_runs_organization_id ON informatica_job_runs(organization_id);
CREATE INDEX idx_informatica_job_runs_status ON informatica_job_runs(status);
CREATE INDEX idx_informatica_job_runs_sync_performed_at ON informatica_job_runs(sync_perfomed_at);

-- Indexes for informatica_jobs_logs
CREATE INDEX idx_informatica_jobs_logs_job_run_id ON informatica_jobs_logs(job_run_id);
CREATE INDEX idx_informatica_jobs_logs_type ON informatica_jobs_logs(type);
CREATE INDEX idx_informatica_jobs_logs_object_id ON informatica_jobs_logs(object_id);
CREATE INDEX idx_informatica_jobs_logs_object_name ON informatica_jobs_logs(object_name);
CREATE INDEX idx_informatica_jobs_logs_run_id ON informatica_jobs_logs(run_id);
CREATE INDEX idx_informatica_jobs_logs_start_time ON informatica_jobs_logs(start_time);
CREATE INDEX idx_informatica_jobs_logs_end_time ON informatica_jobs_logs(end_time);
CREATE INDEX idx_informatica_jobs_logs_start_time_utc ON informatica_jobs_logs(start_time_utc);
CREATE INDEX idx_informatica_jobs_logs_end_time_utc ON informatica_jobs_logs(end_time_utc);
CREATE INDEX idx_informatica_jobs_logs_state ON informatica_jobs_logs(state);
CREATE INDEX idx_informatica_jobs_logs_ui_state ON informatica_jobs_logs(ui_state);
CREATE INDEX idx_informatica_jobs_logs_started_by ON informatica_jobs_logs(started_by);
CREATE INDEX idx_informatica_jobs_logs_run_context_type ON informatica_jobs_logs(run_context_type);
CREATE INDEX idx_informatica_jobs_logs_agent_id ON informatica_jobs_logs(agent_id);
CREATE INDEX idx_informatica_jobs_logs_runtime_environment_id ON informatica_jobs_logs(runtime_environment_id);
CREATE INDEX idx_informatica_jobs_logs_context_external_id ON informatica_jobs_logs(context_external_id);
CREATE INDEX idx_organizations_domain ON organizations(domain);
CREATE INDEX idx_organizations_name ON organizations(name);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);

CREATE INDEX idx_jobs_created_by ON jobs(created_by);
CREATE INDEX idx_jobs_organization_id ON jobs(organization_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_trigger_type ON jobs(trigger_type);
CREATE INDEX idx_jobs_template_id ON jobs(template_id);

CREATE INDEX idx_job_executions_job_id ON job_executions(job_id);
CREATE INDEX idx_job_executions_status ON job_executions(status);
CREATE INDEX idx_job_executions_started_at ON job_executions(started_at);

CREATE INDEX idx_job_templates_created_by ON job_templates(created_by);
CREATE INDEX idx_job_templates_organization_id ON job_templates(organization_id);
CREATE INDEX idx_job_templates_script_type ON job_templates(script_type);

CREATE INDEX idx_job_notifications_job_id ON job_notifications(job_id);
CREATE INDEX idx_job_notifications_type ON job_notifications(notification_type);
CREATE INDEX idx_job_notifications_trigger ON job_notifications(trigger_on);

-- Metric Summarizer tables
CREATE TABLE metric_temp (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internal_job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    export_job_id VARCHAR(255),
    frequency VARCHAR(20) NOT NULL,
    change_threshold NUMERIC(10, 2) NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT valid_frequency CHECK (frequency IN ('daily', 'weekly', 'monthly')),
    CONSTRAINT valid_metric_status CHECK (status IN ('pending', 'processing', 'completed', 'failed'))
);

CREATE TABLE meter_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id VARCHAR(255) NOT NULL,
    meter_id VARCHAR(255) NOT NULL,
    meter_name VARCHAR(255),
    usage_date TIMESTAMP WITH TIME ZONE NOT NULL,
    billing_period_start TIMESTAMP WITH TIME ZONE,
    billing_period_end TIMESTAMP WITH TIME ZONE,
    meter_usage NUMERIC(20, 10),
    ipu NUMERIC(20, 10),
    scalar VARCHAR(100),
    metric_category VARCHAR(100),
    org_name VARCHAR(255),
    org_type VARCHAR(100),
    ipu_rate NUMERIC(20, 10),
    job_id UUID REFERENCES metric_temp(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT uq_meter_usage_meter_date UNIQUE (meter_id, usage_date)
);

-- Indexes for metric_temp
CREATE INDEX idx_metric_temp_internal_job_id ON metric_temp(internal_job_id);
CREATE INDEX idx_metric_temp_export_job_id ON metric_temp(export_job_id);
CREATE INDEX idx_metric_temp_status ON metric_temp(status);
CREATE INDEX idx_metric_temp_frequency ON metric_temp(frequency);

-- Indexes for meter_usage
CREATE INDEX idx_meter_usage_org_id ON meter_usage(org_id);
CREATE INDEX idx_meter_usage_meter_id ON meter_usage(meter_id);
CREATE INDEX idx_meter_usage_usage_date ON meter_usage(usage_date);
CREATE INDEX idx_meter_usage_job_id ON meter_usage(job_id);
CREATE INDEX idx_meter_usage_meter_date ON meter_usage(meter_id, usage_date);
