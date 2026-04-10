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

    const mapEl = document.getElementById('hawker-map');
    if (!mapEl || typeof window.L === 'undefined') {
        return;
    }

    const mapDataEl = document.getElementById('hawker-map-data');
    let mapPoints = [];
    try {
        const raw = mapDataEl ? mapDataEl.textContent : '[]';
        mapPoints = JSON.parse(raw);
    } catch (_error) {
        mapPoints = [];
    }

    const map = window.L.map(mapEl, {
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
        return;
    }

    const bounds = [];
    mapPoints.forEach((point) => {
        const marker = window.L.marker([point.lat, point.lng]).addTo(map);
        const accuracyLabel = point.is_exact ? 'Exact' : 'Approximate by region';
        marker.bindPopup(
            `<strong>${point.name}</strong><br>${point.region}<br>Reviews on page: ${point.review_count}<br>${accuracyLabel}`
        );
        bounds.push([point.lat, point.lng]);
    });

    map.fitBounds(bounds, { padding: [28, 28] });
});
