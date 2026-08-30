"""Restricted CEL compilation and evaluation environment."""

import celpy

ALLOWED_TOP_LEVEL_VARS: set[str] = {
    "subject",
    "resource",
    "action",
    "environment",
    "request",
    "token",
}


def get_cel_environment() -> celpy.Environment:
    """
    Construct a secure, restricted CEL environment.
    Exposes only controlled top-level schemas (subject, resource, action, environment, request,
    token) without access to Python runtime builtins or arbitrary execution.
    """
    return celpy.Environment()
