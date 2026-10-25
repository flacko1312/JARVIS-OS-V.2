from __future__ import annotations

import hashlib
import numpy as np


class ModelPointSampler:
    """Area-weighted triangle sampler returning centered exact-size float32 sets."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], np.ndarray] = {}

    def sample(self, name: str, vertices, triangles, count: int, seed: int = 7) -> np.ndarray:
        key = (str(name), int(count))
        if key in self._cache:
            return self._cache[key].copy()
        verts = np.asarray(vertices, dtype=np.float32).reshape(-1, 3)
        faces = np.asarray(triangles, dtype=np.int32).reshape(-1, 3)
        tri = verts[faces]
        areas = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) * .5
        if not len(areas) or float(areas.sum()) <= 0:
            raise ValueError("geometry has no sampleable surface")
        rng = np.random.default_rng(seed)
        chosen = rng.choice(len(faces), size=count, p=areas / areas.sum())
        r1, r2 = rng.random(count), rng.random(count)
        root = np.sqrt(r1)
        a = tri[chosen, 0]
        points = ((1-root)[:, None] * a + (root*(1-r2))[:, None] * tri[chosen, 1]
                  + (root*r2)[:, None] * tri[chosen, 2])
        points -= points.mean(axis=0)
        radius = float(np.max(np.linalg.norm(points, axis=1))) or 1.0
        points = np.ascontiguousarray(points / radius, dtype=np.float32)
        self._cache[key] = points
        return points.copy()

    @staticmethod
    def stable_seed(name: str) -> int:
        return int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "little")
