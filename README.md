# Job Scheduler API

A flexible job scheduling and execution service built with FastAPI, SQLAlchemy, and PostgreSQL.

---

## Features

- **User Management**: CRUD operations for user accounts with password hashing and JWT authentication.
- **Organization Management**: Multi-tenant organization support for job templates and jobs.
- **Job Templates**: Reusable job templates with script definitions and parameter schemas.
- **Job Management**: Create, schedule, and manage jobs with various trigger types (manual, frequency, cron).
- **Job Notifications**: Configure notifications for job success/failure events.
- **RESTful API**: Full REST API with proper error handling and validation.
- **Database**: PostgreSQL with SQLAlchemy ORM.
- **Documentation**: Interactive API docs and Postman collection.

---

## Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd informatica
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv fastapi-env
   source fastapi-env/bin/activate  # On Windows: fastapi-env\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```env
   # Server
   PORT=8001

   # Database Configuration
   POSTGRES_USERNAME=postgres
   POSTGRES_PASSWORD=postgres
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DATABASE=informatica_dev

   # Security
   SECRET_KEY=your-secret-key-here
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30

   # Email (optional)
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USERNAME1=your-email@gmail.com
   EMAIL_PASSWORD1=your-email-app-password
   EMAIL_FROM=your-email@gmail.com

   # Logging
   LOG_LEVEL=INFO

   # Environment
   ENVIRONMENT=development

   WEBHOOK_BASE_URL = "http://localhost:1800"
   ```

5. **Set up PostgreSQL database**
   ```bash
   createdb job_scheduler
   # Or using psql
   psql -U postgres -c "CREATE DATABASE informatica_dev;"
   ```

6. **Run database migrations**
   ```bash
   # Activate virtual environment if not already activated
   source fastapi-env/bin/activate
   
   # Run migrations
   alembic upgrade head
   ```
   
   This will create all necessary database tables automatically.

7. **Run the application**
   ```bash
   python main.py
   ```

The API will be available at `http://localhost:8001`

---

## Database Migrations

This project uses **Alembic** for database migrations. Migrations allow you to version control your database schema and apply changes without running SQL manually.

### Running Migrations

**Apply all pending migrations:**
```bash
alembic upgrade head
```

**Create a new migration (after modifying models):**
```bash
alembic revision --autogenerate -m "Description of changes"
```

**Rollback the last migration:**
```bash
alembic downgrade -1
```

**View migration history:**
```bash
alembic history
```

**View current database revision:**
```bash
alembic current
```

### Migration Workflow

1. **Modify models** in `src/models/`
2. **Generate migration:**
   ```bash
   alembic revision --autogenerate -m "Add new feature"
   ```
3. **Review the generated migration** in `alembic/versions/`
4. **Apply migration:**
   ```bash
   alembic upgrade head
   ```

### Important Notes

- Always review auto-generated migrations before applying them
- Test migrations on a development database first
- Keep migrations small and focused on one change
- Never edit existing migrations that have been applied to production

---

## Authentication (JWT)

This API uses **JWT (JSON Web Token) authentication** for all protected endpoints.

### Public vs Protected Endpoints

**Public Endpoints** (No authentication required):
- `POST /api/v1/users/` - Create user account
- `POST /api/v1/users/login` - Login and get JWT token
- `GET /health` - Health check

**Protected Endpoints** (JWT token required):
- All other endpoints require a valid JWT token in the Authorization header

### How JWT Works

1. **Login**: Send credentials to `/api/v1/users/login`
2. **Get Token**: Receive JWT token in response
3. **Use Token**: Include token in `Authorization: Bearer <token>` header for all subsequent requests

### Example Usage

**Login:**
```bash
curl -X POST "http://localhost:8001/api/v1/users/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Using the token:**
```bash
curl -X GET "http://localhost:8001/api/v1/users/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Postman Setup

1. Import the `postman-collection.json` file
2. Run the "Login User" request first
3. The collection automatically saves the JWT token
4. All subsequent requests will use the saved token

### API Endpoints Summary

