// OCR Processor - Clean Script

// DOM Elements
const $ = (id) => document.getElementById(id);

// ── contenteditable helpers ──────────────────────────────────
function getEditorText() {
    const el = $('extractedText');
    if (!el) return '';
    return el.innerText || '';
}
function setEditorText(text) {
    const el = $('extractedText');
    if (!el) return;
    // Сохраняем plain text, переносы строк → <br>
    el.innerText = text;
    el.classList.toggle('empty', !text.trim());
}
function isEditorReadOnly(val) {
    const el = $('extractedText');
    if (!el) return;
    el.contentEditable = val ? 'false' : 'true';
}



// Controls
const imageInput = $('imageInput');
const pdfInput = $('pdfInput');
const fileName = $('fileName');
const ocrEngine = $('ocrEngine');
const languageSelect = $('language');
const processBtn = $('processBtn');
const processCurrentBtn = $('processCurrentBtn');
const clearBtn = $('clearBtn');

// Navigation
const pageNavigation = $('pageNavigation');
const prevBtn = $('prevBtn');
const currentPageEl = $('currentPage');
const totalPagesEl = $('totalPages');
const nextBtn = $('nextBtn');

// Image Viewer
const imageFileName = $('imageFileName');
const pageStatus = $('pageStatus');
const imageContainer = $('imageContainer');
const imagePlaceholder = $('imagePlaceholder');
const imagePreview = $('imagePreview');
const zoomControls = $('zoomControls');
const zoomLevelDisplay = $('zoomLevel');

// Text Area
const extractedText = $('extractedText');
const fullTextStats = $('fullTextStats');

// Summary
const summaryText = $('summaryText');
const summarizeBtn = $('summarizeBtn');
const summaryStats = $('summaryStats');

// UI
const notification = $('notification');
const progressModal = $('progressModal');
const progressFill = $('progressFill');
const progressText = $('progressText');

// State
let pages = [];
let currentPageIndex = 0;
let scale = 1;
let translateX = 0;
let translateY = 0;
let isPanning = false;
let startX = 0;
let startY = 0;

console.log('OCR Processor initialized');
updateFullTextStats();

// Event Listeners
if (imageInput) {
    imageInput.addEventListener('change', async function(e) {
        const files = Array.from(e.target.files);
        if (files.length === 0) return;

        pages = [];
        currentPageIndex = 0;

        if (fileName) fileName.textContent = files.length === 1 ? files[0].name : `${files.length} файлов выбрано`;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const preview = await readFileAsDataURL(file);
            pages.push({ file, preview, text: '', summary: '', status: 'pending' });
        }

        showPage(0);
        if (pageNavigation) pageNavigation.style.display = 'flex';
        if (zoomControls) zoomControls.style.display = 'flex';
        updatePageNavigation();
        showNotification(`Загружено ${pages.length} изображений`, 'success');
    });
}

if (pdfInput) {
    pdfInput.addEventListener('change', async function(e) {
        const file = e.target.files[0];
        if (!file) return;
        if (fileName) fileName.textContent = file.name;
        await processPdf(file);
        pdfInput.value = '';
    });
}

if (extractedText) {
    extractedText.addEventListener('input', function() {
        if (pages.length > 0 && currentPageIndex < pages.length) {
            pages[currentPageIndex].text = getEditorText();
            updateFullTextStats();
        }
    });
}

if (imageContainer) {
    imageContainer.addEventListener('wheel', function(e) {
        e.preventDefault();
        if (imagePreview.style.display === 'none') return;
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        const newScale = Math.min(Math.max(scale * delta, 0.1), 5);
        const rect = imageContainer.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        const scaleRatio = newScale / scale;
        translateX = mouseX - (mouseX - translateX) * scaleRatio;
        translateY = mouseY - (mouseY - translateY) * scaleRatio;
        scale = newScale;
        updateImageTransform();
        updateZoomLevel();
    });

    imageContainer.addEventListener('mousedown', function(e) {
        if (imagePreview.style.display === 'none') return;
        if (cropMode) return;   // не начинаем pan в режиме crop
        if (e.button !== 0) return;
        isPanning = true;
        startX = e.clientX - translateX;
        startY = e.clientY - translateY;
        imageContainer.classList.add('panning');
        e.preventDefault();
    });
}

document.addEventListener('mousemove', function(e) {
    // Pan
    if (isPanning && !cropMode && imagePreview.style.display !== 'none') {
        translateX = e.clientX - startX;
        translateY = e.clientY - startY;
        updateImageTransform();
    }
    // Crop draw
    if (cropMode && cropDrawing) {
        const r  = cropCanvas.getBoundingClientRect();
        const mx = e.clientX - r.left;
        const my = e.clientY - r.top;
        cropRect = normalizeRect(cropStart.x, cropStart.y, mx, my);
        cropRedraw(cropRect);
    }
});

document.addEventListener('mouseup', function(e) {
    // Pan
    if (isPanning) {
        isPanning = false;
        if (imageContainer) imageContainer.classList.remove('panning');
    }
    // Crop
    if (cropMode && cropDrawing) {
        cropDrawing = false;
        if (!cropRect || cropRect.w < 8 || cropRect.h < 8) {
            cropRect = null;
            cropRedraw(null);
            showNotification('Область слишком маленькая, попробуйте ещё раз', 'error');
            return;
        }
        // Область нарисована — предлагаем запустить OCR через обычные кнопки
        cropHint.textContent = '✓ Область выделена · нажмите «Обработать текущую» · Esc — отмена';
    }
});

// Core Functions

/** Возвращает File/Blob для страницы. Для PDF-страниц конвертирует base64-превью в Blob. */
async function getPageBlob(page) {
    if (page.file) return page.file;
    const res = await fetch(page.preview);
    const blob = await res.blob();
    return new File([blob], 'page.png', { type: 'image/png' });
}

function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = (e) => reject(e);
        reader.readAsDataURL(file);
    });
}

function showPage(index) {
    if (index < 0 || index >= pages.length) return;
    currentPageIndex = index;
    const page = pages[index];

    if (imagePreview) { imagePreview.src = page.preview; imagePreview.style.display = 'block'; }
    if (imagePlaceholder) imagePlaceholder.style.display = 'none';
    if (imageFileName) imageFileName.textContent = page.file ? `(${page.file.name})` : '';

    if (extractedText) { setEditorText(page.text || ''); isEditorReadOnly(page.status === 'pending'); }
    if (summaryText) summaryText.value = page.summary || '';
    if (summaryStats) { summaryStats.style.display = page.summary ? 'block' : 'none'; if (page.summary) updateSummaryStats(); }

    updatePageStatus();
    updatePageNavigation();
    updateFullTextStats();
    resetZoom();
}

function updatePageNavigation() {
    if (!pageNavigation) return;
    if (pages.length === 0) { pageNavigation.style.display = 'none'; return; }
    if (currentPageEl) currentPageEl.textContent = currentPageIndex + 1;
    if (totalPagesEl) totalPagesEl.textContent = pages.length;
    if (prevBtn) prevBtn.disabled = currentPageIndex === 0;
    if (nextBtn) nextBtn.disabled = currentPageIndex === pages.length - 1;
    pageNavigation.style.display = 'flex';
}

