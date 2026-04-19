"""
Watcher Service - Monitors the data directory for new pitch decks and auto-ingests them.
"""
import os
import threading


def start_watcher():
    """
    Start the file system watcher for the data/uploads directory.
    Uses polling to detect new files and trigger auto-ingestion.
    Runs in a background daemon thread so it doesn't block startup.
    """
    watch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/uploads"))
    os.makedirs(watch_dir, exist_ok=True)

    def _poll():
        import time
        seen = set(os.listdir(watch_dir)) if os.path.exists(watch_dir) else set()
        while True:
            try:
                time.sleep(10)  # Poll every 10 seconds
                if not os.path.exists(watch_dir):
                    continue
                current = set(os.listdir(watch_dir))
                new_files = current - seen
                for filename in new_files:
                    filepath = os.path.join(watch_dir, filename)
                    print(f"[Watcher] New file detected: {filename}")
                    # Future: auto-trigger ingestion pipeline here
                seen = current
            except Exception as e:
                print(f"[Watcher] Poll error: {e}")

    thread = threading.Thread(target=_poll, daemon=True, name="FileWatcher")
    thread.start()
    print(f"[Watcher] Monitoring: {watch_dir}")
