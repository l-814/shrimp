from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import oauth_authorized
import pytz

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "fallback_secret_key")

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

tz = pytz.timezone('Asia/Taipei')

os.makedirs(app.instance_path, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, 'users.db')

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

@app.route('/api/latest-data/<pool_id>')
def latest_data(pool_id):
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
        return jsonify({'error': 'No data found'}), 404

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
            c.execute('INSERT INTO alerts (pool_id, sensor_type, description, value, timestamp, status) VALUES (?, ?, ?, ?, ?, ?)',
                      (pool_id, sensor, desc, value_map[sensor], timestamp, '未處理'))

    conn.commit()
    conn.close()

    return jsonify({
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
    })

@app.route('/api/history/latest/<pool_id>')
def api_history_latest(pool_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 抓最新 N 筆資料，例如最新 20 筆
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
        return jsonify({'error': '查無資料'}), 404  # 查無資料時回 404 與訊息

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

@app.route('/api/alerts')
def get_alerts():
    pool_id = request.args.get('pool', 'all')
    event_type = request.args.get('event', 'allodd')

    query = "SELECT pool_id, sensor_type, description, value, timestamp, status FROM alerts WHERE 1=1"
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

    event_type_map = {
        'temp': '水質異常',
        'psu': '水質異常',
        'ph': '水質異常',
        'do': '水質異常',
        'orp': '水質異常',
        'behavior': '行為異常',
        'food': '飼料異常'
    }
    sensor_name_map = {
        'temp': '溫度異常',
        'psu': '鹽度異常',
        'ph': 'pH異常',
        'do': '溶氧異常',
        'orp': 'ORP異常',
        'behavior': '行為異常',
        'food': '餵食異常'
    }

    results = []
    for row in rows:
        event_display = event_type_map.get(row['sensor_type'], row['sensor_type'])
        sensor_display = sensor_name_map.get(row['sensor_type'], row['sensor_type'])
        description = f"{sensor_display}： {row['value']} (正常範圍：{row['description']})"
        results.append({
            'pool': str(row['pool_id']),
            'type': event_display,
            'description': description,
            'time': row['timestamp'],
            'status': row['status'] if row['status'] else '未處理'
        })

    return jsonify(results)

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1000, debug=True)
