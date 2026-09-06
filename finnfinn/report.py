import time

last_tick = time.monotonic()  # refreshed every ticker pass; the watchdog in __main__ restarts the process once it is > 300 s old


def loop(stop):
    """30-s WIB ticker: claim due jobs via db.claim, run them, refresh last_tick every pass."""
    global last_tick
    while not stop.is_set():
        last_tick = time.monotonic()
        stop.wait(30)


def due(now):
    """→ [(kind, period_key, fn)] due at the WIB datetime `now`, including catch-up windows."""
    raise NotImplementedError


def build_harian(day):
    """HTML daily report for the WIB date `day`."""
    raise NotImplementedError


def build_mingguan(monday):
    """HTML weekly report for the Mon–Sun week starting at `monday`."""
    raise NotImplementedError


def build_bulanan(year, month):
    """HTML monthly report."""
    raise NotImplementedError


def build_tahunan(year):
    """HTML yearly report."""
    raise NotImplementedError
