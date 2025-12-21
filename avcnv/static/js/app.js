// 数据存储
let uploadedFiles = [];
let localFiles = [];
let outputFiles = [];
let convertQueue = [];
let currentTaskId = null;
let progressInterval = null;
let isConverting = false;
let isPaused = false;
let currentListSource = 'uploaded'; // 当前激活的文件列表
let uploadProgress = { active: false, remaining: 0 };
let pendingUploadFiles = [];
let pendingUploadStrategy = 'overwrite';
let deleteProgress = { active: false, remaining: 0, total: 0 };

// 文件排序状态（每个列表独立）
const sortState = {
    uploaded: { key: 'name', order: 'asc' },
    local: { key: 'name', order: 'asc' },
    output: { key: 'time', order: 'desc' } // 输出文件默认按时间倒序
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    initSortControls();
    initFolderTabs();
    loadAllFiles();
});

// 初始化事件
function initEventListeners() {
    document.getElementById('uploadBtn').addEventListener('click', () => {
        document.getElementById('fileInput').click();
    });
    document.getElementById('fileInput').addEventListener('change', handleFileUpload);
    document.getElementById('refreshBtn').addEventListener('click', loadAllFiles);
    document.getElementById('clearQueueBtn').addEventListener('click', clearQueue);
    document.getElementById('startConvertBtn').addEventListener('click', startConvert);
    document.getElementById('pauseBtn').addEventListener('click', pauseConvert);

    // 全选和添加选中按钮
    document.getElementById('selectAllUploadedBtn').addEventListener('click', () => selectAllFiles('uploaded'));
    document.getElementById('selectAllLocalBtn').addEventListener('click', () => selectAllFiles('local'));
    document.getElementById('selectAllOutputBtn').addEventListener('click', () => selectAllFiles('output'));
    document.getElementById('bulkDeleteUploadedBtn').addEventListener('click', () => bulkDeleteSelected('uploaded'));
    document.getElementById('bulkDeleteLocalBtn').addEventListener('click', () => bulkDeleteSelected('local'));
    document.getElementById('bulkDeleteOutputBtn').addEventListener('click', () => bulkDeleteSelected('output'));
    document.getElementById('addSelectedUploadedBtn').addEventListener('click', () => addSelectedToQueue('uploaded'));
    document.getElementById('addSelectedLocalBtn').addEventListener('click', () => addSelectedToQueue('local'));
    document.getElementById('downloadSelectedOutputBtn').addEventListener('click', () => downloadSelectedFiles('output'));
}

// 初始化排序控件（统一放在文件浏览器标题行）
function initSortControls() {
    const select = document.getElementById('browserSortSelect');
    const orderBtn = document.getElementById('browserSortOrderBtn');

    if (!select || !orderBtn) return;

    // 初始化 UI 与当前 tab 对齐
    updateSortControlsUI();

    select.addEventListener('change', (e) => {
        sortState[currentListSource].key = e.target.value;
        renderActiveList();
    });

    orderBtn.addEventListener('click', () => {
        const state = sortState[currentListSource];
        state.order = state.order === 'asc' ? 'desc' : 'asc';
        updateSortOrderButton(orderBtn, state.order);
        renderActiveList();
    });
}

function updateSortControlsUI() {
    const select = document.getElementById('browserSortSelect');
    const orderBtn = document.getElementById('browserSortOrderBtn');
    if (!select || !orderBtn) return;

    const state = sortState[currentListSource] || { key: 'name', order: 'asc' };
    select.value = state.key;
    updateSortOrderButton(orderBtn, state.order);
}

function startUploadProgress(total) {
    uploadProgress = { active: true, remaining: total };
    const indicator = document.getElementById('uploadProgressIndicator');
    const number = document.getElementById('uploadProgressNumber');
    if (indicator && number) {
        number.textContent = total;
        indicator.classList.remove('d-none');
    }
}

function stepUploadProgress() {
    if (!uploadProgress.active) return;
    uploadProgress.remaining = Math.max(0, uploadProgress.remaining - 1);
    const number = document.getElementById('uploadProgressNumber');
    if (number) {
        number.textContent = uploadProgress.remaining;
    }
}

function endUploadProgress() {
    uploadProgress.active = false;
    uploadProgress.remaining = 0;
    const indicator = document.getElementById('uploadProgressIndicator');
    const number = document.getElementById('uploadProgressNumber');
    if (number) number.textContent = 0;
    if (indicator) indicator.classList.add('d-none');
}

// 删除进度
function startDeleteProgress(total) {
    deleteProgress = { active: true, remaining: total, total };
    const indicator = document.getElementById('deleteProgressIndicator');
    const number = document.getElementById('deleteProgressNumber');
    if (indicator && number) {
        number.textContent = total;
        indicator.classList.remove('d-none');
    }
}

function stepDeleteProgress() {
    if (!deleteProgress.active) return;
    deleteProgress.remaining = Math.max(0, deleteProgress.remaining - 1);
    const number = document.getElementById('deleteProgressNumber');
    if (number) number.textContent = deleteProgress.remaining;
}

