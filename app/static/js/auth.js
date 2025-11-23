// app/static/js/auth.js
// 认证页面逻辑

class AuthManager {
    constructor() {
        this.init();
    }

    init() {
        // 绑定表单事件
        this.bindEvents();
    }

    bindEvents() {
        // 登录表单
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }

        // 注册表单
        const registerForm = document.getElementById('register-form');
        if (registerForm) {
            registerForm.addEventListener('submit', (e) => this.handleRegister(e));
        }
    }

    async handleLogin(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const credentials = {
            username: formData.get('username'),
            password: formData.get('password')
        };

        try {
            this.showLoading(true);
            this.hideError();

            const response = await fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(credentials)
            });

            if (response.ok) {
                // 登录成功，后端已设置cookie，直接重定向
                window.location.href = '/app';
            } else {
                const data = await response.json();
                this.showError(data.detail || '登录失败，请检查用户名和密码');
            }
        } catch (error) {
            console.error('Login error:', error);
            this.showError('网络错误，请稍后重试');
        } finally {
            this.showLoading(false);
        }
    }

    async handleRegister(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const userData = {
            username: formData.get('username'),
            password: formData.get('password')
        };

        const confirmPassword = formData.get('confirm-password');

        // 验证密码确认
        if (userData.password !== confirmPassword) {
            this.showError('两次输入的密码不一致');
            return;
        }

        try {
            this.showLoading(true);
            this.hideError();

            const response = await fetch('/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(userData)
            });

            const data = await response.json();

            if (response.ok) {
                // 注册成功，提示用户登录
                this.showSuccess('注册成功！现在您可以登录了。');
                // 可选：自动清空表单
                event.target.reset();
            } else {
                this.showError(data.detail || '注册失败，请稍后重试');
            }
        } catch (error) {
            console.error('Registration error:', error);
            this.showError('网络错误，请稍后重试');
        } finally {
            this.showLoading(false);
        }
    }

    showLoading(isLoading) {
        const submitButton = document.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.disabled = isLoading;
            submitButton.innerHTML = isLoading 
                ? '<span class="loader"></span>' 
                : (this.isCurrentPage(['/']) ? '登 录' : '注 册');
        }
    }

    showError(message) {
        const errorElement = document.getElementById('error-message');
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.style.display = 'block';
        }
    }

    hideError() {
        const errorElement = document.getElementById('error-message');
        if (errorElement) {
            errorElement.style.display = 'none';
        }
    }
    
    showSuccess(message) {
        const successElement = document.getElementById('success-message');
        if (successElement) {
            successElement.textContent = message;
            successElement.style.display = 'block';
            // 5秒后自动隐藏
            setTimeout(() => {
                successElement.style.display = 'none';
            }, 5000);
        }
    }
    
    isCurrentPage(paths) {
        return paths.includes(window.location.pathname);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new AuthManager();
});
