// app/static/js/utils/performance.js
// 性能优化工具类

class PerformanceManager {
    constructor() {
        this.lazyLoadImages = [];
        this.intersectionObserver = null;
        this.initLazyLoading();
    }
    
    // 初始化懒加载
    initLazyLoading() {
        if ('IntersectionObserver' in window) {
            this.intersectionObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        this.loadImage(entry.target);
                        this.intersectionObserver.unobserve(entry.target);
                    }
                });
            }, {
                rootMargin: '50px'
            });
        }
    }
    
    // 加载图片
    loadImage(img) {
        if (img.dataset.src) {
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
            img.classList.add('loaded');
        }
    }
    
    // 注册懒加载图片
    registerLazyImage(img) {
        if (this.intersectionObserver) {
            this.intersectionObserver.observe(img);
        } else {
            // fallback for older browsers
            this.loadImage(img);
        }
    }
    
    // 防抖函数
    static debounce(func, wait, immediate = false) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func.apply(this, args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func.apply(this, args);
        };
    }
    
    // 节流函数
    static throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
    
    // 动态导入模块
    static async importModule(modulePath) {
        try {
            const module = await import(modulePath);
            return module;
        } catch (error) {
            console.error(`Failed to import module: ${modulePath}`, error);
            throw error;
        }
    }
    
    // 预加载关键资源
    static preloadResource(url, type = 'image') {
        const link = document.createElement('link');
        link.rel = 'preload';
        link.href = url;
        link.as = type;
        document.head.appendChild(link);
    }
    
    // 内存清理
    static cleanup() {
        // 清理事件监听器
        const elements = document.querySelectorAll('[data-cleanup]');
        elements.forEach(element => {
            const events = element.dataset.cleanup.split(',');
            events.forEach(event => {
                element.removeEventListener(event.trim(), null);
            });
        });
        
        // 清理定时器
        if (window.appTimers) {
            window.appTimers.forEach(timerId => {
                clearTimeout(timerId);
                clearInterval(timerId);
            });
            window.appTimers = [];
        }
    }
    
    // 虚拟滚动（用于大列表）
    static createVirtualScroll(container, items, itemHeight, renderItem) {
        const containerHeight = container.clientHeight;
        const visibleItems = Math.ceil(containerHeight / itemHeight) + 2;
        let scrollTop = 0;
        
        const virtualContainer = document.createElement('div');
        virtualContainer.style.height = `${items.length * itemHeight}px`;
        virtualContainer.style.position = 'relative';
        
        const visibleContainer = document.createElement('div');
        visibleContainer.style.position = 'absolute';
        visibleContainer.style.top = '0';
        visibleContainer.style.width = '100%';
        
        virtualContainer.appendChild(visibleContainer);
        container.appendChild(virtualContainer);
        
        const updateVisible = PerformanceManager.throttle(() => {
            const startIndex = Math.floor(scrollTop / itemHeight);
            const endIndex = Math.min(startIndex + visibleItems, items.length);
            
            visibleContainer.innerHTML = '';
            visibleContainer.style.transform = `translateY(${startIndex * itemHeight}px)`;
            
            for (let i = startIndex; i < endIndex; i++) {
                const itemElement = renderItem(items[i], i);
                visibleContainer.appendChild(itemElement);
            }
        }, 16);
        
        container.addEventListener('scroll', (e) => {
            scrollTop = e.target.scrollTop;
            updateVisible();
        });
        
        updateVisible();
    }
    
    // 监控性能指标
    static monitorPerformance() {
        if ('PerformanceObserver' in window) {
            // 监控 LCP (Largest Contentful Paint)
            const lcpObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const lastEntry = entries[entries.length - 1];
                console.log('LCP:', lastEntry.startTime);
            });
            lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
            
            // 监控 FID (First Input Delay)
            const fidObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                entries.forEach(entry => {
                    console.log('FID:', entry.processingStart - entry.startTime);
                });
            });
            fidObserver.observe({ entryTypes: ['first-input'] });
            
            // 监控 CLS (Cumulative Layout Shift)
            const clsObserver = new PerformanceObserver((list) => {
                let clsValue = 0;
                const entries = list.getEntries();
                entries.forEach(entry => {
                    if (!entry.hadRecentInput) {
                        clsValue += entry.value;
                    }
                });
                console.log('CLS:', clsValue);
            });
            clsObserver.observe({ entryTypes: ['layout-shift'] });
        }
    }
    
    // 优化图片加载
    static optimizeImage(img, options = {}) {
        const {
            quality = 0.8,
            maxWidth = 1920,
            maxHeight = 1080,
            format = 'webp'
        } = options;
        
        if (img.naturalWidth > maxWidth || img.naturalHeight > maxHeight) {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            
            const ratio = Math.min(maxWidth / img.naturalWidth, maxHeight / img.naturalHeight);
            canvas.width = img.naturalWidth * ratio;
            canvas.height = img.naturalHeight * ratio;
            
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            
            return new Promise((resolve) => {
                canvas.toBlob(resolve, `image/${format}`, quality);
            });
        }
        
        return Promise.resolve(null);
    }
    
    // 开始性能监控
    static startMonitoring() {
        if (typeof window.performanceManager !== 'undefined') {
            console.log('Performance monitoring started');
            
            // 监控页面加载时间
            window.addEventListener('load', () => {
                window.performanceManager.measurePageLoad();
            });
            
            // 监控内存使用
            window.performanceManager.setupMemoryMonitoring();
            
            // 监控长任务
            if ('PerformanceObserver' in window) {
                const observer = new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    entries.forEach(entry => {
                        if (entry.duration > 50) {
                            console.warn('Long task detected:', entry.name, entry.duration);
                        }
                    });
                });
                observer.observe({ entryTypes: ['longtask'] });
            }
        }
    }
    
    // 监控性能指标
    static monitorPerformance() {
        if (typeof window.performanceManager !== 'undefined') {
            setInterval(() => {
                window.performanceManager.logMetrics();
            }, 30000); // 每30秒记录一次
        }
    }
}

// 初始化性能管理器
const performanceManager = new PerformanceManager();

// 导出到全局
window.PerformanceManager = PerformanceManager;
window.performanceManager = performanceManager;

// 页面加载完成后启动性能监控
document.addEventListener('DOMContentLoaded', () => {
    PerformanceManager.monitorPerformance();
});
