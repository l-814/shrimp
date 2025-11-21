import sqlite3
import random
from datetime import datetime
import pytz
import time

DB_PATH = './instance/users.db'  # 確保路徑正確

# 設定台灣時間
tz = pytz.timezone('Asia/Taipei')
now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

# 模擬幾個魚池的ID
POOL_IDS = ['1', '2', '3', '4']

def get_oddset():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM oddset ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()

    if not row:
        return {
            'temp_min': 18, 'temp_max': 25,
            'psu_min': 20, 'psu_max': 40,
            'ph_min': 5.5, 'ph_max': 8.5,
            'do_min': 5, 'do_max': 1000,
            'orp_min': 180, 'orp_max': 300
        }

    return {
        'temp_min': row[1], 'temp_max': row[2],
        'psu_min': row[3], 'psu_max': row[4],
        'ph_min': row[5], 'ph_max': row[6],
        'do_min': row[7], 'do_max': row[8],
        'orp_min': row[9], 'orp_max': row[10]
    }

def is_abnormal(value, min_val, max_val):
    return value < min_val or value > max_val

def generate_and_store_data():
    oddset = get_oddset()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    tz = pytz.timezone('Asia/Taipei')
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    for pool_id in POOL_IDS:
        seed = int(pool_id)

        temp = round(random.uniform(15, 30) + seed, 1)
        psu = 10
        ph = round(random.uniform(5.5, 8.5) + seed * 0.1, 1)
        do = round(random.uniform(5, 400) + seed * 0.1, 1)
        orp = round(random.uniform(150, 350) + seed * 2)

        abnormal = {
            'temp': is_abnormal(temp, oddset['temp_min'], oddset['temp_max']),
            'psu': is_abnormal(psu, oddset['psu_min'], oddset['psu_max']),
            'ph': is_abnormal(ph, oddset['ph_min'], oddset['ph_max']),
            'do': is_abnormal(do, oddset['do_min'], oddset['do_max']),
            'orp': is_abnormal(orp, oddset['orp_min'], oddset['orp_max'])
        }

        # 插入 sensor_data
        c.execute('''
            INSERT INTO sensor_data (pool_id, temp, psu, ph, do, orp, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (pool_id, temp, psu, ph, do, orp, now))

        values = {'temp': temp, 'psu': psu, 'ph': ph, 'do': do, 'orp': orp}

        # 插入 alerts，補上 description 欄位
        for key, is_abn in abnormal.items():
            if is_abn:
                min_val = oddset[key + '_min']
                max_val = oddset[key + '_max']
                if min_val > max_val:
                    min_val, max_val = max_val, min_val
                desc = f"{min_val} ~ {max_val}"
                c.execute('''
                    INSERT INTO alerts (pool_id, sensor_type, description, value, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (pool_id, key, desc, values[key], now))


    conn.commit()
    conn.close()


if __name__ == '__main__':
    while True:
        generate_and_store_data()
        print("資料已寫入")
        time.sleep(3)  # 每10秒產生一次
