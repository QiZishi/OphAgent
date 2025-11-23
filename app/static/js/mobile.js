// app/static/js/mobile.js
// 移动端功能和适配

class MobileManager {
    constructor() {
        this.isMobile = this.detectMobile();
        this.touchStartX = 0;
        this.touchStartY = 0;
        this.touchEndX = 0;
        this.touchEndY = 0;
        this.init();
    }
    
    init() {
        this.setupTouchEvents();
        this.setupViewportHandling();
        this.setupMobileOptimizations();
    }
    
    detectMobile() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
               window.innerWidth <= 768;
    }
    
    setupTouchEvents() {
        // 触摸手势支持
        document.addEventListener('touchstart', (e) => {
            this.touchStartX = e.changedTouches[0].screenX;
            this.touchStartY = e.changedTouches[0].screenY;
        }, { passive: true });
        
        document.addEventListener('touchend', (e) => {
            this.touchEndX = e.changedTouches[0].screenX;
            this.touchEndY = e.changedTouches[0].screenY;
            this.handleGesture();
        }, { passive: true });
    }
    
    handleGesture() {
        const deltaX = this.touchEndX - this.touchStartX;
        const deltaY = this.touchEndY - this.touchStartY;
        
        // 侧滑手势
        if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {
            if (deltaX > 0) {
                this.onSwipeRight();
            } else {
                this.onSwipeLeft();
            }
        }
    }
    
    onSwipeRight() {
        // 右滑打开侧边栏
        if (window.uiManager && this.isMobile) {
            const sidebar = document.querySelector('.sidebar');
            if (sidebar && !sidebar.classList.contains('active')) {
                window.uiManager.toggleSidebar();
            }
        }
    }
    
    onSwipeLeft() {
        // 左滑关闭侧边栏
        if (window.uiManager && this.isMobile) {
            const sidebar = document.querySelector('.sidebar');
            if (sidebar && sidebar.classList.contains('active')) {
                window.uiManager.toggleSidebar();
            }
        }
    }
    
    setupViewportHandling() {
        // 防止iOS Safari缩放
        document.addEventListener('gesturestart', (e) => {
            e.preventDefault();
        });
        
        // 处理键盘弹起
        if (this.isMobile) {
            const viewport = document.querySelector('meta[name=viewport]');
            if (viewport) {
                viewport.content = 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no';
            }
        }
    }
    
    setupMobileOptimizations() {
        if (this.isMobile) {
            // 添加移动端样式类
            document.body.classList.add('mobile-device');
            
            // 优化滚动性能
            document.documentElement.style.setProperty('-webkit-overflow-scrolling', 'touch');
            
            // 禁用选中文本
            document.body.style.setProperty('-webkit-user-select', 'none');
            document.body.style.setProperty('-moz-user-select', 'none');
            document.body.style.setProperty('-ms-user-select', 'none');
            document.body.style.setProperty('user-select', 'none');
        }
    }
    
    // 工具方法
    static isPortrait() {
        return window.innerHeight > window.innerWidth;
    }
    
    static isLandscape() {
        return window.innerWidth > window.innerHeight;
    }
    
    static getScreenSize() {
        return {
            width: window.innerWidth,
            height: window.innerHeight
        };
    }
}

// 创建全局实例
window.mobileManager = new MobileManager();
