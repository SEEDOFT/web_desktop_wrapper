/**
 * Drag-and-drop security hardening script.
 * Prevents dropping files on the web view from navigating away when ALLOW_FILE_DROP=false.
 */
(function () {
    function isDropzone(target) {
        return (
            target &&
            typeof target.closest === "function" &&
            target.closest("input[type=file], .dropzone, [data-dropzone]")
        );
    }

    window.addEventListener(
        "dragover",
        function (e) {
            if (!isDropzone(e.target)) {
                e.preventDefault();
            }
        },
        false
    );

    window.addEventListener(
        "drop",
        function (e) {
            if (!isDropzone(e.target)) {
                e.preventDefault();
            }
        },
        false
    );
})();
