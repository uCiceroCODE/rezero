/**
 * Re:Zero Japanese Reader - Core Client Application
 */

const STATE = {
  books: [],
  currentBook: null,
  currentSpineIndex: 0,
  currentChapter: null,
  seenTerms: {},
  activeSentenceContext: '',
  activeWordContext: null,
  activePopupWord: '',
  
  // Settings
  settings: {
    theme: 'slate',
    writingMode: 'vertical',
    fontSize: 22,
    lineHeight: 2.2,
    letterSpacing: 0.08,
    fontFamily: "'Noto Serif JP', 'Hiragino Mincho ProN', 'Yu Mincho', serif",
    furiganaMode: 'original',
    highlightSeen: true
  },

  // Reading stats
  sessionSeconds: 0,
  sessionChars: 0,
  isWindowActive: true,
  idleTimeout: null,
  progressSaveTimer: null
};

// Segmenter for Japanese words
const jaSegmenter = (typeof Intl !== 'undefined' && Intl.Segmenter) 
  ? new Intl.Segmenter('ja', { granularity: 'word' }) 
  : null;

// ==========================================================================
// Initialization
// ==========================================================================

document.addEventListener('DOMContentLoaded', async () => {
  loadSavedSettings();
  applySettings();
  setupEventListeners();
  setupReadingTimer();
  await loadSeenTerms();
  await loadBooks();
});

function loadSavedSettings() {
  const saved = localStorage.getItem('rezero_reader_settings');
  if (saved) {
    try {
      STATE.settings = { ...STATE.settings, ...JSON.parse(saved) };
    } catch (e) {
      console.error(e);
    }
  }
}

function saveSettings() {
  localStorage.setItem('rezero_reader_settings', JSON.stringify(STATE.settings));
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: 'user_preferences', value: STATE.settings })
  }).catch(() => {});
}

function applySettings() {
  const root = document.documentElement;
  const s = STATE.settings;

  // Theme
  root.setAttribute('data-theme', s.theme);
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.setTheme === s.theme);
  });

  // Typography
  root.style.setProperty('--reader-font-size', `${s.fontSize}px`);
  root.style.setProperty('--reader-line-height', s.lineHeight);
  root.style.setProperty('--reader-letter-spacing', `${s.letterSpacing}em`);
  root.style.setProperty('--font-ja', s.fontFamily);
  
  // Sliders display values
  const elSize = document.getElementById('slider-font-size');
  if (elSize) elSize.value = s.fontSize;
  const valSize = document.getElementById('val-font-size');
  if (valSize) valSize.textContent = `${s.fontSize}px`;

  const elLine = document.getElementById('slider-line-height');
  if (elLine) elLine.value = Math.round(s.lineHeight * 10);
  const valLine = document.getElementById('val-line-height');
  if (valLine) valLine.textContent = s.lineHeight;

  const elSpacing = document.getElementById('slider-letter-spacing');
  if (elSpacing) elSpacing.value = Math.round(s.letterSpacing * 100);
  const valSpacing = document.getElementById('val-letter-spacing');
  if (valSpacing) valSpacing.textContent = `${s.letterSpacing}em`;

  const selFont = document.getElementById('select-font-family');
  if (selFont) selFont.value = s.fontFamily;

  // Furigana
  root.setAttribute('data-furigana', s.furiganaMode);
  const selFurigana = document.getElementById('select-furigana-mode');
  if (selFurigana) selFurigana.value = s.furiganaMode;

  // Writing mode
  const stage = document.getElementById('reader-stage');
  const modeInd = document.getElementById('writing-mode-indicator');
  const valMode = document.getElementById('val-writing-mode');
  if (stage) {
    if (s.writingMode === 'vertical') {
      stage.classList.remove('mode-horizontal');
      stage.classList.add('mode-vertical');
      if (modeInd) modeInd.textContent = '縦';
      if (valMode) valMode.textContent = 'Verticale (縦書き)';
    } else {
      stage.classList.remove('mode-vertical');
      stage.classList.add('mode-horizontal');
      if (modeInd) modeInd.textContent = '横';
      if (valMode) valMode.textContent = 'Orizzontale (横書き)';
    }
  }

  // Vocab highlight
  const chkSeen = document.getElementById('check-highlight-seen');
  if (chkSeen) chkSeen.checked = s.highlightSeen;
}

// ==========================================================================
// API & Data Loading
// ==========================================================================

async function loadBooks() {
  try {
    const res = await fetch('/api/books');
    STATE.books = await res.json();
    renderLibrary();
  } catch (e) {
    console.error('Failed to load books:', e);
  }
}

async function loadSeenTerms() {
  try {
    const res = await fetch('/api/seen_terms');
    STATE.seenTerms = await res.json();
  } catch (e) {
    console.error('Failed to load seen terms:', e);
  }
}

