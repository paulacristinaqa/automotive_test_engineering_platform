from pathlib import Path

import build_volume_i_workbook as workbook

SOURCE = workbook.ROOT / "docs" / "workbook-volume-v.md"
OUTPUT = workbook.ROOT / "docs" / "ATEP_Volume_V_Diagnostics_Engineering_Workbook.docx"
VOLUME_NUMBER = "V"
VOLUME_NAME = "Diagnostics"
DOCUMENT_VERSION = "0.1.0"
DOCUMENT_STATUS = "Implemented increment: V-1"
BASELINE_DATE = "25 August 2026"


def build() -> Path:
    original = (
        workbook.SOURCE,
        workbook.OUTPUT,
        workbook.VOLUME_NUMBER,
        workbook.VOLUME_NAME,
        workbook.DOCUMENT_VERSION,
        workbook.DOCUMENT_STATUS,
        workbook.BASELINE_DATE,
    )
    try:
        workbook.SOURCE = SOURCE
        workbook.OUTPUT = OUTPUT
        workbook.VOLUME_NUMBER = VOLUME_NUMBER
        workbook.VOLUME_NAME = VOLUME_NAME
        workbook.DOCUMENT_VERSION = DOCUMENT_VERSION
        workbook.DOCUMENT_STATUS = DOCUMENT_STATUS
        workbook.BASELINE_DATE = BASELINE_DATE
        return workbook.build()
    finally:
        (
            workbook.SOURCE,
            workbook.OUTPUT,
            workbook.VOLUME_NUMBER,
            workbook.VOLUME_NAME,
            workbook.DOCUMENT_VERSION,
            workbook.DOCUMENT_STATUS,
            workbook.BASELINE_DATE,
        ) = original


if __name__ == "__main__":
    print(build())
