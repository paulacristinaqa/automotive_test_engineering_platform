from pathlib import Path

import build_volume_i_workbook as workbook

SOURCE = workbook.ROOT / "docs" / "workbook-volume-ii.md"
OUTPUT = workbook.ROOT / "docs" / "ATEP_Volume_II_Digital_Vehicle_Engineering_Workbook.docx"
VOLUME_NUMBER = "II"
VOLUME_NAME = "Digital Vehicle"
DOCUMENT_VERSION = "0.4.0"
DOCUMENT_STATUS = "Living document - Increments II-1 through II-4 implemented"


def build() -> Path:
    original = (
        workbook.SOURCE,
        workbook.OUTPUT,
        workbook.VOLUME_NUMBER,
        workbook.VOLUME_NAME,
        workbook.DOCUMENT_VERSION,
        workbook.DOCUMENT_STATUS,
    )
    try:
        workbook.SOURCE = SOURCE
        workbook.OUTPUT = OUTPUT
        workbook.VOLUME_NUMBER = VOLUME_NUMBER
        workbook.VOLUME_NAME = VOLUME_NAME
        workbook.DOCUMENT_VERSION = DOCUMENT_VERSION
        workbook.DOCUMENT_STATUS = DOCUMENT_STATUS
        return workbook.build()
    finally:
        (
            workbook.SOURCE,
            workbook.OUTPUT,
            workbook.VOLUME_NUMBER,
            workbook.VOLUME_NAME,
            workbook.DOCUMENT_VERSION,
            workbook.DOCUMENT_STATUS,
        ) = original


if __name__ == "__main__":
    print(build())
