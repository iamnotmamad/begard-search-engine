# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
import database as db
from datetime import datetime

def recrawl_all():
    """تمام سایت‌های خزش‌شده را با اولویت پایین دوباره به صف اضافه می‌کند."""
    conn = db.get_conn()
    sites = conn.execute("SELECT url FROM sites WHERE status='crawled'").fetchall()
    conn.close()
    added = 0
    for site in sites:
        # اولویت 100 برای بازخزش (کمترین فوریت)
        db.add_links_batch([site['url']], discovered_from='recrawl', depth=0, priority=100)
        added += 1
    print(f"[SCHEDULER] Recrawling {added} sites (priority 100).")

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(recrawl_all, 'interval', hours=6, next_run_time=datetime.now())
    scheduler.start()