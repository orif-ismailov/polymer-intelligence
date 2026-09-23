"""Read the Central Bank's bank-branch register out of the .xlsx it is published as.

Pure: bytes in, rows out. No database, no filesystem, no network — which is what
lets the seeder and the admin upload share one code path and one set of tests.

**No Excel library.** An `.xlsx` is a ZIP of XML parts; `zipfile` is stdlib and
`defusedxml` is already a dependency (and is the right parser here — this file
arrives over an upload endpoint, so entity expansion is a real attack surface and
stdlib `ElementTree` would carry it).

Three properties of the published file that the code below is shaped by, all
confirmed against the copy in `app/seed/data/`:

  * **Its own row counter lies.** The metadata block says «Qatorlar soni: 376»;
    the sheet holds 324. Nothing validates against that number — we count rows.
  * **The four sheets are four LANGUAGES of one dataset.** Bank and branch names
    are byte-identical across all of them (Latin Uzbek); only the address column
    and the headers are translated. The sheet index is therefore close to
    cosmetic, and defaults to the Russian one only because the rest of the
    product does.
  * **The MFO is stored as a STRING** (`"00401"`), so its leading zeros survive.
    Read as a number it would become `401` and join against nothing.

The header row is found by its first cell rather than by position, because the
metadata block above it has neither a fixed height nor a fixed shape.
"""

from __future__ import annotations

import datetime
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import cast
from xml.etree.ElementTree import Element  # noqa: S405 — TYPE ONLY; parsing is defusedxml's

from defusedxml import ElementTree as DefusedET

#: The spreadsheetml namespace every part of a workbook lives in.
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

#: First cell of the header row, in each language the register ships in. Matching
#: on the label rather than on a row number: the metadata block above it varies.
_HEADER_LABELS: frozenset[str] = frozenset(
    {"filial kodi", "филиал коди", "код филиала", "branch code"}
)

#: Label introducing the register's publication date. Its VALUE sits in the cell
#: below, not beside it.
_CREATED_LABELS: frozenset[str] = frozenset(
    {
        "fayl yaratilgan sana",
        "файл яратилган сана",
        "дата создания файла",
        "file creation date",
    }
)

#: Columns A–D of a data row. The rest (address, region, STIR, website…) is
#: translated per sheet and unused — the feature needs a bank name for an MFO.
_COL_MFO, _COL_TYPE, _COL_BANK, _COL_BRANCH = "A", "B", "C", "D"

_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


class BankRegisterInvalid(ValueError):
    """The upload is not a register we can trust.

    A `ValueError` so the routers' existing `ValueError → 422` mapping applies
    without a second except-clause.
    """


@dataclass(frozen=True)
class BankBranchRow:
    """One branch: the MFO, its parent bank, and the branch's own name."""

    mfo: str
    bank_name: str
    branch_name: str
    branch_type: str


@dataclass(frozen=True)
class ParsedRegister:
    """What one file yielded. `row_count` is what we PARSED, never what it claimed."""

    rows: tuple[BankBranchRow, ...]
    file_created_at: datetime.date | None

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _xml(data: bytes) -> Element:
    """Parse with defusedxml, typed as the stdlib element it returns.

    `defusedxml` ships no stubs, so every element it hands back is `Any` and the
    explicit-Any ban would spread from here through the whole module. One cast at
    the boundary keeps the rest of the file typed — and the PARSER is still the
    hardened one, which is what matters when the bytes came from an upload.
    """
    return cast(Element, DefusedET.fromstring(data))


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """The workbook's string pool. Cells of type `s` index into it.

    A `<si>` may be split across several `<t>` runs (mixed formatting), so the
    runs are joined — taking only the first would silently truncate a bank name.
    """
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = _xml(zf.read("xl/sharedStrings.xml"))
    out: list[str] = []
    for si in root.findall("m:si", _NS):
        out.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sheet_paths(zf: zipfile.ZipFile) -> list[str]:
    """Worksheet parts in workbook order.

    Derived from the sheet list rather than by globbing the directory, because
    `sheet1.xml` is not guaranteed to be the first tab.
    """
    names = zf.namelist()
    if "xl/workbook.xml" not in names:
        raise BankRegisterInvalid("not_a_workbook")
    root = _xml(zf.read("xl/workbook.xml"))
    sheets = root.findall(".//m:sheet", _NS)
    if not sheets:
        raise BankRegisterInvalid("workbook_has_no_sheets")
    paths = [f"xl/worksheets/sheet{i}.xml" for i in range(1, len(sheets) + 1)]
    return [p for p in paths if p in names]


