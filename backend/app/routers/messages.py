from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.auth import get_current_user, require_admin
from app.db.session import get_db
from app.db.models import User, Message

router = APIRouter(prefix="/messages", tags=["messages"])


class MessageRequest(BaseModel):
    content: str

class ContactRequest(BaseModel):
    name:    str
    email:   str
    message: str


# ── Helper: get user without approval check ────────────────────────────────

async def get_active_user(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
) -> User:
    """Allow unapproved users to use messaging."""
    return current_user


# ── User: بعث message لـ admin ─────────────────────────────────────────────

@router.post("/send")
async def send_message(
    body: MessageRequest,
    db:   AsyncSession = Depends(get_db),
    current_user: User = Depends(get_active_user),
):
    result = await db.execute(select(User).where(User.role == "admin"))
    admin  = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(404, "No admin found")

    msg = Message(
        sender_id   = current_user.user_id,
        receiver_id = admin.user_id,
        content     = body.content,
    )
    db.add(msg)
    await db.commit()
    return {"message": "Message sent successfully"}


# ── User: جيب conversation مع admin ───────────────────────────────────────

@router.get("/my-conversation")
async def get_my_conversation(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_active_user),
):
    result = await db.execute(select(User).where(User.role == "admin"))
    admin  = result.scalar_one_or_none()
    if admin is None:
        return {"messages": []}

    msgs = await db.execute(
        select(Message)
        .where(
            or_(
                and_(Message.sender_id == current_user.user_id,
                     Message.receiver_id == admin.user_id),
                and_(Message.sender_id == admin.user_id,
                     Message.receiver_id == current_user.user_id),
            )
        )
        .order_by(Message.created_at.asc())
    )
    messages = msgs.scalars().all()

    for m in messages:
        if m.receiver_id == current_user.user_id and not m.is_read:
            m.is_read = True
    await db.commit()

    return {
        "messages": [
            {
                "message_id": m.message_id,
                "content":    m.content,
                "is_mine":    m.sender_id == current_user.user_id,
                "is_read":    m.is_read,
                "created_at": str(m.created_at),
            }
            for m in messages
        ]
    }


# ── Admin: جيب list ديال كل conversations ─────────────────────────────────

@router.get("/admin/conversations")
async def get_conversations(
    db:    AsyncSession = Depends(get_db),
    admin: User         = Depends(require_admin),
):
    result = await db.execute(
        select(User).where(User.role != "admin").order_by(User.username)
    )
    users = result.scalars().all()

    conversations = []
    for user in users:
        last_msg = await db.execute(
            select(Message)
            .where(
                or_(
                    and_(Message.sender_id == user.user_id,
                         Message.receiver_id == admin.user_id),
                    and_(Message.sender_id == admin.user_id,
                         Message.receiver_id == user.user_id),
                )
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last = last_msg.scalar_one_or_none()

        unread_result = await db.execute(
            select(Message)
            .where(Message.sender_id == user.user_id)
            .where(Message.receiver_id == admin.user_id)
            .where(Message.is_read == False)
        )
        unread_count = len(unread_result.scalars().all())

        conversations.append({
            "user_id":      user.user_id,
            "username":     user.username,
            "last_message": last.content if last else None,
            "last_time":    str(last.created_at) if last else None,
            "unread":       unread_count,
        })

    return {"conversations": conversations}


# ── Admin: جيب conversation مع user معين ──────────────────────────────────

@router.get("/admin/conversation/{user_id}")
async def get_conversation_with_user(
    user_id: str,
    db:      AsyncSession = Depends(get_db),
    admin:   User         = Depends(require_admin),
):
    msgs = await db.execute(
        select(Message)
        .where(
            or_(
                and_(Message.sender_id == user_id,
                     Message.receiver_id == admin.user_id),
                and_(Message.sender_id == admin.user_id,
                     Message.receiver_id == user_id),
            )
        )
        .order_by(Message.created_at.asc())
    )
    messages = msgs.scalars().all()

    for m in messages:
        if m.receiver_id == admin.user_id and not m.is_read:
            m.is_read = True
    await db.commit()

    return {
        "messages": [
            {
                "message_id": m.message_id,
                "content":    m.content,
                "is_mine":    m.sender_id == admin.user_id,
                "is_read":    m.is_read,
                "created_at": str(m.created_at),
            }
            for m in messages
        ]
    }


# ── Admin: رد على user ─────────────────────────────────────────────────────

@router.post("/admin/reply/{user_id}")
async def reply_to_user(
    user_id: str,
    body:    MessageRequest,
    db:      AsyncSession = Depends(get_db),
    admin:   User         = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.user_id == user_id))
    user   = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "User not found")

    msg = Message(
        sender_id   = admin.user_id,
        receiver_id = user_id,
        content     = body.content,
    )
    db.add(msg)
    await db.commit()
    return {"message": "Reply sent successfully"}


# ── Contact form (public) ──────────────────────────────────────────────────

@router.post("/contact")
async def contact_admin(
    body: ContactRequest,
    db:   AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.role == "admin"))
    admin  = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(404, "No admin found")

    msg = Message(
        sender_id   = admin.user_id,
        receiver_id = admin.user_id,
        content     = f"[Contact Form] From: {body.name} <{body.email}>\n\n{body.message}",
    )
    db.add(msg)
    await db.commit()
    return {"message": "Message sent successfully"}
    
    
# ── Admin: جيب contact form messages ──────────────────────────────────────

@router.get("/admin/contact-forms")
async def get_contact_forms(
    db:    AsyncSession = Depends(get_db),
    admin: User         = Depends(require_admin),
):
    result = await db.execute(
        select(Message)
        .where(Message.sender_id == admin.user_id)
        .where(Message.receiver_id == admin.user_id)
        .where(Message.content.like("[Contact Form]%"))
        .order_by(Message.created_at.desc())
    )
    messages = result.scalars().all()

    # mark as read
    for m in messages:
        if not m.is_read:
            m.is_read = True
    await db.commit()

    parsed = []
    for m in messages:
        # parse: "[Contact Form] From: NAME <EMAIL>\n\nMESSAGE"
        try:
            first_line = m.content.split("\n")[0]
            # "From: NAME <EMAIL>"
            from_part  = first_line.replace("[Contact Form] From: ", "")
            name       = from_part.split("<")[0].strip()
            email      = from_part.split("<")[1].replace(">", "").strip()
            message    = m.content.split("\n\n", 1)[1] if "\n\n" in m.content else ""
        except Exception:
            name    = "Unknown"
            email   = "Unknown"
            message = m.content

        parsed.append({
            "message_id": m.message_id,
            "name":       name,
            "email":      email,
            "message":    message,
            "is_read":    m.is_read,
            "created_at": str(m.created_at),
        })

    return {
        "total":    len(parsed),
        "messages": parsed,
    }
