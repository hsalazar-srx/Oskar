"""
OSKAR — ECN comments/notes endpoints.

Comments are a lightweight annotation thread per ECN with no status restriction.
Unlike ecn_transition_history (immutable audit chain), comments are editable and
deletable by their author; DC may delete any comment.

GET    /ecn/{ecn_id}/comments                  List comments (oldest first)
POST   /ecn/{ecn_id}/comments                  Add a comment
PATCH  /ecn/{ecn_id}/comments/{comment_id}     Edit own comment
DELETE /ecn/{ecn_id}/comments/{comment_id}     Delete own comment (DC may delete any)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session

log = structlog.get_logger(__name__)

ecn_comments_router = APIRouter(tags=["ecn-comments"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CommentCreateBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class CommentUpdateBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


class CommentOut(BaseModel):
    id: str
    ecn_id: str
    author_username: str
    body: str
    created_at: str
    updated_at: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(dt: Any) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


async def _get_comment(
    session: AsyncSession, comment_id: str, ecn_id: str
) -> dict[str, Any]:
    row = await session.execute(
        sa.text(
            "SELECT id, ecn_id, author_username, body, created_at, updated_at "
            "FROM ecn_comments WHERE id = :id AND ecn_id = :ecn_id"
        ),
        {"id": comment_id, "ecn_id": ecn_id},
    )
    result = row.mappings().first()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return dict(result)


async def _ecn_exists(session: AsyncSession, ecn_id: str) -> bool:
    row = await session.execute(
        sa.text("SELECT 1 FROM ecn_instances WHERE id = :id"),
        {"id": ecn_id},
    )
    return row.scalar() is not None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@ecn_comments_router.get(
    "/{ecn_id}/comments",
    response_model=list[CommentOut],
)
async def list_comments(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CommentOut]:
    """List all comments for an ECN, ordered oldest first."""
    if not await _ecn_exists(session, ecn_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")

    rows = await session.execute(
        sa.text(
            "SELECT id, ecn_id, author_username, body, created_at, updated_at "
            "FROM ecn_comments WHERE ecn_id = :ecn_id ORDER BY created_at ASC"
        ),
        {"ecn_id": ecn_id},
    )
    return [
        CommentOut(
            id=str(r["id"]),
            ecn_id=str(r["ecn_id"]),
            author_username=r["author_username"],
            body=r["body"],
            created_at=_ts(r["created_at"]),
            updated_at=_ts(r.get("updated_at")),
        )
        for r in rows.mappings()
    ]


@ecn_comments_router.post(
    "/{ecn_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    ecn_id: str,
    body: CommentCreateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommentOut:
    """Add a comment to an ECN. Allowed at any status including CLOSED."""
    if not await _ecn_exists(session, ecn_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")

    comment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await session.execute(
        sa.text(
            "INSERT INTO ecn_comments (id, ecn_id, author_username, body, created_at) "
            "VALUES (:id, :ecn_id, :author, :body, :created_at)"
        ),
        {
            "id": comment_id,
            "ecn_id": ecn_id,
            "author": user.username,
            "body": body.body.strip(),
            "created_at": now,
        },
    )

    log.info("ecn.comment.added", ecn_id=ecn_id, comment_id=comment_id, actor=user.username)
    return CommentOut(
        id=comment_id,
        ecn_id=ecn_id,
        author_username=user.username,
        body=body.body.strip(),
        created_at=now.isoformat(),
        updated_at=None,
    )


@ecn_comments_router.patch(
    "/{ecn_id}/comments/{comment_id}",
    response_model=CommentOut,
)
async def update_comment(
    ecn_id: str,
    comment_id: str,
    body: CommentUpdateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CommentOut:
    """Edit a comment. Only the author may edit their own comment."""
    comment = await _get_comment(session, comment_id, ecn_id)

    if comment["author_username"] != user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the comment author may edit this comment.",
        )

    now = datetime.now(timezone.utc)
    await session.execute(
        sa.text(
            "UPDATE ecn_comments SET body = :body, updated_at = :updated_at WHERE id = :id"
        ),
        {"body": body.body.strip(), "updated_at": now, "id": comment_id},
    )

    return CommentOut(
        id=str(comment["id"]),
        ecn_id=str(comment["ecn_id"]),
        author_username=comment["author_username"],
        body=body.body.strip(),
        created_at=_ts(comment["created_at"]),
        updated_at=now.isoformat(),
    )


@ecn_comments_router.delete(
    "/{ecn_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_comment(
    ecn_id: str,
    comment_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    """Delete a comment. Author may delete their own; DC may delete any."""
    comment = await _get_comment(session, comment_id, ecn_id)

    is_dc = any(
        g in getattr(user, "groups", []) for g in ("OSKAR-DC",)
    )
    if comment["author_username"] != user.username and not is_dc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the comment author or DC may delete this comment.",
        )

    await session.execute(
        sa.text("DELETE FROM ecn_comments WHERE id = :id"),
        {"id": comment_id},
    )
    log.info("ecn.comment.deleted", ecn_id=ecn_id, comment_id=comment_id, actor=user.username)
