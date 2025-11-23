// app/static/js/performance.js
// 性能监控和优化 (主模块)

// 导出性能管理器到全局
window.PerformanceManager = window.PerformanceManager || class {
    constructor() {
        this.metrics = {
            pageLoadTime: 0,
            renderTime: 0,
            apiCallTimes: new Map(),
            memoryUsage: 0
        };
        this.init();
    }
    
    init() {
        this.measurePageLoad();
        this.measureRenderTime();
        this.setupMemoryMonitoring();
    }
    
    measurePageLoad() {
        if (performance.timing) {
            this.metrics.pageLoadTime = performance.timing.loadEventEnd - performance.timing.navigationStart;
        }
    }
    
    measureRenderTime() {
        if (performance.getEntriesByType) {
            const paintEntries = performance.getEntriesByType('paint');
            const fcp = paintEntries.find(entry => entry.name === 'first-contentful-paint');
            if (fcp) {
                this.metrics.renderTime = fcp.startTime;
            }
        }
    }
    
    setupMemoryMonitoring() {
        if (performance.memory) {
            setInterval(() => {
                this.metrics.memoryUsage = performance.memory.usedJSHeapSize;
            }, 10000); // 每10秒监控一次
        }
    }
    
    measureApiCall(name, startTime, endTime) {
        const duration = endTime - startTime;
        if (!this.metrics.apiCallTimes.has(name)) {
            this.metrics.apiCallTimes.set(name, []);
        }
        this.metrics.apiCallTimes.get(name).push(duration);
    }
    
    getMetrics() {
        return this.metrics;
    }
    
    logMetrics() {
        console.log('Performance Metrics:', this.metrics);
    }
};

// 创建全局实例
window.performanceManager = new window.PerformanceManager();
