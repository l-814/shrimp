let charts = {};

function createChart(ctx, label, borderColor) {
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],  // 時間軸
            datasets: [{
                label: label,
                data: [],
                fill: false,
                borderColor: borderColor,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 6,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        font: {
                            size: 14
                        }
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function (context) {
                            return `${label}: ${context.raw}`;
                        }
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'minute',
                        displayFormats: {
                            minute: 'HH:mm'
                        }
                    },
                    title: {
                        display: true,
                        text: '時間',
                        font: { size: 14 }
                    }
                },
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: label,
                        font: { size: 14 }
                    }
                }
            }
        }
    });
}

function initCharts() {
    charts = {
        temp: createChart(document.getElementById('temp_chart'), '溫度 (°C)', '#FF6384'),
        psu: createChart(document.getElementById('psu_chart'), '鹽度 (%)', '#36A2EB'),
        ph: createChart(document.getElementById('ph_chart'), '酸鹼值', '#FFCE56'),
        do: createChart(document.getElementById('do_chart'), '溶氧 (mg/L)', '#4BC0C0'),
        orp: createChart(document.getElementById('orp_chart'), '氧化還原電位 (mV)', '#9966FF'),
    };
}

function updateCharts(historyData) {
    const sensors = ['temp', 'psu', 'ph', 'do', 'orp'];

    sensors.forEach(sensor => {
        const chart = charts[sensor];
        if (!chart) return;

        const labels = historyData.map(entry => new Date(entry.timestamp));
        const values = historyData.map(entry => entry[sensor]);

        chart.data.labels = labels;
        chart.data.datasets[0].data = values;

        chart.update();
    });
}

// 初始化圖表
window.addEventListener('DOMContentLoaded', () => {
    initCharts();

    // 從全域變數取得資料
    if (typeof historyData !== 'undefined' && historyData.length > 0) {
        updateCharts(historyData);
    }
});
