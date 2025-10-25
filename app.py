# app.py
from flask import Flask, request, redirect, render_template, url_for
import sqlite3
import string
import random
import datetime
import requests

app = Flask(__name__)

# --- Database Setup ---
def init_db():
    conn = sqlite3.connect("urls.db")
    c = conn.cursor()
    # Table for URLs
    c.execute('''CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_url TEXT,
                    short_key TEXT UNIQUE,
                    clicks INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0
                )''')
    # Table for logs (with geolocation info)
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_key TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    country TEXT,
                    region TEXT,
                    city TEXT,
                    timestamp TEXT
                )''')
    conn.commit()
    conn.close()

# Initialize DB
init_db()

# --- Utility ---
def generate_short_key(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- Geolocation Helper (uses ipwho.is) ---
def get_geolocation(ip):
    """Fetch country, region, and city for an IP using ipwho.is"""
    try:
        if ip in ("127.0.0.1", "::1"):
            return {"country": "Localhost", "region": "-", "city": "-"}

        response = requests.get(f"https://ipwho.is/{ip}", timeout=5)
        data = response.json()

        if data.get("success"):
            return {
                "country": data.get("country", "Unknown"),
                "region": data.get("region", "Unknown"),
                "city": data.get("city", "Unknown")
            }
        else:
            return {"country": "Unknown", "region": "Unknown", "city": "Unknown"}
    except Exception as e:
        print(f"[Geo Error] {e}")
        return {"country": "Unknown", "region": "Unknown", "city": "Unknown"}

# --- Routes ---
@app.route('/')
def index():
    short_url = request.args.get('short_url')
    short_key = request.args.get('short_key')
    return render_template('index.html', short_url=short_url, short_key=short_key)

@app.route('/shorten', methods=['POST'])
def shorten():
    original_url = request.form['original_url']
    if not original_url.startswith(('http://', 'https://')):
        original_url = 'http://' + original_url

    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    c.execute("SELECT short_key FROM urls WHERE original_url=?", (original_url,))
    existing = c.fetchone()

    if existing:
        short_key = existing[0]
    else:
        short_key = generate_short_key()
        try:
            c.execute("INSERT INTO urls (original_url, short_key) VALUES (?, ?)", (original_url, short_key))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Error generating short URL. Please try again.", 500

    conn.close()
    short_url = request.host_url + short_key
    return redirect(url_for('index', short_url=short_url, short_key=short_key))

@app.route('/<short_key>')
def redirect_to_original(short_key):
    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    c.execute("SELECT original_url FROM urls WHERE short_key=?", (short_key,))
    result = c.fetchone()

    if result:
        original_url = result[0]
        c.execute("UPDATE urls SET clicks = clicks + 1 WHERE short_key=?", (short_key,))

        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip:
            ip = ip.split(',')[0].strip()

        user_agent = str(request.user_agent.string)
        geo = get_geolocation(ip)

        c.execute('''INSERT INTO logs (short_key, ip_address, user_agent, country, region, city, timestamp)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (short_key, ip, user_agent, geo.get("country"), geo.get("region"),
                   geo.get("city"), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
        conn.close()
        return redirect(original_url)
    else:
        conn.close()
        return "Invalid short URL", 404

@app.route('/dashboard')
def dashboard():
    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    c.execute("SELECT original_url, short_key, clicks, shares FROM urls ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return render_template('dashboard.html', data=data)

@app.route('/logs/<short_key>')
def logs(short_key):
    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    c.execute("SELECT ip_address, user_agent, country, region, city, timestamp FROM logs WHERE short_key=? ORDER BY id DESC", (short_key,))
    log_data = c.fetchall()
    conn.close()
    return render_template('logs.html', data=log_data, short_key=short_key)

@app.route('/share/<short_key>')
def share(short_key):
    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    c.execute("UPDATE urls SET shares = shares + 1 WHERE short_key=?", (short_key,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)
