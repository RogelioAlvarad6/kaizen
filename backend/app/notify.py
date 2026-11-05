"""Windows desktop notifications (falls back to the console elsewhere)."""
import logging
import sys

log = logging.getLogger("sims.notify")


def toast(title: str, message: str) -> None:
    message = (message or "").strip()
    if len(message) > 240:
        message = message[:237] + "..."
    if sys.platform == "win32":
        try:
            from winotify import Notification

            Notification(app_id="SIMS AI Office", title=title[:60], msg=message or " ").show()
            return
        except Exception as e:  # never fail a workflow because a toast failed
            log.warning("toast failed: %s", e)
    log.info("NOTIFY %s: %s", title, message)
