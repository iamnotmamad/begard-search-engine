# app.py
from flask import Flask, render_template, request, jsonify, url_for
from flask_compress import Compress
from markupsafe import Markup
import database as db
from indexer import tokenize
import threading
from crawler_first import run_infinite_crawler
from scheduler import start_scheduler
import difflib
import time
import math
from urllib.parse import urlparse
import os
import csv
import re
from datetime import datetime

app = Flask(__name__)
Compress(app)

INDEXED_WORDS = []
LAST_WORD_UPDATE = 0
search_cache = {}
site_cache = {}

def get_site_cached(site_id):
    if site_id not in site_cache:
        site_cache[site_id] = db.get_site_by_id(site_id)
    return site_cache[site_id]

def update_indexed_words():
    global INDEXED_WORDS, LAST_WORD_UPDATE
    conn = db.get_index_conn()
    rows = conn.execute("SELECT DISTINCT word FROM inverted_index").fetchall()
    INDEXED_WORDS = [row[0] for row in rows]
    conn.close()
    LAST_WORD_UPDATE = time.time()

# ---------- پارامترهای BM25 ----------
K1 = 1.5
B = 0.75
WEIGHTS = {
    'title': 5.0,
    'meta_description': 3.0,
    'meta_keywords': 3.0,
    'hashtags': 4.0,
    'content': 1.0
}

# ---------- تنوع دامنه ----------
def diversify_results(results, max_consecutive=2):
    if not results:
        return results
    diversified = []
    domain_positions = {}
    remaining = list(results)
    while remaining:
        selected = None
        for i, res in enumerate(remaining):
            domain = res['domain']
            last_pos = domain_positions.get(domain, -1)
            if len(diversified) - last_pos > max_consecutive:
                selected = i
                break
        if selected is None:
            selected = 0
        res = remaining.pop(selected)
        diversified.append(res)
        domain_positions[res['domain']] = len(diversified) - 1
    return diversified

# ---------- صفحه‌بندی ----------
def pagination(page, total_pages, query):
    if total_pages <= 1:
        return Markup('')
    html = '<div class="pagination">'
    if page > 1:
        html += f'<a class="page" href="/search?q={query}&page=1">۱</a>'
    else:
        html += '<span class="page current">۱</span>'
    if page > 1:
        html += f'<a class="page prev-next" href="/search?q={query}&page={page-1}">&lt;</a>'
    else:
        html += '<span class="page disabled">&lt;</span>'
    html += f'<span class="page current">{page}</span>'
    if page < total_pages:
        html += f'<a class="page prev-next" href="/search?q={query}&page={page+1}">&gt;</a>'
    else:
        html += '<span class="page disabled">&gt;</span>'
    if page < total_pages:
        html += f'<a class="page" href="/search?q={query}&page={total_pages}">{total_pages}</a>'
    else:
        html += f'<span class="page current">{total_pages}</span>'
    html += '</div>'
    return Markup(html)

app.add_template_global(pagination, 'pagination')

# ---------- مسیرها ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/popular')
def popular():
    popular = db.get_top_popular_searches(4)
    return jsonify(popular)

@app.route('/suggest')
def suggest():
    q = request.args.get('q', '').strip()
    if not q:
        popular = db.get_top_popular_searches(4)
        return jsonify(popular)
    suggestions = []
    exact = db.get_exact_search_matches(q, limit=2)
    suggestions.extend(exact)
    similar = db.get_similar_searches(q, limit=2)
    for s in similar:
        if s not in suggestions:
            suggestions.append(s)
    if time.time() - LAST_WORD_UPDATE > 300:
        update_indexed_words()
    if INDEXED_WORDS:
        matches = difflib.get_close_matches(q, INDEXED_WORDS, n=2, cutoff=0.6)
        for w in matches:
            if w not in suggestions:
                suggestions.append(w)
    return jsonify(suggestions[:4])

