from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "ATEP_Volume_VII_ADAS_Engineering_Workbook.docx"


def shade(cell, fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    element = OxmlElement("w:shd")
    element.set(qn("w:fill"), fill)
    props.append(element)


def add_table(
    doc: Document, headers: list[str], rows: list[list[str]], widths: list[float]
) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for index, (cell, value) in enumerate(zip(table.rows[0].cells, headers, strict=True)):
        cell.width = Inches(widths[index])
        shade(cell, "17365D")
        run = cell.paragraphs[0].add_run(value)
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for row_index, values in enumerate(rows):
        cells = table.add_row().cells
        for index, (cell, value) in enumerate(zip(cells, values, strict=True)):
            cell.width = Inches(widths[index])
            if row_index % 2:
                shade(cell, "EAF0F7")
            cell.text = value
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    doc.add_paragraph()


def bullets(doc: Document, values: list[str]) -> None:
    for value in values:
        doc.add_paragraph(value, style="List Bullet")


def main() -> None:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = section.bottom_margin = Inches(0.75)
    section.left_margin = section.right_margin = Inches(0.8)
    doc.styles["Normal"].font.name = "Aptos"
    doc.styles["Normal"].font.size = Pt(10.5)
    for name, size in [("Title", 26), ("Heading 1", 17), ("Heading 2", 13)]:
        doc.styles[name].font.name = "Aptos Display"
        doc.styles[name].font.size = Pt(size)
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    title_properties = doc.styles["Title"].element.get_or_add_pPr()
    title_border = title_properties.find(qn("w:pBdr"))
    if title_border is not None:
        title_properties.remove(title_border)

    title = doc.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("ATEP Volume VII ADAS Engineering Workbook")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run("Version 0.1.0   VII 1 Deterministic World Model").bold = True
    doc.add_paragraph(
        "This workbook records the first engineering baseline for the ATEP ADAS volume. "
        "The world model provides deterministic sensor independent ground truth, so later "
        "perception and planning components can be tested against an authoritative scene."
    )
    add_table(
        doc,
        ["Field", "Value"],
        [
            ["Status", "VII-1 implemented and verified"],
            ["Technology", "FastAPI, PostgreSQL, SQLAlchemy, Alembic, Pydantic"],
            ["Cost", "Local first with no paid cloud or AI dependency"],
            ["Next", "VII-2 environment conditions and actor trajectories"],
        ],
        [1.5, 5.4],
    )

    doc.add_heading("1 Scope and Outcome", level=1)
    doc.add_paragraph(
        "VII-1 establishes the scene truth used by every future ADAS test. It includes an "
        "ENU coordinate frame, bounded road and lane geometry, exactly one ego vehicle, "
        "other traffic actors, deterministic logical time, persistence, RBAC, audit records, "
        "and transactional integration events."
    )
    bullets(
        doc,
        [
            "In scope: creation, lookup, pagination, and constant velocity advancement.",
            "In scope: ego vehicle, vehicle, pedestrian, cyclist, and static obstacle actors.",
            "Deferred: weather, traffic controls, sensor physics, perception, planning, "
            "and alerts.",
        ],
    )

    doc.add_heading("2 Architecture", level=1)
    doc.add_paragraph(
        "The Android Automotive interface and future simulators continue to communicate "
        "through ATEP APIs. The ADAS module owns world truth. Sensor modules will consume a "
        "scene revision and produce observations without changing that truth."
    )
    add_table(
        doc,
        ["Layer", "Responsibility"],
        [
            ["FastAPI router", "HTTP contracts, RBAC, pagination, and transaction boundaries"],
            ["Domain service", "Deterministic advancement, audit, and outbox evidence"],
            ["Pydantic", "Bounds and invariants for coordinates, geometry, actors, and time"],
            [
                "PostgreSQL",
                "Vehicle scoped scene, revision, logical time, roads, lanes, and actors",
            ],
            ["Alembic", "Reproducible migration 0044 and downgrade"],
        ],
        [1.55, 5.35],
    )

    doc.add_heading("3 Domain Model and Contracts", level=1)
    add_table(
        doc,
        ["Concept", "Invariant"],
        [
            ["Coordinate frame", "East North Up with bounded WGS84 origin"],
            ["Road and lane", "Unique identifiers and at least two centerline points per lane"],
            ["Actor", "Unique identifier with bounded dimensions, pose, heading, and velocity"],
            ["Ego vehicle", "Exactly one per scene"],
            ["Revision", "Starts at one and increments for every accepted advance"],
            ["Logical time", "Starts at zero and changes only through an advance command"],
        ],
        [1.55, 5.35],
    )

    doc.add_heading("4 API Surface", level=1)
    add_table(
        doc,
        ["Method", "Path", "Permission", "Purpose"],
        [
            ["POST", "/vehicles/{vehicle_id}/adas/scenes", "adas:manage", "Create truth"],
            ["GET", "/vehicles/{vehicle_id}/adas/scenes", "adas:read", "List scenes"],
            ["GET", "/vehicles/{vehicle_id}/adas/scenes/{scene_id}", "adas:read", "Read scene"],
            [
                "POST",
                "/vehicles/{vehicle_id}/adas/scenes/{scene_id}/advance",
                "adas:manage",
                "Advance time",
            ],
        ],
        [0.65, 3.35, 1.2, 1.25],
    )

    doc.add_heading("5 Engineering Decisions", level=1)
    add_table(
        doc,
        ["Decision", "Rationale", "Consequence"],
        [
            [
                "Separate truth from detections",
                "Allows objective perception scoring",
                "Sensors reference a scene revision",
            ],
            [
                "Use ENU locally",
                "Supports simple metric calculations",
                "Large area projection is deferred",
            ],
            [
                "Use logical time",
                "Makes tests independent of wall clock",
                "Time changes only through commands",
            ],
            [
                "Use expected revision",
                "Prevents silent concurrent overwrite",
                "Stale writes return stable HTTP 409",
            ],
            [
                "Store bounded JSON aggregates",
                "Supports heterogeneous actors",
                "Schema evolution needs contract discipline",
            ],
        ],
        [1.7, 2.65, 2.45],
    )

    doc.add_heading("6 Verification Catalogue", level=1)
    definitions = [
        ("Valid ENU scene", "Accept complete ground truth"),
        ("Single ego rule", "Reject missing or multiple ego actors"),
        ("Identifier uniqueness", "Prevent ambiguous roads, lanes, and actors"),
        ("Physical bounds", "Reject unsafe inputs"),
        ("Deterministic advance", "Verify positions and logical time"),
        ("Stale revision", "Prevent mutation on conflict"),
        ("Creation evidence", "Prove atomic audit and event evidence"),
        ("Advance evidence", "Keep event evidence minimized"),
        ("RBAC", "Prove read and manage protection"),
        ("Pagination", "Protect collection resources"),
        ("Migration", "Prove upgrade and downgrade"),
        ("Isolated replay", "Prove identical results from identical inputs"),
    ]
    rows = [
        [f"ADAS-T-{index:03d}", name, objective]
        for index, (name, objective) in enumerate(definitions, 1)
    ]
    add_table(doc, ["ID", "Test", "Objective"], rows, [1.05, 2.15, 3.65])

    doc.add_heading("7 Evidence and Quality Gates", level=1)
    bullets(
        doc,
        [
            "Focused ADAS and API contract tests pass in one process.",
            "Ruff formatting and static checks pass for the new module.",
            "mypy passes for the module and application composition.",
            "Migration 0044 follows the Volume VI migration head.",
            "The implementation uses no GPU and no paid external service.",
        ],
    )
    doc.add_heading("8 Risks and Controls", level=1)
    add_table(
        doc,
        ["Risk", "Control", "Future action"],
        [
            [
                "Unbounded scenes",
                "Limits for roads, lanes, actors, and points",
                "Add payload metrics",
            ],
            ["Floating point drift", "Round positions to six decimals", "Evaluate fixed point"],
            [
                "Truth coupled to sensors",
                "Separate scenes from observation models",
                "Link observations to revisions",
            ],
            ["Concurrent mutation", "Expected revision conflict", "Add idempotent command IDs"],
            [
                "Simplified motion",
                "Document constant velocity baseline",
                "Add trajectories in VII-2",
            ],
        ],
        [1.65, 2.8, 2.1],
    )
    doc.add_heading("9 Next Development", level=1)
    doc.add_paragraph(
        "VII-2 will add deterministic weather, illumination, visibility, road friction, "
        "traffic signs, traffic lights, and actor trajectories without mixing sensor output "
        "into ground truth."
    )
    doc.add_heading("10 Study Exercises", level=1)
    bullets(
        doc,
        [
            "Create an urban crossing and calculate actor positions after two seconds.",
            "Repeat an advance with a stale revision and explain the stable conflict.",
            "Design a radar miss while preserving the scene truth.",
            "Compare ENU coordinates with latitude and longitude for local simulation.",
        ],
    )
    doc.core_properties.title = "ATEP Volume VII ADAS Engineering Workbook"
    doc.core_properties.subject = "Deterministic ADAS world model engineering evidence"
    doc.core_properties.author = "ATEP Engineering"
    doc.save(OUTPUT)


if __name__ == "__main__":
    main()
