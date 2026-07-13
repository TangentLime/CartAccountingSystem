// ============================================================
// Cart Tracker - Jurassic Park content editor
// Loads JP carts, lets a local operator edit contents + use-by
// date, and PATCHes the changes back to the server.
// ============================================================

const TARGET_LOCATION = 'Jurassic Park';

// The JP cart-ids currently rendered. null until the first load completes, so the
// SSE handler won't compare a live snapshot against an empty/absent baseline.
let shownJpIds = null;

// Emergency mode: when true, the page lists ALL carts (non-JP shown red) and each
// save requires a reason and is sent as an emergency edit. Unlocked via password.
let emergencyMode = false;

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

// Live server-connection pill (mirrors the dashboard): ● Connected / ◐ Connecting /
// ✕ Disconnected, driven by the SSE EventSource in watchForChanges().
function setConn(cls, text) {
  const el = document.getElementById('conn-status');
  el.className = cls;
  const prefix = cls === 'ok' ? '● ' : (cls === 'error' ? '✕ ' : '◐ ');
  el.textContent = prefix + text;
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
  // Stash the loaded values as data-base so Save can stay disabled until an
  // input actually differs from what was last loaded/refreshed.
  // An "Empty" (or blank) cart is shown as a real placeholder: the field value is
  // empty, so the greyed "Empty" hint sits in the background with the cursor at the
  // start and vanishes natively on the first keystroke.
  const raw = cart.contents ?? '';
  const isEmpty = raw === '' || raw === 'Empty';
  const contents = isEmpty ? '' : escapeHtml(raw);
  const placeholder = isEmpty ? 'Empty' : '';
  const pickerDate = dbToPicker(cart.date_usage);
  // In emergency mode we list every cart; flag non-JP ones red and show their location.
  const nonJp = emergencyMode && cart.current_location !== TARGET_LOCATION;
  const rowClass = 'cart-row' + (nonJp ? ' non-jp' : '');
  const locLine = emergencyMode
    ? `<span class="cart-loc">${escapeHtml(cart.current_location)}</span>` : '';
  return `
    <div class="${rowClass}" data-cart-id="${cart.id}">
      <div class="cart-meta">
        <span class="cart-id">ID ${cart.id}</span>
        ${locLine}
      </div>
      <div class="field">
        <label for="contents-${cart.id}">Contents</label>
        <input type="text" id="contents-${cart.id}" class="contents-input"
               value="${contents}" data-base="${contents}" placeholder="${placeholder}">
      </div>
      <div class="field">
        <label for="date-${cart.id}">Use-by date</label>
        <input type="date" id="date-${cart.id}" class="date-input"
               value="${pickerDate}" data-base="${pickerDate}">
      </div>
      <button type="button" class="save-btn" data-save="${cart.id}" disabled>Save</button>
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

  list.querySelectorAll('.cart-row').forEach(row => {
    const cartId = Number(row.dataset.cartId);
    const contentsInput = row.querySelector('.contents-input');
    const dateInput = row.querySelector('.date-input');
    const saveBtn = row.querySelector('[data-save]');

    // Enable Save only while something differs from the loaded baseline.
    const refresh = () => updateSaveState(row);
    contentsInput.addEventListener('input', refresh);
    dateInput.addEventListener('input', refresh);
    dateInput.addEventListener('change', refresh);   // date picker also fires 'change'

    saveBtn.addEventListener('click', () => saveCart(cartId));
  });
}

// Disable a row's Save button unless its contents or date differ from the values
// captured when the row was rendered (data-base).
function updateSaveState(row) {
  const contentsInput = row.querySelector('.contents-input');
  const dateInput = row.querySelector('.date-input');
  const saveBtn = row.querySelector('[data-save]');
  const dirty =
    contentsInput.value !== contentsInput.dataset.base ||
    dateInput.value !== dateInput.dataset.base;
  saveBtn.disabled = !dirty;
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
    const all = await resp.json();
    let carts;
    if (emergencyMode) {
      // Show every cart with non-JP (red) carts FIRST -- they're the reason to be in
      // emergency mode -- then JP carts below; each group by id. Membership/stale
      // tracking is JP-specific, so it's off here.
      carts = all.slice().sort((a, b) => {
        const aJp = a.current_location === TARGET_LOCATION ? 1 : 0;
        const bJp = b.current_location === TARGET_LOCATION ? 1 : 0;
        return aJp - bJp || a.id - b.id;
      });
      shownJpIds = null;
    } else {
      carts = all
        .filter(c => c.current_location === TARGET_LOCATION)
        .sort((a, b) => a.id - b.id);
      shownJpIds = carts.map(c => c.id);   // baseline for staleness comparison
    }
    renderRows(carts);
    hideBanner();                          // this render is now the fresh truth
    setStatus('ok', `Loaded ${carts.length} cart(s)`);
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
  const dateUsage = pickerToDb(pickerVal);   // MM-DD-YYYY string for the API
  
  if (!contents) {
    setRowMsg(cartId, 'error', 'Please specify the contents');
    return;
  }
  if (!dateUsage) {
    setRowMsg(cartId, 'error', 'Please select a date');
    return;
  }

  // Reject past dates. dateUsage stays a STRING for the API, so parse a separate
  // local-midnight Date to compare. Use getTime() (full date), not getDate()
  // (day-of-month only, which mis-compares across months).
  const [yyyy, mm, dd] = pickerVal.split('-').map(Number);
  const chosen = new Date(yyyy, mm - 1, dd);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  if (chosen.getTime() < today.getTime()) {
    setRowMsg(cartId, 'error', 'The carts cannot time-travel');
    return;
  }

  // If the JP list drifted since load (stale banner up), force an explicit choice:
  // Reload (refresh the list) or Proceed (save anyway). A cart that has since left
  // JP is rejected server-side with 403, so proceeding fails safely on its own.
  if (bannerActive()) {
    const choice = await confirmStale();
    if (choice === 'reload') {
      loadCarts();
      return;
    }
  }

  // Emergency edits require a typed reason (entered in a modal) and are sent flagged.
  let reason = null;
  if (emergencyMode) {
    reason = await promptReason();
    if (reason === null) {            // operator cancelled the reason modal
      setRowMsg(cartId, '', 'Cancelled');
      return;
    }
  }

  setRowMsg(cartId, '', 'Saving…');
  try {
    const body = emergencyMode
      ? { contents, date_usage: dateUsage, emergency: true, reason }
      : { contents, date_usage: dateUsage };
    const resp = await fetch(`/api/carts/${cartId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (resp.status === 401) {
      // Session expired mid-edit -> back to login.
      location.href = '/login';
      return;
    }

    const data = await resp.json().catch(() => ({}));
    if (resp.ok) {
      setRowMsg(cartId, 'ok', '✓ Saved');
      // The just-saved values are the new baseline -> re-disable Save until the
      // operator edits again (the SSE 'reload' then refreshes the whole page).
      const row = document.querySelector(`.cart-row[data-cart-id="${cartId}"]`);
      if (row) {
        const ci = row.querySelector('.contents-input');
        const di = row.querySelector('.date-input');
        ci.dataset.base = ci.value;
        di.dataset.base = di.value;
        updateSaveState(row);
      }
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
function bannerActive() { return !document.getElementById('stale-banner').hidden; }

// Modal shown when saving while the stale banner is up. Resolves to 'reload' or
// 'proceed' -- one of the two buttons MUST be clicked (there is no backdrop/Esc
// dismissal), so the operator always makes an explicit choice.
function confirmStale() {
  return new Promise(resolve => {
    const modal = document.getElementById('stale-modal');
    const reloadBtn = document.getElementById('stale-modal-reload');
    const proceedBtn = document.getElementById('stale-modal-proceed');

    const done = (choice) => {
      modal.hidden = true;
      reloadBtn.removeEventListener('click', onReload);
      proceedBtn.removeEventListener('click', onProceed);
      resolve(choice);
    };
    const onReload = () => done('reload');
    const onProceed = () => done('proceed');

    reloadBtn.addEventListener('click', onReload);
    proceedBtn.addEventListener('click', onProceed);
    modal.hidden = false;
    reloadBtn.focus();   // Reload is the recommended default
  });
}

// ---------- emergency mode ----------

// Password modal -> resolves to the typed password, or null if cancelled. Pass an
// errorMsg to show a red hint (e.g. after a wrong attempt) when reopening.
function promptPassword(errorMsg) {
  return new Promise(resolve => {
    const modal = document.getElementById('emg-modal');
    const input = document.getElementById('emg-input');
    const okBtn = document.getElementById('emg-ok');
    const cancelBtn = document.getElementById('emg-cancel');
    const err = document.getElementById('emg-err');

    input.value = '';
    err.textContent = errorMsg || '';
    err.hidden = !errorMsg;

    const done = (val) => {
      modal.hidden = true;
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      input.removeEventListener('keydown', onKey);
      resolve(val);
    };
    const onOk = () => { if (input.value) done(input.value); };
    const onCancel = () => done(null);
    const onKey = (e) => { if (e.key === 'Enter') onOk(); };

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    input.addEventListener('keydown', onKey);
    modal.hidden = false;
    input.focus();
  });
}

// Reason modal -> resolves to a non-empty trimmed reason, or null if cancelled.
function promptReason() {
  return new Promise(resolve => {
    const modal = document.getElementById('reason-modal');
    const input = document.getElementById('reason-input');
    const okBtn = document.getElementById('reason-ok');
    const cancelBtn = document.getElementById('reason-cancel');
    const err = document.getElementById('reason-err');

    input.value = '';
    err.hidden = true;

    const done = (val) => {
      modal.hidden = true;
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      resolve(val);
    };
    const onOk = () => {
      const v = input.value.trim();
      if (!v) { err.hidden = false; input.focus(); return; }
      done(v);
    };
    const onCancel = () => done(null);

    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    modal.hidden = false;
    input.focus();
  });
}

// Prompt for the password and unlock emergency mode server-side; loop on wrong password.
async function startEmergency() {
  let errMsg = '';
  while (true) {
    const pw = await promptPassword(errMsg);
    if (pw === null) return;                  // cancelled
    try {
      const resp = await fetch('/emergency/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pw })
      });
      if (resp.ok) {
        const data = await resp.json().catch(() => ({}));
        enterEmergency(data.ip);
        return;
      }
      errMsg = resp.status === 401 ? 'Incorrect password' : `Unlock failed (${resp.status})`;
    } catch (e) {
      console.error(e);
      errMsg = 'Network error';
    }
  }
}

function enterEmergency(ip) {
  emergencyMode = true;
  document.getElementById('emergency-ip').textContent = ip || 'unknown';
  document.documentElement.classList.add('emergency-mode');
  document.getElementById('emergency-banner').hidden = false;
  loadCarts();
}

async function exitEmergency() {
  try { await fetch('/emergency/lock', { method: 'POST' }); } catch (e) { /* best effort */ }
  emergencyMode = false;
  document.documentElement.classList.remove('emergency-mode');
  document.getElementById('emergency-banner').hidden = true;
  loadCarts();
}

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
  setConn('connecting', 'Connecting…');
  const es = new EventSource('/api/stream');

  // Live connection state. EventSource auto-reconnects, so onopen fires again on
  // recovery -> the pill returns to Connected without manual retry logic.
  es.onopen  = () => setConn('ok', 'Connected');
  es.onerror = () => setConn('error', 'Disconnected');

  // The server sends a 'reload' event after a successful edit-page save. Hold
  // briefly first so the "✓ Saved" confirmation is visible before the refresh
  // (the trigger is still server-driven; the delay is just display timing).
  // After a save the server broadcasts 'reload'. Normal mode does a full page reload;
  // emergency mode does a soft re-fetch so the operator stays unlocked for consecutive
  // fixes. A real F5 still exits emergency mode via /edit (which clears the session).
  es.addEventListener('reload', () => setTimeout(() => {
    if (emergencyMode) loadCarts(); else location.reload();
  }, 600));

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
document.getElementById('emergency-btn').addEventListener('click', startEmergency);
document.getElementById('emergency-exit').addEventListener('click', exitEmergency);

loadCarts();
watchForChanges();
