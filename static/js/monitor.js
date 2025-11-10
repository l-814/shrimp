const rowsPerPage = 9;
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
        alertsTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:red;">錯誤: ${err.message}</td></tr>`;
        pageInfo.textContent = "";
        prevBtn.disabled = true;
        nextBtn.disabled = true;
    }
}

function renderTable(page) {
    alertsTbody.innerHTML = "";

    if (allResults.length === 0) {
        alertsTbody.innerHTML = `<tr><td colspan="5" style="text-align:center;">沒有異常事件</td></tr>`;
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
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${alert.pool}</td>
            <td>${alert.type}</td>
            <td>${alert.description}</td>
            <td>${alert.time}</td>
            <td>${alert.status}</td>
        `;
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
