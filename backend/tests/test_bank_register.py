"""Parsing the Central Bank's branch register (.xlsx) with the standard library.

The register is the join between an MFO and a bank name: «Код филиала» IS the
5-digit MFO a company types on the registration bank step. It is republished
periodically, so the parser has to survive a file we did not author.

Everything here runs against the REAL file (`app/seed/data/bank_branches.xlsx`),
because the two traps it contains are exactly the ones a hand-made fixture would
paper over:

  * **The file's own row counter is wrong.** «Qatorlar soni» says 376; the sheet
    holds 324. An importer that validated against that number would reject every
    real register. We count what we parsed.
  * **Four sheets are four LANGUAGES**, not four datasets — same 324 rows, and the
    bank/branch names are byte-identical across all of them (they are Latin
    Uzbek). Only the address column and the headers are translated. So the sheet
    we pick may not change a single name.

No Excel library: an `.xlsx` is a ZIP of XML, `zipfile` is stdlib and `defusedxml`
is already a dependency.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.domains.reference.bank_register import (
    BankRegisterInvalid,
    parse_register,
)

_FILE = Path(__file__).resolve().parents[1] / "app" / "seed" / "data" / "bank_branches.xlsx"


@pytest.fixture(scope="module")
def content() -> bytes:
    return _FILE.read_bytes()


class TestTheRealRegister:
    def test_it_parses_the_rows_that_are_there_not_the_count_the_file_claims(
        self, content: bytes
    ) -> None:
        """«Qatorlar soni: 376» vs 324 actual rows — the header is not evidence."""
        parsed = parse_register(content)
        assert len(parsed.rows) == 324
        assert parsed.row_count == 324

    def test_the_mfo_is_the_five_digit_branch_code(self, content: bytes) -> None:
        """Leading zeros survive because the cell is a shared STRING, not a number.
        Losing them would turn `00401` into `401` and join against nothing."""
        parsed = parse_register(content)
        for row in parsed.rows:
            assert len(row.mfo) == 5, row
            assert row.mfo.isdigit(), row

    def test_the_join_that_the_feature_rests_on(self, content: bytes) -> None:
        """`00401` is also the MFO in the captured Didox record
        (`tests/test_didox_client.py::INFO_FOUND`), which is what makes this
        register the missing half of that prefill."""
        by_mfo = {r.mfo: r for r in parse_register(content).rows}
        assert by_mfo["00401"].bank_name == "ALOQABANK"
        assert by_mfo["00001"].bank_name == "MARKAZIY BANK"

    def test_every_mfo_is_unique(self, content: bytes) -> None:
        """It is the natural key of the table, so a duplicate is not importable."""
        mfos = [r.mfo for r in parse_register(content).rows]
        assert len(set(mfos)) == len(mfos)

    def test_it_reads_the_registers_own_publication_date(self, content: bytes) -> None:
        """«Fayl yaratilgan sana» — the only thing that tells an operator whether
        the copy they are looking at is stale."""
        parsed = parse_register(content)
        assert parsed.file_created_at is not None
        assert parsed.file_created_at.isoformat() == "2024-11-18"

    def test_every_row_names_a_bank(self, content: bytes) -> None:
        """A branch with no parent bank name is the one row that cannot serve the
        feature, so it may not be imported silently."""
        for row in parse_register(content).rows:
            assert row.bank_name.strip(), row

    def test_branch_types_are_kept_not_filtered(self, content: bytes) -> None:
        """A company's account sits at a BRANCH (type 3), not at a head office, so
        filtering to head offices would miss the common case. All four types are
        imported and every one still names its parent bank."""
        types = {r.branch_type for r in parse_register(content).rows}
        assert types == {"0", "1", "2", "3"}


class TestTheSheetsAreLanguagesNotData:
    def test_the_names_are_identical_whichever_sheet_is_read(self, content: bytes) -> None:
        """Four sheets, one dataset. If this ever fails, the file's shape changed
        and picking a sheet became a real decision rather than a formality."""
        ru = {r.mfo: r.bank_name for r in parse_register(content, sheet_index=2).rows}
        uz = {r.mfo: r.bank_name for r in parse_register(content, sheet_index=0).rows}
        en = {r.mfo: r.bank_name for r in parse_register(content, sheet_index=3).rows}
        assert ru == uz == en

    def test_each_sheet_yields_the_same_row_count(self, content: bytes) -> None:
        counts = {i: len(parse_register(content, sheet_index=i).rows) for i in range(4)}
        assert set(counts.values()) == {324}, counts


class TestItRefusesWhatItCannotTrust:
    def test_a_file_that_is_not_a_zip(self) -> None:
        with pytest.raises(BankRegisterInvalid):
            parse_register(b"%PDF-1.7 this is a pdf")

    def test_a_zip_that_is_not_a_workbook(self) -> None:
        """`storage_service.validate_upload` accepts any `PK\\x03\\x04`, which is the
        generic ZIP header — a .docx or a plain .zip passes it and is labelled a
        spreadsheet. The parser is the real gate."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("hello.txt", "not a workbook")
        with pytest.raises(BankRegisterInvalid):
            parse_register(buf.getvalue())

    def test_an_empty_register(self) -> None:
        """Zero rows would empty the live table on import. Refused rather than
        applied — a register with no banks in it is a broken file, not an update."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheets><sheet name="S1" sheetId="1"/></sheets></workbook>',
            )
            zf.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData/></worksheet>",
            )
        with pytest.raises(BankRegisterInvalid):
            parse_register(buf.getvalue())

    def test_an_out_of_range_sheet(self, content: bytes) -> None:
        with pytest.raises(BankRegisterInvalid):
            parse_register(content, sheet_index=9)
