"""
OSKAR — ECN router assembly.

Assembles ecn_router from three sub-modules and re-exports it so
src/routers/__init__.py continues to work unchanged.

Sub-modules:
  ecn_core    — ECN CRUD, workflow transitions, roles, approval
  ecn_items   — Item + MPN CRUD
  ecn_routing — Routing operation CRUD
  ecn_schemas — All Pydantic models and serialiser helpers (shared)
"""

from fastapi import APIRouter

from src.routers.ecn_core import ecn_core_router
from src.routers.ecn_items import ecn_items_router
from src.routers.ecn_routing import ecn_routing_router

ecn_router = APIRouter(prefix="/ecn")
ecn_router.include_router(ecn_core_router)
ecn_router.include_router(ecn_items_router)
ecn_router.include_router(ecn_routing_router)
