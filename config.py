# config.py
import os
from dotenv import load_dotenv

load_dotenv()

USER_AGENT = os.getenv('USER_AGENT', 'begardBot/1.0')
CRAWLER_TIMEOUT = int(os.getenv('CRAWLER_TIMEOUT', '8'))
TIMEOUT = CRAWLER_TIMEOUT                     # نام مستعار برای خزنده‌ها

CRAWLER_DELAY = float(os.getenv('CRAWLER_DELAY', '0.1'))
DELAY_BETWEEN_SAME_DOMAIN = CRAWLER_DELAY     # نام مستعار

CRAWLER_THREADS = int(os.getenv('CRAWLER_THREADS', '20'))
INDEXER_THREADS = int(os.getenv('INDEXER_THREADS', '2'))

CRAWLER_DB_PATH = os.getenv('CRAWLER_DB_PATH', 'crawler.db')
INDEX_DB_PATH = os.getenv('INDEX_DB_PATH', 'index.db')

EXCLUDED_EXTENSIONS = os.getenv(
    'EXCLUDED_EXTENSIONS',
    '.pdf,.zip,.rar,.mp4,.mp3,.avi,.mov,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.gif,.svg,.webp,.exe,.dmg,.bz2,.gz,.tar,.7z'
).split(',')