function updatePageStatus() {
    if (!pageStatus) return;
    const page = pages[currentPageIndex];
    const icons = { 'pending': '⏳', 'processing': '🔄', 'done': '✅', 'error': '❌' };
    const labels = { 'pending': 'Не обработано', 'processing': 'Обработка...', 'done': 'Обработано', 'error': 'Ошибка' };
    pageStatus.textContent = `${icons[page.status]} ${labels[page.status]}`;
}

function previousPage() { if (currentPageIndex > 0) showPage(currentPageIndex - 1); }
function nextPage() { if (currentPageIndex < pages.length - 1) showPage(currentPageIndex + 1); }

// OCR Processing
async function processCurrentImage() {
    if (pages.length === 0) return showNotification('Загрузите изображения!', 'error');
    // Если есть активное выделение — обрабатываем только его
    if (cropRect) return processCropRegion({});
    try {
        await processPage(pages[currentPageIndex], currentPageIndex);
        showNotification(`Страница ${currentPageIndex + 1} обработана`, 'success');
    } catch (error) { showNotification('Ошибка: ' + error.message, 'error'); }
}

async function processAllImages() {
    if (pages.length === 0) return showNotification('Загрузите изображения!', 'error');
    if (progressModal) progressModal.style.display = 'flex';
    let successCount = 0;

    for (let i = 0; i < pages.length; i++) {
        const page = pages[i];
        page.status = 'processing';
        if (progressText) progressText.textContent = `Обработка страницы ${i + 1} из ${pages.length}`;
        if (progressFill) progressFill.style.width = `${((i) / pages.length) * 100}%`;
        if (currentPageIndex === i) showPage(i);
        try {
            await processPage(page, i, ocrEngine.value, languageSelect.value, false);
            successCount++;
        } catch (error) { console.error(`Ошибка страницы ${i + 1}:`, error); }
    }
    if (progressFill) progressFill.style.width = '100%';
    setTimeout(() => {
        if (progressModal) progressModal.style.display = 'none';
        showNotification(`Обработано ${successCount} из ${pages.length}`, 'success');
    }, 500);
}

async function processPage(page, index, engine = null, lang = null, showNotif = true) {
    const formData = new FormData();
    formData.append('file', await getPageBlob(page));
    formData.append('ocr_engine', engine || (ocrEngine ? ocrEngine.value : 'tesseract'));
    formData.append('language', lang || (languageSelect ? languageSelect.value : 'rus'));
    const modeEl = document.getElementById('textMode');
    formData.append('text_mode', modeEl ? modeEl.value : 'printed');
    const preprocEl = document.getElementById('preprocessing');
    formData.append('preprocessing', preprocEl ? preprocEl.value : 'none');

    const showProgress = (currentPageIndex === index);
    if (showProgress) showOcrProgress(5, 'Подготовка...');

    return new Promise((resolve, reject) => {
        fetch('/process-stream', { method: 'POST', body: formData })
            .then(response => {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                function read() {
                    reader.read().then(({ done, value }) => {
                        if (done) { hideOcrProgress(); resolve(true); return; }
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop();

                        for (const line of lines) {
                            if (!line.startsWith('data: ')) continue;
                            try {
                                const evt = JSON.parse(line.slice(6));
                                if (showProgress) showOcrProgress(evt.progress, evt.message);

                                if (evt.stage === 'done') {
                                    page.text = evt.text;
                                    page.status = 'done';
                                    if (currentPageIndex === index) {
                                        setEditorText(page.text);
                                        isEditorReadOnly(false);
                                        updatePageStatus();
                                        updateFullTextStats();
                                    }
                                    if (showNotif) showNotification(`Страница ${index + 1} обработана`, 'success');
                                    hideOcrProgress();
                                    resolve(true);
                                } else if (evt.stage === 'error') {
                                    page.status = 'error';
                                    if (currentPageIndex === index) updatePageStatus();
                                    if (showNotif) showNotification('Ошибка: ' + evt.message, 'error');
                                    hideOcrProgress();
                                    reject(new Error(evt.message));
                                }
                            } catch (e) { /* ignore parse errors */ }
                        }
                        read();
                    }).catch(err => { hideOcrProgress(); reject(err); });
                }
                read();
            })
            .catch(err => { hideOcrProgress(); reject(err); });
    });
}


async function processPdf(file) {
    pages = [];
    currentPageIndex = 0;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ocr_engine', ocrEngine ? ocrEngine.value : 'tesseract');
    formData.append('language', languageSelect ? languageSelect.value : 'rus');
    const modeEl = document.getElementById('textMode');
    formData.append('text_mode', modeEl ? modeEl.value : 'printed');
    const preprocEl = document.getElementById('preprocessing');
    formData.append('preprocessing', preprocEl ? preprocEl.value : 'none');

    showOcrProgress(3, 'Чтение PDF...');

    return new Promise((resolve, reject) => {
        fetch('/process-pdf-stream', { method: 'POST', body: formData })
            .then(response => {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                function read() {
                    reader.read().then(({ done, value }) => {
                        if (done) { hideOcrProgress(); resolve(); return; }
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop();

                        for (const line of lines) {
                            if (!line.startsWith('data: ')) continue;
                            try {
                                const evt = JSON.parse(line.slice(6));
                                showOcrProgress(evt.progress, evt.message);

                                if (evt.stage === 'pdf_info') {
                                    // Инициализируем массив страниц
                                    pages = Array.from({ length: evt.total_pages }, (_, i) => ({
                                        file: null,
                                        preview: '',
                                        text: '',
                                        summary: '',
                                        status: 'processing',
                                        isPdfPage: true,
                                    }));
                                    if (pageNavigation) pageNavigation.style.display = 'flex';
                                    if (zoomControls) zoomControls.style.display = 'flex';
                                    updatePageNavigation();
                                    if (imagePlaceholder) imagePlaceholder.style.display = 'none';

                                } else if (evt.stage === 'page_done') {
                                    const idx = evt.page;
                                    if (pages[idx]) {
                                        pages[idx].text = evt.text;
                                        pages[idx].status = 'done';
                                        pages[idx].preview = 'data:image/png;base64,' + evt.image_base64;
                                        if (idx === 0 || idx === currentPageIndex) {
                                            showPage(idx);
                                        }
                                        if (idx === 0) {
                                            currentPageIndex = 0;
                                            showPage(0);
                                        }
                                    }
                                    updatePageNavigation();

                                } else if (evt.stage === 'page_error') {
                                    const idx = evt.page;
                                    if (pages[idx]) pages[idx].status = 'error';

                                } else if (evt.stage === 'done') {
                                    hideOcrProgress();
                                    showNotification(`PDF обработан: ${evt.total_pages} стр.`, 'success');
                                    resolve();

                                } else if (evt.stage === 'error') {
                                    hideOcrProgress();
                                    showNotification('Ошибка: ' + evt.message, 'error');
                                    reject(new Error(evt.message));
                                }
                            } catch (e) { /* ignore parse errors */ }
                        }
                        read();
                    }).catch(err => { hideOcrProgress(); reject(err); });
                }
                read();
            })
            .catch(err => { hideOcrProgress(); showNotification('Ошибка: ' + err.message, 'error'); reject(err); });
    });
}

