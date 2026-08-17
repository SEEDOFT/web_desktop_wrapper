"""Application constants used throughout the codebase.

This module centralizes magic numbers and configuration values to improve
maintainability and make parameters easily adjustable.
"""

# ============================================================================
# Keyboard and Input Constants
# ============================================================================

# Keyboard key code mappings (Windows virtual key codes)
KEYBOARD_KEY_CODES = {
    82: "r",        # R key
    116: "f5",      # F5 key
    187: "=",       # OEM_Plus (= key)
    107: "=",       # Numpad Add
    189: "-",       # OEM_Minus (- key)
    109: "-",       # Numpad Subtract
    48: "0",        # D0 (0 key)
    96: "0",        # Numpad 0
    70: "f",        # F key
    80: "p",        # P key
    87: "w",        # W key
    36: "home",     # Home key
    46: "delete",   # Delete key
    122: "f11",     # F11 key
    37: "left",     # Left arrow key
    39: "right",    # Right arrow key
}

# ============================================================================
# Shortcut Timing Constants
# ============================================================================

# Debounce time for keyboard shortcuts to prevent rapid successive triggers
SHORTCUT_DEBOUNCE_SECONDS = 0.4

# ============================================================================
# Swipe Navigation Constants (JavaScript in WebView)
# ============================================================================

# Minimum horizontal mouse wheel delta to trigger navigation
SWIPE_THRESHOLD_PIXELS = 100

# Cooldown period between navigation swipes to prevent accidental triggers
SWIPE_COOLDOWN_MS = 600

# ============================================================================
# WebView2 Error Constants
# ============================================================================

# WebView2 operation cancelled error status code
# See: https://learn.microsoft.com/en-us/microsoft-edge/webview2/reference/win32/webview2-idl?view=webview2-1.0.1823.32#webview2_web_error_status
OPERATION_CANCELED_WEB_ERROR_STATUS = 14

# ============================================================================
# Navigation Constants
# ============================================================================

# Error page text shown when navigation fails
NAVIGATION_ERROR_MESSAGE = (
    "The application could not be reached. "
    "Check your connection and try again."
)

# Default icon file when config icon path is empty
DEFAULT_ICON_PATH = "assets/digi_express.ico"
