from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..deps import get_current_user
from ..models import Notification, User
from ..schemas import NotificationOut
from datetime import datetime, timezone

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(rows)


@router.post("/{notif_id}/mark-read", response_model=NotificationOut)
def mark_read(
    notif_id: UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Notification:
    notif = db.get(Notification, notif_id)
    if notif is None or notif.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found")
    if notif.read_at is None:
        notif.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(notif)
    return notif
