// Matchbox web — small client glue. Keep minimal; HTMX + Alpine handle most.

document.addEventListener('htmx:beforeRequest', (e) => {
    const t = e.detail.elt;
    if (t.tagName === 'BUTTON') t.setAttribute('disabled', 'disabled');
});

document.addEventListener('htmx:afterRequest', (e) => {
    const t = e.detail.elt;
    if (t.tagName === 'BUTTON') t.removeAttribute('disabled');
});

// Filter form refresh trigger.
document.body.addEventListener('rows:refresh', () => {
    const filters = document.getElementById('filters');
    if (filters) htmx.trigger(filters, 'change');
});

// ─────────────────────────────────────────────────────────
// Toast system — single SSOT; receives `matchbox:toast` events
// triggered by the HX-Trigger response header from any route.
// Payload: { message: string, level?: "info"|"success"|"error",
//            undo?: { url: string, payload: { ... } } }
// ─────────────────────────────────────────────────────────
(function () {
    const HOST_ID = 'toast-host';
    const LEVEL_CLASS = {
        info:    'bg-slate-900',
        success: 'bg-emerald-700',
        error:   'bg-rose-700',
    };

    function showToast(detail) {
        const host = document.getElementById(HOST_ID);
        if (!host) return;
        const level = LEVEL_CLASS[detail.level] || LEVEL_CLASS.info;

        const el = document.createElement('div');
        el.className = `${level} text-white text-sm px-4 py-2 rounded-lg shadow-lg pointer-events-auto flex items-center gap-3`;

        const msg = document.createElement('span');
        msg.textContent = detail.message;
        el.appendChild(msg);

        if (detail.undo && detail.undo.url) {
            const btn = document.createElement('button');
            btn.textContent = 'Undo';
            btn.className = 'underline text-white/90 hover:text-white text-xs';
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                const fd = new FormData();
                for (const [k, v] of Object.entries(detail.undo.payload || {})) {
                    fd.append(k, v);
                }
                try {
                    const res = await fetch(detail.undo.url, { method: 'POST', body: fd });
                    if (res.ok) {
                        // Re-fetch the panel + rows to reflect the undo.
                        const filters = document.getElementById('filters');
                        if (filters) htmx.trigger(filters, 'change');
                        showToast({ message: 'Undone', level: 'success' });
                    }
                } catch (err) {
                    showToast({ message: 'Undo failed: ' + err, level: 'error' });
                }
                el.remove();
            });
            el.appendChild(btn);
        }

        host.appendChild(el);
        setTimeout(() => el.remove(), detail.undo ? 6000 : 2500);
    }

    document.body.addEventListener('matchbox:toast', (e) => showToast(e.detail));
})();