| Endpoint                        | Method     | Authentication |
|---------------------------------|------------|----------------|
| /health                         | GET        | Public         |
| /api/v1/users/                  | POST       | Public         |
| /api/v1/users/login             | POST       | Public         |
| /api/v1/users/                  | GET        | Protected      |
| /api/v1/users/me                | GET        | Protected      |
| /api/v1/users/{user_id}         | GET, PUT, DELETE | Protected |
| /api/v1/organizations/*         | ALL        | Protected      |
| /api/v1/job-templates/*         | ALL        | Protected      |
| /api/v1/jobs/*                  | ALL        | Protected      |
| /api/v1/job-notifications/*     | ALL        | Protected      |
| /api/v1/job-executions/*        | ALL        | Protected      |

### Troubleshooting
- **401 Unauthorized:**
  - Ensure you are sending the `Authorization: Bearer <token>` header.
  - Ensure your token is not expired.
  - Ensure you are not sending the token to public endpoints (not required).

---

## API Documentation

### Interactive Documentation

- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

### Documentation Files

- **Postman Collection**: `postman-collection.json` - Import into Postman for testing

---

## API Endpoints

### Base URL

```
http://localhost:8001/api/v1
```

### Users (`/users/`)
- `GET /` - List users with pagination (protected)
- `GET /me` - Get current user's profile (protected)
- `GET /{user_id}` - Get specific user (protected)
- `POST /` - Create new user (public)
- `PUT /{user_id}` - Update user (protected)
- `DELETE /{user_id}` - Delete user (protected)
- `POST /login` - Login and get JWT token (public)

### Organizations (`/organizations/`)
- `GET /` - List organizations with pagination (protected)
- `GET /{organization_id}` - Get specific organization (protected)
- `POST /` - Create new organization (protected)
- `PUT /{organization_id}` - Update organization (protected)
- `DELETE /{organization_id}` - Delete organization (protected)

### Job Templates (`/job-templates/`)
- `GET /` - List job templates (protected)
- `GET /{template_id}` - Get specific template (protected)
- `POST /` - Create new template (protected)
- `PUT /{template_id}` - Update template (protected)
- `DELETE /{template_id}` - Delete template (protected)

### Jobs (`/jobs/`)
- `GET /` - List jobs with last 5 executions (protected)
- `GET /{job_id}` - Get specific job with last 5 executions (protected)
- `POST /` - Create new job (protected)
- `PUT /{job_id}` - Update job (protected)
- `DELETE /{job_id}` - Delete job (protected)

### Job Notifications (`/job-notifications/`)
- `GET /` - List notifications (protected)
- `GET /{notification_id}` - Get specific notification (protected)
- `POST /` - Create new notification (protected)
- `PUT /{notification_id}` - Update notification (protected)
- `DELETE /{notification_id}` - Delete notification (protected)

### Job Executions (`/job-executions/`)
- `GET /job/{job_id}` - Get executions for a specific job (protected)

### Health Check
- `GET /health` - API health status

---

## Project Structure

```
informatica/
├── main.py                          # FastAPI application entry point
├── requirements.txt                 # Python dependencies
├── postman-collection.json          # Postman collection
├── src/
│   ├── models/                      # SQLAlchemy database models
│   ├── modules/                     # API modules (user, organization, job, job_template, job_notification)
│   └── utils/                       # Utility modules (config, auth, database, etc.)
```

---

## Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PORT` | Server port | `8001` | No |
| `POSTGRES_USERNAME` | PostgreSQL username | `postgres` | Yes |
| `POSTGRES_PASSWORD` | PostgreSQL password | `postgres` | Yes |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` | Yes |
| `POSTGRES_PORT` | PostgreSQL port | `5432` | Yes |
| `POSTGRES_DATABASE` | PostgreSQL database name | `informatica_dev` | Yes |
| `SECRET_KEY` | JWT secret key | `default-secret-key` | Yes |
| `ALGORITHM` | JWT algorithm | `HS256` | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT token expiry (minutes) | `30` | No |
| `INFORMATICA_USERNAME` | Informatica username | `admin` | No |
| `INFORMATICA_PASSWORD` | Informatica password | `admin` | No |
| `EMAIL_HOST` | SMTP host | - | No |
| `EMAIL_PORT` | SMTP port | `587` | No |
| `EMAIL_USERNAME1` | SMTP username | - | No |
| `EMAIL_PASSWORD1` | SMTP password | - | No |
| `EMAIL_FROM` | From email address | - | No |
| `LOG_LEVEL` | Logging level | `INFO` | No |
| `ENVIRONMENT` | Environment name | `development` | No |

---

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src
```

### Database Migrations

The database schema is defined in `db/database.ddl.sql`. To apply changes:

```bash
psql -U postgres -d informatica_dev -f db/database.ddl.sql
```

### Code Style

This project follows PEP 8 style guidelines. Use a linter like `flake8` or `black` for code formatting.

---

## License

This project is licensed under the MIT License.
