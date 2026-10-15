#!/usr/bin/env python3
"""Apply the IntraSpot visual hierarchy to a Graphify Obsidian export."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any


# Obsidian Canvas IDs: 1 red, 2 orange, 3 yellow, 4 green, 5 cyan, 6 purple.
PALETTE = {
    "coral": ("1", 0xE7898E),
    "amber": ("2", 0xE6A756),
    "gold": ("3", 0xD2BE67),
    "sage": ("4", 0x71B89A),
    "teal": ("5", 0x64B8C4),
    "violet": ("6", 0xA58BCB),
}
PROJECT_PATH = "Hermes/Projects/IntraSpot"
VAULT_GROUP_PREFIX = f'path:"{PROJECT_PATH}" ('
HUB_QUERY = f'path:"{PROJECT_PATH}/Graphify/_COMMUNITY_"'
CANONICAL_BY_ACCENT = {
    "teal": [f"{PROJECT_PATH}.md", f"{PROJECT_PATH}/AI Index.md", f"{PROJECT_PATH}/Development Handoff.md"],
    "amber": [f"{PROJECT_PATH}/Open Questions.md"],
    "sage": [f"{PROJECT_PATH}/Functionality.md", f"{PROJECT_PATH}/UI & UX.md"],
    "coral": [f"{PROJECT_PATH}/Security & Operations.md"],
    "gold": [],
    "violet": [f"{PROJECT_PATH}/System Architecture.md", f"{PROJECT_PATH}/Future Ideas.md"],
}

# Community labels are generated content. New labels must be deliberately
# assigned a zone, accent, and order here before they can be laid out.
COMMUNITY_STYLE = {
    "Project Source Map": ("orient", "teal", 0),
    "Prototype Validation": ("orient", "teal", 1),
    "Eligibility and Open Decisions": ("orient", "amber", 2),
    "Registration and Capacity": ("product", "sage", 0),
    "Organization Approval Flow": ("product", "sage", 1),
    "Event Feed Discovery": ("product", "sage", 2),
    "Attendee Registration States": ("product", "sage", 3),
    "Featured Event Placement": ("product", "sage", 4),
    "Responsive Interface": ("product", "sage", 5),
    "Operations and Service Boundaries": ("trust", "coral", 0),
    "Persona Privacy Controls": ("trust", "gold", 1),
    "Personal User Reports": ("trust", "coral", 2),
    "Deployment and Migrations": ("platform", "violet", 0),
    "Deferred Ideas": ("platform", "violet", 1),
}

LANES = {
    "orient": ("01 · ORIENT & DECIDE", "teal", 0, 0),
    "product": ("02 · PRODUCT EXPERIENCE", "sage", 1, 0),
    "trust": ("03 · TRUST & OPERATIONS", "coral", 0, 1),
    "platform": ("04 · PLATFORM & FUTURE", "violet", 1, 1),
}
INDEX_FILE = "IntraSpot AI Navigation Index.md"
OWNED_TEXT_IDS = {
    "graphify-style-title",
    "graphify-style-legend",
    *(f"graphify-style-lane-{lane}" for lane in LANES),
}

CARD_WIDTH = 218
CARD_HEIGHT = 76
CARD_GAP_X = 18
CARD_GAP_Y = 16
GROUP_PAD_X = 22
GROUP_HEADER = 78
GROUP_BOTTOM = 22
GROUP_COLUMN_STEP = 1030
LANE_COLUMN_STEP = 2100
TOP_GROUP_Y = 315
BOTTOM_GROUP_Y = 1600
GROUP_ROW_GAP = 54


def file_name(node: dict[str, Any]) -> str:
    return str(node.get("file", "")).replace("\\", "/").rsplit("/", 1)[-1]


def color_id(accent: str) -> str:
    return PALETTE[accent][0]


def tag_slug(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")


def group_dimensions(card_count: int) -> tuple[int, int, int]:
    columns = max(1, min(4, math.ceil(math.sqrt(max(card_count, 1)))))
    rows = math.ceil(card_count / columns)
    width = 2 * GROUP_PAD_X + columns * CARD_WIDTH + (columns - 1) * CARD_GAP_X
    height = GROUP_HEADER + rows * CARD_HEIGHT + max(0, rows - 1) * CARD_GAP_Y + GROUP_BOTTOM
    return columns, width, height


def validate_canvas(data: dict[str, Any]) -> None:
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("Canvas must contain node and edge lists.")

    ids = [node.get("id") for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("Canvas contains duplicate node IDs.")
    known_ids = set(ids)
    if not all(edge.get("fromNode") in known_ids and edge.get("toNode") in known_ids for edge in edges):
        raise ValueError("Canvas contains an edge with a missing endpoint.")

    groups = [node for node in nodes if node.get("type") == "group"]
    labels = [group.get("label") for group in groups]
    if len(labels) != len(set(labels)):
        raise ValueError("Canvas contains duplicate community labels.")
    unclassified = sorted(set(labels) - set(COMMUNITY_STYLE))
    if unclassified:
        raise ValueError(
            "Unclassified Graphify community label(s): "
            + ", ".join(map(str, unclassified))
            + ". Add each to COMMUNITY_STYLE before styling this export."
        )
    if not groups:
        raise ValueError("Canvas has no Graphify community groups.")

    file_nodes = [node for node in nodes if node.get("type") == "file"]
    index_nodes = [node for node in file_nodes if file_name(node) == INDEX_FILE]
    if len(index_nodes) != 1:
        raise ValueError(f"Expected exactly one start note named {INDEX_FILE!r}.")
    index = index_nodes[0]
    for node in file_nodes:
        if node is index:
            continue
        cx = node["x"] + node["width"] / 2
        cy = node["y"] + node["height"] / 2
        owners = [
            group
            for group in groups
            if group["x"] <= cx <= group["x"] + group["width"]
            and group["y"] <= cy <= group["y"] + group["height"]
        ]
        if len(owners) != 1:
            raise ValueError(f"File card {file_name(node)!r} must belong to exactly one community.")


def style_canvas(data: dict[str, Any]) -> dict[str, Any]:
    nodes = data["nodes"]
    groups = [node for node in nodes if node.get("type") == "group"]
    group_by_label = {group["label"]: group for group in groups}
    file_nodes = [node for node in nodes if node.get("type") == "file"]
    index = next(node for node in file_nodes if file_name(node) == INDEX_FILE)

    members: dict[str, list[dict[str, Any]]] = {label: [] for label in group_by_label}
    for node in file_nodes:
        if node is index:
            continue
        cx = node["x"] + node["width"] / 2
        cy = node["y"] + node["height"] / 2
        owners = [
            group
            for group in groups
            if group["x"] <= cx <= group["x"] + group["width"]
            and group["y"] <= cy <= group["y"] + group["height"]
        ]
        if len(owners) != 1:
            raise ValueError(f"Cannot determine one community for {file_name(node)!r}.")
        members[owners[0]["label"]].append(node)

    # Sort cards by title, then pack each semantic zone into two visual columns.
    for lane, (heading, accent, lane_col, lane_row) in LANES.items():
        lane_labels = sorted(
            (label for label, (label_lane, _, _) in COMMUNITY_STYLE.items() if label_lane == lane and label in group_by_label),
            key=lambda label: COMMUNITY_STYLE[label][2],
        )
        group_y = TOP_GROUP_Y if lane_row == 0 else BOTTOM_GROUP_Y
        lane_x = lane_col * LANE_COLUMN_STEP
        for start in range(0, len(lane_labels), 2):
            row_labels = lane_labels[start : start + 2]
            heights = []
            for col, label in enumerate(row_labels):
                cards = sorted(members[label], key=lambda node: file_name(node).casefold())
                columns, width, height = group_dimensions(len(cards))
                group = group_by_label[label]
                group.update(
                    x=lane_x + col * GROUP_COLUMN_STEP,
                    y=group_y,
                    width=width,
                    height=height,
                    color=color_id(COMMUNITY_STYLE[label][1]),
                )
                for position, card in enumerate(cards):
                    card.update(
                        x=group["x"] + GROUP_PAD_X + (position % columns) * (CARD_WIDTH + CARD_GAP_X),
                        y=group["y"] + GROUP_HEADER + (position // columns) * (CARD_HEIGHT + CARD_GAP_Y),
                        width=CARD_WIDTH,
                        height=CARD_HEIGHT,
                    )
                heights.append(height)
            if heights:
                group_y += max(heights) + GROUP_ROW_GAP

    index.update(
        x=LANE_COLUMN_STEP - CARD_WIDTH // 2,
        y=92,
        width=CARD_WIDTH,
        height=CARD_HEIGHT,
        color=color_id("teal"),
    )

    for edge in data["edges"]:
        label = str(edge.get("label", "")).upper()
        if "[INFERRED]" in label:
            edge["color"] = color_id("violet")
        elif "[AMBIGUOUS]" in label:
            edge["color"] = color_id("amber")

    nodes[:] = [node for node in nodes if node.get("id") not in OWNED_TEXT_IDS]
    for reserved_id in OWNED_TEXT_IDS:
        collision = next((node for node in nodes if node.get("id") == reserved_id), None)
        if collision:
            raise ValueError(f"Canvas node ID {reserved_id!r} is reserved by this formatter.")

    nodes.extend(
        [
            {"id": "graphify-style-title", "type": "text", "text": "# IntraSpot · Knowledge Map", "x": 1770, "y": 0, "width": 560, "height": 70},
            {"id": "graphify-style-legend", "type": "text", "text": "> Start at **IntraSpot AI Navigation Index**. Follow zones 01 → 04.\n>\n> Colors group related topics. Default edge = extracted · violet = inferred · amber = ambiguous.", "x": 2600, "y": 55, "width": 1450, "height": 155},
            *[
                {
                    "id": f"graphify-style-lane-{lane}",
                    "type": "text",
                    "text": f"## {heading}",
                    "x": lane_col * LANE_COLUMN_STEP,
                    "y": 238 if lane_row == 0 else 1523,
                    "width": 1400,
                    "height": 62,
                    "color": color_id(accent),
                }
                for lane, (heading, accent, lane_col, lane_row) in LANES.items()
            ],
        ]
    )
    validate_canvas(data)
    return data


def style_graph_settings(data: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    groups = data.get("colorGroups", [])
    if not isinstance(groups, list):
        raise ValueError("Obsidian Graph settings colorGroups must be a list.")
    custom_groups = [
        group
        for group in groups
        if not str(group.get("query", "")).startswith("tag:#community/")
    ]
    community_groups = []
    for label in sorted(labels, key=lambda item: (LANES[COMMUNITY_STYLE[item][0]][3], LANES[COMMUNITY_STYLE[item][0]][2], COMMUNITY_STYLE[item][2])):
        lane, accent, _ = COMMUNITY_STYLE[label]
        community_groups.append(
            {
                "query": f"tag:#community/{tag_slug(label)}",
                "color": {"a": 1, "rgb": PALETTE[accent][1]},
            }
        )
    data["colorGroups"] = community_groups + custom_groups
    data["showArrow"] = True
    return data


def style_vault_graph_settings(data: dict[str, Any], labels: list[str]) -> dict[str, Any]:
    groups = data.get("colorGroups", [])
    if not isinstance(groups, list):
        raise ValueError("Main vault Graph settings colorGroups must be a list.")
    custom_groups = [
        group
        for group in groups
        if group.get("query") != HUB_QUERY
        and not str(group.get("query", "")).startswith(VAULT_GROUP_PREFIX)
    ]
    project_groups = [{"query": HUB_QUERY, "color": {"a": 1, "rgb": 0x88A9C8}}]
    for accent in ("teal", "amber", "sage", "coral", "gold", "violet"):
        terms = [
            f"tag:#community/{tag_slug(label)}"
            for label in sorted(labels, key=lambda item: COMMUNITY_STYLE[item][2])
            if COMMUNITY_STYLE[label][1] == accent
        ]
        terms += [f'path:"{path}"' for path in CANONICAL_BY_ACCENT[accent]]
        if terms:
            project_groups.append(
                {
                    "query": VAULT_GROUP_PREFIX + " OR ".join(terms) + ")",
                    "color": {"a": 1, "rgb": PALETTE[accent][1]},
                }
            )
    data["colorGroups"] = project_groups + custom_groups
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == serialized:
        return
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if reparse_point and attributes & reparse_point:
        with path.open("r+b") as destination:
            destination.write(serialized.encode("utf-8"))
            destination.truncate()
            destination.flush()
            os.fsync(destination.fileno())
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write(serialized)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("canvas", type=Path, help="Graphify-generated graph.canvas")
    parser.add_argument("--graph-settings", type=Path, help="Optional Obsidian .obsidian/graph.json")
    parser.add_argument("--vault-graph-settings", type=Path, help="Optional main vault .obsidian/graph.json")
    args = parser.parse_args()

    canvas_path = args.canvas
    canvas_data = json.loads(canvas_path.read_text(encoding="utf-8"))
    validate_canvas(canvas_data)
    community_labels = [node["label"] for node in canvas_data["nodes"] if node.get("type") == "group"]
    formatted_canvas = style_canvas(canvas_data)

    settings_path = args.graph_settings
    if settings_path is None:
        candidate = canvas_path.parent / ".obsidian" / "graph.json"
        settings_path = candidate if candidate.is_file() else None
    formatted_settings = None
    if settings_path:
        if not settings_path.is_file():
            raise FileNotFoundError(f"Obsidian Graph settings not found: {settings_path}")
        settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
        formatted_settings = style_graph_settings(settings_data, community_labels)

    vault_settings_path = args.vault_graph_settings
    formatted_vault_settings = None
    if vault_settings_path:
        if not vault_settings_path.is_file():
            raise FileNotFoundError(f"Main vault Graph settings not found: {vault_settings_path}")
        vault_settings_data = json.loads(vault_settings_path.read_text(encoding="utf-8"))
        formatted_vault_settings = style_vault_graph_settings(vault_settings_data, community_labels)

    write_json(canvas_path, formatted_canvas)
    if settings_path and formatted_settings is not None:
        write_json(settings_path, formatted_settings)
    if vault_settings_path and formatted_vault_settings is not None:
        write_json(vault_settings_path, formatted_vault_settings)
    print(f"Styled {len(formatted_canvas['nodes'])} canvas nodes across {len(community_labels)} communities and {len(formatted_canvas['edges'])} edges.")
    if settings_path:
        print(f"Updated Obsidian Graph colors and direction arrows in {settings_path}.")
    if vault_settings_path:
        print(f"Updated native Graph View groups in {vault_settings_path}.")


if __name__ == "__main__":
    main()
