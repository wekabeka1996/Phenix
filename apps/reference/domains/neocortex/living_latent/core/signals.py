# SPDX-License-Identifier: MIT
import signal
import time
from .panic_stop import panic_guard
try:
    from living_latent.telemetry.blackbox import log_event as bb_log
except Exception:
    bb_log = None

def install_handlers(run_dir: str, state: dict):
    """Install simple SIGINT/SIGTERM handlers that log a SIGNAL event and call panic_guard.

    This is best-effort: failures during install or handler execution are ignored so the
    main process can continue to run in constrained environments (CI, tests).
    """

    def _handler(signum, frame):
        try:
            if bb_log:
                bb_log(run_dir, "SIGNAL", {"signum": signum, "ts": time.time()})
        except Exception:
            # Never let logging failures break the handler
            pass
        try:
            panic_guard(run_dir, state)
        finally:
            raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except Exception:
            # Some test or windows environments may not allow signals
            pass
