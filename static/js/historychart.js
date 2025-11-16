
(function () {
    const modalEl = document.getElementById('ChartModal');
    const errorMessageEl = document.getElementById('error-message');
    const metricButtonGroup = document.getElementById('metricButtonGroup');
    const chartTitleEl = document.getElementById('primaryChartTitle');

    const metricConfigs = [
        { id: 'temp', title: '溫度 (°C)' },
        { id: 'psu', title: '鹽度 (psu)' },
        { id: 'ph', title: '酸鹼值 (pH)' },
        { id: 'do', title: '溶氧 (mg/L)' },
        { id: 'orp', title: '氧化還原電位 (mV)' },
    ];

    const MAX_POINTS_PER_SERIES = 600;
    const SERIES_COLORS = ['#2563eb', '#f9a216ff', '#10b981', '#c648ecff'];

    const originalData = typeof historyData !== 'undefined' ? historyData : {};
    let selectedMetricId = getInitialMetricId();
    let chartInstance = null;

    function getInitialMetricId() {
        const fallback = metricConfigs.find((config) => dataHasEntriesForMetric(originalData[config.id]));
        return fallback ? fallback.id : (metricConfigs[0] ? metricConfigs[0].id : null);
    }

    function setErrorMessage(message) {
        if (!errorMessageEl) return;
        errorMessageEl.textContent = message || '';
    }

    function destroyChart() {
        if (chartInstance) {
            chartInstance.destroy();
            chartInstance = null;
        }
    }

    function parseTimestamp(value) {
        if (!value) return NaN;
        const iso = value.includes('T') ? value : value.replace(' ', 'T');
        return Date.parse(iso);
    }

    function downsamplePoints(points, maxPoints) {
        if (points.length <= maxPoints) {
            return points;
        }
        const bucketSize = Math.ceil(points.length / maxPoints);
        const result = [];
        for (let i = 0; i < points.length; i += bucketSize) {
            const bucket = points.slice(i, i + bucketSize);
            const avgX = bucket.reduce((sum, p) => sum + p[0], 0) / bucket.length;
            const avgY = bucket.reduce((sum, p) => sum + p[1], 0) / bucket.length;
            result.push([Math.round(avgX), Number(avgY.toFixed(3))]);
        }
        return result;
    }

    function normalizePoolKey(poolKey) {
        if (!poolKey) return '';
        const numeric = poolKey.replace(/\D/g, '');
        return numeric ? `pool${numeric}` : poolKey.toLowerCase();
    }

    function buildSeries(metricData) {
        if (!metricData) return [];
        const pools = Object.keys(metricData).sort();
        if (!pools.length) return [];

        const highlightPool =
            pools.find(
                (pool) =>
                    normalizePoolKey(pool) === 'pool1' &&
                    Array.isArray(metricData[pool]) &&
                    metricData[pool].length > 0
            ) ||
            pools.find((pool) => Array.isArray(metricData[pool]) && metricData[pool].length > 0) ||
            pools[0];

        return pools
            .map((pool, index) => {
                const points = (metricData[pool] || [])
                    .map((entry) => {
                        const time = parseTimestamp(entry.timestamp);
                        const val = Number(entry.value);
                        if (Number.isNaN(time) || !Number.isFinite(val)) return null;
                        return [time, val];
                    })
                    .filter(Boolean)
                    .sort((a, b) => a[0] - b[0]);

                const sampledPoints = downsamplePoints(points, MAX_POINTS_PER_SERIES);
                const baseColor = SERIES_COLORS[index % SERIES_COLORS.length];
                const isPrimary = pool === highlightPool;
                const navigatorLine = baseColor;
                const navigatorFill = baseColor.startsWith('#') ? `${baseColor}33` : 'rgba(34, 197, 94, 0.25)';

                return {
                    type: 'line',
                    name: pool,
                    color: baseColor,
                    visible: isPrimary,
                    opacity: 1,
                    lineWidth: isPrimary ? 2.2 : 1.4,
                    zIndex: isPrimary ? 5 : 1,
                    data: sampledPoints,
                    navigatorOptions: {
                        color: navigatorFill,
                        lineColor: navigatorLine,
                        lineWidth: 1,
                    },
                    showInNavigator: true,
                    tooltip: { valueDecimals: 2 },
                    dataGrouping: {
                        enabled: true,
                        approximation: 'average',
                        groupPixelWidth: 18,
                    },
                };
            })
            .filter((series) => series.data.length > 0);
    }

    function dataHasEntries(data) {
        if (!data) return false;
        return Object.keys(data).some((key) => dataHasEntriesForMetric(data[key]));
    }

    function dataHasEntriesForMetric(metricData) {
        if (!metricData) return false;
        return Object.keys(metricData).some((pool) => {
            const entries = metricData[pool];
            return Array.isArray(entries) && entries.length > 0;
        });
    }

    function ensureSelectedMetricHasData() {
        if (dataHasEntriesForMetric(originalData[selectedMetricId])) {
            return;
        }
        const fallback = metricConfigs.find((config) => dataHasEntriesForMetric(originalData[config.id]));
        if (fallback) {
            selectedMetricId = fallback.id;
            updateButtonActiveState();
        }
    }

    function updateChartHeading(metricConfig) {
        if (chartTitleEl) {
            chartTitleEl.textContent = `${metricConfig.title} 趨勢圖`;
        }
    }

    function renderChart() {
        if (!selectedMetricId) {
            destroyChart();
            setErrorMessage('⚠️ 尚未設定可顯示的項目');
            return;
        }

        const metricConfig = metricConfigs.find((config) => config.id === selectedMetricId);
        const metricData = originalData[selectedMetricId];
        const series = buildSeries(metricData);

        if (!series.length) {
            destroyChart();
            setErrorMessage('⚠️ 沒有可顯示的資料，請選擇其他項目');
            return;
        }

        setErrorMessage('');
        updateChartHeading(metricConfig);
        destroyChart();

        const isNarrowScreen = window.matchMedia('(max-width: 640px)').matches;
        const chartHeight = isNarrowScreen ? 360 : 420;
        const chartSpacing = isNarrowScreen ? [10, 10, 40, 12] : [14, 12, 60, 18];
        const spacingBottom = isNarrowScreen ? 24 : 40;
        const navigatorHeight = isNarrowScreen ? 56 : 70;

        chartInstance = Highcharts.stockChart('primary-chart-container', {
            chart: {
                backgroundColor: 'transparent',
                height: chartHeight,
                animation: false,
                spacing: chartSpacing,
                spacingBottom,
            },
            colors: SERIES_COLORS,
            rangeSelector: {
                selected: 2,
                inputEnabled: false,
                buttonTheme: {
                    fill: 'rgba(148, 163, 184, 0.12)',
                    stroke: '#cbd5f5',
                    'stroke-width': 0,
                    style: { color: '#475569', fontWeight: '600' },
                    states: {
                        hover: { fill: 'rgba(59, 130, 246, 0.18)', style: { color: '#1d4ed8' } },
                        select: { fill: '#2563eb', style: { color: '#ffffff' } },
                    },
                },
                buttons: [
                    { type: 'hour', count: 12, text: '12H' },
                    { type: 'day', count: 1, text: '1D' },
                    { type: 'week', count: 1, text: '1W' },
                    { type: 'month', count: 1, text: '1M' },
                    { type: 'month', count: 3, text: '3M' },
                    { type: 'month', count: 6, text: '6M' },
                    { type: 'all', text: 'All' },
                ],
            },
            legend: {
                enabled: true,
                layout: 'horizontal',
                align: 'center',
                verticalAlign: 'bottom',
                itemStyle: { fontWeight: '600', color: '#1f2937' },
            },
            tooltip: {
                shared: true,
                valueDecimals: 2,
                backgroundColor: 'rgba(15, 23, 42, 0.88)',
                style: { color: '#e2e8f0' },
            },
            credits: { enabled: false },
            exporting: { enabled: false },
            navigator: {
                enabled: true,
                height: navigatorHeight,
                margin: 16,
                maskFill: 'rgba(59, 130, 246, 0.2)',
                series: { lineColor: '#2563eb', lineWidth: 1, color: 'rgba(59, 130, 246, 0.25)' },
            },
            scrollbar: {
                barBackgroundColor: 'rgba(148, 163, 184, 0.4)',
                barBorderColor: 'transparent',
                buttonBackgroundColor: 'rgba(148, 163, 184, 0.5)',
                buttonBorderColor: 'transparent',
                trackBackgroundColor: 'rgba(226, 232, 240, 0.5)',
            },
            xAxis: {
                type: 'datetime',
                lineColor: 'rgba(148, 163, 184, 0.5)',
                tickColor: 'rgba(148, 163, 184, 0.5)',
                labels: { style: { color: '#475569', fontWeight: '500' } },
            },
            yAxis: {
                opposite: false,
                gridLineColor: 'rgba(148, 163, 184, 0.28)',
                title: { text: null },
                labels: { style: { color: '#475569' } },
            },
            plotOptions: {
                series: {
                    animation: false,
                    lineWidth: 1.6,
                    marker: { enabled: false },
                    states: { hover: { lineWidthPlus: 0 } },
                    turboThreshold: 0,
                },
            },
            title: { text: null },
            series,
        });
    }

    function updateButtonActiveState() {
        if (!metricButtonGroup) return;
        metricButtonGroup.querySelectorAll('.metric-button').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.metric === selectedMetricId);
        });
    }

    function renderMetricButtons() {
        if (!metricButtonGroup) return;
        metricButtonGroup.innerHTML = '';
        metricConfigs.forEach((config) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'metric-button';
            btn.dataset.metric = config.id;
            btn.textContent = config.title;
            btn.addEventListener('click', () => {
                if (selectedMetricId === config.id) return;
                selectedMetricId = config.id;
                updateButtonActiveState();
                ensureSelectedMetricHasData();
                renderChart();
            });
            metricButtonGroup.appendChild(btn);
        });
        updateButtonActiveState();
    }

    function initialize() {
        if (typeof historyData === 'undefined') {
            console.error('⚠️ historyData 未定義！');
            return;
        }

        renderMetricButtons();
        ensureSelectedMetricHasData();
        renderChart();
    }

    window.openChartModal = function () {
        if (!modalEl) return;
        modalEl.style.display = 'flex';
        modalEl.scrollTop = 0;
        ensureSelectedMetricHasData();
        renderChart();
    };

    window.closeChartModal = function () {
        if (!modalEl) return;
        modalEl.style.display = 'none';
    };

    document.addEventListener('DOMContentLoaded', initialize);
})();
