// app/static/js/main.js
// 主应用逻辑

class LingTongApp {
    constructor() {
        this.currentUser = null;
        this.isInitialized = false;
        this._mobileEvents = null;
        this._eventHandlers = new Map(); // 存储事件处理器用于清理
    }

    async init() {
        if (this.isInitialized) return;

        try {
            // 显示加载状态
            if (window.ErrorHandler) {
                ErrorHandler.showLoading('正在初始化应用...');
            }
            
            // 清理可能残留的模态框
            this.cleanupLeftoverModals();
            
            // 设置全局错误处理
            this.setupGlobalErrorHandling();
            
            // 认证并加载用户信息
            await this.authenticateAndLoadUser();
            
            // 初始化UI管理器（确保在绑定事件前）
            window.uiManager = new UIManager();
            await window.uiManager.init();
            
            // 绑定全局事件
            this.bindGlobalEvents();
            
            // 设置移动端菜单
            this.setupMobileMenu();
            
            // 设置页面卸载处理
            this.setupBeforeUnload();
            
            this.isInitialized = true;
            console.log('LingTong app initialized successfully');
            
            // 隐藏加载状态
            if (window.ErrorHandler) {
                ErrorHandler.hideLoading();
            }
            
        } catch (error) {
            console.error('Failed to initialize app:', error);
            if (window.ErrorHandler) {
                ErrorHandler.hideLoading();
                // 只有在真正的认证问题时才显示错误，其他错误静默处理
                if (error.message.includes('authentication') || error.message.includes('401')) {
                    ErrorHandler.handleApiError(error);
                    this.handleAuthError();
                } else {
                    console.warn('Non-critical initialization error, continuing...', error);
                }
            } else {
                this.handleAuthError();
            }
        }
    }

    setupGlobalErrorHandling() {
        // 全局JavaScript错误处理
        const errorHandler = (event) => {
            console.error('Global error:', event.error);
            if (window.ErrorHandler) {
                ErrorHandler.handleError(event.error);
            }
        };
        
        window.addEventListener('error', errorHandler);
        this._eventHandlers.set('error', errorHandler);
        
        // Promise rejection处理
        const rejectionHandler = (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            if (window.ErrorHandler) {
                ErrorHandler.handleError(event.reason);
            }
        };
        
        window.addEventListener('unhandledrejection', rejectionHandler);
        this._eventHandlers.set('unhandledrejection', rejectionHandler);
    }

    setupBeforeUnload() {
        const beforeUnloadHandler = () => {
            this.cleanup();
        };
        
        window.addEventListener('beforeunload', beforeUnloadHandler);
        this._eventHandlers.set('beforeunload', beforeUnloadHandler);
    }

    async authenticateAndLoadUser() {
        try {
            if (!window.apiClient) {
                window.apiClient = new ApiClient();
            }
            this.currentUser = await window.apiClient.getCurrentUser();
            this.displayUserInfo();
        } catch (error) {
            console.error('Authentication failed, redirecting to login.', error);
            // 如果获取用户信息失败，API客户端的请求方法会自动处理重定向
            // 这里可以抛出错误以停止初始化流程
            throw new Error('User authentication failed.');
        }
    }

    displayUserInfo() {
        const usernameElement = document.querySelector('.username');
        if (usernameElement && this.currentUser) {
            usernameElement.textContent = this.currentUser.username;
        }
    }

    handleAuthError() {
        // 这个方法现在由api.js中的请求处理逻辑接管
        console.log("Authentication error handled by ApiClient.");
    }

    // 应用级别的事件处理
    bindGlobalEvents() {
        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K: 新建对话
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                if (window.uiManager) {
                    window.uiManager.showAgentSelector();
                }
            }
            
            // Ctrl/Cmd + /: 切换侧边栏
            if ((e.ctrlKey || e.metaKey) && e.key === '/') {
                e.preventDefault();
                if (window.uiManager) {
                    window.uiManager.toggleSidebar();
                }
            }
            
