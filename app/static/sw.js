// Service Worker for 灵瞳医疗AI系统
// 提供离线支持和缓存管理

const CACHE_NAME = 'lingtong-medical-ai-v1';
const urlsToCache = [
    '/',
    '/static/css/style.css',
    '/static/css/components/sidebar.css',
    '/static/css/components/chat.css',
    '/static/css/components/input.css',
    '/static/css/utilities.css',
    '/static/css/responsive.css',
    '/static/js/main.js',
    '/static/js/ui.js',
    '/static/js/api.js',
    '/static/js/utils.js',
    '/static/icons/system_logo.png',
    '/static/icons/user_avatar.png'
];

// 安装事件
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Service Worker: Caching files');
                return cache.addAll(urlsToCache);
            })
            .then(() => {
                console.log('Service Worker: All files cached');
                return self.skipWaiting();
            })
    );
});

// 激活事件
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Service Worker: Clearing old cache');
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            console.log('Service Worker: Activated');
            return self.clients.claim();
        })
    );
});

// 拦截请求
self.addEventListener('fetch', (event) => {
    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                // 如果缓存中有响应，直接返回
                if (response) {
                    return response;
                }
                
                // 否则从网络获取
                return fetch(event.request).then((response) => {
                    // 检查响应是否有效
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }
                    
                    // 克隆响应
                    const responseToCache = response.clone();
                    
                    // 添加到缓存
                    caches.open(CACHE_NAME)
                        .then((cache) => {
                            cache.put(event.request, responseToCache);
                        });
                    
                    return response;
                });
            })
            .catch(() => {
                // 网络失败时的离线页面
                if (event.request.destination === 'document') {
                    return caches.match('/');
                }
            })
    );
});

// 消息处理
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// 错误处理
self.addEventListener('error', (event) => {
    console.error('Service Worker error:', event.error);
});

// 推送通知处理
self.addEventListener('push', (event) => {
    if (event.data) {
        const options = {
            body: event.data.text(),
            icon: '/static/icons/system_logo.png',
            badge: '/static/icons/system_logo.png',
            vibrate: [100, 50, 100],
            data: {
                dateOfArrival: Date.now(),
                primaryKey: 1
            }
        };
        
        event.waitUntil(
            self.registration.showNotification('灵瞳医疗AI系统', options)
        );
    }
});

// 通知点击处理
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.openWindow('/')
    );
});

console.log('Service Worker: Registered and ready');
