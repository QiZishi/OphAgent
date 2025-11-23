// app/static/js/utils/errorHandler.js
// 错误处理工具类

class ErrorHandler {
    static showToast(message, type = 'error', duration = 5000) {
        const toast = document.createElement('div');
        toast.className = `${type}-toast`;
        toast.innerHTML = `
            ${message}
            <button class="toast-close" aria-label="关闭">
                <i data-lucide="x" aria-hidden="true"></i>
            </button>
        `;
        
        document.body.appendChild(toast);
        
        // 初始化图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
        
        // 添加关闭事件
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => {
            this.hideToast(toast);
        });
        
        // 自动关闭
        if (duration > 0) {
            setTimeout(() => {
                this.hideToast(toast);
            }, duration);
        }
        
        return toast;
    }
    
    static hideToast(toast) {
        if (toast && toast.parentNode) {
            toast.style.animation = 'slideOutToRight 0.3s ease';
            setTimeout(() => {
                toast.remove();
            }, 300);
        }
    }
    
    static handleApiError(error) {
        console.error('API Error:', error);
        
        let message = '操作失败，请稍后重试';
        
        if (error.response) {
            // 服务器响应错误
            switch (error.response.status) {
                case 401:
                    message = '认证失败，请重新登录';
                    // 可以在这里处理重定向到登录页面
                    break;
                case 403:
                    message = '权限不足';
                    break;
                case 404:
                    message = '请求的资源不存在';
                    break;
                case 429:
                    message = '请求过于频繁，请稍后再试';
                    break;
                case 500:
                    message = '服务器内部错误';
                    break;
                default:
                    if (error.response.data && error.response.data.detail) {
                        message = error.response.data.detail;
                    }
            }
        } else if (error.request) {
            // 网络错误
            message = '网络连接失败，请检查网络设置';
        }
        
        this.showToast(message, 'error');
        return message;
    }
    
    static showLoading(message = '正在处理...') {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            const messageElement = overlay.querySelector('span');
            if (messageElement) {
                messageElement.textContent = message;
            }
            overlay.style.display = 'flex';
            overlay.setAttribute('aria-hidden', 'false');
        }
    }
    
    static hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
            overlay.setAttribute('aria-hidden', 'true');
        }
    }
    
    static announceToScreenReader(message) {
        const statusElement = document.getElementById('screen-reader-status');
        if (statusElement) {
            statusElement.textContent = message;
            // 清空状态，以便下次公告
            setTimeout(() => {
                statusElement.textContent = '';
            }, 1000);
        }
    }
    
    static handleNetworkError() {
        this.showToast('网络连接中断，请检查网络设置', 'error');
        this.announceToScreenReader('网络连接中断');
    }
    
    static validateInput(input, rules = {}) {
        const errors = [];
        const value = input.value.trim();
        
        if (rules.required && !value) {
            errors.push('此字段为必填项');
        }
        
        if (rules.minLength && value.length < rules.minLength) {
            errors.push(`至少需要 ${rules.minLength} 个字符`);
        }
        
        if (rules.maxLength && value.length > rules.maxLength) {
            errors.push(`最多允许 ${rules.maxLength} 个字符`);
        }
        
        if (rules.pattern && !rules.pattern.test(value)) {
            errors.push(rules.patternMessage || '格式不正确');
        }
        
        if (rules.email && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
            errors.push('请输入有效的邮箱地址');
        }
        
        // 更新UI
        const errorElement = input.parentNode.querySelector('.form-error');
        if (errors.length > 0) {
            input.classList.add('error');
            if (errorElement) {
                errorElement.textContent = errors[0];
            }
        } else {
            input.classList.remove('error');
            if (errorElement) {
                errorElement.textContent = '';
            }
        }
        
        return errors.length === 0;
    }
    
    // 显示加载状态
    static showLoading(message = '加载中...') {
        // 移除已存在的加载提示
        this.hideLoading();
        
        const loading = document.createElement('div');
        loading.id = 'global-loading';
        loading.className = 'loading-overlay';
        loading.innerHTML = `
            <div class="loading-content">
                <div class="spinner"></div>
                <p class="loading-message">${message}</p>
            </div>
        `;
        
        // 添加样式
        loading.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 9999;
        `;
        
        const content = loading.querySelector('.loading-content');
        content.style.cssText = `
            background: white;
            padding: 32px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
        `;
        
        const spinner = loading.querySelector('.spinner');
        spinner.style.cssText = `
            width: 32px;
            height: 32px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #3498db;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 16px;
        `;
        
        // 添加spinner动画
        if (!document.getElementById('spinner-style')) {
            const style = document.createElement('style');
            style.id = 'spinner-style';
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }
        
        document.body.appendChild(loading);
        return loading;
    }
    
    // 隐藏加载状态
    static hideLoading() {
        const loading = document.getElementById('global-loading');
        if (loading) {
            loading.remove();
        }
    }
    
    // 更新加载消息
    static updateLoadingMessage(message) {
        const loading = document.getElementById('global-loading');
        if (loading) {
            const messageElement = loading.querySelector('.loading-message');
            if (messageElement) {
                messageElement.textContent = message;
            }
        }
    }
}

// // 全局错误处理
// window.addEventListener('error', (event) => {
//     console.error('Global error:', event.error);
//     ErrorHandler.showToast('页面发生错误，请刷新重试', 'error');
// });

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    ErrorHandler.showToast('操作失败，请重试', 'error');
});

// 网络状态监控
window.addEventListener('online', () => {
    ErrorHandler.showToast('网络连接已恢复', 'success', 3000);
});

window.addEventListener('offline', () => {
    ErrorHandler.handleNetworkError();
});

// 导出到全局
window.ErrorHandler = ErrorHandler;
