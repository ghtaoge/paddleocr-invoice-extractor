/* ============================================================
   票析 — 增值税发票识别 前端逻辑
   ============================================================ */

(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────
  const API_OCR     = '/api/ocr';
  const API_HEALTH  = '/api/health';
  const MAX_FILE_MB = 10;
  const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
  const ACCEPTED_EXT = ['jpg', 'jpeg', 'png', 'bmp'];

  // ── DOM References ──────────────────────────────────────────
  const $dropzone       = document.getElementById('dropzone');
  const $fileInput      = document.getElementById('fileInput');
  const $previewImg     = document.getElementById('previewImg');
  const $imagePreview   = document.getElementById('imagePreview');
  const $overlayCanvas  = document.getElementById('overlayCanvas');
  const $clearBtn       = document.getElementById('clearBtn');
  const $recognizeBtn   = document.getElementById('recognizeBtn');
  const $emptyState     = document.getElementById('emptyState');
  const $resultContent  = document.getElementById('resultContent');
  const $tabSwitch      = document.getElementById('tabSwitch');
  const $tabAnnotation  = document.getElementById('tabAnnotation');
  const $tabTable       = document.getElementById('tabTable');
  const $annotationView = document.getElementById('annotationView');
  const $tableView      = document.getElementById('tableView');
  const $confValue      = document.getElementById('confValue');
  const $confBarFill    = document.getElementById('confBarFill');
  const $reliabilityArea= document.getElementById('reliabilityArea');
  const $fieldGroups    = document.getElementById('fieldGroups');
  const $exportJsonBtn  = document.getElementById('exportJsonBtn');
  const $exportCsvBtn   = document.getElementById('exportCsvBtn');
  const $runtimeDot     = document.getElementById('runtimeDot');
  const $runtimeLabel   = document.getElementById('runtimeLabel');
  const $toast          = document.getElementById('toast');

  // ── State ───────────────────────────────────────────────────
  let currentFile     = null;       // File object uploaded by user
  let currentResult   = null;       // Full InvoiceResult from API
  let revealedFields  = {};         // { fieldKey: true } for individually-revealed fields
  let activeTab       = 'annotation'; // 'annotation' | 'table'
  let isProcessing    = false;

  // ── Health Check ─────────────────────────────────────────────
  async function checkHealth() {
    $runtimeDot.className = 'runtime-dot runtime-dot--pulse';
    $runtimeLabel.textContent = '检测服务状态…';

    try {
      const res = await fetch(API_HEALTH);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();

      if (data.status === 'ok' && data.model_status === 'loaded') {
        $runtimeDot.className = 'runtime-dot runtime-dot--ok';
        $runtimeLabel.textContent = '服务就绪 · ' + data.device;
      } else if (data.status === 'ok' && data.model_status === 'loading') {
        $runtimeDot.className = 'runtime-dot runtime-dot--warn runtime-dot--pulse';
        $runtimeLabel.textContent = '模型加载中… · ' + data.device;
      } else if (data.status === 'ok' && data.model_status === 'not_loaded') {
        $runtimeDot.className = 'runtime-dot runtime-dot--warn';
        $runtimeLabel.textContent = '模型未加载 · ' + data.device;
      } else {
        $runtimeDot.className = 'runtime-dot runtime-dot--error';
        $runtimeLabel.textContent = '服务异常';
      }
    } catch (_) {
      $runtimeDot.className = 'runtime-dot runtime-dot--error';
      $runtimeLabel.textContent = '服务不可达';
    }
  }

  // ── Toast ────────────────────────────────────────────────────
  let toastTimer = null;

  function showToast(message, type = '') {
    clearTimeout(toastTimer);
    $toast.textContent = message;
    $toast.className = 'toast' + (type ? ' toast--' + type : '') + ' toast--visible';
    toastTimer = setTimeout(() => {
      $toast.classList.remove('toast--visible');
    }, 4000);
  }

  // ── File Validation ──────────────────────────────────────────
  function validateFile(file) {
    if (!file) return '请选择文件';
    if (file.size > MAX_FILE_BYTES) {
      return '文件超过 ' + MAX_FILE_MB + ' MB 限制';
    }
    const fileName = file.name || '';
    const dotIdx = fileName.lastIndexOf('.');
    const fileExt = dotIdx >= 0 ? fileName.slice(dotIdx + 1).toLowerCase() : '';
    if (!ACCEPTED_EXT.includes(fileExt)) {
      return '不支持该图片格式，请上传 JPG/PNG/BMP';
    }
    return null;
  }

  // ── File Upload Handlers ─────────────────────────────────────
  function handleFileSelect(file) {
    const error = validateFile(file);
    if (error) {
      showToast(error, 'error');
      return;
    }

    currentFile = file;
    revealedFields = {};
    currentResult = null;

    // Show preview
    const url = URL.createObjectURL(file);
    $previewImg.src = url;
    $previewImg.onload = () => {
      $dropzone.style.display = 'none';
      $imagePreview.style.display = 'flex';
      $clearBtn.disabled = false;
      $recognizeBtn.disabled = false;
      // Reset canvas size
      resizeOverlayCanvas();
    };

    // Clear previous results
    hideResults();
    clearOverlay();
  }

  function resizeOverlayCanvas() {
    const img = $previewImg;
    // Canvas dimensions match the displayed image size
    $overlayCanvas.width  = img.clientWidth;
    $overlayCanvas.height = img.clientHeight;
  }

  function clearImage() {
    if ($previewImg.src.startsWith('blob:')) {
      URL.revokeObjectURL($previewImg.src);
    }
    $previewImg.src = '';
    $imagePreview.style.display = 'none';
    $dropzone.style.display = '';
    $clearBtn.disabled = true;
    $recognizeBtn.disabled = true;
    currentFile = null;
    currentResult = null;
    revealedFields = {};
    hideResults();
    clearOverlay();
  }

  // ── Dropzone Events ──────────────────────────────────────────
  $dropzone.addEventListener('click', () => $fileInput.click());
  $dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      $fileInput.click();
    }
  });

  $fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  });

  // Drag events
  ['dragenter', 'dragover'].forEach(evt => {
    $dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      $dropzone.classList.add('dropzone--active');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    $dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      $dropzone.classList.remove('dropzone--active');
    });
  });

  $dropzone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files && files[0]) {
      handleFileSelect(files[0]);
    }
  });

  // ── Clear & Recognize ────────────────────────────────────────
  $clearBtn.addEventListener('click', clearImage);

  $recognizeBtn.addEventListener('click', async () => {
    if (!currentFile || isProcessing) return;

    isProcessing = true;
    $recognizeBtn.disabled = true;
    $recognizeBtn.innerHTML = '<span class="spinner"></span> 识别中…';

    try {
      const formData = new FormData();
      formData.append('file', currentFile);

      const res = await fetch(API_OCR, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        let errMsg = '识别失败';
        try {
          const errData = await res.json();
          errMsg = errData.message || errMsg;
        } catch (_) { /* use default */ }
        throw new Error(errMsg);
      }

      currentResult = await res.json();
      revealedFields = {};
      renderResults(currentResult);
      showToast('识别完成', '');

    } catch (err) {
      showToast(err.message || '识别失败，请稍后重试', 'error');
    } finally {
      isProcessing = false;
      $recognizeBtn.disabled = !currentFile;
      $recognizeBtn.innerHTML =
        '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> 开始识别';
    }
  });

  // ── Tab Switch ───────────────────────────────────────────────
  $tabAnnotation.addEventListener('click', () => switchTab('annotation'));
  $tabTable.addEventListener('click', () => switchTab('table'));

  function switchTab(tab) {
    activeTab = tab;

    $tabAnnotation.classList.toggle('segmented-btn--active', tab === 'annotation');
    $tabTable.classList.toggle('segmented-btn--active', tab === 'table');
    $tabAnnotation.setAttribute('aria-selected', tab === 'annotation');
    $tabTable.setAttribute('aria-selected', tab === 'table');

    $annotationView.style.display = tab === 'annotation' ? '' : 'none';
    $tableView.style.display      = tab === 'table' ? '' : 'none';

    if (tab === 'annotation' && currentResult) {
      drawOverlayBoxes(currentResult.ocr_boxes);
    } else {
      clearOverlay();
    }
  }

  // ── Hide / Show Results ──────────────────────────────────────
  function hideResults() {
    $emptyState.style.display = '';
    $resultContent.style.display = 'none';
  }

  function renderResults(result) {
    $emptyState.style.display = 'none';
    $resultContent.style.display = '';

    // Confidence
    const confPercent = Math.round(result.overall_confidence * 100);
    $confValue.textContent = confPercent + '%';
    $confBarFill.style.width = confPercent + '%';

    const confClass = result.overall_confidence >= 0.80 ? 'high' : 'low';
    $confBarFill.className = 'confidence-bar-fill confidence-bar-fill--' + confClass;

    // Reliability
    const relLevel = result.reliability.level;
    const relBadge = document.createElement('span');
    relBadge.className = 'reliability-badge reliability-badge--' + relLevel;
    relBadge.innerHTML = relLevel === 'high'
      ? '<svg class="icon icon--sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> 可靠度高'
      : '<svg class="icon icon--sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg> 可靠度低';

    $reliabilityArea.innerHTML = '';
    $reliabilityArea.appendChild(relBadge);

    if (result.reliability.reasons && result.reliability.reasons.length) {
      const reasonsEl = document.createElement('p');
      reasonsEl.className = 'reliability-reasons';
      reasonsEl.textContent = '原因：' + result.reliability.reasons.join('、');
      $reliabilityArea.appendChild(reasonsEl);
    }

    // Field Groups
    $fieldGroups.innerHTML = '';
    result.groups.forEach(group => {
      if (!group.fields.length) return;

      const section = document.createElement('div');

      // Group header
      const header = document.createElement('div');
      header.className = 'group-header';
      header.innerHTML = group.name +
        '<span class="group-count">' + group.fields.length + ' 个字段</span>';
      section.appendChild(header);

      // Table
      const table = document.createElement('table');
      table.className = 'field-table';

      const thead = document.createElement('thead');
      thead.innerHTML = '<tr><th>字段</th><th>值</th><th>置信度</th></tr>';
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      group.fields.forEach(field => {
        const tr = createFieldRow(field);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      section.appendChild(table);

      $fieldGroups.appendChild(section);
    });

    // Draw overlay if annotation tab is active
    if (activeTab === 'annotation') {
      drawOverlayBoxes(result.ocr_boxes);
    }

    // Switch to annotation tab by default
    switchTab('annotation');
  }

  // ── Field Row ────────────────────────────────────────────────
  function createFieldRow(field) {
    const tr = document.createElement('tr');

    // Label cell
    const tdLabel = document.createElement('td');
    tdLabel.className = 'field-label';
    tdLabel.textContent = field.label;
    tr.appendChild(tdLabel);

    // Value cell
    const tdValue = document.createElement('td');
    const wrap = document.createElement('div');
    wrap.className = 'field-value-wrap';

    const isRevealed = revealedFields[field.key];
    const hasDesensitized = field.desensitized !== field.value;

    const valueSpan = document.createElement('span');
    valueSpan.className = 'field-value' + (isRevealed ? '' : ' field-value--desensitized');
    valueSpan.textContent = isRevealed ? field.value : field.desensitized;
    valueSpan.dataset.key = field.key;
    wrap.appendChild(valueSpan);

    // Reveal toggle button (only for desensitized fields)
    if (hasDesensitized) {
      const revealBtn = document.createElement('button');
      revealBtn.className = 'field-reveal-btn';
      revealBtn.type = 'button';
      revealBtn.setAttribute('aria-label', isRevealed ? '隐藏完整值' : '查看完整值');
      revealBtn.title = isRevealed ? '隐藏完整值' : '查看完整值';
      revealBtn.innerHTML = isRevealed
        ? '<svg class="icon icon--sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'
        : '<svg class="icon icon--sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
      revealBtn.addEventListener('click', () => {
        revealedFields[field.key] = !revealedFields[field.key];
        // Re-render this row
        const newTr = createFieldRow(field);
        tr.parentNode.replaceChild(newTr, tr);
      });
      wrap.appendChild(revealBtn);
    }

    tdValue.appendChild(wrap);
    tr.appendChild(tdValue);

    // Confidence cell
    const tdConf = document.createElement('td');
    const confDiv = document.createElement('div');
    confDiv.className = 'field-confidence';

    const confClass = field.confidence >= 0.80 ? 'high' : 'low';
    const confPercent = Math.round(field.confidence * 100);

    const confValueSpan = document.createElement('span');
    confValueSpan.className = 'field-confidence-value';
    confValueSpan.textContent = confPercent + '%';
    confDiv.appendChild(confValueSpan);

    const confBarOuter = document.createElement('span');
    confBarOuter.className = 'field-confidence-bar';
    const confBarInner = document.createElement('span');
    confBarInner.className = 'field-confidence-bar-fill field-confidence-bar-fill--' + confClass;
    confBarInner.style.width = confPercent + '%';
    confBarOuter.appendChild(confBarInner);
    confDiv.appendChild(confBarOuter);

    tdConf.appendChild(confDiv);
    tr.appendChild(tdConf);

    return tr;
  }

  // ── Canvas Overlay ───────────────────────────────────────────
  function clearOverlay() {
    const ctx = $overlayCanvas.getContext('2d');
    ctx.clearRect(0, 0, $overlayCanvas.width, $overlayCanvas.height);
  }

  function drawOverlayBoxes(ocrBoxes) {
    clearOverlay();
    resizeOverlayCanvas();

    if (!ocrBoxes || !ocrBoxes.length) return;

    const ctx = $overlayCanvas.getContext('2d');
    const imgW = $previewImg.naturalWidth;
    const imgH = $previewImg.naturalHeight;
    const dispW = $previewImg.clientWidth;
    const dispH = $previewImg.clientHeight;

    if (!imgW || !imgH) return;

    const scaleX = dispW / imgW;
    const scaleY = dispH / imgH;

    ctx.strokeStyle = '#c63c2f';
    ctx.lineWidth = 2;
    ctx.fillStyle = 'rgba(198, 60, 47, 0.08)';
    ctx.font = '10px "Microsoft YaHei UI", "PingFang SC", sans-serif';

    ocrBoxes.forEach(boxItem => {
      const coords = boxItem.box;
      // PaddleOCR box format: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
      // Each point is [x, y]
      const x1 = coords[0][0] * scaleX;
      const y1 = coords[0][1] * scaleY;
      const x2 = coords[1][0] * scaleX;
      const y2 = coords[1][1] * scaleY;
      const x3 = coords[2][0] * scaleX;
      const y3 = coords[2][1] * scaleY;
      const x4 = coords[3][0] * scaleX;
      const y4 = coords[3][1] * scaleY;

      // Draw filled polygon
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.lineTo(x3, y3);
      ctx.lineTo(x4, y4);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Label above box
      const labelY = Math.min(y1, y2, y3, y4) - 4;
      const labelX = Math.min(x1, x2, x3, x4);
      ctx.fillStyle = '#c63c2f';
      const confPercent = Math.round(boxItem.confidence * 100);
      ctx.fillText(boxItem.text.slice(0, 12) + ' ' + confPercent + '%', labelX, labelY > 12 ? labelY : 12);
      ctx.fillStyle = 'rgba(198, 60, 47, 0.08)';
    });
  }

  // ── Export ────────────────────────────────────────────────────
  $exportJsonBtn.addEventListener('click', () => {
    if (!currentResult) return;
    const data = buildExportData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    downloadBlob(blob, 'invoice-result.json');
  });

  $exportCsvBtn.addEventListener('click', () => {
    if (!currentResult) return;
    const csv = buildCSV();
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    downloadBlob(blob, 'invoice-result.csv');
  });

  function buildExportData() {
    // Export uses full (non-desensitized) values
    const flat = {};
    currentResult.groups.forEach(group => {
      group.fields.forEach(field => {
        flat[field.key] = {
          label: field.label,
          value: field.value,  // full value, not desensitized
          confidence: field.confidence,
        };
      });
    });
    return {
      overall_confidence: currentResult.overall_confidence,
      reliability: currentResult.reliability,
      device: currentResult.device,
      fields: flat,
    };
  }

  function buildCSV() {
    const rows = [['分组', '字段名', '标签', '完整值', '置信度']];
    currentResult.groups.forEach(group => {
      group.fields.forEach(field => {
        rows.push([
          group.name,
          field.key,
          field.label,
          field.value,  // full value
          String(Math.round(field.confidence * 100) + '%'),
        ]);
      });
    });
    return rows.map(r =>
      r.map(cell => '"' + String(cell).replace(/"/g, '""') + '"').join(',')
    ).join('\n');
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    }, 100);
  }

  // ── Image Resize Observer ────────────────────────────────────
  // Keep overlay canvas aligned with image display size
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => {
      if ($imagePreview.style.display !== 'none') {
        resizeOverlayCanvas();
        if (currentResult && currentResult.ocr_boxes && activeTab === 'annotation') {
          drawOverlayBoxes(currentResult.ocr_boxes);
        }
      }
    });
    ro.observe($previewImg);
  }

  // Also handle window resize for canvas redraw
  window.addEventListener('resize', () => {
    if ($imagePreview.style.display !== 'none' && currentResult && activeTab === 'annotation') {
      resizeOverlayCanvas();
      drawOverlayBoxes(currentResult.ocr_boxes);
    }
  });

  // ── Init ─────────────────────────────────────────────────────
  checkHealth();
  // Periodic health check every 30 seconds
  setInterval(checkHealth, 30000);

})();
