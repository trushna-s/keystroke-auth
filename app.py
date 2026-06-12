from flask import (Flask, render_template, request,
                   redirect, url_for, session,
                   jsonify, Response)
from dotenv import load_dotenv
import sqlite3
import os
import hashlib
import numpy as np
import json
import random
import string
import requests
from datetime import datetime, timedelta
from features.extractor import (extract_features_from_raw,
                                 compare_to_profile,
                                 get_risk_level)
from features.mailer import generate_otp, send_otp_email

load_dotenv()

app            = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
DB_PATH        = os.getenv('DB_PATH')


# ── Time Format Filter ────────────────────────────────────────────
@app.template_filter('timeformat')
def timeformat(value):
    try:
        dt = datetime.strptime(
            str(value), '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%d %b %Y, %I:%M %p')
    except Exception:
        try:
            dt = datetime.strptime(
                str(value), '%Y-%m-%d %H:%M:%S.%f')
            return dt.strftime('%d %b %Y, %I:%M %p')
        except Exception:
            return value


# ── Database ──────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    with open('database/schema.sql', 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("✅ Database initialized!")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_company_code(company_name):
    prefix = ''.join(
        c for c in company_name.upper()
        if c.isalpha()
    )[:3]
    suffix = ''.join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=4
        )
    )
    return f"{prefix}-{suffix}"


def get_user_profile(user_id):
    conn    = get_db()
    profile = conn.execute(
        'SELECT * FROM user_profiles WHERE user_id=?',
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(profile) if profile else None


def get_user_email(user_id):
    conn = get_db()
    user = conn.execute(
        'SELECT email FROM users WHERE id=?',
        (user_id,)
    ).fetchone()
    conn.close()
    return user['email'] if user else None


def get_location_from_ip(ip):
    try:
        if ip in ('127.0.0.1', 'localhost', '::1'):
            return {
                'city':    'Local',
                'country': 'Development'
            }
        resp = requests.get(
            f'http://ip-api.com/json/{ip}',
            timeout=3
        ).json()
        if resp.get('status') == 'success':
            return {
                'city':    resp.get('city', 'Unknown'),
                'country': resp.get('country', 'Unknown')
            }
    except Exception:
        pass
    return {'city': 'Unknown', 'country': 'Unknown'}


def get_browser_info():
    ua      = request.headers.get('User-Agent', '')
    browser = ('Chrome'   if 'Chrome'   in ua else
               'Firefox'  if 'Firefox'  in ua else
               'Safari'   if 'Safari'   in ua else
               'Edge'     if 'Edge'     in ua else
               'Unknown')
    device  = ('Mobile'  if 'Mobile'  in ua or
                            'Android' in ua else
               'Tablet'  if 'Tablet'  in ua or
                            'iPad'    in ua else
               'Desktop')
    return browser, device


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── Routes ────────────────────────────────────────────────────────
@app.route('/')
def home():
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


# ── Company Admin Registration ────────────────────────────────────
@app.route('/register/admin', methods=['GET', 'POST'])
def register_admin():
    error        = None
    success      = False
    company_code = None

    if request.method == 'POST':
        company_name = request.form[
            'company_name'].strip()
        username     = request.form['username'].strip()
        email        = request.form['email'].strip()
        password     = hash_password(
            request.form['password'])

        code = generate_company_code(company_name)

        conn = get_db()
        while conn.execute(
            '''SELECT id FROM companies
               WHERE company_code=?''',
            (code,)
        ).fetchone():
            code = generate_company_code(company_name)

        try:
            cursor = conn.execute(
                '''INSERT INTO companies
                   (name, company_code)
                   VALUES (?, ?)''',
                (company_name, code)
            )
            company_id = cursor.lastrowid

            conn.execute('''
                INSERT INTO users
                (username, email, password,
                 is_admin, is_enrolled,
                 company_id, company_code, role)
                VALUES (?, ?, ?, 1, 1, ?, ?, 'admin')
            ''', (
                username, email, password,
                company_id, code
            ))
            conn.commit()
            success      = True
            company_code = code

        except sqlite3.IntegrityError:
            error = 'Username or email already exists!'
        finally:
            conn.close()

    return render_template(
        'register_admin.html',
        error        = error,
        success      = success,
        company_code = company_code
    )


# ── Employee Registration ─────────────────────────────────────────
@app.route('/register/user', methods=['GET', 'POST'])
def register_user():
    error = None

    if request.method == 'POST':
        company_code = request.form[
            'company_code'].strip().upper()
        username     = request.form['username'].strip()
        email        = request.form['email'].strip()
        password     = hash_password(
            request.form['password'])

        conn    = get_db()
        company = conn.execute(
            '''SELECT * FROM companies
               WHERE company_code=?''',
            (company_code,)
        ).fetchone()

        if not company:
            conn.close()
            error = ('Invalid company code. '
                     'Please check with your admin.')
            return render_template(
                'register_user.html', error=error)

        try:
            conn.execute('''
                INSERT INTO users
                (username, email, password,
                 company_id, company_code, role)
                VALUES (?, ?, ?, ?, ?, 'user')
            ''', (
                username, email, password,
                company['id'], company_code
            ))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))

        except sqlite3.IntegrityError:
            conn.close()
            error = 'Username or email already exists!'

    return render_template(
        'register_user.html', error=error)


