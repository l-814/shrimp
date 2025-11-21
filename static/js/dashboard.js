const sidebar = document.getElementById("sidebar");
let currentPoolId = "{{ pool_id }}"; // 從 Flask 傳來的預設魚池ID
const SENSOR_DISPLAY = {
    temp: { unit: '°C', digits: 1 },
    psu: { unit: 'psu', digits: 1 },
    ph: { unit: '', digits: 2 },
    do: { unit: 'mg/L', digits: 2 },
    orp: { unit: 'mV', digits: 0 },
};

function toggleSidebar() {
    sidebar.classList.toggle("show");
}

// 切換魚池
function switchPool(btn, poolId) {
    // 移除所有按鈕 active 樣式
    document.querySelectorAll(".pool-switcher button").forEach((b) => {
        b.classList.remove("active");
    });
    // 給目前按鈕加上 active
    if (btn) btn.classList.add("active");

    currentPoolId = poolId;

    updateVideo(poolId);
    fetchAndUpdate();  // 新增：立即更新資料
}

// 根據池子ID更新影片區背景顏色 (模擬影片區切換)
function updateVideo(poolId) {
    const videoBox = document.getElementById("video-box");
    const videoSource = document.getElementById("video-source");

    const videoPath = `/static/videos/pool${poolId}.mp4`;

    videoSource.src = videoPath;
    videoBox.load();
}

async function fetchAndUpdate() {
    try {
        const res = await fetch(`/api/latest-data/${currentPoolId}`);
        if (!res.ok) throw new Error("讀取資料失敗");
        const data = await res.json();

        const ts = data.timestamp ? new Date(data.timestamp.replace(' ', 'T')) : null;
        document.getElementById('last-update').textContent = ts ? ts.toLocaleString() : '--';

        const sensors = ['temp', 'psu', 'ph', 'do', 'orp'];

        sensors.forEach(sensor => {
            const valueSpan = document.getElementById(sensor);
            const itemDiv = document.getElementById(`${sensor}-item`);

            const meta = SENSOR_DISPLAY[sensor] || { unit: '', digits: 2 };
            if (typeof data[sensor] === 'number') {
                valueSpan.textContent = `${data[sensor].toFixed(meta.digits)}${meta.unit ? ' ' + meta.unit : ''}`;
            } else {
                valueSpan.textContent = '--';
            }

            if (data.abnormal[sensor]) {
                itemDiv.classList.add('abnormal');
            } else {
                itemDiv.classList.remove('abnormal');
            }
        });
        await updateActionStatus();
    } catch (error) {
        console.error(error);
        // 顯示錯誤訊息
        document.getElementById('last-update').textContent = '無法取得資料';
        await setActionStatusFallback();
    }
}

async function updateActionStatus() {
    const config = [
        { key: 'food', buttonId: 'control-feed', stateId: 'control-feed-state' },
        { key: 'behavior', buttonId: 'control-behavior', stateId: 'control-behavior-state' },
    ];

    try {
        const res = await fetch(`/api/action-status?pool_id=${encodeURIComponent(currentPoolId)}`);
        if (!res.ok) throw new Error('取得異常狀態失敗');
        const status = await res.json();
        config.forEach(({ key, buttonId, stateId }) => {
            const info = status[key] || {};
            setActionButtonState(buttonId, stateId, info.abnormal, info.description);
        });
    } catch (err) {
        console.error(err);
        await setActionStatusFallback();
    }
}

function setActionButtonState(buttonId, stateId, isAbnormal, description) {
    const button = document.getElementById(buttonId);
    const stateEl = document.getElementById(stateId);
    if (!button || !stateEl) return;
    if (isAbnormal) {
        button.classList.remove('normal');
        button.classList.add('abnormal');
        stateEl.textContent = '異常';
        button.title = description ? `異常：${description}` : '異常';
    } else {
        button.classList.add('normal');
        button.classList.remove('abnormal');
        stateEl.textContent = '正常';
        button.title = '正常';
    }
}

async function setActionStatusFallback() {
    setActionButtonState('control-feed', 'control-feed-state', false);
    setActionButtonState('control-behavior', 'control-behavior-state', false);
}

// 頁面載入時執行
window.onload = () => {
    // 魚池切換按鈕初始化
    let defaultBtn = document.querySelector(".pool-switcher button.active");
    if (!defaultBtn) {
        defaultBtn = document.querySelector(".pool-switcher button");
        if (defaultBtn) defaultBtn.classList.add("active");
    }
    if (defaultBtn) {
        const poolId = defaultBtn.textContent.replace(/\D/g, '');
        switchPool(defaultBtn, poolId);
    } else {
        // 預設更新影片區及資料
        updateVideo(currentPoolId);
        fetchAndUpdate();
    }

    // 每 5 秒更新資料
    setInterval(fetchAndUpdate, 5000);
};
