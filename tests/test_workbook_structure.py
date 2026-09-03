from pathlib import Path


def test_each_active_volume_has_an_independent_source_and_output() -> None:
    volume_i = Path("tools/build_volume_i_workbook.py").read_text(encoding="utf-8")
    volume_ii = Path("tools/build_volume_ii_workbook.py").read_text(encoding="utf-8")
    volume_iv = Path("tools/build_volume_iv_workbook.py").read_text(encoding="utf-8")
    volume_v = Path("tools/build_volume_v_workbook.py").read_text(encoding="utf-8")
    volume_vi = Path("tools/build_volume_vi_workbook.py").read_text(encoding="utf-8")
    assert '"workbook-volume-i.md"' in volume_i
    assert '"ATEP_Volume_I_Core_Platform_Engineering_Workbook.docx"' in volume_i
    assert '"workbook-volume-ii.md"' in volume_ii
    assert '"ATEP_Volume_II_Digital_Vehicle_Engineering_Workbook.docx"' in volume_ii
    assert '"workbook-volume-iv.md"' in volume_iv
    assert '"ATEP_Volume_IV_CAN_Network_Engineering_Workbook.docx"' in volume_iv
    assert '"workbook-volume-v.md"' in volume_v
    assert '"ATEP_Volume_V_Diagnostics_Engineering_Workbook.docx"' in volume_v
    assert '"workbook-volume-vi.md"' in volume_vi
    assert '"ATEP_Volume_VI_Electric_Vehicle_Engineering_Workbook.docx"' in volume_vi


def test_workbook_index_covers_all_planned_volumes() -> None:
    index = Path("docs/workbooks.md").read_text(encoding="utf-8")
    for volume in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"):
        assert f"| {volume} |" in index


def test_volume_ii_workbook_tracks_domain_requirements_decisions_and_tests() -> None:
    source = Path("docs/workbook-volume-ii.md").read_text(encoding="utf-8")
    assert "DV-F-015" in source
    assert "DV-NF-008" in source
    assert "ADR-DV-003" in source
    assert "DV-T-022" in source
    assert "II-4" in source
