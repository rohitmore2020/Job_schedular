import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from rich.logging import RichHandler

from backend.app.core.config import settings
from backend.app.core.database import get_db, engine
from backend.app.api.v1 import api_router

# Setup Rich Logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("scheduler.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan events."""
    logger.info(f"🚀 Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")
    
    # Test Database Connectivity
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 AS ready"))
            row = result.fetchone()
            if row and row[0] == 1:
                logger.info("✅ PostgreSQL Database connection established successfully!")
    except Exception as e:
        logger.error(f"❌ Database connection failed on startup: {e}")

    yield

    logger.info("🛑 Shutting down FastAPI application, closing database pool...")
    await engine.dispose()
    logger.info("👋 Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Production-inspired Distributed Job Scheduler Control Plane API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API v1 Routers
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["General"])
async def root():
    """Root endpoint returning service status and documentation link."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX,
    }


@app.get("/health", tags=["Health"])
@app.get(f"{settings.API_V1_PREFIX}/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint checking application and database readiness."""
    try:
        result = await db.execute(text("SELECT 1"))
        ready = result.scalar()
        if ready == 1:
            return {
                "status": "healthy",
                "database": "connected",
                "environment": settings.ENVIRONMENT,
                "version": settings.VERSION,
            }
    except Exception as e:
        logger.error(f"Health check DB probe failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database probe failed: {str(e)}",
        )
