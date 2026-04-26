const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileSelected = document.getElementById('fileSelected');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const fileRemove = document.getElementById('fileRemove');
const submitBtn = document.getElementById('submitBtn');
const statusBar = document.getElementById('statusBar');
const statusText = document.getElementById('statusText');
const resultCard = document.getElementById('resultCard');
const resultIcon = document.getElementById('resultIcon');
const resultTitle = document.getElementById('resultTitle');
const resultStats = document.getElementById('resultStats');
const downloadBtn = document.getElementById('downloadBtn');
const errorMessage = document.getElementById('errorMessage');

let selectedFile = null;

// ===== 拖拉上傳 =====
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length > 0) handleFileSelect(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFileSelect(e.target.files[0]);
});
fileRemove.addEventListener('click', () => {
    selectedFile = null;
    fileSelected.classList.remove('show');
    submitBtn.disabled = true;
    fileInput.value = '';
});

function handleFileSelect(file) {
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    fileSelected.classList.add('show');
    submitBtn.disabled = false;
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// ===== 提交稽核 =====
submitBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    submitBtn.disabled = true;
    submitBtn.classList.add('loading');
    submitBtn.querySelector('.btn-text').textContent = '稽核進行中...';
    statusBar.classList.add('show');
    resultCard.classList.remove('show');

    const steps = [
        '📤 上傳檔案中...', '🔍 解析套件清單...', '🌐 查詢 PyPI 資訊...',
        '🛡️ 掃描漏洞資料庫...', '📝 翻譯功能摘要...', '📊 生成稽核報告...',
    ];
    let stepIndex = 0;
    const stepInterval = setInterval(() => {
        if (stepIndex < steps.length) { statusText.textContent = steps[stepIndex]; stepIndex++; }
    }, 2000);

    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('python_version', document.getElementById('pythonVersion').value);
        const response = await fetch('/api/audit', { method: 'POST', body: formData });
        clearInterval(stepInterval);
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || `HTTP ${response.status}`);
        }
        const data = await response.json();
        showResult(data);
        loadHistory();
    } catch (err) {
        clearInterval(stepInterval);
        showError(err.message);
    } finally {
        submitBtn.disabled = false;
        submitBtn.classList.remove('loading');
        submitBtn.querySelector('.btn-text').textContent = '🚀 開始稽核';
        statusBar.classList.remove('show');
    }
});

function showResult(data) {
    resultCard.classList.add('show', 'success');
    resultCard.classList.remove('error');
    resultIcon.textContent = '✅';
    resultTitle.textContent = '稽核完成';
    resultStats.style.display = 'grid';
    errorMessage.style.display = 'none';
    downloadBtn.style.display = 'inline-flex';
    document.getElementById('statTotal').textContent = data.total_packages;
    document.getElementById('statSafe').textContent = data.total_packages - data.vuln_packages;
    document.getElementById('statSafe').className = 'stat-value safe';
    const vulnEl = document.getElementById('statVuln');
    vulnEl.textContent = data.vuln_packages;
    vulnEl.className = 'stat-value ' + (data.vuln_packages > 0 ? 'danger' : 'safe');
    downloadBtn.href = data.download_url;
}

function showError(message) {
    resultCard.classList.add('show', 'error');
    resultCard.classList.remove('success');
    resultIcon.textContent = '❌';
    resultTitle.textContent = '稽核失敗';
    resultStats.style.display = 'none';
    downloadBtn.style.display = 'none';
    errorMessage.style.display = 'block';
    errorMessage.textContent = message;
}

// ===== 歷史報告 =====
async function loadHistory() {
    const historyList = document.getElementById('historyList');
    try {
        const response = await fetch('/api/reports');
        const data = await response.json();
        if (data.reports.length === 0) {
            historyList.innerHTML = '<li class="history-empty">尚無歷史報告</li>';
            return;
        }
        historyList.innerHTML = data.reports.map(r => `
            <li class="history-item">
                <div class="history-item-info">
                    <span class="history-item-name">${r.filename}</span>
                    <span class="history-item-meta">${r.created} · ${formatBytes(r.size)}</span>
                </div>
                <a class="history-item-download" href="${r.download_url}" download>下載</a>
            </li>
        `).join('');
    } catch { historyList.innerHTML = '<li class="history-empty">載入失敗</li>'; }
}

loadHistory();
