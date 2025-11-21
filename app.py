from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import oauth_authorized
import pytz
import requests
import threading
import time
# 若需DCbot回答問題
# import discord
# from discord.ext import commands

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_secret_key")

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

tz = pytz.timezone('Asia/Taipei')


os.makedirs(app.instance_path, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, 'users.db')


def get_connection():
    return sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)


def ensure_alert_schema():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'")
    if not c.fetchone():
        conn.close()
        return

    c.execute('PRAGMA table_info(alerts)')
    columns = {row[1] for row in c.fetchall()}

    if 'start_time' not in columns:
        c.execute('ALTER TABLE alerts ADD COLUMN start_time TEXT')
    if 'end_time' not in columns:
        c.execute('ALTER TABLE alerts ADD COLUMN end_time TEXT')
    if 'is_notified' not in columns:
        c.execute("ALTER TABLE alerts ADD COLUMN is_notified INTEGER DEFAULT 0")
    if 'notified_at' not in columns:
        c.execute('ALTER TABLE alerts ADD COLUMN notified_at TEXT')
    if 'notify_count' not in columns:
        c.execute('ALTER TABLE alerts ADD COLUMN notify_count INTEGER DEFAULT 0')

    conn.commit()
    conn.close()


ensure_alert_schema()


def ensure_pool_settings_schema():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS pool_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_id TEXT NOT NULL,
            setting_type TEXT NOT NULL,
            value REAL NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(pool_id, setting_type)
        )
        '''
    )
    conn.commit()
    conn.close()


ensure_pool_settings_schema()

LINE_NOTIFY_TOKEN = os.environ.get("LINE_NOTIFY_TOKEN")
_discord_hooks = os.environ.get("DISCORD_WEBHOOKS") or os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_WEBHOOKS = [hook.strip() for hook in (_discord_hooks.split(',') if _discord_hooks else []) if hook.strip()]
DISCORD_BOT_NAME = os.environ.get("DISCORD_BOT_NAME", "Shrimp Monitor")
DISCORD_AVATAR_URL = os.environ.get("DISCORD_AVATAR_URL")

EVENT_TYPE_MAP = {
    'temp': '水質異常',
    'psu': '水質異常',
    'ph': '水質異常',
    'do': '水質異常',
    'orp': '水質異常',
    'behavior': '行為異常',
    'food': '飼料異常'
}

SENSOR_NAME_MAP = {
    'temp': '溫度',
    'psu': '鹽度',
    'ph': 'pH ',
    'do': '溶氧',
    'orp': 'ORP ',
    'behavior': '行為',
    'food': '餵食'
}

VALID_POOL_IDS = {'1', '2', '3', '4'}
VALID_SETTING_TYPES = {'interval', 'feed'}
AUTO_ALERT_INTERVAL = int(os.environ.get('AUTO_ALERT_INTERVAL', '1'))
_monitor_thread_started = False


def send_alert(message: str):
    if not message:
        return False, '訊息內容為空'

    errors = []

    if DISCORD_WEBHOOKS:
        payload = {"content": message}
        if DISCORD_BOT_NAME:
            payload["username"] = DISCORD_BOT_NAME
        if DISCORD_AVATAR_URL:
            payload["avatar_url"] = DISCORD_AVATAR_URL

        for hook in DISCORD_WEBHOOKS:
            try:
                resp = requests.post(hook, json=payload, timeout=10)
                resp.raise_for_status()
                return True, 'Discord 通知已送出'
            except requests.RequestException as exc:
                err = f'Discord 通知失敗: {exc}'
                app.logger.error(err)
                errors.append(err)

    token = LINE_NOTIFY_TOKEN
    if token:
        try:
            response = requests.post(
                "https://notify-api.line.me/api/notify",
                headers={"Authorization": f"Bearer {token}"},
                data={'message': message},
                timeout=10
            )
            response.raise_for_status()
            return True, 'LINE Notify 已送出'
        except requests.RequestException as exc:
            err = f'LINE Notify 傳送失敗: {exc}'
            app.logger.error(err)
            errors.append(str(exc))

    if errors:
        return False, '；'.join(errors)

    app.logger.warning('未設定任何通知方式，無法傳送訊息')
    return False, '未設定任何通知方式'


def build_alert_message(pool_id, sensor_type, value, description, event_time, notify_count):
    event_name = EVENT_TYPE_MAP.get(sensor_type, sensor_type)
    sensor_name = SENSOR_NAME_MAP.get(sensor_type, sensor_type)

    if sensor_type in {"behavior", "food"}:
        detail = description
    else:
        detail = f"異常項目：{sensor_name}\n異常數值：{value}\n正常範圍：{description}\n"

    return (
        f"{event_name}通知\n"
        f"池號：{pool_id} 號\n"
        f"{detail}"
        f"發生時間：{event_time}\n"
        f"本次為第{notify_count}次通知，請盡快處理！"
    )


def upsert_alert_record(cursor, pool_id, sensor_type, description, value, timestamp):
    cursor.execute(
        "SELECT id, is_notified, notify_count FROM alerts WHERE pool_id = ? AND sensor_type = ? AND end_time IS NULL",
        (pool_id, sensor_type)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE alerts SET description = ?, value = ?, timestamp = ? WHERE id = ?",
            (description, value, timestamp, row[0])
        )
        already_notified = bool(row[1])
        notify_count = row[2] or 0
        return row[0], not already_notified, notify_count

    cursor.execute(
        '''
        INSERT INTO alerts (pool_id, sensor_type, description, value, timestamp, status, start_time, end_time, is_notified, notify_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, 0)
        ''',
        (pool_id, sensor_type, description, value, timestamp, '未處理', timestamp)
    )
    return cursor.lastrowid, True, 0


def resolve_alert_record(cursor, pool_id, sensor_type, timestamp):
    cursor.execute(
        "SELECT id FROM alerts WHERE pool_id = ? AND sensor_type = ? AND end_time IS NULL",
        (pool_id, sensor_type)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE alerts SET end_time = ?, timestamp = ? WHERE id = ?",
            (timestamp, timestamp, row[0])
        )

GOOGLE_CLIENT_ID = "510195146091-pi9c4kbmeaompb0nopu5p06r63bjbpte.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"

google_bp = make_google_blueprint(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email"
    ],
    redirect_to="dashboard",
    authorized_url=None
)
app.register_blueprint(google_bp, url_prefix="/login")

@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    resp = blueprint.session.get("/oauth2/v2/userinfo")
    if not resp.ok:
        flash("無法獲取使用者資訊")
        return False
    info = resp.json()
    session['username'] = info['email']
    session['user_id'] = f"google_{info['id']}"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    login_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO login_logs (user_id, login_time) VALUES (?, ?)', (session['user_id'], login_time))
    session['log_id'] = c.lastrowid
    conn.commit()
    conn.close()

    flash("登錄成功")
    return False

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, password FROM users WHERE username = ?', (username,))
    result = c.fetchone()

    if result and check_password_hash(result[1], password):
        user_id = result[0]
        session['username'] = username
        session['user_id'] = user_id

        login_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        c.execute('INSERT INTO login_logs (user_id, login_time) VALUES (?, ?)', (user_id, login_time))
        session['log_id'] = c.lastrowid

        conn.commit()
        conn.close()
        return redirect(url_for('dashboard'))
    else:
        conn.close()
        flash('帳號或密碼錯誤')
        return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm']

        if password != confirm:
            flash("密碼與確認密碼不一致")
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            flash('註冊成功，請登入')
            return redirect(url_for('home'))
        except sqlite3.IntegrityError:
            flash('此帳號已存在，請使用其他帳號')
            return redirect(url_for('register'))
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('home'))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    history_data = {
        "temp": {"pool1": [], "pool2": [], "pool3": [], "pool4": []},
        "psu": {"pool1": [], "pool2": [], "pool3": [], "pool4": []},
        "ph": {"pool1": [], "pool2": [], "pool3": [], "pool4": []},
        "do": {"pool1": [], "pool2": [], "pool3": [], "pool4": []},
        "orp": {"pool1": [], "pool2": [], "pool3": [], "pool4": []}
    }

    for pool_index in range(1, 5):
        pool_key = f"pool{pool_index}"
        c.execute(
            """
            SELECT pool_id, timestamp, temp, psu, ph, do, orp
            FROM sensor_data
            WHERE pool_id = ? OR pool_id = ?
            ORDER BY timestamp ASC
            """,
            (pool_index, pool_key),
        )
        rows = c.fetchall()
        for row in rows:
            ts = row["timestamp"]
            pool_id = row["pool_id"]
            if not str(pool_id).startswith("pool"):
                pool_id = f"pool{pool_id}"
            if pool_id not in history_data["temp"]:
                continue
            history_data["temp"][pool_id].append({"timestamp": ts, "value": row["temp"]})
            history_data["psu"][pool_id].append({"timestamp": ts, "value": row["psu"]})
            history_data["ph"][pool_id].append({"timestamp": ts, "value": row["ph"]})
            history_data["do"][pool_id].append({"timestamp": ts, "value": row["do"]})
            history_data["orp"][pool_id].append({"timestamp": ts, "value": row["orp"]})

    conn.close()
    return render_template("dashboard.html", pool_id=1, history_data=history_data)

@app.route('/oddset', methods=['GET', 'POST'])
def oddset():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if request.method == 'POST':
        data = request.get_json()
        try:
            now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            c.execute('''
                INSERT INTO oddset (
                    temp_min, temp_max, psu_min, psu_max,
                    ph_min, ph_max, do_min, do_max,
                    orp_min, orp_max, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['temp_min'], data['temp_max'],
                data['psu_min'], data['psu_max'],
                data['ph_min'], data['ph_max'],
                data['do_min'], data['do_max'],
                data['orp_min'], data['orp_max'],
                now
            ))
            conn.commit()

            return jsonify({'success': True, 'created_at': now})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        finally:
            conn.close()

    else:
        c.execute('''
            SELECT temp_min, temp_max, psu_min, psu_max,
                   ph_min, ph_max, do_min, do_max,
                   orp_min, orp_max, created_at
            FROM oddset
            ORDER BY id DESC LIMIT 1
        ''')
        row = c.fetchone()
        conn.close()

        if row:
            oddset_data = {
                'temp_min': row[0], 'temp_max': row[1],
                'psu_min': row[2], 'psu_max': row[3],
                'ph_min': row[4], 'ph_max': row[5],
                'do_min': row[6], 'do_max': row[7],
                'orp_min': row[8], 'orp_max': row[9]
            }
            last_updated = row[10]
        else:
            oddset_data = {
                'temp_min': 18, 'temp_max': 25,
                'psu_min': 60, 'psu_max': 80,
                'ph_min': 5.5, 'ph_max': 8.5,
                'do_min': 5, 'do_max': 1000,
                'orp_min': 180, 'orp_max': 300
            }
            last_updated = "尚無更新紀錄"

        return render_template('oddset.html', oddset=oddset_data, last_updated=last_updated)

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/monitor')
def monitor():
    return render_template('monitor.html')

