"""ABAC & Attribute-Based Authorization Subsystem."""

from app.authz.abac.attributes import (
    EnvironmentAttributes,
    RequestAttributes,
    ResourceAttributes,
    SubjectAttributes,
)
from app.authz.abac.cache import CompiledPolicyCache
from app.authz.abac.context import AuthorizationContext
from app.authz.abac.errors import ABACError, ABACPolicyDeniedError
from app.authz.abac.evaluator import ABACEvaluator
from app.authz.abac.policies import ABACPolicyRule, PolicyType

__all__ = [
    "SubjectAttributes",
    "ResourceAttributes",
    "EnvironmentAttributes",
    "RequestAttributes",
    "AuthorizationContext",
    "CompiledPolicyCache",
    "ABACEvaluator",
    "ABACPolicyRule",
    "PolicyType",
    "ABACError",
    "ABACPolicyDeniedError",
]
