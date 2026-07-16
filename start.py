# start.py
import subprocess
import sys
import os
import time
import signal

DB_PATH = 'begard.db'

def clean_db_locks():
    for ext in ['-wal', '-shm']:
        lock_file = DB_PATH + ext
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                print(f"Removed stale lock file: {lock_file}")
            except PermissionError:
                pass

if __name__ == '__main__':
    clean_db_locks()
    print("Starting begard Search Engine...")

    # انتخاب حالت خزش
    print("\nSelect crawl mode:")
    print("  1 - Prioritize internal links (same domain)")
    print("  2 - Follow any discovered link equally")
    print("  3 - Discover new sites (external links first)")
    print("  4 - Re-crawl indexed sites to find new URLs")
    mode = input("Enter mode (1-4): ").strip()
    while mode not in ('1', '2', '3', '4'):
        mode = input("Invalid. Enter 1-4: ").strip()
    mode = int(mode)

    python = sys.executable

    crawler = subprocess.Popen([python, 'crawler_first.py', '--mode', str(mode)])
    print(f"Crawler started (PID: {crawler.pid}) with mode {mode}")
    time.sleep(2)

    webserver = subprocess.Popen([python, 'app.py', '--web-only'])
    print(f"Web server started (PID: {webserver.pid})")

    def shutdown(sig, frame):
        print("\nShutting down...")
        crawler.terminate()
        webserver.terminate()
        crawler.wait()
        webserver.wait()
        print("begard stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)