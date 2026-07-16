# indexer.py
import re
from collections import defaultdict
import database as db

def normalize_word(word):
    word = word.lower().strip()
    word = re.sub(r'^[^\w]+|[^\w]+$', '', word)
    return word

def tokenize(text):
    raw_words = re.split(r'\s+', text)
    tokens = []
    for w in raw_words:
        nw = normalize_word(w)
        if nw:
            tokens.append(nw)
    return tokens

def index_site(site_id, data):
    """
    data: dict with keys title, meta_desc, meta_keys, hashtags, content_text
    """
    db.clear_index_for_site(site_id)

    fields = {
        'title': data.get('title', ''),
        'meta_description': data.get('meta_desc', ''),
        'meta_keywords': data.get('meta_keys', '').replace(',', ' '),
        'hashtags': data.get('hashtags', ''),
        'content': data.get('content_text', '')
    }

    index_entries = []
    for field, text in fields.items():
        if not text:
            db.insert_doc_stat(site_id, field, 0)
            continue
        tokens = tokenize(text)
        length = len(tokens)
        db.insert_doc_stat(site_id, field, length)
        word_positions = defaultdict(list)
        for pos, token in enumerate(tokens):
            word_positions[token].append(pos)
        for word, pos_list in word_positions.items():
            pos_str = ','.join(str(p) for p in pos_list)
            index_entries.append((word, site_id, field, len(pos_list), pos_str))

    # درج گروهی در FTS5
    db.insert_index_batch(index_entries)

    # به‌روزرسانی IDF cache (می‌توان بعداً با زمان‌بند انجام داد، ولی اینجا هم فراخوانی می‌کنیم)
    db.compute_and_store_idf()