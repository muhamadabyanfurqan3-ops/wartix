const filmDetails = {
  'Avengers: Endgame': { genre: 'Aksi · Fiksi ilmiah', order: '01', poster: 'assets/avengers-endgame.jpg' },
  Midway: { genre: 'Perang · Sejarah', order: '02', poster: 'assets/midway.webp' },
  '1917': { genre: 'Perang · Drama', order: '03', poster: 'assets/1917-poster.jpeg' },
};

const state = {
  schedules: [],
  schedule: null,
  selectedScheduleId: null,
  selectedSeats: new Set(),
  statusStreams: new Map(),
  user: null,
};

const movieGrid = document.querySelector('#movie-grid');
const seatMap = document.querySelector('#seat-map');
const seatSummary = document.querySelector('#seat-summary-text');
const bookingButton = document.querySelector('#booking-button');
const paymentButton = document.querySelector('#payment-button');
const paymentNote = document.querySelector('#payment-note');
const paymentFeedback = document.querySelector('#payment-feedback');
const selectedShowCopy = document.querySelector('#selected-show-copy');
const connectionStatus = document.querySelector('#connection-status');
const bookingDialog = document.querySelector('#booking-dialog');
const dialogCopy = document.querySelector('#dialog-copy');
const dialogFeedback = document.querySelector('#dialog-feedback');
const customerName = document.querySelector('#customer-name');
const confirmBookingButton = document.querySelector('#confirm-booking-button');
const receiptDialog = document.querySelector('#receipt-dialog');

// randomUUID is restricted to secure contexts in browsers. The demo is served
// over HTTP on a LAN IP, so generate a UUID using getRandomValues as fallback.
function createRequestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }

  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  // Compatibility fallback for browsers without Web Crypto support.
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function readStoredUser() {
  try {
    return JSON.parse(globalThis.sessionStorage?.getItem('wartix-user') || 'null');
  } catch {
    // Pemesanan tetap dapat dilakukan jika browser membatasi Web Storage.
    return null;
  }
}

