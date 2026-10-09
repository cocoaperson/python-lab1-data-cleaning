import gc
import os
import statistics
import threading
import time

import psutil


def measure(function, repeats=3):
    """Один прогрев, затем три запуска. RSS всего процесса, опрос каждые 2 мс."""
    warm = function()
    del warm
    gc.collect()
    times, peaks = [], []
    for _ in range(repeats):
        gc.collect()
        stop = threading.Event()
        process = psutil.Process(os.getpid())
        samples = [process.memory_info().rss]

        def watch(stop=stop, process=process, samples=samples):
            while not stop.wait(0.002):
                samples.append(process.memory_info().rss)

        monitor = threading.Thread(target=watch, daemon=True)
        monitor.start()
        start = time.perf_counter()
        result = function()
        seconds = time.perf_counter() - start
        samples.append(process.memory_info().rss)
        stop.set()
        monitor.join()
        times.append(seconds)
        peaks.append(max(samples) / 1_000_000)
        del result
    return {
        "seconds": statistics.median(times),
        "peak_mb": statistics.median(peaks),
        "runs_seconds": times,
        "runs_peak_mb": peaks,
    }