function renderLibrary(filterText = '') {
  const grid = document.getElementById('books-grid');
  const heroContainer = document.getElementById('continue-reading-container');
  grid.innerHTML = '';

  const filter = filterText.toLowerCase().trim();
  const filtered = STATE.books.filter(b => 
    b.title.toLowerCase().includes(filter) || 
    b.filename.toLowerCase().includes(filter) ||
    `vol ${b.volume}`.includes(filter)
  );

  // Find most recently read book for Hero Banner
  let mostRecent = null;
  for (const b of STATE.books) {
    if (b.progress && b.progress.updated_at) {
      if (!mostRecent || b.progress.updated_at > mostRecent.progress.updated_at) {
        mostRecent = b;
      }
    }
  }

  if (mostRecent && !filter) {
    const p = mostRecent.progress;
    heroContainer.innerHTML = `
      <div class="continue-hero">
        <img class="continue-cover" src="${mostRecent.cover_url}" alt="Cover" onerror="this.src='/static/placeholder.jpg'">
        <div class="continue-info">
          <div class="continue-tag">Continua la Lettura</div>
          <div class="continue-title">${mostRecent.title}</div>
          <div class="continue-meta">
            Capitolo ${p.spine_index + 1} di ${mostRecent.total_spine} • ${p.percent}% completato
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width: ${p.percent}%;"></div>
          </div>
          <button class="btn btn-primary" onclick="openBook('${mostRecent.id}', ${p.spine_index})">
            ▶️ Riprendi Lettura
          </button>
        </div>
      </div>
    `;
  } else {
    heroContainer.innerHTML = '';
  }

  // Render cards
  filtered.forEach(book => {
    const p = book.progress || {};
    const percent = p.percent || 0;
    const card = document.createElement('div');
    card.className = 'book-card';
    card.onclick = () => openBook(book.id, p.spine_index || 0);

    card.innerHTML = `
      <div class="book-cover-wrap">
        <img class="book-cover" src="${book.cover_url}" alt="Cover" loading="lazy">
        <div class="book-badge-vol">Vol. ${book.volume}</div>
        <div class="book-badge-prog">
          <div class="book-badge-prog-fill" style="width: ${percent}%;"></div>
        </div>
      </div>
      <div class="book-details">
        <div class="book-title" title="${book.title}">${book.title}</div>
        <div class="book-meta">
          <span>${percent}% letto</span>
          <span>${book.total_spine} parti</span>
        </div>
      </div>
    `;
    grid.appendChild(card);
  });
}

// ==========================================================================
// Reader Operations
// ==========================================================================

async function openBook(bookId, spineIndex = 0) {
  const book = STATE.books.find(b => b.id === bookId);
  if (!book) return;

  STATE.currentBook = book;
  STATE.currentSpineIndex = spineIndex;

  document.getElementById('library-view').style.display = 'none';
  document.getElementById('reader-view').style.display = 'flex';

  document.getElementById('tb-book-title').textContent = book.title;

  await loadChapter(spineIndex);
  await loadTOC();
}

function closeReader() {
  saveCurrentProgress();
  document.getElementById('reader-view').style.display = 'none';
  document.getElementById('library-view').style.display = 'block';
  STATE.currentBook = null;
  loadBooks(); // refresh progress indicators
}

async function loadChapter(spineIndex) {
  if (!STATE.currentBook) return;

  const textContainer = document.getElementById('reader-text');
  textContainer.innerHTML = '<div style="padding: 40px; text-align: center; color: var(--text-secondary);">Caricamento capitolo...</div>';

  try {
    const furiganaParam = STATE.settings.furiganaMode === 'auto' ? '?furigana=auto' : '';
    const res = await fetch(`/api/book/${STATE.currentBook.id}/chapter/${spineIndex}${furiganaParam}`);
    if (!res.ok) throw new Error('Chapter load error');
    
    const data = await res.json();
    STATE.currentChapter = data;
    STATE.currentSpineIndex = spineIndex;

    document.getElementById('tb-chapter-title').textContent = data.chapter_title || `Parte ${spineIndex + 1}`;
    document.getElementById('chapter-counter').textContent = `${spineIndex + 1} / ${data.total_spine}`;

    // Update bottom nav buttons
    document.getElementById('btn-prev-chapter').disabled = (data.prev_index === null);
    document.getElementById('btn-next-chapter').disabled = (data.next_index === null);

    // Render HTML and process Japanese words
    textContainer.innerHTML = data.content_html;
    processJapaneseWords(textContainer);
    setupIllustrationLightbox(textContainer);

    // Scroll to start
    const stage = document.getElementById('reader-stage');
    if (STATE.settings.writingMode === 'vertical') {
      stage.scrollLeft = stage.scrollWidth; // Japanese vertical starts right
    } else {
      stage.scrollTop = 0;
    }

    // Update stats
    STATE.lastCharCount = data.char_count || 0;
    STATE.sessionChars += STATE.lastCharCount;

    saveCurrentProgress();
  } catch (e) {
    console.error('Error loading chapter:', e);
    textContainer.innerHTML = '<div style="padding: 40px; text-align: center; color: var(--danger);">Errore nel caricamento del capitolo.</div>';
  }
}

// ==========================================================================
// Japanese Segmentation & Interactive Word Lookup
// ==========================================================================

function processJapaneseWords(rootElement) {
  if (!jaSegmenter) return;

  // Walk text nodes outside script, style, rt
  const walker = document.createTreeWalker(
    rootElement,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent) return NodeFilter.FILTER_REJECT;
        const tag = parent.tagName.toLowerCase();
        if (['script', 'style', 'rt', 'rp', 'title'].includes(tag)) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      }
    }
  );

  const textNodes = [];
  while (walker.nextNode()) {
    textNodes.push(walker.currentNode);
  }

  for (const node of textNodes) {
    const text = node.nodeValue;
    // Check if contains Japanese or word characters
    if (!/[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uff00-\uffef\u4e00-\u9faf]/.test(text)) {
      continue;
    }

    const segments = Array.from(jaSegmenter.segment(text));
    const frag = document.createDocumentFragment();

    for (const seg of segments) {
      const w = seg.segment;
      // Skip pure punctuation or spaces
      if (/^[\s\u3000。、？！「」『』（）…─―]+$/.test(w)) {
        frag.appendChild(document.createTextNode(w));
      } else {
        const span = document.createElement('span');
        span.className = 'ja-word';
        span.textContent = w;
        span.dataset.word = w;

        // Apply tracking status
        if (STATE.settings.highlightSeen && STATE.seenTerms[w]) {
          const status = STATE.seenTerms[w].status;
          span.classList.add(`term-${status}`);
        }

        span.addEventListener('click', onWordClick);
        frag.appendChild(span);
      }
    }

    node.parentNode.replaceChild(frag, node);
  }
}

