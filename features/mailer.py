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
    return str(random.randint(100000, 999999))


def _send_email(to_email, subject, html_body):
    """Base email sender"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = MAIL_EMAIL
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(MAIL_EMAIL, MAIL_PASSWORD)
        server.sendmail(MAIL_EMAIL, to_email,
                        msg.as_string())
        server.quit()
        print(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


def send_otp_email(to_email, username, otp):
    subject = f'KeyAuth Security Alert — OTP: {otp}'
    html    = f"""
    <html>
    <body style="font-family:Segoe UI,sans-serif;
                 background:#0f0f0f;color:#fff;
                 padding:40px">
        <div style="max-width:500px;margin:0 auto;
                    background:#1e1e1e;
                    border-radius:16px;padding:40px;
                    border:1px solid #333">
            <h1 style="color:#6c63ff;margin-bottom:6px">
                🛡️ KeyAuth
            </h1>
            <h2 style="color:#fff;margin-bottom:20px">
                Security Verification Required
            </h2>
            <p style="color:#aaa;margin-bottom:24px">
                Hi <strong style="color:#fff">
                {username}</strong>,
                unusual typing behavior was detected.
                Please verify your identity.
            </p>
            <div style="background:#2a2a2a;
                        border-radius:12px;
                        padding:24px;
                        text-align:center;
                        margin-bottom:24px;
                        border:1px solid #444">
                <p style="color:#888;font-size:13px;
                           margin-bottom:8px">
                    Your verification code
                </p>
                <h1 style="color:#6c63ff;
                            font-size:42px;
                            letter-spacing:8px;
                            margin:0">
                    {otp}
                </h1>
                <p style="color:#666;font-size:12px;
                           margin-top:8px">
                    Expires in 5 minutes
                </p>
            </div>
            <p style="color:#666;font-size:13px">
                If this was not you, your account
                may be compromised.
            </p>
        </div>
    </body>
    </html>"""
    return _send_email(to_email, subject, html)


def send_user_alert_email(to_email, username,
                           alert_type, trust_score,
                           details=''):
    """Send security alert to user"""
    if alert_type == 'HIGH_RISK':
        color   = '#f44336'
        icon    = '🚨'
        title   = 'High Risk Detected'
        message = (f'Your trust score dropped to '
                   f'{trust_score}%. Unusual typing '
                   f'pattern detected on your account.')
    elif alert_type == 'SUSPICIOUS':
        color   = '#ff9800'
        icon    = '⚠️'
        title   = 'Suspicious Activity'
        message = (f'Suspicious typing pattern '
                   f'detected. Trust score: '
                   f'{trust_score}%.')
    elif alert_type == 'SESSION_TERMINATED':
        color   = '#f44336'
        icon    = '🚫'
        title   = 'Session Terminated'
        message = (f'Your session was terminated '
                   f'due to low trust score '
                   f'({trust_score}%).')
    elif alert_type == 'AUTO_BLOCKED':
        color   = '#ff1744'
        icon    = '🔒'
        title   = 'Account Blocked'
        message = (f'Your account has been '
                   f'temporarily blocked due to '
                   f'multiple suspicious sessions. '
                   f'Contact your administrator.')
    else:
        color   = '#6c63ff'
        icon    = '⚠️'
        title   = 'Security Alert'
        message = details or 'Security event detected.'

    subject = f'KeyAuth {icon} {title} — {username}'
    html    = f"""
    <html>
    <body style="font-family:Segoe UI,sans-serif;
                 background:#0f0f0f;color:#fff;
                 padding:40px">
        <div style="max-width:500px;margin:0 auto;
                    background:#1e1e1e;
                    border-radius:16px;padding:40px;
                    border:1px solid #333">
            <h1 style="color:#6c63ff;margin-bottom:6px">
                🛡️ KeyAuth
            </h1>
            <div style="background:{color}22;
                        border:1px solid {color}44;
                        border-radius:10px;
                        padding:16px;
                        margin-bottom:20px">
                <h2 style="color:{color};margin:0 0
                           8px 0;font-size:18px">
                    {icon} {title}
                </h2>
                <p style="color:#aaa;margin:0;
                          font-size:14px">
                    {message}
                </p>
            </div>
            <div style="background:#2a2a2a;
                        border-radius:10px;
                        padding:16px;
                        margin-bottom:20px">
                <p style="color:#888;font-size:12px;
                           margin-bottom:4px">
                    Account
                </p>
                <p style="color:#fff;font-size:14px;
                           margin:0;font-weight:600">
                    {username}
                </p>
                <p style="color:#888;font-size:12px;
                           margin:10px 0 4px 0">
                    Trust Score
                </p>
                <p style="color:{color};font-size:24px;
                           margin:0;font-weight:700">
                    {trust_score}%
                </p>
            </div>
            {"<p style='color:#aaa;font-size:13px'>" +
             details + "</p>" if details else ""}
            <p style="color:#666;font-size:12px;
                      margin-top:20px">
                This is an automated alert from
                KeyAuth Security System.
            </p>
        </div>
    </body>
    </html>"""
    return _send_email(to_email, subject, html)


def send_admin_alert_email(admin_email, admin_name,
                            username, alert_type,
                            trust_score, details=''):
    """Send security alert to admin"""
    if alert_type == 'HIGH_RISK':
        color   = '#f44336'
        icon    = '🚨'
        title   = 'Employee High Risk Alert'
        message = (f'Employee <strong>{username}'
                   f'</strong> has a critically low '
                   f'trust score of {trust_score}%.')
    elif alert_type == 'SUSPICIOUS':
        color   = '#ff9800'
        icon    = '⚠️'
        title   = 'Suspicious Employee Activity'
        message = (f'Suspicious typing detected for '
                   f'<strong>{username}</strong>. '
                   f'Trust score: {trust_score}%.')
    elif alert_type == 'SESSION_TERMINATED':
        color   = '#f44336'
        icon    = '🚫'
        title   = 'Employee Session Terminated'
        message = (f'Session for <strong>{username}'
                   f'</strong> was terminated. '
                   f'Trust score: {trust_score}%.')
    elif alert_type == 'AUTO_BLOCKED':
        color   = '#ff1744'
        icon    = '🔒'
        title   = 'Employee Auto-Blocked'
        message = (f'<strong>{username}</strong> '
                   f'has been automatically blocked '
                   f'after multiple suspicious '
                   f'sessions.')
    elif alert_type == 'NEW_LOCATION':
        color   = '#ff9800'
        icon    = '📍'
        title   = 'New Location Login'
        message = (f'<strong>{username}</strong> '
                   f'logged in from a new location. '
                   f'{details}')
    else:
        color   = '#6c63ff'
        icon    = '⚠️'
        title   = 'Security Event'
        message = (f'Security event for '
                   f'<strong>{username}</strong>. '
                   f'{details}')

    subject = (f'KeyAuth Admin Alert {icon} — '
               f'{username}: {title}')
    html    = f"""
    <html>
    <body style="font-family:Segoe UI,sans-serif;
                 background:#0f0f0f;color:#fff;
                 padding:40px">
        <div style="max-width:540px;margin:0 auto;
                    background:#1e1e1e;
                    border-radius:16px;padding:40px;
                    border:1px solid #333">
            <h1 style="color:#6c63ff;margin-bottom:6px">
                🛡️ KeyAuth Admin Alert
            </h1>
            <p style="color:#888;margin-bottom:24px;
                      font-size:13px">
                Hi {admin_name}, action may be required.
            </p>
            <div style="background:{color}22;
                        border:1px solid {color}44;
                        border-left:4px solid {color};
                        border-radius:10px;
                        padding:16px;
                        margin-bottom:20px">
                <h2 style="color:{color};margin:0 0
                           8px 0;font-size:18px">
                    {icon} {title}
                </h2>
                <p style="color:#aaa;margin:0;
                          font-size:14px">{message}</p>
            </div>
            <div style="background:#2a2a2a;
                        border-radius:10px;
                        padding:16px;
                        margin-bottom:20px;
                        display:grid">
                <div style="margin-bottom:10px">
                    <p style="color:#888;font-size:12px;
                               margin:0 0 4px 0">
                        Employee
                    </p>
                    <p style="color:#fff;font-size:15px;
                               font-weight:600;margin:0">
                        {username}
                    </p>
                </div>
                <div>
                    <p style="color:#888;font-size:12px;
                               margin:0 0 4px 0">
                        Trust Score at Alert
                    </p>
                    <p style="color:{color};
                               font-size:28px;
                               font-weight:700;margin:0">
                        {trust_score}%
                    </p>
                </div>
            </div>
            {"<div style='background:#2a2a2a;border-radius:10px;padding:14px;margin-bottom:16px'><p style='color:#aaa;font-size:13px;margin:0'>" + details + "</p></div>" if details else ""}
            <p style="color:#888;font-size:13px;
                      margin-top:20px">
                Login to your admin dashboard to
                review and take action:
                <a href="http://localhost:5000/admin"
                   style="color:#6c63ff">
                    Open Dashboard →
                </a>
            </p>
            <p style="color:#666;font-size:12px;
                      margin-top:16px">
                KeyAuth Automated Security System
            </p>
        </div>
    </body>
    </html>"""
    return _send_email(admin_email, subject, html)