@app.route('/history/delete', methods=['POST'])
def delete_history():
    data = request.get_json()
    query = data.get('query')
    if query:
        db.delete_search_history(query)
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/search')
def search():
    global site_cache
    t_start = time.time()
    if time.time() - LAST_WORD_UPDATE > 300:
        update_indexed_words()

    raw_query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    auto_corrected = False

    # ----- تجزیهٔ site: -----
    filter_domain = None
    search_query = raw_query
    site_pattern = r'^site:([^\s]+)\s*(.*)'
    match = re.match(site_pattern, raw_query)
    if match:
        filter_domain = match.group(1).lower()
        search_query = match.group(2).strip()
        if not search_query:
            search_query = ''

    # فقط site:
    if not search_query and filter_domain:
        conn = db.get_crawler_conn()
        rows = conn.execute("SELECT id FROM sites WHERE domain=? LIMIT 100", (filter_domain,)).fetchall()
        conn.close()
        results = []
        for row in rows:
            site = get_site_cached(row['id'])
            if site:
                domain = site['domain'] or urlparse(site['url']).netloc
                favicon = url_for('static', filename=f'favicons/{domain}.ico')
                sitelinks = []
                # تشخیص homepage بودن با URL
                if site['url'] == f"https://{domain}" or site['url'] == f"http://{domain}":
                    raw_sitelinks = db.get_top_sitelinks(domain)
                    sitelinks = [link for link in raw_sitelinks if link['title']]
                results.append({
                    'title': site['title'] or site['url'],
                    'url': site['url'],
                    'description': site['meta_description'] or (site['content_text'][:200] if site['content_text'] else ''),
                    'domain': domain,
                    'favicon': favicon,
                    'sitelinks': sitelinks,
                    'score': 0
                })
        results = diversify_results(results)
        total = len(results)
        total_pages = max(1, (total + per_page - 1) // per_page)
        paged_results = results[offset:offset+per_page]
        return render_template('results.html',
                               query=raw_query,
                               results=paged_results,
                               count=total,
                               suggestion=None,
                               auto_corrected=False,
                               page=page,
                               total_pages=total_pages,
                               word_suggestions=[])

    # ---------- جستجوی عادی ----------
    tokens = tokenize(search_query)
    if not tokens:
        return render_template('results.html', query=raw_query, results=[], count=0, suggestion=None)

    db.add_search_history(raw_query)

    valid_tokens = [t for t in tokens if t in INDEXED_WORDS]
    if not valid_tokens:
        suggestion = difflib.get_close_matches(search_query, INDEXED_WORDS, n=1, cutoff=0.8)
        suggestion = suggestion[0] if suggestion else None
        return render_template('results.html', query=raw_query, results=[], count=0, suggestion=suggestion)

    if len(valid_tokens) < len(tokens):
        expanded = list(valid_tokens)
        for t in tokens:
            if t not in INDEXED_WORDS:
                matches = difflib.get_close_matches(t, INDEXED_WORDS, n=2, cutoff=0.75)
                expanded.extend(matches)
        tokens = list(set(expanded))

    cache_key = (tuple(tokens), page, per_page, filter_domain)
    cached = search_cache.get(cache_key)
    if cached:
        return render_template('results.html', **cached)

    # ----- FTS5 + BM25F -----
    fts_query = ' AND '.join(f'"{w}"' for w in tokens)
    conn_idx = db.get_index_conn()

    if filter_domain:
        candidate_rows = conn_idx.execute(f'''
            SELECT ii.site_id, SUM(ii.rank) as rank_sum
            FROM inverted_index ii
            JOIN sites s ON ii.site_id = s.id
            WHERE ii.inverted_index MATCH ? AND s.domain = ?
            GROUP BY ii.site_id
            ORDER BY rank_sum DESC
            LIMIT 150
        ''', (fts_query, filter_domain)).fetchall()
    else:
        candidate_rows = conn_idx.execute(f'''
            SELECT site_id, SUM(rank) as rank_sum
            FROM inverted_index
            WHERE inverted_index MATCH ?
            GROUP BY site_id
            ORDER BY rank_sum DESC
            LIMIT 150
        ''', (fts_query,)).fetchall()

    if not candidate_rows:
        suggestion = difflib.get_close_matches(search_query, INDEXED_WORDS, n=1, cutoff=0.8)
        if suggestion:
            suggestion = suggestion[0]
            suggested_tokens = tokenize(suggestion)
            if suggested_tokens:
                suggested_fts = ' AND '.join(f'"{w}"' for w in suggested_tokens)
                if filter_domain:
                    candidate_rows = conn_idx.execute(f'''
                        SELECT ii.site_id, SUM(ii.rank) as rank_sum
                        FROM inverted_index ii
                        JOIN sites s ON ii.site_id = s.id
                        WHERE ii.inverted_index MATCH ? AND s.domain = ?
                        GROUP BY ii.site_id
                        ORDER BY rank_sum DESC
                        LIMIT 150
                    ''', (suggested_fts, filter_domain)).fetchall()
                else:
                    candidate_rows = conn_idx.execute(f'''
                        SELECT site_id, SUM(rank) as rank_sum
                        FROM inverted_index
                        WHERE inverted_index MATCH ?
                        GROUP BY site_id
                        ORDER BY rank_sum DESC
                        LIMIT 150
                    ''', (suggested_fts,)).fetchall()
                if candidate_rows:
                    auto_corrected = True
                    tokens = suggested_tokens
                else:
                    suggestion = None
        else:
            suggestion = None

        if not candidate_rows:
            conn_idx.close()
            result_data = {
                'query': raw_query,
                'results': [],
                'count': 0,
                'suggestion': suggestion,
                'auto_corrected': False,
                'page': page,
                'total_pages': 1,
                'word_suggestions': []
            }
            return render_template('results.html', **result_data)

    # ----- محاسبه BM25F -----
    N = db.get_total_docs()
    idf_cache = {w: db.get_idf(w) for w in tokens}
    site_ids = [row['site_id'] for row in candidate_rows]

    placeholders_sites = ','.join('?' for _ in site_ids)
    placeholders_words = ','.join('?' for _ in tokens)

    stats_rows = conn_idx.execute(f'''
        SELECT
            ii.site_id,
            ii.word,
            ii.field,
            ii.term_freq,
            ds.length as field_length,
            avg_len.avg_len as avg_field_length
        FROM inverted_index ii
        JOIN doc_stats ds ON ii.site_id = ds.site_id AND ii.field = ds.field
        LEFT JOIN (
            SELECT field, AVG(length) as avg_len
            FROM doc_stats
            GROUP BY field
        ) avg_len ON ii.field = avg_len.field
        WHERE ii.word IN ({placeholders_words})
          AND ii.site_id IN ({placeholders_sites})
    ''', tokens + site_ids).fetchall()

    from collections import defaultdict
    site_data = defaultdict(list)
    for row in stats_rows:
        site_data[row['site_id']].append(row)

    scored_sites = []
    for sid in site_ids:
        score = 0.0
        if sid in site_data:
            for trow in site_data[sid]:
                field = trow['field']
                tf = trow['term_freq']
                word = trow['word']
                field_len = trow['field_length'] or 1
                avg_len = trow['avg_field_length'] or 1
                tf_score = (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * field_len / avg_len))
                score += WEIGHTS.get(field, 1.0) * idf_cache[word] * tf_score
        scored_sites.append((sid, score))

    scored_sites.sort(key=lambda x: x[1], reverse=True)
    total = len(scored_sites)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page_sites = scored_sites[offset:offset+per_page]

    # ----- ساخت نتایج با اولویت جدید (فقط یک rich result) -----
    normal_results = []
    rich_result = None   # فقط یک rich result مجاز است

    for sid, score in page_sites:
        site = get_site_cached(sid)
        if not site:
            continue
        domain = site['domain'] or urlparse(site['url']).netloc
        favicon = url_for('static', filename=f'favicons/{domain}.ico')

        # تشخیص homepage بودن: مسیر ریشه (/) یا خالی
        parsed_url = urlparse(site['url'])
        is_homepage = (parsed_url.path in ('', '/'))

        sitelinks = []
        if is_homepage:
            raw_sitelinks = db.get_top_sitelinks(domain)
            sitelinks = [link for link in raw_sitelinks if link['title']]

        # اگر homepage باشد و sitelink داشته باشد و هنوز rich_result نداریم
        if is_homepage and sitelinks and rich_result is None:
            rich_result = {
                'title': site['title'] or site['url'],
                'url': site['url'],
                'description': site['meta_description'] or (site['content_text'][:200] if site['content_text'] else ''),
                'domain': domain,
                'favicon': favicon,
                'sitelinks': sitelinks,
                'score': score
            }
        else:
            # بقیهٔ نتایج بدون sitelink
            normal_results.append({
                'title': site['title'] or site['url'],
                'url': site['url'],
                'description': site['meta_description'] or (site['content_text'][:200] if site['content_text'] else ''),
                'domain': domain,
                'favicon': favicon,
                'sitelinks': [],
                'score': score
            })
    # تنوع دامنه روی normal_results
    normal_results.sort(key=lambda x: x['score'], reverse=True)
    normal_results = diversify_results(normal_results)

    final_results = []
    if rich_result:
        final_results.append(rich_result)
    final_results.extend(normal_results)
    paged_final = final_results[:per_page]

    word_suggestions = []
    if total < 10 and INDEXED_WORDS:
        word_suggestions = difflib.get_close_matches(search_query, INDEXED_WORDS, n=7, cutoff=0.65)

    result_data = {
        'query': raw_query,
        'results': paged_final,
        'count': total,
        'suggestion': suggestion if auto_corrected else None,
        'auto_corrected': auto_corrected,
        'page': page,
        'total_pages': total_pages,
        'word_suggestions': word_suggestions
    }
    search_cache[cache_key] = result_data
    conn_idx.close()

    if len(site_cache) > 200:
        site_cache.clear()

    t_end = time.time()
    print(f"Search completed in {t_end - t_start:.4f}s")
    return render_template('results.html', **result_data)

# ---------- بازخورد ----------
@app.route('/feedback', methods=['POST'])
def feedback():
    data = request.get_json()
    query = data.get('query')
    vote = data.get('vote')
    if query and vote in ('like', 'dislike'):
        os.makedirs('feedback', exist_ok=True)
        filepath = os.path.join('feedback', 'data.csv')
        file_exists = os.path.isfile(filepath)
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['query', 'vote', 'timestamp'])
            writer.writerow([query, vote, datetime.now().isoformat()])
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

if __name__ == '__main__':
    import sys
    db.init_db()
    update_indexed_words()
    if '--web-only' not in sys.argv:
        crawler_thread = threading.Thread(target=run_infinite_crawler, daemon=True)
        crawler_thread.start()
        start_scheduler()
        print("Background crawler and scheduler started.")
    else:
        print("Running in web-only mode (crawler and scheduler disabled).")
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000, threads=8)