async function onWordClick(e) {
  e.stopPropagation();
  const word = e.currentTarget.dataset.word;
  if (!word) return;

  // Find sentence context
  const p = e.currentTarget.closest('p, div, li') || e.currentTarget.parentElement;
  STATE.activeSentenceContext = p ? p.innerText.trim() : word;
  STATE.activeWordContext = e.currentTarget;
  STATE.activePopupWord = word;

  showDictionaryPopup(word, e.currentTarget);
}

async function showDictionaryPopup(word, anchorElement) {
  const popup = document.getElementById('dict-popup');
  const termEl = document.getElementById('dp-term');
  const readingEl = document.getElementById('dp-reading');
  const defsEl = document.getElementById('dp-defs');
  const transEl = document.getElementById('dp-trans-preview');

  transEl.style.display = 'none';
  transEl.textContent = '';
  termEl.textContent = word;
  readingEl.textContent = 'Ricerca nel dizionario...';
  defsEl.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">Caricamento definizioni...</div>';

  popup.style.display = 'block';

  // Position popup near anchor
  const rect = anchorElement.getBoundingClientRect();
  let top = rect.bottom + 8;
  let left = rect.left;

  // Boundary check
  if (left + 320 > window.innerWidth) {
    left = window.innerWidth - 330;
  }
  if (top + 280 > window.innerHeight) {
    top = Math.max(10, rect.top - 290);
  }

  popup.style.top = `${top}px`;
  popup.style.left = `${Math.max(10, left)}px`;

  // Fetch dictionary data
  try {
    const res = await fetch(`/api/dictionary/lookup?word=${encodeURIComponent(word)}`);
    const data = await res.json();

    if (data.found && data.results.length > 0) {
      const first = data.results[0];
      termEl.textContent = first.kanji || word;
      readingEl.textContent = first.reading || '';

      let defsHtml = '<ol>';
      data.results.forEach(r => {
        const defStr = r.definitions.join(', ');
        defsHtml += `<li><strong>${r.reading || ''}</strong>: ${defStr}</li>`;
      });
      defsHtml += '</ol>';
      defsEl.innerHTML = defsHtml;

      // Update state for mining
      STATE.activeWordReading = first.reading || '';
      STATE.activeWordDef = first.definitions.join('; ');
    } else {
      readingEl.textContent = 'Nessuna voce trovata';
      defsEl.innerHTML = '<div style="color: var(--text-muted);">Voce non presente nel dizionario locale. Clicca Jisho.org sotto.</div>';
      STATE.activeWordReading = '';
      STATE.activeWordDef = '';
    }
  } catch (err) {
    console.error(err);
    defsEl.innerHTML = '<div style="color: var(--danger);">Errore durante il lookup.</div>';
  }
}

function hideDictionaryPopup() {
  const popup = document.getElementById('dict-popup');
  if (popup) popup.style.display = 'none';
}

// ==========================================================================
// Actions inside Dictionary Popup (Mine, Audio, Translate, Known)
// ==========================================================================

// Audio Pronunciation (Web Speech API)
function playPronunciation(text) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'ja-JP';
  utterance.rate = 0.9;
  window.speechSynthesis.speak(utterance);
}

// Mine Word to Vocab (Anki)
async function mineWord() {
  const word = STATE.activePopupWord;
  if (!word) return;

  const body = {
    word: word,
    reading: STATE.activeWordReading || '',
    definition: STATE.activeWordDef || '',
    sentence: STATE.activeSentenceContext || '',
    source_book: STATE.currentBook ? STATE.currentBook.title : '',
    status: 'learning'
  };

  try {
    await fetch('/api/vocab', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    STATE.seenTerms[word] = { term: word, status: 'learning' };
    if (STATE.activeWordContext) {
      STATE.activeWordContext.classList.add('term-learning');
    }

    const mineBtn = document.getElementById('dp-mine-btn');
    mineBtn.textContent = '✓ Salvato!';
    setTimeout(() => { mineBtn.textContent = '⭐ Salva (Mine)'; }, 1500);
  } catch (e) {
    console.error('Error saving vocab:', e);
  }
}

// Mark word as Known
async function markWordKnown() {
  const word = STATE.activePopupWord;
  if (!word) return;

  try {
    await fetch('/api/seen_terms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ term: word, status: 'known' })
    });

    STATE.seenTerms[word] = { term: word, status: 'known' };
    if (STATE.activeWordContext) {
      STATE.activeWordContext.classList.remove('term-learning');
      STATE.activeWordContext.classList.add('term-known');
    }

    const knownBtn = document.getElementById('dp-known-btn');
    knownBtn.textContent = '✓ Conosciuto';
    setTimeout(() => { knownBtn.textContent = '👁️ Già visto'; }, 1500);
  } catch (e) {
    console.error('Error marking term:', e);
  }
}

// Free Sentence Translation
async function translateActiveSentence() {
  const text = STATE.activeSentenceContext;
  if (!text) return;

  const transEl = document.getElementById('dp-trans-preview');
  transEl.style.display = 'block';
  transEl.textContent = 'Traduzione in corso...';

  try {
    const res = await fetch('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, lang: 'it' })
    });
    const data = await res.json();
    if (data.success) {
      transEl.innerHTML = `<strong>🇮🇹 Traduzione:</strong> ${data.translated}`;
    } else {
      transEl.textContent = 'Traduzione non disponibile.';
    }
  } catch (e) {
    transEl.textContent = 'Errore di connessione al traduttore.';
  }
}

// ==========================================================================
// Text Selection Bar & Sentence Mining
// ==========================================================================

