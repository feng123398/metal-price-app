// Service Worker - 金属价格分析工作台 PWA
const CACHE_NAME = 'metal-price-v1.0.0';
const ASSETS = [
  './金属价格分析工作台.html',
  './manifest.json',
  './icon-192.png',
  './icon-512.png'
];

// 安装时缓存核心资源
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      // ECharts从CDN加载，单独缓存
      return cache.addAll(ASSETS).catch(err => {
        console.log('部分资源缓存失败，不影响使用:', err);
      });
    })
  );
  self.skipWaiting();
});

// 激活时清理旧缓存
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// 请求拦截策略
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // 新浪财经API请求：总是走网络（实时数据），失败不缓存
  if (url.hostname.includes('sina.com.cn') || url.hostname.includes('sinajs.cn')) {
    event.respondWith(fetch(event.request).catch(() => new Response('', { status: 503 })));
    return;
  }

  // ECharts CDN：先网络，失败则缓存
  if (url.hostname.includes('cdn.jsdelivr.net')) {
    event.respondWith(
      fetch(event.request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => caches.match(event.request))
    );
    return;
  }

  // 本地资源：缓存优先
  event.respondWith(
    caches.match(event.request).then(cached => {
      return cached || fetch(event.request).then(response => {
        if (response.ok && url.origin === self.location.origin) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);
    })
  );
});
