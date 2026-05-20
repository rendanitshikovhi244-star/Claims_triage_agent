"""
Shared configuration for Claims Triage application.

This configuration is used by both the API server and the CLI entrypoint.
Values can be overridden via environment variables.
"""

import os


CONFIG: dict[str, str | int] = {
    # AWS Configuration
    "REGION": os.environ.get("AWS_REGION", "us-east-1"),
    "SECRET_NAME": os.environ.get("SECRET_NAME", "claims-triage-agent-secret"),
    "AWS_PROFILE": os.environ.get("AWS_PROFILE", None),
    # Redis Configuration
    "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    # Database Configuration
    "DATABASE_URL": os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/insurance"
    ),
    # Session Configuration
    "SESSION_DB_URL": os.environ.get("SESSION_DB_URL", "sqlite+aiosqlite:///./claims_sessions.db"),
}
