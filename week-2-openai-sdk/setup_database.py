import sqlite3
import os

DB_FILE = "outreach_log.db"

def setup():
    if os.path.exists(DB_FILE):
        print(f"Database file '{DB_FILE}' already exists. Setup not needed.")
        return

    print(f"Creating new database file: {DB_FILE}")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # A simple table to log who we have contacted.
    # The UNIQUE constraint ensures we don't have duplicate entries.
    create_table_query = """
    CREATE TABLE outreach_recipients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_email TEXT NOT NULL UNIQUE,
        sent_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """

    cursor.execute(create_table_query)
    conn.commit()
    conn.close()

    print("Database setup complete. The 'outreach_recipients' table has been created.")

if __name__ == "__main__":
    setup()