function endDeleteProgress() {
    deleteProgress = { active: false, remaining: 0, total: 0 };
    const indicator = document.getElementById('deleteProgressIndicator');
    const number = document.getElementById('deleteProgressNumber');
    if (number) number.textContent = 0;
    if (indicator) indicator.classList.add('d-none');
}

// 显示上传策略弹窗
function showUploadStrategyModal(total) {
    const modal = document.getElementById('uploadStrategyModal');
    const totalSpan = document.getElementById('uploadTotalCount');
    if (totalSpan) totalSpan.textContent = total;
    modal?.classList.add('show');
}

function closeUploadStrategyModal() {
    const modal = document.getElementById('uploadStrategyModal');
    modal?.classList.remove('show');
}

function getSelectedUploadStrategy() {
    const checked = document.querySelector('input[name="uploadStrategy"]:checked');
    return checked ? checked.value : 'overwrite';
}

async function confirmUploadStrategy() {
    if (!pendingUploadFiles || pendingUploadFiles.length === 0) {
        closeUploadStrategyModal();
        return;
    }

    pendingUploadStrategy = getSelectedUploadStrategy();
    closeUploadStrategyModal();
    await startUploadWithStrategy();
}

async function startUploadWithStrategy() {
    if (!pendingUploadFiles || pendingUploadFiles.length === 0) return;

    startUploadProgress(pendingUploadFiles.length);

    try {
        for (const file of pendingUploadFiles) {
            const formData = new FormData();
            formData.append('file', file);

            await fetch(`/api/upload?strategy=${pendingUploadStrategy}`, {
                method: 'POST',
                body: formData
            });

            stepUploadProgress();
        }

        await loadUploadedFiles();
    } catch (err) {
        alert('上传失败: ' + err.message);
    } finally {
        endUploadProgress();
        pendingUploadFiles = [];
    }
}

function renderActiveList() {
    if (currentListSource === 'uploaded') {
        renderUploadedFiles();
    } else if (currentListSource === 'local') {
        renderLocalFiles();
    } else if (currentListSource === 'output') {
        renderOutputFiles();
    }
}

function updateSortOrderButton(btn, order) {
    if (!btn) return;
    btn.dataset.order = order;
    btn.innerHTML = order === 'asc'
        ? '<i class="bi bi-sort-up"></i>'
        : '<i class="bi bi-sort-down"></i>';
    btn.title = order === 'asc' ? '升序' : '降序';
}

function getFileExtension(file) {
    const name = file?.filename || '';
    const parts = name.split('.');
    return parts.length > 1 ? parts.pop().toLowerCase() : '';
}

function sortFiles(files, source) {
    const { key, order } = sortState[source] || { key: 'name', order: 'asc' };
    const factor = order === 'asc' ? 1 : -1;

    return [...files].sort((a, b) => {
        switch (key) {
            case 'time':
                return ((a.last_modified || 0) - (b.last_modified || 0)) * factor;
            case 'size':
                return ((a.size || 0) - (b.size || 0)) * factor;
            case 'type':
                return getFileExtension(a).localeCompare(getFileExtension(b), 'zh-CN') * factor;
            case 'name':
            default:
                return (a.filename || '').localeCompare(b.filename || '', 'zh-CN') * factor;
        }
    });
}

function initFolderTabs() {
    const tabs = document.querySelectorAll('.folder-tab');
    const sections = document.querySelectorAll('.folder-section');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.getAttribute('data-target');
            if (!targetId) return;

            // 切换标签页激活状态
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // 切换内容区激活状态
            sections.forEach(section => {
                section.classList.toggle('active', section.id === targetId);
            });

            // 记录当前列表来源并同步排序控件 UI
            if (targetId === 'uploadedSection') {
                currentListSource = 'uploaded';
            } else if (targetId === 'localSection') {
                currentListSource = 'local';
            } else if (targetId === 'outputSection') {
                currentListSource = 'output';
            }
            updateSortControlsUI();
        });
    });
}

// 加载所有文件
async function loadAllFiles() {
    await Promise.all([loadUploadedFiles(), loadLocalFiles(), loadOutputFiles()]);
}

// 加载已上传文件
async function loadUploadedFiles() {
    try {
        const res = await fetch('/api/uploaded-files');
        uploadedFiles = await res.json();
        renderUploadedFiles();
    } catch (err) {
        console.error('加载已上传文件失败', err);
    }
}

// 加载本地文件
async function loadLocalFiles() {
    try {
        const res = await fetch('/api/local-files');
        localFiles = await res.json();
        renderLocalFiles();
    } catch (err) {
        console.error('加载本地文件失败:', err);
    }
}

// 渲染已上传文件
function renderUploadedFiles() {
    const container = document.getElementById('uploadedFilesList');
    const count = document.getElementById('uploadedCount');

    count.textContent = uploadedFiles.length;

    if (uploadedFiles.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无文件</div>';
        return;
    }

    const sortedFiles = sortFiles(uploadedFiles, 'uploaded');
    container.innerHTML = sortedFiles.map(file => createFileItemHTML(file, 'upload')).join('');
}

