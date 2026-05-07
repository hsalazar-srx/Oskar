"""
OSKAR — src.services.ecn package.

Re-exports every public name that existed in the old src/services/ecn.py so
that all existing imports (routers, tasks, tests) continue to work unchanged.
"""

from src.services.ecn.models import (
    VALID_FACILITIES,
    VALID_ROLE_IDS,
    ApprovalStep,
    ECNConflict,
    ECNCreateRequest,
    ECNDetail,
    ECNForbidden,
    ECNItemDetail,
    ECNMPNDetail,
    ECNNotFound,
    ECNPreconditionRequired,
    ECNStatusTransitionRequest,
    ECNSummary,
    ECNTransitionError,
    ECNUpdateRequest,
    ECNValidationError,
    RoleAssignment,
    RoleAssignmentResult,
)
from src.services.ecn.service import ECNService

__all__ = [
    "VALID_FACILITIES",
    "VALID_ROLE_IDS",
    "ApprovalStep",
    "ECNConflict",
    "ECNCreateRequest",
    "ECNDetail",
    "ECNForbidden",
    "ECNItemDetail",
    "ECNMPNDetail",
    "ECNNotFound",
    "ECNPreconditionRequired",
    "ECNStatusTransitionRequest",
    "ECNSummary",
    "ECNTransitionError",
    "ECNUpdateRequest",
    "ECNValidationError",
    "RoleAssignment",
    "RoleAssignmentResult",
    "ECNService",
]
