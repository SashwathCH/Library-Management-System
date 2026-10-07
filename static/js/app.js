'use strict';

/* ---------- state and helpers ---------- */
const state = { members: [], me: null, books: [], filter: { q: '', format: 'all', genre: 'all' } };
const view = document.getElementById('view');
const sheet = document.getElementById('sheet');
const toastEl = document.getElementById('toast');
const $ = (selector, root = document) => root.querySelector(selector);

const esc = (value) => String(value ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const fmtDate = (iso) => new Date(iso.slice(0, 10) + 'T00:00:00').toLocaleDateString(undefined,
  { day: 'numeric', month: 'short', year: 'numeric' });
const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
const daysLate = (due) => Math.max(0, Math.round((new Date(todayIso()) - new Date(due)) / 86400000));
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const isLibrarian = () => state.me && state.me.role === 'librarian';

let toastTimer;
function toast(message, isError = false) {
  toastEl.textContent = message;
  toastEl.className = isError ? 'show error' : 'show';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.className = ''; }, 4000);
}

async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.me) headers['X-Member-Id'] = state.me.id;
  const res = await fetch('/api' + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Something went wrong. Try again.');
  return data;
}

/* Spine colour follows genre; unknown genres get a stable colour from their name. */
const GENRE_COLORS = { technology: '#2F5D8A', fiction: '#A23E48', design: '#8A5A0B', biography: '#3F6B3B', general: '#5B6270' };
const EXTRA_COLORS = ['#6A4C93', '#1F7A8C', '#8C4A2F', '#4B6584', '#7A3E65'];
function genreColor(genre) {
  const key = (genre || 'general').toLowerCase();
  if (GENRE_COLORS[key]) return GENRE_COLORS[key];
  let hash = 0;
  for (const ch of key) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return EXTRA_COLORS[hash % EXTRA_COLORS.length];
}

const formData = (form) => Object.fromEntries(new FormData(form));
const paragraphs = (container, text) => {
  container.replaceChildren(...String(text).split(/\n{2,}/).filter((t) => t.trim()).map((t) => {
    const p = document.createElement('p');
    p.textContent = t.trim();   // textContent keeps member-written text from running as HTML
    return p;
  }));
};

const stars = (bookId, mine) => `<div class="stars" role="group" aria-label="Your rating">${[1, 2, 3, 4, 5].map((n) =>
  `<button type="button" class="star ${n <= (mine || 0) ? 'on' : ''}" data-act="rate" data-id="${bookId}" data-n="${n}"
    aria-label="${n} out of 5" aria-pressed="${n === mine}">★</button>`).join('')}</div>`;

