import logging
import os
import signal
import sys
import threading
import time

from . import bot, config, db, report, web

log = logging.getLogger("finnfinn")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN kosong — isi lewat environment")
        sys.exit(1)
    if config.DEV_NO_AUTH:
        log.warning("WARNING: DEV_NO_AUTH=1 — auth disabled for local peers; never run this on a public host")
    if not config.OWNER_IDS:
        log.warning("WARNING: OWNER_IDS kosong — instance ini mode tamu saja (guest-only)")
    db.init(config.DB_PATH)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    threads = [threading.Thread(target=t, args=(stop,), daemon=True, name=n)
               for n, t in (("report", report.loop), ("web", web.serve), ("bot", bot.poll_forever))]
    for t in threads:
        t.start()
    log.info("scheduler tz=Asia/Jakarta")
    log.info("watchdog armed")
    while not stop.wait(30):
        if time.monotonic() - report.last_tick > 300:
            log.error("scheduler macet > 5 menit, restart otomatis")
            report.alert("⚠️ Finn Finn: scheduler macet > 5 menit, restart otomatis.")
            os._exit(1)
    for t in threads:  # report first so a claimed-but-unsent job finishes before the process dies
        t.join(timeout=10)
    db.close()
    log.info("berhenti")


if __name__ == "__main__":
    main()
