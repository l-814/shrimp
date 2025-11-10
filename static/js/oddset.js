// 初始化滑桿控制邏輯
document.querySelectorAll(".setting").forEach(setting => {
    const key = setting.dataset.key;
    const step = parseFloat(setting.dataset.step);
    const minLimit = parseFloat(setting.dataset.min);
    const maxLimit = parseFloat(setting.dataset.max);

    const minInput = document.getElementById(`${key}-min`);
    const maxInput = document.getElementById(`${key}-max`);
    const rangeDiv = document.getElementById(`${key}-range`);
    const statusDiv = document.getElementById(`${key}-status`);

    // 檢查必要元素是否存在
    if (!minInput || !maxInput || !rangeDiv || !statusDiv) {
        console.warn(`缺少元素，key: ${key}，跳過初始化`);
        return;
    }

    noUiSlider.create(rangeDiv, {
        start: [parseFloat(minInput.value), parseFloat(maxInput.value)],
        connect: true,
        step: step,
        range: {
            'min': minLimit,
            'max': maxLimit
        },
        format: {
            to: function(value) {
                return step < 1 ? value.toFixed(1) : value.toFixed(0);
            },
            from: function(value) {
                return parseFloat(value);
            }
        }
    });

    rangeDiv.noUiSlider.on('update', function(values) {
        minInput.value = values[0];
        maxInput.value = values[1];
        statusDiv.textContent = `範圍：${values[0]} ~ ${values[1]}`;
    });

    function updateSliderFromInputs() {
        let minVal = parseFloat(minInput.value);
        let maxVal = parseFloat(maxInput.value);

        if (isNaN(minVal)) minVal = minLimit;
        if (isNaN(maxVal)) maxVal = maxLimit;

        if (minVal < minLimit) minVal = minLimit;
        if (maxVal > maxLimit) maxVal = maxLimit;
        if (maxVal <= minVal) {
            maxVal = Math.min(minVal + step, maxLimit);
        }

        minInput.value = step < 1 ? minVal.toFixed(2) : minVal.toFixed(0);
        maxInput.value = step < 1 ? maxVal.toFixed(2) : maxVal.toFixed(0);

        rangeDiv.noUiSlider.set([minVal, maxVal]);
    }


    minInput.addEventListener("change", updateSliderFromInputs);
    maxInput.addEventListener("change", updateSliderFromInputs);

    statusDiv.textContent = `範圍：${minInput.value} ~ ${maxInput.value}`;
});

// 處理表單送出
document.getElementById('env-form').addEventListener('submit', function(e) {
    e.preventDefault(); // 阻止表單跳轉

    const data = {
        temp_min: parseFloat(document.getElementById('temp-min').value),
        temp_max: parseFloat(document.getElementById('temp-max').value),
        psu_min: parseFloat(document.getElementById('psu-min').value),
        psu_max: parseFloat(document.getElementById('psu-max').value),
        ph_min: parseFloat(document.getElementById('ph-min').value),
        ph_max: parseFloat(document.getElementById('ph-max').value),
        do_min: parseFloat(document.getElementById('do-min').value),
        do_max: parseFloat(document.getElementById('do-max').value),
        orp_min: parseFloat(document.getElementById('orp-min').value),
        orp_max: parseFloat(document.getElementById('orp-max').value)
    };

    fetch('/oddset', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(res => {
        const msgDiv = document.getElementById('message');
        const lastUpdatedDiv = document.getElementById('last-updated');

        if (res.success) {
            msgDiv.style.color = 'green';
            msgDiv.textContent = '儲存成功！';

            // ✅ 前端立即取得台灣時間（Asia/Taipei）更新畫面
            const now = new Date().toLocaleString('zh-TW', {
                timeZone: 'Asia/Taipei',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: false
            });

            lastUpdatedDiv.textContent = `最後更新時間：${now}`;
        } else {
            msgDiv.style.color = 'red';
            msgDiv.textContent = '儲存失敗：' + res.error;
        }
    })
    .catch(() => {
        const msgDiv = document.getElementById('message');
        msgDiv.style.color = 'red';
        msgDiv.textContent = '伺服器錯誤，請稍後再試。';
    });
});
