import sqlite3
import requests
import uuid
import os
from datetime import datetime
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'chiro.db')
GHL_API_KEY = "10b041a3-87b0-4083-bb18-f20d4610fb23"
GHL_LOCATION_ID = "3PwtLKNQL3P2gJ8d3gDi"
GHL_TAG = "started-care"

MILESTONE_EXPECTATIONS = {
    'visit2_pct': 10, 'visit5_pct': 15, 'visit8_pct': 20,
    'visit12_pct': 33, 'visit16_pct': 50,
}

SEED_SCORECARDS = {
    'leadership': [
        ('MARKETING', 'New Leads',               'DC', '',  0, '1784','600', '228','288','','',''),
        ('MARKETING', 'New Patients',             'KH', '',  1, '83',  '100', '4',  '28', '','',''),
        ('MARKETING', 'RED MRI CONVERSION',       'KH', '%', 2, '30',  '60',  '',   '',   '','',''),
        ('FINANCE',   'Total Sales',              'DC', '$', 0, '180000','272000','12000','74000','','',''),
        ('SALES',     'DComp Starts',             'DC', '',  0, '23',  '38',  '4',  '6',  '','',''),
        ('SALES',     'NEW ROF',                  'KH', '',  1, '47',  '68',  '3',  '20', '','',''),
        ('SALES',     'ROF Conversion % Kaplan',  'DC', '%', 2, '',    '',    '',   '',   '','',''),
        ('SALES',     'ROF Conversion % Dudum',   'DC', '%', 3, '',    '',    '',   '',   '','',''),
        ('SALES',     'ROF Conversion % Tong',    'DC', '%', 4, '',    '',    '',   '',   '','',''),
    ],
    'finance': [
        ('METRICS', 'Total Sales',   'DC', '$', 0, '180000','272000','12000','74000','','',''),
        ('METRICS', 'Unloaded CAC',  'DC', '$', 1, '',      '',      '',     '',     '','',''),
    ],
}

