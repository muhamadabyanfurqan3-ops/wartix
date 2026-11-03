const films = [
  { id: 'interstellar', title: 'Interstellar', genre: 'Petualangan · Fiksi ilmiah', duration: '2j 49m', studio: 'Studio 1', times: ['13.00', '16.40'], art: 'space', number: '01' },
  { id: 'oppenheimer', title: 'Oppenheimer', genre: 'Drama · Sejarah', duration: '3j 00m', studio: 'Studio 2', times: ['15.40', '19.10'], art: 'fire', number: '02' },
  { id: 'inception', title: 'Inception', genre: 'Aksi · Fiksi ilmiah', duration: '2j 28m', studio: 'Studio 1', times: ['18.00', '20.30'], art: 'dream', number: '03' },
];

const occupiedByFilm = {
  interstellar: ['A4', 'A5', 'B4', 'C8', 'D8', 'E2'],
  oppenheimer: ['A2', 'B2', 'B3', 'C6', 'E5', 'F5'],
  inception: ['A7', 'B7', 'C3', 'D3', 'E9', 'F9'],
};

const state = { date: 0, filmId: null, time: null, seats: new Set() };
const movieGrid = document.querySelector('#movie-grid');
const dateOptions = document.querySelector('#date-options');
const seatMap = document.querySelector('#seat-map');
const seatSummary = document.querySelector('#seat-summary-text');
const bookingButton = document.querySelector('#booking-button');
const selectedShowCopy = document.querySelector('#selected-show-copy');

function renderDates() {
  const today = new Date();
  const dates = Array.from({ length: 4 }, (_, index) => {
    const day = new Date(today);
    day.setDate(today.getDate() + index);
    return day;
  });
  dateOptions.innerHTML = dates.map((date, index) => {
    const dayName = index === 0 ? 'Hari ini' : new Intl.DateTimeFormat('id-ID', { weekday: 'long' }).format(date);
    const dateLabel = new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short' }).format(date);
    return `<button class="date-button" type="button" data-date="${index}" aria-pressed="${state.date === index}"><strong>${dayName}</strong>${dateLabel}</button>`;
  }).join('');
}

function selectedDateLabel() {
  const date = new Date();
  date.setDate(date.getDate() + state.date);
  return new Intl.DateTimeFormat('id-ID', { weekday: 'long', day: 'numeric', month: 'long' }).format(date);
}

function renderMovies() {
  movieGrid.innerHTML = films.map((film) => `
    <article class="movie-card">
      <div class="movie-poster poster-${film.art}" role="img" aria-label="Ilustrasi film ${film.title}">
        <span class="poster-label">WARTIX · PILIHAN FILM</span>
        <strong class="poster-title">${film.title === 'Interstellar' ? 'INTER<br>STELLAR' : film.title.toUpperCase()}</strong>
        <span class="poster-number" aria-hidden="true">${film.number}</span>
      </div>
      <div class="movie-details">
        <h3>${film.title}</h3>
        <span class="movie-duration">${film.duration}</span>
        <p class="movie-meta">${film.genre} · ${film.studio}</p>
        <div class="showtimes" aria-label="Pilih jam tayang ${film.title}">
          ${film.times.map((time) => `<button class="time-button" type="button" data-film="${film.id}" data-time="${time}" aria-pressed="${state.filmId === film.id && state.time === time}">${time}</button>`).join('')}
        </div>
      </div>
    </article>`).join('');
}

function renderSeats() {
  const selectedFilm = films.find((film) => film.id === state.filmId);
  if (!selectedFilm || !state.time) {
    selectedShowCopy.textContent = 'Pilih film dan jadwal tayang untuk melihat denah kursi.';
    seatMap.innerHTML = '<p class="seat-empty">Denah kursi akan muncul setelah jadwal dipilih.</p>';
    seatSummary.textContent = 'Belum ada';
    bookingButton.disabled = true;
    return;
  }

  selectedShowCopy.textContent = `${selectedFilm.title} · ${selectedDateLabel()} · ${state.time} · ${selectedFilm.studio}`;
  const occupied = occupiedByFilm[selectedFilm.id];
  const rows = ['A', 'B', 'C', 'D', 'E', 'F'];
  seatMap.innerHTML = rows.map((row) => `
    <span class="row-label" aria-hidden="true">${row}</span>
    ${Array.from({ length: 10 }, (_, index) => {
      const seat = `${row}${index + 1}`;
      const taken = occupied.includes(seat);
      const chosen = state.seats.has(seat);
      return `<button class="seat ${taken ? 'occupied' : chosen ? 'selected' : 'available'}" type="button" data-seat="${seat}" aria-label="Kursi ${seat}${taken ? ', terisi' : chosen ? ', dipilih' : ', tersedia'}" aria-pressed="${chosen}" ${taken ? 'disabled' : ''}></button>`;
    }).join('')}`).join('');

  const selection = [...state.seats].sort((a, b) => a.localeCompare(b, 'id', { numeric: true }));
  seatSummary.textContent = selection.length ? selection.join(', ') : 'Belum ada';
  bookingButton.disabled = selection.length === 0;
}

dateOptions.addEventListener('click', (event) => {
  const button = event.target.closest('[data-date]');
  if (!button) return;
  state.date = Number(button.dataset.date);
  renderDates();
  renderSeats();
});

movieGrid.addEventListener('click', (event) => {
  const button = event.target.closest('[data-time]');
  if (!button) return;
  state.filmId = button.dataset.film;
  state.time = button.dataset.time;
  state.seats.clear();
  renderMovies();
  renderSeats();
  document.querySelector('#jadwal').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

seatMap.addEventListener('click', (event) => {
  const button = event.target.closest('[data-seat]');
  if (!button || button.disabled) return;
  const seat = button.dataset.seat;
  if (state.seats.has(seat)) state.seats.delete(seat);
  else state.seats.add(seat);
  renderSeats();
});

bookingButton.addEventListener('click', () => {
  const film = films.find((item) => item.id === state.filmId);
  document.querySelector('#dialog-copy').textContent = `${film.title}, ${selectedDateLabel()}, pukul ${state.time}, ${film.studio}. Kursi ${[...state.seats].sort().join(', ')}.`;
  document.querySelector('#booking-dialog').showModal();
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

renderDates();
renderMovies();
renderSeats();
