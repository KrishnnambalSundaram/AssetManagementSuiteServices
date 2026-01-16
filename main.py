# Standard imports
import logging
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

# Routes
from src.modules.job.routes import router as job_router
from src.modules.job_notification.routes import \
    router as job_notification_router
from src.modules.job_template.routes import router as job_template_router
from src.modules.job_execution.routes import router as job_execution_router
from src.modules.user.routes import protected_router as user_protected_router
from src.modules.user.routes import public_router as user_public_router
from src.modules.organization.routes import router as organization_router
from src.modules.user_organization.routes import router as user_organization_router
from src.modules.informatica_job_logs.routes import router as informatica_job_logs_router
from src.modules.ai_chatbot.routes import router as ai_chatbot_router
from src.modules.webhook.routes import router as webhook_router
from src.modules.job_monitoring.routes import router as job_monitoring_router
from src.modules.job_skip.routes import router as job_skip_router

# Local imports
from src.utils.config import settings
from src.utils.database import create_db_and_tables
from src.utils.scheduler import start_scheduler, stop_scheduler

load_dotenv()

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger(__name__)


# Create FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Job Scheduler API...")

    # Create database tables
    logger.info("Creating database tables")
    create_db_and_tables()

    # Start background scheduler
    # await start_scheduler()

    yield

    # Shutdown
    logger.info("Shutting down Job Scheduler API...")
    await stop_scheduler()


app = FastAPI(
    title="Job Scheduler API",
    description="A flexible job scheduling and execution service",
    version="1.0.0",
    lifespan=lifespan,
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    
    openapi_schema["security"] = [{"Bearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail, "status_code": exc.status_code},
    )


# Include API routes
app.include_router(user_protected_router, prefix="/api/v1")
app.include_router(user_public_router, prefix="/api/v1")
app.include_router(organization_router, prefix="/api/v1")
app.include_router(user_organization_router, prefix="/api/v1")
app.include_router(job_template_router, prefix="/api/v1")
app.include_router(job_router, prefix="/api/v1")
app.include_router(job_notification_router, prefix="/api/v1")
app.include_router(job_execution_router, prefix="/api/v1")
app.include_router(informatica_job_logs_router, prefix="/api/v1")
app.include_router(ai_chatbot_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")
app.include_router(job_monitoring_router, prefix="/api/v1")
app.include_router(job_skip_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True if settings.ENVIRONMENT == "development" else False,
        timeout_keep_alive=600, # 600 seconds = 10 minutes
    )
