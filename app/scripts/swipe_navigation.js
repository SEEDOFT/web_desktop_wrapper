/**
 * Horizontal mouse-wheel swipe navigation script.
 * Emits horizontalSwipe messages to CoreWebView2 for back/forward browser navigation.
 */
(function () {
    if (window.__wdwSwipeNavigationInstalled) {
        return;
    }
    window.__wdwSwipeNavigationInstalled = true;

    var THRESHOLD = parseInt("{{THRESHOLD}}", 10) || 100;
    var COOLDOWN_MS = parseInt("{{COOLDOWN_MS}}", 10) || 600;
    var lastNavigationAt = 0;

    function postDirection(direction) {
        var webview = window.chrome && window.chrome.webview;
        if (webview && webview.postMessage) {
            webview.postMessage({ type: "horizontalSwipe", direction: direction });
        }
    }

    function onWheel(event) {
        if (event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) {
            return;
        }
        if (Math.abs(event.deltaX) < THRESHOLD) {
            return;
        }
        var now = Date.now();
        if (now - lastNavigationAt < COOLDOWN_MS) {
            return;
        }
        lastNavigationAt = now;
        postDirection(event.deltaX > 0 ? "back" : "forward");
    }

    window.addEventListener("wheel", onWheel, true);
})();
