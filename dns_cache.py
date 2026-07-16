# dns_cache.py
import socket
import time

_dns_cache = {}
_cache_ttl = 3600  # 1 hour

def cached_getaddrinfo(host, port=0, family=0, type=0, proto=0, flags=0):
    key = (host, port)
    now = time.time()
    if key in _dns_cache and now - _dns_cache[key][1] < _cache_ttl:
        return _dns_cache[key][0]
    try:
        result = socket.getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        result = None
    _dns_cache[key] = (result, now)
    return result

def install_dns_cache():
    # جایگزینی تابع اصلی getaddrinfo با نسخهٔ کش‌شده
    # در هر نخ جداگانه اعمال می‌شود، اما برای سادگی اینجا انجام می‌دهیم
    import urllib3.util.connection
    # urllib3 از socket.create_connection استفاده می‌کند. نمی‌توانیم مستقیم getaddrinfo را عوض کنیم.
    # در عوض می‌توانیم با monkey-patching resolver کار کنیم.
    # یک راه ساده: نصب resolver سفارشی برای requests با استفاده از adapters.
    pass  # برای جلوگیری از پیچیدگی، از یک راه‌حل ساده‌تر استفاده می‌کنیم: