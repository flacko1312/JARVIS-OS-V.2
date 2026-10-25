"""Deterministic organic neural graph used by AURORA's GPU renderer."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NeuralGraph:
    nodes: np.ndarray
    node_seed: np.ndarray
    node_role: np.ndarray
    node_depth: np.ndarray
    edge_vertices: np.ndarray
    edge_seed: np.ndarray
    edge_path: np.ndarray
    edge_depth: np.ndarray
    edge_count: int


def _unit(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    return vector / max(length, 1e-6)


def build_neural_graph(node_count: int, edge_count: int, seed: int = 7319) -> NeuralGraph:
    """Build one irregular branched network with curved cross-connections.

    Edges are ordered from the denser interior toward the exterior where
    possible. That stable direction lets the fragment shader reverse impulses
    for listening without rebuilding buffers.
    """
    node_count = max(64, int(node_count))
    edge_count = max(node_count - 1, int(edge_count))
    rng = np.random.default_rng(seed + node_count * 3 + edge_count)
    nodes = np.zeros((node_count, 3), dtype=np.float32)
    parents = np.zeros(node_count, dtype=np.int32)
    branch_count = max(12, min(28, node_count // 30))
    cursor = 1
    branch_nodes: list[list[int]] = []

    # Compact asymmetric nucleus: no spherical shell and no orbital geometry.
    nucleus_count = max(20, int(node_count * .12))
    nodes[:nucleus_count] = rng.normal(0.0, (.13, .11, .12), (nucleus_count, 3))
    parents[1:nucleus_count] = rng.integers(0, np.arange(1, nucleus_count))
    cursor = nucleus_count

    allocations = np.full(branch_count, (node_count - cursor) // branch_count, dtype=np.int32)
    allocations[:(node_count - cursor) % branch_count] += 1
    golden = np.pi * (3.0 - np.sqrt(5.0))
    for branch_index, amount in enumerate(allocations):
        if amount <= 0:
            continue
        azimuth = branch_index * golden + rng.normal(0.0, .15)
        elevation = rng.uniform(-.72, .72)
        direction = _unit(np.asarray((
            np.cos(azimuth) * np.cos(elevation),
            np.sin(elevation) * .78,
            np.sin(azimuth) * np.cos(elevation),
        ), dtype=np.float32))
        parent = int(rng.integers(0, nucleus_count))
        branch: list[int] = []
        curl_axis = _unit(rng.normal(size=3).astype(np.float32))
        for step in range(int(amount)):
            index = cursor
            cursor += 1
            progress = (step + 1) / max(1, int(amount))
            direction = _unit(direction * .94 + rng.normal(0.0, .10, 3).astype(np.float32))
            curve = np.cross(direction, curl_axis) * (.018 + .018 * np.sin(progress * np.pi))
            length = rng.uniform(.033, .055) * (1.0 - progress * .14)
            nodes[index] = nodes[parent] + direction * length + curve
            parents[index] = parent
            branch.append(index)
            parent = index
        branch_nodes.append(branch)

    # Normalize into an anisotropic, slightly tilted volume with open negative
    # space. This keeps the silhouette organic instead of becoming a ball.
    nodes -= nodes.mean(axis=0, keepdims=True)
    nodes[:, 0] *= 1.10
    nodes[:, 1] *= .86
    nodes[:, 2] *= .94
    radius = np.percentile(np.linalg.norm(nodes, axis=1), 99.5)
    nodes /= max(float(radius), 1e-6)
    nodes *= .88

    edges: list[tuple[int, int]] = [(int(parents[i]), i) for i in range(1, node_count)]
    seen = {tuple(sorted(edge)) for edge in edges}
    # Add local cross-links. Candidate sampling avoids a large NxN allocation.
    while len(edges) < edge_count:
        a = int(rng.integers(0, node_count))
        candidates = rng.integers(0, node_count, size=12)
        distances = np.linalg.norm(nodes[candidates] - nodes[a], axis=1)
        b = int(candidates[int(np.argmin(distances + (candidates == a) * 100.0))])
        key = tuple(sorted((a, b)))
        if a == b or key in seen:
            continue
        # Keep graph routes local enough to read as filaments, not chords.
        if float(np.linalg.norm(nodes[a] - nodes[b])) > .36:
            continue
        seen.add(key)
        if np.linalg.norm(nodes[a]) <= np.linalg.norm(nodes[b]):
            edges.append((a, b))
        else:
            edges.append((b, a))

    # Each curved connection is three independent GL_LINES segments sampled
    # from a quadratic Bezier. Curvature is deterministic and stored once.
    subdivisions = 3
    edge_vertices = np.empty((edge_count * subdivisions * 2, 3), dtype=np.float32)
    edge_seed_values = np.empty(edge_count * subdivisions * 2, dtype=np.float32)
    edge_path = np.empty(edge_count * subdivisions * 2, dtype=np.float32)
    edge_depth = np.empty(edge_count * subdivisions * 2, dtype=np.float32)
    write = 0
    seeds = rng.random(edge_count).astype(np.float32)
    for edge_index, (a, b) in enumerate(edges[:edge_count]):
        start, end = nodes[a], nodes[b]
        delta = end - start
        normal = np.cross(delta, np.asarray((.21, .73, .43), dtype=np.float32))
        if np.linalg.norm(normal) < 1e-5:
            normal = np.cross(delta, np.asarray((.77, .12, .61), dtype=np.float32))
        normal = _unit(normal)
        bend = normal * min(.055, float(np.linalg.norm(delta)) * .22) * (1 if seeds[edge_index] > .5 else -1)
        control = (start + end) * .5 + bend
        for segment in range(subdivisions):
            for t in (segment / subdivisions, (segment + 1) / subdivisions):
                omt = 1.0 - t
                point = omt * omt * start + 2.0 * omt * t * control + t * t * end
                edge_vertices[write] = point
                edge_seed_values[write] = seeds[edge_index]
                edge_path[write] = t
                edge_depth[write] = np.clip((point[2] + 1.0) * .5, 0.0, 1.0)
                write += 1

    radii = np.linalg.norm(nodes, axis=1)
    node_role = np.clip(radii / max(float(radii.max()), 1e-6), 0.0, 1.0).astype(np.float32)
    node_depth = np.clip((nodes[:, 2] + 1.0) * .5, 0.0, 1.0).astype(np.float32)
    node_seed = rng.random(node_count).astype(np.float32)
    return NeuralGraph(
        nodes=np.ascontiguousarray(nodes),
        node_seed=node_seed,
        node_role=node_role,
        node_depth=node_depth,
        edge_vertices=np.ascontiguousarray(edge_vertices),
        edge_seed=edge_seed_values,
        edge_path=edge_path,
        edge_depth=edge_depth,
        edge_count=edge_count,
    )
