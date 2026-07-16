document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search-input') || document.getElementById('main-search');
    const suggestionsBox = document.getElementById('suggestions-box');
    let debounceTimer;

    const POPULAR_CACHE_KEY = 'begard_popular_searches';
    const POPULAR_CACHE_TIME = 60 * 60 * 1000;

    function getCachedPopular() {
        const cached = localStorage.getItem(POPULAR_CACHE_KEY);
        if (cached) {
            try {
                const data = JSON.parse(cached);
                if (Date.now() - data.timestamp < POPULAR_CACHE_TIME) {
                    return data.queries;
                }
            } catch (e) {}
        }
        return null;
    }

    function cachePopular(queries) {
        localStorage.setItem(POPULAR_CACHE_KEY, JSON.stringify({
            queries: queries,
            timestamp: Date.now()
        }));
    }

    async function fetchPopular() {
        let popular = getCachedPopular();
        if (!popular) {
            try {
                const resp = await fetch('/popular');
                popular = await resp.json();
                cachePopular(popular);
            } catch (e) {
                popular = [];
            }
        }
        return popular;
    }

    searchInput.addEventListener('focus', async function() {
        if (searchInput.value.trim() === '') {
            const popular = await fetchPopular();
            if (popular.length > 0) {
                renderSuggestions(popular);
                suggestionsBox.style.display = 'block';
            }
        }
    });

    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        const query = searchInput.value.trim();
        if (query.length === 0) {
            fetchPopular().then(popular => {
                if (popular.length > 0) {
                    renderSuggestions(popular);
                    suggestionsBox.style.display = 'block';
                } else {
                    suggestionsBox.style.display = 'none';
                }
            });
            return;
        }
        if (query.length < 2) {
            suggestionsBox.style.display = 'none';
            return;
        }
        debounceTimer = setTimeout(async () => {
            try {
                const resp = await fetch(`/suggest?q=${encodeURIComponent(query)}`);
                const data = await resp.json();
                if (data.length > 0) {
                    renderSuggestions(data);
                    suggestionsBox.style.display = 'block';
                } else {
                    suggestionsBox.style.display = 'none';
                }
            } catch (e) {
                suggestionsBox.style.display = 'none';
            }
        }, 300);
    });

    function renderSuggestions(items) {
        suggestionsBox.innerHTML = '';
        items.forEach(item => {
            const div = document.createElement('div');
            div.className = 'suggestion-item';
            div.textContent = item;
            div.addEventListener('click', () => {
                searchInput.value = item;
                suggestionsBox.style.display = 'none';
                searchInput.form.submit();
            });
            suggestionsBox.appendChild(div);
        });
    }

    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !suggestionsBox.contains(e.target)) {
            suggestionsBox.style.display = 'none';
        }
    });

    const voteButtons = document.querySelectorAll('.vote-btn');
    const msg = document.querySelector('.feedback-msg');
    if (voteButtons.length > 0) {
        const query = document.querySelector('.vote-buttons')?.dataset.query;
        voteButtons.forEach(btn => {
            btn.addEventListener('click', async () => {
                const vote = btn.dataset.vote;
                try {
                    const resp = await fetch('/feedback', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({query: query, vote: vote})
                    });
                    if (resp.ok) {
                        msg.textContent = 'بازخورد شما ثبت شد. سپاسگزاریم!';
                        voteButtons.forEach(b => b.disabled = true);
                    } else {
                        msg.textContent = 'خطا در ثبت بازخورد.';
                    }
                } catch (e) {
                    msg.textContent = 'خطا در ارتباط با سرور.';
                }
            });
        });
    }
});