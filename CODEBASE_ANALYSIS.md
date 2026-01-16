# Codebase Analysis

## Project Overview
FastAPI-based job scheduling and execution system for Informatica ETL jobs with APScheduler for cron/frequency triggers, JWT authentication, and comprehensive job execution tracking.

## Tech Stack
- **Backend**: FastAPI, SQLAlchemy, PostgreSQL
- **Scheduler**: APScheduler (AsyncIOScheduler)
- **Auth**: JWT tokens, OAuth2PasswordBearer
- **Database**: PostgreSQL with Alembic migrations
- **Config**: Pydantic Settings with .env

## Architecture

### Entry Point
- `main.py` - FastAPI app with CORS, exception handlers, and router inclusion
- Lifespan: Creates DB tables, starts scheduler on startup; stops scheduler on shutdown

### Database Models (`src/models/`)

**Base Models:**
- `BaseSchema` (in `base.py` and `database.py`): UUID id, created_at, updated_at

**Core Entities:**
- `User` - username, email, password_hash, is_active; relationships: job_templates, jobs, organizations (many-to-many)
- `Organization` - name, description, domain, identifier, username, password, environment, configuration (JSON); relationships: job_templates, jobs, job_logs
- `UserOrganization` - Join table with role ('admin', 'member', 'viewer')

**Job Entities:**
- `JobTemplate` - title, description, script_type ('predefined'), script_path, parameters_schema (JSON), is_active
- `Job` - title, template_id, organization_id, parameters (JSON), status, trigger_type, frequency_* fields, cron_expression, timeout_seconds, max_retries
  - Triggers: 'manual', 'frequency', 'cron'
  - Status: 'pending', 'running', 'completed', 'failed', 'cancelled', 'paused'
- `JobExecution` - job_id, status, started_at, completed_at, result (JSON), error_message, retry_count
- `JobNotification` - job_id, notification_type ('email', 'webhook', 'slack'), trigger_on ('success', 'failure', 'both'), configuration (JSON)

**Informatica Entities:**
- `InformaticaJobRuns` - organization_id, status, sync_performed_at, completed_at, error_message
- `InformaticaJobLogs` - job_run_id, organization_id, informatica_id, type, object_id, object_name, run_id, timestamps, state, row counts (failed/success source/target), agent_id, error_msg, JSON fields (entries, sub_task_entries, transformation_entries, session_variables, log_entry_item_attrs), log_data (Text)
  - Unique constraint on (object_id, run_id, organization_id)

### Module Structure (`src/modules/`)

Each module follows pattern: `routes.py`, `schema.py`, `service.py`

**job/ - Job Management**
- `routes.py`: CRUD with filtering by status, trigger_type, template_id, organization_id, numeric/date operators
  - POST `/jobs`: Creates job with emailIds (for notification), schedules if cron/frequency with status "running"
  - PUT `/jobs/{job_id}`: Updates job, notifications, reschedules
  - POST `/jobs/{job_id}/run`: Manual trigger
  - GET `/jobs/scheduled/list`: List scheduled jobs
- `service.py`: `create_job()` handles template_id as UUID or script path (finds/creates template from PREDEFINED_SCRIPTS), `get_jobs()` with complex operator filtering (lt, gt, lte, gte, eq, ne)

**job_execution/ - Execution Tracking**
- `routes.py`: GET `/job-executions`, `/job-executions/job/{job_id}`, `/job-executions/{execution_id}`
- `service.py`: `get_executions()` with filters (organization_id, job_id, status, started_at, completed_at, retry_count operators), joins Job for organization filter

**job_template/ - Template Management**
- CRUD operations for reusable job templates

**job_notification/ - Notification Management**
- Service for email/webhook notifications on job completion

**user/ - User Management**
- Public router: POST `/users/register`, POST `/users/login` (returns JWT token)
- Protected router: GET `/users`, GET `/users/{id}`, PUT `/users/{id}`, DELETE `/users/{id}`
- Schema: UserCreate, UserResponse, UserLogin, Token

**organization/ - Organization Management**
- CRUD for Informatica organizations with credentials

**user_organization/ - User-Organization Associations**
- Manage user roles in organizations

