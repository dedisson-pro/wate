import pymysql
import pymysql.cursors
import os
from urllib.parse import urlparse

def _parse_db_url():
    """Parse les variables MySQL dans tous les formats Railway possibles."""
    url = (os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL") or
           os.getenv("MYSQL_PRIVATE_URL"))
    if url and ("mysql" in url or "mariadb" in url):
        p = urlparse(url)
        return {
            "host": p.hostname,
            "port": p.port or 3306,
            "user": p.username,
            "password": p.password,
            "database": p.path.lstrip("/")
        }
    return {
        "host": (os.getenv("MYSQL_HOST") or os.getenv("MYSQLHOST") or "localhost"),
        "port": int(os.getenv("MYSQL_PORT") or os.getenv("MYSQLPORT") or 3306),
        "user": (os.getenv("MYSQL_USER") or os.getenv("MYSQLUSER") or
                 os.getenv("MYSQL_USERNAME") or "root"),
        "password": (os.getenv("MYSQL_PASSWORD") or os.getenv("MYSQLPASSWORD") or
                     os.getenv("MYSQL_ROOT_PASSWORD") or ""),
        "database": (os.getenv("MYSQL_DATABASE") or os.getenv("MYSQLDATABASE") or
                     os.getenv("MYSQL_DB") or "whataPlant")
    }

def get_db():
    cfg = _parse_db_url()
    return pymysql.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def init_db():
    """Initialise la base de données — ne crashe pas si MySQL est absent."""
    try:
        cfg = _parse_db_url()
        db_name = cfg["database"]

        # Créer la base si elle n'existe pas
        conn = pymysql.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            charset="utf8mb4", autocommit=True
        )
        with conn.cursor() as c:
            c.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.close()

        # Créer la table
        conn = get_db()
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    image_path   VARCHAR(255),
                    common_name  VARCHAR(255),
                    scientific_name VARCHAR(255),
                    family       VARCHAR(255),
                    confidence   FLOAT,
                    is_edible    VARCHAR(50),
                    is_medicinal VARCHAR(50),
                    is_toxic     VARCHAR(50),
                    is_invasive  VARCHAR(50),
                    health_status TEXT,
                    ai_report    LONGTEXT,
                    plantnet_raw LONGTEXT,
                    latitude     DOUBLE,
                    longitude    DOUBLE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        conn.close()
        print("✅ Base de données initialisée")
    except Exception as e:
        print(f"⚠️  MySQL indisponible au démarrage : {e}")
        print("   L'app démarre quand même — configurez MySQL dans les variables Railway")

def save_scan(data: dict) -> int:
    conn = get_db()
    with conn.cursor() as c:
        c.execute("""
            INSERT INTO scans (image_path, common_name, scientific_name, family, confidence,
                is_edible, is_medicinal, is_toxic, is_invasive, health_status, ai_report,
                plantnet_raw, latitude, longitude)
            VALUES (%(image_path)s, %(common_name)s, %(scientific_name)s, %(family)s,
                %(confidence)s, %(is_edible)s, %(is_medicinal)s, %(is_toxic)s, %(is_invasive)s,
                %(health_status)s, %(ai_report)s, %(plantnet_raw)s, %(latitude)s, %(longitude)s)
        """, data)
        scan_id = c.lastrowid
    conn.close()
    return scan_id

def get_all_scans():
    conn = get_db()
    with conn.cursor() as c:
        c.execute("SELECT * FROM scans ORDER BY created_at DESC")
        rows = c.fetchall()
    conn.close()
    return rows

def get_scan_by_id(scan_id: int):
    conn = get_db()
    with conn.cursor() as c:
        c.execute("SELECT * FROM scans WHERE id = %s", (scan_id,))
        row = c.fetchone()
    conn.close()
    return row

def get_dashboard_stats():
    conn = get_db()
    stats = {}
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) as total FROM scans")
        stats["total"] = c.fetchone()["total"]
        c.execute("""
            SELECT scientific_name, COUNT(*) as count FROM scans
            GROUP BY scientific_name ORDER BY count DESC LIMIT 5
        """)
        stats["top_plants"] = c.fetchall()
        c.execute("SELECT COUNT(*) as n FROM scans WHERE is_edible='Oui'")
        edible = c.fetchone()["n"]
        c.execute("SELECT COUNT(*) as n FROM scans WHERE is_medicinal='Oui'")
        medicinal = c.fetchone()["n"]
        c.execute("SELECT COUNT(*) as n FROM scans WHERE is_toxic='Oui'")
        toxic = c.fetchone()["n"]
        c.execute("SELECT COUNT(*) as n FROM scans WHERE is_invasive='Oui'")
        invasive = c.fetchone()["n"]
        stats["by_category"] = {
            "edible": edible, "medicinal": medicinal,
            "toxic": toxic, "invasive": invasive
        }
        c.execute("""
            SELECT DATE(created_at) as day, COUNT(*) as count
            FROM scans GROUP BY day ORDER BY day DESC LIMIT 7
        """)
        stats["recent"] = c.fetchall()
    conn.close()
    for r in stats["recent"]:
        if hasattr(r.get("day"), "isoformat"):
            r["day"] = r["day"].isoformat()
    return stats