// 渲染本地文件
function renderLocalFiles() {
    const container = document.getElementById('localFilesList');
    const count = document.getElementById('localCount');

    count.textContent = localFiles.length;

    if (localFiles.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无文件</div>';
        return;
    }

    const sortedFiles = sortFiles(localFiles, 'local');
    container.innerHTML = sortedFiles.map(file => createFileItemHTML(file, 'local')).join('');
}

// 加载输出文件
async function loadOutputFiles() {
    try {
        const res = await fetch('/api/output-files');
        outputFiles = await res.json();
        renderOutputFiles();
    } catch (err) {
        console.error('加载输出文件失败:', err);
    }
}

// 渲染输出文件
function renderOutputFiles() {
    const container = document.getElementById('outputFilesList');
    const count = document.getElementById('outputCount');

    count.textContent = outputFiles.length;

    if (outputFiles.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无文件</div>';
        return;
    }

    const sortedFiles = sortFiles(outputFiles, 'output');
    container.innerHTML = sortedFiles.map(file => createFileItemHTML(file, 'output')).join('');
    attachFileItemEvents(container);

    if (currentListSource === 'output') {
        updateSortControlsUI();
    }
}

// 创建文件项HTML
function createFileItemHTML(file, source) {
    const iconType = file.media_type === 'audio' ? 'music-note-beamed' : 'camera-video';
    return `
        <div class="file-item" data-filename="${escapeHTML(file.filename)}" data-source="${source}">
            <input type="checkbox" class="file-checkbox">
            <i class="bi bi-${iconType}"></i>
            <span class="file-name" title="${escapeHTML(file.filename)}">${escapeHTML(file.filename)}</span>
            <div class="file-actions">
                <button class="file-action-btn delete" title="删除文件">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    `;
}

// 渲染完成后添加事件
function renderUploadedFiles() {
    const container = document.getElementById('uploadedFilesList');
    const count = document.getElementById('uploadedCount');

    count.textContent = uploadedFiles.length;

    if (uploadedFiles.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无文件</div>';
        return;
    }

    const sortedFiles = sortFiles(uploadedFiles, 'uploaded');
    container.innerHTML = sortedFiles.map(file => createFileItemHTML(file, 'upload')).join('');
    attachFileItemEvents(container);

    if (currentListSource === 'uploaded') {
        updateSortControlsUI();
    }
}

function renderLocalFiles() {
    const container = document.getElementById('localFilesList');
    const count = document.getElementById('localCount');

    count.textContent = localFiles.length;

    if (localFiles.length === 0) {
        container.innerHTML = '<div class="empty-hint">暂无文件</div>';
        return;
    }

    const sortedFiles = sortFiles(localFiles, 'local');
    container.innerHTML = sortedFiles.map(file => createFileItemHTML(file, 'local')).join('');
    attachFileItemEvents(container);

    if (currentListSource === 'local') {
        updateSortControlsUI();
    }
}

// 附加文件项事件
function attachFileItemEvents(container) {
    container.querySelectorAll('.file-item').forEach(item => {
        const filename = item.dataset.filename;
        const source = item.dataset.source;

        item.querySelector('.add')?.addEventListener('click', (e) => {
            e.stopPropagation();
            addToQueue(filename, source);
        });

        item.querySelector('.delete')?.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteFile(filename, source);
        });

        item.addEventListener('click', () => {
            addToQueue(filename, source);
        });
    });
}

// 添加到队列
function addToQueue(filename, source) {
    if (convertQueue.find(item => item.filename === filename && item.source === source)) {
        return;
    }

    let fileInfo;
    if (source === 'upload') {
        fileInfo = uploadedFiles.find(f => f.filename === filename);
    } else if (source === 'local') {
        fileInfo = localFiles.find(f => f.filename === filename);
    } else if (source === 'output') {
        fileInfo = outputFiles.find(f => f.filename === filename);
    }

    if (!fileInfo) return;

    convertQueue.push({
        filename,
        source,
        type: fileInfo.media_type,
        size: fileInfo.size  // 添加文件大小
    });

    // 智能选择输出格式
    updateDefaultFormat();

    // 检查格式一致性
    checkFormatConsistency();

    renderQueue();
}

// 智能选择默认输出格式
function updateDefaultFormat() {
    if (convertQueue.length === 0) return;

    // 获取队列中第一个文件的类型
    const firstFileType = convertQueue[0].type;

    // 根据文件类型选择默认格式
    let defaultFormat = 'mp4';
    if (firstFileType === 'audio') {
        defaultFormat = 'mp3';
    } else if (firstFileType === 'video') {
        defaultFormat = 'mkv';
    }

    // 设置默认选中的格式
    const formatRadio = document.getElementById(`fmt-${defaultFormat}`);
    if (formatRadio) {
        formatRadio.checked = true;
    }

    // 更新高级选项显示
    updateAdvancedOptions(firstFileType);
}

