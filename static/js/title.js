const toggleBtn = document.getElementById('menuToggle');
const mobileMenu = document.getElementById('mobileMenu');

toggleBtn.addEventListener('click', () => {
    mobileMenu.classList.toggle('active');
});

// 可選：點擊外部關閉選單
document.addEventListener('click', (e) => {
    if (!mobileMenu.contains(e.target) && !toggleBtn.contains(e.target)) {
        mobileMenu.classList.remove('active');
    }
});
