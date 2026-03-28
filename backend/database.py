import psycopg2
from psycopg2.extras import RealDictCursor
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
VARIANTS = ["2L", "1L", "Q", "P", "N"]
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_db():
    # If using Supabase, ensure DATABASE_URL uses pooling (Mode: Transaction)
    if not DB_URL:
        raise ValueError("DATABASE_URL is not set!")
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    if not DB_URL:
        print("Warning: DATABASE_URL not set.")
        return
        
    conn = get_db()
    c = conn.cursor()

    try:
        c.execute("SELECT role FROM users LIMIT 1")
    except psycopg2.errors.UndefinedTable:
        conn.rollback()

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS brands
                 (id SERIAL PRIMARY KEY, name TEXT, is_alcohol BOOLEAN)''')
    c.execute('''CREATE TABLE IF NOT EXISTS prices
                 (brand_id INTEGER, variant TEXT, price REAL,
                  FOREIGN KEY(brand_id) REFERENCES brands(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (date TEXT, brand_id INTEGER, variant TEXT,
                  opening INTEGER, receipts INTEGER, closing INTEGER,
                  status INTEGER DEFAULT 0,
                  UNIQUE(date, brand_id, variant))''') # Added unique constraint for ON CONFLICT to work
    c.execute('''CREATE TABLE IF NOT EXISTS price_audit
                 (id SERIAL PRIMARY KEY,
                  timestamp TEXT, brand_id INTEGER, variant TEXT,
                  old_price REAL, new_price REAL)''')

    c.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin') ON CONFLICT DO NOTHING")
    c.execute("INSERT INTO users (username, password, role) VALUES ('shopkeeper', '1234', 'shopkeeper') ON CONFLICT DO NOTHING")
    conn.commit()
    conn.close()

def get_india_date():
    return datetime.datetime.now(IST).date()