// Summarization
async function summarizeText() {
    const page = pages[currentPageIndex];
    const currentText = extractedText ? getEditorText().trim() : '';
    if (!currentText) return showNotification('Сначала обработайте страницу', 'error');
    if (currentText.split(' ').length < 10) return showNotification('Текст слишком короткий', 'error');

    if (summarizeBtn) { summarizeBtn.disabled = true; summarizeBtn.textContent = 'Генерация...'; }
    if (summaryText) summaryText.value = 'Генерация...';

    try {
        const response = await fetch('/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: currentText })
        });
        const result = await response.json();
        if (response.ok) {
            if (page) page.summary = result.summary;
            if (summaryText) summaryText.value = result.summary;
            if (summaryStats) { summaryStats.style.display = 'block'; updateSummaryStats(); }
            showNotification('Суммаризация завершена', 'success');
        } else {
            if (summaryText) summaryText.value = '';
            if (page) page.summary = '';
            showNotification('Ошибка: ' + (result.detail || 'Неизвестно'), 'error');
        }
    } catch (error) {
        if (summaryText) summaryText.value = '';
        if (page) page.summary = '';
        showNotification('Ошибка: ' + error.message, 'error');
    } finally {
        if (summarizeBtn) { summarizeBtn.disabled = false; summarizeBtn.textContent = 'Создать'; }
    }
}

// Utilities
function copyFullText() {
    const text = extractedText ? getEditorText() : '';
    if (!text) return showNotification('Нет текста', 'error');
    navigator.clipboard.writeText(text).then(() => showNotification('Скопировано', 'success'));
}

function exportText() {
    const text = extractedText ? getEditorText() : '';
    if (!text.trim()) return showNotification('Нет текста', 'error');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ocr_page_${currentPageIndex + 1}_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    showNotification('Файл сохранен', 'success');
}

function clearAll() {
    if (imageInput) imageInput.value = '';
    if (pdfInput) pdfInput.value = '';
    pages = []; currentPageIndex = 0;
    if (imagePreview) { imagePreview.src = ''; imagePreview.style.display = 'none'; }
    if (imagePlaceholder) imagePlaceholder.style.display = 'flex';
    if (imageFileName) imageFileName.textContent = '';
    if (fileName) fileName.textContent = 'Файлы не выбраны';
    if (extractedText) setEditorText('');
    if (summaryText) summaryText.value = '';
    if (summaryStats) summaryStats.style.display = 'none';
    if (zoomControls) zoomControls.style.display = 'none';
    if (pageNavigation) pageNavigation.style.display = 'none';
    clearCropSelection();
    resetZoom();
    updateFullTextStats();
    showNotification('Очищено', 'success');
}

function updateFullTextStats() {
    if (!fullTextStats) return;
    const text = extractedText ? getEditorText() : '';
    fullTextStats.textContent = `${text.length} символов, ${text.trim() ? text.trim().split(/\s+/).length : 0} слов`;
}

function updateSummaryStats() {
    if (!summaryStats) return;
    const text = summaryText ? summaryText.value : '';
    summaryStats.textContent = `${text.length} символов, ${text.trim() ? text.trim().split(/\s+/).length : 0} слов`;
}

function showNotification(message, type) {
    if (!notification) return;
    notification.textContent = message;
    notification.className = `notification ${type} show`;
    setTimeout(() => notification.classList.remove('show'), 3000);
}

// Zoom
function updateImageTransform() {
    if (imagePreview) imagePreview.style.transform = `translate(calc(-50% + ${translateX}px), calc(-50% + ${translateY}px)) scale(${scale})`;
}
function zoomIn() { scale = Math.min(scale * 1.2, 5); updateImageTransform(); updateZoomLevel(); }
function zoomOut() { scale = Math.max(scale / 1.2, 0.1); updateImageTransform(); updateZoomLevel(); }
function resetZoom() { scale = 1; translateX = 0; translateY = 0; updateImageTransform(); updateZoomLevel(); }
function updateZoomLevel() { if (zoomLevelDisplay) zoomLevelDisplay.textContent = Math.round(scale * 100) + '%'; }

// Init
updateFullTextStats();
// ═══════════════════════════════════════════════════════════
//  CROP / REGION SELECTION
// ═══════════════════════════════════════════════════════════

const cropCanvas  = $('cropCanvas');
const cropHint    = $('cropHint');
const cropModeBtn = $('cropModeBtn');

let cropMode    = false;
let cropDrawing = false;
let cropStart   = { x: 0, y: 0 };
let cropRect    = null;   // { x, y, w, h } в пикселях canvas

// ── Включить / выключить режим ──────────────────────────────
function toggleCropMode() {
    if (pages.length === 0) {
        showNotification('Сначала загрузите изображение', 'error');
        return;
    }
    cropMode = !cropMode;

    if (cropMode) {
        syncCropCanvasSize();          // сразу задаём правильный размер canvas
        cropCanvas.style.display = 'block';
        cropHint.style.display   = 'block';
        cropHint.textContent     = 'Нарисуйте прямоугольник для выделения области';
        cropModeBtn.classList.add('active');
        cropModeBtn.textContent  = '✂ Отменить выделение';
        // НЕ блокируем imageContainer — canvas лежит поверх и перехватывает события сам
        cropRect    = null;
        cropDrawing = false;
        cropRedraw(null);
    } else {
        exitCropMode();
    }
}

function exitCropMode() {
    cropMode    = false;
    cropDrawing = false;
    if (cropModeBtn) {
        cropModeBtn.classList.remove('active');
        cropModeBtn.textContent = '✂ Выделить область';
    }
    // Если выделение есть — оставляем его видимым, только скрываем подсказку
    if (cropRect) {
        cropHint.style.display = 'none';
        // Показываем тонкий статус-баннер под кнопкой
        showCropStatus('Область выделена — нажмите «Обработать текущую»');
    } else {
        cropCanvas.style.display = 'none';
        cropHint.style.display   = 'none';
    }
}

// Полностью сбросить выделение (вызывается из clearAll и кнопки отмены)
function clearCropSelection() {
    cropMode    = false;
    cropDrawing = false;
    cropRect    = null;
    cropCanvas.style.display = 'none';
    cropHint.style.display   = 'none';
    hideCropStatus();
    if (cropModeBtn) {
        cropModeBtn.classList.remove('active');
        cropModeBtn.textContent = '✂ Выделить область';
    }
}

// Статус-баннер под изображением
let cropStatusEl = null;
function showCropStatus(msg) {
    if (!cropStatusEl) {
        cropStatusEl = document.createElement('div');
        cropStatusEl.className = 'crop-status-bar';
        // Вставляем после image-container внутри image-viewer
        const viewer = imageContainer.closest('.image-viewer') || imageContainer.parentNode;
        viewer.insertBefore(cropStatusEl, imageContainer.nextSibling);
    }
    cropStatusEl.innerHTML = `<span>${msg}</span><button onclick="clearCropSelection()" title="Снять выделение">✕</button>`;
    cropStatusEl.style.display = 'flex';
}
function hideCropStatus() {
    if (cropStatusEl) cropStatusEl.style.display = 'none';
}