def _rows(zf: zipfile.ZipFile, path: str, pool: list[str]) -> list[dict[str, str]]:
    """One worksheet as a list of {column letter: text} dicts."""
    root = _xml(zf.read(path))
    out: list[dict[str, str]] = []
    for row in root.findall(".//m:row", _NS):
        cells: dict[str, str] = {}
        for c in row.findall("m:c", _NS):
            ref = c.get("r") or ""
            col = "".join(ch for ch in ref if ch.isalpha())
            cells[col] = _cell_text(c, pool)
        out.append(cells)
    return out


def _cell_text(cell: Element, pool: list[str]) -> str:
    """A cell's text, whichever way this workbook chose to store it."""
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter() if _local(t.tag) == "t").strip()
    value = cell.find("m:v", _NS)
    if value is None or value.text is None:
        return ""
    if kind == "s":
        try:
            return pool[int(value.text)].strip()
        except (ValueError, IndexError):
            return ""
    return value.text.strip()


def _file_created_at(rows: list[dict[str, str]], header_at: int) -> datetime.date | None:
    """«Fayl yaratilgan sana» — label in one row, value in the row BELOW it.

    Only the metadata block above the header is searched: a date further down is
    a branch's opening date, which is a different fact.
    """
    for i, row in enumerate(rows[:header_at]):
        for text in row.values():
            if text.lower().strip() in _CREATED_LABELS:
                for candidate in rows[i + 1 : header_at + 1]:
                    for value in candidate.values():
                        match = _DATE_RE.match(value.strip())
                        if match:
                            day, month, year = (int(g) for g in match.groups())
                            try:
                                return datetime.date(year, month, day)
                            except ValueError:
                                return None
    return None


def parse_register(content: bytes, *, sheet_index: int = 2) -> ParsedRegister:
    """Parse the register. `sheet_index` defaults to the Russian sheet (0-based).

    Raises `BankRegisterInvalid` for anything we would not want to import: not a
    ZIP, not a workbook, no recognisable header, no rows, a malformed MFO or a
    duplicate one. Refusing here is what lets the caller replace the live table
    only after a parse has fully succeeded.
    """
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise BankRegisterInvalid("not_a_zip") from exc

    with zf:
        paths = _sheet_paths(zf)
        if not 0 <= sheet_index < len(paths):
            raise BankRegisterInvalid("sheet_out_of_range")
        pool = _shared_strings(zf)
        raw = _rows(zf, paths[sheet_index], pool)

    header_at = next(
        (i for i, r in enumerate(raw) if r.get(_COL_MFO, "").lower().strip() in _HEADER_LABELS),
        None,
    )
    if header_at is None:
        raise BankRegisterInvalid("header_row_not_found")

    rows: list[BankBranchRow] = []
    seen: set[str] = set()
    for row in raw[header_at + 1 :]:
        mfo = row.get(_COL_MFO, "").strip()
        if not mfo:
            continue  # trailing blank rows are ordinary in a published sheet
        if not (mfo.isdigit() and len(mfo) == 5):
            raise BankRegisterInvalid(f"bad_mfo:{mfo}")
        if mfo in seen:
            raise BankRegisterInvalid(f"duplicate_mfo:{mfo}")
        bank = row.get(_COL_BANK, "").strip()
        if not bank:
            raise BankRegisterInvalid(f"missing_bank_name:{mfo}")
        seen.add(mfo)
        rows.append(
            BankBranchRow(
                mfo=mfo,
                bank_name=bank,
                branch_name=row.get(_COL_BRANCH, "").strip(),
                branch_type=row.get(_COL_TYPE, "").strip(),
            )
        )

    if not rows:
        raise BankRegisterInvalid("no_rows")

    return ParsedRegister(rows=tuple(rows), file_created_at=_file_created_at(raw, header_at))
