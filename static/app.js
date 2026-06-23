let previousLocations = {};
let eventSource = null;
let reconnectTimer = null;


function escapeHtml(s)
{
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

  const parts = s.split('-');
  if (parts.length !== 3) return null;

  const [mm, dd, yyyy] = parts.map(Number);
  if (!mm || !dd || !yyyy) return null;

  return new Date(yyyy, mm - 1, dd);
}

function isOverdue(cart) {
  if (cart.current_location === 'JIT' || cart.current_location === 'MAL') {
    return false;
  }
  const useBy = parseUseDate(cart.date_usage);
  if (!useBy) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today >= useBy;
}

function cartCardHtml(cart, justMoved) {
  const overdue = isOverdue(cart);
  const classes = ['cart-card'];
  if (overdue)   classes.push('overdue');
  if (justMoved) classes.push('just-moved');

  return `
    <div class="${classes.join(' ')}" data-cart-id="${cart.id}">
      <div class="cart-id">#${cart.id}</div>
      <div class="cart-name">${escapeHtml(cart.name)}</div>
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

    countEl.textContent = cartsHere.length;
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

// SSE Connection
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