// app/static/js/utils/accessibility.js
// 可访问性增强工具类

class AccessibilityManager {
    constructor() {
        this.focusableElements = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
        this.trapFocus = false;
        this.lastFocusedElement = null;
        this.init();
    }
    
    init() {
        this.setupKeyboardNavigation();
        this.setupFocusManagement();
        this.setupARIALiveRegions();
        this.detectMotionPreference();
    }
    
    // 设置键盘导航
    setupKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            // ESC键处理
            if (e.key === 'Escape') {
                this.handleEscape();
            }
            
            // Tab键焦点陷阱
            if (e.key === 'Tab' && this.trapFocus) {
                this.handleFocusTrap(e);
            }
            
            // 方向键导航
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                this.handleArrowNavigation(e);
            }
            
            // Enter和Space键激活
            if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[role="button"]')) {
                e.preventDefault();
                e.target.click();
            }
        });
    }
    
    // 焦点管理
    setupFocusManagement() {
        // 记录最后聚焦的元素
        document.addEventListener('focusin', (e) => {
            if (!this.trapFocus) {
                this.lastFocusedElement = e.target;
            }
        });
        
        // 为动态添加的元素设置焦点
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'childList') {
                    mutation.addedNodes.forEach((node) => {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            this.enhanceNewElement(node);
                        }
                    });
                }
            });
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
    
    // 增强新添加的元素
    enhanceNewElement(element) {
        // 为没有标签的表单元素添加标签
        const inputs = element.querySelectorAll('input:not([aria-label]):not([aria-labelledby])');
        inputs.forEach(input => {
            if (!input.labels.length) {
                const placeholder = input.getAttribute('placeholder');
                if (placeholder) {
                    input.setAttribute('aria-label', placeholder);
                }
            }
        });
        
        // 为图片添加默认alt属性
        const images = element.querySelectorAll('img:not([alt])');
        images.forEach(img => {
            img.setAttribute('alt', '');
        });
        
        // 为按钮添加角色
        const buttonLike = element.querySelectorAll('[onclick]:not(button):not([role])');
        buttonLike.forEach(el => {
            el.setAttribute('role', 'button');
            el.setAttribute('tabindex', '0');
        });
    }
    
    // 设置ARIA实时区域
    setupARIALiveRegions() {
        // 如果不存在状态通知区域，创建一个
        if (!document.getElementById('screen-reader-status')) {
            const statusRegion = document.createElement('div');
            statusRegion.id = 'screen-reader-status';
            statusRegion.className = 'sr-only';
            statusRegion.setAttribute('aria-live', 'polite');
            statusRegion.setAttribute('aria-atomic', 'true');
            document.body.appendChild(statusRegion);
        }
    }
    
    // 检测动画偏好
    detectMotionPreference() {
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
        
        const handleMotionPreference = () => {
            if (prefersReducedMotion.matches) {
                document.body.classList.add('reduce-motion');
                // 禁用或减少动画
                this.disableAnimations();
            } else {
                document.body.classList.remove('reduce-motion');
            }
        };
        
        handleMotionPreference();
        prefersReducedMotion.addEventListener('change', handleMotionPreference);
    }
    
    // 禁用动画
    disableAnimations() {
        const style = document.createElement('style');
        style.textContent = `
            *, *::before, *::after {
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.01ms !important;
            }
        `;
        document.head.appendChild(style);
    }
    
    // 处理ESC键
    handleEscape() {
        // 关闭模态框
        const modals = document.querySelectorAll('.modal-overlay');
        modals.forEach(modal => {
            if (modal.style.display !== 'none') {
                this.closeModal(modal);
            }
        });
        
        // 关闭弹出菜单
        const popups = document.querySelectorAll('.popup[aria-hidden="false"]');
        popups.forEach(popup => {
            this.closePopup(popup);
        });
    }
    
    // 焦点陷阱处理
    handleFocusTrap(e) {
        const modal = document.querySelector('.modal-overlay:not([style*="display: none"])');
        if (!modal) return;
        
        const focusableElements = modal.querySelectorAll(this.focusableElements);
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        
        if (e.shiftKey) {
            if (document.activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            }
        } else {
            if (document.activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        }
    }
    
    // 方向键导航
    handleArrowNavigation(e) {
        const target = e.target;
        
        // 处理菜单导航
        if (target.matches('[role="menuitem"]')) {
            e.preventDefault();
            const menu = target.closest('[role="menu"]');
            const items = menu.querySelectorAll('[role="menuitem"]');
            const currentIndex = Array.from(items).indexOf(target);
            
            let nextIndex;
            if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
                nextIndex = (currentIndex + 1) % items.length;
            } else {
                nextIndex = (currentIndex - 1 + items.length) % items.length;
            }
            
            items[nextIndex].focus();
        }
        
        // 处理tab导航
        if (target.matches('[role="tab"]')) {
            e.preventDefault();
            const tablist = target.closest('[role="tablist"]');
            const tabs = tablist.querySelectorAll('[role="tab"]');
            const currentIndex = Array.from(tabs).indexOf(target);
            
            let nextIndex;
            if (e.key === 'ArrowLeft') {
                nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
            } else if (e.key === 'ArrowRight') {
                nextIndex = (currentIndex + 1) % tabs.length;
            }
            
            if (nextIndex !== undefined) {
                tabs[nextIndex].focus();
                tabs[nextIndex].click();
            }
        }
    }
    
    // 打开模态框
    openModal(modal) {
        this.lastFocusedElement = document.activeElement;
        this.trapFocus = true;
        
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        
        // 聚焦到模态框的第一个可聚焦元素
        const firstFocusable = modal.querySelector(this.focusableElements);
        if (firstFocusable) {
            firstFocusable.focus();
        }
        
        this.announce('对话框已打开');
    }
    
    // 关闭模态框
    closeModal(modal) {
        this.trapFocus = false;
        
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
        
        // 恢复焦点
        if (this.lastFocusedElement) {
            this.lastFocusedElement.focus();
        }
        
        this.announce('对话框已关闭');
    }
    
    // 关闭弹出框
    closePopup(popup) {
        popup.setAttribute('aria-hidden', 'true');
        popup.style.display = 'none';
    }
    
    // 屏幕阅读器通知
    announce(message) {
        const statusElement = document.getElementById('screen-reader-status');
        if (statusElement) {
            statusElement.textContent = message;
            setTimeout(() => {
                statusElement.textContent = '';
            }, 1000);
        }
    }
    
    // 设置页面标题
    setPageTitle(title) {
        document.title = title;
        this.announce(`页面标题：${title}`);
    }
    
    // 创建跳转链接
    createSkipLinks() {
        const skipLinks = document.createElement('div');
        skipLinks.className = 'skip-links';
        skipLinks.innerHTML = `
            <a href="#main-content" class="skip-link">跳转到主内容</a>
            <a href="#sidebar" class="skip-link">跳转到导航</a>
        `;
        document.body.insertBefore(skipLinks, document.body.firstChild);
    }
    
    // 高对比度模式切换
    toggleHighContrast() {
        document.body.classList.toggle('high-contrast');
        const isHighContrast = document.body.classList.contains('high-contrast');
        this.announce(isHighContrast ? '已启用高对比度模式' : '已关闭高对比度模式');
    }
    
    // 字体大小调整
    adjustFontSize(size) {
        document.documentElement.style.fontSize = `${size}px`;
        this.announce(`字体大小已调整为${size}像素`);
    }
}

// 初始化可访问性管理器
const accessibilityManager = new AccessibilityManager();

// 导出到全局
window.AccessibilityManager = AccessibilityManager;
window.accessibilityManager = accessibilityManager;

// 添加跳转链接 - 已注释掉，因为用户反馈为bug
// document.addEventListener('DOMContentLoaded', () => {
//     accessibilityManager.createSkipLinks();
// });
