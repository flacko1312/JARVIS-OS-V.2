from dataclasses import replace

from core.soak_monitor import ResourceSample, analyze_samples, run_soak


def _sample(rss_mb=100, threads=5, handles=20, children=0, browsers=0, zombies=0):
    return ResourceSample(0, rss_mb * 1024 * 1024, threads, handles, children, browsers, zombies, None)


def test_short_soak_collects_multiple_samples_without_real_services():
    calls = []
    result = run_soak(0.12, 0.05, workload=lambda: calls.append(1))
    assert result.passed
    assert len(result.samples) >= 3
    assert calls


def test_stable_resources_pass():
    assert analyze_samples([_sample(), _sample(rss_mb=105, threads=6)]) == ()


def test_monotonic_rss_runaway_is_reported():
    samples = [_sample(rss_mb=100), _sample(rss_mb=150), _sample(rss_mb=210)]
    assert "monotonic RSS growth" in analyze_samples(samples)[0]


def test_non_monotonic_peak_is_not_claimed_as_runaway():
    samples = [_sample(rss_mb=100), _sample(rss_mb=230), _sample(rss_mb=205)]
    assert not any("RSS" in warning for warning in analyze_samples(samples))


def test_threads_children_browser_and_zombies_are_detected():
    first = _sample()
    last = _sample(threads=20, children=15, browsers=14, zombies=1)
    warnings = analyze_samples([first, last])
    assert any("threads" in warning for warning in warnings)
    assert any("children" in warning for warning in warnings)
    assert any("browser_workers" in warning for warning in warnings)
    assert any("zombie" in warning for warning in warnings)


def test_handle_growth_has_separate_threshold():
    first = _sample()
    last = replace(first, handles=100)
    assert any("handles" in warning for warning in analyze_samples([first, last]))
