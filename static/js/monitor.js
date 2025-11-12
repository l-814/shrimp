const rowsPerPage = 8;
let currentPage = 1;
let allResults = [];

const poolSelect = document.getElementById("poolSelect");
const eventSelect = document.getElementById("oddSelect");
const alertsTbody = document.getElementById("alerts-tbody");
const prevBtn = document.getElementById("prevPage");
const nextBtn = document.getElementById("nextPage");
const pageInfo = document.getElementById("pageInfo");
const queryForm = document.getElementById("queryForm");

async function fetchAlerts() {
    const pool = poolSelect.value;
    const event = eventSelect.value;

    try {
        const res = await fetch(`/api/alerts?pool=${encodeURIComponent(pool)}&event=${encodeURIComponent(event)}`);
        if (!res.ok) throw new Error(`API 請求失敗: ${res.status}`);

        allResults = await res.json();
        currentPage = 1;
        renderTable(currentPage);

    } catch (err) {
        alertsTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:red;">錯誤: ${err.message}</td></tr>`;
        pageInfo.textContent = "";
        prevBtn.disabled = true;
        nextBtn.disabled = true;
    }
}

function formatTimeString(value) {
    return value ? value : '-';
}

function updateCachedAlert(alertId, changes) {
    allResults = allResults.map(item => {
        if (item.id === alertId) {
            return Object.assign({}, item, changes);
        }
        return item;
    });
}

function createStatusButton(alert) {
    const button = document.createElement('button');
    button.className = 'action-btn status-btn';
    button.textContent = alert.status;
    if (alert.status === '已處理') {
        button.disabled = true;
        return button;
    }
    button.addEventListener('click', () => handleStatusUpdate(alert.id, button));
    return button;
}

function createNotifyButton(alert) {
    const button = document.createElement('button');
    button.className = 'action-btn notify-btn';
    button.textContent = alert.notify_count > 0 ? '重新通知' : '未通知';
    button.addEventListener('click', () => handleManualNotify(alert.id, button));
    return button;
}

async function fetchJsonWithFallback(url, options = {}) {
    const mergedOptions = Object.assign({ credentials: 'same-origin' }, options);
    const response = await fetch(url, mergedOptions);
    const rawText = await response.text();

    let parsed;
    try {
        parsed = rawText ? JSON.parse(rawText) : {};
    } catch (err) {
        const snippet = rawText ? rawText.substring(0, 120) : '（無內容）';
        throw new Error(`伺服器回傳非 JSON（HTTP ${response.status}）：${snippet}`);
    }

    return { response, data: parsed };
}

async function handleStatusUpdate(alertId, button) {
    if (!confirm('是否確認已處理？')) {
        return;
    }
    button.disabled = true;
    try {
        const { response, data } = await fetchJsonWithFallback(`/api/alerts/${alertId}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok || !data.success) {
            throw new Error(data.message || '狀態更新失敗');
        }
        updateCachedAlert(alertId, { status: data.status });
        renderTable(currentPage);
    } catch (error) {
        alert(error.message);
        button.disabled = false;
    }
}

async function handleManualNotify(alertId, button) {
    button.disabled = true;
    try {
        const { response, data } = await fetchJsonWithFallback(`/api/alerts/${alertId}/notify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok || !data.success) {
            throw new Error(data.message || '通知失敗');
        }
        updateCachedAlert(alertId, {
            notified: true,
            notified_at: data.notified_at,
            notify_count: data.notify_count || 1
        });
        renderTable(currentPage);
    } catch (error) {
        alert(error.message);
        button.disabled = false;
    }
}

function renderTable(page) {
    alertsTbody.innerHTML = "";

    if (allResults.length === 0) {
        alertsTbody.innerHTML = `<tr><td colspan="7" style="text-align:center;">沒有異常事件</td></tr>`;
        pageInfo.textContent = "第 0 頁（共 0 頁）";
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        return;
    }

    const totalPages = Math.ceil(allResults.length / rowsPerPage);
    const start = (page - 1) * rowsPerPage;
    const end = Math.min(start + rowsPerPage, allResults.length);
    const pageData = allResults.slice(start, end);

    pageData.forEach(alert => {
        const tr = document.createElement('tr');

        const statusCell = document.createElement('td');
        statusCell.appendChild(createStatusButton(alert));

        const notifyCell = document.createElement('td');
        notifyCell.appendChild(createNotifyButton(alert));

        tr.innerHTML = `
            <td>${alert.pool}</td>
            <td>${alert.type}</td>
            <td>${alert.description}</td>
            <td>${formatTimeString(alert.time)}</td>
            <td>${formatTimeString(alert.end_time)}</td>
        `;

        tr.appendChild(statusCell);
        tr.appendChild(notifyCell);
        alertsTbody.appendChild(tr);
    });

    pageInfo.textContent = `第 ${page} 頁（共 ${totalPages} 頁）`;
    prevBtn.disabled = page === 1;
    nextBtn.disabled = page === totalPages;
}

prevBtn.addEventListener("click", () => {
    if (currentPage > 1) {
        currentPage--;
        renderTable(currentPage);
    }
});

nextBtn.addEventListener("click", () => {
    const totalPages = Math.ceil(allResults.length / rowsPerPage);
    if (currentPage < totalPages) {
        currentPage++;
        renderTable(currentPage);
    }
});

queryForm.addEventListener("submit", e => {
    e.preventDefault();
    fetchAlerts();
});

// 頁面載入後先抓一次資料
window.addEventListener("load", fetchAlerts);
