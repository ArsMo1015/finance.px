import os
import sqlite3
import random
import time
from datetime import date
from functools import wraps
from contextlib import contextmanager
from flask import Flask, request, session, redirect, url_for, render_template_string, render_template, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'pydroid-secret-rpg-world'
DB = 'finance.db'

os.makedirs('static/buildings', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('static/furniture', exist_ok=True)
os.makedirs('templates', exist_ok=True)

@contextmanager
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, 
            pw TEXT NOT NULL,
            money REAL DEFAULT 1000,
            status TEXT DEFAULT 'Нищий',
            jobs TEXT DEFAULT '',
            hunger INTEGER DEFAULT 50,
            quest_state INTEGER DEFAULT 0,
            quest_day INTEGER DEFAULT 1,
            quest_item TEXT DEFAULT '',
            quest_reward REAL DEFAULT 0,
            has_apartment INTEGER DEFAULT 0,
            apt_furniture TEXT DEFAULT '',
            last_worked_day INTEGER DEFAULT 0,
            current_district TEXT DEFAULT 'Центральный',
            courier_status TEXT DEFAULT '',
            courier_address TEXT DEFAULT '',
            courier_target TEXT DEFAULT '',
            courier_reward REAL DEFAULT 0,
            death_started_at REAL DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL, 
            qty INTEGER DEFAULT 1, 
            price REAL NOT NULL
        );
        ''')
        for col, col_def in [
            ('death_started_at', 'REAL DEFAULT NULL'),
            ('apt_furniture', "TEXT DEFAULT ''"),
            ('has_apartment', 'INTEGER DEFAULT 0'),
            ('jobs', "TEXT DEFAULT ''"),
            ('current_district', "TEXT DEFAULT 'Центральный'")
        ]:
            try:
                c.execute(f'SELECT {col} FROM users LIMIT 1')
            except sqlite3.OperationalError:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {col_def}')
                
        try:
            c.execute('UPDATE users SET apt_furniture = REPLACE(apt_furniture, "Игровой ПК", "Корпус ПК") WHERE apt_furniture LIKE "%Игровой ПК%"')
        except Exception:
            pass

JOBS = {
    'Дворник': {'salary': 800, 'penalty': 5000, 'req': 'Нищий', 'game': 'hold', 'desc': 'Собирай листья', 'icon': '🧹', 'loc': 'Стройка'},
    'Грузчик': {'salary': 1500, 'penalty': 5000, 'req': 'Нищий', 'game': 'clicker', 'desc': 'Скидывай коробки', 'icon': '📦', 'loc': 'Стройка'},
    'Сварщик': {'salary': 3500, 'penalty': 7000, 'req': 'Обычный', 'game': 'weld', 'desc': 'Вари швы', 'icon': '🔧', 'loc': 'Стройка'},
    'Каменщик': {'salary': 6000, 'penalty': 10000, 'req': 'Обычный', 'game': 'clicker', 'desc': 'Класть кирпичи', 'icon': '🧱', 'loc': 'Стройка'},
    'Прораб': {'salary': 15000, 'penalty': 20000, 'req': 'Мажор', 'game': 'math', 'desc': 'Считать смету', 'icon': '📋', 'loc': 'Стройка'},
    'Курьер': {'salary': 0, 'penalty': 15000, 'req': 'Обычный', 'game': 'courier', 'desc': 'Доставляй заказы', 'icon': '🚴', 'loc': 'Офис'},
    'Менеджер': {'salary': 6000, 'penalty': 20000, 'req': 'Обычный', 'game': 'math', 'desc': 'Решай задачи', 'icon': '💼', 'loc': 'Офис'},
    'Аналитик': {'salary': 12000, 'penalty': 30000, 'req': 'Мажор', 'game': 'math_hard', 'desc': 'Считай графики', 'icon': '📊', 'loc': 'Офис'},
    'Программист': {'salary': 0, 'penalty': 40000, 'req': 'Мажор', 'game': 'coder', 'desc': 'Фикси баги', 'icon': '💻', 'loc': 'Офис'},
    'Директор': {'salary': 35000, 'penalty': 60000, 'req': 'Влиятельный', 'game': 'logic', 'desc': 'Управляй компанией', 'icon': '📈', 'loc': 'Офис'},
    'Тимлид': {'salary': 50000, 'penalty': 80000, 'req': 'Влиятельный', 'game': 'math_hard', 'desc': 'Планируй спринт', 'icon': '👨‍💻', 'loc': 'Офис'},
    'Депутат': {'salary': 120000, 'penalty': 50000, 'req': 'Влиятельный', 'game': 'speech', 'desc': 'Продвигай законы', 'icon': '🏛', 'loc': 'Ратуша'},
    'Министр': {'salary': 250000, 'penalty': 100000, 'req': 'Влиятельный', 'game': 'math_hard', 'desc': 'Распределяй бюджет', 'icon': '📜', 'loc': 'Ратуша'},
    'Президент': {'salary': 500000, 'penalty': 100000, 'req': 'Президент', 'game': 'president', 'desc': 'Управляй страной', 'icon': '👑', 'loc': 'Ратуша'},
}

STATUSES = ['Нищий', 'Обычный', 'Мажор', 'Влиятельный', 'Президент']
UPGRADE_COST = {'Обычный': 15000, 'Мажор': 150000, 'Влиятельный': 1500000, 'Президент': 15000000}
SHOP = {'Хлеб': {'price': 50, 'hunger': 15}, 'Пицца': {'price': 300, 'hunger': 50}, 'Элитный стейк': {'price': 2000, 'hunger': 100}}

FURNITURE = {
    'Диван': 25000, 'Телевизор': 40000, 'Холодильник': 30000, 'Корпус ПК': 50000, 
    'Монитор 60Hz': 20000, 'Монитор 144Hz': 45000, 'Офисная клавиатура': 3000, 
    'Механическая клавиатура': 10000, 'Офисная мышь': 1500, 'Игровая мышь': 6000
}

QUEST_POOL = [
    {'item': 'Хлеб', 'reward': 150, 'text': 'Принеси хлеб, я заплачу 150 ₽.'},
    {'item': 'Пицца', 'reward': 500, 'text': 'Умираю с голоду! Тащи пиццу!'},
    {'item': 'Элитный стейк', 'reward': 3000, 'text': 'Принеси стейк, получишь 3000 ₽!'}
]
COURIER_ADDRESSES = ["ул. Ленина, д. 42", "пр. Мира, д. 15", "ул. Пушкина, д. 7", "ул. Гагарина, д. 99", "ТЦ 'Город', 3 этаж"]

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if 'uid' not in session:
            return redirect(url_for('login'))
        return f(*a, **k)
    return w

CSS = '''
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,system-ui,sans-serif;background:#0f172a;color:#f8fafc;padding-bottom:0;overflow:hidden;height:100vh;}
.top{background:linear-gradient(135deg,#1e293b,#334155);padding:12px;display:flex;justify-content:space-between;align-items:center;position:absolute;top:0;left:0;right:0;z-index:100;border-bottom:1px solid #475569}
.top h1{font-size:1rem;color:#38bdf8}
.top a{color:#f8fafc;text-decoration:none;padding:6px 12px;border:1px solid rgba(255,255,255,.2);border-radius:8px;font-size:.8rem}
.card{background:#1e293b;border-radius:16px;padding:16px;margin-bottom:12px;box-shadow:0 4px 6px rgba(0,0,0,.3);border:1px solid #334155}
.balance{background:linear-gradient(135deg,#4f46e5,#7c3aed);border-radius:16px;padding:20px;margin-bottom:16px;box-shadow:0 4px 15px rgba(124,58,237,.4)}
.balance .l{font-size:.85rem;opacity:.85;text-transform:uppercase;letter-spacing:1px}
.balance .v{font-size:2.2rem;font-weight:800;margin:4px 0 12px}
.btn{display:block;width:100%;padding:14px;border:none;border-radius:12px;font-size:1rem;font-weight:600;cursor:pointer;text-align:center;text-decoration:none;min-height:48px;color:white;touch-action:manipulation}
.btn:active{transform:scale(0.98)}
.btn.green{background:#22c55e}
.btn.blue{background:#3b82f6}
.btn.red{background:#ef4444}
.btn.gray{background:#475569}
.btn.yellow{background:#eab308; color:#0f172a}
.fg{margin-bottom:14px}
.fg label{display:block;font-size:.9rem;margin-bottom:6px;font-weight:500;color:#94a3b8}
.fc{width:100%;padding:13px 14px;border:1.5px solid #334155;border-radius:12px;font-size:1rem;background:#0f172a;color:white;font-family:inherit}
.fc:focus{outline:none;border-color:#38bdf8}
.flash{padding:12px;border-radius:12px;margin-bottom:12px;font-size:.9rem;font-weight:600;position:fixed;top:60px;left:50%;transform:translateX(-50%);z-index:999;width:90%;max-width:400px;}
.flash.error{background:#7f1d1d;color:#fecaca}
.flash.success{background:#14532d;color:#bbf7d0}
.txn{display:flex;align-items:center;justify-content:space-between;padding:12px;background:#0f172a;border-radius:12px;margin-bottom:8px;border:1px solid #334155}
.auth{max-width:400px;margin:40px auto;padding:24px;background:#1e293b;border-radius:16px;border:1px solid #334155}
.auth h1{text-align:center;font-size:1.5rem;margin-bottom:6px}
.auth .st{text-align:center;color:#94a3b8;font-size:.9rem;margin-bottom:20px}
.auth .lk{display:block;text-align:center;margin-top:14px;color:#38bdf8;text-decoration:none;font-size:.9rem}
.bar{height:12px;background:#0f172a;border-radius:6px;overflow:hidden;margin-top:8px;border:1px solid #334155}
.bar>div{height:100%;transition:width .3s}
h2{font-size:1.1rem;margin:16px 0 10px;font-weight:600;color:#38bdf8}
.tag{display:inline-block;padding:4px 10px;border-radius:20px;font-size:.75rem;font-weight:700;background:#334155;color:#f8fafc;margin-left:8px}
.casino-num{font-size:4rem; font-weight:900; text-align:center; color:#eab308; margin:20px 0; text-shadow:0 0 20px rgba(234,179,8,.5);}
#map-container { position: absolute; top: 50px; bottom: 0; left: 0; right: 0; display: flex; justify-content: center; align-items: center; overflow: hidden; background: #0f172a;}
#gameCanvas { background: #064e3b; touch-action: none; width: 100%; height: 100%; display: block; image-rendering: pixelated;}
.action-btn { position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); background: #22c55e; color: white; border: none; padding: 12px 24px; border-radius: 30px; font-size: 1.1rem; font-weight: bold; display: none; z-index: 20; box-shadow: 0 4px 15px rgba(34,197,94,0.5); cursor: pointer; }
.scroll-content { padding: 70px 16px 20px 16px; overflow-y: auto; height: 100vh; }
#phone-btn { position: absolute; top: 70px; right: 10px; background: #1e293b; border: 2px solid #475569; border-radius: 50%; width: 50px; height: 50px; font-size: 24px; display: flex; justify-content: center; align-items: center; z-index: 50; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
#map-btn { position: absolute; top: 130px; right: 10px; background: #1e293b; border: 2px solid #475569; border-radius: 50%; width: 50px; height: 50px; font-size: 24px; display: flex; justify-content: center; align-items: center; z-index: 50; cursor: pointer; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
#phone-overlay { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 200; display: none; justify-content: center; align-items: center; padding: 20px; backdrop-filter: blur(2px); }
.phone-screen { background: #0f172a; width: 100%; max-width: 350px; height: 80%; max-height: 600px; border-radius: 30px; border: 8px solid #1e293b; display: flex; flex-direction: column; overflow: hidden; position: relative; box-shadow: 0 10px 30px rgba(0,0,0,0.8); }
.phone-top { background: #1e293b; padding: 10px; text-align: center; font-size: 12px; color: #94a3b8; border-bottom: 1px solid #334155; }
.phone-tabs { display: flex; background: #1e293b; }
.phone-tabs button { flex: 1; background: none; border: none; color: #94a3b8; padding: 12px 0; font-size: 13px; font-weight: bold; cursor: pointer; border-bottom: 2px solid transparent; }
.phone-tabs button.active { color: #38bdf8; border-bottom-color: #38bdf8; }
.phone-content { flex: 1; overflow-y: auto; padding: 15px; }
.close-phone { position: absolute; top: 10px; right: 15px; color: #ef4444; font-size: 20px; font-weight: bold; cursor: pointer; z-index: 210; }
.modal { display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.8); z-index:300; justify-content:center; align-items:center; padding:20px; }
.modal-content { background:#fff; color:#000; padding:20px; border-radius:10px; width:100%; max-width:400px; }
.signature-canvas { border:2px dashed #ccc; border-radius:5px; width:100%; height:150px; touch-action:none; }
#death-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: black; opacity: 0; pointer-events: none; z-index: 9000; transition: opacity 0.3s; }
.toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); padding: 12px 24px; border-radius: 12px; font-weight: bold; z-index: 9999; animation: slideDown 0.3s ease-out; display: flex; align-items: center; gap: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
.toast.error { background: #7f1d1d; color: #fecaca; border: 1px solid #ef4444; }
.toast.warning { background: #78350f; color: #fde68a; border: 1px solid #f59e0b; }
@keyframes slideDown { from { top: -50px; opacity: 0; } to { top: 20px; opacity: 1; } }
#hunger-timer { display: none; position: fixed; top: 20%; left: 50%; transform: translateX(-50%); font-size: 4rem; font-weight: 900; color: #ef4444; z-index: 9500; text-shadow: 0 0 20px black, 0 0 40px red; pointer-events: none; animation: pulse 1s infinite; }
@keyframes pulse { 0% { transform: translateX(-50%) scale(1); } 50% { transform: translateX(-50%) scale(1.1); } 100% { transform: translateX(-50%) scale(1); } }
.stat-bar { display:flex; align-items:center; gap:10px; margin-bottom:8px; font-size:14px; font-weight:bold; }
.stat-bar .label { width: 80px; color:#94a3b8; }
.stat-bar .track { flex:1; height:16px; background:#0f172a; border-radius:8px; overflow:hidden; border:1px solid #334155; }
.stat-bar .fill { height:100%; transition:width 0.3s; }
.mini-card { background:#1e293b; border:1px solid #334155; padding:15px; border-radius:12px; margin-bottom:10px; text-align:center; }
.choice-btn { display:block; width:100%; padding:12px; margin-bottom:8px; background:#334155; color:white; border:none; border-radius:8px; font-size:14px; cursor:pointer; text-align:left; transition:background 0.2s; }
.choice-btn:hover { background:#475569; }
.choice-btn.selected { border: 2px solid #38bdf8; background: rgba(56,189,248,0.2); }
#map-overlay { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); display: none; justify-content: center; align-items: center; z-index: 300; backdrop-filter: blur(4px); }
.map-cell { background: #334155; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #94a3b8; font-weight: bold; font-size: 12px; position: relative; border: 2px solid transparent; transition: all 0.2s; }
.map-cell.active { background: #3b82f6; color: white; border-color: #38bdf8; }
.map-cell.active::after { content: '📍'; position: absolute; top: -10px; right: -10px; font-size: 20px; animation: pulse 1s infinite; }
'''

BASE = '''<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#1e293b"><title>{{title}}</title>
<style>''' + CSS + '''</style></head><body>
<div id="death-overlay"></div>
<div id="hunger-timer">30 сек</div>
{% if session.uid %}<div class="top"><h1>{{hdr or '🌆 Симулятор жизни'}}</h1><a href="{{ '/logout' if active == 'home' else '/' }}">{{ 'Выйти' if active == 'home' else 'На улицу' }}</a></div>{% endif %}
{% with m = get_flashed_messages(with_categories=true) %}{% for c,msg in m %}<div class="flash {{c}}">{{msg}}</div>{% endfor %}{% endwith %}
{% if active == 'home' %}
    {{body|safe}}
{% else %}
    <div class="scroll-content">{{body|safe}}</div>
{% endif %}
<script>window.deathRemainingAtLoad = {{ death_remaining or 0 }};</script>
<script src="/static/js/hunger_timer.js"></script>
</body></html>'''

def get_death_remaining(u):
    if not u or not u['death_started_at']:
        return 0
    elapsed = time.time() - u['death_started_at']
    return max(0, 30 - elapsed)

def render(body, title='Игра', hdr=None, active=None):
    death_remaining = 0
    if 'uid' in session:
        u = get_user(session['uid'])
        if u:
            if u['death_started_at']:
                elapsed = time.time() - u['death_started_at']
                if elapsed >= 30:
                    return redirect(url_for('die'))
                death_remaining = max(0, 30 - elapsed)
            elif u['hunger'] <= 5:
                now = time.time()
                with db() as c:
                    c.execute('UPDATE users SET death_started_at=? WHERE id=?', (now, u['id']))
                death_remaining = 30
    return render_template_string(BASE, body=body, title=title, hdr=hdr, active=active, death_remaining=death_remaining)

def get_user(uid):
    with db() as c:
        return c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()

# ============ АВТОРИЗАЦИЯ ============

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('u', '').strip()
        p = request.form.get('p', '')
        with db() as c:
            r = c.execute('SELECT * FROM users WHERE username=?', (u,)).fetchone()
        if r and check_password_hash(r['pw'], p):
            session['uid'] = r['id']
            session['un'] = r['username']
            if u == 'Admin':
                session['admin'] = True
            return redirect(url_for('index'))
        flash('Неверный логин или пароль', 'error')
    return render('''<div class="auth"><h1>🌆 Симулятор</h1><p class="st">Вход</p><form method="POST"><div class="fg"><label>Логин</label><input class="fc" name="u" required autofocus></div><div class="fg"><label>Пароль</label><input class="fc" type="password" name="p" required></div><button class="btn blue" type="submit">Войти</button></form><a href="/register" class="lk">Нет аккаунта? Регистрация</a></div>''', 'Вход')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('u', '').strip()
        p = request.form.get('p', '')
        p2 = request.form.get('p2', '')
        if len(u) < 3:
            flash('Логин минимум 3 символа', 'error')
        elif len(p) < 6:
            flash('Пароль минимум 6 символов', 'error')
        elif p == u:
            flash('Пароль не может совпадать с логином!', 'error')
        elif p != p2:
            flash('Пароли не совпадают', 'error')
        else:
            try:
                with db() as c:
                    cur = c.execute('INSERT INTO users(username,pw) VALUES(?,?)', (u, generate_password_hash(p)))
                    session['uid'] = cur.lastrowid
                    session['un'] = u
                return redirect(url_for('index'))
            except sqlite3.IntegrityError:
                flash('Такой логин уже есть', 'error')
    return render('''<div class="auth"><h1>🎉 Регистрация</h1><p class="st">Начни с 1000 ₽</p><form method="POST"><div class="fg"><label>Логин</label><input class="fc" name="u" required minlength="3" autofocus></div><div class="fg"><label>Пароль</label><input class="fc" type="password" name="p" required minlength="6"></div><div class="fg"><label>Повторите пароль</label><input class="fc" type="password" name="p2" required minlength="6"></div><button class="btn green" type="submit">Зарегистрироваться</button></form><a href="/login" class="lk">Уже есть аккаунт? Войти</a></div>''', 'Регистрация')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============ СМЕРТЬ ОТ ГОЛОДА ============

@app.route('/die')
@login_required
def die():
    u = get_user(session['uid'])
    lost_money = u['money'] * 0.5
    new_money = u['money'] - lost_money
    with db() as c:
        c.execute('UPDATE users SET money=?, hunger=50, death_started_at=NULL WHERE id=?', (new_money, u['id']))
    
    body = f'''<div style="text-align:center; margin-top:50px;">
        <h1 style="color:#ef4444; font-size:4rem; text-shadow:0 0 20px red;">💀 ТЫ ПОГИБ</h1>
        <p style="font-size:1.2rem; margin:20px 0;">Ты умер от голода. Врачи чудом спасли тебя, но забрали половину твоих сбережений.</p>
        <p style="color:#eab308; font-size:1.5rem; font-weight:bold; margin-bottom:30px;">Потеряно: {lost_money:,.0f} ₽</p>
        <a href="/" class="btn green" style="display:inline-block; width:auto; padding:15px 40px;">Очнуться в больнице</a>
    </div>'''
    return render(body, 'Смерть', '💀 Клиника', 'office')

@app.route('/update_district', methods=['POST'])
@login_required
def update_district():
    district = request.form.get('district')
    if district:
        with db() as c:
            c.execute('UPDATE users SET current_district=? WHERE id=?', (district, session['uid']))
    return jsonify({"status": "ok"})

# ============ ГЛАВНАЯ СТРАНИЦА ============

@app.route('/')
def index():
    if 'uid' not in session:
        return redirect(url_for('login'))
    u = get_user(session['uid'])
    if not u:
        session.clear()
        return redirect(url_for('login'))

    enter_dir = request.args.get('dir', '')
    current_district = u['current_district'] if u['current_district'] else 'Центральный'

    with db() as c:
        items = c.execute('SELECT * FROM inventory WHERE user_id=?', (u['id'],)).fetchall()

    inv_html = ""
    for i in items:
        sell_price = int(i['price'] * 0.7)
        if i['item'] in FURNITURE:
            inv_html += f'''<div class="txn"><div><div style="font-weight:700">{i['item']} (Мебель)</div><div style="font-size:.8rem;color:#f59e0b">Отнеси домой</div></div><form method="POST" action="/sell"><input type="hidden" name="id" value="{i['id']}"><button class="btn gray" style="padding:6px 12px; min-height:32px; width:auto; font-size:.8rem;" type="submit">Продать ({sell_price} ₽)</button></form></div>'''
        else:
            inv_html += f'''<div class="txn"><div><div style="font-weight:700">{i['item']} (x{i['qty']})</div></div><div style="display:flex; gap:6px;"><form method="POST" action="/eat"><input type="hidden" name="id" value="{i['id']}"><input type="hidden" name="item" value="{i['item']}"><button class="btn blue" style="padding:6px 12px; min-height:32px; width:auto; font-size:.8rem;" type="submit">Съесть</button></form><form method="POST" action="/sell"><input type="hidden" name="id" value="{i['id']}"><button class="btn gray" style="padding:6px 12px; min-height:32px; width:auto; font-size:.8rem;" type="submit">Продать ({sell_price} ₽)</button></form></div></div>'''

    q_state = u['quest_state'] if u['quest_state'] else 0
    quest_html = ""
    if q_state == 0:
        quest_html = "<p style='color:#94a3b8;'>Нет активных заданий. Найди Бизнесмена 🤵 в центре города!</p>"
    elif q_state == 1:
        quest_html = f"<div class='card'><h3>📦 {u['quest_item']}</h3><p style='font-size:14px; margin-top:5px;'>Бизнесмен ждет это из магазина.</p><p style='color:#eab308; font-size:12px; margin-top:10px;'>Награда: {u['quest_reward']} ₽</p></div>"
    elif q_state == 2:
        quest_html = "<p style='color:#22c55e;'>Все задания выполнены! Приходи после 6 утра.</p>"

    apt_status = "Есть" if u['has_apartment'] else "Нет"
    furn_list = u['apt_furniture'].split('|') if u['apt_furniture'] else []
    furn_html = ", ".join([f.split(':')[0] for f in furn_list if f]) if furn_list else "Пусто"

    is_admin = 'true' if session.get('admin') else 'false'
    user_jobs = u['jobs'].split(',') if u['jobs'] else []
    jobs_display = ", ".join(user_jobs) if user_jobs else "Безработный"

    courier_info = ""
    if u['courier_status'] == 'delivering':
        courier_info = f"<div class='card' style='border-color:#f59e0b;'><h3 style='color:#f59e0b;'>🚴 Доставка</h3><p style='font-size:14px;'>Доставить: {u['courier_address']}</p><p style='font-size:14px;'>Район: {u['courier_target']}</p></div>"

    hunger_color = '#22c55e'
    if u['hunger'] <= 50: hunger_color = '#eab308'
    if u['hunger'] <= 25: hunger_color = '#ef4444'

    body = f'''
    <div id="map-container">
        <canvas id="gameCanvas"></canvas>
        <button id="actionBtn" class="action-btn">Войти</button>
        <button id="phone-btn" onclick="togglePhone()">📱</button>
        <button id="map-btn" onclick="toggleMap()">🗺️</button>
    </div>

    <div id="map-overlay">
        <div style="background: #1e293b; border: 2px solid #38bdf8; border-radius: 16px; padding: 20px; text-align: center; max-width: 350px; width: 90%;">
            <h2 style="color: #38bdf8; margin-top: 0;">Карта города</h2>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin: 15px auto; width: 300px; height: 300px;">
                <div></div><div class="map-cell" id="map-Северный">Северный</div><div></div>
                <div class="map-cell" id="map-Западный">Западный</div><div class="map-cell" id="map-Центральный">Центральный</div><div class="map-cell" id="map-Восточный">Восточный</div>
                <div></div><div class="map-cell" id="map-Южный">Южный</div><div></div>
            </div>
            <p style="color: #94a3b8; font-size: 14px; margin: 5px 0;">Вы находитесь: <b id="map-current-district" style="color: #f8fafc;">{current_district}</b></p>
            <p style="color: #94a3b8; font-size: 14px; margin-bottom: 20px;">Улица: <b style="color: #f8fafc;">Проспект Мира</b></p>
            <button onclick="toggleMap()" class="btn gray" style="padding: 10px;">Закрыть</button>
        </div>
    </div>

    <div id="phone-overlay">
        <div class="phone-screen">
            <div class="close-phone" onclick="togglePhone()">✕</div>
            <div class="phone-top">📶 Poco 4G 🔋 91%</div>
            <div class="phone-tabs">
                <button id="tab-bank" class="active" onclick="switchTab('bank')">Банк</button>
                <button id="tab-quest" onclick="switchTab('quest')">Квесты</button>
                <button id="tab-inv" onclick="switchTab('inv')">Рюкзак</button>
                <button id="tab-settings" onclick="switchTab('settings')">⚙️</button>
            </div>
            <div class="phone-content">
                <div id="content-bank" style="display:block;">
                    <div class="balance"><div class="l">Кошелек</div><div class="v">{u['money']:,.0f} ₽</div></div>
                    <div class="card">
                        <div style="display:flex; justify-content:space-between; margin-bottom:5px;"><span>Статус:</span> <b>{u['status']}</b></div>
                        <div style="display:flex; justify-content:space-between; margin-bottom:5px;"><span>Голод:</span> <b id="phone-hunger-text">{u['hunger']}/100</b></div>
                        <div class="bar" style="margin-bottom:10px;"><div id="phone-hunger-bar" style="width:{u['hunger']}%; background:{hunger_color};"></div></div>
                        <div style="display:flex; justify-content:space-between; margin-bottom:10px;"><span>Работы:</span> <b>{jobs_display}</b></div>
                        <div style="display:flex; justify-content:space-between; margin-bottom:10px;"><span>Квартира:</span> <b>{apt_status}</b></div>
                        <div style="display:flex; justify-content:space-between;"><span>Мебель:</span> <b>{furn_html}</b></div>
                    </div>
                </div>
                <div id="content-quest" style="display:none;">
                    <h3 style="color:#38bdf8; margin-bottom:10px;">Задания</h3>
                    {courier_info}
                    {quest_html}
                </div>
                <div id="content-inv" style="display:none;">
                    {inv_html if inv_html else '<p style="text-align:center; color:#94a3b8; margin-top:20px;">Рюкзак пуст</p>'}
                </div>
                <div id="content-settings" style="display:none;">
                    <h3 style="color:#38bdf8; margin-bottom:10px;">Управление</h3>
                    <div class="card" style="display:flex; flex-direction:column; gap:15px;">
                        <label style="display:flex; align-items:center; gap:10px; cursor:pointer;">
                            <input type="radio" name="ctrl_mode" value="fixed" onchange="setControl('fixed')" id="ctrl-fixed" style="width:20px; height:20px;">
                            <span>Фиксированный (слева)</span>
                        </label>
                        <label style="display:flex; align-items:center; gap:10px; cursor:pointer;">
                            <input type="radio" name="ctrl_mode" value="dynamic" onchange="setControl('dynamic')" id="ctrl-dynamic" style="width:20px; height:20px;">
                            <span>Динамический (в любом месте)</span>
                        </label>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const isAdmin = {is_admin};
        if(isAdmin) {{
            const btn = document.createElement('a');
            btn.href = '/admin';
            btn.innerText = '👑 АДМИН';
            btn.style.cssText = 'position:absolute; top:70px; left:10px; background:#ef4444; color:white; padding:10px 15px; border-radius:10px; font-weight:bold; text-decoration:none; z-index:100; box-shadow:0 4px 10px rgba(0,0,0,0.5);';
            document.getElementById('map-container').appendChild(btn);
        }}
        const lastWorkedDay = {u['last_worked_day']};
        const hasJobs = {1 if u['jobs'] else 0};
        const startDistrict = "{current_district}";
        const startEnterDir = "{enter_dir}";
        const questState = {q_state};
        const courierStatus = "{u['courier_status']}";
        const courierTarget = "{u['courier_target']}";
        const currentHunger = {u['hunger']};

        (function() {{
            let level = currentHunger <= 5 ? 'dying' : (currentHunger <= 25 ? 'critical' : (currentHunger <= 50 ? 'warning' : 'ok'));
            let lastLevel = localStorage.getItem('lastHungerLevel') || 'ok';
            if (level !== lastLevel) {{
                localStorage.setItem('lastHungerLevel', level);
                if (level === 'warning') showToast('⚠️ Голод ниже 50! Скоро захочется есть.', 'warning');
                if (level === 'critical') showToast('🚨 Голод ниже 25! Срочно поешьте!', 'error');
                if (level === 'dying') showToast('💀 ТЫ УМИРАЕШЬ ОТ ГОЛОДА!', 'error');
            }}
        }})();

        function showToast(msg, type) {{
            let t = document.createElement('div');
            t.className = 'toast ' + type;
            t.innerText = msg;
            document.body.appendChild(t);
            setTimeout(() => t.remove(), 5000);
        }}
        
        let savedTime = localStorage.getItem('gameTime');
        let gameTime = savedTime ? parseFloat(savedTime) : 12;
        let savedDay = localStorage.getItem('gameDay');
        let gameDay = savedDay ? parseInt(savedDay) : 1;

        if (hasJobs && lastWorkedDay > 0 && gameDay > lastWorkedDay + 1) {{
            window.location.href = '/penalize';
        }}
        
        function toggleMap() {{
            const m = document.getElementById('map-overlay');
            if (m.style.display === 'flex') {{
                m.style.display = 'none';
            }} else {{
                m.style.display = 'flex';
                document.querySelectorAll('.map-cell').forEach(el => el.classList.remove('active'));
                const currentEl = document.getElementById('map-' + startDistrict);
                if (currentEl) currentEl.classList.add('active');
                document.getElementById('map-current-district').innerText = startDistrict;
            }}
        }}
    </script>

    <script>
        const canvas = document.getElementById('gameCanvas');
        const ctx = canvas.getContext('2d');
        const actionBtn = document.getElementById('actionBtn');
        ctx.imageSmoothingEnabled = false;

        const WORLD_W = 2400;
        const WORLD_H = 2400;
        let cx = 1200;
        let cy = 1200;
        const roadW = 100;

        const BUILDING_IMAGES = {{
            'Стройка':   'stroyka.png', 'Агентство': 'agentstvo.png', 'Карьера':   'karera.png',
            'Ратуша':    'ratusha.png', 'Магазин':   'magazin.png', 'Офис':      'ofis.png',
            'Мебельный': 'mebelniy.png', 'Дом':       'dom.png', 'Казино':    'kazino.png',
            'ТЦ':        'tc.png', 'Жилой дом': 'jiloy_dom.png', 'Бизнесмен': 'biznesmen.png'
        }};
        const buildingImages = {{}};

        function loadAndCleanImage(id, file) {{
            const img = new Image();
            img.onload = () => {{
                const tempCanvas = document.createElement('canvas');
                tempCanvas.width = img.width;
                tempCanvas.height = img.height;
                const tempCtx = tempCanvas.getContext('2d');
                tempCtx.drawImage(img, 0, 0);
                const imgData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
                const data = imgData.data;
                for (let i = 0; i < data.length; i += 4) {{
                    if (data[i] > 230 && data[i+1] > 230 && data[i+2] > 230) {{
                        data[i+3] = 0;
                    }}
                }}
                tempCtx.putImageData(imgData, 0, 0);
                buildingImages[id] = tempCanvas;
            }};
            img.onerror = () => console.warn('Нет спрайта: static/buildings/' + file);
            img.src = '/static/buildings/' + file;
        }}

        for (const [id, file] of Object.entries(BUILDING_IMAGES)) {{
            loadAndCleanImage(id, file);
        }}

        let isPaused = false;
        let controlMode = localStorage.getItem('controlMode') || 'fixed';
        
        function setControl(mode) {{
            controlMode = mode;
            localStorage.setItem('controlMode', mode);
        }}
        
        if (controlMode === 'fixed') document.getElementById('ctrl-fixed').checked = true;
        else document.getElementById('ctrl-dynamic').checked = true;

        function togglePhone() {{
            const p = document.getElementById('phone-overlay');
            if (p.style.display === 'flex') {{ p.style.display = 'none'; isPaused = false; }}
            else {{ p.style.display = 'flex'; isPaused = true; joy.active = false; moveX=0; moveY=0; }}
        }}
        function switchTab(t) {{
            document.getElementById('content-bank').style.display = t==='bank'?'block':'none';
            document.getElementById('content-quest').style.display = t==='quest'?'block':'none';
            document.getElementById('content-inv').style.display = t==='inv'?'block':'none';
            document.getElementById('content-settings').style.display = t==='settings'?'block':'none';
            document.getElementById('tab-bank').className = t==='bank'?'active':'';
            document.getElementById('tab-quest').className = t==='quest'?'active':'';
            document.getElementById('tab-inv').className = t==='inv'?'active':'';
            document.getElementById('tab-settings').className = t==='settings'?'active':'';
        }}

        let buildings = [];
        let currentDistrict = startDistrict;

        function initMap() {{
            // УВЕЛИЧЕННЫЙ РАЗМЕР ЗДАНИЙ (150x150)
            const bSize = 150; 
            
            buildings = [
                // ЦЕНТРАЛЬНЫЙ РАЙОН (Сетка 3x3)
                {{ id: 'Стройка',   name: 'Стройка',   icon: '🏗️', x: 880, y: 880, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'Ратуша',    name: 'Ратуша',    icon: '🏛️', x: 1100, y: 880, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'Офис',      name: 'Офис',      icon: '🏢', x: 1320, y: 880, w: bSize, h: bSize, isNPC: false }},
                
                {{ id: 'Агентство', name: 'Агентство', icon: '🏘️', x: 880, y: 1100, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'Казино',    name: 'Казино',    icon: '🎰', x: 1100, y: 1100, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'Мебельный', name: 'Мебельный', icon: '🛋️', x: 1320, y: 1100, w: bSize, h: bSize, isNPC: false }},
                
                {{ id: 'Карьера',   name: 'Карьера',   icon: '📈', x: 880, y: 1320, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'Магазин',   name: 'Магазин',   icon: '🏪', x: 1100, y: 1320, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'Дом',       name: 'Дом',       icon: '🏠', x: 1320, y: 1320, w: bSize, h: bSize, isNPC: false }},
                
                {{ id: 'Бизнесмен', name: 'Бизнесмен', icon: '🤵', x: 1175, y: 1260, w: 50, h: 50, isNPC: true }},

                // ЗАПАДНЫЙ
                {{ id: 'Дом', name: 'Жилой дом', icon: '🏠', x: 250, y: 1000, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'ТЦ',  name: 'Торговый центр', icon: '🏬', x: 400, y: 1300, w: bSize, h: bSize, isNPC: false }},
                
                // ВОСТОЧНЫЙ
                {{ id: 'Дом', name: 'Жилой дом', icon: '🏠', x: 2000, y: 1000, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'ТЦ',  name: 'Торговый центр', icon: '🏬', x: 1850, y: 1300, w: bSize, h: bSize, isNPC: false }},
                
                // СЕВЕРНЫЙ
                {{ id: 'Дом', name: 'Жилой дом', icon: '🏠', x: 1000, y: 250, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'ТЦ',  name: 'Торговый центр', icon: '🏬', x: 1300, y: 400, w: bSize, h: bSize, isNPC: false }},
                
                // ЮЖНЫЙ
                {{ id: 'Дом', name: 'Жилой дом', icon: '🏠', x: 1000, y: 2000, w: bSize, h: bSize, isNPC: false }},
                {{ id: 'ТЦ',  name: 'Торговый центр', icon: '🏬', x: 1300, y: 1850, w: bSize, h: bSize, isNPC: false }}
            ];
        }}

        function resize() {{
            canvas.width = canvas.parentElement.clientWidth;
            canvas.height = canvas.parentElement.clientHeight;
            initMap();
        }}
        window.addEventListener('resize', resize); resize();

        function isOnRoad(x, y) {{
            let onV1 = (x > 800 - 60 && x < 800 + 60);
            let onV2 = (x > 1600 - 60 && x < 1600 + 60);
            let onH1 = (y > 800 - 60 && y < 800 + 60);
            let onH2 = (y > 1600 - 60 && y < 1600 + 60);
            return onV1 || onV2 || onH1 || onH2;
        }}

        let grassPatches = [];
        let grassDetails = [];
        for(let i=0; i<100; i++) grassPatches.push({{x: Math.random()*WORLD_W, y: Math.random()*WORLD_H, w: Math.random()*40+20, h: Math.random()*40+20}});
        for(let i=0; i<400; i++) grassDetails.push({{x: Math.random()*WORLD_W, y: Math.random()*WORLD_H, type: Math.random()>0.85?'flower':(Math.random()>0.5?'leaf':'grass')}});

        let trees = [];
        for(let i=0; i<100; i++) {{
            let tx, ty;
            do {{
                tx = Math.random() * WORLD_W;
                ty = Math.random() * WORLD_H;
            }} while (isOnRoad(tx, ty));
            trees.push({{x: tx, y: ty}});
        }}
        
        let cars = [
            {{x: 0, y: 800 - 30, speed: 2, w: 40, h: 20, color:'#ef4444', dir: 1}},
            {{x: WORLD_W, y: 800 + 10, speed: 3, w: 40, h: 20, color:'#3b82f6', dir: -1}},
            {{x: 800 - 30, y: 0, speed: 2, w: 20, h: 40, color:'#22c55e', dir: 1, isVertical: true}},
            {{x: 1600 + 10, y: WORLD_H, speed: 3, w: 20, h: 40, color:'#eab308', dir: -1, isVertical: true}}
        ];

        let npcs = [];
        for(let i=0; i<10; i++) {{
            let nx, ny;
            do {{
                nx = Math.random()*WORLD_W; ny = Math.random()*WORLD_H;
            }} while (isOnRoad(nx, ny));
            npcs.push({{x: nx, y: ny, speed: 1, dirX: Math.random()>0.5?1:-1, dirY: Math.random()>0.5?1:-1}});
        }}

        let player = {{ x: cx, y: cy + 100, size: 24, speed: 2.2, dir: 1, frame: 0 }};
        let savedPos = localStorage.getItem('globalPlayerPos');
        if (savedPos) {{
            let p = JSON.parse(savedPos);
            if (p.x > 10 && p.x < WORLD_W - 10 && p.y > 10 && p.y < WORLD_H - 10) {{
                player.x = p.x; player.y = p.y;
            }}
        }}
        
        if (checkCollision(player.x, player.y)) {{
            player.x = cx; player.y = cy + 100;
        }}

        let joy = {{ active: false, startX: 0, startY: 0, curX: 0, curY: 0, radius: 40 }};
        let moveX = 0; let moveY = 0;
        let nearbyTarget = null;
        let transitioning = false;

        let keys = {{}};
        window.addEventListener('keydown', e => {{
            keys[e.key.toLowerCase()] = true;
            if(['arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'w', 'a', 's', 'd'].includes(e.key.toLowerCase())) {{
                e.preventDefault();
            }}
            
            if (e.code === 'Space' || e.key.toLowerCase() === 'e' || e.key.toLowerCase() === 'у') {{
                if (nearbyTarget && actionBtn.style.display === 'block') {{
                    e.preventDefault();
                    actionBtn.click();
                }}
            }}
            if (e.key.toLowerCase() === 't' || e.key.toLowerCase() === 'е') {{
                togglePhone();
            }}
        }});
        window.addEventListener('keyup', e => {{
            keys[e.key.toLowerCase()] = false;
        }});

        function savePosAndTime() {{
            localStorage.setItem('globalPlayerPos', JSON.stringify({{x: player.x, y: player.y}}));
            localStorage.setItem('gameTime', gameTime);
            localStorage.setItem('gameDay', gameDay);
        }}

        canvas.addEventListener('touchstart', e => {{
            if(isPaused || transitioning) return;
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const touch = e.touches[0];
            const tx = touch.clientX - rect.left; const ty = touch.clientY - rect.top;
            
            if (controlMode === 'fixed') {{
                if (tx < rect.width / 2 && ty > rect.height / 2) {{
                    joy.active = true; joy.startX = tx; joy.startY = ty; joy.curX = tx; joy.curY = ty;
                }}
            }} else {{
                joy.active = true; joy.startX = tx; joy.startY = ty; joy.curX = tx; joy.curY = ty;
            }}
        }});
        canvas.addEventListener('touchmove', e => {{
            if(isPaused || !joy.active) return;
            e.preventDefault();
            const rect = canvas.getBoundingClientRect();
            const touch = e.touches[0];
            joy.curX = touch.clientX - rect.left; joy.curY = touch.clientY - rect.top;
        }});
        canvas.addEventListener('touchend', e => {{ if(isPaused) return; e.preventDefault(); joy.active = false; moveX = 0; moveY = 0; }});
        
        canvas.addEventListener('mousedown', e => {{
            if(isPaused || transitioning) return;
            const rect = canvas.getBoundingClientRect(); const tx = e.clientX - rect.left; const ty = e.clientY - rect.top;
            if (controlMode === 'fixed') {{
                if (tx < rect.width / 2 && ty > rect.height / 2) {{ joy.active = true; joy.startX = tx; joy.startY = ty; joy.curX = tx; joy.curY = ty; }}
            }} else {{
                joy.active = true; joy.startX = tx; joy.startY = ty; joy.curX = tx; joy.curY = ty;
            }}
        }});
        canvas.addEventListener('mousemove', e => {{ if(joy.active && !isPaused) {{ const rect = canvas.getBoundingClientRect(); joy.curX = e.clientX - rect.left; joy.curY = e.clientY - rect.top; }} }});
        canvas.addEventListener('mouseup', () => {{ joy.active = false; moveX = 0; moveY = 0; }});

        function checkCollision(nx, ny) {{
            for (let b of buildings) {{
                if (b.isNPC) continue;
                // Отступ 10 пикселей для плавности
                if (nx > b.x - 10 && nx < b.x + b.w + 10 && ny > b.y - 10 && ny < b.y + b.h + 10) return true;
            }}
            return false;
        }}

        let lastTime = 0;
        const fpsInterval = 1000 / 60;

        function gameLoop(time) {{
            requestAnimationFrame(gameLoop);
            if (time - lastTime < fpsInterval) return;
            lastTime = time;

            if(!isPaused && !transitioning) {{
                let oldTime = gameTime;
                gameTime += 0.005; 
                if (oldTime < 6 && gameTime >= 6) {{ gameDay++; localStorage.setItem('gameDay', gameDay); }}
                if (gameTime >= 24) gameTime = 0;
                if(Math.random() < 0.05) localStorage.setItem('gameTime', gameTime); 
                
                if (joy.active) {{
                    let dx = joy.curX - joy.startX; let dy = joy.curY - joy.startY;
                    let dist = Math.hypot(dx, dy);
                    if (dist > 0) {{
                        let maxDist = 30; if (dist > maxDist) {{ dx = (dx/dist)*maxDist; dy = (dy/dist)*maxDist; }}
                        moveX = dx / maxDist; moveY = dy / maxDist;
                    }}
                }} else {{
                    moveX = 0; moveY = 0;
                    if (keys['w'] || keys['arrowup'] || keys['ц']) moveY = -1;
                    if (keys['s'] || keys['arrowdown'] || keys['ы']) moveY = 1;
                    if (keys['a'] || keys['arrowleft'] || keys['ф']) moveX = -1;
                    if (keys['d'] || keys['arrowright'] || keys['в']) moveX = 1;
                    
                    if (moveX !== 0 && moveY !== 0) {{
                        moveX *= 0.707;
                        moveY *= 0.707;
                    }}
                }}
                
                if (moveX !== 0 || moveY !== 0) {{
                    let nx = player.x + moveX * player.speed; let ny = player.y + moveY * player.speed;
                    if (!checkCollision(nx, player.y)) player.x = nx;
                    if (!checkCollision(player.x, ny)) player.y = ny;
                    player.frame += 0.15; if (moveX > 0) player.dir = 1; else if (moveX < 0) player.dir = -1;
                }}

                if (player.x < 20) player.x = 20;
                if (player.x > WORLD_W - 20) player.x = WORLD_W - 20;
                if (player.y < 20) player.y = 20;
                if (player.y > WORLD_H - 20) player.y = WORLD_H - 20;

                let newDistrict = 'Пустошь';
                if (player.x >= 850 && player.x <= 1550 && player.y >= 850 && player.y <= 1550) newDistrict = 'Центральный';
                else if (player.x < 800 && player.y >= 800 && player.y <= 1600) newDistrict = 'Западный';
                else if (player.x > 1600 && player.y >= 800 && player.y <= 1600) newDistrict = 'Восточный';
                else if (player.x >= 800 && player.x <= 1600 && player.y < 800) newDistrict = 'Северный';
                else if (player.x >= 800 && player.x <= 1600 && player.y > 1600) newDistrict = 'Южный';
                
                if (newDistrict !== currentDistrict) {{
                    currentDistrict = newDistrict;
                    document.getElementById('map-current-district').innerText = currentDistrict;
                    fetch('/update_district', {{method:'POST', headers:{{'Content-Type':'application/x-www-form-urlencoded'}}, body:'district='+currentDistrict}});
                }}

                cars.forEach(c => {{
                    if(c.isVertical) {{
                        c.y += c.speed * c.dir;
                        if (c.dir === 1 && c.y > WORLD_H) c.y = -c.h;
                        if (c.dir === -1 && c.y < -c.h) c.y = WORLD_H;
                    }} else {{
                        c.x += c.speed * c.dir;
                        if (c.dir === 1 && c.x > WORLD_W) c.x = -c.w;
                        if (c.dir === -1 && c.x < -c.w) c.x = WORLD_W;
                    }}
                }});

                npcs.forEach(n => {{
                    n.x += n.speed * n.dirX;
                    n.y += n.speed * n.dirY;
                    if (n.x < 0 || n.x > WORLD_W) n.dirX *= -1;
                    if (n.y < 0 || n.y > WORLD_H) n.dirY *= -1;
                }});

                nearbyTarget = null;
                for (let b of buildings) {{
                    let b_cx = b.x + b.w/2; let b_cy = b.y + b.h/2;
                    let dist = b.isNPC ? 60 : 100; // Чуть увеличили радиус взаимодействия для больших зданий
                    if (Math.hypot(player.x - b_cx, player.y - b_cy) < dist) nearbyTarget = b;
                }}
                
                if (nearbyTarget) {{
                    actionBtn.style.display = 'block';
                    if (courierStatus === 'delivering' && currentDistrict === courierTarget && (nearbyTarget.id === 'Дом' || nearbyTarget.id === 'ТЦ')) {{
                        actionBtn.innerText = '📦 Доставить заказ';
                        actionBtn.onclick = () => {{ savePosAndTime(); window.location.href = '/deliver_courier?day=' + gameDay; }};
                    }} else if (nearbyTarget.isNPC) {{
                        actionBtn.innerText = 'Поговорить';
                        actionBtn.onclick = () => {{ savePosAndTime(); window.location.href = '/talk_npc?day=' + gameDay; }};
                    }} else {{
                        actionBtn.innerText = 'Войти в ' + nearbyTarget.name;
                        actionBtn.onclick = () => {{ savePosAndTime(); window.location.href = '/building/' + encodeURIComponent(nearbyTarget.id) + '?day=' + gameDay; }};
                    }}
                }} else {{
                    actionBtn.style.display = 'none';
                }}
            }}
            draw(); 
        }}

        function drawBuilding(b) {{
            const img = buildingImages[b.id];
            if (img) {{
                ctx.drawImage(img, b.x, b.y, b.w, b.h);
            }} else {{
                ctx.fillStyle = '#334155';
                ctx.fillRect(b.x, b.y, b.w, b.h);
                ctx.font = '48px Arial'; // Увеличили шрифт заглушки
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(b.icon, b.x + b.w / 2, b.y + b.h / 2);
                ctx.textBaseline = 'alphabetic';
            }}
            if (b.isNPC && questState < 2) {{
                ctx.fillStyle = '#eab308';
                ctx.font = 'bold 30px Arial'; // Увеличили восклицательный знак
                ctx.textAlign = 'center';
                ctx.fillText('!', b.x + b.w / 2, b.y - 10);
            }}
        }}

        function draw() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            ctx.fillStyle = '#064e3b';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            ctx.save();
            ctx.translate(canvas.width / 2 - player.x, canvas.height / 2 - player.y);

            ctx.fillStyle = '#4ade80';
            ctx.fillRect(800, 800, 800, 800);

            ctx.fillStyle = '#86efac';
            ctx.fillRect(800, 0, 800, 800);
            ctx.fillRect(0, 800, 800, 800);
            ctx.fillRect(1600, 800, 800, 800);
            ctx.fillRect(800, 1600, 800, 800);
            
            grassPatches.forEach(p => {{
                if (p.x > 800 && p.x < 1600 && p.y > 800 && p.y < 1600) ctx.fillStyle = '#22c55e';
                else ctx.fillStyle = '#4ade80';
                ctx.fillRect(p.x, p.y, p.w, p.h);
            }});
            
            grassDetails.forEach(g => {{
                if(g.type === 'grass') {{ ctx.fillStyle = '#16a34a'; ctx.fillRect(g.x, g.y, 2, 4); }} 
                else if(g.type === 'flower') {{ ctx.fillStyle = Math.random()>0.5?'#fcd34d':'#f472b6'; ctx.fillRect(g.x, g.y, 4, 4); ctx.fillStyle = '#fff'; ctx.fillRect(g.x+1, g.y+1, 2, 2); }} 
                else {{ ctx.fillStyle = '#854d0e'; ctx.fillRect(g.x, g.y, 3, 2); }}
            }});
            
            ctx.fillStyle = '#94a3b8'; 
            ctx.fillRect(0, 800 - 60, WORLD_W, 120);
            ctx.fillRect(0, 1600 - 60, WORLD_W, 120); 
            ctx.fillRect(800 - 60, 0, 120, WORLD_H);
            ctx.fillRect(1600 - 60, 0, 120, WORLD_H);
            
            ctx.fillStyle = '#334155'; 
            ctx.fillRect(0, 800 - 50, WORLD_W, 100);
            ctx.fillRect(0, 1600 - 50, WORLD_W, 100);
            ctx.fillRect(800 - 50, 0, 100, WORLD_H);
            ctx.fillRect(1600 - 50, 0, 100, WORLD_H);
            
            ctx.strokeStyle = '#fcd34d'; ctx.setLineDash([20, 20]); ctx.lineWidth = 4;
            ctx.beginPath(); ctx.moveTo(0, 800); ctx.lineTo(WORLD_W, 800); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(0, 1600); ctx.lineTo(WORLD_W, 1600); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(800, 0); ctx.lineTo(800, WORLD_H); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(1600, 0); ctx.lineTo(1600, WORLD_H); ctx.stroke();
            ctx.setLineDash([]);

            trees.forEach(t => {{
                ctx.fillStyle = '#78350f'; ctx.fillRect(t.x-4, t.y, 8, 16);
                ctx.fillStyle = '#15803d'; ctx.fillRect(t.x-16, t.y-16, 32, 24);
                ctx.fillStyle = '#22c55e'; ctx.fillRect(t.x-12, t.y-20, 24, 16);
                ctx.fillStyle = '#86efac'; ctx.fillRect(t.x-8, t.y-24, 12, 8);
            }});

            buildings.forEach(b => {{
                drawBuilding(b);
            }});

            cars.forEach(c => {{ 
                ctx.fillStyle = c.color; 
                ctx.fillRect(c.x, c.y, c.w, c.h); 
                ctx.fillStyle = '#38bdf8'; 
                if(c.isVertical) ctx.fillRect(c.x+2, c.dir===1?c.y+c.h-12:c.y+2, 6, 8);
                else ctx.fillRect(c.dir===1?c.x+c.w-12:c.x+2, c.y+2, 8, 6); 
            }});
            
            npcs.forEach(n => {{ ctx.fillStyle = '#ef4444'; ctx.fillRect(n.x-3, n.y, 6, 10); ctx.fillStyle = '#fcd34d'; ctx.fillRect(n.x-2, n.y-6, 4, 6); }});

            ctx.save(); ctx.translate(player.x, player.y); ctx.scale(player.dir, 1);
            let legOffset = Math.sin(player.frame) * 3;
            ctx.fillStyle = '#1e293b'; ctx.fillRect(-6, 14 + legOffset, 4, 6); ctx.fillRect(2, 14 - legOffset, 4, 6);
            ctx.fillStyle = '#3b82f6'; ctx.fillRect(-8, -2, 16, 16);
            ctx.fillStyle = '#2563eb'; ctx.fillRect(-10, 0, 2, 10); ctx.fillRect(8, 0, 2, 10);
            ctx.fillStyle = '#fcd34d'; ctx.fillRect(-6, -14, 12, 12);
            ctx.fillStyle = '#78350f'; ctx.fillRect(-6, -16, 12, 4); ctx.fillRect(-8, -14, 2, 6);
            ctx.fillStyle = '#000'; ctx.fillRect(2, -10, 2, 2); ctx.fillRect(-2, -10, 1, 2); 
            ctx.restore();

            ctx.restore();

            if (joy.active) {{
                ctx.beginPath(); ctx.arc(joy.startX, joy.startY, joy.radius, 0, Math.PI*2); ctx.fillStyle = 'rgba(15,23,42,0.5)'; ctx.fill();
                let dx = joy.curX - joy.startX; let dy = joy.curY - joy.startY;
                let dist = Math.hypot(dx, dy); if (dist > joy.radius) {{ dx = (dx/dist)*joy.radius; dy = (dy/dist)*joy.radius; }}
                ctx.beginPath(); ctx.arc(joy.startX + dx, joy.startY + dy, 20, 0, Math.PI*2); ctx.fillStyle = 'rgba(56,189,248,0.8)'; ctx.fill();
            }} else {{
                if (controlMode === 'fixed') {{
                    ctx.beginPath(); ctx.arc(60, canvas.height - 60, 30, 0, Math.PI*2); ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.lineWidth = 2; ctx.stroke();
                    ctx.fillStyle = 'rgba(255,255,255,0.6)'; ctx.font = '12px Arial'; ctx.textAlign = 'center'; ctx.fillText('Джойстик', 60, canvas.height - 56);
                }}
            }}

            let darkness = 0;
            if (gameTime > 20 || gameTime < 6) darkness = 0.6; 
            else if (gameTime > 18) darkness = (gameTime - 18) / 2 * 0.6; 
            else if (gameTime < 8) darkness = (8 - gameTime) / 2 * 0.6; 
            if (darkness > 0) {{ ctx.fillStyle = 'rgba(0, 0, 40, ' + darkness + ')'; ctx.fillRect(0, 0, canvas.width, canvas.height); }}

            let h = Math.floor(gameTime); let m = Math.floor((gameTime - h) * 60);
            let timeStr = (h<10?'0':'')+h + ':' + (m<10?'0':'')+m;
            ctx.fillStyle = 'rgba(15,23,42,0.8)'; ctx.fillRect(canvas.width - 70, 10, 60, 25);
            ctx.fillStyle = '#38bdf8'; ctx.font = 'bold 14px Arial'; ctx.textAlign = 'center'; ctx.fillText(timeStr, canvas.width - 40, 28);
        }}
        requestAnimationFrame(gameLoop);
    </script>
    '''
    return render(body, 'Город', '🗺️ Город', 'home')
@app.route('/penalize')
@login_required
def penalize():
    u = get_user(session['uid'])
    user_jobs = u['jobs'].split(',') if u['jobs'] else []
    if user_jobs:
        penalty = sum(JOBS[j]['penalty'] for j in user_jobs if j in JOBS)
        new_money = max(0, u['money'] - penalty)
        with db() as c:
            c.execute('UPDATE users SET money=?, jobs="" WHERE id=?', (new_money, u['id']))
        flash(f'Ты прогулял работу! Тебя уволили со всех работ и выписали штраф {penalty} ₽.', 'error')
    return redirect(url_for('index'))

# ============ NPC / КВЕСТЫ / КУРЬЕР ============

@app.route('/talk_npc')
@login_required
def talk_npc():
    u = get_user(session['uid'])
    game_day = int(request.args.get('day', 1))
    if u['quest_day'] < game_day:
        with db() as c:
            c.execute('UPDATE users SET quest_state=0, quest_day=? WHERE id=?', (game_day, u['id']))
        u = get_user(session['uid'])
    q_state = u['quest_state'] or 0
    if q_state == 0:
        quest = random.choice(QUEST_POOL)
        with db() as c:
            c.execute('UPDATE users SET quest_state=1, quest_item=?, quest_reward=?, quest_day=? WHERE id=?',
                      (quest['item'], quest['reward'], game_day, u['id']))
        u = get_user(session['uid'])
    if u['quest_state'] == 1:
        with db() as c:
            has_item = c.execute("SELECT * FROM inventory WHERE user_id=? AND item=?", (u['id'], u['quest_item'])).fetchone()
        if has_item:
            body = f'''<div class="card" style="text-align:center;"><h1 style="font-size:3rem; margin-bottom:10px;">🤵</h1><h2>Бизнесмен</h2><p style="margin:10px 0; color:#94a3b8;">"О, {u['quest_item']}! Ты спас меня!"</p><form method="POST" action="/complete_quest"><input type="hidden" name="inv_id" value="{has_item['id']}"><button class="btn green" type="submit">Отдать (Получить {u['quest_reward']} ₽)</button></form></div>'''
        else:
            body = f'''<div class="card" style="text-align:center;"><h1 style="font-size:3rem; margin-bottom:10px;">🤵</h1><h2>Бизнесмен</h2><p style="margin:10px 0; color:#94a3b8;">"Ты принес {u['quest_item']}? Я жду. Загляни в магазин!"</p><a href="/" class="btn gray">Я скоро</a></div>'''
    else:
        body = f'''<div class="card" style="text-align:center;"><h1 style="font-size:3rem; margin-bottom:10px;">🤵</h1><h2>Бизнесмен</h2><p style="margin:10px 0; color:#94a3b8;">"Спасибо за помощь! Приходи после 6 утра, будет новое задание."</p><a href="/" class="btn gray">Уйти</a></div>'''
    return render(body, 'Разговор', '💬 Разговор', 'office')

@app.route('/complete_quest', methods=['POST'])
@login_required
def complete_quest():
    u = get_user(session['uid'])
    inv_id = request.form.get('inv_id')
    with db() as c:
        c.execute('DELETE FROM inventory WHERE id=? AND user_id=?', (inv_id, session['uid']))
        c.execute('UPDATE users SET money=money+?, quest_state=2 WHERE id=?', (u['quest_reward'], session['uid']))
    flash(f'Задание выполнено! Получено {u["quest_reward"]} ₽.', 'success')
    return redirect(url_for('index'))

@app.route('/accept_courier', methods=['POST'])
@login_required
def accept_courier():
    u = get_user(session['uid'])
    districts = ['Северный', 'Южный', 'Западный', 'Восточный']
    target = random.choice(districts)
    address = random.choice(COURIER_ADDRESSES)
    reward = random.randint(2000, 5000)
    with db() as c:
        c.execute('UPDATE users SET courier_status="delivering", courier_address=?, courier_target=?, courier_reward=? WHERE id=?',
                  (address, target, reward, u['id']))
    flash(f'Заказ принят! Доставь посылку в {target} район на {address}.', 'success')
    return redirect(url_for('index'))

@app.route('/deliver_courier')
@login_required
def deliver_courier():
    u = get_user(session['uid'])
    if u['courier_status'] == 'delivering' and u['current_district'] == u['courier_target']:
        with db() as c:
            c.execute('UPDATE users SET money=money+?, courier_status="", last_worked_day=? WHERE id=?',
                      (u['courier_reward'], int(request.args.get('day', 1)), u['id']))
        flash(f'Заказ доставлен! Получено {u["courier_reward"]} ₽ чаевых.', 'success')
    return redirect(url_for('index'))

# ============ ЗДАНИЯ ============

@app.route('/building/<b_name>')
@login_required
def building(b_name):
    u = get_user(session['uid'])
    game_day = int(request.args.get('day', 1))
    user_jobs = u['jobs'].split(',') if u['jobs'] else []

    if b_name == 'Магазин':
        death_remaining = get_death_remaining(u)
        if u['death_started_at'] and death_remaining <= 0:
            return redirect(url_for('die'))
        return render_template('shop.html', money=u['money'], death_remaining=death_remaining)

    if b_name in ['ТЦ', 'Жилой дом']:
        return render('<div class="card" style="text-align:center;"><h2>🏢 Здание</h2><p style="margin:20px 0;">Здесь пока пусто. Но сюда можно доставлять заказы!</p><a href="/" class="btn gray">На улицу</a></div>', 'Здание', '🏢 Здание', 'office')

    if b_name == 'Карьера':
        next_status = STATUSES[min(STATUSES.index(u['status'])+1, len(STATUSES)-1)]
        upgrade_btn = ""
        if u['status'] != 'Президент':
            cost = UPGRADE_COST[next_status]
            if u['money'] >= cost:
                upgrade_btn = f'<form method="POST" action="/upgrade"><button class="btn green" style="margin-bottom:20px;" type="submit">Повысить до "{next_status}" ({cost:,.0f} ₽)</button></form>'
            else:
                upgrade_btn = f'<button class="btn gray" style="margin-bottom:20px;" disabled>Нужно {cost:,.0f} ₽ для "{next_status}"</button>'
        else:
            upgrade_btn = '<p style="color:#22c55e; margin-bottom:20px;">Ты уже достиг максимального статуса!</p>'
        body = f'''<div class="card"><h2 style="margin-top:0">📈 Центр Карьеры</h2><p style="font-size:14px; color:#94a3b8; margin-bottom:15px;">Твой текущий статус: <b>{u['status']}</b>.</p>{upgrade_btn}</div><a href="/" class="btn gray">На улицу</a>'''
        return render(body, 'Карьера', '📈 Карьера', 'office')

    if b_name == 'Агентство':
        if u['has_apartment']:
            return render('<div class="card" style="text-align:center;"><h2>🏘️ Агентство</h2><p style="margin:20px 0; color:#94a3b8;">"У вас уже есть квартира!"</p><a href="/" class="btn gray">На улицу</a></div>', 'Агентство', '🏘️ Агентство', 'office')
        body = f'''<div class="balance"><div class="l">Кошелек</div><div class="v">{u['money']:,.0f} ₽</div></div><div class="card" style="text-align:center;"><h2 style="margin-top:0">🏘️ Купить квартиру</h2><p style="margin:10px 0; color:#94a3b8;">Маленькая студия в центре города.</p><div style="font-size:2rem; font-weight:bold; color:#eab308; margin:20px 0;">250 000 ₽</div><form method="POST" action="/buy_apt"><button class="btn green" type="submit">Купить квартиру</button></form></div>'''
        return render(body, 'Агентство', '🏘️ Агентство', 'office')

    if b_name == 'Мебельный':
        items_html = ""
        for item, price in FURNITURE.items():
            items_html += f'''<div class="txn" style="flex-direction:column; align-items:flex-start; gap:10px;"><div style="display:flex; justify-content:space-between; width:100%;"><b>{item}</b> <span style="color:#22c55e;">{price} ₽</span></div><div style="display:flex; gap:5px; width:100%;"><form method="POST" action="/buy_furn" style="flex:1;"><input type="hidden" name="item" value="{item}"><input type="hidden" name="delivery" value="carry"><button class="btn blue" style="padding:8px; min-height:32px; font-size:.8rem;" type="submit">Сам понесу</button></form><form method="POST" action="/buy_furn" style="flex:1;"><input type="hidden" name="item" value="{item}"><input type="hidden" name="delivery" value="hire"><button class="btn green" style="padding:8px; min-height:32px; font-size:.8rem;" type="submit">Грузчики (+1000₽)</button></form></div></div>'''
        return render(f'<div class="balance"><div class="l">Кошелек</div><div class="v">{u["money"]:,.0f} ₽</div></div><div class="card"><h2 style="margin-top:0">🛋️ Мебельный</h2>{items_html}</div>', 'Мебельный', '🛋️ Мебельный', 'shop')

    if b_name == 'Дом':
        if not u['has_apartment']:
            return render('<div class="card" style="text-align:center;"><h2>🏠 Мой дом</h2><p style="margin:20px 0; color:#ef4444;">У вас пока нет жилья.</p><a href="/" class="btn gray">На улицу</a></div>', 'Дом', '🏠 Мой дом', 'office')
        
        death_remaining = get_death_remaining(u)
        if u['death_started_at'] and death_remaining <= 0:
            return redirect(url_for('die'))
            
        with db() as c:
            carried_furn = c.execute("SELECT * FROM inventory WHERE user_id=?", (u['id'],)).fetchall()
        
        carried_list = []
        for item in carried_furn:
            if item['item'] in FURNITURE:
                carried_list.append({'id': item['id'], 'item': item['item'], 'icon': '📦'})
        
        return render_template('home.html', furniture=u['apt_furniture'], carried=carried_list, death_remaining=death_remaining)

    if b_name == 'Казино':
        current_num = random.randint(1, 100)
        session['casino_num'] = current_num
        body = f'''<div class="balance"><div class="l">Кошелек</div><div class="v">{u['money']:,.0f} ₽</div></div><div class="card" style="text-align:center;"><h2 style="margin-top:0">🎰 Больше / Меньше</h2><div class="casino-num">{current_num}</div><form method="POST" action="/play_casino"><div class="fg"><label>Ставка (₽)</label><input class="fc" type="number" name="bet" min="1" value="100" required style="text-align:center; font-size:1.5rem; font-weight:bold; color:#eab308;"></div><div style="font-size:12px; color:#94a3b8; margin-bottom:10px;">Комиссия казино: 10%</div><div style="display:flex; gap:10px;"><button class="btn blue" type="submit" name="guess" value="lower">⬇️ Меньше</button><button class="btn red" type="submit" name="guess" value="higher">⬆️ Больше</button></div></form></div>'''
        return render(body, 'Казино', '🎰 Казино', 'casino')

    if 'Курьер' in user_jobs and u['current_district'] == 'Центральный' and b_name == 'Офис':
        if u['courier_status'] == 'delivering':
            body = f'''<div class="card" style="text-align:center;"><h2 style="color:#f59e0b;">🚴 У тебя уже есть активный заказ!</h2><p style="margin:20px 0;">Доставь его по адресу: <b>{u['courier_address']}</b> в район <b>{u['courier_target']}</b>.</p><p style="color:#94a3b8; font-size:14px;">Выйди на улицу и иди к краю карты, чтобы сменить район.</p><a href="/" class="btn gray">На улицу</a></div>'''
        else:
            body = f'''<div class="card" style="text-align:center;"><h2 style="color:#f59e0b;">🚴 Взять заказ</h2><p style="margin:20px 0; color:#94a3b8;">Доставь посылку, и получи хорошие чаевые!</p><form method="POST" action="/accept_courier"><button class="btn green" type="submit">Получить адрес</button></form></div>'''
        return render(body, 'Курьер', '📦 Курьер', 'office')

    jobs_html = ""
    for job_name, data in JOBS.items():
        if data['loc'] == b_name and STATUSES.index(u['status']) >= STATUSES.index(data['req']):
            if job_name in user_jobs:
                work_link = f'/work/{job_name}?day={game_day}' if job_name == 'Программист' else f'/work/{job_name}?day={game_day}'
                btn_text = 'Работать' if job_name == 'Программист' else f'Работать (+{data["salary"]} ₽)'
                form_method = 'GET' if job_name == 'Программист' else 'POST'
                
                jobs_html += f'''<div class="card" style="margin-bottom:10px;"><div style="display:flex; justify-content:space-between; margin-bottom:10px;"><div><div style="font-weight:700; color:#22c55e;">{data['icon']} {job_name}</div><div style="font-size:.8rem;color:#94a3b8">Зарплата: {data['salary']} ₽</div></div><div class="tag" style="background:#22c55e; color:white;">Устроен</div></div><form method="{form_method}" action="{work_link}" style="margin-bottom:8px;"><button class="btn green" style="padding:10px; min-height:36px;" type="submit">{btn_text}</button></form><div style="display:flex; gap:5px;"><button class="btn yellow" style="padding:8px; min-height:32px; font-size:.8rem;" onclick="showResignModal('{job_name}')">Написать заявление</button><button class="btn red" style="padding:8px; min-height:32px; font-size:.8rem;" onclick="runAway('{job_name}')">Сбежать ({data['penalty']} ₽)</button></div></div>'''
            else:
                jobs_html += f'''<div class="txn" style="flex-direction:column; align-items:flex-start; gap:10px;"><div style="display:flex; justify-content:space-between; width:100%;"><div><div style="font-weight:700">{data['icon']} {job_name}</div><div style="font-size:.8rem;color:#94a3b8">{data['desc']}</div></div><div class="tag" style="background:#3b82f6; color:white;">+{data['salary']} ₽</div></div><button class="btn blue" style="width:100%; padding:10px;" onclick="hireJob('{job_name}')">Устроиться</button></div>'''

    body = f'''<div class="card"><h2 style="margin-top:0" id="jobs">{b_name}</h2><p style="font-size:14px; color:#94a3b8; margin-bottom:10px;">Ты можешь работать на нескольких работах одновременно!</p>{jobs_html}</div><a href="/" class="btn gray">На улицу</a><div id="resignModal" class="modal"><div class="modal-content"><h2 style="color:#000; margin-top:0;">Заявление на увольнение</h2><p style="color:#000; margin-bottom:10px;">Прошу уволить меня по собственному желанию.</p><p style="color:#000; margin-bottom:10px;">Я, <b>{u['username']}</b>, работающий на должности <b>{request.form.get('job_name', '')}</b>, прошу освободить меня от занимаемой должности.</p><p style="color:#000; margin-bottom:20px;">Дата: {date.today().isoformat()}</p><p style="color:#000; margin-bottom:5px;">Подпись:</p><canvas id="signatureCanvas" class="signature-canvas"></canvas><div style="display:flex; gap:10px; margin-top:20px;"><button class="btn gray" onclick="closeResignModal()" style="flex:1;">Отмена</button><button class="btn green" onclick="submitResign()" style="flex:1;">Подписать и уволиться</button></div></div></div><script>let currentResignJob='';const sigCanvas=document.getElementById('signatureCanvas');const sigCtx=sigCanvas.getContext('2d');let isDrawing=false;sigCanvas.width=sigCanvas.offsetWidth;sigCanvas.height=sigCanvas.offsetHeight;sigCtx.lineWidth=2;sigCtx.lineCap='round';sigCtx.strokeStyle='#000';sigCanvas.addEventListener('mousedown',startDrawing);sigCanvas.addEventListener('mousemove',draw);sigCanvas.addEventListener('mouseup',stopDrawing);sigCanvas.addEventListener('mouseout',stopDrawing);sigCanvas.addEventListener('touchstart',(e)=>{{e.preventDefault();startDrawing(e.touches[0]);}},{{passive:false}});sigCanvas.addEventListener('touchmove',(e)=>{{e.preventDefault();draw(e.touches[0]);}},{{passive:false}});sigCanvas.addEventListener('touchend',stopDrawing);function startDrawing(e){{isDrawing=true;const rect=sigCanvas.getBoundingClientRect();sigCtx.beginPath();sigCtx.moveTo(e.clientX-rect.left,e.clientY-rect.top);}}function draw(e){{if(!isDrawing)return;const rect=sigCanvas.getBoundingClientRect();sigCtx.lineTo(e.clientX-rect.left,e.clientY-rect.top);sigCtx.stroke();}}function stopDrawing(){{isDrawing=false;}}function showResignModal(jobName){{currentResignJob=jobName;document.getElementById('resignModal').style.display='flex';sigCtx.clearRect(0,0,sigCanvas.width,sigCanvas.height);}}function closeResignModal(){{document.getElementById('resignModal').style.display='none';}}function submitResign(){{fetch('/resign_clean',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'job_name='+encodeURIComponent(currentResignJob)}}).then(()=>{{closeResignModal();location.reload();}});}}function hireJob(jobName){{fetch('/hire',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'job_name='+encodeURIComponent(jobName)}}).then(()=>location.reload());}}function runAway(jobName){{if(confirm('Ты уверен, что хочешь сбежать? Придется заплатить штраф!')){{fetch('/resign_penalty',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'job_name='+encodeURIComponent(jobName)}}).then(()=>location.reload());}}}}</script>'''
    return render(body, b_name, '🏢 ' + b_name, 'office')

# ============ РАБОТА (мини-игры) ============

@app.route('/work/<job_name>', methods=['GET', 'POST'])
@login_required
def work_game(job_name):
    if job_name not in JOBS:
        return redirect(url_for('index'))
    u = get_user(session['uid'])
    game_day = int(request.args.get('day', 1))
    
    if job_name == 'Программист':
        diff = request.args.get('diff')
        
        if not diff:
            body = f'''<div class="card" style="text-align:center; padding: 20px;">
                <h2 style="color:#8b5cf6; font-size: 1.5rem;">💻 Выбор сложности</h2>
                <p style="color:#94a3b8; margin-bottom: 20px;">Выбери уровень задач. Чем сложнее, тем выше зарплата!</p>
                <a href="/work/Программист?day={game_day}&diff=easiest" class="btn" style="background:#38bdf8; color:#0f172a; margin-bottom:10px;">Легче некуда (5 000 ₽)</a>
                <a href="/work/Программист?day={game_day}&diff=easy" class="btn" style="background:#22c55e; margin-bottom:10px;">Лёгкое (15 000 ₽)</a>
                <a href="/work/Программист?day={game_day}&diff=medium" class="btn yellow" style="margin-bottom:10px;">Среднее (35 000 ₽)</a>
                <a href="/work/Программист?day={game_day}&diff=hard" class="btn red" style="margin-bottom:10px;">Сложное (80 000 ₽)</a>
                <a href="/work/Программист?day={game_day}&diff=impossible" class="btn" style="background:#000; border: 1px solid #ef4444; margin-bottom:20px; color:white;">Невозможное (200 000 ₽)</a>
                <a href="/building/Офис?day={game_day}#jobs" class="btn gray">Отмена</a>
            </div>'''
            return render(body, 'Работа', '💻 IT-Отдел', 'work')
            
        tasks = {
            'easiest': [
                {'bug': 'HelloWorld("print")', 'fix': 'print("HelloWorld")'},
                {'bug': 'console.log("Привет")', 'fix': 'print("Привет")'},
                {'bug': 'x = 5; y = 10; x + y', 'fix': 'print(x + y)'},
                {'bug': 'print("Hello"', 'fix': 'print("Hello")'}
            ],
            'easy': [
                {'bug': 'if x = 10:', 'fix': 'if x == 10:'},
                {'bug': 'for i in range(5)', 'fix': 'for i in range(5):'},
                {'bug': 'a = 10; b = "5"; print(a + b)', 'fix': 'a = 10; b = "5"; print(a + int(b))'},
                {'bug': 'while x < 5', 'fix': 'while x < 5:'}
            ],
            'medium': [
                {'bug': 'x = [1, 2, 3]; print(x[3])', 'fix': 'x = [1, 2, 3]; print(x[2])'},
                {'bug': 'def add(a, b) return a + b', 'fix': 'def add(a, b): return a + b'},
                {'bug': 'name = "John"; print("Hello " + name)', 'fix': 'name = "John"; print(f"Hello {name}")'},
                {'bug': 'x = 10; if x > 5 print("Yes")', 'fix': 'x = 10; if x > 5: print("Yes")'}
            ],
            'hard': [
                {'bug': 'x = [i for i in range(10) if i % 2 = 0]', 'fix': 'x = [i for i in range(10) if i % 2 == 0]'},
                {'bug': 'try: print(1/0) except: print("Err")', 'fix': 'try: print(1/0) except ZeroDivisionError: print("Err")'},
                {'bug': 'my_list = [1, 2, 3]; my_list.remove(4)', 'fix': 'my_list = [1, 2, 3]; my_list.remove(4) if 4 in my_list else None'},
                {'bug': 'class MyClass: def __init__(self) self.x = 1', 'fix': 'class MyClass: def __init__(self): self.x = 1'}
            ],
            'impossible': [
                {'bug': 'def func(a, b=[]): b.append(a); return b', 'fix': 'def func(a, b=None): b = b or []; b.append(a); return b'},
                {'bug': 'print(0.1 + 0.2 == 0.3)', 'fix': 'print(round(0.1 + 0.2, 1) == 0.3)'},
                {'bug': 'x = 10; y = 20; x = y; y = x', 'fix': 'x = 10; y = 20; x, y = y, x'},
                {'bug': 'def decorator(func): return func()', 'fix': 'def decorator(func): return func'}
            ]
        }
        
        task = random.choice(tasks[diff])
        session['programmer_fix'] = task['fix']
        session['programmer_diff'] = diff
        
        body = f'''<div style="background:#1e1e1e; border: 2px solid #8b5cf6; border-radius: 16px; padding: 20px; text-align:left; font-family: monospace; box-shadow: 0 0 20px rgba(139, 92, 246, 0.3);">
            <h2 style="color:#8b5cf6; margin-top:0; font-family: sans-serif;">💻 Исправь баг</h2>
            <p style="color:#94a3b8; font-family: sans-serif; font-size: 14px; margin-bottom: 15px;">В коде произошла ошибка. Исправь её, чтобы запустить программу.</p>
            
            <div style="background:#2d2d2d; padding:15px; border-radius:8px; margin-bottom:20px; border-left: 4px solid #ef4444;">
                <span style="color:#6b7280; user-select:none;">1&nbsp;&nbsp;</span>
                <span style="color:#f87171;">{task['bug']}</span>
            </div>
            
            <form method="POST" action="/work/programmer_check?day={game_day}&diff={diff}">
                <div style="display:flex; align-items:center; margin-bottom: 20px;">
                    <span style="color:#6b7280; margin-right:10px; user-select:none;">1&nbsp;&nbsp;</span>
                    <input type="text" name="user_fix" autocomplete="off" placeholder="Введите исправленный код..." style="flex:1; background:transparent; border:none; border-bottom: 2px solid #475569; color:#a7f3d0; font-family:monospace; font-size:16px; padding:8px 5px; outline:none;" autofocus>
                </div>
                <button type="submit" class="btn" style="background:#8b5cf6; color:white; width:100%; margin-bottom:10px; border-radius: 8px;">▶ Запустить</button>
                <a href="/building/Офис?day={game_day}#jobs" class="btn gray" style="font-family: sans-serif; text-align:center; border-radius: 8px;">Отмена</a>
            </form>
        </div>'''
        return render(body, 'Код', '💻 IT-Отдел', 'work')

    if u['hunger'] < 20:
        flash('Ты слишком голоден! Сначала поешь в магазине.', 'error')
        return redirect(url_for('building', b_name=JOBS[job_name]['loc'], day=game_day, _anchor='jobs'))
    if job_name == 'Курьер':
        flash('Курьерам не нужно работать по клику. Просто возьми заказ в офисе!', 'error')
        return redirect(url_for('building', b_name='Офис', day=game_day, _anchor='jobs'))
    
    job = JOBS[job_name]
    game = job['game']
    win_form = f'<form id="winForm" method="POST" action="/work/finish" style="display:none;"><input type="hidden" name="job" value="{job_name}"><input type="hidden" name="game_day" value="{game_day}"><input type="hidden" name="accuracy" id="accuracyInput" value="100"></form>'
    content = ""
    
    if game == 'hold':
        target_score = random.randint(10, 20)
        content = f'''<p>Тапай по полю, чтобы дворник шёл за метлой! (Собери {target_score} листьев)</p><div style="position:relative; width:100%; margin-top:10px; display:flex; justify-content:center;"><canvas id="gameCanvas" width="300" height="300" style="background:#0f172a; border-radius:12px; border:2px solid #334155; touch-action:none; width:100%; max-width:300px;"></canvas><div style="position:absolute; top:10px; left:10px; color:#38bdf8; font-weight:bold; z-index:10; pointer-events:none;">Листья: <span id="score">0</span> / {target_score}</div></div><script>const target={target_score};const canvas=document.getElementById('gameCanvas');const ctx=canvas.getContext('2d');let score=0;let player={{x:150,y:150,size:24,speed:3,dir:1,frame:0}};let leaves=[];for(let i=0;i<{target_score};i++)leaves.push({{x:Math.random()*260+20,y:Math.random()*260+20,active:true}});let joy={{active:false,startX:0,startY:0,curX:0,curY:0,radius:40}};let moveX=0;let moveY=0;canvas.addEventListener('touchstart',e=>{{e.preventDefault();const rect=canvas.getBoundingClientRect();const tx=(e.touches[0].clientX-rect.left)*(canvas.width/rect.width);const ty=(e.touches[0].clientY-rect.top)*(canvas.height/rect.height);if(tx<120&&ty>180){{joy.active=true;joy.startX=tx;joy.startY=ty;joy.curX=tx;joy.curY=ty;}}}});canvas.addEventListener('touchmove',e=>{{e.preventDefault();if(!joy.active)return;const rect=canvas.getBoundingClientRect();joy.curX=(e.touches[0].clientX-rect.left)*(canvas.width/rect.width);joy.curY=(e.touches[0].clientY-rect.top)*(canvas.height/rect.height);}});canvas.addEventListener('touchend',e=>{{e.preventDefault();joy.active=false;moveX=0;moveY=0;}});function gameLoop(){{if(score>=target)return;if(joy.active){{let dx=joy.curX-joy.startX;let dy=joy.curY-joy.startY;let dist=Math.hypot(dx,dy);if(dist>0){{let maxDist=30;if(dist>maxDist){{dx=(dx/dist)*maxDist;dy=(dy/dist)*maxDist;}}moveX=dx/maxDist;moveY=dy/maxDist;}}}}if(moveX!==0||moveY!==0){{player.x+=moveX*player.speed;player.y+=moveY*player.speed;player.frame+=0.2;if(moveX>0)player.dir=1;else if(moveX<0)player.dir=-1;if(player.x<20)player.x=20;if(player.x>280)player.x=280;if(player.y<20)player.y=20;if(player.y>280)player.y=280;leaves.forEach(l=>{{if(l.active&&Math.hypot(player.x-l.x,player.y-l.y)<20){{l.active=false;score++;document.getElementById('score').innerText=score;if(score>=target)document.getElementById('winForm').submit();}}}});}}ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#ea580c';leaves.forEach(l=>{{if(!l.active)return;ctx.beginPath();ctx.arc(l.x,l.y,6,0,Math.PI*2);ctx.fill();}});ctx.save();ctx.translate(player.x,player.y);ctx.scale(player.dir,1);let legOffset=Math.sin(player.frame)*3;ctx.fillStyle='#3b82f6';ctx.fillRect(-8,-2,16,16);ctx.fillStyle='#1e293b';ctx.fillRect(-6,14+legOffset,4,6);ctx.fillRect(2,14-legOffset,4,6);ctx.fillStyle='#fcd34d';ctx.fillRect(-6,-14,12,12);ctx.fillStyle='#ef4444';ctx.fillRect(-8,-16,16,6);ctx.fillStyle='#000';ctx.fillRect(2,-10,2,2);ctx.restore();if(joy.active){{ctx.beginPath();ctx.arc(joy.startX,joy.startY,joy.radius,0,Math.PI*2);ctx.fillStyle='rgba(255,255,255,0.2)';ctx.fill();let dx=joy.curX-joy.startX;let dy=joy.curY-joy.startY;let dist=Math.hypot(dx,dy);if(dist>joy.radius){{dx=(dx/dist)*joy.radius;dy=(dy/dist)*joy.radius;}}ctx.beginPath();ctx.arc(joy.startX+dx,joy.startY+dy,20,0,Math.PI*2);ctx.fillStyle='rgba(56,189,248,0.8)';ctx.fill();}}requestAnimationFrame(gameLoop);}}gameLoop();</script>'''
    elif game == 'clicker':
        clicks_needed = random.randint(25, 45)
        content = f'''<p>Быстро кликни {clicks_needed} раз за 5 секунд!</p><div style="font-size:1.5rem; color:red; font-weight:bold; margin-bottom:10px;" id="timer">5.0</div><button id="clickBtn" class="btn blue" style="font-size:1.2rem; margin-top:20px;">Клик (0/{clicks_needed})</button><script>let clicks=0;let timeLeft=5.0;const goal={clicks_needed};let timer=setInterval(()=>{{timeLeft-=0.1;if(timeLeft<=0){{clearInterval(timer);alert('Время вышло! Смена провалена.');location.href='/';}}document.getElementById('timer').innerText=timeLeft.toFixed(1);}},100);document.getElementById('clickBtn').addEventListener('click',()=>{{clicks++;document.getElementById('clickBtn').innerText='Клик ('+clicks+'/'+goal+')';if(clicks>=goal){{clearInterval(timer);document.getElementById('winForm').submit();}}}});</script>'''
    elif game == 'weld':
        content = f'''<p>Зажми экран и веди сварку точно по шву!</p>
        <div style="position:relative; width:100%; margin-top:10px; display:flex; justify-content:center;">
            <canvas id="weldCanvas" width="300" height="300" style="background:#0f172a; border-radius:12px; border:2px solid #334155; touch-action:none; width:100%; max-width:300px;"></canvas>
        </div>
        <script>
            const canvas = document.getElementById('weldCanvas');
            const ctx = canvas.getContext('2d');
            let points = [];
            let currentIndex = 0;
            let isTouching = false;
            let accuracy = 100;
            let lastX = 0;
            let lastY = 0;

            let startY = 150 + (Math.random() * 100 - 50);
            points.push({{x: 50, y: startY}});
            for(let i=1; i<=10; i++) {{
                let prev = points[points.length-1];
                let nx = prev.x + 20;
                let ny = prev.y + (Math.random() * 120 - 60);
                ny = Math.max(30, Math.min(270, ny));
                points.push({{x: nx, y: ny}});
            }}

            function draw() {{
                ctx.clearRect(0,0,300,300);
                
                ctx.beginPath();
                ctx.moveTo(points[0].x, points[0].y);
                for(let i=1; i<points.length; i++) ctx.lineTo(points[i].x, points[i].y);
                ctx.strokeStyle = '#475569';
                ctx.lineWidth = 22;
                ctx.lineJoin = 'round';
                ctx.stroke();

                if (currentIndex > 0) {{
                    ctx.beginPath();
                    ctx.moveTo(points[0].x, points[0].y);
                    for(let i=1; i<=currentIndex; i++) ctx.lineTo(points[i].x, points[i].y);
                    ctx.strokeStyle = '#38bdf8';
                    ctx.lineWidth = 10;
                    ctx.lineJoin = 'round';
                    ctx.stroke();
                }}

                if (currentIndex < points.length - 1) {{
                    let p = points[currentIndex + 1];
                    ctx.beginPath();
                    ctx.arc(p.x, p.y, 12, 0, Math.PI*2);
                    ctx.fillStyle = '#fcd34d';
                    ctx.shadowBlur = 25;
                    ctx.shadowColor = '#fcd34d';
                    ctx.fill();
                    ctx.shadowBlur = 0;
                }}

                ctx.fillStyle = '#fff';
                ctx.font = 'bold 16px Arial';
                ctx.textAlign = 'left';
                ctx.fillText('Аккуратность: ' + Math.round(accuracy) + '%', 10, 25);

                if (isTouching && currentIndex < points.length - 1) {{
                    let nextP = points[currentIndex + 1];
                    let dist = Math.hypot(lastX - nextP.x, lastY - nextP.y);
                    if (dist > 50) {{
                        accuracy -= 0.5;
                        if (accuracy < 0) accuracy = 0;
                    }}
                }}

                requestAnimationFrame(draw);
            }}

            function handleMove(x, y) {{
                lastX = x;
                lastY = y;

                if (currentIndex >= points.length - 1) {{
                    document.getElementById('accuracyInput').value = Math.round(accuracy);
                    document.getElementById('winForm').submit();
                    return;
                }}

                let nextP = points[currentIndex + 1];
                let dist = Math.hypot(x - nextP.x, y - nextP.y);
                if (dist < 45) {{
                    currentIndex++;
                }}
            }}

            canvas.addEventListener('touchstart', (e) => {{
                e.preventDefault();
                isTouching = true;
                const rect = canvas.getBoundingClientRect();
                const touch = e.touches[0];
                handleMove((touch.clientX - rect.left) * (canvas.width / rect.width), (touch.clientY - rect.top) * (canvas.height / rect.height));
            }}, {{passive: false}});
            
            canvas.addEventListener('touchmove', (e) => {{
                e.preventDefault();
                if(!isTouching) return;
                const rect = canvas.getBoundingClientRect();
                const touch = e.touches[0];
                handleMove((touch.clientX - rect.left) * (canvas.width / rect.width), (touch.clientY - rect.top) * (canvas.height / rect.height));
            }}, {{passive: false}});
            
            canvas.addEventListener('touchend', () => isTouching = false);

            canvas.addEventListener('mousedown', (e) => {{
                isTouching = true;
                const rect = canvas.getBoundingClientRect();
                handleMove((e.clientX - rect.left) * (canvas.width / rect.width), (e.clientY - rect.top) * (canvas.height / rect.height));
            }});
            canvas.addEventListener('mousemove', (e) => {{
                if(!isTouching) return;
                const rect = canvas.getBoundingClientRect();
                handleMove((e.clientX - rect.left) * (canvas.width / rect.width), (e.clientY - rect.top) * (canvas.height / rect.height));
            }});
            canvas.addEventListener('mouseup', () => isTouching = false);
            canvas.addEventListener('mouseleave', () => isTouching = false);

            draw();
        </script>'''
    elif game == 'math':
        content = f'''<h3 id="q" style="margin-bottom:20px;">Вопрос</h3><div id="opts" style="display:flex; flex-direction:column; gap:10px;"></div><script>let a=Math.floor(Math.random()*30)+15;let b=Math.floor(Math.random()*15)+2;let ans=a*b;document.getElementById('q').innerText='Сколько будет '+a+' * '+b+'?';let opts=[ans,ans+5,ans-5,ans+10].sort(()=>Math.random()-0.5);let html='';opts.forEach(o=>{{html+=`<button class="btn gray" onclick="check(${{o}}, ${{ans}})">${{o}}</button>`;}});document.getElementById('opts').innerHTML=html;function check(sel,correct){{if(sel===correct)document.getElementById('winForm').submit();else{{alert('Неверно!');location.href='/';}}}}</script>'''
    elif game == 'math_hard':
        content = f'''<h3 id="q" style="margin-bottom:20px;">Вопрос</h3><div id="opts" style="display:flex; flex-direction:column; gap:10px;"></div><script>let a=Math.floor(Math.random()*50)+20;let b=Math.floor(Math.random()*20)+5;let c=Math.floor(Math.random()*150)+50;let ans=a*b+c;document.getElementById('q').innerText='Сколько будет ('+a+' * '+b+') + '+c+'?';let opts=[ans,ans+10,ans-10,ans+20].sort(()=>Math.random()-0.5);let html='';opts.forEach(o=>{{html+=`<button class="btn gray" onclick="check(${{o}}, ${{ans}})">${{o}}</button>`;}});document.getElementById('opts').innerHTML=html;function check(sel,correct){{if(sel===correct)document.getElementById('winForm').submit();else{{alert('Неверно!');location.href='/';}}}}</script>'''
    elif game == 'logic':
        content = f'''
        <p style="color:#94a3b8; font-size:14px; margin-bottom:15px;">Управляй компанией 5 ходов. Удерживай Доходы > Расходы и Мораль > 30!</p>
        <div class="mini-card" id="directorGame">
            <div class="stat-bar"><div class="label">Доходы:</div><div class="track"><div class="fill" id="bar-rev" style="width:50%; background:#22c55e;"></div></div><span id="val-rev">50</span></div>
            <div class="stat-bar"><div class="label">Расходы:</div><div class="track"><div class="fill" id="bar-exp" style="width:50%; background:#ef4444;"></div></div><span id="val-exp">50</span></div>
            <div class="stat-bar"><div class="label">Мораль:</div><div class="track"><div class="fill" id="bar-mor" style="width:50%; background:#3b82f6;"></div></div><span id="val-mor">50</span></div>
            <hr style="border-color:#334155; margin:15px 0;">
            <div id="event-text" style="font-weight:bold; margin-bottom:10px; font-size:15px; color:#fcd34d;">Загрузка...</div>
            <div id="choices" style="display:flex; flex-direction:column; gap:8px;"></div>
        </div>
        <script>
            let rev = 50, exp = 50, mor = 50;
            let turn = 0;
            const maxTurns = 5;
            
            const events = [
                {{ text: "Сотрудник просит повышения.", choices: [ {{ t: "Отказать", rev: 0, exp: 0, mor: -10 }}, {{ t: "Повысить зарплату", rev: 15, exp: 5, mor: 15 }}, {{ t: "Уволить его", rev: -10, exp: -15, mor: -25 }} ]}},
                {{ text: "Сломался станок.", choices: [ {{ t: "Ремонт", rev: 0, exp: 15, mor: 0 }}, {{ t: "Купить новый", rev: 40, exp: 20, mor: 10 }}, {{ t: "Игнорировать", rev: -20, exp: 0, mor: -15 }} ]}},
                {{ text: "Крупный заказчик требует скидку.", choices: [ {{ t: "Дать скидку", rev: 25, exp: 5, mor: 0 }}, {{ t: "Отказать", rev: -15, exp: 0, mor: 0 }}, {{ t: "Предложить бонусы", rev: 10, exp: 15, mor: 10 }} ]}},
                {{ text: "Налоговая проверка!", choices: [ {{ t: "Заплатить штраф", rev: 0, exp: 20, mor: -5 }}, {{ t: "Дать взятку", rev: 0, exp: 10, mor: -20 }}, {{ t: "Судиться", rev: -10, exp: 0, mor: 10 }} ]}},
                {{ text: "Сотрудники бастуют из-за переработок.", choices: [ {{ t: "Поднять зарплаты", rev: 0, exp: 15, mor: 25 }}, {{ t: "Уволить зачинщиков", rev: -15, exp: -10, mor: -20 }}, {{ t: "Нанять новых", rev: 0, exp: 10, mor: -5 }} ]}}
            ];

            function updateBars() {{
                document.getElementById('bar-rev').style.width = Math.max(0, Math.min(100, rev)) + '%'; document.getElementById('val-rev').innerText = rev;
                document.getElementById('bar-exp').style.width = Math.max(0, Math.min(100, exp)) + '%'; document.getElementById('val-exp').innerText = exp;
                document.getElementById('bar-mor').style.width = Math.max(0, Math.min(100, mor)) + '%'; document.getElementById('val-mor').innerText = mor;
            }}

            function nextTurn() {{
                if (rev <= 0 || mor <= 0 || exp >= 100) {{ alert("Компания обанкротилась! Вы уволены."); location.href = '/building/Офис#jobs'; return; }}
                if (turn >= maxTurns) {{
                    if (rev > exp && mor > 30) {{ alert("Вы успешно провели компанию через кризис!"); document.getElementById('winForm').submit(); }} 
                    else {{ alert("Совет директоров недоволен результатами. Вы уволены."); location.href = '/building/Офис#jobs'; }}
                    return;
                }}
                let ev = events[turn];
                document.getElementById('event-text').innerText = ev.text;
                let chDiv = document.getElementById('choices'); chDiv.innerHTML = '';
                ev.choices.forEach(c => {{
                    let btn = document.createElement('button'); btn.className = 'choice-btn'; btn.innerText = c.t;
                    btn.onclick = () => {{ rev += c.rev; exp += c.exp; mor += c.mor; turn++; updateBars(); nextTurn(); }};
                    chDiv.appendChild(btn);
                }});
            }}
            updateBars(); nextTurn();
        </script>'''
    elif game == 'speech':
        content = f'''
        <p style="color:#94a3b8; font-size:14px; margin-bottom:15px;">Набери 50+ голосов в 2 из 3 фракций. У тебя 100 бюджета.</p>
        <div class="mini-card" id="deputyGame">
            <div class="stat-bar"><div class="label">Бюджет:</div><div class="track"><div class="fill" id="bar-bud" style="width:100%; background:#eab308;"></div></div><span id="val-bud">100</span></div>
            <div class="stat-bar"><div class="label">Бизнес:</div><div class="track"><div class="fill" id="bar-biz" style="width:20%; background:#3b82f6;"></div></div><span id="val-biz">20</span></div>
            <div class="stat-bar"><div class="label">Народ:</div><div class="track"><div class="fill" id="bar-peo" style="width:20%; background:#22c55e;"></div></div><span id="val-peo">20</span></div>
            <div class="stat-bar"><div class="label">Консерв.:</div><div class="track"><div class="fill" id="bar-con" style="width:20%; background:#ef4444;"></div></div><span id="val-con">20</span></div>
            <hr style="border-color:#334155; margin:15px 0;">
            <p style="font-size:13px; color:#94a3b8; margin-bottom:10px;">Выбери пункты для закона (в рамках бюджета):</p>
            <div id="clauses" style="display:flex; flex-direction:column; gap:8px;"></div>
            <button class="btn green" style="margin-top:15px;" onclick="submitLaw()">Внести закон на голосование</button>
        </div>
        <script>
            let budget = 100, biz = 20, peo = 20, con = 20;
            let selected = [];

            const clauses = [
                {{ id: 1, t: "Снизить налоги для бизнеса", cost: 10, b: 20, p: -10, c: 0 }},
                {{ id: 2, t: "Бесплатное образование", cost: 20, b: -10, p: 20, c: 0 }},
                {{ id: 3, t: "Запретить митинги", cost: 5, b: 0, p: -20, c: 20 }},
                {{ id: 4, t: "Поддержать малый бизнес", cost: 15, b: 15, p: 15, c: 0 }},
                {{ id: 5, t: "Повысить пенсии", cost: 25, b: 0, p: 25, c: 0 }},
                {{ id: 6, t: "Военный парад", cost: 15, b: -5, p: 0, c: 15 }}
            ];

            function updateUI() {{
                document.getElementById('bar-bud').style.width = Math.max(0, budget) + '%'; document.getElementById('val-bud').innerText = budget;
                document.getElementById('bar-biz').style.width = Math.max(0, Math.min(100, biz)) + '%'; document.getElementById('val-biz').innerText = biz;
                document.getElementById('bar-peo').style.width = Math.max(0, Math.min(100, peo)) + '%'; document.getElementById('val-peo').innerText = peo;
                document.getElementById('bar-con').style.width = Math.max(0, Math.min(100, con)) + '%'; document.getElementById('val-con').innerText = con;
            }}

            function toggleClause(c, btn) {{
                let idx = selected.indexOf(c.id);
                if (idx > -1) {{ selected.splice(idx, 1); budget += c.cost; biz -= c.b; peo -= c.p; con -= c.c; btn.classList.remove('selected'); }} 
                else {{
                    if (budget - c.cost < 0) {{ alert("Недостаточно бюджета!"); return; }}
                    selected.push(c.id); budget -= c.cost; biz += c.b; peo += c.p; con += c.c; btn.classList.add('selected');
                }}
                updateUI();
            }}

            function submitLaw() {{
                if (selected.length === 0) {{ alert("Выберите хотя бы один пункт!"); return; }}
                let winCount = 0;
                if (biz >= 50) winCount++; if (peo >= 50) winCount++; if (con >= 50) winCount++;
                if (winCount >= 2) {{ alert("Закон принят! Вы отличный депутат."); document.getElementById('winForm').submit(); }} 
                else {{ alert("Закон отклонен. Вы не набрали нужного влияния."); location.href = '/building/Ратуша#jobs'; }}
            }}

            const cDiv = document.getElementById('clauses');
            clauses.forEach(c => {{
                let btn = document.createElement('button'); btn.className = 'choice-btn';
                btn.innerHTML = `<b>${{c.t}}</b><br><span style="font-size:12px; color:#94a3b8;">Цена: ${{c.cost}} | Б: ${{c.b}} | Н: ${{c.p}} | К: ${{c.c}}</span>`;
                btn.onclick = () => toggleClause(c, btn); cDiv.appendChild(btn);
            }});
            updateUI();
        </script>'''
    elif game == 'president':
        content = f'''
        <p style="color:#94a3b8; font-size:14px; margin-bottom:15px;">Продержись 5 ходов. Не допусти обнуления ни одной шкалы!</p>
        <div class="mini-card" id="presidentGame">
            <div class="stat-bar"><div class="label">Экономика:</div><div class="track"><div class="fill" id="p-econ" style="width:50%; background:#22c55e;"></div></div><span id="v-econ">50</span></div>
            <div class="stat-bar"><div class="label">Армия:</div><div class="track"><div class="fill" id="p-army" style="width:50%; background:#ef4444;"></div></div><span id="v-army">50</span></div>
            <div class="stat-bar"><div class="label">Народ:</div><div class="track"><div class="fill" id="p-people" style="width:50%; background:#3b82f6;"></div></div><span id="v-people">50</span></div>
            <hr style="border-color:#334155; margin:15px 0;">
            <div id="p-event" style="font-weight:bold; margin-bottom:10px; font-size:15px; color:#fcd34d;">Загрузка...</div>
            <div id="p-choices" style="display:flex; flex-direction:column; gap:8px;"></div>
        </div>
        <script>
            let econ = 50, army = 50, people = 50;
            let p_turn = 0; const p_maxTurns = 5;

            const p_events = [
                {{ text: "Экономический кризис! Инфляция растет.", choices: [ {{ t: "Напечатать деньги", e: 20, a: 0, p: -15 }}, {{ t: "Поднять налоги", e: 15, a: 0, p: -25 }}, {{ t: "Урезать расходы", e: 10, a: -15, p: -5 }} ]}},
                {{ text: "Военный конфликт на границе!", choices: [ {{ t: "Мобилизация", e: -20, a: 30, p: -20 }}, {{ t: "Дипломатия", e: 0, a: -10, p: 10 }}, {{ t: "Купить оружие", e: -30, a: 20, p: 0 }} ]}},
                {{ text: "Массовые протесты из-за цен!", choices: [ {{ t: "Разогнать силой", e: 0, a: 10, p: -30 }}, {{ t: "Ввести гос. цены", e: -15, a: 0, p: 20 }}, {{ t: "Игнорировать", e: -10, a: -10, p: -15 }} ]}},
                {{ text: "Экологическая катастрофа!", choices: [ {{ t: "Выделить деньги", e: -20, a: 0, p: 25 }}, {{ t: "Свалить на других", e: 10, a: 0, p: -15 }}, {{ t: "Ввести ЧС", e: -10, a: 15, p: -5 }} ]}},
                {{ text: "Крупный теракт!", choices: [ {{ t: "Ужесточить законы", e: 0, a: 20, p: -15 }}, {{ t: "Реформа спецслужб", e: -15, a: 15, p: 10 }}, {{ t: "Обещать спокойствие", e: 0, a: -5, p: 5 }} ]}}
            ];

            function updateP() {{
                document.getElementById('p-econ').style.width = Math.max(0, Math.min(100, econ)) + '%'; document.getElementById('v-econ').innerText = econ;
                document.getElementById('p-army').style.width = Math.max(0, Math.min(100, army)) + '%'; document.getElementById('v-army').innerText = army;
                document.getElementById('p-people').style.width = Math.max(0, Math.min(100, people)) + '%'; document.getElementById('v-people').innerText = people;
            }}

            function nextP() {{
                if (econ <= 0 || army <= 0 || people <= 0) {{ alert("Вы свергнуты! Страна в хаосе."); location.href = '/building/Ратуша#jobs'; return; }}
                if (p_turn >= p_maxTurns) {{
                    if (econ > 20 && army > 20 && people > 20) {{ alert("Вы успешно правили страной 5 сроков!"); document.getElementById('winForm').submit(); }} 
                    else {{ alert("Народ требует импичмента."); location.href = '/building/Ратуша#jobs'; }}
                    return;
                }}
                let ev = p_events[p_turn];
                document.getElementById('p-event').innerText = ev.text;
                let chDiv = document.getElementById('p-choices'); chDiv.innerHTML = '';
                ev.choices.forEach(c => {{
                    let btn = document.createElement('button'); btn.className = 'choice-btn'; btn.innerText = c.t;
                    btn.onclick = () => {{ econ += c.e; army += c.a; people += c.p; p_turn++; updateP(); nextP(); }};
                    chDiv.appendChild(btn);
                }});
            }}
            updateP(); nextP();
        </script>'''
    
    body = f'''<div class="card" style="text-align:center;"><h2 style="margin-top:0">{job['icon']} {job_name}</h2><p style="color:#94a3b8; margin-bottom:10px;">Зарплата: {job['salary']} ₽ (Голод -20)</p>{win_form}{content}<br><a href="/building/{job['loc']}?day={game_day}#jobs" class="btn gray">Отмена</a></div>'''
    return render(body, job_name, f'{job["icon"]} {job_name}', 'work')

@app.route('/work/programmer_check', methods=['POST'])
@login_required
def programmer_check():
    u = get_user(session['uid'])
    game_day = int(request.args.get('day', 1))
    diff = request.args.get('diff', 'easiest')
    user_fix = request.form.get('user_fix', '').strip()
    correct_fix = session.get('programmer_fix', '').strip()
    if not correct_fix: return redirect(url_for('work_game', job_name='Программист', day=game_day, diff=diff))
    if user_fix.replace(" ", "") == correct_fix.replace(" ", ""): return redirect(url_for('work_finish', job='Программист', game_day=game_day, diff=diff, accuracy=100))
    else:
        flash('❌ Ошибка компиляции! Код всё еще содержит баг. Попробуй еще раз.', 'error')
        return redirect(url_for('work_game', job_name='Программист', day=game_day, diff=diff))

@app.route('/work/finish', methods=['GET', 'POST'])
@login_required
def work_finish():
    job_name = request.values.get('job')
    game_day = int(request.values.get('game_day', 1))
    accuracy = int(request.values.get('accuracy', 100))
    diff = request.values.get('diff', 'easiest')
    
    if job_name not in JOBS: return redirect(url_for('index'))
    u = get_user(session['uid'])
    if u['hunger'] < 20: return redirect(url_for('index'))

    if job_name == 'Программист':
        salaries = {'easiest': 5000, 'easy': 15000, 'medium': 35000, 'hard': 80000, 'impossible': 200000}
        final_salary = salaries.get(diff, 5000)
        flash(f'Задача решена! Получено {final_salary} ₽. Голод -20.', 'success')
    else:
        base_salary = JOBS[job_name]['salary']
        final_salary = int(base_salary * (accuracy / 100))
        if job_name == 'Сварщик': flash(f'Смена окончена! Аккуратность: {accuracy}%. Получено {final_salary} ₽ (базовая: {base_salary} ₽). Голод -20.', 'success')
        else: flash(f'Смена окончена! Получено {final_salary} ₽. Голод -20.', 'success')

    new_hunger = max(0, u['hunger'] - 20)
    new_death_time = u['death_started_at']
    if new_hunger <= 5 and not new_death_time: new_death_time = time.time()

    with db() as c:
        c.execute('UPDATE users SET money=money+?, hunger=?, last_worked_day=?, death_started_at=? WHERE id=?', (final_salary, new_hunger, game_day, new_death_time, u['id']))
    return redirect(url_for('building', b_name=JOBS[job_name]['loc'], day=game_day, _anchor='jobs'))

# ============ ЭКОНОМИКА / МАГАЗИНЫ / КВАРТИРА / МЕБЕЛЬ ============

@app.route('/buy_apt', methods=['POST'])
@login_required
def buy_apt():
    u = get_user(session['uid'])
    if u['money'] >= 250000:
        with db() as c: c.execute('UPDATE users SET money=money-250000, has_apartment=1 WHERE id=?', (u['id'],))
        flash('Поздравляю с покупкой квартиры! 🎉', 'success')
    else: flash('Недостаточно денег!', 'error')
    return redirect(url_for('building', b_name='Агентство'))

@app.route('/buy_furn', methods=['POST'])
@login_required
def buy_furn():
    u = get_user(session['uid'])
    item = request.form.get('item'); delivery = request.form.get('delivery')
    if item not in FURNITURE: return redirect(url_for('index'))
    if not u['has_apartment']:
        flash('Сначала купите квартиру!', 'error')
        return redirect(url_for('building', b_name='Мебельный'))
    price = FURNITURE[item]; total_price = price + (1000 if delivery == 'hire' else 0)
    if u['money'] < total_price:
        flash('Недостаточно денег!', 'error')
        return redirect(url_for('building', b_name='Мебельный'))
    with db() as c:
        c.execute('UPDATE users SET money=money-? WHERE id=?', (total_price, u['id']))
        if delivery == 'hire':
            current = u['apt_furniture'] if u['apt_furniture'] else ''
            if current and ':' not in current:
                items = [f for f in current.split(',') if f]
                current = "|".join([f"{i}:0,0,0" for i in items])
            new_item_str = f"{item}:-1,-1,0"
            new_furn = f"{current}|{new_item_str}" if current else new_item_str
            c.execute('UPDATE users SET apt_furniture=? WHERE id=?', (new_furn, u['id']))
            flash(f'Грузчики доставили {item} в квартиру!', 'success')
        else:
            c.execute('INSERT INTO inventory(user_id,item,qty,price) VALUES(?,?,1,?)', (u['id'], item, price))
            flash(f'Вы купили {item}. Отнесите домой!', 'success')
    return redirect(url_for('building', b_name='Мебельный'))

@app.route('/unpack_furn', methods=['POST'])
@login_required
def unpack_furn():
    u = get_user(session['uid'])
    inv_id = request.form.get('id'); item = request.form.get('item')
    with db() as c:
        c.execute('DELETE FROM inventory WHERE id=? AND user_id=?', (inv_id, u['id']))
        current = u['apt_furniture'] if u['apt_furniture'] else ''
        if current and ':' not in current:
            items = [f for f in current.split(',') if f]
            current = "|".join([f"{i}:0,0,0" for i in items])
        new_item_str = f"{item}:-1,-1,0"
        new_furn = f"{current}|{new_item_str}" if current else new_item_str
        c.execute('UPDATE users SET apt_furniture=? WHERE id=?', (new_furn, u['id']))
    flash(f'Вы распаковали {item}!', 'success')
    return redirect(url_for('building', b_name='Дом'))

@app.route('/save_home_layout', methods=['POST'])
@login_required
def save_home_layout():
    data = request.get_json(); layout = data.get('layout', ''); placed_ids = data.get('placed_ids', [])
    with db() as c:
        c.execute('UPDATE users SET apt_furniture=? WHERE id=?', (layout, session['uid']))
        for item_id in placed_ids: c.execute('DELETE FROM inventory WHERE id=? AND user_id=?', (item_id, session['uid']))
    return jsonify({"status": "ok"})

@app.route('/clear_room', methods=['POST'])
@login_required
def clear_room():
    u = get_user(session['uid'])
    if u['apt_furniture']:
        items = u['apt_furniture'].split('|')
        with db() as c:
            for item in items:
                name = item.split(':')[0]
                if name in FURNITURE:
                    row = c.execute('SELECT * FROM inventory WHERE user_id=? AND item=?', (u['id'], name)).fetchone()
                    if row: c.execute('UPDATE inventory SET qty=qty+1 WHERE id=?', (row['id'],))
                    else: c.execute('INSERT INTO inventory(user_id,item,qty,price) VALUES(?,?,1,?)', (u['id'], name, FURNITURE[name]))
            c.execute('UPDATE users SET apt_furniture="" WHERE id=?', (u['id'],))
    return jsonify({"status": "ok"})

@app.route('/play_casino', methods=['POST'])
@login_required
def play_casino():
    u = get_user(session['uid'])
    try:
        bet = int(request.form.get('bet', 0)); guess = request.form.get('guess'); num1 = session.get('casino_num', 50)
        if bet > 0 and u['money'] >= bet:
            num2 = random.randint(1, 100)
            win = (guess == 'higher' and num2 > num1) or (guess == 'lower' and num2 < num1)
            commission = int(bet * 0.1)
            with db() as c:
                admin = c.execute("SELECT id FROM users WHERE username='Admin'").fetchone()
                if admin: c.execute('UPDATE users SET money=money+? WHERE id=?', (commission, admin['id']))
                if win:
                    c.execute('UPDATE users SET money=money+? WHERE id=?', (bet - commission, u['id']))
                    flash(f'🎉 Выпало {num2}! Ты выиграл {bet - commission} ₽ (комиссия {commission} ₽).', 'success')
                else:
                    c.execute('UPDATE users SET money=money-? WHERE id=?', (bet, u['id']))
                    flash(f'💸 Выпало {num2}. Ты проиграл {bet} ₽.', 'error')
        else: flash('Недостаточно денег!', 'error')
    except Exception: pass
    return redirect(url_for('building', b_name='Казино'))

@app.route('/upgrade', methods=['POST'])
@login_required
def upgrade():
    u = get_user(session['uid'])
    next_status = STATUSES[min(STATUSES.index(u['status'])+1, len(STATUSES)-1)]
    cost = UPGRADE_COST.get(next_status)
    if cost and u['money'] >= cost:
        with db() as c: c.execute('UPDATE users SET money=money-?, status=? WHERE id=?', (cost, next_status, u['id']))
        flash(f'Поздравляю! Теперь твой статус: {next_status}!', 'success')
    else: flash('Недостаточно денег!', 'error')
    return redirect(url_for('building', b_name='Карьера'))

@app.route('/eat', methods=['POST'])
@login_required
def eat():
    u = get_user(session['uid'])
    if u['death_started_at']:
        if time.time() - u['death_started_at'] >= 30: return redirect(url_for('die'))
    iid = request.form.get('id'); item = request.form.get('item')
    if item in SHOP:
        with db() as c:
            row = c.execute('SELECT * FROM inventory WHERE id=? AND user_id=?', (iid, u['id'])).fetchone()
            if row:
                new_hunger = min(100, u['hunger'] + SHOP[item]['hunger'])
                c.execute('UPDATE users SET hunger=?, death_started_at=NULL WHERE id=?', (new_hunger, u['id']))
                if row['qty'] == 1: c.execute('DELETE FROM inventory WHERE id=?', (iid,))
                else: c.execute('UPDATE inventory SET qty=qty-1 WHERE id=?', (iid,))
                flash(f'Съедено: {item}', 'success')
    return redirect(url_for('index'))

@app.route('/sell', methods=['POST'])
@login_required
def sell():
    u = get_user(session['uid'])
    iid = request.form.get('id')
    with db() as c:
        row = c.execute('SELECT * FROM inventory WHERE id=? AND user_id=?', (iid, u['id'])).fetchone()
        if row:
            price = float(row['price'] * 0.7)
            c.execute('UPDATE users SET money=money+? WHERE id=?', (price, u['id']))
            if row['qty'] == 1: c.execute('DELETE FROM inventory WHERE id=?', (iid,))
            else: c.execute('UPDATE inventory SET qty=qty-1 WHERE id=?', (iid,))
            flash(f'Продано за {price:.0f} ₽', 'success')
    return redirect(url_for('index'))

# ============ УВОЛЬНЕНИЕ / НАЙМ ============

@app.route('/hire', methods=['GET', 'POST'])
@login_required
def hire():
    if request.method == 'GET': return redirect(url_for('index'))
    job_name = request.form.get('job_name')
    if job_name in JOBS:
        u = get_user(session['uid'])
        user_jobs = u['jobs'].split(',') if u['jobs'] else []
        if job_name not in user_jobs:
            user_jobs.append(job_name); new_jobs = ",".join(user_jobs)
            with db() as c: c.execute('UPDATE users SET jobs=? WHERE id=?', (new_jobs, u['id']))
            flash(f'Ты устроился на работу: {job_name}!', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/resign_penalty', methods=['GET', 'POST'])
@login_required
def resign_penalty():
    if request.method == 'GET': return redirect(url_for('index'))
    job_name = request.form.get('job_name'); u = get_user(session['uid'])
    user_jobs = u['jobs'].split(',') if u['jobs'] else []
    if job_name in user_jobs:
        penalty = JOBS[job_name]['penalty']; new_money = max(0, u['money'] - penalty)
        user_jobs.remove(job_name); new_jobs = ",".join(user_jobs)
        with db() as c: c.execute('UPDATE users SET money=?, jobs=? WHERE id=?', (new_money, new_jobs, u['id']))
        flash(f'Ты сбежал с работы {job_name}. Выписан штраф {penalty} ₽.', 'error')
    return redirect(url_for('building', b_name=JOBS[job_name]['loc'], day=request.referrer.split('day=')[-1] if 'day=' in request.referrer else 1, _anchor='jobs'))

@app.route('/resign_clean', methods=['GET', 'POST'])
@login_required
def resign_clean():
    if request.method == 'GET': return redirect(url_for('index'))
    job_name = request.form.get('job_name'); u = get_user(session['uid'])
    user_jobs = u['jobs'].split(',') if u['jobs'] else []
    if job_name in user_jobs:
        user_jobs.remove(job_name); new_jobs = ",".join(user_jobs)
        with db() as c: c.execute('UPDATE users SET jobs=? WHERE id=?', (new_jobs, u['id']))
        flash(f'Ты уволился с работы {job_name} по собственному желанию. Без штрафов.', 'success')
    return redirect(url_for('building', b_name=JOBS[job_name]['loc'], day=request.referrer.split('day=')[-1] if 'day=' in request.referrer else 1, _anchor='jobs'))

# ============ АДМИНКА ============

@app.route('/admin')
@login_required
def admin_panel():
    if not session.get('admin'):
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('index'))
    u = get_user(session['uid'])
    body = f'''<div class="card"><h2 style="margin-top:0; color:#ef4444;">👑 Админ-панель</h2><p style="color:#94a3b8; font-size:14px; margin-bottom:20px;">Текущий баланс: {u['money']:,.0f} ₽</p><form method="POST" action="/cheat_money" style="margin-bottom:10px;"><button class="btn green" type="submit">💰 Добавить 1 000 000 ₽</button></form><form method="POST" action="/cheat_status" style="margin-bottom:10px;"><button class="btn yellow" type="submit">👑 Сделать Президентом</button></form><form method="POST" action="/cheat_hunger" style="margin-bottom:10px;"><button class="btn blue" type="submit">🍗 Восстановить голод (100)</button></form><form method="POST" action="/cheat_apt" style="margin-bottom:20px;"><button class="btn gray" type="submit">🏠 Выдать квартиру и всю мебель</button></form><a href="/" class="btn red">Вернуться в игру</a></div>'''
    return render(body, 'Админка', '👑 Админ-панель', 'office')

@app.route('/cheat_money', methods=['POST'])
@login_required
def cheat_money():
    if not session.get('admin'): return redirect(url_for('index'))
    with db() as c: c.execute('UPDATE users SET money=money+1000000 WHERE id=?', (session['uid'],))
    flash('Начислен 1 000 000 ₽!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/cheat_status', methods=['POST'])
@login_required
def cheat_status():
    if not session.get('admin'): return redirect(url_for('index'))
    with db() as c: c.execute("UPDATE users SET status='Президент' WHERE id=?", (session['uid'],))
    flash('Статус изменен на Президента!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/cheat_hunger', methods=['POST'])
@login_required
def cheat_hunger():
    if not session.get('admin'): return redirect(url_for('index'))
    with db() as c: c.execute('UPDATE users SET hunger=100, death_started_at=NULL WHERE id=?', (session['uid'],))
    flash('Голод восстановлен!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/cheat_apt', methods=['POST'])
@login_required
def cheat_apt():
    if not session.get('admin'): return redirect(url_for('index'))
    with db() as c: c.execute('UPDATE users SET has_apartment=1, apt_furniture="Диван:-1,-1,0|Телевизор:-1,-1,0|Холодильник:-1,-1,0|Корпус ПК:-1,-1,0|Монитор 144Hz:-1,-1,0|Механическая клавиатура:-1,-1,0|Игровая мышь:-1,-1,0" WHERE id=?', (session['uid'],))
    flash('Квартира с мебелью выдана!', 'success')
    return redirect(url_for('admin_panel'))

# ============ API МАГАЗИНА (КОРЗИНА) ============

@app.route('/shop/add', methods=['POST'])
@login_required
def shop_add():
    item = request.form.get('item')
    if not item or item not in SHOP: return {"status": "error", "msg": "Товар не найден"}
    if 'cart' not in session: session['cart'] = {}
    cart = dict(session['cart']); cart[item] = cart.get(item, 0) + 1; session['cart'] = cart; session.modified = True
    total = sum(SHOP[i]['price'] * q for i, q in cart.items())
    return {"status": "ok", "cart": cart, "total": total}

@app.route('/shop/pay', methods=['POST'])
@login_required
def shop_pay():
    cart = session.get('cart', {})
    if not cart: return {"status": "error", "msg": "Корзина пуста"}
    total = sum(SHOP[item]['price'] * qty for item, qty in cart.items())
    u = get_user(session['uid'])
    if u['money'] < total: return {"status": "error", "msg": "Недостаточно денег!"}
    with db() as c:
        c.execute('UPDATE users SET money=money-? WHERE id=?', (total, u['id']))
        for item, qty in cart.items():
            row = c.execute('SELECT * FROM inventory WHERE user_id=? AND item=?', (u['id'], item)).fetchone()
            if row: c.execute('UPDATE inventory SET qty=qty+? WHERE id=?', (qty, row['id']))
            else: c.execute('INSERT INTO inventory(user_id,item,qty,price) VALUES(?,?,?,?)', (u['id'], item, qty, SHOP[item]['price']))
    session['cart'] = {}; session.modified = True
    return {"status": "ok", "msg": f"Успешно оплачено {total} ₽!"}

@app.route('/shop/clear', methods=['POST'])
@login_required
def shop_clear():
    session['cart'] = {}; session.modified = True
    return {"status": "ok"}

if __name__ == '__main__':
    init_db()
    print('=' * 50)
    print('ИГРА ЗАПУЩЕНА! ВСЁ ВКЛЮЧЕНО.')
    print('Открой: http://127.0.0.1:5000 (или по IP)')
    print('Спрайты зданий: static/buildings/*.png')
    print('Спрайты мебели: static/furniture/*.png')
    print('Магазин: templates/shop.html + static/js/shop.js')
    print('Таймер голода: static/js/hunger_timer.js')
    print('=' * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)