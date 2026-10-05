/** Visible page-navigation feedback, independent of Livewire's bar configuration. */
(function () {
    if (window.top !== window || window.__wdwNavigationProgress) return;

    var timer;
    var startedAt = 0;
    var host;

    function mount() {
        if (!document.documentElement) return null;
        if (host && host.isConnected) return host;
        host = document.createElement("div");
        host.id = "wdw-navigation-progress";
        host.setAttribute("role", "progressbar");
        host.setAttribute("aria-label", "Loading page");
        var styles = {
            position: "fixed", top: "0", left: "0", width: "100%", height: "4px",
            "z-index": "2147483647", "pointer-events": "none", display: "none"
        };
        Object.keys(styles).forEach(function (key) {
            host.style.setProperty(key, styles[key], "important");
        });
        // Isolate the indicator from website styles and Livewire body replacement.
        var shadow = host.attachShadow({ mode: "open" });
        shadow.innerHTML = '<style>:host{color-scheme:light dark}' +
            '.track{height:4px;background:rgba(14,165,233,.2);overflow:hidden}' +
            '.bar{height:100%;width:40%;background:#0ea5e9;' +
            'box-shadow:0 0 8px #0ea5e9;animation:loading 1s ease-in-out infinite}' +
            '@keyframes loading{from{transform:translateX(-100%)}to{transform:translateX(350%)}}' +
            '@media(prefers-reduced-motion:reduce){.bar{animation:none;width:100%}}' +
            '</style><div class="track"><div class="bar"></div></div>';
        document.documentElement.appendChild(host);
        return host;
    }

    function start() {
        clearTimeout(timer);
        startedAt = Date.now();
        var element = mount();
        if (element) element.style.setProperty("display", "block", "important");
        // Avoid a stuck indicator if a website aborts navigation without a completion event.
        timer = setTimeout(hide, 60000);
    }

    function hide() {
        clearTimeout(timer);
        startedAt = 0;
        if (host) host.style.setProperty("display", "none", "important");
    }

    function finish() {
        if (!startedAt) return;
        clearTimeout(timer);
        timer = setTimeout(hide, Math.max(0, 180 - (Date.now() - startedAt)));
    }

    window.__wdwNavigationProgress = { start: start, finish: finish };
    document.addEventListener("livewire:navigate", function (event) {
        queueMicrotask(function () { if (!event.defaultPrevented) start(); });
    });
    document.addEventListener("livewire:navigating", start);
    document.addEventListener("livewire:navigated", finish);

    // Native links/forms also need feedback when they do not use wire:navigate.
    document.addEventListener("click", function (event) {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        var anchor = event.target && event.target.closest && event.target.closest("a[href]");
        if (!anchor || anchor.hasAttribute("download") || (anchor.target && anchor.target !== "_self")) return;
        var destination;
        try { destination = new URL(anchor.href, window.location.href); } catch (e) { return; }
        if (destination.origin !== window.location.origin ||
            (destination.pathname === window.location.pathname && destination.search === window.location.search)) return;
        queueMicrotask(function () { if (!event.defaultPrevented) start(); });
    });
    document.addEventListener("submit", function (event) {
        if (event.target.target && event.target.target !== "_self") return;
        queueMicrotask(function () { if (!event.defaultPrevented) start(); });
    });
    window.addEventListener("pageshow", finish);
    window.addEventListener("unhandledrejection", finish);
})();
