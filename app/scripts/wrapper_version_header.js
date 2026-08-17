/**
 * Client-side request interceptor.
 * Injects X-Wrapper-Version header into window.fetch and XMLHttpRequest.
 */
(function () {
    var wrapperVersion = "{{WRAPPER_VERSION}}";
    if (!wrapperVersion) {
        return;
    }

    // Intercept window.fetch
    var origFetch = window.fetch;
    if (origFetch) {
        window.fetch = function (input, init) {
            init = init || {};
            // If input is a Request object, attach header to input.headers
            if (typeof Request !== "undefined" && input instanceof Request) {
                try {
                    input.headers.set("X-Wrapper-Version", wrapperVersion);
                } catch (e) {}
            }
            if (init.headers) {
                if (typeof Headers !== "undefined" && init.headers instanceof Headers) {
                    init.headers.set("X-Wrapper-Version", wrapperVersion);
                } else if (Array.isArray(init.headers)) {
                    init.headers.push(["X-Wrapper-Version", wrapperVersion]);
                } else {
                    init.headers["X-Wrapper-Version"] = wrapperVersion;
                }
            } else {
                init.headers = { "X-Wrapper-Version": wrapperVersion };
            }
            return origFetch.call(this, input, init);
        };
    }

    // Intercept XMLHttpRequest
    var origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function () {
        var res = origOpen.apply(this, arguments);
        try {
            this.setRequestHeader("X-Wrapper-Version", wrapperVersion);
        } catch (e) {}
        return res;
    };

    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function () {
        try {
            this.setRequestHeader("X-Wrapper-Version", wrapperVersion);
        } catch (e) {}
        return origSend.apply(this, arguments);
    };
})();
