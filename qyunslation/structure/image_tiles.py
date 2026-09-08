# SPDX-License-Identifier: MPL-2.0
"""Tile planning for oversized image canvases (PLAN-030f Task 5)."""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TILE_MAX_SIDE = 2048
DEFAULT_TILE_OVERLAP = 128
DEFAULT_TILE_MEMORY_BUDGET_PX = 200_000_000


@dataclass(frozen=True, slots=True)
class ImageTile:
    index: int
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


def plan_image_tiles(
    width: int,
    height: int,
    *,
    max_side: int = DEFAULT_TILE_MAX_SIDE,
    overlap: int = DEFAULT_TILE_OVERLAP,
) -> list[ImageTile]:
    if width <= 0 or height <= 0:
        return []
    if max(width, height) <= max_side:
        return [ImageTile(0, 0, 0, width, height)]

    tiles: list[ImageTile] = []
    index = 0
    y = 0
    while y < height:
        x = 0
        tile_h = min(max_side, height - y)
        if y + tile_h < height:
            tile_h = min(max_side, tile_h)
        while x < width:
            tile_w = min(max_side, width - x)
            x1 = min(width, x + tile_w)
            y1 = min(height, y + tile_h)
            tiles.append(ImageTile(index, x, y, x1, y1))
            index += 1
            if x1 >= width:
                break
            x = max(x + 1, x1 - overlap)
        if y + tile_h >= height:
            break
        y = max(y + 1, y + tile_h - overlap)
    return tiles


def tile_memory_pixels(tiles: list[ImageTile]) -> int:
    return sum(tile.width * tile.height for tile in tiles)


def detect_tile_seam_overlaps(
    left_blocks: list[tuple[int, int, int, int, str]],
    right_blocks: list[tuple[int, int, int, int, str]],
    *,
    overlap_px: int,
    gap_tolerance: float = 24.0,
) -> list[str]:
    """Return human-readable seam warnings when adjacent tiles disagree in overlap band."""
    warnings: list[str] = []
    if overlap_px <= 0:
        return warnings
    for lx0, ly0, lx1, ly1, ltext in left_blocks:
        for rx0, ry0, rx1, ry1, rtext in right_blocks:
            if abs(ly0 - ry0) > gap_tolerance or abs(ly1 - ry1) > gap_tolerance:
                continue
            if ltext.strip().lower() == rtext.strip().lower() and ltext.strip():
                continue
            if lx1 - overlap_px <= rx0 <= lx1 + gap_tolerance:
                warnings.append(
                    f"seam mismatch near x={lx1}: {ltext!r} vs {rtext!r}"
                )
    return warnings