function storeUser(user) {
  try {
    globalThis.sessionStorage?.setItem('wartix-user', JSON.stringify(user));
  } catch {
    // Identitas cukup disimpan di memori untuk sesi halaman ini.
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(data?.error || data?.pesan || `Permintaan gagal (${response.status})`);
  return data;
}

function showConnection(message, isError = false) {
  connectionStatus.textContent = message;
  connectionStatus.classList.toggle('is-error', isError);
}

function renderMovies() {
  if (!state.schedules.length) {
    movieGrid.innerHTML = '<p class="catalog-empty">Belum ada jadwal film yang tersedia.</p>';
    return;
  }

  const films = state.schedules.reduce((groups, schedule) => {
    groups.set(schedule.nama_film, [...(groups.get(schedule.nama_film) || []), schedule]);
    return groups;
  }, new Map());
  movieGrid.innerHTML = [...films.entries()].map(([film, schedules]) => {
    const details = filmDetails[film] || { genre: 'Film pilihan', order: '', poster: '' };
    const poster = details.poster
      ? `<img class="poster-image" src="${details.poster}" alt="Poster ${film}" loading="lazy" />`
      : '<div class="poster-fallback" aria-hidden="true">WARTIX</div>';
    const filmSelected = schedules.some((schedule) => state.selectedScheduleId === schedule.jadwal_id);
    return `
      <article class="movie-card ${filmSelected ? 'is-selected' : ''}">
        <div class="movie-poster">${poster}<span class="poster-label">PILIHAN FILM <b>${details.order}</b></span></div>
        <div class="movie-details">
          <h3>${film}</h3>
          <p class="movie-meta">${details.genre} · ${schedules[0].studio_id}</p>
          <div class="showtimes" aria-label="Jadwal ${film}">
            ${schedules.map((schedule) => {
              const selected = state.selectedScheduleId === schedule.jadwal_id;
              return `<button class="time-button${selected ? ' is-selected' : ''}" type="button" data-schedule="${schedule.jadwal_id}" aria-pressed="${selected}">
                ${schedule.jam_tayang.slice(0, 5)}
              </button>`;
            }).join('')}
          </div>
        </div>
      </article>`;
  }).join('');
}

function statusLabel(status, isMine) {
  if (status === 'AVAILABLE') return 'tersedia';
  if (status === 'PENDING_PAYMENT') return isMine ? 'ditahan olehmu' : 'sedang ditahan';
  return 'terjual';
}

function renderSeats() {
  const schedule = state.schedule;
  if (!schedule) {
    selectedShowCopy.textContent = 'Pilih film dan jam tayang untuk melihat denah kursi.';
    seatMap.innerHTML = '<p class="seat-empty">Denah kursi akan dimuat dari server setelah jadwal dipilih.</p>';
    seatSummary.textContent = 'Belum ada';
    bookingButton.disabled = true;
    paymentButton.hidden = true;
    paymentNote.hidden = true;
    paymentFeedback.hidden = true;
    return;
  }

  selectedShowCopy.textContent = `${schedule.nama_film} · ${schedule.jam_tayang.slice(0, 5)} · ${schedule.studio_id} · ${schedule.kursi_tersedia} kursi tersedia`;
  const seats = new Map(schedule.kursi.map((seat) => [seat.kursi_id, seat]));
  const rows = ['A', 'B', 'C', 'D', 'E', 'F'];
  seatMap.innerHTML = rows.map((row) => `
    <span class="row-label" aria-hidden="true">${row}</span>
    ${Array.from({ length: 10 }, (_, index) => {
      const seatId = `${row}${index + 1}`;
      const seat = seats.get(seatId);
      const status = seat?.status || 'AVAILABLE';
      const selected = state.selectedSeats.has(seatId);
      const mine = status === 'PENDING_PAYMENT' && seat.user_id === state.user?.id;
      const kind = selected ? 'selected' : status === 'AVAILABLE' ? 'available' : status === 'PENDING_PAYMENT' ? 'held' : 'occupied';
      const label = statusLabel(status, mine);
      const cancelAction = mine ? `data-cancel-seat="${seatId}"` : '';
      const disabled = status !== 'AVAILABLE' && !mine;
      const description = mine ? 'klik untuk membatalkan hold' : label;
      return `<button class="seat ${kind}${mine ? ' mine' : ''}" type="button" data-seat="${seatId}" ${cancelAction} aria-label="Kursi ${seatId}, ${selected ? 'dipilih' : description}" aria-pressed="${selected}" ${disabled ? 'disabled' : ''} title="Kursi ${seatId}: ${description}"></button>`;
    }).join('')}`).join('');

  const selected = [...state.selectedSeats].sort((a, b) => a.localeCompare(b, 'id', { numeric: true }));
  seatSummary.textContent = selected.length ? selected.join(', ') : 'Belum ada';
  bookingButton.disabled = selected.length === 0;
  const ownedHolds = schedule.kursi.filter((seat) =>
    seat.status === 'PENDING_PAYMENT' && seat.user_id === state.user?.id
  );
  paymentButton.hidden = ownedHolds.length === 0;
  paymentButton.disabled = false;
  paymentButton.textContent = ownedHolds.length > 1
    ? `Konfirmasi pembayaran ${ownedHolds.length} kursi`
    : 'Konfirmasi pembayaran';
  paymentNote.hidden = ownedHolds.length === 0;
}

async function loadSchedules() {
  showConnection('Menghubungkan ke server Wartix…');
  try {
    state.schedules = await api('/api/schedules');
    showConnection('Terhubung ke server Wartix · jadwal dan kursi diperbarui langsung.');
    renderMovies();
  } catch (error) {
    showConnection(`Server Wartix belum dapat dihubungi: ${error.message}`, true);
    movieGrid.innerHTML = '<button class="button button-red" id="retry-catalog" type="button">Coba lagi</button>';
  }
}

async function chooseSchedule(scheduleId) {
  closeAllStatusStreams();
  paymentFeedback.textContent = '';
  paymentFeedback.hidden = true;
  state.selectedScheduleId = scheduleId;
  state.selectedSeats.clear();
  state.schedule = null;
  renderMovies();
  renderSeats();
  try {
    state.schedule = await api(`/api/schedule?jadwal_id=${encodeURIComponent(scheduleId)}`);
    renderMovies();
    renderSeats();
    document.querySelector('#jadwal').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    showConnection(`Jadwal tidak dapat dimuat: ${error.message}`, true);
  }
}

function closeAllStatusStreams() {
  for (const stream of state.statusStreams.values()) stream.close();
  state.statusStreams.clear();
}

function watchSeatStatus(seatId) {
  if (state.statusStreams.has(seatId) || !state.selectedScheduleId) return;
  const query = new URLSearchParams({ jadwal_id: state.selectedScheduleId, kursi_id: seatId });
  const stream = new EventSource(`/api/stream-status?${query}`);
  state.statusStreams.set(seatId, stream);
  stream.onmessage = (event) => {
    const update = JSON.parse(event.data);
    if (state.schedule?.jadwal_id !== update.jadwal_id) return;
    const seat = state.schedule.kursi.find((item) => item.kursi_id === update.kursi_id);
    if (!seat) return;
    Object.assign(seat, update);
    if (update.status !== 'AVAILABLE' && update.user_id !== state.user?.id && state.selectedSeats.delete(update.kursi_id)) {
      notify(`Kursi ${update.kursi_id} baru saja ditahan oleh pemesan lain.`);
      stream.close();
      state.statusStreams.delete(seatId);
    }
    renderSeats();
  };
  stream.onerror = () => {
    // EventSource akan mencoba tersambung kembali otomatis.
  };
}

function toggleSeat(seatId) {
  const seat = state.schedule?.kursi.find((item) => item.kursi_id === seatId);
  if (!seat || seat.status !== 'AVAILABLE') return;
  if (state.selectedSeats.has(seatId)) {
    state.selectedSeats.delete(seatId);
    state.statusStreams.get(seatId)?.close();
    state.statusStreams.delete(seatId);
  } else {
    state.selectedSeats.add(seatId);
    watchSeatStatus(seatId);
  }
  renderSeats();
}

async function cancelHold(seatId) {
  const seat = state.schedule?.kursi.find((item) => item.kursi_id === seatId);
  if (!seat || seat.status !== 'PENDING_PAYMENT' || seat.user_id !== state.user?.id) return;
  try {
    const result = await api('/api/cancel', {
      method: 'POST',
      body: JSON.stringify({
        request_id: createRequestId(),
        jadwal_id: state.schedule.jadwal_id,
        kursi_id: seatId,
        user_id: state.user.id,
      }),
    });
    await refreshSelectedSchedule();
    notify(result.pesan);
  } catch (error) {
    notify(`Hold tidak dapat dibatalkan: ${error.message}`, true);
  }
}

async function refreshSelectedSchedule() {
  if (!state.selectedScheduleId) return;
  state.schedule = await api(`/api/schedule?jadwal_id=${encodeURIComponent(state.selectedScheduleId)}`);
  const summary = state.schedules.find((item) => item.jadwal_id === state.selectedScheduleId);
  if (summary) summary.kursi_tersedia = state.schedule.kursi_tersedia;
  renderMovies();
  renderSeats();
}

function notify(message, isError = false) {
  const element = document.querySelector('#toast');
  element.textContent = message;
  element.classList.toggle('is-error', isError);
  element.classList.add('is-visible');
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => element.classList.remove('is-visible'), 4200);
}