// 更新高级选项显示（根据文件类型）
function updateAdvancedOptions(fileType) {
    const videoOptions = document.getElementById('videoOptions');
    const audioOptions = document.getElementById('audioOptions');

    if (fileType === 'video') {
        // 显示视频选项，隐藏音频选项
        videoOptions.style.display = 'block';
        audioOptions.style.display = 'none';
    } else if (fileType === 'audio') {
        // 显示音频选项，隐藏视频选项
        videoOptions.style.display = 'none';
        audioOptions.style.display = 'block';
    } else {
        // 都隐藏
        videoOptions.style.display = 'none';
        audioOptions.style.display = 'none';
    }
}

// 检查队列中文件格式是否一致
function checkFormatConsistency() {
    const queueFooter = document.querySelector('.queue-footer .queue-info');
    const startBtn = document.getElementById('startConvertBtn');

    if (convertQueue.length === 0) {
        // 队列为空，移除警告
        const existingWarning = document.getElementById('formatWarning');
        if (existingWarning) existingWarning.remove();
        startBtn.disabled = true;
        return;
    }

    // 检查是否所有文件类型一致
    const firstType = convertQueue[0].type;
    const allSameType = convertQueue.every(item => item.type === firstType);

    // 移除旧的警告（如果存在）
    const existingWarning = document.getElementById('formatWarning');
    if (existingWarning) existingWarning.remove();

    if (!allSameType) {
        // 格式不一致，显示警告并禁用按钮
        const warning = document.createElement('span');
        warning.id = 'formatWarning';
        warning.style.color = '#dc3545';
        warning.style.fontWeight = '600';
        warning.style.marginLeft = '1rem';
        warning.innerHTML = '<i class="bi bi-exclamation-triangle"></i> 队列中文件有多种格式，请保持格式一致才能进行批量处理';
        queueFooter.appendChild(warning);

        startBtn.disabled = true;
    } else {
        // 格式一致，检查是否有待处理的文件
        const hasPendingFiles = convertQueue.some(item => !item.status || item.status === 'pending');

        // 只有在不处于转换中且有待处理文件时才启用按钮
        if (!isConverting && hasPendingFiles) {
            startBtn.disabled = false;
        } else {
            startBtn.disabled = true;
        }
    }
}

// 格式化文件大小为MB
function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '-';
    const mb = bytes / (1024 * 1024);
    return mb.toFixed(2) + ' MB';
}

// 渲染队列
function renderQueue(taskData = null) {
    const container = document.getElementById('queueContent');
    const count = document.getElementById('queueCount');
    const clearBtn = document.getElementById('clearQueueBtn');
    const startBtn = document.getElementById('startConvertBtn');

    count.textContent = convertQueue.length;
    clearBtn.disabled = convertQueue.length === 0 || isConverting;

    // 不在这里直接设置 startBtn.disabled，由 checkFormatConsistency 统一管理
    // startBtn.disabled = convertQueue.length === 0 || isConverting;

    if (convertQueue.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="bi bi-inbox"></i><p>从左侧点击文件添加到队列</p></div>';

        // 队列为空时移除警告
        const existingWarning = document.getElementById('formatWarning');
        if (existingWarning) existingWarning.remove();

        startBtn.disabled = true;
        return;
    }

    // 检查格式一致性（确保警告状态正确）
    checkFormatConsistency();

    // 构建表格
    const tableRows = convertQueue.map((item, idx) => {
        // 优先使用 convertQueue 中已同步的状态和进度
        // 如果 item 有 status 和 progress 属性,说明已经同步过
        let status = item.status || 'pending';
        let progress = item.progress || 0;
        let outputSize = item.output_size || null;

        // 如果有 taskData,且 item 没有 status,则从 taskData 查找
        if (taskData && taskData.files && !item.status) {
            const fileData = taskData.files.find(f => f.filename === item.filename);
            if (fileData) {
                status = fileData.status;
                progress = fileData.progress;
                outputSize = fileData.output_size;
            }
        }

        // 原文件大小
        const inputSizeText = formatFileSize(item.size);

        // 输出文件大小
        const outputSizeText = status === 'completed' && outputSize
            ? formatFileSize(outputSize)
            : '-';

        // 构建状态列显示
        const statusHTML = `
            <div class="queue-item-status-col">
                <span class="queue-item-status status-${status}">${statusText(status)}</span>
                <div class="progress">
                    <div class="progress-bar bg-${getProgressColor(status)}"
                         style="width: ${progress}%">${Math.round(progress)}%</div>
                </div>
            </div>
        `;

        return `
            <tr data-idx="${idx}">
                <td class="col-filename">
                    <div class="queue-item-name">
                        <div class="queue-item-icon">
                            <i class="bi bi-${item.type === 'audio' ? 'music-note' : 'camera-video'}"></i>
                        </div>
                        <div style="flex: 1; min-width: 0;">
                            <div title="${escapeHTML(item.filename)}" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                ${escapeHTML(item.filename)}
                            </div>
                            <div style="font-size: 0.7rem; color: #6c757d; margin-top: 2px;">
                                ${inputSizeText}
                            </div>
                        </div>
                    </div>
                </td>
                <td class="col-status">
                    ${statusHTML}
                </td>
                <td class="col-actions">
                    <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
                        <div style="font-size: 0.7rem; color: #6c757d; min-height: 16px;">
                            ${outputSizeText !== '-' ? outputSizeText : ''}
                        </div>
                        <div>
                            ${status === 'completed'
                                ? '<button class="btn btn-sm btn-success queue-item-download" data-idx="' + idx + '"><i class="bi bi-download"></i> 下载</button>'
                                : ''
                            }
                            ${!isConverting
                                ? '<button class="btn btn-sm btn-outline-danger queue-item-remove" data-idx="' + idx + '">删除</button>'
                                : ''
                            }
                        </div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <table class="queue-table">
            <thead>
                <tr>
                    <th class="col-filename">文件名</th>
                    <th class="col-status">转换状态</th>
                    <th class="col-actions">操作</th>
                </tr>
            </thead>
            <tbody>
                ${tableRows}
            </tbody>
        </table>
    `;

    // 添加移除事件监听
    if (!isConverting) {
        container.querySelectorAll('.queue-item-remove').forEach((btn) => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.getAttribute('data-idx'));
                removeFromQueue(idx);
            });
        });
    }

    // 添加下载事件监听
    container.querySelectorAll('.queue-item-download').forEach((btn) => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.getAttribute('data-idx'));
            downloadFile(idx);
        });
    });
}

