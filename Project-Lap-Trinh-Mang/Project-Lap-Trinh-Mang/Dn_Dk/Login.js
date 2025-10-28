// Hàm chuyển đổi giữa trang Admin và Student
function togglePage(page) {
    if (page === 'student') {
        document.querySelector('.title').textContent = 'USER';
        document.getElementById('username').placeholder = 'Enter Code';
        document.getElementById('passwordField').style.display = 'none';
        document.getElementById('adminInputs').style.display = 'none';
        document.getElementById('studentInputs').style.display = 'block';
        document.getElementById('toggleToStudent').style.display = 'none';
        document.getElementById('toggleToAdmin').style.display = 'block';
        
        document.getElementById('bannerName').textContent = 'User';
        document.getElementById('bannerImage').src = '/Project-Lap-Trinh-Mang/imgs/LOGO.jpg';
    } else {
        document.querySelector('.title').textContent = 'ADMIN';
        document.getElementById('username').placeholder = 'Name';
        document.getElementById('passwordField').style.display = 'block';
        document.getElementById('adminInputs').style.display = 'block';
        document.getElementById('studentInputs').style.display = 'none';
        document.getElementById('toggleToAdmin').style.display = 'none';
        document.getElementById('toggleToStudent').style.display = 'block';
        
        document.getElementById('bannerName').textContent = 'Admin';
        document.getElementById('bannerImage').src = '/Project-Lap-Trinh-Mang/imgs/LOGO.jpg';
    }
}
 
// Mặc định là Admin khi trang được tải
window.onload = function() {
    togglePage('admin');
    createSnow(); // Tạo hiệu ứng tuyết
};

// Hàm để hiển thị thông báo thành công khi đăng nhập thành công
function showSuccessMessage() {
    document.querySelector('.wrapper').classList.add('success');
    document.querySelector('.success-message').textContent = 'Login Successful! Redirecting...';
    setTimeout(() => {
        window.location.href = 'dashboard.html';
    }, 2000);
}

// =================================Tạo hiệu ứng tuyết===================================================
function createSnow() {
    let snowContainer = document.createElement('div');
    snowContainer.classList.add('snow');
    document.body.appendChild(snowContainer);

    let numberOfSnowflakes = 50;

    for (let i = 0; i < numberOfSnowflakes; i++) {
        let snowflake = document.createElement('div');
        snowflake.classList.add('snowflake');
        
        let size = Math.random() * 10 + 5;
        let leftPosition = Math.random() * 100 + '%';
        let animationDuration = Math.random() * 5 + 5 + 's';
        
        snowflake.style.width = size + 'px';
        snowflake.style.height = size + 'px';
        snowflake.style.left = leftPosition;
        snowflake.style.animationDuration = animationDuration;
        
        snowContainer.appendChild(snowflake);
    }
}