function setupTextSelection() {
  document.addEventListener('selectionchange', () => {
    const sel = window.getSelection();
    const bar = document.getElementById('selection-bar');
    if (!sel || sel.isCollapsed || !sel.toString().trim()) {
      if (bar) bar.style.display = 'none';
      return;
    }

    const text = sel.toString().trim();
    if (text.length < 2) return;

    try {
      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      if (rect.width === 0) return;

      bar.style.display = 'flex';
      bar.style.top = `${Math.max(10, rect.top - 44)}px`;
      bar.style.left = `${Math.max(10, rect.left + rect.width / 2 - 100)}px`;
    } catch (e) {}
  });

  document.getElementById('sb-translate-btn')?.addEventListener('click', async () => {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : '';
    if (!text) return;

    const bar = document.getElementById('selection-bar');
    bar.innerHTML = '<span style="font-size: 12px; padding: 6px;">Traduzione...</span>';

    try {
      const res = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text, lang: 'it' })
      });
      const data = await res.json();
      alert(`Traduzione (Italiano):\n\n${data.translated}`);
    } catch (e) {
      alert('Errore traduzione');
    }
    bar.style.display = 'none';
    bar.innerHTML = `
      <button class="btn" id="sb-translate-btn">Traduci Selezione</button>
      <button class="btn" id="sb-save-sentence-btn">Salva Frase</button>
    `;
    setupTextSelection();
  });

  document.getElementById('sb-save-sentence-btn')?.addEventListener('click', async () => {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : '';
    if (!text) return;

    try {
      // Get translation first
      const tRes = await fetch('/api/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text, lang: 'it' })
      });
      const tData = await tRes.json();

      await fetch('/api/sentences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sentence: text,
          translation: tData.translated || '',
          note: '',
          source_book: STATE.currentBook ? STATE.currentBook.title : ''
        })
      });
      alert('Frase salvata nel taccuino!');
    } catch (e) {
      alert('Errore nel salvataggio della frase.');
    }
    document.getElementById('selection-bar').style.display = 'none';
  });
}

// ==========================================================================
// Bookmarks
// ==========================================================================

