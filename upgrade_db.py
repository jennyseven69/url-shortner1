import sqlite3

conn = sqlite3.connect("urls.db")
c = conn.cursor()

# Add new columns if they don't exist
columns = [col[1] for col in c.execute("PRAGMA table_info(logs);").fetchall()]
new_cols = [("country", "TEXT"), ("region", "TEXT"), ("city", "TEXT")]

for col_name, col_type in new_cols:
    if col_name not in columns:
        c.execute(f"ALTER TABLE logs ADD COLUMN {col_name} {col_type};")
        print(f"✅ Added column: {col_name}")

conn.commit()
conn.close()
print("🎉 Database successfully upgraded!")
