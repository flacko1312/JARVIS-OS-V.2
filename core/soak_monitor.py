"""Non-destructive process resource sampling for short and manual soak runs."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Callable

import psutil


@dataclass(frozen=True)
class ResourceSample:
    elapsed_seconds: float
    rss_bytes: int
    threads: int
    handles: int | None
    children: int
    browser_workers: int
    zombie_children: int
    asyncio_tasks: int | None


@dataclass(frozen=True)
class SoakResult:
    passed: bool
    duration_seconds: float
    samples: tuple[ResourceSample, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "duration_seconds": self.duration_seconds,
            "warnings": list(self.warnings),
            "samples": [asdict(sample) for sample in self.samples],
        }


def _asyncio_task_count() -> int | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    return len([task for task in asyncio.all_tasks(loop) if not task.done()])


def sample_process(process: psutil.Process | None = None, *, elapsed: float = 0.0) -> ResourceSample:
    process = process or psutil.Process()
    children = process.children(recursive=True)
    names = []
    zombies = 0
    for child in children:
        try:
            names.append(child.name().casefold())
            zombies += child.status() == psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    try:
        handles = process.num_handles() if hasattr(process, "num_handles") else None
    except (psutil.Error, OSError):
        handles = None
    return ResourceSample(
        elapsed_seconds=round(elapsed, 3),
        rss_bytes=process.memory_info().rss,
        threads=process.num_threads(),
        handles=handles,
        children=len(children),
        browser_workers=sum(any(token in name for token in ("chrome", "msedge", "playwright")) for name in names),
        zombie_children=zombies,
        asyncio_tasks=_asyncio_task_count(),
    )


def analyze_samples(samples: list[ResourceSample], *, rss_growth_limit_mb: float = 96.0,
                    count_growth_limit: int = 12) -> tuple[str, ...]:
    if len(samples) < 2:
        return ()
    first, last = samples[0], samples[-1]
    warnings: list[str] = []
    rss_growth = (last.rss_bytes - first.rss_bytes) / (1024 * 1024)
    if rss_growth > rss_growth_limit_mb and all(
        later.rss_bytes >= earlier.rss_bytes for earlier, later in zip(samples, samples[1:])
    ):
        warnings.append(f"monotonic RSS growth: {rss_growth:.1f} MB")
    for field in ("threads", "children", "browser_workers"):
        growth = getattr(last, field) - getattr(first, field)
        if growth > count_growth_limit:
            warnings.append(f"{field} grew by {growth}")
    if first.handles is not None and last.handles is not None:
        growth = last.handles - first.handles
        if growth > count_growth_limit * 4:
            warnings.append(f"handles grew by {growth}")
    if any(sample.zombie_children for sample in samples):
        warnings.append("zombie child process detected")
    return tuple(warnings)


def run_soak(duration_seconds: float = 10.0, interval_seconds: float = 1.0,
             workload: Callable[[], None] | None = None) -> SoakResult:
    duration = max(0.1, min(float(duration_seconds), 3600.0))
    interval = max(0.05, min(float(interval_seconds), 30.0))
    process = psutil.Process()
    started = time.monotonic()
    samples: list[ResourceSample] = []
    while True:
        elapsed = time.monotonic() - started
        samples.append(sample_process(process, elapsed=elapsed))
        if elapsed >= duration:
            break
        if workload is not None:
            workload()
        time.sleep(min(interval, max(0.0, duration - elapsed)))
    warnings = analyze_samples(samples)
    return SoakResult(not warnings, time.monotonic() - started, tuple(samples), warnings)