async function addCurrentBookmark() {
  if (!STATE.currentBook) return;

  const stage = document.getElementById('reader-stage');
  const snippet = STATE.activeSentenceContext || 
                  (document.querySelector('.reader-text-container p')?.innerText.slice(0, 80) || 'Segnalibro');

  const body = {
    book_id: STATE.currentBook.id,
    spine_index: STATE.currentSpineIndex,
    chapter_title: STATE.currentChapter ? STATE.currentChapter.chapter_title : '',
    snippet: snippet,
    note: ''
  };

  try {
    await fetch('/api/bookmarks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    const btn = document.getElementById('btn-add-bookmark');
    btn.classList.add('active');
    setTimeout(() => btn.classList.remove('active'), 1500);
    alert('Segnalibro salvato!');
  } catch (e) {
    console.error('Error adding bookmark:', e);
  }
}

async function loadBookmarksList() {
  const container = document.getElementById('bookmarks-list');
  container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">Caricamento segnalibri...</div>';

  try {
    const res = await fetch(`/api/bookmarks${STATE.currentBook ? `?book_id=${STATE.currentBook.id}` : ''}`);
    const bms = await res.json();

    if (bms.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">Nessun segnalibro salvato.</div>';
      return;
    }

    container.innerHTML = '';
    bms.forEach(bm => {
      const card = document.createElement('div');
      card.className = 'card-item';
      card.innerHTML = `
        <div class="card-header">
          <strong>${bm.chapter_title || 'Capitolo'}</strong>
          <span style="font-size: 11px; color: var(--text-muted);">${bm.created_at}</span>
        </div>
        <div class="card-sentence">${bm.snippet}</div>
        <div class="card-actions">
          <button class="btn btn-primary" style="font-size: 11px; padding: 4px 8px;" onclick="jumpToBookmark('${bm.book_id}', ${bm.spine_index})">Vai</button>
          <button class="btn" style="font-size: 11px; padding: 4px 8px;" onclick="deleteBookmark(${bm.id})">Elimina</button>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = 'Errore caricamento segnalibri.';
  }
}

async function jumpToBookmark(bookId, spineIndex) {
  closeDrawers();
  await openBook(bookId, spineIndex);
}

async function deleteBookmark(id) {
  await fetch(`/api/bookmarks/${id}`, { method: 'DELETE' });
  loadBookmarksList();
}

// ==========================================================================
// Table of Contents
// ==========================================================================

async function loadTOC() {
  if (!STATE.currentBook) return;
  const container = document.getElementById('toc-items-container');
  container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">Caricamento indice...</div>';

  try {
    const res = await fetch(`/api/book/${STATE.currentBook.id}/toc`);
    const toc = await res.json();

    container.innerHTML = '';
    if (toc.length === 0) {
      // Fallback: list of spine items
      for (let i = 0; i < STATE.currentBook.total_spine; i++) {
        const item = document.createElement('div');
        item.className = `toc-item ${i === STATE.currentSpineIndex ? 'active' : ''}`;
        item.textContent = `Parte ${i + 1}`;
        item.onclick = () => {
          closeDrawers();
          loadChapter(i);
        };
        container.appendChild(item);
      }
      return;
    }

    toc.forEach(entry => {
      const item = document.createElement('div');
      item.className = `toc-item ${entry.spine_index === STATE.currentSpineIndex ? 'active' : ''}`;
      item.innerHTML = `
        <span>${entry.title}</span>
        <span style="font-size: 11px; color: var(--text-muted);">Parte ${entry.spine_index + 1}</span>
      `;
      item.onclick = () => {
        closeDrawers();
        loadChapter(entry.spine_index);
      };
      container.appendChild(item);
    });
  } catch (e) {
    container.innerHTML = 'Errore caricamento indice.';
  }
}

// ==========================================================================
// Vocab & Saved Words Manager
// ==========================================================================

async function loadVocabList() {
  const container = document.getElementById('vocab-items-container');
  container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">Caricamento vocaboli...</div>';

  try {
    const res = await fetch('/api/vocab');
    const words = await res.json();

    const search = document.getElementById('vocab-search').value.toLowerCase().trim();
    const filterStatus = document.getElementById('vocab-filter-status').value;

    const filtered = words.filter(w => {
      if (filterStatus !== 'all' && w.status !== filterStatus) return false;
      if (search && !w.word.toLowerCase().includes(search) && !w.reading.toLowerCase().includes(search) && !w.definition.toLowerCase().includes(search)) return false;
      return true;
    });

    if (filtered.length === 0) {
      container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">Nessun vocabolo corrispondente.</div>';
      return;
    }

    container.innerHTML = '';
    filtered.forEach(w => {
      const card = document.createElement('div');
      card.className = 'card-item';
      card.innerHTML = `
        <div class="card-header">
          <span class="card-word">${w.word}</span>
          <span class="card-reading">[${w.reading || ''}]</span>
        </div>
        <div class="card-def">${w.definition || 'Nessuna definizione salvata'}</div>
        ${w.sentence ? `<div class="card-sentence">"${w.sentence}"</div>` : ''}
        <div class="card-actions">
          <button class="btn btn-icon dp-audio-btn" style="width: 28px; height: 28px;" onclick="playPronunciation('${w.word}')">🔊</button>
          <select class="btn" style="font-size: 11px; padding: 2px 6px;" onchange="updateVocabStatus(${w.id}, this.value)">
            <option value="learning" ${w.status === 'learning' ? 'selected' : ''}>In studio</option>
            <option value="known" ${w.status === 'known' ? 'selected' : ''}>Conosciuto</option>
          </select>
          <button class="btn" style="font-size: 11px; padding: 2px 6px;" onclick="deleteVocabWord(${w.id})">Elimina</button>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = 'Errore caricamento vocabolario.';
  }
}

async function updateVocabStatus(id, status) {
  await fetch(`/api/vocab/${id}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status })
  });
  await loadSeenTerms();
}

async function deleteVocabWord(id) {
  await fetch(`/api/vocab/${id}`, { method: 'DELETE' });
  loadVocabList();
}

// ==========================================================================
// Reading Stats & Timer
// ==========================================================================

function setupReadingTimer() {
  // Activity tracking
  const resetIdle = () => {
    STATE.isWindowActive = true;
    clearTimeout(STATE.idleTimeout);
    STATE.idleTimeout = setTimeout(() => {
      STATE.isWindowActive = false;
    }, 60000); // 1 min idle
  };

  window.addEventListener('mousemove', resetIdle);
  window.addEventListener('keydown', resetIdle);
  window.addEventListener('scroll', resetIdle, true);
  document.addEventListener('visibilitychange', () => {
    STATE.isWindowActive = !document.hidden;
  });

  // Second ticker
  setInterval(() => {
    if (STATE.currentBook && STATE.isWindowActive) {
      STATE.sessionSeconds += 1;
      updateStatsToolbarDisplay();
    }
  }, 1000);

  // Periodic autosave progress (every 15s)
  setInterval(() => {
    if (STATE.currentBook && STATE.isWindowActive) {
      saveCurrentProgress();
    }
  }, 15000);
}

function updateStatsToolbarDisplay() {
  const m = Math.floor(STATE.sessionSeconds / 60);
  const timeEl = document.getElementById('reading-active-timer');
  const charsEl = document.getElementById('reading-chars-stat');
  const speedEl = document.getElementById('reading-speed-stat');

  if (timeEl) timeEl.textContent = `⏱️ ${m}m`;
  if (charsEl) charsEl.textContent = `📝 ${STATE.sessionChars} car`;

  if (speedEl && m > 0) {
    const speed = Math.round(STATE.sessionChars / m);
    speedEl.textContent = `⚡ ${speed} c/m`;
  }
}

function saveCurrentProgress() {
  if (!STATE.currentBook) return;

  const stage = document.getElementById('reader-stage');
  let ratio = 0;
  if (STATE.settings.writingMode === 'vertical') {
    const maxScroll = stage.scrollWidth - stage.clientWidth;
    ratio = maxScroll > 0 ? (stage.scrollLeft / maxScroll) : 0;
  } else {
    const maxScroll = stage.scrollHeight - stage.clientHeight;
    ratio = maxScroll > 0 ? (stage.scrollTop / maxScroll) : 0;
  }

  const payload = {
    book_id: STATE.currentBook.id,
    spine_index: STATE.currentSpineIndex,
    scroll_ratio: Math.max(0, Math.min(1, ratio)),
    chapter_title: STATE.currentChapter ? STATE.currentChapter.chapter_title : '',
    seconds: 15,
    chars: 0
  };

  fetch('/api/progress', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).catch(() => {});
}

async function loadStatsDrawer() {
  const container = document.getElementById('stats-body');
  container.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">Caricamento statistiche...</div>';

  try {
    const res = await fetch('/api/stats');
    const stats = await res.json();

    const totalHours = Math.round((stats.total_seconds / 3600) * 10) / 10;
    const todayMins = Math.round(stats.today_seconds / 60);

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
        <div class="card-item" style="text-align: center;">
          <div style="font-size: 24px; font-weight: 700; color: var(--accent);">${totalHours}h</div>
          <div style="font-size: 12px; color: var(--text-muted);">Tempo Totale</div>
        </div>
        <div class="card-item" style="text-align: center;">
          <div style="font-size: 24px; font-weight: 700; color: var(--success);">${stats.total_characters.toLocaleString()}</div>
          <div style="font-size: 12px; color: var(--text-muted);">Caratteri Letti</div>
        </div>
        <div class="card-item" style="text-align: center;">
          <div style="font-size: 24px; font-weight: 700;">${todayMins}m</div>
          <div style="font-size: 12px; color: var(--text-muted);">Tempo Oggi</div>
        </div>
        <div class="card-item" style="text-align: center;">
          <div style="font-size: 24px; font-weight: 700;">${stats.total_mined_words}</div>
          <div style="font-size: 12px; color: var(--text-muted);">Vocaboli Salvati</div>
        </div>
      </div>

      <div class="setting-label">Termini Tracciati</div>
      <div class="card-item" style="margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
          <span>Conosciuti: <strong>${stats.known_words}</strong></span>
          <span>In Studio: <strong>${stats.learning_words}</strong></span>
        </div>
      </div>

      <div class="setting-label">Attività Ultimi Giorni</div>
      <div class="bm-list">
        ${stats.history.map(h => `
          <div class="toc-item">
            <span>${h.day}</span>
            <span><strong>${h.characters_read.toLocaleString()}</strong> car • ${Math.round(h.seconds_read / 60)} min</span>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    container.innerHTML = 'Errore caricamento statistiche.';
  }
}

// ==========================================================================
// Image Lightbox & Zoom
// ==========================================================================

let lbScale = 1;

function setupIllustrationLightbox(root) {
  root.querySelectorAll('.reader-ill-img, img').forEach(img => {
    img.addEventListener('click', (e) => {
      e.stopPropagation();
      openLightbox(img.src);
    });
  });
}

function openLightbox(src) {
  const modal = document.getElementById('lightbox-modal');
  const img = document.getElementById('lb-image');
  img.src = src;
  lbScale = 1;
  updateLightboxZoom();
  modal.style.display = 'flex';
}

function closeLightbox() {
  document.getElementById('lightbox-modal').style.display = 'none';
}

function updateLightboxZoom() {
  const img = document.getElementById('lb-image');
  const lbl = document.getElementById('lb-zoom-level');
  img.style.transform = `scale(${lbScale})`;
  lbl.textContent = `${Math.round(lbScale * 100)}%`;
}

// ==========================================================================
// UI Event Handlers & Drawers
// ==========================================================================

function openDrawer(drawerId) {
  document.getElementById('drawer-overlay').classList.add('active');
  document.querySelectorAll('.drawer').forEach(d => d.classList.remove('active'));
  document.getElementById(drawerId).classList.add('active');
}

function closeDrawers() {
  document.getElementById('drawer-overlay').classList.remove('active');
  document.querySelectorAll('.drawer').forEach(d => d.classList.remove('active'));
}

function setupEventListeners() {
  // Navigation
  document.getElementById('btn-back-to-lib')?.addEventListener('click', closeReader);
  document.getElementById('lib-search')?.addEventListener('input', (e) => renderLibrary(e.target.value));

  // Chapter buttons
  document.getElementById('btn-prev-chapter')?.addEventListener('click', () => {
    if (STATE.currentChapter && STATE.currentChapter.prev_index !== null) {
      loadChapter(STATE.currentChapter.prev_index);
    }
  });

  document.getElementById('btn-next-chapter')?.addEventListener('click', () => {
    if (STATE.currentChapter && STATE.currentChapter.next_index !== null) {
      loadChapter(STATE.currentChapter.next_index);
    }
  });

  // Slider navigation
  const stage = document.getElementById('reader-stage');
  stage.addEventListener('scroll', () => {
    let percent = 0;
    if (STATE.settings.writingMode === 'vertical') {
      const max = stage.scrollWidth - stage.clientWidth;
      percent = max > 0 ? Math.round(((stage.scrollWidth - stage.clientWidth - stage.scrollLeft) / max) * 100) : 0;
    } else {
      const max = stage.scrollHeight - stage.clientHeight;
      percent = max > 0 ? Math.round((stage.scrollTop / max) * 100) : 0;
    }
    document.getElementById('bb-chapter-slider').value = percent;
    document.getElementById('bb-scroll-percent').textContent = `${percent}%`;
  });

  document.getElementById('bb-chapter-slider')?.addEventListener('input', (e) => {
    const val = parseInt(e.target.value) / 100;
    if (STATE.settings.writingMode === 'vertical') {
      const max = stage.scrollWidth - stage.clientWidth;
      stage.scrollLeft = (1 - val) * max;
    } else {
      const max = stage.scrollHeight - stage.clientHeight;
      stage.scrollTop = val * max;
    }
  });

  // Keyboard Shortcuts (Arrow Left/Right, B for bookmark, F for fullscreen, ESC)
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === 'Escape') {
      hideDictionaryPopup();
      closeDrawers();
      closeLightbox();
    } else if (e.key === 'ArrowRight') {
      if (STATE.settings.writingMode === 'vertical') {
        document.getElementById('btn-prev-chapter')?.click();
      } else {
        document.getElementById('btn-next-chapter')?.click();
      }
    } else if (e.key === 'ArrowLeft') {
      if (STATE.settings.writingMode === 'vertical') {
        document.getElementById('btn-next-chapter')?.click();
      } else {
        document.getElementById('btn-prev-chapter')?.click();
      }
    } else if (e.key === 'b' || e.key === 'B') {
      addCurrentBookmark();
    } else if (e.key === 'f' || e.key === 'F') {
      toggleFullscreen();
    }
  });

  // Drawers triggers
  document.getElementById('btn-open-toc')?.addEventListener('click', () => { loadTOC(); openDrawer('toc-drawer'); });
  document.getElementById('btn-open-bookmarks')?.addEventListener('click', () => { loadBookmarksList(); openDrawer('bookmarks-drawer'); });
  document.getElementById('btn-open-vocab')?.addEventListener('click', () => { loadVocabList(); openDrawer('vocab-drawer'); });
  document.getElementById('btn-open-vocab-lib')?.addEventListener('click', () => { loadVocabList(); openDrawer('vocab-drawer'); });
  document.getElementById('btn-open-stats-lib')?.addEventListener('click', () => { loadStatsDrawer(); openDrawer('stats-drawer'); });
  document.getElementById('btn-open-settings')?.addEventListener('click', () => openDrawer('settings-drawer'));
  document.getElementById('btn-open-settings-lib')?.addEventListener('click', () => openDrawer('settings-drawer'));
  document.getElementById('btn-add-bookmark')?.addEventListener('click', addCurrentBookmark);

  // Close drawers
  document.getElementById('drawer-overlay')?.addEventListener('click', closeDrawers);
  document.querySelectorAll('.close-drawer').forEach(btn => btn.addEventListener('click', closeDrawers));

  // Dictionary Popup Actions
  document.getElementById('dp-audio-btn')?.addEventListener('click', () => playPronunciation(STATE.activePopupWord));
  document.getElementById('dp-mine-btn')?.addEventListener('click', mineWord);
  document.getElementById('dp-known-btn')?.addEventListener('click', markWordKnown);
  document.getElementById('dp-translate-sent-btn')?.addEventListener('click', translateActiveSentence);
  document.getElementById('dp-jisho-btn')?.addEventListener('click', () => {
    if (STATE.activePopupWord) {
      window.open(`https://jisho.org/search/${encodeURIComponent(STATE.activePopupWord)}`, '_blank');
    }
  });

  // Close popup on outside click
  document.addEventListener('click', (e) => {
    const popup = document.getElementById('dict-popup');
    if (popup && !popup.contains(e.target) && !e.target.classList.contains('ja-word')) {
      hideDictionaryPopup();
    }
  });

  // Writing Mode Toggle
  document.getElementById('btn-toggle-writing-mode')?.addEventListener('click', () => {
    STATE.settings.writingMode = (STATE.settings.writingMode === 'vertical') ? 'horizontal' : 'vertical';
    applySettings();
    saveSettings();
  });
  document.getElementById('set-mode-vertical')?.addEventListener('click', () => {
    STATE.settings.writingMode = 'vertical';
    applySettings();
    saveSettings();
  });
  document.getElementById('set-mode-horizontal')?.addEventListener('click', () => {
    STATE.settings.writingMode = 'horizontal';
    applySettings();
    saveSettings();
  });

  // Furigana Mode Toggle
  document.getElementById('btn-furigana-mode')?.addEventListener('click', () => {
    const modes = ['original', 'auto', 'hover', 'hidden'];
    const next = modes[(modes.indexOf(STATE.settings.furiganaMode) + 1) % modes.length];
    STATE.settings.furiganaMode = next;
    applySettings();
    saveSettings();
    if (next === 'auto' && STATE.currentBook) {
      loadChapter(STATE.currentSpineIndex); // reload with server-injected furigana
    }
  });
  document.getElementById('select-furigana-mode')?.addEventListener('change', (e) => {
    STATE.settings.furiganaMode = e.target.value;
    applySettings();
    saveSettings();
    if (e.target.value === 'auto' && STATE.currentBook) {
      loadChapter(STATE.currentSpineIndex);
    }
  });

  // Themes
  document.querySelectorAll('.theme-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      STATE.settings.theme = btn.dataset.setTheme;
      applySettings();
      saveSettings();
    });
  });

  // Settings Sliders
  document.getElementById('slider-font-size')?.addEventListener('input', (e) => {
    STATE.settings.fontSize = parseInt(e.target.value);
    applySettings();
    saveSettings();
  });
  document.getElementById('slider-line-height')?.addEventListener('input', (e) => {
    STATE.settings.lineHeight = parseFloat(e.target.value) / 10;
    applySettings();
    saveSettings();
  });
  document.getElementById('slider-letter-spacing')?.addEventListener('input', (e) => {
    STATE.settings.letterSpacing = parseFloat(e.target.value) / 100;
    applySettings();
    saveSettings();
  });
  document.getElementById('select-font-family')?.addEventListener('change', (e) => {
    STATE.settings.fontFamily = e.target.value;
    applySettings();
    saveSettings();
  });
  document.getElementById('check-highlight-seen')?.addEventListener('change', (e) => {
    STATE.settings.highlightSeen = e.target.checked;
    applySettings();
    saveSettings();
    if (STATE.currentChapter) {
      processJapaneseWords(document.getElementById('reader-text'));
    }
  });

  // Fullscreen
  document.getElementById('btn-toggle-fullscreen')?.addEventListener('click', toggleFullscreen);

  // Lightbox Zoom
  document.getElementById('lb-close')?.addEventListener('click', closeLightbox);
  document.getElementById('lb-zoom-in')?.addEventListener('click', () => { lbScale = Math.min(3.5, lbScale + 0.25); updateLightboxZoom(); });
  document.getElementById('lb-zoom-out')?.addEventListener('click', () => { lbScale = Math.max(0.4, lbScale - 0.25); updateLightboxZoom(); });
  document.getElementById('lb-zoom-reset')?.addEventListener('click', () => { lbScale = 1; updateLightboxZoom(); });

  // Vocab search and filters
  document.getElementById('vocab-search')?.addEventListener('input', loadVocabList);
  document.getElementById('vocab-filter-status')?.addEventListener('change', loadVocabList);

  // Anki and JSON Export
  document.getElementById('btn-export-anki')?.addEventListener('click', () => {
    window.location.href = '/api/export/anki';
  });
  document.getElementById('btn-export-json')?.addEventListener('click', () => {
    window.location.href = '/api/export/json';
  });

  // iPad Modal Event Handlers
  setupIpadModal();

  // Import EPUB Modal & Verification
  setupImportModal();

  // iPad / Touchscreen Swipe Gestures
  setupTouchGestures();

  setupTextSelection();
}

