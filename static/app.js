// ============================================================
// Cart Tracker - SSE-driven dashboard
// ============================================================

let previousLocations = {};
let eventSource = null;
let reconnectTimer = null;

// ---------- helpers ----------

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;',
    '"': '&quot;', "'": '&#39;'
  }[c]));
}

function setStatus(cls, text) {
  const el = document.getElementById('connection-status');
  el.className = cls;
  const prefix = cls === 'ok' ? '● ' : (cls === 'error' ? '✕ ' : '◐ ');
  el.textContent = prefix + text;
}

function parseUseDate(s) {
  if (!s) return null;
  if (s === 'Return')
  {
    return false;
  }
  const parts = s.split('-');
  if (parts.length !== 3) return null;
  const [mm, dd, yyyy] = parts.map(Number);
  if (!mm || !dd || !yyyy) return null;
  return new Date(yyyy, mm - 1, dd);
}

function isOverdue(cart) {
  const useBy = parseUseDate(cart.date_usage);
  if (!useBy) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const leadDate = new Date(useBy);
  leadDate.setDate(leadDate.getDate() - 3);
  
  if (cart.current_location === 'MAL') {
    return false;
  }
  else if (cart.current_location === 'JIT') {
    return today > useBy;
  }
  else if (cart.current_location === 'Jurassic Park') {
    return today > leadDate;
  }
}

function isWarning(cart)
{
  const useBy = parseUseDate(cart.date_usage);
  if (!useBy) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const leadDate = new Date(useBy);
  leadDate.setDate(leadDate.getDate() - 3);

  if (cart.current_location === 'MAL') {
    return today > useBy;
  }
  else if (cart.current_location === 'JIT') {
    return today == useBy;
  }
  else if (cart.current_location === 'Jurassic Park') {
    return today == leadDate;
  }
}

// ---------- rendering ----------

function cartCardHtml(cart, justMoved) {
  const overdue = isOverdue(cart);
  const warning = isWarning(cart);
  const classes = ['cart-card'];
  if (overdue) {
    classes.push('overdue')
  }
  else if (warning) {
    classes.push('warning')
  }
  if (justMoved) classes.push('just-moved');

  if (cart.date_usage == 'Return')
  {
    return `
    <div class="${classes.join(' ')}" data-cart-id="${cart.id}">
      <div class="cart-id">ID: ${cart.id}</div>
      <div class="cart-contents">${escapeHtml(cart.contents)}</div>
      <div class="cart-date">Returning...</div>
    </div>`;
  }
  return `
    <div class="${classes.join(' ')}" data-cart-id="${cart.id}">
      <div class="cart-id">ID: ${cart.id}</div>
      <div class="cart-contents">${escapeHtml(cart.contents)}</div>
      <div class="cart-date">📅 ${escapeHtml(cart.date_usage)}</div>
    </div>`;
}

function renderBoard(carts) {
  const byLocation = {};
  carts.forEach(c => {
    if (!byLocation[c.current_location]) byLocation[c.current_location] = [];
    byLocation[c.current_location].push(c);
  });

  document.querySelectorAll('.column').forEach(col => {
    const location = col.dataset.location;
    const cartsHere = (byLocation[location] || []).sort((a, b) => a.id - b.id);
    const cardsContainer = col.querySelector('[data-cards-for]');
    const countEl        = col.querySelector('[data-count-for]');

    cardsContainer.innerHTML = cartsHere.map(cart => {
      const wasElsewhere =
        previousLocations[cart.id] !== undefined &&
        previousLocations[cart.id] !== cart.current_location;
      return cartCardHtml(cart, wasElsewhere);
    }).join('');

    // Tell the CSS how many cards are here so it can pick a good grid layout
    cardsContainer.setAttribute('data-count', cartsHere.length);

    countEl.textContent = "Carts: " + cartsHere.length;
  });

  Object.keys(byLocation).forEach(loc => {
    if (!document.querySelector(`.column[data-location="${loc}"]`)) {
      console.warn(`Unknown location "${loc}" - no column exists for it`);
    }
  });

  previousLocations = {};
  carts.forEach(c => previousLocations[c.id] = c.current_location);
}

function handleSnapshot(payload) {
  renderBoard(payload.carts);

  let timeText;
  if (payload.server_time) {
    timeText = new Date(payload.server_time).toLocaleString();
  } else {
    timeText = new Date().toLocaleString();
  }
  document.getElementById('updated').textContent = 'Last updated: ' + timeText;

  setStatus('ok', 'Connected');
}

// ---------- SSE connection ----------

function connect() {
  if (eventSource) eventSource.close();

  setStatus('connecting', 'Connecting…');
  eventSource = new EventSource('/api/stream');

  eventSource.addEventListener('snapshot', (e) => {
    try {
      handleSnapshot(JSON.parse(e.data));
    } catch (err) {
      console.error('Failed to parse SSE payload:', err);
    }
  });

  eventSource.onopen = () => {
    setStatus('ok', 'Connected');
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  eventSource.onerror = () => {
    setStatus('error', 'Disconnected');
    if (eventSource.readyState === EventSource.CLOSED) {
      reconnectTimer = setTimeout(connect, 5000);
    }
  };
}

connect();