**informatica_job_logs/ - Informatica Log Storage**
- API for storing/retrieving Informatica job run logs

**ai_chatbot/ - AI Integration**
- Routes for AI-powered chatbot (likely for job assistance)

**webhook/ - Webhook Endpoints**
- External webhook handling

**job_monitoring/ - Job Monitoring Agent**
- `routes.py`: 
  - POST `/job-monitoring/monitor`: Triggers monitoring report for a job by name, sends email with job details and execution history
  - GET `/job-monitoring/job/{job_name}`: Retrieves job details by name
  - GET `/job-monitoring/executions/{job_name}`: Retrieves recent executions for a job by name (with limit param)
- `service.py`:
  - `monitor_job()`: Gets job by name, retrieves all executions, builds HTML email report with job details and execution table, sends via `send_email_with_attachment()`
  - `get_job_details_by_name()`: Returns job with template and organization info
  - `get_job_executions_by_name()`: Returns paginated executions sorted by started_at desc
  - `_build_email_body()`: Creates HTML email with job info table and execution history table (Execution ID, Status, Started At, Completed At, Retry Count, Error Message)

**job_skip/ - Job Skip Agent**
- `routes.py`:
  - POST `/job-skip/check`: Checks for missed jobs within time window and sends notification
  - GET `/job-skip/organization/{organization_id}/missed`: Retrieves missed jobs without sending notification (query param: time_window_hours)
- `service.py`:
  - `check_job_skips()`: Validates organization, identifies skipped jobs, sends notification if any found
  - `_identify_skipped_jobs()`: Gets all running scheduled jobs (frequency/cron), checks last execution time
  - `_check_expected_run()`: For frequency jobs, calculates expected next run; for cron jobs, uses croniter to get next scheduled run; returns missed if expected time is past
  - `_get_next_cron_run()`: Uses croniter to calculate next scheduled run from cron expression
  - `_send_skip_notification()`: Sends HTML email alert with missed job details table
  - `_build_skip_email_body()`: Creates HTML email with missed jobs table (Job Name, Last Run Time, Expected Run Time, Skip Reason)

### Job Skip Flow
1. Client POSTs to `/api/v1/job-skip/check` with organization_id, email_recipients, time_window_hours (default 24)
2. JobSkipService.check_job_skips():
   - Validates organization exists
   - Gets all "running" jobs with trigger_type "frequency" or "cron" for that organization
   - For each job: Gets last execution from JobExecution table
   - Calculates expected next run time based on trigger type:
     - Frequency: last_run + interval_seconds
     - Cron: Uses croniter to get next scheduled run
   - If expected run time is past current time and last run is within time window → marked as missed
3. If missed jobs exist: Sends HTML email notification via `send_email_with_attachment()`
4. Returns JobSkipCheckResponse with missed_jobs_count

### Utilities (`src/utils/`)

**config.py** - Pydantic Settings
- Database, JWT, Email, OpenAI, Webhook config

**database.py** - SQLAlchemy Setup
- Engine with pool (size=10, max_overflow=20)
- SessionLocal generator for dependency injection
- `create_db_and_tables()` imports all models and creates tables

**auth.py** - JWT Authentication
- `create_access_token()`, `verify_access_token()`, `get_current_user()`
- `inject_user_fields()` decorator for request body modification

**scheduler.py** - APScheduler Integration
- `JobScheduler` class:
  - `start()`: Loads existing "running" jobs
  - `schedule_job()`: Handles cron/frequency/manual triggers based on job status
  - `_execute_job()`: Creates JobExecution record, runs script via `_run_job_script()`
  - `_run_job_script()`: For predefined scripts, runs `python src/scripts/{script_path}.py --job_id {job.id} --execution_id {execution.id}`
  - `_send_notifications()`: Sends notifications based on trigger_on

**constants.py** - PREDEFINED_SCRIPTS
- List of predefined scripts with name, description, script, parameters

**organization_handlers.py, informatica.py, notify.py** - Helper utilities

### Scripts (`src/scripts/`)
Python scripts executed by scheduler:
- `incremental_log_sync.py`
- `metric_summarizer.py`
- `unused_connections.py`
- `delayed_jobs.py`
- `user_disabling.py`
- `paginated_job_logs.py`

