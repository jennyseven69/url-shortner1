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
    # --- Corrected Table Creation for 'urls' ---
    c.execute('''CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_url TEXT,
                    short_key TEXT UNIQUE,
                    clicks INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0
                )''')
    # --- Corrected Table Creation for 'logs' (including country, region, city) ---
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    short_key TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    country TEXT, -- Added
                    region TEXT,  -- Added
                    city TEXT,    -- Added
                    timestamp TEXT
                )''')
    conn.commit()
    conn.close()

# Initialize the database when the app starts
init_db()

# --- Utility ---
def generate_short_key(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- Geolocation Helper ---
def get_geolocation(ip):
    """Use free IP geolocation API."""
    api_url = f"https://ipapi.co/{ip}/json/"
    try:
        response = requests.get(api_url, timeout=5, headers={'User-Agent': 'URL-Shortener-App'})
        response.raise_for_status()  # Raise an exception for HTTP error codes (4xx or 5xx)
        
        data = response.json()
        
        # Extract relevant fields based on the ipapi.co JSON structure
        return {
            "country": data.get("country_name", "Unknown"), # Use 'country_name' from ipapi
            "region": data.get("region", "Unknown"),       # Use 'region' from ipapi
            "city": data.get("city", "Unknown")            # Use 'city' from ipapi
        }
    except requests.exceptions.HTTPError as e:
        # Specifically catch HTTP errors (e.g., 429 rate limit, 404 if IP is invalid)
        print(f"HTTP error during geolocation for IP {ip}: {e}")
        # Return unknown values or handle the error as needed
        return {"country": "Unknown", "region": "Unknown", "city": "Unknown"}
    except requests.exceptions.RequestException as e:
        # Catch other requests-related errors (e.g., timeout, connection error)
        print(f"Request error during geolocation for IP {ip}: {e}")
        return {"country": "Unknown", "region": "Unknown", "city": "Unknown"}
    except ValueError: # Handles potential JSON decode errors if the response isn't valid JSON
        print(f"Geolocation API JSON decode error for IP {ip}")
        return {"country": "Unknown", "region": "Unknown", "city": "Unknown"}


# --- Routes ---
@app.route('/')
def index():
    # Pass any short_url and short_key generated from a previous shorten action
    short_url = request.args.get('short_url')
    short_key = request.args.get('short_key')
    return render_template('index.html', short_url=short_url, short_key=short_key)

@app.route('/shorten', methods=['POST'])
def shorten():
    original_url = request.form['original_url']
    
    # Basic validation
    if not original_url.startswith(('http://', 'https://')):
        original_url = 'http://' + original_url

    conn = sqlite3.connect('urls.db')
    c = conn.cursor()

    # Check if URL already shortened
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
            # Handle potential race condition if generated key already exists
            # In practice, this is very unlikely with 6 random chars
            conn.close()
            return "Error generating short URL. Please try again.", 500

    conn.close()
    short_url = request.host_url + short_key
    # Redirect back to index with the generated URL as query parameters
    return redirect(url_for('index', short_url=short_url, short_key=short_key))

@app.route('/<short_key>')
def redirect_to_original(short_key):
    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    c.execute("SELECT original_url FROM urls WHERE short_key=?", (short_key,))
    result = c.fetchone()

    if result:
        original_url = result[0]
        # Update click count
        c.execute("UPDATE urls SET clicks = clicks + 1 WHERE short_key=?", (short_key,))

        # Log click with IP & Geolocation
        # Handle potential proxy headers
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        # If X-Forwarded-For is a comma-separated list, take the first IP
        if ip:
            ip = ip.split(',')[0].strip()
        # Fallback if remote_addr is also empty (shouldn't happen usually)
        # Note: Geolocation for 127.0.0.1 or localhost will likely fail or return 'Reserved'
        user_agent = str(request.user_agent.string) # Ensure it's a string
        geo = get_geolocation(ip)

        # Only log if IP was successfully resolved (not empty or localhost in some cases)
        # Logging localhost might be okay for testing but isn't usually desired for production stats
        # You might want to add a check like `if ip and ip != '127.0.0.1' and ip != '::1':`
        # For now, let's log everything that gets an IP address from Flask
        if ip: 
            c.execute('''INSERT INTO logs (short_key, ip_address, user_agent, country, region, city, timestamp)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (short_key, ip, user_agent, geo.get("country"), geo.get("region"), geo.get("city"),
                       datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
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
    # Order by creation time or ID if you add a timestamp column later
    # For now, just order by ID descending (newest first)
    c.execute("SELECT original_url, short_key, clicks, shares FROM urls ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return render_template('dashboard.html', data=data)

@app.route('/logs/<short_key>')
def logs(short_key):
    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    # --- CORRECTED: SELECT statement now includes country, region, city ---
    # Order by log ID descending (newest first)
    c.execute("SELECT ip_address, user_agent, country, region, city, timestamp FROM logs WHERE short_key=? ORDER BY id DESC", (short_key,))
    log_data = c.fetchall()
    conn.close()
    
    # Fetch the original URL for context (optional, you can remove this if not needed)
    # conn = sqlite3.connect('urls.db')
    # c = conn.cursor()
    # c.execute("SELECT original_url FROM urls WHERE short_key=?", (short_key,))
    # url_result = c.fetchone()
    # conn.close()
    # 
    # original_url = url_result[0] if url_result else "Not Found"
    
    # Pass the log_data to the template
    return render_template('logs.html', data=log_data, short_key=short_key)


@app.route('/share/<short_key>')
def share(short_key):
    conn = sqlite3.connect('urls.db')
    c = conn.cursor()
    c.execute("UPDATE urls SET shares = shares + 1 WHERE short_key=?", (short_key,))
    conn.commit()
    conn.close()
    # Redirect back to the dashboard or index after sharing
    # For now, redirecting to index
    return redirect(url_for('index'))

if __name__ == "__main__":
    app.run(debug=True)