def process_latest_data(pool_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    default_oddset = (18, 25, 60, 80, 5.5, 8.5, 5, 1000, 180, 300)
    c.execute('SELECT temp_min, temp_max, psu_min, psu_max, ph_min, ph_max, do_min, do_max, orp_min, orp_max FROM oddset ORDER BY id DESC LIMIT 1')
    oddset = c.fetchone()
    if oddset is None or any(v is None for v in oddset):
        oddset = default_oddset
    else:
        oddset = tuple(val if val is not None else default for val, default in zip(oddset, default_oddset))

    c.execute('SELECT temp, psu, ph, do, orp, timestamp FROM sensor_data WHERE pool_id = ? ORDER BY timestamp DESC LIMIT 1', (pool_id,))
    data = c.fetchone()
    if not data:
        conn.close()
        return None, 'No data found', 404

    temp, psu, ph, do, orp, timestamp = data
    temp_min, temp_max, psu_min, psu_max, ph_min, ph_max, do_min, do_max, orp_min, orp_max = oddset

    abnormal = {
        'temp': temp < temp_min or temp > temp_max,
        'psu': psu < psu_min or psu > psu_max,
        'ph': ph < ph_min or ph > ph_max,
        'do': do < do_min or do > do_max,
        'orp': orp < orp_min or orp > orp_max
    }
    range_map = {
        'temp': f"{temp_min}~{temp_max}",
        'psu': f"{psu_min}~{psu_max}",
        'ph': f"{ph_min}~{ph_max}",
        'do': f"{do_min}~{do_max}",
        'orp': f"{orp_min}~{orp_max}"
    }
    value_map = {'temp': temp, 'psu': psu, 'ph': ph, 'do': do, 'orp': orp}

    for sensor, is_abn in abnormal.items():
        if is_abn:
            desc = range_map[sensor]
            alert_id, should_notify, notify_count = upsert_alert_record(
                c, pool_id, sensor, desc, value_map[sensor], timestamp
            )
            if should_notify:
                new_count = (notify_count or 0) + 1
                message = build_alert_message(pool_id, sensor, value_map[sensor], desc, timestamp, new_count)
                success, detail = send_alert(message)
                notified_at = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S") if success else None
                if success:
                    c.execute(
                        "UPDATE alerts SET is_notified = 1, notified_at = ?, notify_count = ? WHERE id = ?",
                        (notified_at, new_count, alert_id)
                    )
                else:
                    app.logger.warning('通知傳送失敗：%s', detail)
        else:
            resolve_alert_record(c, pool_id, sensor, timestamp)

    conn.commit()
    conn.close()

    return {
        'temp': temp, 'psu': psu, 'ph': ph, 'do': do, 'orp': orp,
        'timestamp': timestamp,
        'abnormal': abnormal,
        'oddset': {
            'temp_min': temp_min, 'temp_max': temp_max,
            'psu_min': psu_min, 'psu_max': psu_max,
            'ph_min': ph_min, 'ph_max': ph_max,
            'do_min': do_min, 'do_max': do_max,
            'orp_min': orp_min, 'orp_max': orp_max
        }
    }, None, 200


def alert_monitor_loop():
    interval = max(AUTO_ALERT_INTERVAL, 1)
    app.logger.info('Auto alert monitor started (interval %s seconds)', interval)
    while True:
        for pool in sorted(VALID_POOL_IDS):
            try:
                process_latest_data(pool)
            except Exception as exc:
                app.logger.exception('Auto alert monitor exception for pool %s: %s', pool, exc)
        time.sleep(interval)


def ensure_monitor_thread():
    global _monitor_thread_started
    if _monitor_thread_started:
        return
    thread = threading.Thread(target=alert_monitor_loop, name='alert-monitor', daemon=True)
    thread.start()
    _monitor_thread_started = True


@app.route('/api/latest-data/<pool_id>')
def latest_data(pool_id):
    result, error_msg, status_code = process_latest_data(pool_id)
    if error_msg:
        return jsonify({'error': error_msg}), status_code
    return jsonify(result)


@app.route('/api/action-status')
def action_status():
    pool_id = request.args.get('pool_id', '').strip()
    if pool_id not in VALID_POOL_IDS:
        return jsonify({'error': '池號不正確'}), 400

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = c.execute(
        '''
        SELECT sensor_type, start_time, description
        FROM alerts
        WHERE sensor_type IN ('behavior', 'food')
          AND end_time IS NULL
          AND pool_id = ?
        ORDER BY start_time DESC
        ''',
        (pool_id,)
    ).fetchall()
    conn.close()

    default_status = {'abnormal': False, 'timestamp': None, 'description': None}
    result = {'behavior': default_status.copy(), 'food': default_status.copy()}

    for row in rows:
        key = row['sensor_type']
        if key in result:
            result[key] = {
                'abnormal': True,
                'timestamp': row['start_time'],
                'description': row['description'],
            }

    return jsonify(result)

@app.route('/api/history/latest/<pool_id>')
def api_history_latest(pool_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('''
        SELECT timestamp, temp, psu, ph, do, orp
        FROM sensor_data
        WHERE pool_id = ?
        ORDER BY timestamp DESC
        LIMIT 20
    ''', (pool_id,))
    rows = c.fetchall()
    conn.close()

    data = [dict(row) for row in rows]
    return jsonify(data)

@app.route('/api/history', methods=['POST'])
def api_history():
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('''
        SELECT pool_id, timestamp, temp, psu, ph, do, orp
        FROM sensor_data
        WHERE timestamp BETWEEN ? AND ?
        ORDER BY timestamp ASC
    ''', (start_date, end_date))

    rows = c.fetchall()
    conn.close()

    if not rows:
        return jsonify({'error': '查無資料'}), 404

    result = {
        "temp": {}, "psu": {}, "ph": {}, "do": {}, "orp": {}
    }
    for row in rows:
        pool = row['pool_id']
        if not pool.startswith("pool"):
            pool = f"pool{pool}"
        for key in result.keys():
            if pool not in result[key]:
                result[key][pool] = []
            result[key][pool].append({
                "timestamp": row['timestamp'],
                "value": row[key]
            })

    return jsonify(result)


@app.route('/api/settings', methods=['GET', 'POST'])
def pool_settings():
    if 'username' not in session:
        return jsonify({'success': False, 'message': '未登入'}), 401

    if request.method == 'GET':
        pool_id = request.args.get('pool_id', '').strip()
        setting_type = request.args.get('setting_type', '').strip()

        if pool_id not in VALID_POOL_IDS or setting_type not in VALID_SETTING_TYPES:
            return jsonify({'success': False, 'message': '參數不正確'}), 400

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        row = c.execute(
            '''
            SELECT value, updated_at
            FROM pool_settings
            WHERE pool_id = ? AND setting_type = ?
            ''',
            (pool_id, setting_type)
        ).fetchone()
        conn.close()

        if not row:
            return jsonify({'success': True, 'value': None, 'updated_at': None})

        return jsonify({
            'success': True,
            'value': row['value'],
            'updated_at': row['updated_at']
        })

    data = request.get_json(silent=True) or {}
    pool_id = data.get('pool_id')
    setting_type = data.get('setting_type')
    value = data.get('value')

    if pool_id is None or str(pool_id).strip() not in VALID_POOL_IDS:
        return jsonify({'success': False, 'message': '池號不正確'}), 400
    pool_id = str(pool_id).strip()

    if setting_type not in VALID_SETTING_TYPES:
        return jsonify({'success': False, 'message': '設定項目不正確'}), 400

    try:
        value = float(value)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '請輸入正確的數值'}), 400

    if value <= 0:
        return jsonify({'success': False, 'message': '數值需大於 0'}), 400

    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            '''
            INSERT INTO pool_settings (pool_id, setting_type, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pool_id, setting_type) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            ''',
            (pool_id, setting_type, value, now)
        )
        conn.commit()
    except sqlite3.Error as exc:
        return jsonify({'success': False, 'message': f'資料庫錯誤: {exc}'}), 500
    finally:
        if conn:
            conn.close()

    return jsonify({
        'success': True,
        'pool_id': pool_id,
        'setting_type': setting_type,
        'value': value,
        'updated_at': now
    })

