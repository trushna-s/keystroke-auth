import smtplib
import random
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

MAIL_EMAIL    = os.getenv('MAIL_EMAIL')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')


def generate_otp():
    """Generate a 6 digit OTP"""
    return str(random.randint(100000, 999999))


def send_otp_email(to_email, username, otp):
    """Send OTP email to user"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'KeyAuth Security Alert — OTP: {otp}'
        msg['From']    = MAIL_EMAIL
        msg['To']      = to_email

        html = f"""
        <html>
        <body style="font-family: Segoe UI, sans-serif;
                     background: #0f0f0f; color: #fff;
                     padding: 40px;">
            <div style="max-width: 500px; margin: 0 auto;
                        background: #1e1e1e;
                        border-radius: 16px;
                        padding: 40px;
                        border: 1px solid #333;">

                <h1 style="color: #6c63ff; margin-bottom: 6px;">
                    🛡️ KeyAuth
                </h1>
                <h2 style="color: #fff; margin-bottom: 20px;">
                    Security Verification Required
                </h2>

                <p style="color: #aaa; margin-bottom: 24px;">
                    Hi <strong style="color:#fff">{username}</strong>,
                    unusual typing behavior was detected in your
                    session. Please verify it's you.
                </p>

                <div style="background: #2a2a2a;
                            border-radius: 12px;
                            padding: 24px;
                            text-align: center;
                            margin-bottom: 24px;
                            border: 1px solid #444;">
                    <p style="color: #888; font-size: 13px;
                               margin-bottom: 8px;">
                        Your verification code
                    </p>
                    <h1 style="color: #6c63ff;
                                font-size: 42px;
                                letter-spacing: 8px;
                                margin: 0;">
                        {otp}
                    </h1>
                    <p style="color: #666; font-size: 12px;
                               margin-top: 8px;">
                        Expires in 5 minutes
                    </p>
                </div>

                <p style="color: #666; font-size: 13px;">
                    If this wasn't you, your account may be
                    compromised. Contact support immediately.
                </p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(MAIL_EMAIL, MAIL_PASSWORD)
        server.sendmail(MAIL_EMAIL, to_email, msg.as_string())
        server.quit()

        print(f"✅ OTP sent to {to_email}")
        return True

    except Exception as e:
        print(f"❌ Email error: {e}")
        return False