/* ---------- shell: sign-in switcher and navigation ---------- */
function renderChrome() {
  const links = [['shelf', 'Shelf'], ['foryou', 'For you'], ['mine', 'My library'], ['write', 'Write']];
  if (isLibrarian()) links.push(['desk', 'Desk']);
  $('#nav').innerHTML = links.map(([id, label]) => `<a href="#/${id}" data-page="${id}">${label}</a>`).join('');
  $('#who').innerHTML = state.members.map((m) =>
    `<option value="${m.id}" ${m.id === state.me.id ? 'selected' : ''}>${esc(m.name)} (${esc(m.role)})</option>`).join('');
  $('#who-wrap').hidden = false;
}
function markNav(page) {
  document.querySelectorAll('#nav a').forEach((a) => {
    if (a.dataset.page === page) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
}

/* ---------- Shelf ---------- */
function spineHtml(b) {
  const out = b.format === 'physical' && b.available < 1;
  const width = 44 + ((b.id * 53) % 5) * 5;
  const height = 170 + ((b.id * 37) % 61);
  const label = `${b.title} by ${b.author}. ${b.genre}. ${b.format === 'ebook' ? 'E-book' : 'Physical book'}${out ? ', all copies out' : ''}`;
  return `<div class="cell" role="listitem"><button type="button" class="spine ${b.format === 'ebook' ? 'ebook' : ''} ${out ? 'out' : ''}"
    style="--c:${genreColor(b.genre)};--w:${width}px;--h:${height}px" data-act="open-book" data-id="${b.id}"
    aria-label="${esc(label)}" title="${esc(b.title)}"><span>${esc(b.title)}</span></button></div>`;
}

function drawShelf() {
  const { q, format, genre } = state.filter;
  const needle = q.trim().toLowerCase();
  const list = state.books.filter((b) =>
    (format === 'all' || b.format === format) && (genre === 'all' || b.genre === genre) &&
    (!needle || [b.title, b.author, b.genre, b.isbn || ''].some((x) => x.toLowerCase().includes(needle))));
  $('#shelf').innerHTML = list.map(spineHtml).join('');
  $('#shelf').hidden = !list.length;
  $('#shelf-empty').hidden = list.length > 0;
  $('#count').textContent = `Showing ${list.length} of ${plural(state.books.length, 'title')}`;
}

async function viewShelf() {
  state.books = await api('/books');
  const genres = [...new Set(state.books.map((b) => b.genre))].sort();
  view.innerHTML = `
    <h1>Shelf</h1>
    <p class="lede">Open a spine to borrow the book or read it online.</p>
    <form class="filters" role="search" onsubmit="return false">
      <input type="search" id="q" placeholder="Search title, author, ISBN or genre" aria-label="Search books" value="${esc(state.filter.q)}">
      <select id="fmt" aria-label="Format">
        <option value="all">Books and e-books</option>
        <option value="physical">Physical books</option>
        <option value="ebook">E-books</option>
      </select>
      <select id="genre" aria-label="Genre">
        <option value="all">All genres</option>
        ${genres.map((g) => `<option value="${esc(g)}">${esc(g)}</option>`).join('')}
      </select>
    </form>
    <p class="count" id="count"></p>
    <div id="shelf" class="case" role="list"></div>
    <p id="shelf-empty" class="shelf-empty" hidden>No titles match. Clear the search or choose another genre.</p>
    <ul class="legend" aria-label="Legend">
      ${genres.map((g) => `<li><span class="swatch" style="--c:${genreColor(g)}"></span>${esc(g)}</li>`).join('')}
      <li><span class="swatch band"></span>Band on top: e-book</li>
      <li><span class="swatch dim"></span>Dimmed: all copies out</li>
    </ul>`;
  $('#fmt').value = state.filter.format;
  $('#genre').value = genres.includes(state.filter.genre) ? state.filter.genre : 'all';
  state.filter.genre = $('#genre').value;
  drawShelf();
}

/* ---------- Book sheet ---------- */
async function openBook(id) {
  const b = await api('/books/' + id);
  const rating = b.rating_count
    ? `Rated ${b.avg_rating} out of 5 by ${plural(b.rating_count, 'reader')}.` : 'No ratings yet.';
  let action;
  if (b.format === 'ebook') {
    action = `<a class="btn" href="#/read/${b.id}" data-act="close-sheet">Read e-book</a>`;
  } else if (b.my_loan) {
    action = `<p class="note">You have this book. Due ${fmtDate(b.my_loan.due_date)}.</p>
      <button class="btn" data-act="return" data-loan="${b.my_loan.id}" data-book="${b.id}">Return book</button>`;
  } else if (b.available > 0) {
    action = `<button class="btn" data-act="borrow" data-id="${b.id}">Borrow for 14 days</button>
      <p class="note">${b.available} of ${b.copies} copies on the shelf.</p>`;
  } else {
    action = `<p class="note">All ${b.copies} copies are out. Check back after the due dates.</p>`;
  }
  sheet.innerHTML = `
    <div class="sheet-band" style="--c:${genreColor(b.genre)}"></div>
    <div class="sheet-body">
      <button type="button" class="btn quiet small" data-act="close-sheet">Close</button>
      <h2>${esc(b.title)}</h2>
      <p class="sub">By ${esc(b.author)}</p>
      <p><span class="tag">${esc(b.genre)}</span> <span class="tag">${b.format === 'ebook' ? 'E-book' : 'Physical book'}</span></p>
      ${b.description ? `<p>${esc(b.description)}</p>` : ''}
      <p class="note">${rating}</p>
      <div class="actions">${action}</div>
      ${b.can_rate ? `<p class="note" id="rate-label">Your rating</p>${stars(b.id, b.my_rating)}` : ''}
      ${isLibrarian() ? `<p><button class="btn danger small" data-act="remove-book" data-id="${b.id}">Remove from catalogue</button></p>` : ''}
    </div>`;
  if (!sheet.open) sheet.showModal();
}

/* ---------- Reader ---------- */
async function viewRead(id) {
  const b = await api(`/ebooks/${id}/read`);
  view.innerHTML = `
    <article class="reader">
      <a class="back" href="#/shelf">Back to shelf</a>
      <h1>${esc(b.title)}</h1>
      <p class="byline">By ${esc(b.author)}</p>
      <div class="text" id="text"></div>
      <footer class="reader-end">
        <p><strong>Finished?</strong> Rate this book to improve your recommendations.</p>
        ${stars(b.id, b.my_rating)}
      </footer>
    </article>`;
  paragraphs($('#text'), b.content);
}

/* ---------- For you ---------- */
async function viewForYou() {
  const picks = await api('/recommendations?limit=8');
  view.innerHTML = `
    <h1>For you</h1>
    <p class="lede">Picked from the genres and authors you read, and from readers with similar taste.</p>
    ${picks.length ? `<ul class="picks">${picks.map((r) => `
      <li style="--c:${genreColor(r.genre)}">
        <button class="link-title" data-act="open-book" data-id="${r.id}">${esc(r.title)}</button>
        <p class="sub">${esc(r.author)}, ${r.format === 'ebook' ? 'e-book' : 'physical book'}</p>
        <p>${esc(r.reason)}</p>
      </li>`).join('')}</ul>`
      : `<p>No picks yet. <a href="#/shelf">Borrow or read a few books</a> and they will show up here.</p>`}`;
}

/* ---------- My library ---------- */
async function viewMine() {
  const [loans, reads, made] = await Promise.all([api('/loans/mine'), api('/my/reads'), api('/my/books')]);
  const current = loans.filter((l) => !l.return_date);
  const past = loans.filter((l) => l.return_date);
  const statusText = { published: 'On the shelf', pending: 'Waiting for approval' };
  view.innerHTML = `
    <h1>My library</h1>
    <p class="lede">Everything you have borrowed, read and written.</p>

    <h2>Borrowed now</h2>
    ${current.length ? `<ul class="rows">${current.map((l) => `
      <li><div class="grow"><strong>${esc(l.title)}</strong> <span class="sub">by ${esc(l.author)}</span></div>
        <span>Due ${fmtDate(l.due_date)}</span>
        ${daysLate(l.due_date) ? `<span class="tag late">${plural(daysLate(l.due_date), 'day')} late</span>` : ''}
        <button class="btn small" data-act="return" data-loan="${l.id}" data-book="${l.book_id}">Return book</button></li>`).join('')}</ul>`
      : `<p class="note">Nothing borrowed. <a href="#/shelf">Open a spine on the shelf</a> to borrow it.</p>`}

    <h2>E-books you have read</h2>
    ${reads.length ? `<ul class="rows">${reads.map((r) => `
      <li><div class="grow"><strong>${esc(r.title)}</strong> <span class="sub">by ${esc(r.author)}</span></div>
        <span class="sub">Last read ${fmtDate(r.last_read)}</span>
        <a class="btn quiet small" href="#/read/${r.book_id}">Read again</a></li>`).join('')}</ul>`
      : `<p class="note">No e-books read yet.</p>`}

    <h2>Returned</h2>
    ${past.length ? `<ul class="rows">${past.map((l) => `
      <li><div class="grow"><strong>${esc(l.title)}</strong> <span class="sub">by ${esc(l.author)}</span></div>
        <span class="sub">Returned ${fmtDate(l.return_date)}</span>
        ${l.fine > 0 ? `<span class="tag late">Fine Rs ${l.fine.toFixed(2)}</span>` : ''}</li>`).join('')}</ul>`
      : `<p class="note">No returned books yet.</p>`}

    <h2>Your writing</h2>
    ${made.length ? `<ul class="rows">${made.map((m) => `
      <li><div class="grow"><strong>${esc(m.title)}</strong> <span class="sub">${esc(m.genre)}</span></div>
        <span class="tag">${statusText[m.status] || esc(m.status)}</span>
        ${m.status === 'published' ? `<a class="btn quiet small" href="#/read/${m.id}">Read</a>` : ''}</li>`).join('')}</ul>`
      : `<p class="note">You have not written anything yet. <a href="#/write">Write an e-book</a>.</p>`}`;
}

/* ---------- Write ---------- */
async function viewWrite() {
  const books = await api('/books');
  const genres = [...new Set(['Fiction', 'Technology', 'Design', 'Biography', ...books.map((b) => b.genre)])].sort();
  const direct = state.me.role !== 'member';
  view.innerHTML = `
    <h1>Write an e-book</h1>
    <p class="lede">${direct
      ? 'As an author, your e-book goes on the shelf as soon as you publish it.'
      : 'A librarian checks your e-book before it goes on the shelf.'}</p>
    <form class="form" data-form="write">
      <div class="field-row">
        <div class="field"><label for="w-title">Title</label><input id="w-title" name="title" required maxlength="120"></div>
        <div class="field"><label for="w-genre">Genre</label><input id="w-genre" name="genre" list="genres" value="Fiction" required>
          <datalist id="genres">${genres.map((g) => `<option value="${esc(g)}">`).join('')}</datalist></div>
      </div>
      <div class="field"><label for="w-desc">Short description</label><input id="w-desc" name="description" maxlength="200"></div>
      <div class="field"><label for="w-text">Text</label>
        <textarea id="w-text" name="content" required></textarea>
        <span class="note">Separate paragraphs with a blank line.</span></div>
      <div class="field"><label for="file">Or load a .txt file</label><input id="file" type="file" accept=".txt,text/plain"></div>
      <div><button class="btn" type="submit">${direct ? 'Publish e-book' : 'Send for approval'}</button></div>
    </form>`;
}

/* ---------- Desk (librarians) ---------- */
async function viewDesk() {
  const [pending, loans, members, physical] = await Promise.all([
    api('/pending'), api('/loans'), api('/admin/members'), api('/books?format=physical')]);
  const today = todayIso();
  const lendable = physical.filter((b) => b.available > 0);
  view.innerHTML = `
    <h1>Desk</h1>
    <p class="lede">Approve new e-books, lend and take back books, and manage members.</p>

    <h2>Waiting for approval</h2>
    ${pending.length ? `<ul class="rows">${pending.map((p) => `
      <li><div class="grow"><strong>${esc(p.title)}</strong> <span class="sub">by ${esc(p.author)}, ${esc(p.genre)}</span></div>
        <button class="btn quiet small" data-act="preview" data-id="${p.id}">Preview</button>
        <button class="btn small" data-act="approve" data-id="${p.id}">Approve</button>
        <button class="btn danger small" data-act="reject" data-id="${p.id}">Reject</button></li>`).join('')}</ul>`
      : `<p class="note">Nothing waiting. New submissions from members appear here.</p>`}

    <h2>Out on loan</h2>
    ${loans.length ? `<ul class="rows">${loans.map((l) => `
      <li><div class="grow"><strong>${esc(l.title)}</strong> <span class="sub">with ${esc(l.member)}</span></div>
        <span>Due ${fmtDate(l.due_date)}</span>
        ${l.due_date < today ? `<span class="tag late">Overdue</span>` : ''}
        <button class="btn small" data-act="return" data-loan="${l.id}">Take back</button></li>`).join('')}</ul>`
      : `<p class="note">No books are out right now.</p>`}

    <h2>Lend a book</h2>
    <form class="inline-form" data-form="issue">
      <div class="field"><label for="i-book">Book</label><select id="i-book" name="book_id" required>
        ${lendable.map((b) => `<option value="${b.id}">${esc(b.title)} (${b.available} left)</option>`).join('')}</select></div>
      <div class="field"><label for="i-member">Member</label><select id="i-member" name="member_id" required>
        ${members.map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join('')}</select></div>
      <button class="btn" type="submit" ${lendable.length ? '' : 'disabled'}>Lend book</button>
    </form>

    <h2>Add to the catalogue</h2>
    <form class="form" data-form="catalogue">
      <div class="field-row">
        <div class="field"><label for="c-type">Type</label><select id="c-type" name="format">
          <option value="physical">Physical book</option><option value="ebook">E-book</option></select></div>
        <div class="field"><label for="c-title">Title</label><input id="c-title" name="title" required></div>
        <div class="field"><label for="c-author">Author</label><input id="c-author" name="author" required></div>
      </div>
      <div class="field-row">
        <div class="field"><label for="c-genre">Genre</label><input id="c-genre" name="genre" value="General"></div>
        <div class="field"><label for="c-isbn">ISBN (optional)</label><input id="c-isbn" name="isbn"></div>
        <div class="field" id="c-copies-wrap"><label for="c-copies">Copies</label><input id="c-copies" name="copies" type="number" min="1" value="1"></div>
      </div>
      <div class="field"><label for="c-desc">Short description</label><input id="c-desc" name="description"></div>
      <div class="field" id="c-text-wrap" hidden><label for="c-text">E-book text</label><textarea id="c-text" name="content"></textarea></div>
      <div><button class="btn" type="submit">Add to catalogue</button></div>
    </form>

    <h2>Members</h2>
    <ul class="rows">${members.map((m) => `
      <li><div class="grow"><strong>${esc(m.name)}</strong> <span class="sub">${esc(m.email || 'no email')}</span></div>
        <label class="sub" for="role-${m.id}">Role</label>
        <select id="role-${m.id}" data-role-for="${m.id}">${['member', 'author', 'librarian'].map((r) =>
          `<option ${r === m.role ? 'selected' : ''}>${r}</option>`).join('')}</select></li>`).join('')}</ul>
    <form class="inline-form" data-form="add-member" style="margin-top:1rem">
      <div class="field"><label for="m-name">Name</label><input id="m-name" name="name" required></div>
      <div class="field"><label for="m-email">Email (optional)</label><input id="m-email" name="email" type="email"></div>
      <div class="field"><label for="m-role">Role</label><select id="m-role" name="role">
        <option>member</option><option>author</option><option>librarian</option></select></div>
      <button class="btn" type="submit">Add member</button>
    </form>`;
}

/* ---------- First run ---------- */
function viewSetup() {
  $('#nav').innerHTML = '';
  $('#who-wrap').hidden = true;
  view.innerHTML = `
    <section class="setup">
      <h1>Set up your library</h1>
      <p class="lede">There are no members yet. Load demo data to explore every feature, or start empty with a librarian account.</p>
      <button class="btn" data-act="seed">Load sample data</button>
      <form class="form" data-form="setup">
        <div class="field"><label for="s-name">Librarian name</label><input id="s-name" name="name" required></div>
        <div class="field"><label for="s-email">Email (optional)</label><input id="s-email" name="email" type="email"></div>
        <div><button class="btn quiet" type="submit">Start with an empty library</button></div>
      </form>
    </section>`;
}

/* ---------- Routing ---------- */
const pages = {
  shelf: viewShelf, foryou: viewForYou, mine: viewMine, write: viewWrite,
  desk: () => (isLibrarian() ? viewDesk() : (location.hash = '#/shelf')),
  read: (arg) => viewRead(Number(arg)),
};

async function render() {
  const [, page = 'shelf', arg] = (location.hash || '#/shelf').split('/');
  if (!pages[page]) { location.hash = '#/shelf'; return; }
  markNav(page);
  try { await pages[page](arg); } catch (err) { view.innerHTML = `<p class="error-text">${esc(err.message)}</p>`; }
  markNav(page);
}
async function route() {
  await render();
  window.scrollTo(0, 0);
  view.focus({ preventScroll: true });
}
async function refresh(bookId) {
  if (sheet.open && bookId) await openBook(bookId);
  await render();
}

async function boot() {
  state.members = await api('/members');
  if (!state.members.length) { viewSetup(); return; }
  const saved = Number(localStorage.getItem('lms.member'));
  state.me = state.members.find((m) => m.id === saved)
    || state.members.find((m) => m.role === 'member') || state.members[0];
  renderChrome();
  await route();
}

/* ---------- Actions (buttons with data-act) ---------- */
const actions = {
  'open-book': (el) => openBook(Number(el.dataset.id)),
  'close-sheet': () => sheet.close(),
  borrow: async (el) => {
    const r = await api(`/books/${el.dataset.id}/borrow`, { method: 'POST', body: {} });
    toast(`Borrowed. Due ${fmtDate(r.due_date)}.`);
    await refresh(Number(el.dataset.id));
  },
  return: async (el) => {
    const r = await api(`/loans/${el.dataset.loan}/return`, { method: 'POST' });
    toast(r.fine > 0 ? `Returned. Fine: Rs ${r.fine.toFixed(2)}.` : 'Returned.');
    await refresh(el.dataset.book ? Number(el.dataset.book) : null);
  },
  rate: async (el) => {
    const id = Number(el.dataset.id), n = Number(el.dataset.n);
    await api(`/books/${id}/rate`, { method: 'POST', body: { rating: n } });
    document.querySelectorAll(`.star[data-id="${id}"]`).forEach((s) => {
      const on = Number(s.dataset.n) <= n;
      s.classList.toggle('on', on);
      s.setAttribute('aria-pressed', String(Number(s.dataset.n) === n));
    });
    toast('Rating saved.');
    if (sheet.open) await openBook(id);
  },
  approve: async (el) => { await api(`/pending/${el.dataset.id}/approve`, { method: 'POST' }); toast('Approved.'); sheet.close(); await render(); },
  reject: async (el) => {
    if (!confirm('Reject this submission? The author will not be able to recover it.')) return;
    await api(`/pending/${el.dataset.id}/reject`, { method: 'POST' });
    toast('Rejected.'); sheet.close(); await render();
  },
  preview: async (el) => {
    const b = await api('/pending/' + el.dataset.id);
    sheet.innerHTML = `
      <div class="sheet-band" style="--c:${genreColor(b.genre)}"></div>
      <div class="sheet-body">
        <button type="button" class="btn quiet small" data-act="close-sheet">Close</button>
        <h2>${esc(b.title)}</h2><p class="sub">By ${esc(b.author)}</p>
        <div class="preview" id="preview"></div>
        <div class="actions"><button class="btn" data-act="approve" data-id="${b.id}">Approve</button>
          <button class="btn danger" data-act="reject" data-id="${b.id}">Reject</button></div>
      </div>`;
    paragraphs($('#preview'), b.content);
    if (!sheet.open) sheet.showModal();
  },
  'remove-book': async (el) => {
    if (!confirm('Remove this book from the catalogue?')) return;
    await api('/books/' + el.dataset.id, { method: 'DELETE' });
    toast('Removed.'); sheet.close(); await render();
  },
  seed: async () => { await api('/setup', { method: 'POST', body: { sample: true } }); toast('Sample data loaded.'); await boot(); },
};

document.addEventListener('click', async (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || !actions[el.dataset.act]) return;
  if (el.tagName === 'BUTTON') e.preventDefault();
  try { await actions[el.dataset.act](el); } catch (err) { toast(err.message, true); }
});
sheet.addEventListener('click', (e) => { if (e.target === sheet) sheet.close(); });   // click on backdrop

/* ---------- Forms (data-form) ---------- */
const forms = {
  write: async (form) => {
    const r = await api('/my/books', { method: 'POST', body: formData(form) });
    toast(r.status === 'published' ? 'Published.' : 'Sent for approval.');
    location.hash = '#/mine';
  },
  issue: async (form) => {
    const d = formData(form);
    const r = await api(`/books/${d.book_id}/borrow`, { method: 'POST', body: { member_id: Number(d.member_id) } });
    toast(`Lent. Due ${fmtDate(r.due_date)}.`);
    await render();
  },
  catalogue: async (form) => {
    const d = formData(form);
    if (d.format === 'physical') delete d.content; else delete d.copies;
    await api('/books', { method: 'POST', body: d });
    toast('Added to catalogue.');
    await render();
  },
  'add-member': async (form) => {
    await api('/members', { method: 'POST', body: formData(form) });
    state.members = await api('/members');
    renderChrome();
    toast('Member added.');
    await render();
  },
  setup: async (form) => { await api('/setup', { method: 'POST', body: formData(form) }); toast('Library ready.'); await boot(); },
};

document.addEventListener('submit', async (e) => {
  const name = e.target.dataset.form;
  if (!name || !forms[name]) return;
  e.preventDefault();
  try { await forms[name](e.target); } catch (err) { toast(err.message, true); }
});

/* ---------- Other events ---------- */
document.addEventListener('input', (e) => {
  if (e.target.id === 'q') { state.filter.q = e.target.value; drawShelf(); }
});
document.addEventListener('change', async (e) => {
  const t = e.target;
  if (t.id === 'fmt') { state.filter.format = t.value; drawShelf(); }
  else if (t.id === 'genre') { state.filter.genre = t.value; drawShelf(); }
  else if (t.id === 'who') {
    state.me = state.members.find((m) => m.id === Number(t.value));
    localStorage.setItem('lms.member', state.me.id);
    renderChrome();
    if (location.hash === '#/desk' && !isLibrarian()) location.hash = '#/shelf'; else await route();
  } else if (t.id === 'c-type') {
    const ebook = t.value === 'ebook';
    $('#c-copies-wrap').hidden = ebook;
    $('#c-text-wrap').hidden = !ebook;
    $('#c-text').required = ebook;
  } else if (t.dataset.roleFor) {
    try {
      await api(`/members/${t.dataset.roleFor}/role`, { method: 'PATCH', body: { role: t.value } });
      state.members = await api('/members');
      state.me = state.members.find((m) => m.id === state.me.id) || state.me;
      renderChrome();
      toast('Role updated.');
    } catch (err) { toast(err.message, true); await render(); }
  } else if (t.id === 'file' && t.files[0]) {
    const file = t.files[0];
    $('#w-text').value = await file.text();
    if (!$('#w-title').value) $('#w-title').value = file.name.replace(/\.txt$/i, '');
  }
});

window.addEventListener('hashchange', route);
boot().catch((err) => { view.innerHTML = `<p class="error-text">${esc(err.message)}</p>`; });