SEED_DASHBOARD = [
    ('DComp Starts',              'DC', '',  '10',    '+38.1', 'red',   0),
    ('New Leads',                 'DC', '',  '516',   '-16.6', 'green', 1),
    ('DComp Start Revenue',       'DC', '$', '53763', '+57.9', 'green', 2),
    ('Unloaded CAC',              'DC', '$', '',      '',      '',      3),
    ('Average Order Value',       'DC', '$', '5560',  '+76.8', 'green', 4),
    ('NEW ROF',                   'KH', '',  '23',    '+43.8', 'green', 5),
    ('Booking Confirmed',         'DC', '',  '',      '',      '',      6),
    ('Cancelled Continuity Memb', 'DC', '',  '',      '',      '',      7),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS patients (
        id TEXT PRIMARY KEY, source TEXT DEFAULT 'manual', name TEXT NOT NULL,
        phone TEXT DEFAULT '', email TEXT DEFAULT '', treatment_start_date TEXT,
        visits_prescribed INTEGER, visits_completed INTEGER, current_week INTEGER,
        collections_status TEXT DEFAULT 'Not Set', mri_status TEXT DEFAULT 'Not Ordered',
        visit2_pct REAL, visit5_pct REAL, visit8_pct REAL, visit12_pct REAL, visit16_pct REAL,
        missed_appointments INTEGER DEFAULT 0, today_status TEXT DEFAULT 'not_scheduled',
        notes TEXT DEFAULT '', active INTEGER DEFAULT 1, last_updated TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS scorecard_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scorecard TEXT NOT NULL, section TEXT NOT NULL, metric_name TEXT NOT NULL,
        owner TEXT DEFAULT 'DC', unit TEXT DEFAULT '',
        actuals TEXT DEFAULT '', goals TEXT DEFAULT '',
        w18 TEXT DEFAULT '', w19 TEXT DEFAULT '',
        w20 TEXT DEFAULT '', w21 TEXT DEFAULT '', w22 TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0, last_updated TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS dashboard_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL, owner TEXT DEFAULT 'DC', unit TEXT DEFAULT '',
        value TEXT DEFAULT '', change_pct TEXT DEFAULT '', change_dir TEXT DEFAULT '',
        sort_order INTEGER DEFAULT 0, last_updated TEXT)''')

    conn.commit()

    for scorecard, rows in SEED_SCORECARDS.items():
        if conn.execute("SELECT COUNT(*) FROM scorecard_metrics WHERE scorecard=?", (scorecard,)).fetchone()[0] == 0:
            for (section, name, owner, unit, order, act, goals, w18, w19, w20, w21, w22) in rows:
                conn.execute(
                    '''INSERT INTO scorecard_metrics
                       (scorecard,section,metric_name,owner,unit,actuals,goals,w18,w19,w20,w21,w22,sort_order,last_updated)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (scorecard, section, name, owner, unit, act, goals, w18, w19, w20, w21, w22, order, datetime.now().isoformat()))

    if conn.execute("SELECT COUNT(*) FROM dashboard_metrics").fetchone()[0] == 0:
        for (name, owner, unit, val, chg, dir_, order) in SEED_DASHBOARD:
            conn.execute(
                '''INSERT INTO dashboard_metrics (metric_name,owner,unit,value,change_pct,change_dir,sort_order,last_updated)
                   VALUES (?,?,?,?,?,?,?,?)''',
                (name, owner, unit, val, chg, dir_, order, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def sync_ghl_contacts():
    synced = 0; scanned = 0; errors = []
    params = {"locationId": GHL_LOCATION_ID, "limit": 100}
    while True:
        try:
            resp = requests.get("https://rest.gohighlevel.com/v1/contacts/",
                headers={"Authorization": f"Bearer {GHL_API_KEY}"}, params=params, timeout=15)
            data = resp.json()
        except Exception as e:
            errors.append(str(e)); break
        contacts = data.get("contacts", [])
        scanned += len(contacts)
        if not contacts: break
        conn = get_db()
        for c in contacts:
            if GHL_TAG.lower() not in [t.lower() for t in c.get("tags", [])]: continue
            ghl_id = f"ghl_{c['id']}"
            if not conn.execute("SELECT id FROM patients WHERE id=?", (ghl_id,)).fetchone():
                name = c.get("contactName") or f"{c.get('firstName','')} {c.get('lastName','')}".strip() or "Unknown"
                conn.execute('''INSERT INTO patients (id,source,name,phone,email,active,last_updated)
                    VALUES (?,'ghl',?,?,?,1,?)''',
                    (ghl_id, name, c.get("phone",""), c.get("email",""), datetime.now().isoformat()))
                synced += 1
        conn.commit(); conn.close()
        meta = data.get("meta", {})
        if not meta.get("nextPage") or not meta.get("startAfter"): break
        params = {"locationId": GHL_LOCATION_ID, "limit": 100,
                  "startAfter": meta.get("startAfter"), "startAfterId": meta.get("startAfterId")}
    return {"synced": synced, "scanned": scanned, "errors": errors}


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

# ── Patient API ────────────────────────────────────────────────────────────────

@app.route('/api/patients', methods=['GET'])
def get_patients():
    conn = get_db()
    rows = conn.execute("SELECT * FROM patients WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/patients/sync', methods=['POST'])
def sync():
    return jsonify(sync_ghl_contacts())

@app.route('/api/patients', methods=['POST'])
def add_patient():
    data = request.get_json()
    if not data or not data.get('name','').strip():
        return jsonify({'error': 'name is required'}), 400
    pid = f"manual_{uuid.uuid4().hex[:10]}"
    conn = get_db()
    conn.execute('''INSERT INTO patients (id,source,name,phone,email,active,last_updated)
        VALUES (?,'manual',?,?,?,1,?)''',
        (pid, data['name'].strip(), data.get('phone',''), data.get('email',''), datetime.now().isoformat()))
    conn.commit()
    patient = dict(conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(patient), 201

@app.route('/api/patients/<pid>', methods=['PUT'])
def update_patient(pid):
    data = request.get_json()
    allowed = {'name','phone','email','treatment_start_date','visits_prescribed','visits_completed',
               'current_week','collections_status','mri_status','visit2_pct','visit5_pct',
               'visit8_pct','visit12_pct','visit16_pct','missed_appointments','today_status','notes'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates: return jsonify({'error': 'no valid fields'}), 400
    updates['last_updated'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k}=?" for k in updates)
    conn = get_db()
    conn.execute(f"UPDATE patients SET {set_clause} WHERE id=?", list(updates.values()) + [pid])
    conn.commit()
    patient = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not patient: return jsonify({'error': 'not found'}), 404
    return jsonify(dict(patient))

@app.route('/api/patients/<pid>', methods=['DELETE'])
def remove_patient(pid):
    conn = get_db()
    conn.execute("UPDATE patients SET active=0 WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return jsonify({'status': 'ok'})

@app.route('/api/reset_today', methods=['POST'])
def reset_today():
    conn = get_db()
    conn.execute("UPDATE patients SET today_status='not_scheduled' WHERE active=1")
    conn.commit(); conn.close()
    return jsonify({'status': 'ok'})

# ── Scorecard API ──────────────────────────────────────────────────────────────

@app.route('/api/scorecard/<name>', methods=['GET'])
def get_scorecard(name):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM scorecard_metrics WHERE scorecard=? ORDER BY section, sort_order",
        (name,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/scorecard/metric/<int:mid>', methods=['PUT'])
def update_metric(mid):
    data = request.get_json()
    allowed = {'actuals','goals','w18','w19','w20','w21','w22','metric_name'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates: return jsonify({'error': 'no valid fields'}), 400
    updates['last_updated'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k}=?" for k in updates)
    conn = get_db()
    conn.execute(f"UPDATE scorecard_metrics SET {set_clause} WHERE id=?", list(updates.values()) + [mid])
    conn.commit()
    row = dict(conn.execute("SELECT * FROM scorecard_metrics WHERE id=?", (mid,)).fetchone())
    conn.close()
    return jsonify(row)

@app.route('/api/scorecard/<name>/add', methods=['POST'])
def add_metric(name):
    data = request.get_json()
    if not data or not data.get('metric_name','').strip():
        return jsonify({'error': 'metric_name required'}), 400
    conn = get_db()
    section = data.get('section', 'METRICS')
    max_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order),0) FROM scorecard_metrics WHERE scorecard=? AND section=?",
        (name, section)).fetchone()[0]
    conn.execute('''INSERT INTO scorecard_metrics
        (scorecard,section,metric_name,owner,unit,actuals,goals,w18,w19,w20,w21,w22,sort_order,last_updated)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (name, section, data['metric_name'].strip(), data.get('owner','DC'),
         data.get('unit',''), '','','','','','','', max_order+1, datetime.now().isoformat()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM scorecard_metrics WHERE id=last_insert_rowid()").fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/scorecard/metric/<int:mid>', methods=['DELETE'])
def delete_metric(mid):
    conn = get_db()
    conn.execute("DELETE FROM scorecard_metrics WHERE id=?", (mid,))
    conn.commit(); conn.close()
    return jsonify({'status': 'ok'})

# ── Dashboard metrics API ──────────────────────────────────────────────────────

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    conn = get_db()
    rows = conn.execute("SELECT * FROM dashboard_metrics ORDER BY sort_order").fetchall()
    patients = conn.execute("SELECT COUNT(*) FROM patients WHERE active=1").fetchone()[0]
    conn.close()
    return jsonify({'metrics': [dict(r) for r in rows], 'patient_count': patients})

@app.route('/api/dashboard/<int:mid>', methods=['PUT'])
def update_dashboard_metric(mid):
    data = request.get_json()
    allowed = {'value','change_pct','change_dir'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates: return jsonify({'error':'no valid fields'}), 400
    updates['last_updated'] = datetime.now().isoformat()
    set_clause = ', '.join(f"{k}=?" for k in updates)
    conn = get_db()
    conn.execute(f"UPDATE dashboard_metrics SET {set_clause} WHERE id=?", list(updates.values()) + [mid])
    conn.commit()
    row = dict(conn.execute("SELECT * FROM dashboard_metrics WHERE id=?", (mid,)).fetchone())
    conn.close()
    return jsonify(row)

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5050))
    print(f"Dashboard running at http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
