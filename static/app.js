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

// Whole-day difference (DST-safe) between two local-midnight dates.
function daysBetween(from, to) {
  return Math.round((to - from) / 86400000);
}

// Human phrase for how far off the use-by date is.
function describeDue(daysUntil) {
  if (daysUntil < 0) {
    const n = -daysUntil;
    return `${n} day${n === 1 ? '' : 's'} overdue`;
  }
  if (daysUntil === 0) return 'Due today';
  return `Due in ${daysUntil} day${daysUntil === 1 ? '' : 's'}`;
}

// Single source of truth for a cart's flag colour AND its reason line, so the two
// can never disagree. Returns { level: 'overdue' | 'warning' | null, reason }.
function cartStatus(cart) {
  const loc = cart.current_location;

  // A 'Return' cart was emptied on its way out of MAL. If it's still sitting in
  // MAL it hasn't been taken back yet, so flag it red with that instruction.
  // Return carts elsewhere (already home / en route) stay neutral.
  if (cart.date_usage === 'Return') {
    if (loc === 'MAL') return { level: 'overdue', reason: '🔴 Return to Jurassic Park' };
    return { level: null, reason: '' };
  }

  const useBy = parseUseDate(cart.date_usage);
  if (!useBy) return { level: null, reason: '' };

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const daysUntil = daysBetween(today, useBy);

  // Thresholds reproduce the original isOverdue/isWarning truth table exactly.
  let level = null;
  if (loc === 'MAL') {
    level = daysUntil < 0 ? 'warning' : null;        // MAL never goes red on a date
  } else if (loc === 'JIT') {
    if (daysUntil < 0)       level = 'overdue';
    else if (daysUntil === 0) level = 'warning';
  } else if (loc === 'Jurassic Park') {
    if (daysUntil <= 2)       level = 'overdue';      // JP needs a 3-day prep lead
    else if (daysUntil === 3) level = 'warning';
  }

  if (!level) return { level: null, reason: '' };
  const emoji = level === 'overdue' ? '🔴' : '🟡';
  return { level, reason: `${emoji} ${describeDue(daysUntil)}` };
}

// ---------- rendering ----------

function cartCardHtml(cart) {
  const { level, reason } = cartStatus(cart);
  const classes = ['cart-card'];
  if (level) classes.push(level);                // 'overdue' | 'warning' (mutually exclusive)
  if (cart.emergency_flag) classes.push('emergency');

  // ⚠️ badge is always in the DOM; CSS reveals it only on .emergency cards, so
  // updateCard just toggles the class (no markup churn for the FLIP reconciler).
  const badge = `<span class="emergency-badge" title="Emergency edit — pending review">⚠️</span>`;

  const dateText = cart.date_usage === 'Return'
    ? 'Returning...'
    : `📅 ${escapeHtml(cart.date_usage)}`;

  // .cart-reason is always in the DOM (empty on unflagged cards); CSS reveals it
  // only on .warning/.overdue cards, mirroring the emergency-badge pattern.
  return `
    <div class="${classes.join(' ')}" data-cart-id="${cart.id}">
      ${badge}
      <div class="cart-id">ID: ${cart.id}</div>
      <div class="cart-contents">${escapeHtml(cart.contents)}</div>
      <div class="cart-date">${dateText}</div>
      <div class="cart-reason">${escapeHtml(reason)}</div>
    </div>`;
}

// Build a fresh card element from the HTML template (first render of a card).
function buildCard(cart) {
  const tpl = document.createElement('template');
  tpl.innerHTML = cartCardHtml(cart).trim();
  return tpl.content.firstElementChild;
}

