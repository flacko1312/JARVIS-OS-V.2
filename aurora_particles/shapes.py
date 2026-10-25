from __future__ import annotations

import numpy as np


def _surface_sphere(rng, n, scale=(1., 1., 1.)):
    v = rng.normal(size=(n, 3)).astype(np.float32)
    v /= np.linalg.norm(v, axis=1)[:, None]
    return v * np.asarray(scale, dtype=np.float32)


def core(count: int) -> np.ndarray:
    rng = np.random.default_rng(1103)
    counts = [int(count*r) for r in (.25, .30, .075, .075, .20)]
    counts.append(count-sum(counts))
    nucleus = _surface_sphere(rng, counts[0], (.25, .25, .25))
    nucleus *= (.45+.55*rng.random((counts[0],1))).astype(np.float32)
    def ring(n, radius, tilt):
        a=rng.random(n).astype(np.float32)*np.float32(np.pi*2)
        p=np.column_stack((radius*np.cos(a), radius*np.sin(a), .012*rng.normal(size=n))).astype(np.float32)
        c,s=np.cos(tilt),np.sin(tilt); rot=np.asarray(((1,0,0),(0,c,-s),(0,s,c)),dtype=np.float32)
        return p@rot.T
    main=ring(counts[1],.78,0.0); secondary_a=ring(counts[2],.62,np.pi/2)
    secondary_b=ring(counts[3],.58,np.pi/4)
    phase=rng.random(counts[4]).astype(np.float32)*np.float32(np.pi*5)
    streams=np.column_stack((.38*np.cos(phase),.38*np.sin(phase),.24*np.sin(phase*.6))).astype(np.float32)
    ambient=_surface_sphere(rng,counts[5],(.66,.66,.66))
    ambient*=rng.uniform(.72,1.0,(counts[5],1)).astype(np.float32)
    return np.ascontiguousarray(np.vstack((nucleus,main,secondary_a,secondary_b,streams,ambient))*.78,dtype=np.float32)


def brain(count: int) -> np.ndarray:
    rng = np.random.default_rng(2207)
    side = rng.choice((-1., 1.), count).astype(np.float32)
    p = _surface_sphere(rng, count, (.58, .76, .67))
    p[:, 0] += side * .44
    grooves = .045 * np.sin(p[:, 1]*24 + p[:, 2]*18 + side)
    p *= (1.0 + grooves[:, None]).astype(np.float32)
    p[:, 1] += .08
    p[:, 2] += .08 * np.sin(p[:, 0]*7)
    p /= max(1., float(np.max(np.linalg.norm(p, axis=1))))
    return np.ascontiguousarray(p, dtype=np.float32)


def skull(count: int) -> np.ndarray:
    rng = np.random.default_rng(3301)
    out = []
    while sum(len(x) for x in out) < count:
        n = max(512, count - sum(len(x) for x in out))
        p = _surface_sphere(rng, n, (.72, .88, .72))
        p[:, 1] += .20
        # Carve full projection columns: an additive point cloud has no opaque
        # face to hide the rear shell, so front-only holes would be filled by
        # points behind them and cease to read as eye sockets.
        eye = (p[:, 1] > .05) & (p[:, 1] < .43) & (np.abs(np.abs(p[:, 0])-.28) < .17)
        nose = (p[:, 1] > -.23) & (p[:, 1] < .08) & (np.abs(p[:, 0]) < .12)
        temple = (p[:, 1] < -.18) & (np.abs(p[:, 0]) > .52)
        out.append(p[~(eye | nose | temple)])
    cranium = np.vstack(out)[:int(count*.78)]
    jaw_n = count - len(cranium)
    a = rng.random(jaw_n).astype(np.float32) * np.float32(np.pi)
    jaw = np.column_stack((.48*np.cos(a), -.48-.34*np.sin(a), -.43+.05*rng.normal(size=jaw_n))).astype(np.float32)
    return np.ascontiguousarray(np.vstack((cranium, jaw))[:count], dtype=np.float32)