function setupIpadModal() {
  const modal = document.getElementById('ipad-modal');
  const btnOpen = document.getElementById('btn-open-ipad');
  const btnClose = document.getElementById('btn-close-ipad-modal');
  const inputUrl = document.getElementById('ipad-url-input');
  const btnCopy = document.getElementById('btn-copy-ipad-url');
  const qrImg = document.getElementById('ipad-qr-img');

  btnOpen?.addEventListener('click', async () => {
    if (modal) modal.style.display = 'flex';
    try {
      const res = await fetch('/api/server_info');
      const data = await res.json();
      if (inputUrl) inputUrl.value = data.url;
      if (qrImg) qrImg.src = `/api/qr?t=${Date.now()}`;
    } catch (e) {
      if (inputUrl) inputUrl.value = window.location.href;
    }
  });

  btnClose?.addEventListener('click', () => {
    if (modal) modal.style.display = 'none';
  });

  modal?.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
  });

  btnCopy?.addEventListener('click', async () => {
    if (!inputUrl) return;
    try {
      await navigator.clipboard.writeText(inputUrl.value);
      btnCopy.textContent = '✓ Copiato!';
      setTimeout(() => { btnCopy.textContent = 'Copia'; }, 1800);
    } catch (e) {
      inputUrl.select();
      document.execCommand('copy');
      btnCopy.textContent = '✓ Copiato!';
      setTimeout(() => { btnCopy.textContent = 'Copia'; }, 1800);
    }
  });
}

