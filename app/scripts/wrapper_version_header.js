/**
 * Client-side request interceptor.
 * Injects X-Wrapper-Version into same-origin fetch and XMLHttpRequest calls.
 */
(function () {
    var wrapperVersion = "{{WRAPPER_VERSION}}";
    if (!wrapperVersion || window.__wdwWrapperVersionHeaderInstalled) {
        return;
    }
    window.__wdwWrapperVersionHeaderInstalled = true;

    // Keep Livewire's own navigation progress visible above fixed page chrome.
    // Livewire owns its lifecycle; never force an idle indicator to display.
    function preserveNavigationProgress() {
        if (!document.head || document.getElementById("wdw-navigation-progress-style")) {
            return;
        }
        var style = document.createElement("style");
        style.id = "wdw-navigation-progress-style";
        style.textContent = "#nprogress { pointer-events: none; } " +
            "#nprogress .bar { position: fixed !important; top: 0 !important; " +
            "left: 0 !important; z-index: 2147483647 !important; } " +
            "#nprogress .spinner { z-index: 2147483647 !important; }";
        document.head.appendChild(style);
    }
    preserveNavigationProgress();
    document.addEventListener("DOMContentLoaded", preserveNavigationProgress, { once: true });
    document.addEventListener("livewire:navigated", preserveNavigationProgress);

    try {
        window.WRAPPER_VERSION = wrapperVersion;
        window.X_WRAPPER_VERSION = wrapperVersion;
        document.cookie = "x_wrapper_version=" + encodeURIComponent(wrapperVersion) + "; path=/; SameSite=Lax";
    } catch (e) {}

    // Intercept window.fetch
    var origFetch = window.fetch;
    if (origFetch) {
        window.fetch = function (input, init) {
            var requestUrl = input instanceof URL ? input.href : (typeof input === "string" ? input : input && input.url);
            try {
                if (requestUrl && new URL(requestUrl, window.location.href).origin !== window.location.origin) {
                    return origFetch.call(this, input, init);
                }
            } catch (e) {
                return origFetch.call(this, input, init);
            }
            var originalHeaders = init && init.headers;
            if (!originalHeaders && typeof Request !== "undefined" && input instanceof Request) {
                originalHeaders = input.headers;
            }
            var headers = new Headers(originalHeaders || {});
            headers.set("X-Wrapper-Version", wrapperVersion);
            var nextInit = Object.assign({}, init || {}, { headers: headers });
            return origFetch.call(this, input, nextInit);
        };
    }

    // Intercept XMLHttpRequest
    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
        var res = origOpen.apply(this, arguments);
        try {
            if (new URL(url, window.location.href).origin === window.location.origin) {
                this.setRequestHeader("X-Wrapper-Version", wrapperVersion);
            }
        } catch (e) {}
        return res;
    };
})();