// ── Синхронизировать размер canvas с контейнером ────────────
function syncCropCanvasSize() {
    if (!cropCanvas) return;
    const rect = imageContainer.getBoundingClientRect();
    // Присвоение width/height сбрасывает содержимое canvas — делаем это только при необходимости
    if (cropCanvas.width !== Math.round(rect.width) || cropCanvas.height !== Math.round(rect.height)) {
        cropCanvas.width  = Math.round(rect.width);
        cropCanvas.height = Math.round(rect.height);
    }
}

// ── Нарисовать выделение ─────────────────────────────────────
function cropRedraw(rect) {
    if (!cropCanvas) return;
    const ctx = cropCanvas.getContext('2d');
    ctx.clearRect(0, 0, cropCanvas.width, cropCanvas.height);
    if (!rect || rect.w < 1 || rect.h < 1) return;

    const { x, y, w, h } = rect;

    // Полупрозрачное затемнение снаружи выделения
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.fillRect(0, 0, cropCanvas.width, cropCanvas.height);
    // «Вырезаем» прозрачное окно
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillRect(x, y, w, h);
    ctx.restore();

    // Пунктирная рамка
    ctx.save();
    ctx.strokeStyle = '#F59E0B';
    ctx.lineWidth   = 2;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);
    ctx.restore();

    // Угловые маркеры
    const cs = 12;
    ctx.save();
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth   = 2.5;
    ctx.setLineDash([]);
    [[x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1]].forEach(([cx, cy, sx, sy]) => {
        ctx.beginPath();
        ctx.moveTo(cx + sx * cs, cy);
        ctx.lineTo(cx, cy);
        ctx.lineTo(cx, cy + sy * cs);
        ctx.stroke();
    });
    ctx.restore();
}

// ── Mouse events — вешаем на сам canvas ─────────────────────
cropCanvas.addEventListener('mousedown', (e) => {
    if (!cropMode) return;
    e.preventDefault();
    e.stopPropagation();
    syncCropCanvasSize();
    const r    = cropCanvas.getBoundingClientRect();
    cropStart  = { x: e.clientX - r.left, y: e.clientY - r.top };
    cropRect   = null;
    cropDrawing = true;
    cropRedraw(null);
});

// Esc — выход из режима
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && cropMode) exitCropMode();
});

// ── Вспомогательная: нормализовать прямоугольник (w/h > 0) ──
function normalizeRect(x1, y1, x2, y2) {
    return {
        x: Math.min(x1, x2),
        y: Math.min(y1, y2),
        w: Math.abs(x2 - x1),
        h: Math.abs(y2 - y1)
    };
}

// ── Вычислить координаты выделения в пикселях оригинала ─────
function canvasRectToImagePixels(canvasRect) {
    // imagePreview позиционируется как: translate(-50%+tx, -50%+ty) scale(s)
    // центр изображения в координатах контейнера:
    const containerW = cropCanvas.width;
    const containerH = cropCanvas.height;

    const imgNaturalW = imagePreview.naturalWidth;
    const imgNaturalH = imagePreview.naturalHeight;

    // Размер img на экране (без учёта scale — getBoundingClientRect учитывает transform)
    const imgRect = imagePreview.getBoundingClientRect();
    const canvasRect2 = cropCanvas.getBoundingClientRect();

    // Позиция левого верхнего угла img в координатах canvas
    const imgLeft = imgRect.left - canvasRect2.left;
    const imgTop  = imgRect.top  - canvasRect2.top;
    const imgW    = imgRect.width;
    const imgH    = imgRect.height;

    // Перевод из canvas-координат в пиксели оригинала
    const scaleX = imgNaturalW / imgW;
    const scaleY = imgNaturalH / imgH;

    const px = Math.round((canvasRect.x - imgLeft) * scaleX);
    const py = Math.round((canvasRect.y - imgTop)  * scaleY);
    const pw = Math.round(canvasRect.w * scaleX);
    const ph = Math.round(canvasRect.h * scaleY);

    // Зажать в границы изображения
    const cx = Math.max(0, Math.min(px, imgNaturalW - 1));
    const cy = Math.max(0, Math.min(py, imgNaturalH - 1));
    const cw = Math.max(1, Math.min(pw, imgNaturalW - cx));
    const ch = Math.max(1, Math.min(ph, imgNaturalH - cy));

    return { x: cx, y: cy, w: cw, h: ch };
}

