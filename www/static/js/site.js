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
});
