# app.py
from flask import Flask, request, redirect, render_template, url_for
import string, random, sqlite3

app = Flask(__name__)

# -----------------------------
# Database setup
# -----------------------------
def init_db():
    conn = sqlite3.connect("urls.db")
    c = conn.cursor()

    # main urls table
    c.execute('''CREATE TABLE IF NOT EXISTS urls 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  original_url TEXT, 
                  short_key TEXT UNIQUE, 
                  clicks INTEGER DEFAULT 0,
                  shares INTEGER DEFAULT 0)''')

    # logs table for IP / UA / timestamp
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  short_key TEXT,
                  ip_address TEXT,
                  user_agent TEXT,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    conn.commit()
    conn.close()

init_db()

# -----------------------------
# Generate random short key
# -----------------------------
def generate_short_key(length=6):
    characters = string.ascii_letters + string.digits
    conn = sqlite3.connect("urls.db")
    c = conn.cursor()
    while True:
        short_key = ''.join(random.choice(characters) for _ in range(length))
        c.execute("SELECT 1 FROM urls WHERE short_key=?", (short_key,))
        if not c.fetchone():  # ensures unique
            conn.close()
            return short_key

# -----------------------------
# Home page (form)
# -----------------------------
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

# -----------------------------
# Shorten URL (form POST)
# -----------------------------
@app.route("/shorten", methods=["POST"])
def shorten_url():
    original_url = request.form["original_url"].strip()

    # basic normalization: add http:// if user omitted scheme
    if not (original_url.startswith("http://") or original_url.startswith("https://")):
        original_url = "http://" + original_url

    short_key = generate_short_key()

    conn = sqlite3.connect("urls.db")
    c = conn.cursor()
    c.execute("INSERT INTO urls (original_url, short_key) VALUES (?, ?)", 
              (original_url, short_key))
    conn.commit()
    conn.close()

    short_url = request.host_url + short_key  # e.g. http://.0.0.1:5000/Ab12Xy
    return render_template("result.html", short_url=short_url, short_key=short_key)

# -----------------------------
# Redirect short URL + log IP & UA
# -----------------------------
@app.route("/<short_key>")
def redirect_url(short_key):
    conn = sqlite3.connect("urls.db")
    c = conn.cursor()
    c.execute("SELECT original_url, clicks FROM urls WHERE short_key=?", (short_key,))
    row = c.fetchone()

    if row:
        original_url, clicks = row

        # update click count
        c.execute("UPDATE urls SET clicks=? WHERE short_key=?", (clicks+1, short_key))

        # detect client IP (supporting proxy header if present)
        x_forwarded_for = request.headers.get("X-Forwarded-For", None)
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0].strip()
        else:
            ip_address = request.remote_addr

        # user agent string
        user_agent = request.user_agent.string

        # insert log
        c.execute("INSERT INTO logs (short_key, ip_address, user_agent) VALUES (?, ?, ?)",
                  (short_key, ip_address, user_agent))

        conn.commit()
        conn.close()
        return redirect(original_url)

    conn.close()
    return "Invalid short URL!", 404

# -----------------------------
# Track share (increments shares)
# -----------------------------
@app.route("/share/<short_key>")
def share(short_key):
    conn = sqlite3.connect("urls.db")
    c = conn.cursor()
    c.execute("SELECT shares FROM urls WHERE short_key=?", (short_key,))
    row = c.fetchone()
    if row:
        shares = row[0]
        c.execute("UPDATE urls SET shares=? WHERE short_key=?", (shares+1, short_key))
        conn.commit()
    conn.close()
    return f"✅ Thanks for sharing! Short link: /{short_key}"

# -----------------------------
# Dashboard (list of URLs)
# -----------------------------
@app.route("/dashboard")
def dashboard():
    conn = sqlite3.connect("urls.db")
    c = conn.cursor()
    c.execute("SELECT original_url, short_key, clicks, shares FROM urls ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return render_template("dashboard.html", data=data)

# -----------------------------
# Logs viewer for a short key
# -----------------------------
@app.route("/logs/<short_key>")
def logs(short_key):
    conn = sqlite3.connect("urls.db")
    c = conn.cursor()
    c.execute("SELECT ip_address, user_agent, timestamp FROM logs WHERE short_key=? ORDER BY id DESC", (short_key,))
    data = c.fetchall()
    conn.close()
    return render_template("logs.html", short_key=short_key, data=data)

# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