@app.route('/api/alerts')
def get_alerts():
    pool_id = request.args.get('pool', 'all')
    event_type = request.args.get('event', 'allodd')

    query = """
        SELECT id, pool_id, sensor_type, description, value, timestamp, status,
               start_time, end_time, is_notified, notified_at, notify_count
        FROM alerts
        WHERE 1=1
    """
    params = []
    if pool_id != 'all':
        # 你的池號是字串 '1', '2'，資料庫 pool_id 可能是字串也可能是類似 pool_1，請確認一致
        # 假設資料庫 pool_id 就是 '1', '2' 這類字串
        query += " AND pool_id = ?"
        params.append(pool_id)
    if event_type != 'allodd':
        event_map = {
            'waterodd': ['temp','psu','ph','do','orp'],
            'actionodd': ['behavior'],
            'foododd': ['food']
        }
        allowed = event_map.get(event_type, [])
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            query += f" AND sensor_type IN ({placeholders})"
            params.extend(allowed)

    query += " ORDER BY timestamp DESC"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = c.execute(query, params).fetchall()
    conn.close()

    results = []
    for row in rows:
        event_display = EVENT_TYPE_MAP.get(row['sensor_type'], row['sensor_type'])
        sensor_display = SENSOR_NAME_MAP.get(row['sensor_type'], row['sensor_type'])
        description = f"{sensor_display}： {row['value']} (正常範圍：{row['description']})"
        results.append({
            'id': row['id'],
            'pool': str(row['pool_id']),
            'type': event_display,
            'description': description,
            'time': row['start_time'] or row['timestamp'],
            'end_time': row['end_time'],
            'status': row['status'] if row['status'] else '未處理',
            'notified': bool(row['is_notified']),
            'notified_at': row['notified_at'],
            'active': row['end_time'] is None,
            'notify_count': row['notify_count'] or 0
        })

    return jsonify(results)


