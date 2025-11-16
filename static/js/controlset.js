
let currentSetting = '';

function openModal(settingType) {
    currentSetting = settingType;
    const modal = document.getElementById('settingModal');
    modal.style.display = 'flex';
    document.getElementById('modalError').style.display = 'none';

    const input = document.getElementById('modalInput');
    const range = document.getElementById('modalRange');
    const title = document.getElementById('modalTitle');

    if (settingType === 'interval') {
        title.textContent = '設定平台升降間隔（分）';
        input.min = range.min = 1;
        input.max = range.max = 60;
        input.step = range.step = 1;
        input.value = range.value = 5;
    } else if (settingType === 'feed') {
        title.textContent = '設定每次飼料量（克）';
        input.min = range.min = 1;
        input.max = range.max = 500;
        input.step = range.step = 1;
        input.value = range.value = 100;
    }

    setStatusLabels();
    loadSettingStatus();
}

function closeModal() {
    document.getElementById('settingModal').style.display = 'none';
    currentSetting = '';
}

function toggleMenu() {
    const menu = document.getElementById('fabMenu');
    menu.classList.toggle('show');
}

async function applySetting() {
    const val = parseFloat(document.getElementById('modalInput').value);
    const poolId = document.getElementById('poolSelect').value;
    const error = document.getElementById('modalError');

    if (isNaN(val) || val <= 0) {
        error.textContent = '請輸入正確數值';
        error.style.display = 'block';
        return;
    }

    if (!currentSetting) {
        error.textContent = '請選擇設定項目';
        error.style.display = 'block';
        return;
    }

    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                pool_id: poolId,
                setting_type: currentSetting,
                value: val
            })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || '儲存失敗，請稍後再試');
        }

        error.style.display = 'none';
        const label = currentSetting === 'interval' ? '平台升降間隔' : '每次飼料量';
        const unit = currentSetting === 'interval' ? '分' : '克';
        alert(`✅ 水池 ${poolId} 的${label}設定為 ${val} ${unit}`);
        setStatusLabels(result.updated_at, result.value);
        closeModal();
    } catch (err) {
        error.textContent = err.message || '儲存失敗，請稍後再試';
        error.style.display = 'block';
    }
}

// 雙向綁定 input 和 range
window.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('modalInput');
    const range = document.getElementById('modalRange');
    const poolSelect = document.getElementById('poolSelect');

    input.addEventListener('input', () => {
        range.value = input.value;
    });

    range.addEventListener('input', () => {
        input.value = range.value;
    });

    poolSelect.addEventListener('change', () => {
        if (currentSetting) {
            loadSettingStatus();
        }
    });
});

function setStatusLabels(updatedAt, value) {
    const updateEl = document.getElementById('lastUpdateLabel');
    const valueEl = document.getElementById('lastValueLabel');
    updateEl.textContent = `上次更新：${updatedAt || '--'}`;
    valueEl.textContent = `上次數值：${value ?? '--'}`;
}

function setStatusMessage(message) {
    const updateEl = document.getElementById('lastUpdateLabel');
    const valueEl = document.getElementById('lastValueLabel');
    updateEl.textContent = `上次更新：${message}`;
    valueEl.textContent = '上次數值：--';
}

async function loadSettingStatus() {
    if (!currentSetting) {
        setStatusLabels();
        return;
    }

    const poolId = document.getElementById('poolSelect').value;
    const input = document.getElementById('modalInput');
    const range = document.getElementById('modalRange');

    setStatusMessage('查詢中...');

    try {
        const params = new URLSearchParams({
            pool_id: poolId,
            setting_type: currentSetting
        });
        const response = await fetch(`/api/settings?${params.toString()}`);
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.message || '查詢失敗');
        }

        if (result.value == null) {
            setStatusMessage('尚無紀錄');
            return;
        }

        setStatusLabels(result.updated_at, result.value);
        input.value = result.value;
        range.value = result.value;
    } catch (err) {
        setStatusMessage(err.message || '查詢失敗');
    }
}