function openBookingDialog() {
  const schedule = state.schedule;
  const selected = [...state.selectedSeats].sort((a, b) => a.localeCompare(b, 'id', { numeric: true }));
  if (!schedule || !selected.length) return;
  dialogCopy.textContent = `${schedule.nama_film} · ${schedule.jam_tayang.slice(0, 5)} · ${schedule.studio_id} · Kursi ${selected.join(', ')}`;
  dialogFeedback.textContent = '';
  confirmBookingButton.disabled = false;
  confirmBookingButton.dataset.done = 'false';
  confirmBookingButton.textContent = 'Pesan kursi';
  confirmBookingButton.onclick = null;
  bookingDialog.showModal();
  if (state.user?.name) customerName.value = state.user.name;
  customerName.focus();
}

async function submitBooking() {
  const name = customerName.value.trim();
  if (!name) {
    customerName.focus();
    dialogFeedback.textContent = 'Masukkan nama pemesan terlebih dahulu.';
    return;
  }

  const user = state.user?.name === name
    ? state.user
    : { id: `web-${createRequestId()}`, name };
  state.user = user;
  storeUser(user);

  const schedule = state.schedule;
  const selected = [...state.selectedSeats].sort((a, b) => a.localeCompare(b, 'id', { numeric: true }));
  confirmBookingButton.disabled = true;
  dialogFeedback.textContent = 'Memproses hold kursi di server…';
  const results = [];

  for (const seatId of selected) {
    try {
      const result = await api('/api/book', {
        method: 'POST',
        body: JSON.stringify({
          request_id: createRequestId(),
          jadwal_id: schedule.jadwal_id,
          kursi_id: seatId,
          user_id: user.id,
        }),
      });
      const until = new Date(result.held_until * 1000).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
      results.push(`${seatId} berhasil ditahan sampai ${until}`);
    } catch (error) {
      results.push(`${seatId} gagal: ${error.message}`);
    }
  }

  state.selectedSeats.clear();
  closeAllStatusStreams();
  try {
    state.schedule = await api(`/api/schedule?jadwal_id=${encodeURIComponent(schedule.jadwal_id)}`);
    const summary = state.schedules.find((item) => item.jadwal_id === schedule.jadwal_id);
    if (summary) summary.kursi_tersedia = state.schedule.kursi_tersedia;
    renderMovies();
    renderSeats();
  } catch (error) {
    console.error('Gagal menyegarkan status kursi:', error);
  }

  dialogFeedback.textContent = results.join('. ');
  confirmBookingButton.disabled = false;
  confirmBookingButton.dataset.done = 'true';
  confirmBookingButton.textContent = 'Selesai';
}