            // Esc: 关闭弹窗或返回
            if (e.key === 'Escape') {
                this.handleEscapeKey();
            }
        });

        // 窗口大小变化处理
        if (window.PerformanceManager) {
            window.addEventListener('resize', PerformanceManager.debounce(() => {
                this.handleResize();
            }, 250));
        }

        // 页面可见性变化处理
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                console.log('[DEBUG] Page hidden - WebSocket功能已被HTTP API替代');
            } else {
                console.log('[DEBUG] Page visible - WebSocket功能已被HTTP API替代');
            }
        });

        // 在线状态变化处理
        window.addEventListener('online', () => {
            console.log('网络连接已恢复');
            this.showNetworkStatus('网络连接已恢复', 'success');
        });

        window.addEventListener('offline', () => {
            console.log('网络连接已断开');
            this.showNetworkStatus('网络连接已断开，部分功能可能不可用', 'error');
        });

        // 性能监控
        this.monitorPerformance();
    }

    handleEscapeKey() {
        // 关闭弹窗或对话框
        const modals = document.querySelectorAll('.modal, .dialog, .overlay, .report-edit-modal, .modal-overlay');
        modals.forEach(modal => {
            if (modal.style.display !== 'none') {
                modal.style.display = 'none';
                // 完全移除动态创建的模态框
                if (modal.classList.contains('report-edit-modal')) {
                    modal.remove();
                }
            }
        });
    }

    monitorPerformance() {
        if (window.PerformanceManager) {
            PerformanceManager.startMonitoring();
        }
    }

    handleResize() {
        // 响应式处理
        const isMobile = window.innerWidth <= 768;
        document.body.classList.toggle('mobile', isMobile);
        
        // 在移动设备上自动折叠侧边栏
        if (isMobile) {
            const appContainer = document.getElementById('app-container');
            if (appContainer && !appContainer.classList.contains('sidebar-collapsed')) {
                appContainer.classList.add('sidebar-collapsed');
            }
        }
    }

    showNetworkStatus(message, type = 'info') {
        // 创建网络状态提示
        const statusElement = document.createElement('div');
        statusElement.className = `network-status ${type}`;
        statusElement.textContent = message;
        statusElement.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 10000;
            animation: slideIn 0.3s ease-out;
            ${type === 'success' ? 'background: #28a745;' : 'background: #dc3545;'}
        `;
        
        document.body.appendChild(statusElement);
        
        // 3秒后自动移除
        setTimeout(() => {
            if (statusElement.parentNode) {
                statusElement.style.animation = 'slideOut 0.3s ease-in';
                setTimeout(() => {
                    statusElement.parentNode.removeChild(statusElement);
                }, 300);
            }
        }, 3000);
    }

    // 应用级别的工具方法
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        if (typeof bytes !== 'number' || bytes < 0) return 'Invalid size';
        
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    validateFile(file) {
        if (!file || !(file instanceof File)) {
            throw new Error('请选择一个有效的文件');
        }
        
        const maxSize = 10 * 1024 * 1024; // 10MB
        const allowedTypes = [
            'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp',
            'application/pdf', 'text/plain'
        ];

        if (file.size > maxSize) {
            throw new Error(`文件大小不能超过 ${this.formatFileSize(maxSize)}`);
        }

        if (!allowedTypes.includes(file.type)) {
            throw new Error('不支持的文件类型，请上传图片、PDF或文本文件');
        }

        return true;
    }

    // 导出功能
    exportConversation(format = 'pdf') {
        const chatMessages = document.getElementById('chat-messages');
        if (!chatMessages) {
            console.error('Chat messages container not found');
            if (window.ErrorHandler) {
                ErrorHandler.showError('找不到聊天记录，无法导出');
            }
            return;
        }

        const titleElement = document.getElementById('conversation-title');
        const title = titleElement ? titleElement.textContent : '对话记录';
        
        try {
            if (format === 'pdf') {
                this.exportToPDF(chatMessages, title);
            } else if (format === 'docx') {
                this.exportToDocx(chatMessages, title);
            } else if (format === 'txt') {
                this.exportToText(chatMessages, title);
            } else {
                throw new Error('不支持的导出格式');
            }
        } catch (error) {
            console.error('Export failed:', error);
            if (window.ErrorHandler) {
                ErrorHandler.showError(`导出失败：${error.message}`);
            }
        }
    }

    exportToPDF(element, title) {
        if (typeof html2pdf === 'undefined') {
            throw new Error('PDF导出库未加载，请稍后重试');
        }

        const opt = {
            margin: 1,
            filename: `${title}_${new Date().toISOString().split('T')[0]}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { scale: 2, useCORS: true },
            jsPDF: { unit: 'in', format: 'a4', orientation: 'portrait' }
        };

        return html2pdf().set(opt).from(element).save();
    }

    exportToText(element, title) {
        const messages = element.querySelectorAll('.message');
        const textContent = Array.from(messages).map(msg => {
            const sender = msg.querySelector('.sender')?.textContent || 'Unknown';
            const content = msg.querySelector('.content')?.textContent || '';
            const timestamp = msg.querySelector('.timestamp')?.textContent || '';
            return `[${timestamp}] ${sender}: ${content}`;
        }).join('\n\n');

        const blob = new Blob([textContent], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title}_${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    exportToDocx(element, title) {
        // DOCX导出功能（需要额外的库支持）
        throw new Error('DOCX导出功能暂未实现');
    }

    // 设置移动端菜单 (已禁用)
    setupMobileMenu() {
        console.log('Mobile menu functionality disabled');
        // 移动端菜单按钮已从模板中移除
    }
    
    // 绑定移动端事件 (已禁用)
    bindMobileEvents() {
        // 移动端功能已禁用
    }
    
    // 解绑移动端事件 (已禁用)
    unbindMobileEvents() {
        // 移动端功能已禁用
    }

    // 清理资源
    cleanup() {
        this.unbindMobileEvents();
        
        // 移除遮罩层
        const overlay = document.querySelector('.sidebar-overlay');
        if (overlay && overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }
        
        // 恢复body样式
        document.body.style.overflow = '';
        
        // 移除全局错误处理
        this._eventHandlers.forEach((handler, event) => {
            window.removeEventListener(event, handler);
        });
        this._eventHandlers.clear();
        
        console.log('LingTong app cleaned up');
    }
    
    // 清理可能残留的模态框和遮罩
    cleanupLeftoverModals() {
        try {
            // 查找并移除所有可能的模态框
            const modalSelectors = [
                '.modal-overlay',
                '.report-edit-modal', 
                '.dialog',
                '.sidebar-overlay',
                '[class*="modal"]',
                '[class*="overlay"]'
            ];
            
            modalSelectors.forEach(selector => {
                const elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    // 检查是否为动态创建的元素（非模板元素）
                    if (!element.id || !element.id.startsWith('static-')) {
                        element.remove();
                    }
                });
            });
            
            // 清理toast通知元素（通过样式检测动态创建的toast）
            const allDivs = document.querySelectorAll('div[style*="position: fixed"][style*="z-index"]');
            allDivs.forEach(div => {
                const style = div.style.cssText;
                // 检测可能的toast样式特征
                if (style.includes('top: 20px') && style.includes('right: 20px') && 
                    (style.includes('background: #28a745') || style.includes('background: #dc3545') || style.includes('background: #17a2b8'))) {
                    div.remove();
                }
            });
            
            // 清理可能的body样式修改
            document.body.style.overflow = '';
            document.body.classList.remove('modal-open', 'overlay-active');
            
            console.log('Cleaned up leftover modals and overlays');
        } catch (error) {
            console.warn('Error cleaning up modals:', error);
        }
    }
}

