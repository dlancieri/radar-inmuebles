import sqlite3


DB_NAME = "properties.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_id TEXT,
            title TEXT,
            price_usd REAL,
            area_m2 REAL,
            neighborhood TEXT,
            city TEXT,
            link TEXT UNIQUE,
            description TEXT,
            score INTEGER,
            signals TEXT,
            usd_m2 REAL,
            detected_at TEXT,
            last_seen_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def upsert_property(prop, score, signals, usd_m2):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO properties (
            source, external_id, title, price_usd, area_m2,
            neighborhood, city, link, description,
            score, signals, usd_m2, detected_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(link) DO UPDATE SET
            title=excluded.title,
            price_usd=excluded.price_usd,
            area_m2=excluded.area_m2,
            neighborhood=excluded.neighborhood,
            city=excluded.city,
            description=excluded.description,
            score=excluded.score,
            signals=excluded.signals,
            usd_m2=excluded.usd_m2,
            last_seen_at=excluded.last_seen_at
    """, (
        prop.source,
        prop.external_id,
        prop.title,
        prop.price_usd,
        prop.area_m2,
        prop.neighborhood,
        prop.city,
        prop.link,
        prop.description,
        score,
        ", ".join(signals),
        usd_m2,
        prop.detected_at,
        prop.detected_at,
    ))

    conn.commit()
    conn.close()


def export_opportunities_csv(filename="oportunidades.csv"):
    import pandas as pd

    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT
            source,
            title,
            price_usd,
            area_m2,
            ROUND(usd_m2, 2) AS usd_m2,
            neighborhood,
            city,
            score,
            signals,
            link,
            detected_at,
            last_seen_at
        FROM properties
        WHERE score >= 30
        ORDER BY score DESC, usd_m2 ASC
    """, conn)

    conn.close()
    df.to_csv(filename, index=False)
    return df
