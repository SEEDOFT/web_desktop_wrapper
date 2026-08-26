/**
 * Client-side request interceptor.
 * Injects X-Wrapper-Version header into window.fetch, XMLHttpRequest, and form submissions.
 */
(function () {
    var wrapperVersion = "{{WRAPPER_VERSION}}";
    if (!wrapperVersion) {
        return;
    }

    try {
        window.WRAPPER_VERSION = wrapperVersion;
        window.X_WRAPPER_VERSION = wrapperVersion;
        document.cookie = "x_wrapper_version=" + encodeURIComponent(wrapperVersion) + "; path=/; SameSite=Lax";
    } catch (e) {}

    // Intercept window.fetch
    var origFetch = window.fetch;
    if (origFetch) {
        window.fetch = function (input, init) {
            init = init || {};
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

    // Inject hidden inputs and intercept standard form POST submissions
    function enhanceFormInputs(form) {
        if (!form) return;
        var names = ["X-Wrapper-Version", "x_wrapper_version", "wrapper_version"];
        for (var i = 0; i < names.length; i++) {
            var name = names[i];
            if (!form.querySelector('input[name="' + name + '"]')) {
                var input = document.createElement("input");
                input.type = "hidden";
                input.name = name;
                input.value = wrapperVersion;
                form.appendChild(input);
            }
        }
    }

    document.addEventListener("submit", function (e) {
        var form = e.target;
        if (!form || form.tagName !== "FORM") return;
        enhanceFormInputs(form);

        if (form.getAttribute("data-wrapper-handled") === "true") {
            return;
        }

        // If form has file uploads, let native submit handle it with hidden inputs
        var fileInputs = form.querySelectorAll('input[type="file"]');
        for (var f = 0; f < fileInputs.length; f++) {
            if (fileInputs[f].files && fileInputs[f].files.length > 0) {
                return;
            }
        }

        var method = (form.method || "GET").toUpperCase();
        if (method !== "POST") {
            return;
        }

        // Handle POST form submission via fetch to include X-Wrapper-Version header
        e.preventDefault();
        e.stopPropagation();

        var action = form.action || window.location.href;
        var formData = new FormData(form);
        var encType = form.enctype || form.encoding || "application/x-www-form-urlencoded";
        var options = {
            method: "POST",
            headers: {
                "X-Wrapper-Version": wrapperVersion,
            },
            credentials: "include",
        };

        if (encType.indexOf("urlencoded") !== -1) {
            options.headers["Content-Type"] = "application/x-www-form-urlencoded";
            options.body = new URLSearchParams(formData).toString();
        } else {
            options.body = formData;
        }

        origFetch(action, options).then(function (response) {
            if (response.redirected && response.url) {
                window.location.href = response.url;
            } else if (response.ok) {
                var contentType = response.headers.get("content-type") || "";
                if (contentType.indexOf("application/json") !== -1) {
                    return response.json().then(function (json) {
                        if (json.redirect || json.url || json.location) {
                            window.location.href = json.redirect || json.url || json.location;
                        } else {
                            window.location.reload();
                        }
                    }).catch(function () {
                        window.location.href = response.url || action;
                    });
                }
                return response.text().then(function (html) {
                    if (response.url && response.url !== window.location.href) {
                        window.location.href = response.url;
                    } else {
                        document.open();
                        document.write(html);
                        document.close();
                    }
                });
            } else {
                return response.text().then(function (html) {
                    document.open();
                    document.write(html);
                    document.close();
                });
            }
        }).catch(function () {
            // Fallback to native submission if fetch encounters an error
            form.setAttribute("data-wrapper-handled", "true");
            form.submit();
        });
    }, true);
})();
