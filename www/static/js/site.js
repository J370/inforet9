document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.querySelector('.search-wrap input[name="q"]');
    const quickQueries = document.querySelectorAll('.quick-query');

    quickQueries.forEach((button) => {
        button.addEventListener('click', () => {
            if (!searchInput) {
                return;
            }
            searchInput.value = button.dataset.query || '';
            searchInput.closest('form').submit();
        });
    });

    const readCookie = (name) => {
        const cookieValue = document.cookie
            .split(';')
            .map((cookie) => cookie.trim())
            .find((cookie) => cookie.startsWith(`${name}=`));
        return cookieValue ? decodeURIComponent(cookieValue.split('=').slice(1).join('=')) : '';
    };

    const relevanceControls = document.querySelectorAll('.relevance-controls');
    const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = readCookie('csrftoken') || (csrfTokenMeta ? csrfTokenMeta.content : '');
    relevanceControls.forEach((control) => {
        const buttons = control.querySelectorAll('.relevance-btn');
        const status = control.querySelector('.relevance-status');
        buttons.forEach((button) => {
            button.addEventListener('click', async () => {
                const baseVote = Number(button.dataset.vote || 0);
                if (![1, -1].includes(baseVote)) {
                    return;
                }
                const vote = button.classList.contains('active') ? 0 : baseVote;

                buttons.forEach((btn) => {
                    btn.disabled = true;
                });
                if (status) {
                    status.textContent = 'Saving...';
                    status.classList.remove('saved', 'error');
                }
                try {
                    const response = await fetch('/feedback/relevance/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken,
                        },
                        credentials: 'same-origin',
                        body: JSON.stringify({
                            query: control.dataset.query || '',
                            item_key: control.dataset.itemKey || '',
                            vote,
                            profile: {
                                dish: control.dataset.dish || '',
                                stall: control.dataset.stall || '',
                                hawker_centre: control.dataset.hawkerCentre || '',
                                review: control.dataset.review || '',
                            },
                        }),
                    });

                    if (!response.ok) {
                        throw new Error('Failed to save relevance feedback.');
                    }

                    buttons.forEach((btn) => {
                        const btnVote = Number(btn.dataset.vote || 0);
                        btn.classList.toggle('active', vote !== 0 && btnVote === vote);
                    });
                    if (status) {
                        status.textContent = vote === 0 ? 'Cleared' : 'Saved';
                        status.classList.remove('error');
                        status.classList.add('saved');
                    }
                } catch (_error) {
                    if (status) {
                        status.textContent = 'Failed';
                        status.classList.remove('saved');
                        status.classList.add('error');
                    }
                } finally {
                    buttons.forEach((btn) => {
                        btn.disabled = false;
                    });
                }
            });
        });
    });

    const insightsDropdown = document.getElementById('insights-dropdown');
    if (!insightsDropdown) {
        return;
    }

    const mapEl = document.getElementById('hawker-map');
    const mapDataEl = document.getElementById('hawker-map-data');
    let mapPoints = [];
    try {
        const raw = mapDataEl ? mapDataEl.textContent : '[]';
        mapPoints = JSON.parse(raw);
    } catch (_error) {
        mapPoints = [];
    }

    let map = null;
    let mapInitialized = false;

    const initMap = () => {
        if (!mapEl || typeof window.L === 'undefined') {
            return;
        }

        if (mapInitialized) {
            if (map) {
                map.invalidateSize();
            }
            return;
        }

        map = window.L.map(mapEl, {
            zoomControl: true,
            scrollWheelZoom: false,
        });

        window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors',
            referrerPolicy: 'origin',
        }).addTo(map);

        if (!mapPoints.length) {
            map.setView([1.3521, 103.8198], 11);
            mapInitialized = true;
            return;
        }

        const bounds = [];
        mapPoints.forEach((point) => {
            const marker = window.L.marker([point.lat, point.lng]).addTo(map);
            const accuracyLabel = point.is_exact ? 'Exact' : 'Approximate by region';
            marker.bindPopup(
                `<strong>${point.name}</strong><br>${point.region}<br>Matched reviews: ${point.review_count}<br>${accuracyLabel}`
            );
            bounds.push([point.lat, point.lng]);
        });

        map.fitBounds(bounds, { padding: [28, 28] });
        mapInitialized = true;
    };

    const wordCloudCanvas = document.getElementById('wordcloud-canvas');
    const wordCloudDataEl = document.getElementById('word-cloud-data');
    let wordCloudRendered = false;

    const renderWordCloud = () => {
        if (wordCloudRendered || !wordCloudCanvas || typeof window.WordCloud === 'undefined') {
            return;
        }

        let terms = [];
        try {
            const raw = wordCloudDataEl ? wordCloudDataEl.textContent : '[]';
            terms = JSON.parse(raw);
        } catch (_error) {
            terms = [];
        }

        if (!Array.isArray(terms) || !terms.length) {
            return;
        }

        const dpr = window.devicePixelRatio || 1;
        const width = Math.max(320, wordCloudCanvas.clientWidth || 700);
        const height = Math.max(220, wordCloudCanvas.clientHeight || 330);
        wordCloudCanvas.width = Math.round(width * dpr);
        wordCloudCanvas.height = Math.round(height * dpr);
        const ctx = wordCloudCanvas.getContext('2d');
        if (ctx) {
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }

        const list = terms
            .filter((term) => term && term.word && Number(term.count) > 0)
            .map((term) => [term.word, Number(term.count)]);

        if (!list.length) {
            return;
        }

        const sortedWeights = list.map((item) => item[1]).sort((a, b) => b - a);
        const maxWeight = sortedWeights[0] || 1;
        const minWeight = sortedWeights[sortedWeights.length - 1] || 1;
        const spread = Math.max(1, maxWeight - minWeight);
        const palette = ['#1f5d2d', '#2f7a3c', '#5c4a2a', '#7c6837', '#38553f'];

        window.WordCloud(wordCloudCanvas, {
            list,
            shape: 'circle',
            rotateRatio: 0.24,
            rotationSteps: 2,
            minRotation: -Math.PI / 2,
            maxRotation: Math.PI / 2,
            gridSize: Math.max(8, Math.round(wordCloudCanvas.offsetWidth / 44)),
            drawOutOfBound: false,
            backgroundColor: 'transparent',
            fontFamily: 'Nunito, sans-serif',
            weightFactor(weight) {
                const normalized = (weight - minWeight) / spread;
                return 14 + normalized * 58;
            },
            color(word, weight) {
                const idx = (word.length + Math.round(weight)) % palette.length;
                return palette[idx];
            },
            classes: 'wordcloud-rendered-term',
        });
        wordCloudRendered = true;
    };

    if (insightsDropdown.open) {
        initMap();
        renderWordCloud();
    }

    insightsDropdown.addEventListener('toggle', () => {
        if (!insightsDropdown.open) {
            return;
        }
        // Give the details element a beat to finish layout before map sizing.
        window.requestAnimationFrame(() => {
            initMap();
            renderWordCloud();
            if (map) {
                map.invalidateSize();
            }
        });
    });
});
