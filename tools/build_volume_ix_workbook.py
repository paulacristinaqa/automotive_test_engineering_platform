from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

OUTPUT = Path("docs/ATEP_Volume_IX_AI_Test_Engineer_Engineering_Workbook.docx")
BLUE = "1F4E78"
PALE = "EAF1F8"


def shade(cell, fill: str) -> None:  # type: ignore[no-untyped-def]
    properties = cell._tc.get_or_add_tcPr()
    element = OxmlElement("w:shd")
    element.set(qn("w:fill"), fill)
    properties.append(element)


def table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    item = doc.add_table(rows=1, cols=len(headers))
    item.style = "Table Grid"
    header_properties = item.rows[0]._tr.get_or_add_trPr()
    header_marker = OxmlElement("w:tblHeader")
    header_marker.set(qn("w:val"), "true")
    header_properties.append(header_marker)
    for index, header in enumerate(headers):
        cell = item.rows[0].cells[index]
        cell.text = header
        shade(cell, BLUE)
        cell.width = Inches(widths[index])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
    for row_index, values in enumerate(rows):
        row = item.add_row()
        row_properties = row._tr.get_or_add_trPr()
        row_properties.append(OxmlElement("w:cantSplit"))
        cells = row.cells
        for index, value in enumerate(values):
            cells[index].text = value
            cells[index].width = Inches(widths[index])
            cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_index % 2:
                shade(cells[index], PALE)
    doc.add_paragraph()


def build() -> None:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.75)
    section.right_margin = Inches(0.75)
    styles = doc.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"].font.size = Pt(10.5)
    for name in ("Title", "Heading 1", "Heading 2"):
        styles[name].font.color.rgb = RGBColor(0, 0, 0)
        styles[name].font.name = "Aptos"
    title_properties = styles["Title"].element.get_or_add_pPr()
    title_border = title_properties.find(qn("w:pBdr"))
    if title_border is not None:
        title_properties.remove(title_border)
    title = doc.add_paragraph(style="Title")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("ATEP Volume IX AI Test Engineer Engineering Workbook")
    intro = doc.add_paragraph()
    intro.alignment = WD_ALIGN_PARAGRAPH.CENTER
    intro.add_run("Version 0.1.0  Provider Neutral Foundation").bold = True
    doc.add_paragraph(
        "This workbook records the first governed AI boundary for ATEP. IX-1 captures analysis "
        "intent without invoking a model, requiring a paid service, downloading model weights, "
        "or using a GPU."
    )
    table(
        doc,
        ["Field", "Value"],
        [
            ["Status", "IX-1 implemented"],
            ["Cost", "Local first and no paid dependency"],
            ["Migration", "0057_ai_analysis_foundation"],
            ["Next", "IX-2 deterministic local analysis workers"],
        ],
        [1.6, 5.2],
    )
    doc.add_heading("1 Scope and Architecture", level=1)
    doc.add_paragraph(
        "FastAPI accepts bounded provider-neutral requests. A domain service applies idempotency "
        "and data-classification policy. PostgreSQL preserves queued intent, while RBAC, audit, "
        "and outbox "
        "evidence provide a traceable boundary. Model execution deliberately follows in IX-2."
    )
    table(
        doc,
        ["Layer", "Responsibility"],
        [
            ["API", "Validation, pagination, filtering, and RBAC"],
            ["Domain service", "Policy, idempotency, audit, and outbox"],
            ["PostgreSQL", "Immutable request intent and status"],
            ["Future worker", "Local rules first, optional provider adapters later"],
        ],
        [1.7, 5.1],
    )
    doc.add_heading("2 Contract and Governance", level=1)
    table(
        doc,
        ["Control", "Rule", "Purpose"],
        [
            [
                "Provider policy",
                "Local only by default",
                "No mandatory external cost or data egress",
            ],
            ["Classification", "Restricted requires local only", "Prevent unsafe transmission"],
            ["Context", "16384 encoded bytes", "Bound storage and processing"],
            ["Evidence", "50 unique references", "Reference artifacts without copying them"],
            ["Authority", "AI remains advisory", "Prevent direct vehicle or test mutation"],
        ],
        [1.55, 2.25, 3.0],
    )
    doc.add_heading("3 Tasks and Subjects", level=1)
    table(
        doc,
        ["Dimension", "Supported values"],
        [
            [
                "Tasks",
                "Log analysis, failure explanation, test suggestion, root cause, risk analysis",
            ],
            ["Subjects", "Test run, automation report, fault execution, mutation execution"],
            ["Lifecycle", "IX-1 creates queued requests; IX-2 owns execution and results"],
        ],
        [1.55, 5.25],
    )
    doc.add_heading("4 Verification Catalogue", level=1)
    table(
        doc,
        ["ID", "Objective"],
        [
            ["AI-T-001", "Validate schema and resource bounds"],
            ["AI-T-002", "Verify local-only defaults"],
            ["AI-T-003", "Reject restricted external processing"],
            ["AI-T-004", "Verify idempotency and conflict"],
            ["AI-T-005", "Verify minimized audit and event evidence"],
            ["AI-T-006", "Verify RBAC and OpenAPI contracts"],
            ["AI-T-007", "Apply migration through hosted Docker integration"],
        ],
        [1.4, 5.4],
    )
    doc.add_heading("5 Risks and Next Development", level=1)
    table(
        doc,
        ["Risk", "Control"],
        [
            ["Sensitive data egress", "Classification and provider policy gate"],
            ["Hallucinated authority", "Advisory-only boundary and future citations"],
            ["Unexpected cost", "No provider call and local-only default"],
            ["Resource consumption", "No model or GPU in IX-1"],
            ["Prompt leakage", "Minimized audit and outbox metadata"],
        ],
        [2.2, 4.6],
    )
    doc.add_paragraph(
        "IX-2 will add deterministic local rules, worker lifecycle, retries, and result contracts "
        "before any optional LLM adapter. This order keeps the platform testable, free to run, "
        "and provider neutral."
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)


if __name__ == "__main__":
    build()
