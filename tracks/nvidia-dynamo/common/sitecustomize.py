"""Opt-in: freeze Python's GC after warmup in Dynamo SGLang worker processes.

The 8K/128K study logged generation-2 collections of ~890K objects every ~11 s,
pausing token output for 0.34-0.45 s on every stream of the worker. SGLang
recommends freeze_gc after warmup, but Dynamo 1.4.0 never calls it. When
SERVING_GC_FREEZE_AFTER_S is set, this hook (mounted on PYTHONPATH) collects once and
moves every surviving object to the permanent generation after that many seconds,
so later full collections skip the long-lived startup objects.
"""
import os

_delay = os.environ.get('SERVING_GC_FREEZE_AFTER_S')
if _delay:
    import gc
    import threading

    def _freeze():
        gc.collect()
        gc.freeze()
        print(f'[sitecustomize] gc.freeze() pid={os.getpid()} frozen={gc.get_freeze_count()}', flush=True)

    _timer = threading.Timer(float(_delay), _freeze)
    _timer.daemon = True
    _timer.start()
