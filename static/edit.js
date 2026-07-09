// ============================================================
// Cart Tracker - Jurassic Park content editor
// Loads JP carts, lets a local operator edit contents + use-by
// date, and PATCHes the changes back to the server.
// ============================================================

const TARGET_LOCATION = 'Jurassic Park';

// The JP cart-ids currently rendered. null until the first load completes, so the
// SSE handler won't compare a live snapshot against an empty/absent baseline.
let shownJpIds = null;

// ---------- helpers ----------

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;',
    '"': '&quot;', "'": '&#39;'
  }[c]));
}

function setStatus(cls, text) {
  const el = document.getElementById('status');
  el.className = cls;
  el.textContent = text;
}

// DB stores dates as MM-DD-YYYY; <input type=date> wants YYYY-MM-DD.
function dbToPicker(s) {
  if (!s) return '';
  const parts = s.split('-');
  if (parts.length !== 3) return '';           // e.g. 'Return' / 'Empty'
  const [mm, dd, yyyy] = parts;
  if (mm.length !== 2 || dd.length !== 2 || yyyy.length !== 4) return '';
  return `${yyyy}-${mm}-${dd}`;
}

function pickerToDb(s) {
  if (!s) return '';
  const parts = s.split('-');
  if (parts.length !== 3) return '';
  const [yyyy, mm, dd] = parts;
  return `${mm}-${dd}-${yyyy}`;
}

// ---------- rendering ----------

function rowHtml(cart) {
  return `
    <div class="cart-row" data-cart-id="${cart.id}">
      <div class="cart-meta">
        <span class="cart-id">ID ${cart.id}</span>
        <span class="cart-name">${escapeHtml(cart.name)}</span>
      </div>
      <div class="field">
        <label for="contents-${cart.id}">Contents</label>
        <input type="text" id="contents-${cart.id}" class="contents-input"
               value="${escapeHtml(cart.contents)}">
      </div>
      <div class="field">
        <label for="date-${cart.id}">Use-by date</label>
        <input type="date" id="date-${cart.id}" class="date-input"
               value="${dbToPicker(cart.date_usage)}">
      </div>
      <button type="button" class="save-btn" data-save="${cart.id}">Save</button>
      <span class="row-msg" data-msg="${cart.id}"></span>
    </div>`;
}

function renderRows(carts) {
  const list = document.getElementById('cart-list');
  if (!carts.length) {
    list.innerHTML = `<p class="empty-note">No carts are currently in ${escapeHtml(TARGET_LOCATION)}.</p>`;
    return;
  }
  list.innerHTML = carts.map(rowHtml).join('');
  list.querySelectorAll('[data-save]').forEach(btn => {
    btn.addEventListener('click', () => saveCart(Number(btn.dataset.save)));
  });
}

// ---------- load ----------

async function loadCarts() {
  setStatus('connecting', 'Loading…');
  try {
    // The session cookie is sent automatically (same-origin); no header needed.
    const resp = await fetch('/api/carts');
    if (resp.status === 401) {
      // Session expired or logged out -> send the operator back to the login form.
      location.href = '/login';
      return;
    }
    if (!resp.ok) {
      setStatus('error', `Load failed (${resp.status})`);
      return;
    }
    const carts = await resp.json();
    const jpCarts = carts
      .filter(c => c.current_location === TARGET_LOCATION)
      .sort((a, b) => a.id - b.id);
    renderRows(jpCarts);
    shownJpIds = jpCarts.map(c => c.id);   // baseline for staleness comparison
    hideBanner();                          // this render is now the fresh truth
    setStatus('ok', `Loaded ${jpCarts.length} cart(s)`);
  } catch (err) {
    console.error(err);
    setStatus('error', 'Network error');
  }
}

// ---------- save ----------

function setRowMsg(cartId, cls, text) {
  const el = document.querySelector(`[data-msg="${cartId}"]`);
  if (el) {
    el.className = 'row-msg ' + cls;
    el.textContent = text;
  }
}

async function saveCart(cartId) {
  const contents = document.getElementById(`contents-${cartId}`).value.trim();
  const pickerVal = document.getElementById(`date-${cartId}`).value;
  const dateUsage = pickerToDb(pickerVal);

  if (!contents) {
    setRowMsg(cartId, 'error', 'Contents required');
    return;
  }
  if (!dateUsage) {
    setRowMsg(cartId, 'error', 'Pick a date');
    return;
  }

  setRowMsg(cartId, '', 'Saving…');
  try {
    const resp = await fetch(`/api/carts/${cartId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ contents, date_usage: dateUsage })
    });

    if (resp.status === 401) {
      // Session expired mid-edit -> back to login.
      location.href = '/login';
      return;
    }

    const data = await resp.json().catch(() => ({}));
    if (resp.ok) {
      setRowMsg(cartId, 'ok', '✓ Saved');
    } else {
      setRowMsg(cartId, 'error', data.message || `Error ${resp.status}`);
    }
  } catch (err) {
    console.error(err);
    setRowMsg(cartId, 'error', 'Network error');
  }
}

// ---------- staleness banner (SSE-driven) ----------

function showBanner() { document.getElementById('stale-banner').hidden = false; }
function hideBanner() { document.getElementById('stale-banner').hidden = true; }

// Order-independent set equality on two id arrays.
function sameIdSet(a, b) {
  if (a.length !== b.length) return false;
  const setB = new Set(b);
  return a.every(id => setB.has(id));
}

// Subscribe to the live stream and flag when the JP membership drifts from what's
// on screen. Deliberately does NOT re-render - the operator's in-progress edits stay
// put; we only surface a Reload prompt. Relative URL -> same-origin HTTPS (:5000).
function watchForChanges() {
  const es = new EventSource('/api/stream');

  // The server sends a 'reload' event after a successful edit-page save. Hold
  // briefly first so the "✓ Saved" confirmation is visible before the refresh
  // (the trigger is still server-driven; the delay is just display timing).
  es.addEventListener('reload', () => setTimeout(() => location.reload(), 600));

  es.addEventListener('snapshot', (e) => {
    if (shownJpIds === null) return;   // no baseline yet; wait for the first load
    let payload;
    try {
      payload = JSON.parse(e.data);
    } catch (err) {
      console.error('Bad SSE payload:', err);
      return;
    }
    const liveJpIds = (payload.carts || [])
      .filter(c => c.current_location === TARGET_LOCATION)
      .map(c => c.id);
    // Membership only: a save never changes location, so it never trips this.
    if (sameIdSet(liveJpIds, shownJpIds)) {
      hideBanner();
    } else {
      showBanner();
    }
  });
}

// ---------- wire up ----------

document.getElementById('reload-btn').addEventListener('click', loadCarts);
document.getElementById('stale-reload').addEventListener('click', loadCarts);

loadCarts();
watchForChanges();
