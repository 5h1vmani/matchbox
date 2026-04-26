// Matchbox web — small client glue. Keep minimal; HTMX + Alpine handle most.

document.addEventListener('htmx:beforeRequest', (e) => {
    // Disable double-submits.
    const t = e.detail.elt;
    if (t.tagName === 'BUTTON') t.setAttribute('disabled', 'disabled');
});

document.addEventListener('htmx:afterRequest', (e) => {
    const t = e.detail.elt;
    if (t.tagName === 'BUTTON') t.removeAttribute('disabled');
});

// Listen for HX-Trigger header from server to refresh rows.
document.body.addEventListener('rows:refresh', () => {
    const filters = document.getElementById('filters');
    if (filters) htmx.trigger(filters, 'change');
});