function setupImportModal() {
  const modal = document.getElementById('import-modal');
  const btnOpen = document.getElementById('btn-open-import');
  const btnClose = document.getElementById('btn-close-import-modal');
  const dropZone = document.getElementById('epub-drop-zone');
  const fileInput = document.getElementById('epub-file-input');
  const btnBrowse = document.getElementById('btn-browse-file');
  const statusEl = document.getElementById('import-status');

  btnOpen?.addEventListener('click', () => {
    if (modal) {
      modal.style.display = 'flex';
      if (statusEl) {
        statusEl.style.display = 'none';
        statusEl.innerHTML = '';
      }
    }
  });

  btnClose?.addEventListener('click', () => {
    if (modal) modal.style.display = 'none';
  });

  modal?.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
  });

  btnBrowse?.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput?.click();
  });

  dropZone?.addEventListener('click', () => {
    fileInput?.click();
  });

  fileInput?.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleEpubUpload(e.target.files[0]);
    }
  });

  // Drag and drop events
  ['dragenter', 'dragover'].forEach(name => {
    dropZone?.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropZone?.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragover');
    });
  });

  dropZone?.addEventListener('drop', (e) => {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleEpubUpload(e.dataTransfer.files[0]);
    }
  });

  async function handleEpubUpload(file) {
    if (!file.name.toLowerCase().endsWith('.epub')) {
      showStatus('❌ Il file selezionato non ha estensione .epub!', 'error');
      return;
    }

    showStatus('⏳ Caricamento e analisi linguistica giapponese del testo in corso...', 'info');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/books/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();

      if (res.ok && data.success) {
        if (data.warning) {
          showStatus(`⚠️ <strong>Volume importato con avviso:</strong><br><span style="font-size: 12px;">${data.warning}</span>`, 'warning');
        } else {
          showStatus(`✅ <strong>Successo!</strong> ${data.message || 'Volume verificato e aggiunto.'}`, 'success');
        }
        await loadBooks(); // Refresh library view
        setTimeout(() => {
          if (modal) modal.style.display = 'none';
        }, data.warning ? 4500 : 2200);
      } else {
        showStatus(`❌ <strong>Errore:</strong> ${data.error || 'Errore durante la verifica.'}`, 'error');
      }
    } catch (err) {
      showStatus(`❌ Errore di rete o server: ${err.message}`, 'error');
    }
  }

  function showStatus(html, type) {
    if (!statusEl) return;
    statusEl.style.display = 'block';
    statusEl.className = `import-alert-${type}`;
    statusEl.innerHTML = html;
  }
}

