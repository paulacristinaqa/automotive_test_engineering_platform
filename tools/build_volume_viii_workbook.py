from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "workbook-volume-viii.md"
OUTPUT = ROOT / "docs" / "ATEP_Volume_VIII_Test_Framework_Engineering_Workbook.docx"


def shade(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    element = OxmlElement("w:shd")
    element.set(qn("w:fill"), fill)
    properties.append(element)


def borders(cell) -> None:  # type: ignore[no-untyped-def]
    properties = cell._tc.get_or_add_tcPr()
    table_borders = properties.first_child_found_in("w:tcBorders")
    if table_borders is None:
        table_borders = OxmlElement("w:tcBorders")
        properties.append(table_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:color"), "D9D9D9")
        table_borders.append(element)


def add_table(
    doc: Document, headers: list[str], rows: list[list[str]], widths: list[float]
) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.autofit = False
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for index, (cell, value) in enumerate(zip(table.rows[0].cells, headers, strict=True)):
        cell.width = Inches(widths[index])
        shade(cell, "17365D")
        borders(cell)
        run = cell.paragraphs[0].add_run(value)
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for row_index, values in enumerate(rows):
        cells = table.add_row().cells
        for index, (cell, value) in enumerate(zip(cells, values, strict=True)):
            cell.width = Inches(widths[index])
            borders(cell)
            if row_index % 2:
                shade(cell, "EAF0F7")
            cell.text = value
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    doc.add_paragraph()


def bullets(doc: Document, values: list[str]) -> None:
    for value in values:
        doc.add_paragraph(value, style="List Bullet")


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = section.bottom_margin = Inches(0.72)
    section.left_margin = section.right_margin = Inches(0.8)
    doc.styles["Normal"].font.name = "Aptos"
    doc.styles["Normal"].font.size = Pt(10.5)
    for name, size in (("Title", 25), ("Heading 1", 17), ("Heading 2", 13)):
        doc.styles[name].font.name = "Aptos Display"
        doc.styles[name].font.size = Pt(size)
        doc.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    title_properties = doc.styles["Title"].element.get_or_add_pPr()
    title_border = title_properties.find(qn("w:pBdr"))
    if title_border is not None:
        title_properties.remove(title_border)

    title = doc.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("ATEP Volume VIII Test Framework Engineering Workbook")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run("Version 0.1.0   VIII 1 Test Catalog Implemented").bold = True
    doc.add_paragraph(
        "This workbook records the first Test Framework baseline for ATEP. Reusable definitions "
        "now describe test intent independently from execution, while suites preserve ordered, "
        "versioned composition for later scheduling and result analysis."
    )
    add_table(
        doc,
        ["Field", "Value"],
        [
            ["Status", "VIII-1 implemented and verified"],
            ["Technology", "FastAPI, PostgreSQL, SQLAlchemy, Alembic, Pydantic"],
            ["Security", "test_catalog:read and test_catalog:manage"],
            ["Cost", "Local first with no paid cloud, AI, or GPU dependency"],
            ["Next", "VIII-2 suite execution binding and case results"],
        ],
        [1.5, 5.4],
    )

    doc.add_heading("1 Scope and Outcome", level=1)
    doc.add_paragraph(
        "VIII-1 separates reusable test design from test execution. A definition captures one "
        "test's preconditions, actions, inputs, expectations, classification, and resource budget. "
        "A suite selects active definitions in an explicit order and freezes their versions."
    )
    bullets(
        doc,
        [
            (
                "Definitions cover core, vehicle, ECU, CAN, diagnostics, EV, ADAS, and "
                "integration domains."
            ),
            "Suites classify smoke, sanity, regression, performance, stress, and safety intent.",
            (
                "Execution, scheduling, campaigns, mutation testing, and coverage remain "
                "later increments."
            ),
        ],
    )

    doc.add_page_break()
    doc.add_heading("2 Architecture", level=1)
    add_table(
        doc,
        ["Layer", "Responsibility"],
        [
            ["FastAPI", "Bounded contracts, pagination, status filtering, and RBAC"],
            ["Domain service", "Idempotency, lifecycle, snapshots, audit, and outbox"],
            ["PostgreSQL", "Definitions, suite composition snapshots, versions, and status"],
            ["Alembic", "Linear migration 0051 with reversible schema creation"],
            [
                "Future executor",
                "Consumes an active suite snapshot without rewriting catalog intent",
            ],
        ],
        [1.55, 5.35],
    )

    doc.add_heading("3 Definition Contract", level=1)
    add_table(
        doc,
        ["Concept", "Control", "Engineering purpose"],
        [
            ["Identity", "Lowercase URL-safe ID", "Stable API and evidence references"],
            ["Classification", "Domain, level, automation mode", "Selection and reporting"],
            ["Budget", "Timeout from 1 to 86400 seconds", "Bound future executor resources"],
            ["Preconditions", "At most twenty statements", "Make setup assumptions explicit"],
            ["Steps", "One to one hundred unique structured steps", "Preserve executable intent"],
            ["Inputs", "JSON limited to 8192 bytes per step", "Prevent unbounded payloads"],
        ],
        [1.3, 2.45, 3.15],
    )

    doc.add_page_break()
    doc.add_heading("4 Suite Composition", level=1)
    doc.add_paragraph(
        "A suite contains one to two hundred unique active definitions. Every case has a unique "
        "order, required flag, and bounded parameter overrides. The stored composition adds the "
        "definition name and version, creating a deterministic snapshot for future execution."
    )
    add_table(
        doc,
        ["Rule", "Rejected condition", "Reason"],
        [
            ["Known reference", "Definition does not exist", "Prevent dangling suites"],
            ["Active reference", "Definition is draft or archived", "Use reviewed test intent"],
            ["Unique definition", "Same definition appears twice", "Prevent accidental repetition"],
            ["Unique order", "Two cases share an order", "Guarantee deterministic sequence"],
            ["Version snapshot", "None", "Protect intent from later lifecycle changes"],
        ],
        [1.45, 2.55, 2.9],
    )

    doc.add_heading("5 Lifecycle and Concurrency", level=1)
    doc.add_paragraph(
        "Definitions and suites move only from draft to active to archived. A client supplies the "
        "expected version for every transition. Stale versions and backward transitions return "
        "stable HTTP 409 errors before mutation."
    )

    doc.add_heading("6 API and Access Control", level=1)
    add_table(
        doc,
        ["Resource", "Operations", "Permission"],
        [
            ["Test definitions", "Create and status change", "test_catalog:manage"],
            ["Test definitions", "List and detail", "test_catalog:read"],
            ["Test suites", "Create and status change", "test_catalog:manage"],
            ["Test suites", "List and detail", "test_catalog:read"],
        ],
        [1.65, 3.25, 2.0],
    )

    doc.add_page_break()
    doc.add_heading("7 Events and Audit", level=1)
    add_table(
        doc,
        ["Mutation", "Outbox event", "Audit action"],
        [
            ["Create definition", "atep.test_definition.created.v1", "test_definition.created"],
            [
                "Change definition status",
                "atep.test_definition.status_changed.v1",
                "test_definition.status_changed",
            ],
            ["Create suite", "atep.test_suite.created.v1", "test_suite.created"],
            [
                "Change suite status",
                "atep.test_suite.status_changed.v1",
                "test_suite.status_changed",
            ],
        ],
        [1.65, 3.15, 2.1],
    )
    doc.add_paragraph(
        "The resource, audit record, and outbox event share one database transaction. Exact create "
        "replays return the original resource without duplicate evidence; changed reuse of the "
        "same "
        "public identifier returns a stable conflict."
    )

    doc.add_heading("8 Engineering Decisions", level=1)
    add_table(
        doc,
        ["Decision", "Rationale", "Consequence"],
        [
            [
                "Separate catalog and runs",
                "Reuse intent across vehicles",
                "Runs bind snapshots later",
            ],
            [
                "Snapshot suite cases",
                "Preserve reviewed composition",
                "Definition edits require a new version",
            ],
            ["Forward-only status", "Avoid accidental reuse", "Archived content remains auditable"],
            ["Bound JSON and lists", "Protect shared resources", "Large data belongs in artifacts"],
        ],
        [1.65, 2.75, 2.5],
    )

    doc.add_page_break()
    doc.add_heading("9 Verification Catalogue", level=1)
    add_table(
        doc,
        ["ID range", "Coverage", "Objective"],
        [
            ["TF-T-001 to 004", "Definition contracts", "Validate bounds, evidence, and replay"],
            [
                "TF-T-005 to 008",
                "Suite composition",
                "Validate references, snapshots, and evidence",
            ],
            ["TF-T-009 to 010", "Lifecycle", "Validate state and optimistic concurrency"],
            ["TF-T-011 to 012", "RBAC and API", "Validate permissions and safe pagination"],
            ["TF-T-013 to 015", "Persistence", "Validate migration, uniqueness, and atomicity"],
        ],
        [1.55, 2.45, 2.9],
    )

    doc.add_heading("10 Risks and Controls", level=1)
    add_table(
        doc,
        ["Risk", "Control", "Next action"],
        [
            ["Ambiguous sequence", "Unique explicit case order", "Executor follows snapshot order"],
            ["Catalog drift", "Definition version snapshot", "Record execution snapshot in VIII-2"],
            ["Unbounded tests", "Timeout and collection limits", "Add run-level budgets"],
            [
                "Unsafe activation",
                "Draft review lifecycle and RBAC",
                "Add approval policy if required",
            ],
            ["Large evidence", "Metadata bounds", "Store binary evidence as artifacts"],
        ],
        [1.5, 2.55, 2.85],
    )

    doc.add_heading("11 Study Exercises", level=1)
    bullets(
        doc,
        [
            "Create one ADAS definition and identify every invariant enforced before persistence.",
            "Compose a smoke suite and explain its stored definition versions.",
        ],
    )

    doc.add_heading("12 Next Development", level=1)
    doc.add_paragraph(
        "VIII-2 will bind active suite snapshots to runs, persist ordered case results, and "
        "correlate artifact evidence."
    )
    doc.core_properties.title = "ATEP Volume VIII Test Framework Engineering Workbook"
    doc.core_properties.subject = "Reusable test definitions and deterministic suite composition"
    doc.core_properties.author = "ATEP Engineering"
    doc.save(OUTPUT)


if __name__ == "__main__":
    main()
