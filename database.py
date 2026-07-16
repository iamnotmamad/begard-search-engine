# database.py
import sqlite3
from datetime import datetime
from urllib.parse import urlparse
from config import CRAWLER_DB_PATH, INDEX_DB_PATH

# دو مسیر جداگانه
CRAWLER_DB = CRAWLER_DB_PATH
INDEX_DB = INDEX_DB_PATH

def get_crawler_conn():
    conn = sqlite3.connect(CRAWLER_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=20000")
    conn.execute("PRAGMA cache_size=-2000000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def get_index_conn():
    conn = sqlite3.connect(INDEX_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=20000")
    conn.execute("PRAGMA cache_size=-2000000")
    return conn

def init_crawler_db():
    conn = get_crawler_conn()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS links_to_crawl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            discovered_from TEXT,
            depth INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            retry_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            domain TEXT,
            last_crawled DATETIME,
            status TEXT DEFAULT 'pending',
            title TEXT,
            meta_description TEXT,
            meta_keywords TEXT,
            hashtags TEXT,
            content_text TEXT,
            raw_html TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            src TEXT,
            alt TEXT,
            title TEXT,
            context TEXT,
            FOREIGN KEY (site_id) REFERENCES sites(id)
        );

        CREATE TABLE IF NOT EXISTS crawl_tree (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_site_id INTEGER,
            child_site_id INTEGER NOT NULL,
            parent_url TEXT,
            child_url TEXT UNIQUE NOT NULL,
            depth INTEGER,
            discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_site_id) REFERENCES sites(id) ON DELETE SET NULL,
            FOREIGN KEY (child_site_id) REFERENCES sites(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            searched_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_links_status_priority ON links_to_crawl(status, priority);
        CREATE INDEX IF NOT EXISTS idx_sites_url ON sites(url);
        CREATE INDEX IF NOT EXISTS idx_crawl_tree_child ON crawl_tree(child_site_id);
        CREATE INDEX IF NOT EXISTS idx_crawl_tree_parent ON crawl_tree(parent_site_id);
    ''')
    conn.commit()
    conn.close()

def init_index_db():
    conn = get_index_conn()
    conn.executescript('''
        CREATE VIRTUAL TABLE IF NOT EXISTS inverted_index USING fts5(
            word,
            site_id,
            field,
            term_freq,
            positions,
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE TABLE IF NOT EXISTS doc_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            field TEXT NOT NULL,
            length INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS idf_cache (
            word TEXT PRIMARY KEY,
            idf_value REAL NOT NULL
        );
    ''')
    conn.commit()
    conn.close()

def init_db():
    init_crawler_db()
    init_index_db()

# توابع مدیریت صف خزش (مانند قبل با تغییر اتصال به crawler db)
def add_links_batch(urls, discovered_from=None, depth=0, priority=0):
    conn = get_crawler_conn()
    for url in urls:
        try:
            conn.execute('''
                INSERT INTO links_to_crawl (url, discovered_from, depth, priority)
                VALUES (?, ?, ?, ?)
            ''', (url, discovered_from, depth, priority))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()

def get_pending_links(limit=10):
    conn = get_crawler_conn()
    rows = conn.execute('''
        SELECT * FROM links_to_crawl
        WHERE status='pending'
        ORDER BY priority ASC, added_at ASC
        LIMIT ?
    ''', (limit,)).fetchall()
    conn.close()
    return rows

def set_link_status(url, status):
    conn = get_crawler_conn()
    conn.execute("UPDATE links_to_crawl SET status=? WHERE url=?", (status, url))
    conn.commit()
    conn.close()

def set_link_failed(url):
    conn = get_crawler_conn()
    row = conn.execute("SELECT retry_count FROM links_to_crawl WHERE url=?", (url,)).fetchone()
    if row:
        retry = row['retry_count'] + 1
        if retry >= 3:
            conn.execute("UPDATE links_to_crawl SET status='failed', retry_count=? WHERE url=?", (retry, url))
        else:
            conn.execute("UPDATE links_to_crawl SET retry_count=?, status='pending' WHERE url=?", (retry, url))
    conn.commit()
    conn.close()

def url_exists_in_queue(url):
    conn = get_crawler_conn()
    row = conn.execute("SELECT 1 FROM links_to_crawl WHERE url=?", (url,)).fetchone()
    conn.close()
    return row is not None

def insert_site(url, domain, title=None, meta_desc=None, meta_keys=None,
                hashtags=None, content_text=None, raw_html=None):
    conn = get_crawler_conn()
    now = datetime.now()
    conn.execute('''
        INSERT INTO sites (url, domain, title, meta_description, meta_keywords, hashtags,
                           content_text, raw_html, status, last_crawled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'crawled', ?)
        ON CONFLICT(url) DO UPDATE SET
            title=EXCLUDED.title,
            meta_description=EXCLUDED.meta_description,
            meta_keywords=EXCLUDED.meta_keywords,
            hashtags=EXCLUDED.hashtags,
            content_text=EXCLUDED.content_text,
            raw_html=EXCLUDED.raw_html,
            status='crawled',
            last_crawled=EXCLUDED.last_crawled
    ''', (url, domain, title, meta_desc, meta_keys, hashtags, content_text, raw_html, now))
    site_id = conn.execute("SELECT id FROM sites WHERE url=?", (url,)).fetchone()['id']
    conn.commit()
    conn.close()
    return site_id

def get_site_by_id(site_id):
    conn = get_crawler_conn()
    row = conn.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
    conn.close()
    return row

def url_exists_in_sites(url):
    conn = get_crawler_conn()
    row = conn.execute("SELECT id FROM sites WHERE url=?", (url,)).fetchone()
    conn.close()
    return row is not None

def insert_image(site_id, src, alt, title, context):
    conn = get_crawler_conn()
    conn.execute("INSERT INTO images (site_id, src, alt, title, context) VALUES (?, ?, ?, ?, ?)",
                 (site_id, src, alt, title, context))
    conn.commit()
    conn.close()

def insert_crawl_relation(parent_site_id, child_site_id, parent_url, child_url, depth):
    conn = get_crawler_conn()
    try:
        conn.execute('''
            INSERT INTO crawl_tree (parent_site_id, child_site_id, parent_url, child_url, depth)
            VALUES (?, ?, ?, ?, ?)
        ''', (parent_site_id, child_site_id, parent_url, child_url, depth))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

def get_total_docs():
    conn = get_crawler_conn()
    row = conn.execute("SELECT COUNT(*) FROM sites WHERE status='crawled'").fetchone()
    conn.close()
    return row[0] if row else 0

def get_incoming_link_count(site_id):
    conn = get_crawler_conn()
    row = conn.execute("SELECT COUNT(*) FROM crawl_tree WHERE child_site_id=? AND parent_site_id IS NOT NULL",
                       (site_id,)).fetchone()
    conn.close()
    return row[0] if row else 0

# توابع تاریخچه جستجو (روی crawler db)
def add_search_history(query):
    conn = get_crawler_conn()
    conn.execute("INSERT INTO search_history (query) VALUES (?)", (query,))
    conn.commit()
    conn.close()

def get_recent_searches(limit=10):
    conn = get_crawler_conn()
    rows = conn.execute(
        "SELECT query, MAX(searched_at) as last_time FROM search_history GROUP BY query ORDER BY last_time DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [row['query'] for row in rows]

def get_exact_search_matches(partial_query, limit=3):
    conn = get_crawler_conn()
    rows = conn.execute(
        "SELECT DISTINCT query FROM search_history WHERE query = ? ORDER BY searched_at DESC LIMIT ?",
        (partial_query, limit)).fetchall()
    conn.close()
    return [row['query'] for row in rows]

def get_similar_searches(partial_query, limit=5):
    conn = get_crawler_conn()
    rows = conn.execute(
        "SELECT DISTINCT query FROM search_history WHERE query LIKE ? ORDER BY searched_at DESC LIMIT ?",
        (f"%{partial_query}%", limit)).fetchall()
    conn.close()
    return [row['query'] for row in rows]

def delete_search_history(query):
    conn = get_crawler_conn()
    conn.execute("DELETE FROM search_history WHERE query=?", (query,))
    conn.commit()
    conn.close()

def get_top_popular_searches(limit=4):
    conn = get_crawler_conn()
    rows = conn.execute(
        "SELECT query, COUNT(*) as cnt FROM search_history GROUP BY query ORDER BY cnt DESC LIMIT ?",
        (limit,)).fetchall()
    conn.close()
    return [row['query'] for row in rows]

# ---------- توابع ایندکس (index.db) ----------
def clear_index_for_site(site_id):
    conn = get_index_conn()
    conn.execute("DELETE FROM inverted_index WHERE site_id=?", (site_id,))
    conn.execute("DELETE FROM doc_stats WHERE site_id=?", (site_id,))
    conn.commit()
    conn.close()

def insert_index_batch(entries):
    """entries: list of (word, site_id, field, term_freq, positions)"""
    conn = get_index_conn()
    # FTS5 نیاز به INSERT معمولی دارد
    conn.executemany(
        "INSERT INTO inverted_index (word, site_id, field, term_freq, positions) VALUES (?, ?, ?, ?, ?)",
        entries
    )
    conn.commit()
    conn.close()

def insert_doc_stat(site_id, field, length):
    conn = get_index_conn()
    conn.execute("INSERT INTO doc_stats (site_id, field, length) VALUES (?, ?, ?)",
                 (site_id, field, length))
    conn.commit()
    conn.close()

def get_field_length(site_id, field):
    conn = get_index_conn()
    row = conn.execute("SELECT length FROM doc_stats WHERE site_id=? AND field=?", (site_id, field)).fetchone()
    conn.close()
    return row['length'] if row else 0

def get_avg_field_length(field):
    conn = get_index_conn()
    row = conn.execute("SELECT AVG(length) FROM doc_stats WHERE field=?", (field,)).fetchone()
    conn.close()
    return row[0] if row and row[0] else 1.0

def compute_and_store_idf():
    """پیش‌محاسبه و ذخیرهٔ IDF تمام کلمات"""
    conn = get_index_conn()
    total_docs = get_total_docs()
    if total_docs == 0:
        return
    # پاک کردن قدیمی
    conn.execute("DELETE FROM idf_cache")
    # محاسبه IDF با فرمول استاندارد
    rows = conn.execute('''
        SELECT word, COUNT(DISTINCT site_id) as doc_freq
        FROM inverted_index
        GROUP BY word
    ''').fetchall()
    idf_data = []
    for r in rows:
        idf = math.log((total_docs - r[1] + 0.5) / (r[1] + 0.5) + 1.0)
        idf_data.append((r[0], idf))
    conn.executemany("INSERT INTO idf_cache (word, idf_value) VALUES (?, ?)", idf_data)
    conn.commit()
    conn.close()

def get_idf(word):
    """خواندن IDF از کش"""
    conn = get_index_conn()
    row = conn.execute("SELECT idf_value FROM idf_cache WHERE word=?", (word,)).fetchone()
    conn.close()
    return row[0] if row else 0.0

def search_fts(tokens, limit=20, offset=0):
    """جستجوی FTS5: عبارات با پشتیبانی از AND و رتبه‌بندی"""
    conn = get_index_conn()
    # تبدیل توکن‌ها به query FTS5: "word1" AND "word2" AND ...
    query = ' AND '.join(f'"{w}"' for w in tokens)
    sql = f'''
        SELECT site_id, SUM(rank) as total_score
        FROM inverted_index
        WHERE inverted_index MATCH ?
        GROUP BY site_id
        ORDER BY total_score DESC
        LIMIT ? OFFSET ?
    '''
    # FTS5 rank با تابع bm25
    rows = conn.execute(sql, (query, limit, offset)).fetchall()
    conn.close()
    return rows


def is_domain_indexed(domain):
    conn = get_crawler_conn()
    row = conn.execute("SELECT 1 FROM sites WHERE domain=? AND status='crawled' LIMIT 1", (domain,)).fetchone()
    conn.close()
    return row is not None

def get_term_stats_for_site(site_id, word):
    conn = get_index_conn()
    rows = conn.execute("SELECT field, term_freq, positions FROM inverted_index WHERE word=? AND site_id=?", (word, site_id)).fetchall()
    conn.close()
    return rows

def compute_and_store_idf():
    conn = get_index_conn()
    total_docs = get_total_docs()
    if total_docs == 0:
        return
    conn.execute("DELETE FROM idf_cache")
    rows = conn.execute('''
        SELECT word, COUNT(DISTINCT site_id) as doc_freq
        FROM inverted_index
        GROUP BY word
    ''').fetchall()
    idf_data = []
    for r in rows:
        idf = math.log((total_docs - r[1] + 0.5) / (r[1] + 0.5) + 1.0)
        idf_data.append((r[0], idf))
    conn.executemany("INSERT INTO idf_cache (word, idf_value) VALUES (?, ?)", idf_data)
    conn.commit()
    conn.close()


def is_homepage(site_id):
    """بررسی می‌کند که آیا این سایت یک homepage است (یعنی در crawl_tree به عنوان فرزند ثبت نشده است)"""
    conn = get_crawler_conn()
    row = conn.execute("SELECT 1 FROM crawl_tree WHERE child_site_id=?", (site_id,)).fetchone()
    conn.close()
    # اگر در crawl_tree به عنوان فرزند وجود نداشته باشد، homepage است
    return row is None

def get_top_sitelinks(domain, limit=6):
    """
    برمی‌گرداند sitelinkهای یک دامنه.
    homepage را بر اساس مسیر ریشه (/) تشخیص می‌دهد.
    """
    conn = get_crawler_conn()
    # یافتن homepage: آدرس‌هایی از دامنه که path آن‌ها '/' یا خالی باشد
    rows = conn.execute('SELECT id, url FROM sites WHERE domain = ?', (domain,)).fetchall()
    homepage_id = None
    for row in rows:
        parsed = urlparse(row['url'])
        if parsed.path in ('', '/'):
            homepage_id = row['id']
            break
    if homepage_id is None:
        # اگر هیچ homepage با مسیر ریشه پیدا نشد، اولین صفحهٔ دامنه را به‌عنوان homepage قبول کن
        if rows:
            homepage_id = rows[0]['id']
        else:
            conn.close()
            return []

    # sitelinkها = صفحات همان دامنه به جز homepage
    sitelink_rows = conn.execute('''
        SELECT s.url, s.title, COUNT(ct.id) as incoming
        FROM sites s
        LEFT JOIN crawl_tree ct ON s.id = ct.child_site_id
        WHERE s.domain = ? AND s.id != ?
        GROUP BY s.id
        ORDER BY incoming DESC
        LIMIT ?
    ''', (domain, homepage_id, limit)).fetchall()
    conn.close()
    return [{'url': row['url'], 'title': row['title']} for row in sitelink_rows if row['title'] and row['title'].strip()]