## Key Flows

### Job Creation Flow
1. Client POSTs to `/api/v1/jobs` with JobCreate + emailIds
2. JobService.create_job():
   - Parses template_id as UUID or script_path
   - If script_path: finds/creates JobTemplate from PREDEFINED_SCRIPTS
   - Validates organization exists
   - Creates Job record
3. JobNotificationService creates email notification
4. If trigger_type is 'cron'/'frequency' and status 'running': scheduler.schedule_job()

### Job Execution Flow
1. Scheduler fires job → `_execute_job(job_id)`
2. Fetches Job and JobTemplate from DB
3. Creates JobExecution record (status='running')
4. Calls `_run_job_script()` → executes `python src/scripts/{script_path}.py --job_id {job.id} --execution_id {execution.id}`
5. Sends notifications via `_send_notifications()`
6. Updates JobExecution status (completed/failed)

### Authentication Flow
1. User registers/login → returns JWT access token
2. Client sends `Authorization: Bearer <token>` header
3. `get_current_user()` dependency validates token and injects User object

### Job Monitoring Flow
1. Client POSTs to `/api/v1/job-monitoring/monitor` with job_name and email_recipients
2. JobMonitoringService.monitor_job():
   - Finds job by name
   - Retrieves all executions for the job (ordered by started_at desc)
   - Builds HTML email report with job details (title, status, trigger_type, template, organization)
   - Includes execution history table with all executions
   - Sends email via `send_email_with_attachment()` using configured email settings
3. Returns JobMonitoringResponse with execution count and timestamp

## API Endpoints Summary

| Module | Prefix | Endpoints |
|--------|--------|-----------|
| users | /api/v1/users | POST /login, POST /register, GET /, GET /{id}, PUT /{id}, DELETE /{id} |
| organizations | /api/v1/organizations | CRUD |
| user-organizations | /api/v1/user-organizations | CRUD |
| job-templates | /api/v1/job-templates | CRUD |
| jobs | /api/v1/jobs | GET /, POST /, GET /{id}, PUT /{id}, DELETE /{id}, POST /{id}/run, GET /scheduled/list |
| job-executions | /api/v1/job-executions | GET /, GET /job/{job_id}, GET /{execution_id} |
| job-notifications | /api/v1/job-notifications | CRUD |
| informatica-job-logs | /api/v1/informatica-job-logs | CRUD |
| ai-chatbot | /api/v1/ai-chatbot | Chat endpoints |
| webhook | /api/v1/webhook | Webhook endpoints |
| job-monitoring | /api/v1/job-monitoring | POST /monitor, GET /job/{job_name}, GET /executions/{job_name} |
| job-skip | /api/v1/job-skip | POST /check, GET /organization/{organization_id}/missed |

## Build/Run Commands
```bash
# Run dev server
python main.py

# Lint
flake8 src/ main.py

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "message"
alembic downgrade -1
alembic history

# Tests
pytest
```

## Code Style
- Imports: Standard library → Third-party → Local (from src.)
- Models: Inherit BaseSchema, use UUID PKs, constraints in `__table_args__`
- Schemas: Pydantic v2 with `from_attributes = True`, separate Create/Update/Response
- Routes: APIRouter with prefix/tags, `Depends(get_current_user)` for protected, `Depends(db)` for session
- Services: Business logic, raise ValueError (400) / Exception (500)
- Naming: Models PascalCase, tables snake_case plural, routes snake_case, services snake_case
- Pagination: skip/limit query params with ge/le constraints
- UUID: `UUID(as_uuid=True)`, convert to string for API
- JSON columns: `Column(JSON, default={})`

## Key Relationships
- User → JobTemplate (one-to-many via created_by)
- User → Job (one-to-many via created_by)
- User ↔ Organization (many-to-many via UserOrganization)
- Organization → JobTemplate (one-to-many)
- Organization → Job (one-to-many)
- Organization → InformaticaJobLogs (one-to-many)
- JobTemplate → Job (one-to-many)
- Job → JobExecution (one-to-many, cascade delete)
- Job → JobNotification (one-to-many, cascade delete)
- InformaticaJobRuns → InformaticaJobLogs (one-to-many, cascade delete)
