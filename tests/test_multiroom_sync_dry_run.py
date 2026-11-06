import pytest

from core.multiroom_dry_run import Route, RouteError
from core.multiroom_sync_dry_run import SpeakerProbe, Coordination, simulate_sync


ROUTES = (Route("despacho", "windows"), Route("comedor", "ubuntu"))


def test_compensation_for_latency():
    assert simulate_sync(ROUTES, {"windows": SpeakerProbe(True, 40), "ubuntu": SpeakerProbe(True, 70)}) == (
        Coordination("despacho", "windows", 30),
        Coordination("comedor", "ubuntu", 0),
    )


def test_equal_latency():
    assert all(x.offset_ms == 0 for x in simulate_sync(ROUTES, {"windows": SpeakerProbe(True, 20), "ubuntu": SpeakerProbe(True, 20)}))


@pytest.mark.parametrize("probes", [
    {"windows": SpeakerProbe(True, 20)},
    {"windows": SpeakerProbe(True, 20), "ubuntu": SpeakerProbe(False, 20)},
    {"windows": SpeakerProbe(True, 20), "ubuntu": SpeakerProbe(True, 200)},
    {"windows": SpeakerProbe(True, 20), "ubuntu": SpeakerProbe(True, 501)},
    {"windows": SpeakerProbe(True, 20), "ubuntu": SpeakerProbe(True, -1)},
    {"windows": SpeakerProbe(True, 20), "ubuntu": SpeakerProbe(True, True)},
])
def test_fail_closed(probes):
    with pytest.raises(RouteError):
        simulate_sync(ROUTES, probes)


def test_reject_duplicate_and_empty_routes():
    with pytest.raises(RouteError):
        simulate_sync((), {})
    with pytest.raises(RouteError):
        simulate_sync((ROUTES[0], ROUTES[0]), {"windows": SpeakerProbe(True, 20)})


def test_does_not_mutate_probes():
    probes = {"windows": SpeakerProbe(True, 10), "ubuntu": SpeakerProbe(True, 15)}
    before = dict(probes)
    simulate_sync(ROUTES, probes)
    assert probes == before