// 应用初始化
document.addEventListener('DOMContentLoaded', async () => {
    console.log('DOM loaded, waiting for dependencies...');
    
    // 等待所有必要的类加载完成
    const waitForDependencies = () => {
        return new Promise((resolve) => {
            const checkDependencies = () => {
                if (typeof UIManager !== 'undefined' && 
                    typeof ApiClient !== 'undefined' && 
                    typeof ErrorHandler !== 'undefined') {
                    console.log('All dependencies loaded, initializing LingTong app...');
                    resolve();
                } else {
                    console.log('Waiting for dependencies...', {
                        UIManager: typeof UIManager !== 'undefined',
                        ApiClient: typeof ApiClient !== 'undefined',
                        ErrorHandler: typeof ErrorHandler !== 'undefined'
                    });
                    setTimeout(checkDependencies, 100);
                }
            };
            checkDependencies();
        });
    };
    
    try {
        // 等待依赖项加载
        await waitForDependencies();
        
        const app = new LingTongApp();
        
        // 初始化应用
        await app.init();
        
        // 创建全局应用实例
        window.app = app;
        
        console.log('LingTong app ready!');
    } catch (error) {
        console.error('Failed to initialize LingTong app:', error);
        if (window.ErrorHandler) {
            ErrorHandler.handleApiError(error);
        }
    }
});
