from pathlib import Path

import build_volume_i_workbook as workbook

SOURCE = workbook.ROOT / "docs" / "workbook-volume-vi.md"
OUTPUT = workbook.ROOT / "docs" / "ATEP_Volume_VI_Electric_Vehicle_Engineering_Workbook.docx"
VOLUME_NUMBER = "VI"
VOLUME_NAME = "Electric Vehicle"
DOCUMENT_VERSION = "0.4.0"
DOCUMENT_STATUS = "VI-1 through VI-4 implemented, including AC/DC charging sessions"
BASELINE_DATE = "4 September 2026"


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
