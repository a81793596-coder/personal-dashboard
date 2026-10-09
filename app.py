import sqlite3
import csv
import io
import re
from flask import Flask, render_template, request, jsonify, Response, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super_secret_personal_dashboard_key_ali'
DB_NAME = 'database.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جدول المستخدمين يعتمد على الجيميل والاسم الكامل
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            gmail TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # جدول البيانات اليومية
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            sleep_hours REAL DEFAULT 0,
            steps INTEGER DEFAULT 0,
            study_hours REAL DEFAULT 0,
            work_hours REAL DEFAULT 0,
            play_hours REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            UNIQUE(user_id, date),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def index():
    return render_template('index.html', full_name=session.get('full_name'))

@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    full_name = data.get('full_name', '').strip()
    gmail = data.get('gmail', '').strip().lower()
    password = data.get('password', '').strip()

    if not full_name or not gmail or not password:
        return jsonify({'status': 'error', 'message': 'يرجى تعبئة جميع الحقول'}), 400

    if not gmail.endswith('@gmail.com'):
        return jsonify({'status': 'error', 'message': 'يرجى إدخال عنوان الجيميل صحيح يكتمل بـ @gmail.com'}), 400

    hashed_pw = generate_password_hash(password)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (full_name, gmail, password) VALUES (?, ?, ?)", (full_name, gmail, hashed_pw))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن'})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'status': 'error', 'message': 'حساب الجيميل هذا مسجل بالفعل'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    gmail = data.get('gmail', '').strip().lower()
    password = data.get('password', '').strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, password FROM users WHERE gmail = ?", (gmail,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[2], password):
        session['user_id'] = user[0]
        session['full_name'] = user[1]
        return jsonify({'status': 'success', 'message': 'تم تسجيل الدخول بنجاح'})

    return jsonify({'status': 'error', 'message': 'حساب الجيميل أو كلمة المرور غير صحيحة'}), 400

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/api/data', methods=['GET'])
@login_required
def get_data():
    period = request.args.get('period', 'all')
    user_id = session['user_id']
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if period == '7':
        cursor.execute("SELECT * FROM daily_data WHERE user_id = ? ORDER BY date DESC LIMIT 7", (user_id,))
    elif period == '14':
        cursor.execute("SELECT * FROM daily_data WHERE user_id = ? ORDER BY date DESC LIMIT 14", (user_id,))
    elif period == '30':
        cursor.execute("SELECT * FROM daily_data WHERE user_id = ? ORDER BY date DESC LIMIT 30", (user_id,))
    else:
        cursor.execute("SELECT * FROM daily_data WHERE user_id = ? ORDER BY date ASC", (user_id,))
        
    rows = cursor.fetchall()
    conn.close()

    if period in ['7', '14', '30']:
        rows = list(reversed(rows))

    data = [dict(row) for row in rows]
    return jsonify(data)

@app.route('/api/add', methods=['POST'])
@login_required
def add_data():
    payload = request.get_json()
    user_id = session['user_id']
    date = payload.get('date')
    sleep_hours = float(payload.get('sleep_hours', 0))
    steps = int(payload.get('steps', 0))
    study_hours = float(payload.get('study_hours', 0))
    work_hours = float(payload.get('work_hours', 0))
    play_hours = float(payload.get('play_hours', 0))
    notes = payload.get('notes', '')

    if not date:
        return jsonify({'status': 'error', 'message': 'التاريخ مطلوب'}), 400

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO daily_data (user_id, date, sleep_hours, steps, study_hours, work_hours, play_hours, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            sleep_hours=excluded.sleep_hours,
            steps=excluded.steps,
            study_hours=excluded.study_hours,
            work_hours=excluded.work_hours,
            play_hours=excluded.play_hours,
            notes=excluded.notes
    ''', (user_id, date, sleep_hours, steps, study_hours, work_hours, play_hours, notes))
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'تم حفظ البيانات بنجاح'})

@app.route('/api/delete/<int:item_id>', methods=['DELETE'])
@login_required
def delete_data(item_id):
    user_id = session['user_id']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_data WHERE id = ? AND user_id = ?", (item_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': 'تم حذف السجل بنجاح'})

@app.route('/api/export', methods=['GET'])
@login_required
def export_csv():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT date, sleep_hours, steps, study_hours, work_hours, play_hours, notes FROM daily_data WHERE user_id = ? ORDER BY date ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'SleepHours', 'Steps', 'StudyHours', 'WorkHours', 'PlayHours', 'Notes'])
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=personal_analytics_data.csv"}
    )

@app.route('/api/import', methods=['POST'])
@login_required
def import_csv():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'لم يتم تحديد ملف'}), 400
    
    file = request.files['file']
    user_id = session['user_id']

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    csv_input = csv.reader(stream)
    next(csv_input, None)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    imported_count = 0

    for row in csv_input:
        if len(row) >= 6:
            try:
                date = row[0]
                sleep = float(row[1])
                steps = int(row[2])
                study = float(row[3])
                work = float(row[4])
                play = float(row[5])
                notes = row[6] if len(row) > 6 else ''

                cursor.execute('''
                    INSERT INTO daily_data (user_id, date, sleep_hours, steps, study_hours, work_hours, play_hours, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, date) DO UPDATE SET
                        sleep_hours=excluded.sleep_hours,
                        steps=excluded.steps,
                        study_hours=excluded.study_hours,
                        work_hours=excluded.work_hours,
                        play_hours=excluded.play_hours,
                        notes=excluded.notes
                ''', (user_id, date, sleep, steps, study, work, play, notes))
                imported_count += 1
            except ValueError:
                continue

    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': f'تم استيراد {imported_count} سجل بنجاح'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)