import threading
import time
import os
import sys
import webview
from server import app, init_db

PORT = 5050


def start_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)


def main():
    # Resolve DB path when running as a bundled .app
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        # Place DB next to the .app in the user's home so data persists across updates
        db_dir = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'DudumDashboard')
        os.makedirs(db_dir, exist_ok=True)
        import server
        server.DB_PATH = os.path.join(db_dir, 'chiro.db')

    init_db()

    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    time.sleep(0.8)  # let Flask bind

    webview.create_window(
        'Dudum Dashboard',
        f'http://127.0.0.1:{PORT}',
        width=1440,
        height=900,
        min_size=(900, 600),
    )
    webview.start()


if __name__ == '__main__':
    main()
