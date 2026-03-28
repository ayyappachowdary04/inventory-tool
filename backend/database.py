import psycopg2
import psycopg2.errors
from psycopg2.extras import RealDictCursor
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME", "postgres")
VARIANTS = ["2L", "1L", "Q", "P", "N"]
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

class PostgresWrapper:
    def __init__(self, conn):
        self.conn = conn
    def execute(self, sql, params=None):
        # Translate SQLite ? to PostgreSQL %s
        sql = sql.replace("?", "%s")
        # Translate INSERT OR IGNORE to ON CONFLICT DO NOTHING
        if "INSERT OR IGNORE" in sql.upper():
            sql = sql.upper().replace("INSERT OR IGNORE", "INSERT") + " ON CONFLICT DO NOTHING"
        
        try:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return cur
        except Exception as e:
            print(f"DATABASE ERROR in execute: {str(e)}")
            raise e
    def cursor(self):
        return self.conn.cursor()
    def commit(self):
        self.conn.commit()
    def rollback(self):
        self.conn.rollback()
    def close(self):
        self.conn.close()

def get_db():
    try:
        if DB_HOST and DB_USER and DB_PASS:
            print(f"DATABASE: Connecting via individual variables to host: {DB_HOST}")
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                dbname=DB_NAME,
                sslmode='require',
                cursor_factory=RealDictCursor
            )
        elif DB_URL:
            # Hide password for security
            safe_url = DB_URL.split('@')[-1] if '@' in DB_URL else 'HIDDEN'
            print(f"DATABASE: Connecting via URL to host: {safe_url}")
            conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
        else:
            print("CRITICAL: No database configuration found (DATABASE_URL or DB_HOST/USER/PASS)!")
            raise ValueError("No database configuration found!")
        
        print("DATABASE: Connection successful!")
        return PostgresWrapper(conn)
    except Exception as e:
        print(f"CRITICAL: Failed to connect to database: {str(e)}")
        raise e

def init_db():
    if not DB_URL and not DB_HOST:
        print("Warning: No database configuration found for initialization.")
        return
        
    conn = get_db()
    # PostgresWrapper already provides an execute() method
    c = conn

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
