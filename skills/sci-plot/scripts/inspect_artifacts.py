#!/usr/bin/env python3
"""Inspect exported scientific-figure artifacts without installing dependencies.

The dependency-free path understands SVG, PDF, and PNG metadata. TIFF metadata
and raster-content heuristics use Pillow when it is already available. Missing
optional support is reported as WARN, never installed automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree


SCHEMA = "sciplot.artifact-qa/v1"
STATUS_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}
SUPPORTED_FORMATS = {"svg", "pdf", "png", "tiff"}
MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _status(checks: Iterable[dict[str, Any]]) -> str:
    worst = max((STATUS_ORDER.get(str(item.get("status")), 2) for item in checks), default=2)
    return ("PASS", "WARN", "FAIL")[worst]


def _check(
    checks: list[dict[str, Any]],
    check_id: str,
    status: str,
    artifact: Path,
    evidence: str,
    **details: Any,
) -> None:
    item: dict[str, Any] = {
        "id": check_id,
        "status": status,
        "artifact": str(artifact),
        "evidence": evidence,
    }
    if details:
        item["details"] = details
    checks.append(item)


def _detect_format(data: bytes) -> str | None:
    stripped = data.lstrip()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if stripped.startswith(b"<svg") or (
        stripped.startswith(b"<?xml") and b"<svg" in stripped[:4096]
    ):
        return "svg"
    return None


def _declared_format(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        return "tiff"
    value = suffix.removeprefix(".")
    return value if value in SUPPORTED_FORMATS else None


def _parse_length_mm(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(
        r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(mm|cm|in|pt|px)?\s*",
        value,
    )
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "mm":
        return number
    if unit == "cm":
        return number * 10.0
    if unit == "in":
        return number * MM_PER_INCH
    if unit == "pt":
        return number * MM_PER_INCH / POINTS_PER_INCH
    # Unitless SVG lengths and CSS px have no intrinsic print size.
    return None


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.match(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", value)
    return float(match.group(1)) if match else None


def _outside_tolerance(actual: float, expected: float, tolerance: float) -> bool:
    if expected == 0:
        return actual != 0
    return abs(actual - expected) / abs(expected) > tolerance


def _compare_dimensions(
    checks: list[dict[str, Any]],
    check_id: str,
    path: Path,
    actual_width: float | None,
    actual_height: float | None,
    target_width: float | None,
    target_height: float | None,
    unit: str,
    tolerance: float,
) -> None:
    expected = {
        "width": target_width,
        "height": target_height,
    }
    actual = {
        "width": actual_width,
        "height": actual_height,
    }
    requested = {axis: value for axis, value in expected.items() if value is not None}
    if not requested:
        return
    missing = [axis for axis in requested if actual[axis] is None]
    if missing:
        _check(
            checks,
            check_id,
            "WARN",
            path,
            f"cannot verify target {unit} for {', '.join(missing)}",
            actual=actual,
            expected=expected,
            tolerance_fraction=tolerance,
        )
        return
    mismatches = [
        axis
        for axis in requested
        if _outside_tolerance(float(actual[axis]), float(expected[axis]), tolerance)
    ]
    if mismatches:
        _check(
            checks,
            check_id,
            "FAIL",
            path,
            f"declared {unit} mismatch for {', '.join(mismatches)}",
            actual=actual,
            expected=expected,
            tolerance_fraction=tolerance,
        )
    else:
        _check(
            checks,
            check_id,
            "PASS",
            path,
            f"declared {unit} match within {tolerance:.1%}",
            actual=actual,
            expected=expected,
            tolerance_fraction=tolerance,
        )


def _svg_info(
    path: Path,
    data: bytes,
    checks: list[dict[str, Any]],
    require_svg_text: bool,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {}
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        _check(checks, "AR-02", "FAIL", path, f"invalid SVG XML: {exc}")
        return artifact
    if root.tag.split("}")[-1] != "svg":
        _check(checks, "AR-02", "FAIL", path, "XML root is not <svg>")
        return artifact

    texts = [node for node in root.iter() if node.tag.split("}")[-1] == "text"]
    artifact["editable_text_nodes"] = len(texts)
    if texts:
        _check(checks, "AR-02", "PASS", path, f"valid SVG with {len(texts)} editable text node(s)")
    elif require_svg_text:
        _check(checks, "AR-02", "FAIL", path, "editable SVG text was required but no <text> node exists")
    else:
        _check(checks, "AR-02", "WARN", path, "valid SVG contains no editable <text> nodes")

    width_mm = _parse_length_mm(root.get("width"))
    height_mm = _parse_length_mm(root.get("height"))
    view_box: list[float] | None = None
    raw_view_box = root.get("viewBox")
    if raw_view_box:
        try:
            values = [float(value) for value in re.split(r"[\s,]+", raw_view_box.strip()) if value]
            if len(values) == 4:
                view_box = values
        except ValueError:
            view_box = None
    artifact.update(
        {
            "width_mm": width_mm,
            "height_mm": height_mm,
            "view_box": view_box,
        }
    )
    if view_box is not None and (view_box[2] <= 0 or view_box[3] <= 0):
        _check(checks, "AR-01", "FAIL", path, "SVG viewBox has a non-positive width or height")
    elif width_mm is None or height_mm is None:
        _check(
            checks,
            "AR-01",
            "WARN",
            path,
            "SVG opens, but physical size is not fully declared with absolute units",
        )
    else:
        _check(
            checks,
            "AR-01",
            "PASS",
            path,
            f"SVG opens at {width_mm:.3f} × {height_mm:.3f} mm",
        )

    if view_box and texts:
        min_x, min_y, box_width, box_height = view_box
        max_x, max_y = min_x + box_width, min_y + box_height
        margin_x, margin_y = box_width * 0.01, box_height * 0.01
        risky: list[str] = []
        for index, node in enumerate(texts, start=1):
            x = _parse_number(node.get("x"))
            y = _parse_number(node.get("y"))
            if x is None or y is None:
                continue
            if (
                x < min_x
                or x > max_x
                or y < min_y
                or y > max_y
                or x - min_x < margin_x
                or max_x - x < margin_x
                or y - min_y < margin_y
                or max_y - y < margin_y
            ):
                risky.append(f"text[{index}]@({x:g},{y:g})")
        if risky:
            _check(
                checks,
                "AR-02",
                "WARN",
                path,
                "text anchor is outside or within 1% of the viewBox edge; inspect clipping",
                risky_nodes=risky[:20],
            )
        else:
            _check(
                checks,
                "AR-02",
                "PASS",
                path,
                "text anchors are inside the basic viewBox clipping margin",
            )
    return artifact


def _png_info(path: Path, data: bytes, checks: list[dict[str, Any]]) -> dict[str, Any]:
    artifact: dict[str, Any] = {}
    if len(data) < 33 or data[12:16] != b"IHDR":
        _check(checks, "AR-04", "FAIL", path, "PNG is missing a readable IHDR chunk")
        return artifact
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    artifact.update(
        {
            "width_px": width,
            "height_px": height,
            "bit_depth": bit_depth,
            "color_type": color_type,
            "has_alpha": color_type in {4, 6} or b"tRNS" in data,
        }
    )
    dpi_x: float | None = None
    dpi_y: float | None = None
    offset = 8
    has_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            _check(checks, "AR-04", "FAIL", path, f"truncated PNG chunk {chunk_type!r}")
            break
        chunk_data = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        if expected_crc != actual_crc:
            _check(
                checks,
                "AR-04",
                "FAIL",
                path,
                f"PNG chunk {chunk_type!r} has an invalid CRC",
            )
            break
        if chunk_type == b"pHYs" and len(chunk_data) == 9:
            x_ppm, y_ppm, unit = struct.unpack(">IIB", chunk_data)
            if unit == 1:
                dpi_x = x_ppm * 0.0254
                dpi_y = y_ppm * 0.0254
        if chunk_type == b"IEND":
            has_iend = True
            break
        offset = chunk_end
    artifact["dpi_x"] = dpi_x
    artifact["dpi_y"] = dpi_y
    if width <= 0 or height <= 0 or not has_iend:
        _check(checks, "AR-04", "FAIL", path, "PNG has invalid dimensions or no complete IEND chunk")
    elif width <= 1 or height <= 1:
        _check(checks, "AR-04", "WARN", path, f"PNG is only {width} × {height} px; likely placeholder")
    else:
        dpi_text = (
            f", {dpi_x:.1f} × {dpi_y:.1f} DPI"
            if dpi_x is not None and dpi_y is not None
            else ", no DPI metadata"
        )
        _check(checks, "AR-04", "PASS", path, f"PNG opens at {width} × {height} px{dpi_text}")
    return artifact


_PDF_WHITESPACE = b"\x00\t\n\f\r "
_PDF_XREF_ENTRY = re.compile(
    rb"([0-9]{10})[ \t]+([0-9]{5})[ \t]+([nf])[ \t]*(?:\r\n|\r|\n)"
)
_PDF_OBJECT_HEADER = re.compile(rb"([0-9]+)[ \t\r\n]+([0-9]+)[ \t\r\n]+obj\b")


def _skip_pdf_space_and_comments(data: bytes, position: int, limit: int) -> int:
    while position < limit:
        if data[position] in _PDF_WHITESPACE:
            position += 1
            continue
        if data[position] == ord("%"):
            newline = position + 1
            while newline < limit and data[newline] not in b"\r\n":
                newline += 1
            position = newline
            continue
        break
    return position


def _pdf_dictionary(
    data: bytes,
    position: int,
    limit: int,
) -> tuple[bytes, int] | None:
    """Return one balanced PDF dictionary and the position after it."""
    if not data.startswith(b"<<", position):
        return None
    start = position
    depth = 0
    while position < limit:
        if data[position] == ord("%"):
            position = _skip_pdf_space_and_comments(data, position, limit)
            continue
        if data[position] == ord("("):
            position += 1
            string_depth = 1
            while position < limit and string_depth:
                if data[position] == ord("\\"):
                    position += 2
                    continue
                if data[position] == ord("("):
                    string_depth += 1
                elif data[position] == ord(")"):
                    string_depth -= 1
                position += 1
            if string_depth:
                return None
            continue
        if data.startswith(b"<<", position):
            depth += 1
            position += 2
            continue
        if data.startswith(b">>", position):
            depth -= 1
            position += 2
            if depth == 0:
                return data[start:position], position
            if depth < 0:
                return None
            continue
        if data[position] == ord("<"):
            closing = data.find(b">", position + 1, limit)
            if closing < 0:
                return None
            position = closing + 1
            continue
        position += 1
    return None


def _validate_pdf_xref_table(
    data: bytes,
    xref_offset: int,
    startxref_offset: int,
    *,
    visited: set[int],
    terminal_required: bool,
) -> str | None:
    if not data.startswith(b"xref", xref_offset):
        return "startxref does not point to an xref table"
    position = xref_offset + len(b"xref")
    if position >= startxref_offset or data[position] not in _PDF_WHITESPACE:
        return "xref keyword is not followed by a cross-reference section"

    entries: list[tuple[int, int, int, bytes]] = []
    while True:
        position = _skip_pdf_space_and_comments(data, position, startxref_offset)
        if data.startswith(b"trailer", position):
            break
        subsection = re.match(
            rb"([0-9]+)[ \t]+([0-9]+)[ \t]*(?:\r\n|\r|\n)",
            data[position:startxref_offset],
        )
        if subsection is None:
            return "xref table has no readable subsection header"
        first_object = int(subsection.group(1))
        entry_count = int(subsection.group(2))
        if entry_count > len(data) // 10 + 1:
            return "xref subsection declares an impossible entry count"
        position += subsection.end()
        for index in range(entry_count):
            entry = _PDF_XREF_ENTRY.match(data, position, startxref_offset)
            if entry is None:
                return "xref subsection contains a malformed entry"
            entries.append(
                (
                    first_object + index,
                    int(entry.group(2)),
                    int(entry.group(1)),
                    entry.group(3),
                )
            )
            position = entry.end()

    if not entries:
        return "xref table contains no entries"
    position += len(b"trailer")
    position = _skip_pdf_space_and_comments(data, position, startxref_offset)
    parsed_dictionary = _pdf_dictionary(data, position, startxref_offset)
    if parsed_dictionary is None:
        return "xref trailer is missing a balanced dictionary"
    trailer, position = parsed_dictionary
    size_match = re.search(rb"/Size[ \t\r\n]+([0-9]+)\b", trailer)
    root_match = re.search(
        rb"/Root[ \t\r\n]+([0-9]+)[ \t\r\n]+([0-9]+)[ \t\r\n]+R\b",
        trailer,
    )
    previous_match = re.search(rb"/Prev[ \t\r\n]+([0-9]+)\b", trailer)
    has_previous_xref = previous_match is not None
    if size_match is None or int(size_match.group(1)) <= 0:
        return "xref trailer has no valid /Size"
    if root_match is None and not has_previous_xref:
        return "xref trailer has neither /Root nor /Prev"

    in_use = [entry for entry in entries if entry[3] == b"n"]
    if not in_use and not has_previous_xref:
        return "xref table has no in-use object"
    for object_number, generation, object_offset, _state in in_use:
        if object_offset <= 0 or object_offset >= xref_offset:
            return "xref entry points outside the preceding PDF body"
        object_header = _PDF_OBJECT_HEADER.match(data, object_offset, xref_offset)
        if object_header is None:
            return "xref entry does not point to an indirect object"
        if (
            int(object_header.group(1)) != object_number
            or int(object_header.group(2)) != generation
        ):
            return "xref entry points to the wrong indirect object"

    if root_match is not None and not has_previous_xref:
        root_reference = (int(root_match.group(1)), int(root_match.group(2)))
        if not any(
            (object_number, generation) == root_reference
            for object_number, generation, _offset, _state in in_use
        ):
            return "xref trailer /Root is not an in-use object"

    position = _skip_pdf_space_and_comments(data, position, startxref_offset)
    if terminal_required and position != startxref_offset:
        return "unexpected data appears between the trailer and startxref"
    if previous_match is not None:
        previous_offset = int(previous_match.group(1))
        if previous_offset <= 0 or previous_offset >= xref_offset:
            return "xref trailer /Prev is outside the preceding PDF body"
        previous_error = _validate_pdf_section(
            data,
            previous_offset,
            xref_offset,
            visited=visited,
            terminal_required=False,
        )
        if previous_error is not None:
            return f"invalid /Prev cross-reference section: {previous_error}"
    return None


def _validate_pdf_xref_stream(
    data: bytes,
    xref_offset: int,
    startxref_offset: int,
    *,
    visited: set[int],
    terminal_required: bool,
) -> str | None:
    object_header = _PDF_OBJECT_HEADER.match(data, xref_offset, startxref_offset)
    if object_header is None:
        return "startxref points to neither an xref table nor an indirect object"
    position = _skip_pdf_space_and_comments(
        data,
        object_header.end(),
        startxref_offset,
    )
    parsed_dictionary = _pdf_dictionary(data, position, startxref_offset)
    if parsed_dictionary is None:
        return "xref stream object is missing a balanced dictionary"
    dictionary, position = parsed_dictionary
    if re.search(rb"/Type[ \t\r\n]*/XRef\b", dictionary) is None:
        return "startxref object is not an /XRef stream"
    size_match = re.search(rb"/Size[ \t\r\n]+([0-9]+)\b", dictionary)
    width_match = re.search(
        rb"/W[ \t\r\n]*\[[ \t\r\n]*([0-9]+)[ \t\r\n]+"
        rb"([0-9]+)[ \t\r\n]+([0-9]+)[ \t\r\n]*\]",
        dictionary,
    )
    length_match = re.search(
        rb"/Length[ \t\r\n]+([0-9]+)(?:[ \t\r\n]+([0-9]+)[ \t\r\n]+R\b)?",
        dictionary,
    )
    root_match = re.search(
        rb"/Root[ \t\r\n]+([0-9]+)[ \t\r\n]+([0-9]+)[ \t\r\n]+R\b",
        dictionary,
    )
    previous_match = re.search(rb"/Prev[ \t\r\n]+([0-9]+)\b", dictionary)
    has_previous_xref = previous_match is not None
    if size_match is None or int(size_match.group(1)) <= 0:
        return "xref stream has no valid /Size"
    size = int(size_match.group(1))
    if width_match is None or sum(int(value) for value in width_match.groups()) <= 0:
        return "xref stream has no valid /W field"
    widths = tuple(int(value) for value in width_match.groups())
    if length_match is None:
        return "xref stream has no valid /Length"
    if root_match is None and not has_previous_xref:
        return "xref stream has neither /Root nor /Prev"

    position = _skip_pdf_space_and_comments(data, position, startxref_offset)
    stream_header = re.match(
        rb"stream[ \t]*(?:\r\n|\r|\n)",
        data[position:startxref_offset],
    )
    if stream_header is None:
        return "xref stream object has no stream body"
    content_start = position + stream_header.end()
    if length_match.group(2) is None:
        stream_length = int(length_match.group(1))
        if stream_length <= 0 or content_start + stream_length > startxref_offset:
            return "xref stream has an invalid direct /Length"
        stream_bytes = data[content_start : content_start + stream_length]
        endstream_position = content_start + stream_length
        if data.startswith(b"\r\n", endstream_position):
            endstream_position += 2
        elif (
            endstream_position < startxref_offset
            and data[endstream_position] in b"\r\n"
        ):
            endstream_position += 1
    else:
        endstream_position = data.rfind(
            b"endstream",
            content_start,
            startxref_offset,
        )
        if endstream_position < 0:
            return "xref stream object has no endstream marker"
        stream_bytes = data[content_start:endstream_position].rstrip(b"\r\n")
    if not data.startswith(b"endstream", endstream_position):
        return "xref stream /Length does not end at endstream"
    position = _skip_pdf_space_and_comments(
        data,
        endstream_position + len(b"endstream"),
        startxref_offset,
    )
    if not data.startswith(b"endobj", position):
        return "xref stream object has no endobj marker"
    position = _skip_pdf_space_and_comments(
        data,
        position + len(b"endobj"),
        startxref_offset,
    )
    if terminal_required and position != startxref_offset:
        return "unexpected data appears between the xref stream and startxref"

    filter_match = re.search(
        rb"/Filter[ \t\r\n]+(/[A-Za-z0-9]+|\[[^\]]*\])",
        dictionary,
    )
    filters = (
        re.findall(rb"/([A-Za-z0-9]+)", filter_match.group(1))
        if filter_match
        else []
    )
    if filters not in ([], [b"FlateDecode"], [b"Fl"]):
        return "xref stream uses an unsupported filter chain"
    if filters:
        try:
            inflater = zlib.decompressobj()
            decoded = inflater.decompress(stream_bytes) + inflater.flush()
        except zlib.error as exc:
            return f"xref stream FlateDecode failed: {exc}"
        if not inflater.eof or inflater.unused_data:
            return "xref stream FlateDecode did not consume one complete stream"
    else:
        decoded = stream_bytes

    index_match = re.search(rb"/Index[ \t\r\n]*\[([^\]]*)\]", dictionary)
    if index_match:
        index_values = [int(value) for value in re.findall(rb"[0-9]+", index_match.group(1))]
        if not index_values or len(index_values) % 2:
            return "xref stream has a malformed /Index"
        ranges = list(zip(index_values[0::2], index_values[1::2]))
    else:
        ranges = [(0, size)]
    if any(count <= 0 or start < 0 or start + count > size for start, count in ranges):
        return "xref stream /Index lies outside /Size"

    entry_width = sum(widths)
    entry_count = sum(count for _start, count in ranges)
    if len(decoded) != entry_width * entry_count:
        return "xref stream byte count does not match /W and /Index"

    entries: dict[int, tuple[int, int, int]] = {}
    cursor = 0
    for first_object, count in ranges:
        for object_number in range(first_object, first_object + count):
            fields: list[int] = []
            for width in widths:
                fields.append(
                    int.from_bytes(decoded[cursor : cursor + width], "big")
                    if width
                    else 0
                )
                cursor += width
            entry_type = fields[0] if widths[0] else 1
            if entry_type not in {0, 1, 2}:
                return "xref stream contains an unknown entry type"
            entries[object_number] = (entry_type, fields[1], fields[2])

    xref_object = int(object_header.group(1))
    xref_generation = int(object_header.group(2))
    xref_entry = entries.get(xref_object)
    if xref_entry != (1, xref_offset, xref_generation):
        return "xref stream does not contain a valid entry for itself"

    for object_number, (entry_type, field_two, field_three) in entries.items():
        if entry_type != 1:
            continue
        object_offset = field_two
        if object_offset <= 0 or object_offset >= startxref_offset:
            return "xref stream entry points outside the PDF body"
        header = _PDF_OBJECT_HEADER.match(data, object_offset, startxref_offset)
        if header is None:
            return "xref stream entry does not point to an indirect object"
        if (
            int(header.group(1)) != object_number
            or int(header.group(2)) != field_three
        ):
            return "xref stream entry points to the wrong indirect object"

    if root_match is not None:
        root_object = int(root_match.group(1))
        root_generation = int(root_match.group(2))
        root_entry = entries.get(root_object)
        if root_entry is None or root_entry[0] == 0:
            return "xref stream /Root is not a live object"
        if root_entry[0] == 1 and root_entry[2] != root_generation:
            return "xref stream /Root generation does not match its entry"
        if root_entry[0] == 2:
            if root_generation != 0:
                return "compressed xref stream /Root must use generation zero"
            object_stream = entries.get(root_entry[1])
            if object_stream is None or object_stream[0] != 1:
                return "xref stream /Root references a missing object stream"

    if previous_match is not None:
        previous_offset = int(previous_match.group(1))
        if previous_offset <= 0 or previous_offset >= xref_offset:
            return "xref stream /Prev is outside the preceding PDF body"
        previous_error = _validate_pdf_section(
            data,
            previous_offset,
            xref_offset,
            visited=visited,
            terminal_required=False,
        )
        if previous_error is not None:
            return f"invalid /Prev cross-reference section: {previous_error}"
    return None


def _validate_pdf_section(
    data: bytes,
    xref_offset: int,
    section_limit: int,
    *,
    visited: set[int],
    terminal_required: bool,
) -> str | None:
    if xref_offset in visited:
        return "cross-reference /Prev chain contains a cycle"
    if xref_offset <= 0 or xref_offset >= section_limit:
        return "cross-reference offset is outside its containing PDF section"
    visited.add(xref_offset)
    if data.startswith(b"xref", xref_offset):
        return _validate_pdf_xref_table(
            data,
            xref_offset,
            section_limit,
            visited=visited,
            terminal_required=terminal_required,
        )
    return _validate_pdf_xref_stream(
        data,
        xref_offset,
        section_limit,
        visited=visited,
        terminal_required=terminal_required,
    )


def _pdf_structure_error(data: bytes) -> str | None:
    if re.match(rb"%PDF-(?:1\.[0-7]|2\.0)(?:\r\n|\r|\n)", data) is None:
        return "PDF header has no supported version line"
    startxref_matches = list(
        re.finditer(
            rb"startxref[ \t\r\n]+([0-9]+)[ \t\r\n]+%%EOF[ \t\r\n]*\Z",
            data,
        )
    )
    if not startxref_matches:
        return "PDF is missing a terminal startxref/%%EOF section"
    terminal = startxref_matches[-1]
    xref_offset = int(terminal.group(1))
    if xref_offset <= 0 or xref_offset >= terminal.start():
        return "startxref offset is outside the PDF body"
    return _validate_pdf_section(
        data,
        xref_offset,
        terminal.start(),
        visited=set(),
        terminal_required=True,
    )


def _pdf_info(path: Path, data: bytes, checks: list[dict[str, Any]]) -> dict[str, Any]:
    structure_error = _pdf_structure_error(data)
    if structure_error is not None:
        _check(checks, "AR-03", "FAIL", path, f"invalid PDF structure: {structure_error}")
        return {"structure_valid": False}

    artifact: dict[str, Any] = {"structure_valid": True}
    _check(
        checks,
        "AR-03",
        "PASS",
        path,
        "PDF has a terminal startxref and a structurally valid cross-reference section",
    )
    page_matches = re.findall(rb"/Type\s*/Page(?!s)\b", data)
    media_box = re.search(
        rb"/MediaBox\s*\[\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s+"
        rb"([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\]",
        data,
    )
    width_mm: float | None = None
    height_mm: float | None = None
    if media_box:
        x0, y0, x1, y1 = (float(value) for value in media_box.groups())
        width_mm = (x1 - x0) * MM_PER_INCH / POINTS_PER_INCH
        height_mm = (y1 - y0) * MM_PER_INCH / POINTS_PER_INCH
    artifact.update(
        {
            "pages_detected": len(page_matches) or None,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "has_font_resource": b"/Font" in data,
            "has_embedded_font_marker": any(
                marker in data for marker in (b"/FontFile", b"/FontFile2", b"/FontFile3")
            ),
            "has_content_stream": b"stream" in data,
        }
    )
    if width_mm is None or height_mm is None:
        _check(
            checks,
            "AR-03",
            "WARN",
            path,
            "PDF opens by signature, but MediaBox could not be inspected without a PDF library",
        )
    elif width_mm <= 0 or height_mm <= 0:
        _check(checks, "AR-03", "FAIL", path, "PDF MediaBox has non-positive dimensions")
    else:
        _check(
            checks,
            "AR-03",
            "PASS",
            path,
            f"PDF MediaBox is {width_mm:.3f} × {height_mm:.3f} mm",
            pages_detected=len(page_matches) or None,
        )
    if b"/Font" not in data:
        _check(checks, "AR-03", "WARN", path, "no PDF font resource marker was detected")
    elif not artifact["has_embedded_font_marker"]:
        _check(
            checks,
            "AR-03",
            "WARN",
            path,
            "font resources exist, but embedding cannot be confirmed from raw metadata",
        )
    else:
        _check(checks, "AR-03", "PASS", path, "an embedded-font marker is present")
    if b"stream" not in data:
        _check(checks, "AR-03", "WARN", path, "no PDF content stream marker was detected; inspect blank-page risk")
    return artifact


def _pillow_raster_info(
    path: Path,
    checks: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> None:
    try:
        from PIL import Image, ImageChops  # type: ignore
    except ImportError:
        _check(
            checks,
            "AR-04",
            "WARN",
            path,
            "Pillow is unavailable; raster content/color/transparency heuristics were skipped",
            optional_dependency="Pillow",
        )
        return
    try:
        with Image.open(path) as image:
            image.load()
            artifact.setdefault("width_px", image.width)
            artifact.setdefault("height_px", image.height)
            artifact["color_mode"] = image.mode
            artifact["frames"] = getattr(image, "n_frames", 1)
            dpi = image.info.get("dpi")
            if isinstance(dpi, tuple) and len(dpi) >= 2:
                artifact["dpi_x"] = float(dpi[0])
                artifact["dpi_y"] = float(dpi[1])
            alpha = "A" in image.getbands()
            artifact["has_alpha"] = alpha
            if artifact.get("format") == "tiff":
                dpi_text = (
                    f", {artifact['dpi_x']:.1f} × {artifact['dpi_y']:.1f} DPI"
                    if artifact.get("dpi_x") is not None and artifact.get("dpi_y") is not None
                    else ", no readable DPI metadata"
                )
                if image.width <= 1 or image.height <= 1:
                    _check(
                        checks,
                        "AR-04",
                        "WARN",
                        path,
                        f"TIFF is only {image.width} × {image.height} px; likely placeholder",
                    )
                else:
                    _check(
                        checks,
                        "AR-04",
                        "PASS",
                        path,
                        f"TIFF opens at {image.width} × {image.height} px{dpi_text}",
                    )
            if alpha and image.getchannel("A").getbbox() is None:
                _check(checks, "AR-04", "FAIL", path, "all raster pixels are fully transparent")
                return
            if alpha:
                rgba = image.convert("RGBA")
                sample = Image.alpha_composite(
                    Image.new("RGBA", rgba.size, (255, 255, 255, 255)),
                    rgba,
                ).convert("RGB")
            else:
                sample = image.convert("RGB")
            extrema = ImageChops.difference(
                sample,
                sample.crop((0, 0, 1, 1)).resize(sample.size),
            ).getbbox()
            if extrema is None:
                _check(checks, "AR-04", "WARN", path, "raster is a single uniform color; inspect blank-image risk")
            else:
                _check(
                    checks,
                    "AR-04",
                    "PASS",
                    path,
                    f"raster content is non-uniform in {image.mode} mode",
                )
    except Exception as exc:  # Pillow raises format-specific subclasses.
        _check(checks, "AR-04", "FAIL", path, f"Pillow could not decode raster: {exc}")


def inspect_artifact(
    path: Path,
    *,
    target_width_mm: float | None,
    target_height_mm: float | None,
    target_width_px: int | None,
    target_height_px: int | None,
    target_dpi: float | None,
    tolerance: float,
    require_svg_text: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    artifact: dict[str, Any] = {"path": str(path), "name": path.name}
    try:
        data = path.read_bytes()
    except OSError as exc:
        _check(checks, "AR-01", "FAIL", path, f"artifact is missing or unreadable: {exc}")
        return artifact, checks
    artifact["bytes"] = len(data)
    artifact["sha256"] = _sha256(data)
    if not data:
        _check(checks, "AR-01", "FAIL", path, "artifact is empty")
        return artifact, checks

    detected = _detect_format(data)
    declared = _declared_format(path)
    artifact["format"] = detected
    artifact["declared_format"] = declared
    if detected is None:
        _check(checks, "AR-01", "FAIL", path, "unsupported or unrecognized artifact signature")
        return artifact, checks
    if declared is None:
        _check(checks, "AR-05", "WARN", path, f"recognized {detected}, but filename has no supported suffix")
    elif declared != detected:
        _check(
            checks,
            "AR-05",
            "FAIL",
            path,
            f"filename declares {declared}, but content is {detected}",
        )
    else:
        _check(checks, "AR-05", "PASS", path, f"filename and content both declare {detected}")

    if detected == "svg":
        artifact.update(_svg_info(path, data, checks, require_svg_text))
    elif detected == "png":
        artifact.update(_png_info(path, data, checks))
        _pillow_raster_info(path, checks, artifact)
    elif detected == "tiff":
        _check(checks, "AR-04", "PASS", path, "TIFF signature is readable")
        _pillow_raster_info(path, checks, artifact)
    elif detected == "pdf":
        artifact.update(_pdf_info(path, data, checks))

    if detected in {"svg", "pdf"}:
        _compare_dimensions(
            checks,
            "AR-01" if detected == "svg" else "AR-03",
            path,
            artifact.get("width_mm"),
            artifact.get("height_mm"),
            target_width_mm,
            target_height_mm,
            "physical dimensions (mm)",
            tolerance,
        )
    if detected in {"png", "tiff"}:
        expected_width_px = target_width_px
        expected_height_px = target_height_px
        if target_dpi is not None:
            if expected_width_px is None and target_width_mm is not None:
                expected_width_px = round(target_width_mm / MM_PER_INCH * target_dpi)
            if expected_height_px is None and target_height_mm is not None:
                expected_height_px = round(target_height_mm / MM_PER_INCH * target_dpi)
        _compare_dimensions(
            checks,
            "AR-04",
            path,
            artifact.get("width_px"),
            artifact.get("height_px"),
            expected_width_px,
            expected_height_px,
            "pixel dimensions",
            tolerance,
        )
        if target_dpi is None and (target_width_mm is not None or target_height_mm is not None):
            dpi_x, dpi_y = artifact.get("dpi_x"), artifact.get("dpi_y")
            actual_width_mm = (
                float(artifact["width_px"]) / float(dpi_x) * MM_PER_INCH
                if artifact.get("width_px") is not None and dpi_x
                else None
            )
            actual_height_mm = (
                float(artifact["height_px"]) / float(dpi_y) * MM_PER_INCH
                if artifact.get("height_px") is not None and dpi_y
                else None
            )
            _compare_dimensions(
                checks,
                "AR-04",
                path,
                actual_width_mm,
                actual_height_mm,
                target_width_mm,
                target_height_mm,
                "physical dimensions inferred from raster DPI (mm)",
                tolerance,
            )
        if target_dpi is not None:
            dpi_x, dpi_y = artifact.get("dpi_x"), artifact.get("dpi_y")
            if dpi_x is None or dpi_y is None:
                _check(
                    checks,
                    "AR-04",
                    "WARN",
                    path,
                    f"target is {target_dpi:g} DPI, but readable DPI metadata is absent",
                )
            elif _outside_tolerance(float(dpi_x), target_dpi, tolerance) or _outside_tolerance(
                float(dpi_y), target_dpi, tolerance
            ):
                _check(
                    checks,
                    "AR-04",
                    "FAIL",
                    path,
                    f"DPI metadata does not match target {target_dpi:g}",
                    actual={"x": dpi_x, "y": dpi_y},
                    expected=target_dpi,
                    tolerance_fraction=tolerance,
                )
            else:
                _check(
                    checks,
                    "AR-04",
                    "PASS",
                    path,
                    f"DPI metadata matches {target_dpi:g} within {tolerance:.1%}",
                )
    return artifact, checks


def inspect(
    paths: list[Path],
    *,
    target_width_mm: float | None = None,
    target_height_mm: float | None = None,
    target_width_px: int | None = None,
    target_height_px: int | None = None,
    target_dpi: float | None = None,
    tolerance: float = 0.02,
    require_svg_text: bool = False,
    strict: bool = False,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    names: dict[str, list[str]] = {}
    for path in paths:
        artifact, artifact_checks = inspect_artifact(
            path,
            target_width_mm=target_width_mm,
            target_height_mm=target_height_mm,
            target_width_px=target_width_px,
            target_height_px=target_height_px,
            target_dpi=target_dpi,
            tolerance=tolerance,
            require_svg_text=require_svg_text,
        )
        artifacts.append(artifact)
        checks.extend(artifact_checks)
        names.setdefault(path.name.casefold(), []).append(str(path))
    duplicates = [values for values in names.values() if len(values) > 1]
    if duplicates:
        for values in duplicates:
            _check(
                checks,
                "AR-05",
                "FAIL",
                Path(values[0]),
                "duplicate artifact filename is ambiguous",
                duplicate_paths=values,
            )

    if strict:
        for item in checks:
            if item["status"] == "WARN":
                item["status"] = "FAIL"
                item["strict_promotion"] = True
    result_status = _status(checks)
    unresolved = [
        {
            "id": item["id"],
            "status": item["status"],
            "artifact": item.get("artifact"),
            "evidence": item["evidence"],
        }
        for item in checks
        if item["status"] != "PASS"
    ]
    return {
        "schema": SCHEMA,
        "status": result_status,
        "strict": strict,
        "summary": {
            "pass": sum(item["status"] == "PASS" for item in checks),
            "warn": sum(item["status"] == "WARN" for item in checks),
            "fail": sum(item["status"] == "FAIL" for item in checks),
        },
        "targets": {
            "width_mm": target_width_mm,
            "height_mm": target_height_mm,
            "width_px": target_width_px,
            "height_px": target_height_px,
            "dpi": target_dpi,
            "tolerance_fraction": tolerance,
            "require_svg_text": require_svg_text,
        },
        "checks": checks,
        "artifacts": artifacts,
        "unresolved": unresolved,
    }


def _positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite value greater than zero")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _same_file_target(left: Path, right: Path) -> bool:
    try:
        if left.resolve(strict=False) == right.resolve(strict=False):
            return True
    except (OSError, RuntimeError):
        pass
    try:
        return left.samefile(right)
    except (OSError, ValueError):
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect SVG/PDF/PNG/TIFF artifacts and emit stable AR-* JSON."
    )
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--width-mm", type=_positive_float, help="Expected physical width.")
    parser.add_argument("--height-mm", type=_positive_float, help="Expected physical height.")
    parser.add_argument("--width-px", type=_positive_int, help="Expected raster width.")
    parser.add_argument("--height-px", type=_positive_int, help="Expected raster height.")
    parser.add_argument("--dpi", type=_positive_float, help="Expected raster DPI.")
    parser.add_argument(
        "--tolerance",
        type=_positive_float,
        default=0.02,
        help="Relative dimension/DPI tolerance (default: 0.02).",
    )
    parser.add_argument(
        "--require-svg-text",
        action="store_true",
        help="FAIL an SVG that contains no editable <text> nodes.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Promote every WARN to FAIL.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.output:
        conflict = next(
            (
                artifact
                for artifact in args.artifacts
                if _same_file_target(args.output, artifact)
            ),
            None,
        )
        if conflict is not None:
            print(
                json.dumps(
                    {
                        "schema": SCHEMA,
                        "status": "FAIL",
                        "error": (
                            "--output must not refer to an input artifact: "
                            f"{conflict}"
                        ),
                    },
                    ensure_ascii=False,
                )
            )
            return 2
    result = inspect(
        args.artifacts,
        target_width_mm=args.width_mm,
        target_height_mm=args.height_mm,
        target_width_px=args.width_px,
        target_height_px=args.height_px,
        target_dpi=args.dpi,
        tolerance=args.tolerance,
        require_svg_text=args.require_svg_text,
        strict=args.strict,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        try:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            print(json.dumps({"schema": SCHEMA, "status": "FAIL", "error": str(exc)}))
            return 2
    else:
        print(rendered)
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
