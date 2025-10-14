import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from dotenv import load_dotenv
from urllib import parse as urlparse

load_dotenv()


def get_connection():
    """Return a connection to the DATABASE_URL. If the database doesn't exist,
    attempt to create it on the server and reconnect.

    This keeps existing behavior (returns a RealDictCursor connection) but
    handles the common OperationalError where the database name is missing on
    the server.
    """
    dsn = os.getenv("DATABASE_URL")
    try:
        return psycopg2.connect(dsn, cursor_factory=RealDictCursor)
    except psycopg2.OperationalError as e:
        msg = str(e)
        if "does not exist" in msg or ("database" in msg and "does not exist" in msg):
            _create_database_if_missing(dsn)
            return psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        raise


def _create_database_if_missing(dsn: str):
    """Connect to the server default DB (postgres) using the same credentials
    and create the target database if it's missing.

    - Parses the DATABASE_URL to extract the database name.
    - Connects to the 'postgres' database on the same host/port/user.
    - Checks pg_database and creates the DB if absent.
    """
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set")

    parsed = urlparse.urlparse(dsn)
    target_db = parsed.path.lstrip('/')
    if not target_db:
        raise RuntimeError("No database name found in DATABASE_URL")

    # Build a DSN that points at the built-in 'postgres' DB (safe default).
    admin_parsed = parsed._replace(path='/postgres')
    admin_dsn = urlparse.urlunparse(admin_parsed)

    # Connect as the same user/host to the default DB and create the target if missing.
    # Use autocommit because CREATE DATABASE cannot run inside a transaction block.
    conn = psycopg2.connect(admin_dsn)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (target_db,))
        exists = cur.fetchone()
        if not exists:
            cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(target_db)))
    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()
        


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # Check if the last_sent column exists and add it if it doesn't
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='last_sent'
            ) THEN
                ALTER TABLE users ADD COLUMN last_sent DATE;
            END IF;
        END $$;
    """
    )
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            birthday DATE,
            last_sent DATE
            
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
