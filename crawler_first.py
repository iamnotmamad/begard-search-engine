# crawler_first.py
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import database as db
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from indexer import index_site
import os
import threading
import log_utils as log
from config import (
    USER_AGENT, TIMEOUT, DELAY_BETWEEN_SAME_DOMAIN,
    CRAWLER_THREADS, INDEXER_THREADS, EXCLUDED_EXTENSIONS
)

QUEUE_FILE = 'crawl_queue.txt'
queue_file_lock = threading.Lock()

domain_last_request = {}
url_cache_lock = threading.Lock()
queued_urls = set()
site_urls = set()

add_links_lock = threading.Lock()
allow_adding_links = True

index_executor = ThreadPoolExecutor(max_workers=INDEXER_THREADS)
favicon_executor = ThreadPoolExecutor(max_workers=2)

CRAWL_MODE = 1

def update_queue_file():
    conn = db.get_crawler_conn()
    rows = conn.execute("SELECT url FROM links_to_crawl WHERE status='pending' ORDER BY priority ASC, added_at ASC").fetchall()
    conn.close()
    with queue_file_lock:
        with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(r['url'] + '\n')

def create_session():
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[500,502,503,504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({'User-Agent': USER_AGENT})
    return session

def normalize_url(url, _cache={}):
    if url in _cache:
        return _cache[url]
    parsed = urlparse(url)
    parsed = parsed._replace(fragment='')
    if parsed.hostname and parsed.hostname.startswith('www.'):
        netloc = parsed.hostname[4:] + (f':{parsed.port}' if parsed.port else '')
        parsed = parsed._replace(netloc=netloc)
    if parsed.hostname:
        parsed = parsed._replace(netloc=parsed.hostname.lower() + (f':{parsed.port}' if parsed.port else ''))
    path = parsed.path
    if path != '/' and path.endswith('/'):
        path = path.rstrip('/')
        parsed = parsed._replace(path=path)
    result = urlunparse(parsed)
    _cache[url] = result
    return result

def can_fetch(url):
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
        return False
    return urlparse(url).scheme in ('http', 'https')

def extract_page_data(html, final_url):
    soup = BeautifulSoup(html, 'lxml')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else ''
    meta_desc, meta_keys = '', ''
    for meta in soup.find_all('meta'):
        name = meta.get('name', '').lower()
        if name == 'description': meta_desc = meta.get('content', '')
        elif name == 'keywords': meta_keys = meta.get('content', '')
    clean_text = ' '.join(soup.stripped_strings)[:5000]
    hashtags = ' '.join(re.findall(r'#\w+', clean_text))
    links = set()
    for a in soup.find_all('a', href=True):
        absolute = urljoin(final_url, a['href'].strip())
        if can_fetch(absolute):
            links.add(normalize_url(absolute))
    images = []
    for img in soup.find_all('img'):
        src = urljoin(final_url, img.get('src', ''))
        alt = img.get('alt', '')
        img_title = img.get('title', '')
        parent_text = img.parent.get_text(separator=' ', strip=True) if img.parent else ''
        images.append((src, alt, img_title, parent_text[:500]))
    favicon_url = None
    icon_link = soup.find('link', rel=lambda r: r and 'icon' in r)
    if icon_link and icon_link.get('href'):
        favicon_url = urljoin(final_url, icon_link['href'])
    else:
        favicon_url = f"https://{urlparse(final_url).netloc}/favicon.ico"
    return {
        'title': title, 'meta_desc': meta_desc, 'meta_keys': meta_keys,
        'hashtags': hashtags, 'content_text': clean_text,
        'images': images, 'links': links, 'favicon_url': favicon_url
    }

def download_favicon(domain, favicon_url):
    try:
        resp = requests.get(favicon_url, timeout=5, stream=True)
        if resp.status_code == 200 and 'image' in resp.headers.get('Content-Type',''):
            os.makedirs('static/favicons', exist_ok=True)
            with open(f'static/favicons/{domain}.ico', 'wb') as f: f.write(resp.content)
            return
    except: pass
    try:
        resp = requests.get(f"https://www.google.com/s2/favicons?domain={domain}", timeout=5, stream=True)
        if resp.status_code == 200 and 'image' in resp.headers.get('Content-Type',''):
            with open(f'static/favicons/{domain}.ico', 'wb') as f: f.write(resp.content)
    except: pass

def check_queue_threshold():
    global allow_adding_links
    try:
        conn = db.get_crawler_conn()
        cnt = conn.execute("SELECT COUNT(*) FROM links_to_crawl WHERE status='pending'").fetchone()[0]
        conn.close()
    except Exception:
        return
    with add_links_lock:
        if cnt > 500:
            allow_adding_links = False
            log.warning(f"Queue limit reached ({cnt} pending). Pausing new links.")
        elif cnt <= 100:
            allow_adding_links = True
            log.info(f"Queue below 100 ({cnt} pending). Resuming new links.")

def queue_monitor():
    while True:
        time.sleep(5)
        check_queue_threshold()

def crawl_single(url_row):
    original_url = url_row['url']
    depth = url_row['depth']
    discovered_from = url_row['discovered_from']
    domain = urlparse(original_url).netloc

    now = time.time()
    if domain in domain_last_request:
        elapsed = now - domain_last_request[domain]
        if elapsed < DELAY_BETWEEN_SAME_DOMAIN:
            time.sleep(DELAY_BETWEEN_SAME_DOMAIN - elapsed)
    domain_last_request[domain] = time.time()

    session = create_session()
    try:
        resp = session.get(original_url, timeout=TIMEOUT, stream=True)
        if 'text/html' not in resp.headers.get('Content-Type', ''):
            db.set_link_status(original_url, 'done')
            return
        final_url = normalize_url(resp.url)
        html = resp.text
    except Exception as e:
        log.error(f"{original_url}: {e}")
        db.set_link_failed(original_url)
        return

    if final_url != original_url:
        if db.url_exists_in_sites(final_url):
            log.skip(f"{original_url} -> {final_url}")
            db.set_link_status(original_url, 'done')
            return

    data = extract_page_data(html, final_url)
    site_id = db.insert_site(final_url, domain, data['title'], data['meta_desc'],
                             data['meta_keys'], data['hashtags'], data['content_text'], html)
    for src, alt, img_title, ctx in data['images']:
        db.insert_image(site_id, src, alt, img_title, ctx)

    favicon_executor.submit(download_favicon, domain, data['favicon_url'])
    index_executor.submit(index_site, site_id, data)

    with url_cache_lock:
        site_urls.add(final_url)

    new_links = data['links']
    added = 0
    for link in new_links:
        link_domain = urlparse(link).netloc
        with url_cache_lock:
            if link in queued_urls or link in site_urls:
                continue
            with add_links_lock:
                if not allow_adding_links:
                    break

            if CRAWL_MODE == 1:
                if link_domain == domain:
                    db.add_links_batch([link], discovered_from=final_url, depth=depth+1, priority=2)
                    queued_urls.add(link)
                    child_id = db.insert_site(link, link_domain)
                    db.insert_crawl_relation(site_id, child_id, final_url, link, depth+1)
                    added += 1
                else:
                    homepage = f"https://{link_domain}/"
                    if homepage not in queued_urls and homepage not in site_urls and not db.url_exists_in_sites(homepage):
                        db.add_links_batch([homepage], discovered_from=final_url, depth=0, priority=5)
                        queued_urls.add(homepage)
                        added += 1
                    if link not in queued_urls and link not in site_urls:
                        db.add_links_batch([link], discovered_from=final_url, depth=depth+1, priority=6)
                        queued_urls.add(link)
                        child_id = db.insert_site(link, link_domain)
                        db.insert_crawl_relation(site_id, child_id, final_url, link, depth+1)
                        added += 1

            elif CRAWL_MODE == 2:
                db.add_links_batch([link], discovered_from=final_url, depth=depth+1, priority=10)
                queued_urls.add(link)
                child_id = db.insert_site(link, link_domain)
                db.insert_crawl_relation(site_id, child_id, final_url, link, depth+1)
                added += 1

            elif CRAWL_MODE == 3:
                if link_domain == domain:
                    db.add_links_batch([link], discovered_from=final_url, depth=depth+1, priority=20)
                    queued_urls.add(link)
                    child_id = db.insert_site(link, link_domain)
                    db.insert_crawl_relation(site_id, child_id, final_url, link, depth+1)
                    added += 1
                else:
                    homepage = f"https://{link_domain}/"
                    if homepage not in queued_urls and homepage not in site_urls and not db.url_exists_in_sites(homepage):
                        db.add_links_batch([homepage], discovered_from=final_url, depth=0, priority=1)
                        queued_urls.add(homepage)
                        added += 1
                    if link not in queued_urls and link not in site_urls:
                        db.add_links_batch([link], discovered_from=final_url, depth=depth+1, priority=2)
                        queued_urls.add(link)
                        child_id = db.insert_site(link, link_domain)
                        db.insert_crawl_relation(site_id, child_id, final_url, link, depth+1)
                        added += 1

            elif CRAWL_MODE == 4:
                if db.is_domain_indexed(link_domain):
                    priority = 1
                else:
                    priority = 50
                db.add_links_batch([link], discovered_from=final_url, depth=depth+1, priority=priority)
                queued_urls.add(link)
                child_id = db.insert_site(link, link_domain)
                db.insert_crawl_relation(site_id, child_id, final_url, link, depth+1)
                added += 1

    log.crawl(f"{final_url} (d={depth})")
    db.set_link_status(original_url, 'done')
    update_queue_file()

def run_infinite_crawler():
    global queued_urls, site_urls
    db.init_db()
    conn = db.get_crawler_conn()
    rows = conn.execute("SELECT url FROM links_to_crawl").fetchall()
    queued_urls = {r['url'] for r in rows}
    rows = conn.execute("SELECT url FROM sites").fetchall()
    site_urls = {r['url'] for r in rows}
    conn.close()
    update_queue_file()

    threading.Thread(target=queue_monitor, daemon=True).start()

    DEFAULT_FEED = 'feeds/urls.txt'
    if os.path.exists(DEFAULT_FEED):
        log.info(f"Auto-loading feeds from {DEFAULT_FEED}")
        from feed_loader import load_feed
        load_feed(DEFAULT_FEED)
        conn = db.get_crawler_conn()
        rows = conn.execute("SELECT url FROM links_to_crawl").fetchall()
        queued_urls.update(r['url'] for r in rows)
        conn.close()
        update_queue_file()

    mode_names = {1: 'Internal First', 2: 'All Equal', 3: 'Discover New Sites', 4: 'Recrawl Indexed'}
    log.info(f"Background crawler started ({CRAWLER_THREADS} workers) [Mode {CRAWL_MODE}: {mode_names.get(CRAWL_MODE, 'Unknown')}]...")
    with ThreadPoolExecutor(max_workers=CRAWLER_THREADS) as executor:
        while True:
            urls = db.get_pending_links(limit=CRAWLER_THREADS)
            if not urls:
                log.warning("Queue empty, sleeping 1s...")
                time.sleep(1)
                continue
            for u in urls:
                db.set_link_status(u['url'], 'crawling')
            futures = {executor.submit(crawl_single, u): u for u in urls}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    url = futures[f]['url']
                    log.critical(f"{url}: {e}")
                    db.set_link_failed(url)

if __name__ == '__main__':
    import sys
    mode = 1
    if '--mode' in sys.argv:
        idx = sys.argv.index('--mode')
        if idx + 1 < len(sys.argv):
            mode = int(sys.argv[idx+1])
    CRAWL_MODE = mode
    run_infinite_crawler()