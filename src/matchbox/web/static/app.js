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

// ─────────────────────────────────────────────────────────
// Focus trap for modals (WCAG AA / ALERT 1).
// Any element with [data-focus-trap] that is currently visible (offsetParent
// non-null) wins; Tab + Shift+Tab cycle within it. The topmost such element
// in DOM order takes precedence so nested modals nest cleanly.
// ─────────────────────────────────────────────────────────
const _FOCUSABLE_SEL = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled]):not([type=hidden])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
].join(',');

function _visibleModals() {
    return Array.from(document.querySelectorAll('[data-focus-trap]'))
                .filter(el => el.offsetParent !== null);
}

function _focusableIn(container) {
    return Array.from(container.querySelectorAll(_FOCUSABLE_SEL))
                .filter(el => el.offsetParent !== null);
}

document.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const modals = _visibleModals();
    if (modals.length === 0) return;
    const trap = modals[modals.length - 1];

    // If focus is outside the modal, pull it back in.
    if (!trap.contains(document.activeElement)) {
        e.preventDefault();
        const focusables = _focusableIn(trap);
        focusables[0]?.focus();
        return;
    }

    const focusables = _focusableIn(trap);
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    }
}, true);  // capture so we beat default tab behaviour even inside HTMX-swapped content

// When a modal becomes visible (added or x-show flips), move focus into it.
// Uses MutationObserver to catch dynamic modals (bulk tailor inserts via fetch).
new MutationObserver((mutations) => {
    for (const m of mutations) {
        for (const node of m.addedNodes) {
            if (node.nodeType !== 1) continue;
            const trap = node.matches?.('[data-focus-trap]') ? node : node.querySelector?.('[data-focus-trap]');
            if (trap && trap.offsetParent !== null) {
                _focusableIn(trap)[0]?.focus();
            }
        }
    }
}).observe(document.body, { childList: true, subtree: true });

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