def _vortex_ring(rng, count: int, radius: float, tube: float,
                 rotate_x: float = 0.0, rotate_y: float = 0.0,
                 offset=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Sample a luminous toroidal orbit and rotate it into a 3D plane."""
    theta = rng.random(count).astype(np.float32) * np.float32(np.pi * 2)
    phi = rng.random(count).astype(np.float32) * np.float32(np.pi * 2)
    local_radius = radius + tube * np.cos(phi)
    points = np.column_stack((
        local_radius * np.cos(theta),
        local_radius * np.sin(theta),
        tube * np.sin(phi),
    )).astype(np.float32)
    cx, sx = np.cos(rotate_x), np.sin(rotate_x)
    cy, sy = np.cos(rotate_y), np.sin(rotate_y)
    rx = np.asarray(((1, 0, 0), (0, cx, -sx), (0, sx, cx)), dtype=np.float32)
    ry = np.asarray(((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)), dtype=np.float32)
    return np.ascontiguousarray(points @ rx.T @ ry.T + np.asarray(offset,dtype=np.float32))


def vortex(count: int) -> np.ndarray:
    """Technological energy vortex: nucleus, four crossed orbits and streams.

    Distribution is deterministic and always totals exactly ``count``:
    14% compact nucleus, 24% horizontal ring, 20% vertical ring,
    16%/+45 degree, 14%/-45 degree and the remainder in three internal
    energy streams.
    """
    rng = np.random.default_rng(4417)
    counts = [int(count * ratio) for ratio in (.14, .24, .20, .16, .14)]
    counts.append(count - sum(counts))

    nucleus = _surface_sphere(rng, counts[0], (.27, .27, .27))
    nucleus *= (.38 + .62 * rng.random((counts[0], 1))).astype(np.float32)
    horizontal = _vortex_ring(rng, counts[1], .80, .012, offset=(0,0,.035))
    vertical = _vortex_ring(rng, counts[2], .70, .011, rotate_x=np.pi / 2, offset=(.025,0,-.025))
    diagonal_a = _vortex_ring(rng, counts[3], .65, .010,
                              rotate_x=np.pi / 4, rotate_y=np.pi / 5, offset=(-.025,.018,.015))
    diagonal_b = _vortex_ring(rng, counts[4], .57, .009,
                              rotate_x=-np.pi / 4, rotate_y=-np.pi / 6, offset=(.02,-.02,-.035))

    stream_n = counts[5]
    phase = rng.random(stream_n).astype(np.float32) * np.float32(np.pi * 6)
    lane = rng.integers(0, 3, stream_n)
    stream_radius = (.12 + .34 * (phase / np.float32(np.pi * 6))).astype(np.float32)
    streams = np.column_stack((
        stream_radius * np.cos(phase + lane * (2*np.pi/3)),
        stream_radius * np.sin(phase + lane * (2*np.pi/3)),
        .34 * np.sin(phase * .5 + lane),
    )).astype(np.float32)

    points = np.vstack((nucleus, horizontal, vertical, diagonal_a, diagonal_b, streams))
    radius = float(np.max(np.linalg.norm(points, axis=1))) or 1.0
    return np.ascontiguousarray(points[:count] / radius, dtype=np.float32)


SHAPE_FACTORIES = {"core": core, "brain": brain, "skull": skull, "vortex": vortex}


def accent_mask(name: str, count: int) -> np.ndarray:
    """Per-particle neon-lilac emphasis while retaining one point-cloud draw.

    Vortex's nucleus plus principal horizontal/vertical rings are accented;
    inclined secondary rings and streams retain the active theme. CORE accents
    a small inner energy subset and its technological ring. Other shapes remain
    theme-coloured.
    """
    mask = np.zeros(int(count), dtype=np.float32)
    if name == "vortex":
        mask[:int(count * (.14 + .24 + .20))] = 1.0
    elif name == "core":
        mask[:int(count * .70)] = 1.0
    return mask
