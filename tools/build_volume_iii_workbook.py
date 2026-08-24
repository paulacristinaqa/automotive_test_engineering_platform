from pathlib import Path

import build_volume_i_workbook as workbook

SOURCE = workbook.ROOT / "docs" / "workbook-volume-iii.md"
OUTPUT = workbook.ROOT / "docs" / "ATEP_Volume_III_ECU_Simulator_Engineering_Workbook.docx"
VOLUME_NUMBER = "III"
VOLUME_NAME = "ECU Simulator"
DOCUMENT_VERSION = "0.3.0"
DOCUMENT_STATUS = "Living document - Increments III-1 through III-3 implemented"
BASELINE_DATE = "24 August 2026"


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