# ── Old register redirect ─────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    return redirect(url_for('register_user'))


# ── Enrollment ────────────────────────────────────────────────────
@app.route('/enroll')
def enroll():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template(
        'enroll.html',
        username=session['username']
    )


@app.route('/save_enrollment', methods=['POST'])
def save_enrollment():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data    = request.get_json()
    samples = data.get('samples', [])

    if len(samples) < 4:
        return jsonify(
            {'error': 'Need at least 4 samples'}), 400

    all_features = []
    for sample in samples:
        feats = extract_features_from_raw(
            sample['keystrokes'],
            sample['backspace_count']
        )
        if feats:
            all_features.append(feats)

    if len(all_features) < 3:
        return jsonify(
            {'error': 'Not enough valid samples'}), 400

    dwell_means = [f['dwell_mean']  for f in all_features]
    dd_means    = [f['dd_mean']     for f in all_features]
    ud_means    = [f['ud_mean']     for f in all_features]
    wpm_vals    = [f['wpm']         for f in all_features]
    error_vals  = [f['error_rate']  for f in all_features]
    pause_vals  = [f['pause_count'] for f in all_features]

    conn = get_db()
    conn.execute(
        'DELETE FROM user_profiles WHERE user_id=?',
        (session['user_id'],)
    )
    conn.execute('''
        INSERT INTO user_profiles
        (user_id, dwell_mean, dwell_std,
         dd_mean, dd_std, ud_mean, ud_std,
         wpm_mean, wpm_std, error_rate_mean,
         pause_count_mean, sample_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        session['user_id'],
        np.mean(dwell_means), np.std(dwell_means),
        np.mean(dd_means),    np.std(dd_means),
        np.mean(ud_means),    np.std(ud_means),
        np.mean(wpm_vals),    np.std(wpm_vals),
        np.mean(error_vals),
        np.mean(pause_vals),
        len(all_features)
    ))
    conn.execute(
        'UPDATE users SET is_enrolled=1 WHERE id=?',
        (session['user_id'],)
    )
    conn.commit()
    conn.close()

    session['is_enrolled'] = 1
    session.modified       = True

    return jsonify({
        'success': True,
        'message': 'Profile created!',
        'samples': len(all_features)
    })


# ── Login ─────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(
            request.form['password'])

        ip              = request.environ.get(
            'HTTP_X_FORWARDED_FOR',
            request.remote_addr
        )
        location        = get_location_from_ip(ip)
        browser, device = get_browser_info()

        conn = get_db()
        user = conn.execute(
            '''SELECT * FROM users
               WHERE username=? AND password=?''',
            (username, password)
        ).fetchone()

        if user:
            if user['is_blocked']:
                conn.close()
                error = ('Account blocked. '
                         'Contact your administrator.')
                return render_template(
                    'login.html', error=error)

            company_name = 'KeyAuth'
            if user['company_id']:
                company = conn.execute(
                    '''SELECT name FROM companies
                       WHERE id=?''',
                    (user['company_id'],)
                ).fetchone()
                if company:
                    company_name = company['name']

            cursor = conn.execute('''
                INSERT INTO sessions
                (user_id, ip_address, city,
                 country, browser, device, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            ''', (
                user['id'], ip,
                location['city'],
                location['country'],
                browser, device
            ))
            session_id = cursor.lastrowid

            prev = conn.execute('''
                SELECT city, country FROM sessions
                WHERE user_id=? AND id!=?
                ORDER BY login_time DESC LIMIT 1
            ''', (user['id'], session_id)).fetchone()

            if prev and \
               prev['country'] != location['country'] \
               and location['country'] != 'Development':
                conn.execute('''
                    INSERT INTO alerts
                    (user_id, session_id,
                     alert_type, message)
                    VALUES (?, ?, ?, ?)
                ''', (
                    user['id'], session_id,
                    'NEW_LOCATION',
                    f"New login from "
                    f"{location['city']}, "
                    f"{location['country']} "
                    f"via {browser} on {device}"
                ))

            conn.commit()
            conn.close()

            session['user_id']     = user['id']
            session['username']    = user['username']
            session['is_enrolled'] = user['is_enrolled']
            session['is_admin']    = user['is_admin']
            session['session_id']  = session_id
            session['company']     = company_name
            session['company_id']  = user['company_id']

            if user['is_admin']:
                return redirect(
                    url_for('admin_dashboard'))
            if not user['is_enrolled']:
                return redirect(url_for('enroll'))
            return redirect(url_for('dashboard'))
        else:
            conn.close()
            error = 'Invalid username or password!'

    return render_template('login.html', error=error)


# ── User Dashboard ────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    user = conn.execute(
        'SELECT is_enrolled FROM users WHERE id=?',
        (session['user_id'],)
    ).fetchone()

    login_history = conn.execute('''
        SELECT * FROM sessions
        WHERE user_id=?
        ORDER BY login_time DESC LIMIT 5
    ''', (session['user_id'],)).fetchall()

    user_alerts = conn.execute('''
        SELECT * FROM alerts
        WHERE user_id=?
        ORDER BY timestamp DESC LIMIT 5
    ''', (session['user_id'],)).fetchall()

    latest_log = conn.execute('''
        SELECT trust_score FROM keystroke_logs
        WHERE user_id=?
        ORDER BY timestamp DESC LIMIT 1
    ''', (session['user_id'],)).fetchone()

    conn.close()

    if not user or not user['is_enrolled']:
        return redirect(url_for('enroll'))

    session['is_enrolled'] = 1
    session.modified       = True

    return render_template(
        'dashboard.html',
        username      = session['username'],
        company       = session.get('company', ''),
        login_history = login_history,
        user_alerts   = user_alerts,
        latest_score  = latest_log['trust_score']
                        if latest_log else None
    )


# ── Admin Dashboard ───────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn       = get_db()
    company_id = session.get('company_id')

    total_users = conn.execute(
        '''SELECT COUNT(*) as c FROM users
           WHERE is_admin=0 AND company_id=?''',
        (company_id,)
    ).fetchone()['c']

    enrolled_users = conn.execute(
        '''SELECT COUNT(*) as c FROM users
           WHERE is_enrolled=1 AND is_admin=0
           AND company_id=?''',
        (company_id,)
    ).fetchone()['c']

    blocked_users = conn.execute(
        '''SELECT COUNT(*) as c FROM users
           WHERE is_blocked=1 AND company_id=?''',
        (company_id,)
    ).fetchone()['c']

    active_sessions = conn.execute(
        '''SELECT COUNT(*) as c FROM sessions s
           JOIN users u ON s.user_id=u.id
           WHERE s.status='active'
           AND u.company_id=?''',
        (company_id,)
    ).fetchone()['c']

    total_logs = conn.execute(
        '''SELECT COUNT(*) as c
           FROM keystroke_logs k
           JOIN users u ON k.user_id=u.id
           WHERE u.company_id=?''',
        (company_id,)
    ).fetchone()['c']

    users = conn.execute('''
        SELECT u.id, u.username, u.email,
               u.is_enrolled, u.is_blocked,
               u.created_at,
               COUNT(DISTINCT k.id) as log_count,
               AVG(k.trust_score) as avg_trust,
               MAX(s.login_time) as last_login,
               s.city, s.country,
               s.browser, s.device
        FROM users u
        LEFT JOIN keystroke_logs k ON u.id=k.user_id
        LEFT JOIN sessions s ON u.id=s.user_id
        WHERE u.is_admin=0 AND u.company_id=?
        GROUP BY u.id
        ORDER BY u.created_at DESC
    ''', (company_id,)).fetchall()

    logs = conn.execute('''
        SELECT k.*, u.username
        FROM keystroke_logs k
        JOIN users u ON k.user_id=u.id
        WHERE u.company_id=?
        ORDER BY k.timestamp DESC LIMIT 20
    ''', (company_id,)).fetchall()

    alerts = conn.execute('''
        SELECT a.*, u.username
        FROM alerts a
        JOIN users u ON a.user_id=u.id
        WHERE u.company_id=?
        ORDER BY a.timestamp DESC LIMIT 20
    ''', (company_id,)).fetchall()

    login_locations = conn.execute('''
        SELECT s.*, u.username
        FROM sessions s
        JOIN users u ON s.user_id=u.id
        WHERE u.company_id=?
        ORDER BY s.login_time DESC LIMIT 20
    ''', (company_id,)).fetchall()

    simulations = conn.execute('''
        SELECT * FROM attack_simulations
        WHERE admin_id=?
        ORDER BY timestamp DESC LIMIT 10
    ''', (session['user_id'],)).fetchall()

    trust_stats = conn.execute('''
        SELECT AVG(k.trust_score) as avg_score,
               MIN(k.trust_score) as min_score,
               MAX(k.trust_score) as max_score
        FROM keystroke_logs k
        JOIN users u ON k.user_id=u.id
        WHERE u.company_id=?
    ''', (company_id,)).fetchone()

    company = conn.execute(
        'SELECT * FROM companies WHERE id=?',
        (company_id,)
    ).fetchone()

    conn.close()

    return render_template('admin.html',
        total_users     = total_users,
        enrolled_users  = enrolled_users,
        total_logs      = total_logs,
        blocked_users   = blocked_users,
        active_sessions = active_sessions,
        users           = users,
        logs            = logs,
        alerts          = alerts,
        login_locations = login_locations,
        simulations     = simulations,
        trust_stats     = trust_stats,
        username        = session['username'],
        company         = session.get('company', ''),
        company_code    = company['company_code']
                          if company else ''
    )


# ── Admin Block/Unblock/Delete ────────────────────────────────────
@app.route('/admin/block/<int:user_id>',
           methods=['POST'])
@admin_required
def block_user(user_id):
    conn = get_db()
    conn.execute(
        'UPDATE users SET is_blocked=1 WHERE id=?',
        (user_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/admin/unblock/<int:user_id>',
           methods=['POST'])
@admin_required
def unblock_user(user_id):
    conn = get_db()
    conn.execute(
        'UPDATE users SET is_blocked=0 WHERE id=?',
        (user_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/admin/delete/<int:user_id>',
           methods=['POST'])
@admin_required
def delete_user(user_id):
    conn = get_db()
    for table in ['keystroke_logs', 'user_profiles',
                  'otp_tokens', 'sessions', 'alerts']:
        conn.execute(
            f'DELETE FROM {table} WHERE user_id=?',
            (user_id,)
        )
    conn.execute(
        'DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ── Admin Export ──────────────────────────────────────────────────
@app.route('/admin/export')
@admin_required
def export_logs():
    import csv
    import io

    company_id = session.get('company_id')
    conn       = get_db()
    logs       = conn.execute('''
        SELECT u.username, k.dwell_time,
               k.flight_time, k.wpm,
               k.trust_score, k.timestamp
        FROM keystroke_logs k
        JOIN users u ON k.user_id=u.id
        WHERE u.company_id=?
        ORDER BY k.timestamp DESC
    ''', (company_id,)).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Username', 'Dwell Time', 'Flight Time',
        'WPM', 'Trust Score', 'Timestamp'
    ])
    for log in logs:
        writer.writerow(list(log))

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition':
            'attachment; filename=security_report.csv'
        }
    )


# ── Admin Change Credentials ──────────────────────────────────────
@app.route('/admin/change-credentials',
           methods=['POST'])
@admin_required
def change_credentials():
    data         = request.get_json()
    new_username = data.get('username', '').strip()
    new_password = data.get('password', '').strip()
    new_email    = data.get('email', '').strip()

    if not new_username or not new_email:
        return jsonify({
            'success': False,
            'message': 'Username and email required'
        })

    conn = get_db()
    try:
        if new_password:
            conn.execute('''
                UPDATE users SET
                    username=?, email=?, password=?
                WHERE id=?
            ''', (
                new_username, new_email,
                hash_password(new_password),
                session['user_id']
            ))
        else:
            conn.execute('''
                UPDATE users SET username=?, email=?
                WHERE id=?
            ''', (
                new_username, new_email,
                session['user_id']
            ))
        conn.commit()
        conn.close()
        session['username'] = new_username
        session.modified    = True
        return jsonify({
            'success': True,
            'message': 'Credentials updated!'
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            'success': False,
            'message': 'Username or email taken'
        })


# ── Attack Simulation ─────────────────────────────────────────────
@app.route('/admin/simulate', methods=['POST'])
@admin_required
def simulate_attack():
    data        = request.get_json()
    attack_type = data.get('attack_type', '')
    results     = run_simulation(attack_type)

    conn = get_db()
    conn.execute('''
        INSERT INTO attack_simulations
        (admin_id, attack_type,
         initial_score, final_score,
         detected, response, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        session['user_id'],
        attack_type,
        results['initial_score'],
        results['final_score'],
        1 if results['detected'] else 0,
        results['response'],
        json.dumps(results['details'])
    ))
    conn.commit()
    conn.close()

    return jsonify(results)


def run_simulation(attack_type):
    sims = {
        'password_sharing': {
            'name':        'Password Sharing Attack',
            'description': 'Someone using stolen credentials',
            'initial':     random.uniform(75, 95),
            'final':       random.uniform(5, 25),
            'time':        round(random.uniform(2, 8), 1),
            'response':    'Session Terminated + Alert',
            'details': {
                'dwell_deviation':
                    f'+{random.randint(40,80)}%',
                'flight_deviation':
                    f'+{random.randint(30,70)}%',
                'wpm_deviation':
                    f'-{random.randint(20,50)}%',
                'anomaly_features': [
                    'Key Hold Time',
                    'Time Between Keys',
                    'Typing Speed'
                ]
            }
        },
        'session_hijacking': {
            'name':        'Session Hijacking Attack',
            'description': 'Mid-session account takeover',
            'initial':     random.uniform(70, 90),
            'final':       random.uniform(8, 30),
            'time':        round(random.uniform(1, 5), 1),
            'response':    'OTP Triggered + Admin Alerted',
            'details': {
                'dwell_deviation':
                    f'+{random.randint(50,90)}%',
                'flight_deviation':
                    f'+{random.randint(40,80)}%',
                'wpm_deviation':
                    f'-{random.randint(30,60)}%',
                'anomaly_features': [
                    'Key Hold Time',
                    'Pause Pattern',
                    'Error Rate'
                ]
            }
        },
        'unknown_location': {
            'name':        'Unknown Location Login',
            'description': 'Login from unrecognized location',
            'initial':     random.uniform(60, 80),
            'final':       random.uniform(40, 65),
            'time':        round(random.uniform(0.5, 2), 1),
            'response':    'Location Alert + OTP Required',
            'details': {
                'location_match':    'Failed',
                'new_location':      'Unknown City',
                'previous_location': 'Known Location',
                'anomaly_features': [
                    'Login Location',
                    'Login Time',
                    'Device Fingerprint'
                ]
            }
        },
        'bot_typing': {
            'name':        'Bot Typing Attack',
            'description': 'Automated bot keystroke injection',
            'initial':     random.uniform(50, 70),
            'final':       random.uniform(2, 15),
            'time':        round(random.uniform(1, 4), 1),
            'response':    'Session Blocked + IP Flagged',
            'details': {
                'dwell_deviation':
                    f'-{random.randint(60,90)}%',
                'flight_deviation':
                    f'-{random.randint(50,80)}%',
                'regularity_score': '99.8% (Too Perfect)',
                'anomaly_features': [
                    'Inhuman Consistency',
                    'Zero Pause Pattern',
                    'No Error Rate'
                ]
            }
        }
    }

    sim = sims.get(attack_type, {
        'name': 'Unknown', 'description': '',
        'initial': 75, 'final': 50, 'time': 0,
        'response': 'No response', 'details': {}
    })

    return {
        'attack_type':    attack_type,
        'name':           sim['name'],
        'description':    sim['description'],
        'initial_score':  round(sim['initial'], 1),
        'final_score':    round(sim['final'], 1),
        'score_drop':     round(
            sim['initial'] - sim['final'], 1),
        'detected':       True,
        'detection_time': sim['time'],
        'response':       sim['response'],
        'details':        sim['details'],
        'timestamp':      datetime.now().strftime(
            '%Y-%m-%d %H:%M:%S')
    }


# ── Analyze Keystrokes ────────────────────────────────────────────
@app.route('/analyze_keystrokes', methods=['POST'])
def analyze_keystrokes():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data            = request.get_json()
    keystrokes      = data.get('keystrokes', [])
    backspace_count = data.get('backspace_count', 0)

    features = extract_features_from_raw(
        keystrokes, backspace_count)

    if features is None:
        return jsonify({
            'trust_score': 75.0,
            'status':      'allow',
            'risk_level':  'Low',
            'explanation': {},
            'message':     'Not enough data yet'
        })

    profile = get_user_profile(session['user_id'])

    if not profile:
        return jsonify({
            'trust_score': 75.0,
            'status':      'allow',
            'risk_level':  'Low',
            'explanation': {},
            'message':     'No profile found'
        })

    trust_score, explanation = compare_to_profile(
        features, profile)
    status, risk_level = get_risk_level(trust_score)

    if status in ('otp', 'terminate'):
        otp    = generate_otp()
        expiry = datetime.now() + timedelta(minutes=5)
        conn   = get_db()
        conn.execute(
            'DELETE FROM otp_tokens WHERE user_id=?',
            (session['user_id'],)
        )
        conn.execute('''
            INSERT INTO otp_tokens
            (user_id, otp_code, expires_at)
            VALUES (?, ?, ?)
        ''', (session['user_id'], otp, expiry))
        conn.commit()
        conn.close()

    conn = get_db()
    conn.execute('''
        INSERT INTO keystroke_logs
        (user_id, session_id, dwell_time,
         flight_time, wpm, pause_count,
         error_rate, trust_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        session['user_id'],
        session.get('session_id', 0),
        features['dwell_mean'],
        features['dd_mean'],
        features['wpm'],
        features['pause_count'],
        features['error_rate'],
        trust_score
    ))
    conn.commit()
    conn.close()

    print(f"User: {session['username']} | "
          f"Trust: {trust_score}% | "
          f"Status: {status}")

    return jsonify({
        'trust_score': trust_score,
        'status':      status,
        'risk_level':  risk_level,
        'explanation': explanation,
        'message':     f'Trust score: {trust_score}%'
    })


# ── Log Incident ──────────────────────────────────────────────────
@app.route('/log_incident', methods=['POST'])
def log_incident():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data   = request.get_json()
    reason = data.get('reason', 'Unknown')
    score  = data.get('score', 0)

    conn = get_db()
    conn.execute('''
        INSERT INTO alerts
        (user_id, session_id, alert_type, message)
        VALUES (?, ?, ?, ?)
    ''', (
        session['user_id'],
        session.get('session_id', 0),
        'SESSION_TERMINATED',
        f'Session terminated. {reason}. '
        f'Score: {score}%'
    ))
    conn.execute('''
        UPDATE sessions
        SET status='terminated',
            logout_time=CURRENT_TIMESTAMP
        WHERE id=?
    ''', (session.get('session_id', 0),))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


# ── Send OTP ──────────────────────────────────────────────────────
@app.route('/send_otp', methods=['POST'])
def send_otp():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    conn  = get_db()
    token = conn.execute('''
        SELECT * FROM otp_tokens
        WHERE user_id=? AND is_used=0
        ORDER BY created_at DESC LIMIT 1
    ''', (session['user_id'],)).fetchone()
    conn.close()

    if not token:
        otp    = generate_otp()
        expiry = datetime.now() + timedelta(minutes=5)
        conn   = get_db()
        conn.execute(
            'DELETE FROM otp_tokens WHERE user_id=?',
            (session['user_id'],)
        )
        conn.execute('''
            INSERT INTO otp_tokens
            (user_id, otp_code, expires_at)
            VALUES (?, ?, ?)
        ''', (session['user_id'], otp, expiry))
        conn.commit()
        conn.close()
    else:
        otp = token['otp_code']

    email   = get_user_email(session['user_id'])
    success = send_otp_email(
        email, session['username'], otp)

    return jsonify({
        'success': success,
        'message': 'OTP sent!' if success
                   else 'Failed to send OTP'
    })


# ── Verify OTP ────────────────────────────────────────────────────
@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data      = request.get_json()
    otp_input = data.get('otp', '').strip()

    conn  = get_db()
    token = conn.execute('''
        SELECT * FROM otp_tokens
        WHERE user_id=? AND is_used=0
        ORDER BY created_at DESC LIMIT 1
    ''', (session['user_id'],)).fetchone()

    if not token:
        conn.close()
        return jsonify({
            'success': False,
            'message': 'No OTP found.'
        })

    try:
        expires_at = datetime.strptime(
            token['expires_at'],
            '%Y-%m-%d %H:%M:%S.%f')
    except ValueError:
        expires_at = datetime.strptime(
            token['expires_at'],
            '%Y-%m-%d %H:%M:%S')

    if datetime.now() > expires_at:
        conn.close()
        return jsonify({
            'success': False,
            'message': 'OTP expired.'
        })

    if otp_input == token['otp_code']:
        conn.execute(
            'UPDATE otp_tokens SET is_used=1 WHERE id=?',
            (token['id'],)
        )
        conn.commit()
        conn.close()
        return jsonify({
            'success': True,
            'message': 'Verified!'
        })
    else:
        conn.close()
        return jsonify({
            'success': False,
            'message': 'Incorrect OTP.'
        })


# ── Update Profile ────────────────────────────────────────────────
@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    data            = request.get_json()
    keystrokes      = data.get('keystrokes', [])
    backspace_count = data.get('backspace_count', 0)

    features = extract_features_from_raw(
        keystrokes, backspace_count)
    if not features:
        return jsonify({'success': False})

    profile = get_user_profile(session['user_id'])
    if not profile:
        return jsonify({'success': False})

    lr = 0.1
    conn = get_db()
    conn.execute('''
        UPDATE user_profiles SET
            dwell_mean      = dwell_mean * ? + ? * ?,
            dd_mean         = dd_mean    * ? + ? * ?,
            ud_mean         = ud_mean    * ? + ? * ?,
            wpm_mean        = wpm_mean   * ? + ? * ?,
            error_rate_mean = error_rate_mean * ? + ? * ?,
            sample_count    = sample_count + 1,
            updated_at      = CURRENT_TIMESTAMP
        WHERE user_id=?
    ''', (
        1-lr, lr, features['dwell_mean'],
        1-lr, lr, features['dd_mean'],
        1-lr, lr, features['ud_mean'],
        1-lr, lr, features['wpm'],
        1-lr, lr, features['error_rate'],
        session['user_id']
    ))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# ── Employee Stats for Admin ──────────────────────────────────────
@app.route('/admin/employee/<int:user_id>')
@admin_required
def employee_stats(user_id):
    conn       = get_db()
    company_id = session.get('company_id')

    # Verify employee belongs to admin's company
    user = conn.execute('''
        SELECT * FROM users
        WHERE id=? AND company_id=?
        AND is_admin=0
    ''', (user_id, company_id)).fetchone()

    if not user:
        conn.close()
        return redirect(url_for('admin_dashboard'))

    # Recent keystroke logs
    logs = conn.execute('''
        SELECT * FROM keystroke_logs
        WHERE user_id=?
        ORDER BY timestamp DESC LIMIT 50
    ''', (user_id,)).fetchall()

    # Recent sessions
    sessions_list = conn.execute('''
        SELECT * FROM sessions
        WHERE user_id=?
        ORDER BY login_time DESC LIMIT 10
    ''', (user_id,)).fetchall()

    # Alerts
    alerts = conn.execute('''
        SELECT * FROM alerts
        WHERE user_id=?
        ORDER BY timestamp DESC LIMIT 10
    ''', (user_id,)).fetchall()

    # Profile
    profile = conn.execute('''
        SELECT * FROM user_profiles
        WHERE user_id=?
    ''', (user_id,)).fetchone()

    # Stats
    stats = conn.execute('''
        SELECT
            AVG(trust_score)  as avg_trust,
            MIN(trust_score)  as min_trust,
            MAX(trust_score)  as max_trust,
            AVG(wpm)          as avg_wpm,
            AVG(dwell_time)   as avg_dwell,
            AVG(flight_time)  as avg_flight,
            AVG(error_rate)   as avg_error,
            COUNT(*)          as total_windows
        FROM keystroke_logs
        WHERE user_id=?
    ''', (user_id,)).fetchone()

    conn.close()

    return render_template(
        'employee_stats.html',
        employee      = dict(user),
        logs          = logs,
        sessions_list = sessions_list,
        alerts        = alerts,
        profile       = dict(profile)
                        if profile else None,
        stats         = dict(stats)
                        if stats else None,
        username      = session['username'],
        company       = session.get('company', '')
    )

# ── Logout ────────────────────────────────────────────────────────
@app.route('/logout')
def logout():
    if session.get('session_id'):
        conn = get_db()
        conn.execute('''
            UPDATE sessions
            SET status='ended',
                logout_time=CURRENT_TIMESTAMP
            WHERE id=?
        ''', (session['session_id'],))
        conn.commit()
        conn.close()
    session.clear()
    return redirect(url_for('login'))


# ── Run ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(debug=True)