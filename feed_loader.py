# feed_loader.py
import csv
from urllib.parse import urlparse
import database as db
import log_utils as log

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def load_feed(filepath):
    db.init_db()
    urls = []
    if filepath.endswith('.csv'):
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    candidate = row[0].strip()
                    if is_valid_url(candidate):
                        urls.append(candidate)
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                candidate = line.strip()
                if is_valid_url(candidate):
                    urls.append(candidate)

    unique_urls = list(set(urls))
    if not unique_urls:
        log.warning("No valid URLs found.")
        return

    conn = db.get_crawler_conn()
    for url in unique_urls:
        try:
            conn.execute('''
                INSERT INTO links_to_crawl (url, discovered_from, depth, priority, status)
                VALUES (?, 'seed_file', 0, 0, 'pending')
                ON CONFLICT(url) DO UPDATE SET
                    status='pending',
                    depth=0,
                    priority=0,
                    retry_count=0,
                    discovered_from='seed_file'
            ''', (url,))
        except Exception as e:
            log.error(f"Insert {url}: {e}")
    conn.commit()
    conn.close()
    log.info(f"{len(unique_urls)} seed URLs added/reset from {filepath}")

    from crawler_first import update_queue_file
    update_queue_file()