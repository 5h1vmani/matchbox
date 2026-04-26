// Matchbox web — small client glue. Keep minimal; HTMX + Alpine handle most.

// Global top progress bar — animates while any HTMX request is in flight.
let _inFlight = 0;
function _setProgress(scale) {
    const bar = document.getElementById('global-progress');
    if (bar) bar.style.transform = `scaleX(${scale})`;
}
document.addEventListener('htmx:beforeRequest', (e) => {
    _inFlight++;
    _setProgress(0.4);
    const t = e.detail.elt;
    if (t.tagName === 'BUTTON') t.setAttribute('disabled', 'disabled');
});

document.addEventListener('htmx:afterRequest', (e) => {
    _inFlight = Math.max(0, _inFlight - 1);
    if (_inFlight === 0) {
        _setProgress(1);
        setTimeout(() => _setProgress(0), 200);
    }
    const t = e.detail.elt;
    if (t.tagName === 'BUTTON') t.removeAttribute('disabled');
});

// B5: surface server errors as toasts instead of failing silently.
document.addEventListener('htmx:responseError', (e) => {
    const status = e.detail.xhr.status;
    let msg = `Request failed (${status})`;
    try {
        const body = JSON.parse(e.detail.xhr.responseText);
        if (body.detail) msg = `${status}: ${body.detail}`;
    } catch {
        if (e.detail.xhr.responseText && e.detail.xhr.responseText.length < 200) {
            msg = `${status}: ${e.detail.xhr.responseText}`;
        }
    }
    document.body.dispatchEvent(new CustomEvent('matchbox:toast', {
        detail: { message: msg, level: 'error' }
    }));
});

document.addEventListener('htmx:sendError', () => {
    document.body.dispatchEvent(new CustomEvent('matchbox:toast', {
        detail: { message: 'Network error — is the server running?', level: 'error' }
    }));
});

// Filter form refresh trigger.
document.body.addEventListener('rows:refresh', () => {
    const filters = document.getElementById('filters');
    if (filters) htmx.trigger(filters, 'change');
});

// ─────────────────────────────────────────────────────────
// Cmd+K palette keyboard navigation (M3 / item #21 polish).
// Selects results inside #palette-results and routes ↑↓Enter to them.
// ─────────────────────────────────────────────────────────
function paletteNav() {
    return {
        cursor: -1,
        items() { return Array.from(document.querySelectorAll('#palette-results a[href]')); },
        moveCursor(delta) {
            const items = this.items();
            if (items.length === 0) return;
            this.cursor = (this.cursor + delta + items.length) % items.length;
            items.forEach((el, i) => {
                if (i === this.cursor) {
                    el.classList.add('bg-indigo-50', 'ring-1', 'ring-indigo-200');
                    el.scrollIntoView({ block: 'nearest' });
                } else {
                    el.classList.remove('bg-indigo-50', 'ring-1', 'ring-indigo-200');
                }
            });
        },
        openCursor() {
            const items = this.items();
            const target = items[this.cursor >= 0 ? this.cursor : 0];
            if (target) target.click();
        },
    };
}
window.paletteNav = paletteNav;

// Re-fetch the open detail panel (used after undo, bulk actions, etc.).
function refreshOpenDetail() {
    const panel = document.querySelector('#detail-panel [data-job-id]');
    if (!panel) return;
    const jobId = panel.dataset.jobId;
    const profile = location.pathname.split('/')[2];
    htmx.ajax('GET', `/p/${profile}/jobs/${jobId}/detail`, {
        target: '#detail-panel',
        swap: 'innerHTML',
    });
}
window.refreshOpenDetail = refreshOpenDetail;

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
                        // Refresh BOTH the rows (so the row's state badge updates)
                        // AND the open detail panel (so it reflects the reverted state).
                        const filters = document.getElementById('filters');
                        if (filters) htmx.trigger(filters, 'change');
                        if (typeof window.refreshOpenDetail === 'function') {
                            window.refreshOpenDetail();
                        }
                        showToast({ message: 'Undone', level: 'success' });
                    } else {
                        showToast({ message: `Undo failed (${res.status})`, level: 'error' });
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
