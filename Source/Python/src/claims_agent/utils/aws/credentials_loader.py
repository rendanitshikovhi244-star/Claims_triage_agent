"""
Unified credential loader that uses AWS Secrets Manager exclusively
"""

import json
import logging

import boto3
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)

# Cached secrets — loaded once per process
_cached_secrets: dict | None = None


def load_secrets_if_available() -> dict:
    """
    Try to load secrets from AWS Secrets Manager using app config.
    Falls back to an empty dict if unavailable (local dev uses .env instead).

    Results are cached so repeated calls don't hit Secrets Manager.
    """
    global _cached_secrets  # noqa: PLW0603
    if _cached_secrets is not None:
        return _cached_secrets

    from claims_agent.configs.app_config import CONFIG

    try:
        _cached_secrets = loadCredentials(
            secret_name=CONFIG["SECRET_NAME"],
            region_name=CONFIG["REGION"],
            profile_name=CONFIG.get("AWS_PROFILE"),
        )
        logger.info("Successfully loaded credentials from AWS Secrets Manager")
        return _cached_secrets
    except Exception as e:
        logger.info(f"AWS Secrets Manager unavailable ({e}), falling back to .env")
        _cached_secrets = {}
        return _cached_secrets


def loadCredentials(secret_name=None, region_name="us-east-1", profile_name=None):
    # Use provided parameters or fall back to environment variables
    logger.info(f"Loading credentials from AWS Secrets Manager: {secret_name}")
    try:
        # Create a Secrets Manager client
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
            client = session.client(service_name="secretsmanager", region_name=region_name)
        else:
            client = boto3.client(service_name="secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)  # Retrieve the secret value
        return json.loads(response["SecretString"])  # Parse the secret string as JSON
    except ClientError as e:
        logger.info(f"Failed to load secrets: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse secret as JSON: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error during secret manager loader: {e}")
        raise