// Update an existing card node IN PLACE so it keeps its identity (and thus a
// "before" state to animate from). Toggles state classes and crossfades any
// field whose visible text actually changed.
function updateCard(node, cart) {
  const { level, reason } = cartStatus(cart);
  node.classList.toggle('overdue', level === 'overdue');
  node.classList.toggle('warning', level === 'warning');
  node.classList.toggle('emergency', !!cart.emergency_flag);

  const dateText = cart.date_usage === 'Return'
    ? 'Returning...'
    : `📅 ${cart.date_usage ?? ''}`;

  setFieldText(node.querySelector('.cart-id'), `ID: ${cart.id}`);
  setFieldText(node.querySelector('.cart-contents'), String(cart.contents ?? ''));
  setFieldText(node.querySelector('.cart-date'), dateText);
  setFieldText(node.querySelector('.cart-reason'), reason);
}

// Set text only when it changed; restart the crossfade animation each time.
function setFieldText(el, text) {
  if (!el || el.textContent === text) return;
  el.textContent = text;
  el.classList.remove('content-changed');
  void el.offsetWidth;                 // reflow so the animation can retrigger
  el.classList.add('content-changed');
}

// ---------- move/resize animation (interruption-safe FLIP) ----------

const MOVE_MS = 550;                                  // glide/resize duration
const EASING  = 'cubic-bezier(0.4, 0, 0.2, 1)';
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

// In-flight cross-column ghosts, keyed by cart id -> { ghost, timer }. This is the
// single source of truth for measuring and cancelling travel animations across
// renders, so a change mid-flight never leaves an orphan or stuck-hidden card.
const activeGhosts = new Map();

function flashSettle(card) {
  card.classList.add('card-settle');
  card.addEventListener('animationend',
    () => card.classList.remove('card-settle'), { once: true });
}

function playEnter(node) {
  node.classList.add('card-enter');
  node.addEventListener('animationend',
    () => node.classList.remove('card-enter'), { once: true });
}

// Real-node FLIP for a WITHIN-column position/size change (stays inside .cards, so
// overflow:hidden never clips it).
function playFlip(node, first, last) {
  const dx = first.left - last.left;
  const dy = first.top  - last.top;
  const sx = last.width  ? first.width  / last.width  : 1;
  const sy = last.height ? first.height / last.height : 1;

  node.style.transformOrigin = '0 0';
  node.style.transition = 'none';
  node.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
  void node.offsetWidth;                              // commit the inverted start
  node.style.transition = `transform ${MOVE_MS}ms ${EASING}`;
  node.style.transform = 'none';

  node.addEventListener('transitionend', () => {
    node.style.transition = '';
    node.style.transform = '';
    node.style.transformOrigin = '';
  }, { once: true });
}