@app.route('/api/alerts/<int:alert_id>/status', methods=['POST'])
def update_alert_status(alert_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT status FROM alerts WHERE id = ?', (alert_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '找不到異常事件'}), 404

    if row[0] == '已處理':
        conn.close()
        return jsonify({'success': True, 'status': '已處理'})

    c.execute('UPDATE alerts SET status = ? WHERE id = ?', ('已處理', alert_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'status': '已處理'})


@app.route('/api/alerts/<int:alert_id>/notify', methods=['POST'])
def notify_alert(alert_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    row = c.execute('SELECT * FROM alerts WHERE id = ?', (alert_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'success': False, 'message': '找不到異常事件'}), 404

    event_time = row['start_time'] or row['timestamp']
    current_count = row['notify_count'] or 0
    new_count = current_count + 1
    message = build_alert_message(
        row['pool_id'],
        row['sensor_type'],
        row['value'],
        row['description'],
        event_time,
        new_count
    )
    success, detail = send_alert(message)
    if success:
        notified_at = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            'UPDATE alerts SET is_notified = 1, notified_at = ?, notify_count = ? WHERE id = ?',
            (notified_at, new_count, alert_id)
        )
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'notified': True, 'notified_at': notified_at, 'notify_count': new_count})

    conn.close()
    return jsonify({'success': False, 'message': detail}), 500