function showReceipt(schedule, seatIds, orderCode) {
  const paidAt = new Date();
  document.querySelector('#receipt-customer').textContent = state.user?.name || 'Pemesan Wartix';
  document.querySelector('#receipt-date').textContent = new Intl.DateTimeFormat('id-ID', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(paidAt);
  document.querySelector('#receipt-code').textContent = orderCode;
  document.querySelector('#receipt-film-name').textContent = schedule.nama_film;
  document.querySelector('#receipt-showtime').textContent = schedule.jam_tayang.slice(0, 5);
  document.querySelector('#receipt-studio').textContent = schedule.studio_id;
  document.querySelector('#receipt-quantity').textContent = `${seatIds.length} tiket`;

  const itemList = document.querySelector('#receipt-seat-list');
  itemList.replaceChildren();
  for (const [index, seatId] of seatIds.entries()) {
    const row = document.createElement('li');
    for (const value of [String(index + 1).padStart(2, '0'), seatId, 'TERJUAL']) {
      const cell = document.createElement('span');
      cell.textContent = value;
      row.appendChild(cell);
    }
    itemList.appendChild(row);
  }
  receiptDialog.showModal();
}

async function confirmHeldSeats() {
  if (!state.selectedScheduleId || !state.user?.id) return;

  paymentButton.disabled = true;
  paymentFeedback.hidden = false;
  paymentFeedback.textContent = 'Memeriksa status hold terbaru di server…';
  try {
    await refreshSelectedSchedule();
  } catch (error) {
    paymentButton.disabled = false;
    paymentFeedback.textContent = `Status kursi tidak dapat diperiksa: ${error.message}`;
    return;
  }

  const schedule = state.schedule;
  const heldSeats = schedule?.kursi
    .filter((seat) => seat.status === 'PENDING_PAYMENT' && seat.user_id === state.user.id)
    .map((seat) => seat.kursi_id)
    .sort((a, b) => a.localeCompare(b, 'id', { numeric: true }));
  if (!heldSeats.length) {
    paymentFeedback.textContent = 'Hold sudah kedaluwarsa atau tidak lagi aktif. Pilih kursi yang tersedia lalu pesan kembali.';
    notify('Hold kursi sudah tidak aktif. Silakan pesan kembali.', true);
    return;
  }

  paymentButton.textContent = 'Mengonfirmasi pembayaran…';
  paymentFeedback.textContent = 'Mengirim konfirmasi pembayaran ke server…';
  const confirmedSeats = [];
  const failedSeats = [];
  const orderCode = `WTX-${new Date().toISOString().slice(0, 10).replaceAll('-', '')}-${createRequestId().slice(0, 8).toUpperCase()}`;

  for (const seatId of heldSeats) {
    try {
      await api('/api/confirm', {
        method: 'POST',
        body: JSON.stringify({
          request_id: createRequestId(),
          jadwal_id: schedule.jadwal_id,
          kursi_id: seatId,
          user_id: state.user.id,
        }),
      });
      confirmedSeats.push(seatId);
    } catch (error) {
      failedSeats.push(`${seatId}: ${error.message}`);
    }
  }

  try {
    await refreshSelectedSchedule();
  } catch (error) {
    console.error('Gagal menyegarkan status kursi setelah pembayaran:', error);
  }

  if (confirmedSeats.length) {
    paymentFeedback.textContent = `Pembayaran berhasil. Kursi ${confirmedSeats.join(', ')} sekarang berstatus terjual.`;
    showReceipt(schedule, confirmedSeats, orderCode);
  }
  if (failedSeats.length) {
    paymentFeedback.textContent = `Tidak semua kursi berhasil dikonfirmasi: ${failedSeats.join('; ')}.`;
    notify(`Pembayaran gagal untuk ${failedSeats.join('; ')}. Periksa status kursi dan coba lagi.`, true);
  } else if (!confirmedSeats.length) {
    paymentFeedback.textContent = 'Pembayaran tidak berhasil. Hold mungkin sudah kedaluwarsa.';
    notify('Pembayaran tidak berhasil. Hold mungkin sudah kedaluwarsa.', true);
  }
}

movieGrid.addEventListener('click', (event) => {
  const retry = event.target.closest('#retry-catalog');
  if (retry) {
    loadSchedules();
    return;
  }
  const button = event.target.closest('[data-schedule]');
  if (button) chooseSchedule(button.dataset.schedule);
});

seatMap.addEventListener('click', (event) => {
  const button = event.target.closest('[data-seat]');
  if (!button || button.disabled) return;
  if (button.dataset.cancelSeat) cancelHold(button.dataset.cancelSeat);
  else toggleSeat(button.dataset.seat);
});

bookingButton.addEventListener('click', openBookingDialog);
paymentButton.addEventListener('click', async () => {
  try {
    await confirmHeldSeats();
  } catch (error) {
    paymentButton.disabled = false;
    paymentFeedback.hidden = false;
    paymentFeedback.textContent = `Konfirmasi pembayaran gagal: ${error.message}`;
    notify(`Konfirmasi pembayaran gagal: ${error.message}`, true);
  }
});
document.querySelector('#receipt-close-button').addEventListener('click', () => receiptDialog.close());
document.querySelector('#receipt-close-action').addEventListener('click', () => receiptDialog.close());
document.querySelector('#receipt-print-button').addEventListener('click', () => window.print());
confirmBookingButton.addEventListener('click', async () => {
  if (confirmBookingButton.dataset.done === 'true') bookingDialog.close();
  else {
    try {
      await submitBooking();
    } catch (error) {
      confirmBookingButton.disabled = false;
      dialogFeedback.textContent = `Pemesanan gagal: ${error.message}`;
    }
  }
});

const menuToggle = document.querySelector('.menu-toggle');
const mainNav = document.querySelector('.main-nav');
menuToggle.addEventListener('click', () => {
  const open = menuToggle.getAttribute('aria-expanded') !== 'true';
  menuToggle.setAttribute('aria-expanded', String(open));
  menuToggle.setAttribute('aria-label', open ? 'Tutup navigasi' : 'Buka navigasi');
  mainNav.classList.toggle('is-open', open);
});
mainNav.addEventListener('click', (event) => {
  if (event.target.closest('a')) {
    mainNav.classList.remove('is-open');
    menuToggle.setAttribute('aria-expanded', 'false');
    menuToggle.setAttribute('aria-label', 'Buka navigasi');
  }
});

state.user = readStoredUser();

renderSeats();
loadSchedules();
