# log_utils.py
import colorama
from colorama import Fore, Style
from datetime import datetime

colorama.init(autoreset=True)

def _time():
    return datetime.now().strftime('%H:%M:%S')

def info(msg):
    print(f"{Fore.CYAN}[{_time()} INFO]{Style.RESET_ALL} {msg}")

def success(msg):
    print(f"{Fore.GREEN}[{_time()} OK]{Style.RESET_ALL} {msg}")

def warning(msg):
    print(f"{Fore.YELLOW}[{_time()} WARN]{Style.RESET_ALL} {msg}")

def error(msg):
    print(f"{Fore.RED}[{_time()} ERROR]{Style.RESET_ALL} {msg}")

def critical(msg):
    print(f"{Fore.MAGENTA}[{_time()} CRIT]{Style.RESET_ALL} {msg}")

def crawl(msg):
    print(f"{Fore.BLUE}[{_time()} CRAWL]{Style.RESET_ALL} {msg}")

def skip(msg):
    print(f"{Fore.LIGHTBLACK_EX}[{_time()} SKIP]{Style.RESET_ALL} {msg}")

def index(msg):
    print(f"{Fore.LIGHTGREEN_EX}[{_time()} INDEX]{Style.RESET_ALL} {msg}")