function getProgressColor(status) {
    const colorMap = {
        pending: 'secondary',
        processing: 'info',
        completed: 'success',
        failed: 'danger'
    };
    return colorMap[status] || 'secondary';
}

// 从队列移除
function removeFromQueue(idx) {
    convertQueue.splice(idx, 1);

    // 重新检查格式一致性
    checkFormatConsistency();

    // 如果队列不为空，更新默认格式
    if (convertQueue.length > 0) {
        updateDefaultFormat();
    }

    renderQueue();
}

// 下载文件
function downloadFile(idx) {
    const item = convertQueue[idx];
    if (!item || item.status !== 'completed') {
        return;
    }

    // 从output_file路径中提取相对于outputs目录的路径
    // output_file格式类似: "H:\音视频转换\outputs\001仙逆\001仙逆 第0001章 离乡.mp4"
    // 需要提取outputs后面的部分
    let filename = item.filename;

    // 如果item有output_file且已转换完成，从output_file中提取文件名
    if (item.output_file) {
        const outputPath = item.output_file;
        const outputsIndex = outputPath.indexOf('outputs');
        if (outputsIndex !== -1) {
            // 提取outputs/之后的路径
            filename = outputPath.substring(outputsIndex + 8).replace(/\\/g, '/');
        }
    } else {
        // 如果没有output_file，从文件名推断
        // 将扩展名替换为转换后的格式
        const format = document.querySelector('input[name="format"]:checked')?.value || 'mp4';
        const nameParts = filename.split('.');
        nameParts[nameParts.length - 1] = format;
        filename = nameParts.join('.');
    }

    // 构建下载URL
    const downloadUrl = `/api/download/${encodeURIComponent(filename)}`;

    // 创建隐藏的a标签触发下载
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = filename.split('/').pop(); // 只取文件名部分
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// 清空队列
function clearQueue() {
    if (confirm('确定清空队列?')) {
        convertQueue = [];

        // 移除格式警告
        const existingWarning = document.getElementById('formatWarning');
        if (existingWarning) existingWarning.remove();

        renderQueue();
    }
}

// 文件上传
async function handleFileUpload(e) {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    pendingUploadFiles = files;
    showUploadStrategyModal(files.length);

    // 清空 input 以便下次选择同样文件
    e.target.value = '';
}

// 删除文件
async function deleteFile(filename, source) {
    if (!confirm(`确定删除文件 "${filename}"?`)) return;

    startDeleteProgress(1);

    try {
        await fetch(`/api/cleanup/${encodeURIComponent(filename)}?source=${source}`, { method: 'DELETE' });
        alert('删除成功');

        if (source === 'upload') {
            await loadUploadedFiles();
        } else if (source === 'local') {
            await loadLocalFiles();
        } else if (source === 'output') {
            await loadOutputFiles();
        }

        convertQueue = convertQueue.filter(item => !(item.filename === filename && item.source === source));
        renderQueue();
    } catch (err) {
        alert('删除失败: ' + err.message);
    } finally {
        stepDeleteProgress();
        endDeleteProgress();
    }
}

// 开始转换
async function startConvert() {
    // 如果当前处于暂停状态，则执行继续操作
    if (isPaused && currentTaskId) {
        await pauseConvert(); // 暂停按钮在isPaused=true时会执行继续操作
        return;
    }

    const format = document.querySelector('input[name="format"]:checked').value;

    // 判断当前队列的文件类型
    const fileType = convertQueue.length > 0 ? convertQueue[0].type : null;

    // 根据文件类型读取相应的高级选项
    let advancedOptions = {};

    if (fileType === 'video') {
        // 视频选项
        advancedOptions = {
            video_codec: document.getElementById('videoCodec').value || null,
            resolution: document.getElementById('resolution').value || null,
            video_bitrate: document.getElementById('videoBitrate').value || null,
            frame_rate: document.getElementById('frameRate').value || null,
            audio_bitrate: document.getElementById('videoAudioBitrate').value || null
        };
    } else if (fileType === 'audio') {
        // 音频选项
        advancedOptions = {
            audio_codec: document.getElementById('audioCodec').value || null,
            audio_bitrate: document.getElementById('audioBitrate').value || null,
            sample_rate: document.getElementById('sampleRate').value || null,
            audio_channels: document.getElementById('audioChannels').value || null,
            volume_adjust: document.getElementById('volumeAdjust').value || null
        };
    }

    // 按来源分组文件，只包含待处理的文件（排除已完成和失败的文件）
    const groups = { upload: [], local: [], output: [] };
    convertQueue.forEach(item => {
        // 只添加 pending 状态的文件，跳过 completed 和 failed 状态的文件
        if (!item.status || item.status === 'pending') {
            groups[item.source].push(item.filename);
        }
    });

    // 检查是否有待处理的文件（这里不需要弹窗，因为按钮已被禁用）
    const totalPendingFiles = groups.upload.length + groups.local.length + groups.output.length;
    if (totalPendingFiles === 0) {
        // 按钮应该已经被禁用，直接返回
        return;
    }

    try {
        isConverting = true;
        isPaused = false;  // 确保暂停状态被重置
        document.getElementById('startConvertBtn').disabled = true;
        document.getElementById('pauseBtn').disabled = false;
        document.getElementById('overallProgressText').style.display = 'inline';

        // 处理所有分组的转换任务
        for (const [source, files] of Object.entries(groups)) {
            if (files.length === 0) continue;

            const requestBody = {
                files,
                source,
                output_format: format,
                ...advancedOptions
            };

            const res = await fetch('/api/convert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            const data = await res.json();
            currentTaskId = data.task_id;

            // 开始轮询并等待当前任务完成
            const result = await pollTaskProgress(currentTaskId);

            // 如果被停止了，直接退出
            if (result && result.stopped) {
                break;
            }
        }

        // 所有任务完成（只有正常完成才显示提示）
        if (isConverting) {
            isConverting = false;
            document.getElementById('startConvertBtn').disabled = false;
            document.getElementById('pauseBtn').disabled = true;
            document.getElementById('overallProgressText').style.display = 'none';

            // 检查是否所有文件都已完成
            const status = await fetch(`/api/status/${currentTaskId}`);
            const statusData = await status.json();

            const allCompleted = statusData.files.every(f => f.status === 'completed' || f.status === 'failed');

            if (allCompleted) {
                // 全部完成，不弹出对话框，不清空队列，保持显示转换结果
                console.log('所有转换任务已完成');
                renderQueue();
            } else {
                // 部分完成（被暂停），不清空队列
                renderQueue();
            }
        }

    } catch (err) {
        alert('转换失败: ' + err.message);
        isConverting = false;
        document.getElementById('startConvertBtn').disabled = false;
        document.getElementById('pauseBtn').disabled = true;
    }
}

// 轮询单个任务进度（返回 Promise）
function pollTaskProgress(taskId) {
    return new Promise((resolve, reject) => {
        const interval = setInterval(async () => {
            // 检查是否已停止
            if (!isConverting) {
                clearInterval(interval);
                resolve({ stopped: true });
                return;
            }

            // 暂停时不轮询
            if (isPaused) return;

            try {
                const res = await fetch(`/api/status/${taskId}`);
                const data = await res.json();

                // 更新总体进度显示
                document.getElementById('overallProgressValue').textContent = Math.round(data.overall_progress) + '%';

                // 同步服务器状态到 convertQueue
                if (data && data.files) {
                    data.files.forEach(serverFile => {
                        const queueItem = convertQueue.find(item => item.filename === serverFile.filename);
                        if (queueItem) {
                            queueItem.status = serverFile.status;
                            queueItem.progress = serverFile.progress;
                            queueItem.output_file = serverFile.output_file;  // 保存输出文件路径
                            queueItem.output_size = serverFile.output_size;  // 保存输出文件大小
                        }
                    });
                }

                // 更新队列显示（带进度）
                renderQueue(data);

                // 检查是否所有文件都已完成
                if (data.files.every(f => f.status === 'completed' || f.status === 'failed')) {
                    clearInterval(interval);
                    // 刷新输出文件列表
                    await loadOutputFiles();
                    resolve(data);
                }
            } catch (err) {
                console.error('更新进度失败:', err);
                clearInterval(interval);
                reject(err);
            }
        }, 500); // 每 500ms 轮询一次
    });
}

// 暂停/继续转换
async function pauseConvert() {
    // 如果当前是已暂停状态，则执行继续操作
    if (isPaused) {
        if (!currentTaskId) return;

        try {
            // 调用恢复API继续执行任务，发送当前队列的文件列表
            const currentFilenames = convertQueue.map(item => item.filename);
            console.log('发送当前队列文件到后端:', currentFilenames);

            const res = await fetch(`/api/resume/${currentTaskId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ filenames: currentFilenames })
            });
            const data = await res.json();

            // 重置按钮为暂停状态
            const pauseBtn = document.getElementById('pauseBtn');
            pauseBtn.innerHTML = '<i class="bi bi-pause-circle"></i> 暂停';
            pauseBtn.classList.remove('btn-outline-success');
            pauseBtn.classList.add('btn-outline-warning');

            isPaused = false;
            isConverting = true;
            document.getElementById('startConvertBtn').disabled = true;
            document.getElementById('pauseBtn').disabled = false;
            document.getElementById('overallProgressText').style.display = 'inline';

            // 开始轮询任务进度
            await pollTaskProgress(currentTaskId);

            // 任务完成后的处理 - 检查是否所有文件都已完成
            const status = await fetch(`/api/status/${currentTaskId}`);
            const statusData = await status.json();

            const allCompleted = statusData.files.every(f => f.status === 'completed' || f.status === 'failed');

            if (allCompleted) {
                // 全部完成,重置状态
                isConverting = false;
                isPaused = false;
                document.getElementById('startConvertBtn').disabled = false;
                document.getElementById('pauseBtn').disabled = true;
                document.getElementById('overallProgressText').style.display = 'none';

                // 不弹出对话框，不清空队列，保持显示转换结果
                console.log('所有转换任务已完成');
            } else {
                // 未全部完成(被暂停),保持暂停状态
                isConverting = false;
                isPaused = true;

                // 暂停按钮变成继续按钮
                const pauseBtn = document.getElementById('pauseBtn');
                pauseBtn.innerHTML = '<i class="bi bi-play-circle"></i> 继续';
                pauseBtn.classList.remove('btn-outline-warning');
                pauseBtn.classList.add('btn-outline-success');
                pauseBtn.disabled = false;  // 确保按钮可用

                document.getElementById('overallProgressText').style.display = 'none';
                renderQueue(statusData);
            }

        } catch (err) {
            console.error('继续转换失败:', err);
            alert('继续转换失败: ' + err.message);
        }
        return;
    }

    // 执行暂停操作
    if (!currentTaskId) return;

    try {
        console.log('暂停转换，当前task_id:', currentTaskId);

        // 调用暂停API - 会终止FFmpeg进程并重置正在处理的文件
        await fetch(`/api/pause/${currentTaskId}`, { method: 'POST' });

        isConverting = false;
        isPaused = true;  // 标记为已暂停状态

        if (progressInterval) {
            clearInterval(progressInterval);
        }

        // 暂停按钮变成继续按钮
        const pauseBtn = document.getElementById('pauseBtn');
        pauseBtn.innerHTML = '<i class="bi bi-play-circle"></i> 继续';
        pauseBtn.classList.remove('btn-outline-warning');
        pauseBtn.classList.add('btn-outline-success');

        document.getElementById('overallProgressText').style.display = 'none';

        // 从服务器获取最新状态并重新渲染队列
        const status = await fetch(`/api/status/${currentTaskId}`);
        const statusData = await status.json();

        console.log('暂停后获取到的状态:', statusData);
        console.log('当前convertQueue:', convertQueue);

        // 重要：将服务器返回的文件状态同步到 convertQueue
        // 确保 convertQueue 中的文件与服务器状态保持一致
        if (statusData && statusData.files) {
            statusData.files.forEach(serverFile => {
                const queueItem = convertQueue.find(item => item.filename === serverFile.filename);
                if (queueItem) {
                    // 同步状态和进度到队列项
                    queueItem.status = serverFile.status;
                    queueItem.progress = serverFile.progress;
                    queueItem.output_file = serverFile.output_file;  // 保存输出文件路径
                    queueItem.output_size = serverFile.output_size;  // 保存输出文件大小
                }
            });
        }

        renderQueue(statusData);

    } catch (err) {
        console.error('暂停失败:', err);
        alert('暂停失败: ' + err.message);
    }
}

function statusText(status) {
    const map = { pending: '等待', processing: '处理中', completed: '完成', failed: '失败' };
    return map[status] || status;
}

function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// 全选文件
function selectAllFiles(type) {
    let containerId;
    if (type === 'uploaded') {
        containerId = 'uploadedFilesList';
    } else if (type === 'local') {
        containerId = 'localFilesList';
    } else if (type === 'output') {
        containerId = 'outputFilesList';
    }

    const checkboxes = document.querySelectorAll(`#${containerId} .file-checkbox`);
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);

    checkboxes.forEach(cb => {
        cb.checked = !allChecked;
    });

    updateSelectedButtons(type);
}

// 添加选中的文件到队列
function addSelectedToQueue(type) {
    let containerId, source, fileArray;

    if (type === 'uploaded') {
        containerId = 'uploadedFilesList';
        source = 'upload';
        fileArray = uploadedFiles;
    } else if (type === 'local') {
        containerId = 'localFilesList';
        source = 'local';
        fileArray = localFiles;
    } else if (type === 'output') {
        containerId = 'outputFilesList';
        source = 'output';
        fileArray = outputFiles;
    }

    const checkedItems = document.querySelectorAll(`#${containerId} .file-checkbox:checked`);

    checkedItems.forEach(checkbox => {
        const fileItem = checkbox.closest('.file-item');
        const filename = fileItem.dataset.filename;
        const fileInfo = fileArray.find(f => f.filename === filename);

        if (fileInfo && !convertQueue.find(item => item.filename === filename && item.source === source)) {
            convertQueue.push({
                filename,
                source,
                type: fileInfo.media_type,
                size: fileInfo.size  // 添加文件大小
            });
        }

        checkbox.checked = false;
    });

    // 智能选择输出格式
    updateDefaultFormat();

    // 检查格式一致性
    checkFormatConsistency();

    renderQueue();
    updateSelectedButtons(type);
}

// 批量删除选中的文件
async function bulkDeleteSelected(type) {
    let containerId, source, reloadFn;

    if (type === 'uploaded') {
        containerId = 'uploadedFilesList';
        source = 'upload';
        reloadFn = loadUploadedFiles;
    } else if (type === 'local') {
        containerId = 'localFilesList';
        source = 'local';
        reloadFn = loadLocalFiles;
    } else if (type === 'output') {
        containerId = 'outputFilesList';
        source = 'output';
        reloadFn = loadOutputFiles;
    } else {
        return;
    }

    const checkedItems = document.querySelectorAll(`#${containerId} .file-checkbox:checked`);
    if (checkedItems.length === 0) return;

    const filenames = Array.from(checkedItems).map(cb => cb.closest('.file-item').dataset.filename);

    if (!confirm(`确认删除选中的 ${filenames.length} 个文件吗？`)) return;

    try {
        startDeleteProgress(filenames.length);

        for (const name of filenames) {
            await fetch(`/api/cleanup/${encodeURIComponent(name)}?source=${source}`, { method: 'DELETE' });
            // 同步移除队列中的条目
            convertQueue = convertQueue.filter(item => !(item.filename === name && item.source === source));
            stepDeleteProgress();
        }

        await reloadFn();
        renderQueue();
    } catch (err) {
        alert('删除失败: ' + err.message);
    } finally {
        endDeleteProgress();
        checkedItems.forEach(cb => cb.checked = false);
        updateSelectedButtons(type);
    }
}

// 更新选中按钮状态
function updateSelectedButtons(type) {
    let containerId, btnId;

    if (type === 'uploaded') {
        containerId = 'uploadedFilesList';
        btnId = 'addSelectedUploadedBtn';
    } else if (type === 'local') {
        containerId = 'localFilesList';
        btnId = 'addSelectedLocalBtn';
    } else if (type === 'output') {
        containerId = 'outputFilesList';
        btnId = 'downloadSelectedOutputBtn';
    }

    const selectedCount = document.querySelectorAll(`#${containerId} .file-checkbox:checked`).length;

    document.getElementById(btnId).disabled = selectedCount === 0;

    // 控制批量删除按钮
    if (type === 'uploaded') {
        document.getElementById('bulkDeleteUploadedBtn').disabled = selectedCount === 0;
    } else if (type === 'local') {
        document.getElementById('bulkDeleteLocalBtn').disabled = selectedCount === 0;
    } else if (type === 'output') {
        document.getElementById('bulkDeleteOutputBtn').disabled = selectedCount === 0;
    }
}

// 下载选中的输出文件
function downloadSelectedFiles(type) {
    if (type !== 'output') return;

    const containerId = 'outputFilesList';
    const checkedItems = document.querySelectorAll(`#${containerId} .file-checkbox:checked`);

    checkedItems.forEach(checkbox => {
        const fileItem = checkbox.closest('.file-item');
        const filename = fileItem.dataset.filename;

        // 构建下载URL
        const downloadUrl = `/api/download/${encodeURIComponent(filename)}`;

        // 创建隐藏的a标签触发下载
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename.split('/').pop(); // 只取文件名部分
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        // 取消选中
        checkbox.checked = false;
    });

    updateSelectedButtons(type);
}

// 修改附加文件项事件函数，添加复选框监听
function attachFileItemEvents(container) {
    let containerType;
    if (container.id === 'uploadedFilesList') {
        containerType = 'uploaded';
    } else if (container.id === 'localFilesList') {
        containerType = 'local';
    } else if (container.id === 'outputFilesList') {
        containerType = 'output';
    }

    container.querySelectorAll('.file-item').forEach(item => {
        const filename = item.dataset.filename;
        const source = item.dataset.source;

        // 复选框变化事件
        const checkbox = item.querySelector('.file-checkbox');
        checkbox?.addEventListener('change', () => {
            updateSelectedButtons(containerType);
        });

        // 删除按钮事件
        item.querySelector('.delete')?.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteFile(filename, source);
        });

        // 点击文件项（排除复选框和按钮）添加到队列
        item.addEventListener('click', (e) => {
            if (e.target !== checkbox && e.target.tagName !== 'BUTTON' && e.target.tagName !== 'I') {
                addToQueue(filename, source);
            }
        });
    });
}
