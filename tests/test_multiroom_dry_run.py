import pytest

from core.multiroom_dry_run import Route, RouteError, plan_routes


ZONES = {"despacho": "windows", "comedor": "ubuntu"}
AVAILABLE = ["windows", "ubuntu"]


def test_two_zones():
    assert plan_routes(["despacho", "comedor"], ZONES, AVAILABLE) == (
        Route("despacho", "windows"), Route("comedor", "ubuntu")
    )


def test_single_zone():
    assert plan_routes(["comedor"], ZONES, AVAILABLE) == (Route("comedor", "ubuntu"),)


@pytest.mark.parametrize("zones", [[], ["desconocida"], ["despacho", "despacho"], [" despacho"], [""]])
def test_invalid_zones(zones):
    with pytest.raises(RouteError):
        plan_routes(zones, ZONES, AVAILABLE)


def test_unavailable_speaker():
    with pytest.raises(RouteError, match="unavailable"):
        plan_routes(["comedor"], ZONES, ["windows"])


def test_duplicate_speaker():
    with pytest.raises(RouteError, match="multiple"):
        plan_routes(["despacho", "comedor"], {"despacho": "ubuntu", "comedor": "ubuntu"}, AVAILABLE)


def test_no_mutation():
    mapping = dict(ZONES)
    speakers = list(AVAILABLE)
    plan_routes(["comedor"], mapping, speakers)
    assert mapping == ZONES and speakers == AVAILABLE


def test_reject_string_as_zones():
    with pytest.raises(RouteError):
        plan_routes("comedor", ZONES, AVAILABLE)