// ── Кропнуть через offscreen canvas и отправить на OCR ──────
async function processCropRegion(options = {}) {
    if (!cropRect || pages.length === 0) return;


    const pixels = canvasRectToImagePixels(cropRect);
    if (pixels.w < 4 || pixels.h < 4) {
        showNotification('Выделенная область слишком мала', 'error');
        return;
    }

    // Spinner поверх выделения
    const overlay = document.createElement('div');
    overlay.className = 'crop-processing-overlay';
    overlay.innerHTML = '<div class="crop-spinner"></div><span>Распознавание области...</span>';
    imageContainer.appendChild(overlay);

    // Кроп через offscreen canvas
    const offscreen = document.createElement('canvas');
    offscreen.width  = pixels.w;
    offscreen.height = pixels.h;
    const octx = offscreen.getContext('2d');
    octx.drawImage(imagePreview, pixels.x, pixels.y, pixels.w, pixels.h, 0, 0, pixels.w, pixels.h);

    let blob;
    try {
        blob = await new Promise((res, rej) =>
            offscreen.toBlob(b => b ? res(b) : rej(new Error('toBlob failed')), 'image/png'));
    } catch (err) {
        overlay.remove();
        showNotification('Ошибка кропа: ' + err.message, 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', blob, 'crop_region.png');
    formData.append('ocr_engine', ocrEngine.value);
        formData.append('language', languageSelect.value);

    const endpoint = '/process';

    try {
        const response = await fetch(endpoint, { method: 'POST', body: formData });
        const result   = await response.json();

        overlay.remove();

        if (response.ok) {
            // Показываем popup — не пишем сразу в textarea
            showCropResultPopup(result.text);
        } else {
            showNotification('Ошибка: ' + (result.detail || 'Сервер недоступен'), 'error');
            clearCropSelection();
        }
    } catch (err) {
        overlay.remove();
        showNotification('Ошибка соединения: ' + err.message, 'error');
        clearCropSelection();
    }
}

// ── Панель результата распознавания области ─────────────────
const cropResultPanel = $('cropResultPanel');
const cropResultText  = $('cropResultText');

function showCropResultPopup(recognizedText) {
    if (!cropResultPanel || !cropResultText) return;
    cropResultText.value = recognizedText;
    cropResultPanel.style.display = 'flex';
    cropResultText.focus();
}

function closeCropPanel() {
    if (cropResultPanel) cropResultPanel.style.display = 'none';
    if (cropResultText)  cropResultText.value = '';
    clearCropSelection();
}

function cropApplyReplace() {
    if (!cropResultText || !extractedText) return;
    setEditorText(cropResultText.value);
    isEditorReadOnly(false);
    if (pages[currentPageIndex]) {
        pages[currentPageIndex].text   = getEditorText();
        pages[currentPageIndex].status = 'done';
    }
    updateFullTextStats();
    updatePageStatus();
    showNotification('Текст заменён ✓', 'success');
    closeCropPanel();
}

function cropApplyInsert() {
    if (!cropResultText || !extractedText) return;
    const insertText = cropResultText.value;
    isEditorReadOnly(false);
    const start = extractedText.selectionStart != null ? extractedText.selectionStart : getEditorText().length;
    const end   = extractedText.selectionEnd   != null ? extractedText.selectionEnd   : start;
    setEditorText(getEditorText().substring(0, start) + insertText + getEditorText().substring(end));
    const newPos = start + insertText.length;
    extractedText.setSelectionRange(newPos, newPos);
    extractedText.focus();
    if (pages[currentPageIndex]) {
        pages[currentPageIndex].text   = getEditorText();
        pages[currentPageIndex].status = 'done';
    }
    updateFullTextStats();
    updatePageStatus();
    showNotification('Текст вставлен ✓', 'success');
    closeCropPanel();
}

// ── Resize панели результата кропа ───────────────────────────
(function () {
    const handle = $('crpResizeHandle');
    const panel  = $('cropResultPanel');
    if (!handle || !panel) return;

    const MIN_H = 100;
    const MAX_H = 500;

    let dragging = false;
    let startY   = 0;
    let startH   = 0;

    handle.addEventListener('mousedown', (e) => {
        dragging = true;
        startY   = e.clientY;
        startH   = panel.offsetHeight;
        handle.classList.add('dragging');
        document.body.style.cursor    = 'ns-resize';
        document.body.style.userSelect = 'none';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        // Тянем вверх — панель растёт, вниз — уменьшается
        const delta  = startY - e.clientY;
        const newH   = Math.min(MAX_H, Math.max(MIN_H, startH + delta));
        panel.style.maxHeight = newH + 'px';
        panel.style.height    = newH + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        handle.classList.remove('dragging');
        document.body.style.cursor     = '';
        document.body.style.userSelect = '';
    });
})();

// ═══════════════════════════════════════════════════════════
//  LAYOUT ANALYSIS
// ═══════════════════════════════════════════════════════════

const layoutCanvas  = $('layoutCanvas');
const layoutBtn     = $('layoutBtn');
const clearLayoutBtn = $('clearLayoutBtn');

let layoutBlocks = [];      // последний результат детекции
let hoveredBlock = null;    // блок под курсором

// ── Запуск анализа ───────────────────────────────────────────
async function detectLayout() {
    if (pages.length === 0) return showNotification('Загрузите изображение!', 'error');

    layoutBtn.disabled = true;
    layoutBtn.textContent = '⊞ Анализ...';

    const formData = new FormData();
    formData.append('file', await getPageBlob(pages[currentPageIndex]));

    try {
        const response = await fetch('/detect-layout', { method: 'POST', body: formData });
        const result   = await response.json();

        if (!response.ok) {
            showNotification('Ошибка: ' + (result.detail || 'Сервер'), 'error');
            return;
        }

        layoutBlocks = result.blocks;
        renderLayoutBlocks(result.image_width, result.image_height);

        if (clearLayoutBtn) clearLayoutBtn.style.display = 'inline-block';
        showNotification(`Найдено блоков: ${layoutBlocks.length}`, 'success');

    } catch (err) {
        showNotification('Ошибка соединения: ' + err.message, 'error');
    } finally {
        layoutBtn.disabled = false;
        layoutBtn.textContent = '⊞ Анализ блоков';
    }
}

// ── Отрисовка блоков на canvas ───────────────────────────────
function renderLayoutBlocks(imgNatW, imgNatH) {
    if (!layoutCanvas) return;

    syncLayoutCanvasSize();
    layoutCanvas.style.display = 'block';

    const ctx = layoutCanvas.getContext('2d');
    ctx.clearRect(0, 0, layoutCanvas.width, layoutCanvas.height);

    // Координаты img на экране
    const imgRect  = imagePreview.getBoundingClientRect();
    const canvRect = layoutCanvas.getBoundingClientRect();
    const imgLeft  = imgRect.left  - canvRect.left;
    const imgTop   = imgRect.top   - canvRect.top;
    const imgW     = imgRect.width;
    const imgH     = imgRect.height;

    const scaleX = imgW  / imgNatW;
    const scaleY = imgH  / imgNatH;

    layoutBlocks.forEach((block, idx) => {
        const { x, y, w, h } = block.bbox;
        const cx = imgLeft + x * scaleX;
        const cy = imgTop  + y * scaleY;
        const cw = w * scaleX;
        const ch = h * scaleY;

        // Сохраняем экранные координаты для hit-test
        block._screen = { x: cx, y: cy, w: cw, h: ch };

        drawBlock(ctx, block, cx, cy, cw, ch, false);
    });
}

function drawBlock(ctx, block, x, y, w, h, hovered) {
    const color = block.color;
    const alpha = hovered ? 0.18 : 0.08;

    // Заливка
    ctx.save();
    ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2, '0');
    ctx.fillRect(x, y, w, h);
    ctx.restore();

    // Рамка
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth   = hovered ? 2.5 : 1.5;
    ctx.setLineDash(hovered ? [] : []);
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    ctx.restore();

    // Лейбл
    const label = `${block.label} ${Math.round(block.confidence * 100)}%`;
    const fontSize = 11;
    ctx.save();
    ctx.font = `600 ${fontSize}px Inter, sans-serif`;
    const textW = ctx.measureText(label).width;
    const padX = 5, padY = 3;
    const tagW = textW + padX * 2;
    const tagH = fontSize + padY * 2;
    // Фон тега
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(x, y, tagW, tagH, 3);
    ctx.fill();
    // Текст тега
    ctx.fillStyle = '#ffffff';
    ctx.fillText(label, x + padX, y + tagH - padY - 1);
    ctx.restore();
}

function syncLayoutCanvasSize() {
    if (!layoutCanvas) return;
    const rect = imageContainer.getBoundingClientRect();
    layoutCanvas.width  = Math.round(rect.width);
    layoutCanvas.height = Math.round(rect.height);
}

// ── Hover — подсветка блока под курсором ─────────────────────
layoutCanvas && layoutCanvas.addEventListener('mousemove', (e) => {
    if (!layoutBlocks.length) return;
    const r  = layoutCanvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;

    // Ищем самый маленький блок под курсором (чтобы выбирать вложенные)
    let found = null;
    let minArea = Infinity;
    layoutBlocks.forEach(block => {
        const s = block._screen;
        if (!s) return;
        if (mx >= s.x && mx <= s.x + s.w && my >= s.y && my <= s.y + s.h) {
            const area = s.w * s.h;
            if (area < minArea) { minArea = area; found = block; }
        }
    });

    if (found !== hoveredBlock) {
        hoveredBlock = found;
        layoutCanvas.style.cursor = found ? 'pointer' : 'default';
        redrawLayoutBlocks();
    }
});

layoutCanvas && layoutCanvas.addEventListener('mouseleave', () => {
    hoveredBlock = null;
    redrawLayoutBlocks();
});

// ── Клик по блоку → кроп + OCR ──────────────────────────────
layoutCanvas && layoutCanvas.addEventListener('click', (e) => {
    if (!hoveredBlock) return;
    const block = hoveredBlock;

    // Переводим экранные координаты блока в пиксели оригинала
    const imgRect  = imagePreview.getBoundingClientRect();
    const canvRect = layoutCanvas.getBoundingClientRect();
    const imgLeft  = imgRect.left  - canvRect.left;
    const imgTop   = imgRect.top   - canvRect.top;
    const imgW     = imgRect.width;
    const imgH     = imgRect.height;
    const scaleX   = imagePreview.naturalWidth  / imgW;
    const scaleY   = imagePreview.naturalHeight / imgH;

    const s = block._screen;
    const px = Math.round((s.x - imgLeft) * scaleX);
    const py = Math.round((s.y - imgTop)  * scaleY);
    const pw = Math.round(s.w * scaleX);
    const ph = Math.round(s.h * scaleY);

    const pixels = {
        x: Math.max(0, px),
        y: Math.max(0, py),
        w: Math.min(pw, imagePreview.naturalWidth  - Math.max(0, px)),
        h: Math.min(ph, imagePreview.naturalHeight - Math.max(0, py)),
    };

    processCropFromPixels(pixels, block.label);
});

// ── Кроп по готовым пикселям (вызывается из layout click) ────
async function processCropFromPixels(pixels, blockLabel = '') {
    if (pixels.w < 4 || pixels.h < 4) return;

    const overlay = document.createElement('div');
    overlay.className = 'crop-processing-overlay';
    overlay.innerHTML = '<div class="crop-spinner"></div><span>Распознавание блока...</span>';
    imageContainer.appendChild(overlay);

    const offscreen = document.createElement('canvas');
    offscreen.width  = pixels.w;
    offscreen.height = pixels.h;
    offscreen.getContext('2d').drawImage(
        imagePreview, pixels.x, pixels.y, pixels.w, pixels.h, 0, 0, pixels.w, pixels.h
    );

    let blob;
    try {
        blob = await new Promise((res, rej) =>
            offscreen.toBlob(b => b ? res(b) : rej(new Error('toBlob failed')), 'image/png'));
    } catch (err) {
        overlay.remove();
        showNotification('Ошибка кропа: ' + err.message, 'error');
        return;
    }

    const isTable = blockLabel.toLowerCase().includes('table');
    const formData = new FormData();
    formData.append('file', blob, 'layout_block.png');

    try {
        let response, result;
        if (isTable) {
            formData.append('language', languageSelect ? languageSelect.value : 'rus');
            response = await fetch('/extract-table', { method: 'POST', body: formData });
            result = await response.json();
            overlay.remove();
            if (response.ok) {
                showTableModal(result.rows, result.csv);
            } else {
                showNotification('Ошибка извлечения таблицы: ' + (result.detail || ''), 'error');
            }
        } else {
            formData.append('ocr_engine', ocrEngine ? ocrEngine.value : 'tesseract');
            formData.append('language', languageSelect ? languageSelect.value : 'rus');
            response = await fetch('/process', { method: 'POST', body: formData });
            result = await response.json();
            overlay.remove();
            if (response.ok) {
                showCropResultPopup(result.text);
            } else {
                showNotification('Ошибка: ' + (result.detail || ''), 'error');
            }
        }
    } catch (err) {
        overlay.remove();
        showNotification('Ошибка: ' + err.message, 'error');
    }
}

function redrawLayoutBlocks() {
    if (!layoutCanvas || !layoutBlocks.length) return;
    const ctx = layoutCanvas.getContext('2d');
    ctx.clearRect(0, 0, layoutCanvas.width, layoutCanvas.height);
    layoutBlocks.forEach(block => {
        if (!block._screen) return;
        const { x, y, w, h } = block._screen;
        drawBlock(ctx, block, x, y, w, h, block === hoveredBlock);
    });
}

function clearLayout() {
    layoutBlocks = [];
    hoveredBlock = null;
    if (layoutCanvas) {
        layoutCanvas.getContext('2d').clearRect(0, 0, layoutCanvas.width, layoutCanvas.height);
        layoutCanvas.style.display = 'none';
    }
    if (clearLayoutBtn) clearLayoutBtn.style.display = 'none';
}

// Перерисовывать блоки при зуме/пане (изображение двигается)
const _origUpdateTransform = updateImageTransform;
updateImageTransform = function () {
    _origUpdateTransform();
    if (layoutBlocks.length) {
        // Небольшая задержка чтобы getBoundingClientRect обновился после transform
        requestAnimationFrame(() => {
            const img = imagePreview;
            if (!img || !img.naturalWidth) return;
            renderLayoutBlocks(img.naturalWidth, img.naturalHeight);
        });
    }
};

// ═══════════════════════════════════════════════════════════
//  TEXT ANALYSIS
// ═══════════════════════════════════════════════════════════

function switchTab(tab) {
    document.getElementById('paneSummary').style.display  = tab === 'summary'  ? 'flex' : 'none';
    document.getElementById('paneAnalysis').style.display = tab === 'analysis' ? 'flex' : 'none';
    document.getElementById('tabSummary').classList.toggle('active',  tab === 'summary');
    document.getElementById('tabAnalysis').classList.toggle('active', tab === 'analysis');
}

async function analyzeText() {
    const text = extractedText ? getEditorText().trim() : '';
    if (!text) return showNotification('Сначала распознайте текст', 'error');
    if (text.split(' ').length < 3) return showNotification('Текст слишком короткий', 'error');

    const btn     = $('analyzeBtn');
    const content = $('analysisContent');
    btn.disabled = true;
    btn.textContent = 'Анализ...';
    content.innerHTML = '<div class="analysis-loading"><div class="crop-spinner" style="border-top-color:#4F46E5"></div><span>Анализируем текст...</span></div>';

    try {
        const response = await fetch('/analyze-text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text }),
        });
        const result = await response.json();
        if (!response.ok) {
            content.innerHTML = `<div class="analysis-error">${result.detail || 'Ошибка'}</div>`;
            return;
        }
        renderAnalysis(result, content);
    } catch (err) {
        content.innerHTML = `<div class="analysis-error">Ошибка: ${err.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Анализировать';
    }
}

function renderAnalysis(data, container) {
    const { statistics: s, keywords, entities, sentiment } = data;
    let html = '';

    // ── Тональность ──────────────────────────────────────
    if (sentiment && sentiment.label !== 'unavailable') {
        const pct = Math.round(sentiment.score * 100);
        html += `
        <div class="an-card">
            <div class="an-card-title">Тональность</div>
            <div class="an-sentiment">
                <span class="an-sentiment-badge" style="background:${sentiment.color}20;color:${sentiment.color};border-color:${sentiment.color}40">
                    ${sentimentIcon(sentiment.label)} ${sentiment.label_ru}
                </span>
                <div class="an-sentiment-bar">
                    <div class="an-sentiment-fill" style="width:${pct}%;background:${sentiment.color}"></div>
                </div>
                <span class="an-sentiment-pct">${pct}%</span>
            </div>
        </div>`;
    }

    // ── Статистика ───────────────────────────────────────
    if (s) {
        html += `
        <div class="an-card">
            <div class="an-card-title">Статистика</div>
            <div class="an-stats-grid">
                ${statCell('Слов', s.words)}
                ${statCell('Предложений', s.sentences)}
                ${statCell('Символов', s.chars)}
                ${statCell('Уникальных слов', s.unique_words)}
                ${statCell('Ср. длина слова', s.avg_word_length + ' букв')}
                ${statCell('Ср. длина предл.', s.avg_sentence_length + ' слов')}
                ${statCell('Лексическое разнообразие', s.lexical_diversity + '%')}
            </div>
            <div class="an-readability">
                <div class="an-readability-label">
                    Читаемость: <strong style="color:${s.readability_color}">${s.readability_label}</strong>
                    <span class="an-readability-score">${s.readability_score}/100</span>
                </div>
                <div class="an-readability-bar">
                    <div style="width:${s.readability_score}%;background:${s.readability_color};height:100%;border-radius:4px;transition:width 0.5s"></div>
                </div>
            </div>
        </div>`;

        // Топ слов
        if (s.top_words && s.top_words.length) {
            const max = s.top_words[0].count;
            html += `<div class="an-card">
                <div class="an-card-title">Частые слова</div>
                <div class="an-words-list">
                ${s.top_words.map(w => `
                    <div class="an-word-row">
                        <span class="an-word-text">${w.word}</span>
                        <div class="an-word-bar-wrap">
                            <div class="an-word-bar" style="width:${Math.round(w.count/max*100)}%"></div>
                        </div>
                        <span class="an-word-count">${w.count}</span>
                    </div>`).join('')}
                </div>
            </div>`;
        }
    }

    // ── Ключевые слова ───────────────────────────────────
    if (keywords && keywords.length) {
        html += `<div class="an-card">
            <div class="an-card-title">Ключевые слова</div>
            <div class="an-keywords">
                ${keywords.map(k => `<span class="an-kw-tag" title="${k.count} упоминаний">${k.word}</span>`).join('')}
            </div>
        </div>`;
    }

    // ── Именованные сущности ─────────────────────────────
    const entLabels = {
        PER:   { label: 'Персоны',        color: '#3B82F6', icon: '👤' },
        ORG:   { label: 'Организации',    color: '#8B5CF6', icon: '🏢' },
        LOC:   { label: 'Локации',        color: '#10B981', icon: '📍' },
        DATE:  { label: 'Даты',           color: '#F59E0B', icon: '📅' },
        MONEY: { label: 'Суммы',          color: '#EF4444', icon: '💰' },
    };
    const hasEntities = entities && Object.values(entities).some(v => v.length > 0);
    if (hasEntities) {
        html += `<div class="an-card"><div class="an-card-title">Именованные сущности</div>`;
        for (const [key, meta] of Object.entries(entLabels)) {
            const items = entities[key];
            if (!items || !items.length) continue;
            html += `<div class="an-ent-group">
                <div class="an-ent-label" style="color:${meta.color}">${meta.icon} ${meta.label}</div>
                <div class="an-ent-tags">
                    ${items.map(e => `<span class="an-ent-tag" style="background:${meta.color}18;border-color:${meta.color}40;color:${meta.color}cc">${e}</span>`).join('')}
                </div>
            </div>`;
        }
        html += `</div>`;
    }

    container.innerHTML = html || '<div class="analysis-placeholder"><p>Нет данных для отображения</p></div>';
}

function statCell(label, value) {
    return `<div class="an-stat-cell"><div class="an-stat-val">${value}</div><div class="an-stat-lbl">${label}</div></div>`;
}
function sentimentIcon(label) {
    return label === 'positive' ? '😊' : label === 'negative' ? '😞' : '😐';
}

// ═══════════════════════════════════════════════════════════
//  ENGINE MODE & SPELL CHECK
// ═══════════════════════════════════════════════════════════

function onEngineChange() {
    const engine = ocrEngine ? ocrEngine.value : 'tesseract';
    const modeEl = $('textModeSelector');
    if (modeEl) modeEl.style.display = engine === 'vlm' ? 'flex' : 'none';
}

// ── OCR Progress Bar// ── OCR Progress Bar ─────────────────────────────────────────
let _ocrProgressEl = null;

function showOcrProgress(pct, msg) {
    if (!_ocrProgressEl) {
        _ocrProgressEl = document.createElement('div');
        _ocrProgressEl.className = 'ocr-progress-bar';
        _ocrProgressEl.innerHTML =
            '<div class="ocr-progress-track"><div class="ocr-progress-fill" id="ocrProgressFill"></div></div>' +
            '<div class="ocr-progress-label" id="ocrProgressLabel"></div>';
        // Вставляем под тулбаром
        const toolbar = document.querySelector('.toolbar');
        toolbar && toolbar.parentNode.insertBefore(_ocrProgressEl, toolbar.nextSibling);
    }
    _ocrProgressEl.style.display = 'flex';
    const fill  = $('ocrProgressFill');
    const label = $('ocrProgressLabel');
    if (fill)  fill.style.width = pct + '%';
    if (label) label.textContent = msg || '';
    // Анимируем прогресс если pct < 100
    fill && fill.classList.toggle('ocr-progress-indeterminate', pct > 0 && pct < 90);
}

function hideOcrProgress() {
    if (_ocrProgressEl) {
        const fill = $('ocrProgressFill');
        if (fill) fill.style.width = '100%';
        setTimeout(() => {
            if (_ocrProgressEl) _ocrProgressEl.style.display = 'none';
        }, 400);
    }
}

// ═══════════════════════════════════════════════════════════
//  ENGINE COMPARE
// ═══════════════════════════════════════════════════════════

async function compareEngines() {
    if (pages.length === 0) return showNotification('Загрузите изображение!', 'error');

    const modal = $('compareModal');
    if (!modal) return;

    $('compareTessText').value = '';
    $('compareVlmText').value  = '';
    $('compareTessTime').textContent = '';
    $('compareVlmTime').textContent  = '';
    $('compareProgress').style.display = 'flex';
    $('compareColumns').style.display  = 'none';
    if ($('compareProgressMsg')) $('compareProgressMsg').textContent = 'Запуск сравнения...';
    modal.style.display = 'flex';

    const page = pages[currentPageIndex];
    const formData = new FormData();
    formData.append('file', await getPageBlob(page));
    formData.append('language', languageSelect ? languageSelect.value : 'rus');
    const modeEl = document.getElementById('textMode');
    formData.append('text_mode', modeEl ? modeEl.value : 'printed');
    const preprocEl = document.getElementById('preprocessing');
    formData.append('preprocessing', preprocEl ? preprocEl.value : 'none');

    try {
        const response = await fetch('/compare-stream', { method: 'POST', body: formData });
        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const evt = JSON.parse(line.slice(6));
                    if ($('compareProgressMsg')) $('compareProgressMsg').textContent = evt.message;

                    if (evt.stage === 'tesseract_done') {
                        $('compareTessText').value = evt.tesseract_text || '';
                        if (evt.tesseract_time) $('compareTessTime').textContent = evt.tesseract_time + ' с';
                        $('compareProgress').style.display = 'none';
                        $('compareColumns').style.display  = 'grid';
                    } else if (evt.stage === 'vlm_done') {
                        $('compareVlmText').value = evt.vlm_error ? `[${evt.vlm_error}]` : (evt.vlm_text || '');
                        if (evt.vlm_time) $('compareVlmTime').textContent = evt.vlm_time + ' с';
                    } else if (evt.stage === 'error') {
                        showNotification('Ошибка: ' + evt.message, 'error');
                        closeCompareModal();
                    }
                } catch (e) { /* ignore */ }
            }
        }
    } catch (err) {
        showNotification('Ошибка: ' + err.message, 'error');
        closeCompareModal();
    }
}

function closeCompareModal() {
    const m = $('compareModal');
    if (m) m.style.display = 'none';
}

function applyCompareResult(engine) {
    const el  = engine === 'tesseract' ? $('compareTessText') : $('compareVlmText');
    const text = el ? el.value : '';
    if (!text) return showNotification('Нет текста', 'error');
    setEditorText(text);
    isEditorReadOnly(false);
    if (pages[currentPageIndex]) {
        pages[currentPageIndex].text   = text;
        pages[currentPageIndex].status = 'done';
    }
    updateFullTextStats();
    updatePageStatus();
    closeCompareModal();
    showNotification('Текст применён ✓', 'success');
}

// ═══════════════════════════════════════════════════════════
//  DOCX EXPORT
// ═══════════════════════════════════════════════════════════

async function exportDocx() {
    const text = extractedText ? getEditorText() : '';
    if (!text.trim()) return showNotification('Нет текста для экспорта', 'error');
    try {
        const filename = `ocr_page_${currentPageIndex + 1}_${Date.now()}`;
        const response = await fetch('/export/docx', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, filename }),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            return showNotification('Ошибка: ' + (err.detail || 'Сервер'), 'error');
        }
        const blob = await response.blob();
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = filename + '.docx';
        a.click();
        URL.revokeObjectURL(url);
        showNotification('DOCX сохранён ✓', 'success');
    } catch (err) {
        showNotification('Ошибка: ' + err.message, 'error');
    }
}

// ═══════════════════════════════════════════════════════════
//  HISTORY
// ═══════════════════════════════════════════════════════════

async function showHistoryModal() {
    const modal = $('historyModal');
    if (modal) modal.style.display = 'flex';
    await loadHistory();
}

function closeHistoryModal() {
    const m = $('historyModal');
    if (m) m.style.display = 'none';
}

async function loadHistory() {
    const list = $('historyList');
    if (!list) return;
    list.innerHTML = '<div class="history-empty">Загрузка...</div>';
    try {
        const response = await fetch('/history');
        const items    = await response.json();
        if (!items.length) {
            list.innerHTML = '<div class="history-empty">История пуста — сохраните результаты обработки кнопкой «Сохранить»</div>';
            return;
        }
        list.innerHTML = items.map(item => `
            <div class="history-item" onclick="restoreFromHistory(${item.id})">
                ${item.image
                    ? `<img class="history-thumb" src="data:image/jpeg;base64,${item.image}" alt="">`
                    : `<div class="history-thumb history-thumb-empty">📄</div>`}
                <div class="history-info">
                    <div class="history-name">${escapeHtml(item.filename)}</div>
                    <div class="history-meta">${item.created_at} · ${item.ocr_engine} · ${item.language} · ${item.page_count} стр.</div>
                    <div class="history-preview">${escapeHtml(item.preview || '')}</div>
                </div>
                <div class="history-actions">
                    <button class="history-del-btn" onclick="event.stopPropagation();deleteHistory(${item.id})" title="Удалить">✕</button>
                </div>
            </div>`).join('');
    } catch (err) {
        list.innerHTML = `<div class="history-empty">Ошибка загрузки: ${err.message}</div>`;
    }
}

async function restoreFromHistory(docId) {
    try {
        const response = await fetch(`/history/${docId}`);
        if (!response.ok) return showNotification('Запись не найдена', 'error');
        const doc = await response.json();
        setEditorText(doc.text || '');
        isEditorReadOnly(false);
        if (pages.length > 0 && pages[currentPageIndex]) {
            pages[currentPageIndex].text   = doc.text || '';
            pages[currentPageIndex].status = 'done';
        }
        updateFullTextStats();
        updatePageStatus();
        closeHistoryModal();
        showNotification(`Загружено: ${doc.filename}`, 'success');
    } catch (err) {
        showNotification('Ошибка: ' + err.message, 'error');
    }
}

async function deleteHistory(docId) {
    try {
        await fetch(`/history/${docId}`, { method: 'DELETE' });
        await loadHistory();
    } catch (err) {
        showNotification('Ошибка удаления: ' + err.message, 'error');
    }
}

async function saveToHistory() {
    const text = extractedText ? getEditorText().trim() : '';
    if (!text) return showNotification('Нет текста для сохранения', 'error');
    const page     = pages[currentPageIndex];
    const filename = page && page.file ? page.file.name : `page_${currentPageIndex + 1}`;
    const image    = page ? (page.preview || '') : '';
    try {
        await fetch('/history/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename,
                engine:     ocrEngine     ? ocrEngine.value     : 'tesseract',
                language:   languageSelect ? languageSelect.value : 'rus',
                text,
                page_count: pages.length || 1,
                image,
            }),
        });
        showNotification('Сохранено в историю ✓', 'success');
    } catch (err) {
        showNotification('Ошибка: ' + err.message, 'error');
    }
}

// ═══════════════════════════════════════════════════════════
//  TABLE MODAL
// ═══════════════════════════════════════════════════════════

function showTableModal(rows, csv) {
    const modal     = $('tableModal');
    const tableBody = $('tableBody');
    const tableCsv  = $('tableCsv');
    if (!modal) return;

    if (tableBody) {
        if (!rows || !rows.length) {
            tableBody.innerHTML = '<tr><td colspan="20" style="text-align:center;padding:24px;color:#6B7280">Таблица не обнаружена</td></tr>';
        } else {
            tableBody.innerHTML = rows.map((row, i) =>
                '<tr>' + row.map(cell =>
                    i === 0
                        ? `<th>${escapeHtml(cell)}</th>`
                        : `<td>${escapeHtml(cell)}</td>`
                ).join('') + '</tr>'
            ).join('');
        }
    }
    if (tableCsv) tableCsv.value = csv || '';
    modal.style.display = 'flex';
}

function closeTableModal() {
    const m = $('tableModal');
    if (m) m.style.display = 'none';
}

function copyTableCsv() {
    const csv = $('tableCsv');
    if (!csv || !csv.value) return showNotification('Нет данных CSV', 'error');
    navigator.clipboard.writeText(csv.value).then(() => showNotification('CSV скопирован ✓', 'success'));
}

// ── Utility ──────────────────────────────────────────────────
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}