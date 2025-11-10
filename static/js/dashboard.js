const sidebar = document.getElementById("sidebar");
let currentPoolId = "{{ pool_id }}"; // 從 Flask 傳來的預設魚池ID

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

        document.getElementById('last-update').textContent = new Date(data.timestamp).toLocaleString();

        const sensors = ['temp', 'psu', 'ph', 'do', 'orp'];

        sensors.forEach(sensor => {
            const valueSpan = document.getElementById(sensor);
            const itemDiv = document.getElementById(`${sensor}-item`);

            valueSpan.textContent = data[sensor];

            if (data.abnormal[sensor]) {
                itemDiv.classList.add('abnormal');
            } else {
                itemDiv.classList.remove('abnormal');
            }
        });
    } catch (error) {
        console.error(error);
        // 顯示錯誤訊息
        document.getElementById('last-update').textContent = '無法取得資料';
    }
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

    // 每 60 秒更新資料
    setInterval(fetchAndUpdate, 60000);
};