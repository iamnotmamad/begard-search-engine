# 🕸️ Begard

Begard یک موتور جستجوی سبک و متن‌باز است که صفحات وب را Crawl و Index می‌کند و نتایج را از طریق یک رابط کاربری ساده نمایش می‌دهد.


<p align="center">
  <img src="assets/shot.png" width="600">
</p>


## ✨ امکانات

- 🔎 جستجوی سریع بین صفحات ایندکس‌شده
- 🌐 Web Crawler
- 📑 مدیریت لیست URLها
- 💾 ذخیره اطلاعات در دیتابیس
- ⚡ رابط کاربری سبک با HTML/CSS/JavaScript
- 🇮🇷 پشتیبانی از فونت Vazir برای زبان فارسی

---

## 📁 ساختار پروژه

```
.
├── app.py                # برنامه اصلی Flask
├── start.py              # اجرای پروژه
├── crawler.py            # خزنده وب
├── crawler_first.py      # اولین مرحله Crawl
├── database.py           # مدیریت دیتابیس
├── dns_cache.py          # کش DNS
├── config.py             # تنظیمات پروژه
├── feeds/
│   └── urls.txt          # لیست سایت‌های اولیه
├── templates/
│   ├── index.html
│   └── results.html
└── static/
    ├── css/
    ├── js/
    └── fonts/
```

---

## 🚀 نصب

ابتدا پروژه را کلون کنید:

```bash
git clone https://github.com/USERNAME/begard.git
cd begard
```

سپس وابستگی‌ها را نصب کنید:

```bash
pip install -r requirements.txt
```

> اگر فایل `requirements.txt` وجود ندارد، پکیج‌های موردنیاز را به صورت دستی نصب کنید.

---

## ▶️ اجرا

```bash
python start.py
```

یا

```bash
python app.py
```

---

## 🌍 افزودن سایت برای Crawl

آدرس سایت‌ها را داخل فایل زیر قرار دهید:

```
feeds/urls.txt
```

هر سایت در یک خط:

```
https://example.com
https://openai.com
https://python.org
```

---

## 📸 رابط کاربری

- صفحه اصلی جستجو
- صفحه نمایش نتایج
- طراحی ساده و سبک
- مناسب برای توسعه بیشتر

---

## 🛠️ تکنولوژی‌ها

- Python
- Flask
- HTML5
- CSS3
- JavaScript
- SQLite

---

## 📌 وضعیت پروژه

🚧 این پروژه هنوز در حال توسعه است و قابلیت‌های بیشتری در نسخه‌های آینده اضافه خواهند شد.

---

## 📄 مجوز

این پروژه تحت مجوز MIT منتشر شده است.

---

<div align="center">

**Made with ❤️ by persia Lab**

</div>