// Ghost travel for a CROSS-column move: a fixed clone rides above the clipped
// columns from the card's captured position/size to its new cell.
function playGhost(node, first, last) {
  const key = node.dataset.cartId;
  const dx = first.left - last.left;
  const dy = first.top  - last.top;
  const sx = last.width  ? first.width  / last.width  : 1;
  const sy = last.height ? first.height / last.height : 1;

  const ghost = node.cloneNode(true);
  ghost.classList.add('card-ghost');
  ghost.classList.remove('card-arriving', 'card-settle');
  ghost.style.left   = last.left   + 'px';
  ghost.style.top    = last.top    + 'px';
  ghost.style.width  = last.width  + 'px';
  ghost.style.height = last.height + 'px';
  ghost.style.transformOrigin = '0 0';
  ghost.style.transform = `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
  document.body.appendChild(ghost);

  node.classList.add('card-arriving');               // hide real card until it lands

  void ghost.offsetWidth;
  ghost.style.transition = `transform ${MOVE_MS}ms ${EASING}`;
  ghost.style.transform = 'none';

  const entry = { ghost, timer: null };
  const land = () => {
    if (activeGhosts.get(key) !== entry) return;      // already retired/replaced
    clearTimeout(entry.timer);
    activeGhosts.delete(key);
    ghost.remove();
    node.classList.remove('card-arriving');
    flashSettle(node);
  };
  ghost.addEventListener('transitionend', land, { once: true });
  entry.timer = setTimeout(land, MOVE_MS + 200);      // safety net
  activeGhosts.set(key, entry);
}

function renderBoard(carts) {
  // ----- First: measure LIVE VISUAL positions BEFORE any cleanup -----
  // (transforms still applied, so a mid-glide card reports where it visually is).
  const firstRects = {};
  const hadGhost = new Set();
  document.querySelectorAll('.cart-card[data-cart-id]:not(.card-ghost)')
    .forEach(el => { firstRects[el.dataset.cartId] = el.getBoundingClientRect(); });
  // A traveling ghost is the true visual position of its (hidden) real card.
  activeGhosts.forEach(({ ghost }, id) => {
    firstRects[id] = ghost.getBoundingClientRect();
    hadGhost.add(id);
  });

  // ----- Cancel prior animations; snap DOM back to true layout -----
  activeGhosts.forEach(({ ghost, timer }) => { clearTimeout(timer); ghost.remove(); });
  activeGhosts.clear();
  document.querySelectorAll('.cart-card[data-cart-id]').forEach(el => {
    el.style.transform = '';
    el.style.transition = '';
    el.style.transformOrigin = '';
    el.classList.remove('card-arriving', 'card-settle');
  });

  // ----- Reconcile DOM, keyed by cart id (preserve node identity) -----
  const existing = {};
  document.querySelectorAll('.cart-card[data-cart-id]')
    .forEach(el => { existing[el.dataset.cartId] = el; });

  const byLocation = {};
  carts.forEach(c => {
    if (!byLocation[c.current_location]) byLocation[c.current_location] = [];
    byLocation[c.current_location].push(c);
  });

  const seen = new Set();
  const isNew = new Set();

  document.querySelectorAll('.column').forEach(col => {
    const location = col.dataset.location;
    const cartsHere = (byLocation[location] || []).sort((a, b) => a.id - b.id);
    const cardsContainer = col.querySelector('[data-cards-for]');
    const countEl        = col.querySelector('[data-count-for]');

    cartsHere.forEach(cart => {
      const key = String(cart.id);
      let node = existing[key];
      if (!node) {
        node = buildCard(cart);
        isNew.add(key);
      } else {
        updateCard(node, cart);
      }
      cardsContainer.appendChild(node);              // moves node here, in sorted order
      seen.add(key);
    });

    // Tell the CSS how many cards are here so it can pick a good grid layout
    cardsContainer.setAttribute('data-count', cartsHere.length);
    countEl.textContent = "Carts: " + cartsHere.length;
  });

  // Remove any card no longer present (safety net; 9 fixed carts rarely trigger it).
  Object.keys(existing).forEach(key => {
    if (!seen.has(key)) existing[key].remove();
  });

  Object.keys(byLocation).forEach(loc => {
    if (!document.querySelector(`.column[data-location="${loc}"]`)) {
      console.warn(`Unknown location "${loc}" - no column exists for it`);
    }
  });

  // ----- Last + Play -----
  carts.forEach(cart => {
    const key = String(cart.id);
    const node = document.querySelector(
      `.cart-card[data-cart-id="${key}"]:not(.card-ghost)`);
    if (!node) return;

    if (isNew.has(key)) {
      if (!prefersReducedMotion.matches) playEnter(node);
      return;
    }

    const first = firstRects[key];
    if (!first) return;
    const last = node.getBoundingClientRect();

    const moved = Math.abs(first.left - last.left) > 0.5 ||
                  Math.abs(first.top  - last.top)  > 0.5 ||
                  Math.abs(first.width  - last.width)  > 0.5 ||
                  Math.abs(first.height - last.height) > 0.5;

    // Nothing to move -> color/content CSS transitions handle any visual change.
    if (prefersReducedMotion.matches || !moved) return;

    const crossColumn =
      (previousLocations[cart.id] !== undefined &&
       previousLocations[cart.id] !== cart.current_location) ||
      hadGhost.has(key);

    if (crossColumn) playGhost(node, first, last);
    else             playFlip(node, first, last);
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