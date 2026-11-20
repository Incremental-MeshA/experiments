"""MovingAI grids and the maps used by the incremental benchmark."""

from __future__ import annotations

from pathlib import Path

import numpy as np

PASSABLE = set(".G")


def load_map(path: str | Path) -> np.ndarray:
    """Read a MovingAI map. 0 is free, 1 is blocked."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    map_start = 0
    for index, line in enumerate(lines):
        if line.split()[:1] == ["map"]:
            map_start = index + 1
            break
    rows = [line.rstrip("\r") for line in lines[map_start:] if line.strip()]
    height = len(rows)
    width = max(len(row) for row in rows)
    grid = np.ones((height, width), dtype=np.uint8)
    for i, row in enumerate(rows):
        for j, char in enumerate(row):
            if char in PASSABLE:
                grid[i, j] = 0
    return grid


def save_map(path: str | Path, grid: np.ndarray) -> None:
    """Write a grid as a MovingAI octile map."""
    height, width = grid.shape
    lines = ["type octile", f"height {height}", f"width {width}", "map"]
    for i in range(height):
        chars = ["." if grid[i, j] == 0 else "@" for j in range(width)]
        lines.append("".join(chars))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_scen(path: str | Path) -> list[dict]:
    """Read MovingAI scenarios. Coordinates come back as (row, column)."""
    tasks = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 9 or parts[0] == "version":
            continue
        try:
            tasks.append(
                {
                    "bucket": int(parts[0]),
                    "map_file": parts[1],
                    "start": (int(float(parts[5])), int(float(parts[4]))),
                    "goal": (int(float(parts[7])), int(float(parts[6]))),
                    "optimal": float(parts[8]),
                }
            )
        except ValueError:
            continue
    return tasks


def in_bounds(grid: np.ndarray, i: int, j: int) -> bool:
    height, width = grid.shape
    return 0 <= i < height and 0 <= j < width


def is_free(grid: np.ndarray, i: int, j: int) -> bool:
    return in_bounds(grid, i, j) and grid[i, j] == 0


def generate_rooms(
    n: int = 5,
    room: int = 16,
    wall: int = 4,
    door: int = 4,
) -> np.ndarray:
    """Rooms joined by doors. Corridors are wide enough for short turns."""
    pitch = room + wall
    size = n * pitch + wall
    grid = np.ones((size, size), dtype=np.uint8)
    for ri in range(n):
        for cj in range(n):
            r0 = wall + ri * pitch
            c0 = wall + cj * pitch
            grid[r0 : r0 + room, c0 : c0 + room] = 0
            if cj + 1 < n:
                mid = r0 + (room - door) // 2
                grid[mid : mid + door, c0 + room : c0 + room + wall] = 0
            if ri + 1 < n:
                mid = c0 + (room - door) // 2
                grid[r0 + room : r0 + room + wall, mid : mid + door] = 0
    return grid


def generate_city(
    blocks: int = 6,
    street: int = 5,
    building: int = 12,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Regular city blocks with a few clipped corners."""
    rng = np.random.default_rng(0) if rng is None else rng
    pitch = building + street
    size = blocks * pitch + street
    grid = np.zeros((size, size), dtype=np.uint8)
    for bi in range(blocks):
        for bj in range(blocks):
            r0 = street + bi * pitch
            c0 = street + bj * pitch
            grid[r0 : r0 + building, c0 : c0 + building] = 1
            if rng.random() < 0.55:
                bite = int(rng.integers(2, 5))
                corner = int(rng.integers(0, 4))
                if corner == 0:
                    grid[r0 : r0 + bite, c0 : c0 + bite] = 0
                elif corner == 1:
                    grid[r0 : r0 + bite, c0 + building - bite : c0 + building] = 0
                elif corner == 2:
                    grid[r0 + building - bite : r0 + building, c0 : c0 + bite] = 0
                else:
                    grid[
                        r0 + building - bite : r0 + building,
                        c0 + building - bite : c0 + building,
                    ] = 0
    return grid


def generate_maze(
    n_cells: int = 16,
    corridor: int = 5,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Recursive-backtracker maze with wide corridors."""
    rng = np.random.default_rng(0) if rng is None else rng
    wall = 1
    pitch = corridor + wall
    size = n_cells * pitch + wall
    grid = np.ones((size, size), dtype=np.uint8)
    visited = np.zeros((n_cells, n_cells), dtype=bool)

    def carve(ci: int, cj: int) -> None:
        visited[ci, cj] = True
        r0 = wall + ci * pitch
        c0 = wall + cj * pitch
        grid[r0 : r0 + corridor, c0 : c0 + corridor] = 0
        order = [(0, 1), (1, 0), (0, -1), (-1, 0)]
        rng.shuffle(order)
        for di, dj in order:
            ni, nj = ci + di, cj + dj
            if not (0 <= ni < n_cells and 0 <= nj < n_cells) or visited[ni, nj]:
                continue
            if di == 0 and dj == 1:
                grid[r0 : r0 + corridor, c0 + corridor : c0 + pitch] = 0
            elif di == 0 and dj == -1:
                grid[r0 : r0 + corridor, c0 - wall : c0] = 0
            elif di == 1 and dj == 0:
                grid[r0 + corridor : r0 + pitch, c0 : c0 + corridor] = 0
            else:
                grid[r0 - wall : r0, c0 : c0 + corridor] = 0
            carve(ni, nj)

    carve(0, 0)
    return grid
