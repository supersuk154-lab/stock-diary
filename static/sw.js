// AI 주식메이트 서비스 워커
self.addEventListener('install', function(e) { self.skipWaiting(); });
self.addEventListener('activate', function(e) { return self.clients.claim(); });
self.addEventListener('fetch', function(e) {});
