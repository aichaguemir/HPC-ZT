import random
import string
from datetime import datetime, timezone, timedelta
import smtplib
from email.mime.text import MIMEText
from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_FROM, SMTP_USER, SMTP_PASS
from app.core.logging import logger
import aiosmtplib
from email.mime.text import MIMEText

OTP_EXPIRY_MINUTES = 10

def _generate_code() -> str:
    return ''.join(random.choices(string.digits, k=6))



async def send_otp(user, db) -> str:
    """Generate OTP, store on user, send via university SMTP asynchronously. Returns the code."""
    code    = _generate_code()
    expires = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    user.email_otp_code       = code
    user.email_otp_expires_at = expires
    await db.commit()

    msg = MIMEText(
        f"Your HPC Gateway verification code is: {code}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n"
        f"If you did not request this, contact your administrator."
    )
    msg['Subject'] = "HPC Gateway – Your verification code"
    msg['From']    = SMTP_FROM
    msg['To']      = user.email

    smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=True, timeout=10)
    try:
        await smtp.connect()
        if SMTP_USER and SMTP_PASS:
            await smtp.login(SMTP_USER, SMTP_PASS)
        await smtp.sendmail(SMTP_FROM, [user.email], msg.as_string())
        await smtp.quit()
        logger.info(f"OTP sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        raise

    return code
