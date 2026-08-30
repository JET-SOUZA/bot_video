"""Single JetBot V2 bootstrap.

Centralizes runtime patch order so Docker no longer owns a fragile chain of ten
inline imports. Runtime mutation happens explicitly here, and final assertions
make accidental wrapper overwrites fail at startup instead of silently changing
production behavior.
"""

import os

# Optional staging-only diagnostics must be installed before Shopee code prints.
if os.getenv("SHOPEE_DIAGNOSTICS", "0").strip().lower() in {"1", "true", "yes", "on"}:
    import shopee_diag_capture  # noqa: F401

import sitecustomize  # noqa: F401,E402
import shopee_structured_patch  # noqa: F401,E402
import shopee_sourcemap_probe  # noqa: F401,E402
import shopee_frontend_api_patch  # noqa: F401,E402
import shopee_timeline_patch  # noqa: F401,E402
import media_fidelity_patch  # noqa: F401,E402
import telegram_fit_patch  # noqa: F401,E402
import youtube_auth_patch  # noqa: F401,E402
import shopee_diag_telegram_patch  # noqa: F401,E402
import run_v2_fallback as entry  # noqa: E402


def _apply_runtime():
    entry.apply_runtime_policy()


def _verify_runtime():
    app = entry.runtime.app
    if app.download_media is not telegram_fit_patch.download_media_with_telegram_fit:
        raise RuntimeError("JetBot V2 bootstrap: Telegram size-fit is not the final media wrapper")
    if telegram_fit_patch._ORIGINAL_DOWNLOAD_MEDIA is not entry.download_media_with_shopee_policy:
        raise RuntimeError("JetBot V2 bootstrap: Shopee policy is not directly under Telegram size-fit")
    if app.download_youtube_file_v2 is not youtube_auth_patch.download_youtube_file_guarded:
        raise RuntimeError("JetBot V2 bootstrap: YouTube auth guard was overwritten")
    if entry._ALLOW_MARKED_FALLBACK:
        raise RuntimeError("JetBot V2 bootstrap: marked Shopee fallback must stay disabled")
    if not entry._RUNTIME_APPLIED:
        raise RuntimeError("JetBot V2 bootstrap: explicit runtime policy was not applied")
    cookie_state = youtube_auth_patch._cookie_session_state()
    print(f"[JetBot YT] cookie_session={cookie_state} (values are never logged)")
    print("[JetBot V2] bootstrap runtime order verified; Shopee clean-only policy active")


def main():
    _apply_runtime()
    _verify_runtime()
    entry.runtime.app.main()


if __name__ == "__main__":
    main()
