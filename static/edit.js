// ============================================================
// Cart Tracker - Jurassic Park content editor
// Loads JP carts, lets a local operator edit contents + use-by
// date, and PATCHes the changes back to the server.
// ============================================================

const TARGET_LOCATION = 'Jurassic Park';
const KEY_STORAGE = 'nfc_api_key';

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

// ---------- API key handling ----------

function getApiKey(forcePrompt) {
  let key = localStorage.getItem(KEY_STORAGE);
  if (!key || forcePrompt) {
    key = window.prompt('Enter the server API key:', key || '');
    if (key) {
      localStorage.setItem(KEY_STORAGE, key.trim());
      key = key.trim();
    }
  }
  return key;
}

function clearApiKey() {
  localStorage.removeItem(KEY_STORAGE);
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
  const key = getApiKey(false);
  if (!key) {
    setStatus('error', 'API key required');
    return;
  }
  setStatus('connecting', 'Loading…');
  try {
    const resp = await fetch('/api/carts', { headers: { 'X-API-Key': key } });
    if (resp.status === 401) {
      clearApiKey();
      setStatus('error', 'Invalid API key');
      getApiKey(true);
      return loadCarts();
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
  const key = getApiKey(false);
  if (!key) {
    setRowMsg(cartId, 'error', 'No API key');
    return;
  }

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
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': key
      },
      body: JSON.stringify({ contents, date_usage: dateUsage })
    });

    if (resp.status === 401) {
      clearApiKey();
      setRowMsg(cartId, 'error', 'Invalid API key');
      getApiKey(true);
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

// ---------- wire up ----------

document.getElementById('reload-btn').addEventListener('click', loadCarts);
document.getElementById('key-btn').addEventListener('click', () => {
  getApiKey(true);
  loadCarts();
});

loadCarts();