function setupTouchGestures() {
  const stage = document.getElementById('reader-stage');
  if (!stage) return;

  let touchStartX = 0;
  let touchStartY = 0;
  let touchStartTime = 0;

  stage.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return;
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    touchStartTime = Date.now();
  }, { passive: true });

  stage.addEventListener('touchend', (e) => {
    if (!touchStartX || !touchStartTime) return;
    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const dx = touchEndX - touchStartX;
    const dy = touchEndY - touchStartY;
    const dt = Date.now() - touchStartTime;

    // Check if it's a deliberate fast horizontal swipe
    if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 1.5 && dt < 600) {
      // In vertical reading mode (Japanese books scroll from right to left)
      if (STATE.settings.writingMode === 'vertical') {
        if (dx < 0) {
          // Swipe left -> advance to next chapter if at end of scroll
          if (stage.scrollLeft <= 10) {
            document.getElementById('btn-next-chapter')?.click();
          }
        } else {
          // Swipe right -> previous chapter if at beginning
          if (stage.scrollLeft >= stage.scrollWidth - stage.clientWidth - 10) {
            document.getElementById('btn-prev-chapter')?.click();
          }
        }
      } else {
        // Horizontal reading mode
        if (dx < 0) {
          document.getElementById('btn-next-chapter')?.click();
        } else {
          document.getElementById('btn-prev-chapter')?.click();
        }
      }
    }

    touchStartX = 0;
    touchStartY = 0;
    touchStartTime = 0;
  }, { passive: true });
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}
