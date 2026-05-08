
import asyncio
from app.db.session import get_db_direct
from app.db.models import User, AuditLog
from sqlalchemy import select, update
from datetime import datetime, timezone, timedelta

async def setup_r7_scenario(username: str):
    async with get_db_direct() as db:
        # Get user
        result = await db.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one()
        
        # Set failed_attempts
        user.failed_attempts = 5
        
        # Insert 5 audit log entries within last 10 minutes
        for i in range(5):
            db.add(AuditLog(
                user_id   = user.user_id,
                action    = "login_failed",
                result    = "failed",
                timestamp = datetime.now(timezone.utc) - timedelta(minutes=i),
            ))
        await db.commit()
        print(f"R7 scenario set up for {username}")

asyncio.run(setup_r7_scenario("aycha_gardenia"))
