
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
        input.max = range.max = 240;
        input.step = range.step = 1;
        input.value = range.value = 5;
    } else if (settingType === 'feed') {
        title.textContent = '設定每次飼料量（克）';
        input.min = range.min = 1;
        input.max = range.max = 500;
        input.step = range.step = 10;
        input.value = range.value = 100;
    }
}

function closeModal() {
    document.getElementById('settingModal').style.display = 'none';
}

function toggleMenu() {
    const menu = document.getElementById('fabMenu');
    menu.classList.toggle('show');
}

function applySetting() {
    const val = parseFloat(document.getElementById('modalInput').value);
    const error = document.getElementById('modalError');

    if (!isNaN(val) && val > 0) {
        error.style.display = 'none';

        if (currentSetting === 'interval') {
            alert(`✅ 平台升降間隔設定為 ${val} 分`);
            console.log("已設定平台升降間隔：", val);
            // TODO: 傳送到後端
        } else if (currentSetting === 'feed') {
            alert(`✅ 每次飼料量設定為 ${val} 克`);
            console.log("已設定飼料量：", val);
            // TODO: 傳送到後端
        }

        closeModal();
    } else {
        error.style.display = 'block';
    }
}

// 雙向綁定 input 和 range
window.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('modalInput');
    const range = document.getElementById('modalRange');

    input.addEventListener('input', () => {
        range.value = input.value;
    });

    range.addEventListener('input', () => {
        input.value = range.value;
    });
});