@app.route('/logout')
def logout():
    if 'log_id' in session:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        logout_time = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        c.execute('UPDATE login_logs SET logout_time = ? WHERE id = ?', (logout_time, session['log_id']))
        conn.commit()
        conn.close()
    session.clear()
    return redirect(url_for('home'))

@app.route('/oddset-check')
def oddset_check():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT temp_min, temp_max, psu_min, psu_max,
               ph_min, ph_max, do_min, do_max,
               orp_min, orp_max, created_at
        FROM oddset
        ORDER BY id DESC LIMIT 1
    ''')
    row = c.fetchone()
    conn.close()

    if not row:
        return "<h3>資料庫中尚無異常上下限設定資料</h3>"

    keys = ['temp', 'psu', 'ph', 'do', 'orp']
    issues = []
    oddset_data = {}

    for i, key in enumerate(keys):
        min_val = row[i*2]
        max_val = row[i*2 + 1]
        oddset_data[key+'_min'] = min_val
        oddset_data[key+'_max'] = max_val

        if min_val is None or max_val is None:
            issues.append(f"{key}: 有空值 (min: {min_val}, max: {max_val})")
        elif min_val > max_val:
            issues.append(f"{key}: 異常範圍錯誤，min ({min_val}) 大於 max ({max_val})")

    created_at = row[-1]

    html = f"<h2>最新異常上下限設定 (建立時間: {created_at})</h2><ul>"
    for key in keys:
        html += f"<li>{key} 範圍: {oddset_data[key+'_min']} ~ {oddset_data[key+'_max']}</li>"
    html += "</ul>"

    if issues:
        html += "<h3 style='color:red;'>發現設定問題：</h3><ul>"
        for issue in issues:
            html += f"<li>{issue}</li>"
        html += "</ul>"
    else:
        html += "<p style='color:green;'>所有設定正常</p>"

    return html

ensure_monitor_thread()

if __name__ == "__main__":
    ensure_monitor_thread()
    app.run(host="0.0.0.0", port=1000, debug=True)
