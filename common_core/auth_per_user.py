# utils/auth_per_user.py
"""
Per-user authentication utilities for IPAM API Gateway
Handles both Kong Gateway forwarded credentials and direct authentication
"""

import base64
import logging
from typing import Tuple, Optional, Union
from fastapi import HTTPException, status, Request

logger = logging.getLogger(__name__)


def extract_user_credentials(request: Request) -> Optional[Union[Tuple[str, str], Tuple[str, str, str]]]:
    """
    Extract user credentials from Kong Gateway headers or Authorization header.
    Supports both username/password and API token authentication.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Tuple of (username, password) for basic auth or (token, secret, 'token') for token auth, None if no credentials found
    """
    
    # Method 1: API Token authentication (highest priority)
    token = request.headers.get("X-User-IPAM-Token")
    secret = request.headers.get("X-User-IPAM-Secret")
    
    if token and secret:
        logger.debug("Found API token credentials")
        return token, secret, 'token'
    
    # Method 2: Kong Gateway forwarded headers (username/password)
    kong_username = request.headers.get("X-User-IPAM-Username")
    kong_password = request.headers.get("X-User-IPAM-Password")
    
    if kong_username and kong_password:
        logger.debug("Found Kong Gateway forwarded credentials")
        return kong_username, kong_password
    
    # Method 3: Direct Authorization header (Basic Auth)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            # Decode Basic Auth
            encoded_credentials = auth_header.replace("Basic ", "")
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
            
            # Re-encode for IPAM (IPAM expects base64 encoded credentials)
            encoded_username = base64.b64encode(username.encode()).decode("utf-8")
            encoded_password = base64.b64encode(password.encode()).decode("utf-8")
            
            logger.debug("Extracted credentials from Authorization header")
            return encoded_username, encoded_password
            
        except Exception as e:
            logger.warning(f"Failed to decode Authorization header: {e}")
            return None
    
    # Method 4: Custom headers (X-IPAM-Username, X-IPAM-Password)
    custom_username = request.headers.get("X-IPAM-Username")
    custom_password = request.headers.get("X-IPAM-Password")
    
    if custom_username and custom_password:
        logger.debug("Found custom IPAM headers")
        return custom_username, custom_password
    
    logger.debug("No user credentials found in request")
    return None


def validate_credentials_format(username: str, password: str) -> bool:
    """
    Validate that credentials are properly formatted for IPAM.
    
    Args:
        username: Base64 encoded username
        password: Base64 encoded password
        
    Returns:
        True if credentials are valid format, False otherwise
    """
    try:
        # Try to decode to ensure they're valid base64
        base64.b64decode(username).decode("utf-8")
        base64.b64decode(password).decode("utf-8")
        return True
    except Exception:
        return False


def get_user_identity(request: Request) -> Optional[str]:
    """
    Extract user identity for logging and audit purposes.
    
    Args:
        request: FastAPI request object
        
    Returns:
        User identity string if available, None otherwise
    """
    
    # Try various headers that might contain user identity
    identity_headers = [
        "X-Authenticated-UserID",
        "X-User-ID", 
        "X-Remote-User",
        "X-Forwarded-User",
        "X-Kong-Consumer-Username"
    ]
    
    for header in identity_headers:
        user_id = request.headers.get(header)
        if user_id:
            return user_id
    
    # Try to extract from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        try:
            encoded_credentials = auth_header.replace("Basic ", "")
            decoded_credentials = base64.b64decode(encoded_credentials).decode("utf-8")
            username = decoded_credentials.split(":", 1)[0]
            return username
        except Exception:
            pass
    
    # Try custom IPAM headers
    custom_username = request.headers.get("X-IPAM-Username")
    if custom_username:
        try:
            return base64.b64decode(custom_username).decode("utf-8")
        except Exception:
            return custom_username
    
    return None


def create_auth_context(request: Request) -> dict:
    """
    Create authentication context for logging and monitoring.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Dictionary containing auth context information
    """
    
    user_credentials = extract_user_credentials(request)
    user_identity = get_user_identity(request)
    
    return {
        "has_user_credentials": user_credentials is not None,
        "user_identity": user_identity,
        "auth_method": _determine_auth_method(request),
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent", "Unknown"),
        "correlation_id": request.headers.get("X-Correlation-ID")
    }


def _determine_auth_method(request: Request) -> str:
    """
    Determine the authentication method used.
    
    Args:
        request: FastAPI request object
        
    Returns:
        String describing the auth method
    """
    
    if request.headers.get("X-User-IPAM-Token"):
        return "api-token"
    elif request.headers.get("X-User-IPAM-Username"):
        return "kong-forwarded"
    elif request.headers.get("Authorization", "").startswith("Basic "):
        return "basic-auth"
    elif request.headers.get("X-IPAM-Username"):
        return "custom-headers"
    else:
        return "no-credentials"