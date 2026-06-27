from contextlib import contextmanager
from threading import Lock


_slot_locks = {}
_slot_locks_guard = Lock()


@contextmanager
def slot_lock(slot_id: str):
    """
    Candado en memoria por horario.

    Evita que dos usuarios intenten crear o mover una cita
    al mismo horario exactamente al mismo tiempo.
    """

    with _slot_locks_guard:
        if slot_id not in _slot_locks:
            _slot_locks[slot_id] = Lock()

        lock = _slot_locks[slot_id]

    lock.acquire()

    try:
        yield
    finally:
        lock.release()