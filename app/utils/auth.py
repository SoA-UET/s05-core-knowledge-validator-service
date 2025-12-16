"""
JWT Authentication and Authorization utilities.
Implements JWKS-based verification according to VERIFY.md specification.
"""

import os
import json
import threading
import time
import jwt
import requests
from functools import wraps
from typing import Any, Callable
from flask import request, g
from dotenv import load_dotenv

load_dotenv()


class JWKSManager:
    """
    Manages JWKS (JSON Web Key Set) retrieval and caching.
    Thread-safe implementation with TTL-based refresh.
    """

    def __init__(self):
        self._keys: dict[str, dict] = {}  # kid -> key info
        self._lock = threading.Lock()
        self._last_refresh: float = 0
        self._ttl_minutes = int(os.getenv("JWKS_TTL_IN_MINUTES", "10"))
        self._identity_service_url = os.getenv("IDENTITY_SERVICE_URL", "")

    def _should_refresh(self) -> bool:
        """Check if JWKS cache should be refreshed based on TTL."""
        if not self._last_refresh:
            return True
        elapsed = time.time() - self._last_refresh
        return elapsed >= (self._ttl_minutes * 60)

    def _fetch_jwks(self) -> None:
        """
        Fetch JWKS from Identity Service.
        Only called when TTL expires, never on verification failure.
        """
        if not self._identity_service_url:
            print("Warning: IDENTITY_SERVICE_URL not configured")
            return

        try:
            url = f"{self._identity_service_url}/.well-known/jwks.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            jwks_data = response.json()

            # Handle both single key and array of keys
            keys = jwks_data if isinstance(jwks_data, list) else [jwks_data]

            new_keys = {}
            for key_info in keys:
                kid = key_info.get("kid")
                if kid:
                    new_keys[kid] = key_info

            with self._lock:
                self._keys = new_keys
                self._last_refresh = time.time()

            print(f"JWKS refreshed successfully. {len(new_keys)} key(s) loaded.")

        except Exception as e:
            print(f"Warning: Failed to fetch JWKS: {e}")
            # Continue using cached keys (graceful degradation)

    def get_public_key(self, kid: str) -> str | None:
        """
        Get the public key for a given key ID.
        Does NOT refresh JWKS on cache miss (per spec).

        Args:
            kid: The key ID from the JWT header

        Returns:
            The public key in PEM format, or None if not found
        """
        # Check if refresh is needed based on TTL
        if self._should_refresh():
            self._fetch_jwks()

        with self._lock:
            key_info = self._keys.get(kid)
            if key_info:
                return key_info.get("public_key")
        return None

    def refresh_keys(self) -> None:
        """
        Force refresh JWKS. Called at service startup and by TTL scheduler.
        """
        self._fetch_jwks()

    def start_background_refresh(self) -> None:
        """
        Start a background thread for periodic JWKS refresh.
        """

        def refresh_loop():
            while True:
                time.sleep(self._ttl_minutes * 60)
                self._fetch_jwks()

        thread = threading.Thread(target=refresh_loop, daemon=True)
        thread.start()


# Singleton instance
jwks_manager = JWKSManager()


def verify_jwt(token: str) -> dict[str, Any]:
    """
    Verify a JWT token and return its payload.

    Args:
        token: The JWT token string

    Returns:
        The decoded JWT payload

    Raises:
        ValueError: If verification fails for any reason
    """
    try:
        # Step 1: Parse JWT header without verification
        unverified_header = jwt.get_unverified_header(token)

        alg = unverified_header.get("alg")
        kid = unverified_header.get("kid")

        # Validate algorithm
        if alg != "RS256":
            raise ValueError(f"Invalid algorithm: {alg}. Only RS256 is supported.")

        # Validate kid presence
        if not kid:
            raise ValueError("Missing 'kid' in JWT header")

        # Step 2: Resolve public key
        public_key = jwks_manager.get_public_key(kid)
        if not public_key:
            raise ValueError(f"Unknown key ID: {kid}")

        # Step 3: Verify signature and decode
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={
                "require": ["exp", "iat", "sub"],
                "verify_exp": True,
                "verify_iat": True,
            },
        )

        # Step 4: Validate required claims
        if not payload.get("sub"):
            raise ValueError("Missing 'sub' claim")
        if not payload.get("full_name"):
            raise ValueError("Missing 'full_name' claim")
        if not payload.get("email"):
            raise ValueError("Missing 'email' claim")

        # Ensure permissions is an array (default to empty)
        if "permissions" not in payload:
            payload["permissions"] = []
        elif not isinstance(payload["permissions"], list):
            raise ValueError("'permissions' claim must be an array")

        return payload

    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")


def auth_required(f: Callable) -> Callable:
    """
    Decorator for Flask routes that require JWT authentication.
    Sets g.user with the verified JWT payload.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return {"status": "error", "message": "Missing or invalid Authorization header"}, 401

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            payload = verify_jwt(token)
            g.user = payload
            g.user_id = payload.get("sub")
            g.permissions = payload.get("permissions", [])
            return f(*args, **kwargs)
        except ValueError as e:
            print(f"JWT verification failed: {e}")
            return {"status": "error", "message": "Unauthorized"}, 401

    return decorated_function


def permission_required(*required_permissions: str) -> Callable:
    """
    Decorator for Flask routes that require specific permissions.
    Must be used after @auth_required.

    Args:
        *required_permissions: Permission strings that the user must have (any one of them)
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_permissions = getattr(g, "permissions", [])

            # Check if user has any of the required permissions
            has_permission = any(p in user_permissions for p in required_permissions)
            if not has_permission:
                return {"status": "error", "message": "Forbidden"}, 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def init_auth():
    """
    Initialize authentication system.
    Should be called at service startup.
    """
    # Initial JWKS fetch
    jwks_manager.refresh_keys()

    # Start background refresh
    jwks_manager.start_background_refresh()

    print("Authentication system initialized")
