"""Request-local state. Analysis routes serialise legacy RNG access and restore it afterwards;
record-keeping routes bypass the lock (see guard.UNSEEDED)."""
from contextlib import contextmanager
from contextvars import ContextVar
import random
import threading

current_request = ContextVar("aitiolin_request", default=None)
_rng_lock = threading.RLock()


@contextmanager
def seeded(seed):
    import numpy as np
    with _rng_lock:
        old_py, old_np = random.getstate(), np.random.get_state()
        random.seed(seed)
        np.random.seed(seed)
        try:
            yield
        finally:
            random.setstate(old_py)
            np.random.set_state(old_np)
