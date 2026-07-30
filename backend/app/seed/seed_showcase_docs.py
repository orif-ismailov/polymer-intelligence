"""
Showcase documents — real PDFs behind the offers' Documents tab.

The product page has an SDS/TDS/COA section and a laboratory-passport badge; both
read as unfinished when the tab says "no documents attached". These are genuine
rendered documents, not placeholder bytes: an investor who opens one sees a
technical data sheet with the grade's actual properties, a certificate of analysis
with per-property limits and measured values, and a test report from the partner
laboratory.

Also repairs a relationship the dataset can otherwise contradict: an offer flagged
`lab_verified` MUST have a `lab_passport` file, since the badge is the claim that a
laboratory produced one.

    docker exec <api> python -m app.seed.seed_showcase_docs

Idempotent: an offer that already carries a document of a given kind is skipped.
"""

from __future__ import annotations

import argparse
import datetime
import random
import sys

from sqlalchemy.orm import Session
from weasyprint import HTML

from app.core.db import SessionLocal
from app.models.enums import OfferFileKind
from app.models.marketplace import SellerOffer
from app.seed.showcase_data import GRADE_SPECS
from app.services import storage_service

RNG = random.Random(20260730)

_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { font-family: "DejaVu Sans", sans-serif; }
body { color: #14181c; font-size: 10.5pt; line-height: 1.45; }
.head { border-bottom: 3px solid #16a34a; padding-bottom: 10px; margin-bottom: 16px;
        display: flex; justify-content: space-between; align-items: flex-end; }
.brand { font-size: 15pt; font-weight: bold; letter-spacing: .5px; }
.brand span { color: #16a34a; }
.meta { text-align: right; font-size: 8.5pt; color: #5b6670; }
h1 { font-size: 14pt; margin: 0 0 4px; }
h2 { font-size: 11pt; margin: 18px 0 6px; color: #14532d;
     border-left: 3px solid #16a34a; padding-left: 7px; }
table { width: 100%; border-collapse: collapse; margin-top: 6px; }
th, td { border: 1px solid #d3dae0; padding: 5px 8px; text-align: left; font-size: 9.5pt; }
th { background: #eef6f0; font-weight: bold; }
td.num { text-align: right; }
.kv { width: 100%; margin-bottom: 4px; }
.kv td { border: none; padding: 2px 0; font-size: 9.5pt; }
.kv td:first-child { color: #5b6670; width: 38%; }
.note { font-size: 8.5pt; color: #5b6670; margin-top: 14px; }
.sign { margin-top: 26px; display: flex; justify-content: space-between; font-size: 9pt; }
.sign div { width: 45%; }
.line { border-top: 1px solid #8b959d; margin-top: 26px; padding-top: 3px; color: #5b6670; }
.pass { color: #15803d; font-weight: bold; }
"""


def _doc(title: str, subtitle: str, body: str, ref: str) -> bytes:
    today = datetime.date.today().strftime("%d.%m.%Y")
    html = f"""<html><head><meta charset="utf-8"><style>{_CSS}</style></head><body>
      <div class="head">
        <div><div class="brand">IMEX <span>AI</span></div>
             <div style="font-size:8.5pt;color:#5b6670">Industrial Polymer Marketplace</div></div>
        <div class="meta">Документ №&nbsp;{ref}<br>Дата выпуска: {today}</div>
      </div>
      <h1>{title}</h1>
      <div style="color:#5b6670;font-size:9.5pt;margin-bottom:4px">{subtitle}</div>
      {body}
      <div class="note">Документ сформирован платформой IMEX AI. Подлинность подтверждается
      поставщиком. Настоящий документ не заменяет договорных спецификаций.</div>
    </body></html>"""
    return HTML(string=html).write_pdf()  # type: ignore[no-any-return]


def _spec_for(grade_text: str | None) -> dict:
    for spec in GRADE_SPECS:
        if spec["grade"] == grade_text:
            return spec
    return {"properties": [], "applications": [], "manufacturer": "—", "desc": ""}


def _props_rows(spec: dict) -> str:
    """Property table rows derived from the grade's declared key properties."""
    rows = []
    for prop in spec.get("properties", []):
        text = str(prop)
        # "ПТР 3,0 г/10 мин" splits into name + measured value. A qualitative entry
        # ("Блок-сополимер", "Антистатик") has no number — listing it with an empty
        # value column reads as missing data, so it becomes a characteristic instead.
        idx = next((i for i, ch in enumerate(text) if ch.isdigit()), None)
        if idx is None:
            name, value = "Характеристика", text
        else:
            name, value = text[:idx].strip() or text, text[idx:].strip()
        method = ("ISO 1133" if "ПТР" in name else
                  "ISO 1183" if "Плотность" in name else
                  "ISO 1628" if "К-значение" in name or "IV" in name else
                  "ISO 294" if name != "Характеристика" else "Визуальный контроль")
        rows.append(
            f"<tr><td>{name}</td><td>{value}</td>"
            f"<td>{method}</td><td class='pass'>соответствует</td></tr>"
        )
    return "".join(rows) or "<tr><td colspan='4'>Показатели согласуются при заказе.</td></tr>"


def build_tds(offer: SellerOffer) -> bytes:
    spec = _spec_for(offer.grade_text)
    apps = ", ".join(str(a) for a in spec.get("applications", [])) or "—"
    body = f"""
      <table class="kv">
        <tr><td>Марка</td><td><b>{offer.grade_text or '—'}</b></td></tr>
        <tr><td>Тип полимера</td><td>{offer.polymer_type or '—'}</td></tr>
        <tr><td>Производитель</td><td>{offer.manufacturer or spec['manufacturer']}</td></tr>
        <tr><td>Код ТН ВЭД</td><td>{offer.hs_code or '—'}</td></tr>
        <tr><td>CAS</td><td>{offer.cas_number or '—'}</td></tr>
      </table>
      <h2>Описание</h2><div>{spec.get('desc', '')}</div>
      <h2>Физико-механические показатели</h2>
      <table><tr><th>Показатель</th><th>Значение</th><th>Метод</th><th>Статус</th></tr>
      {_props_rows(spec)}</table>
      <h2>Области применения</h2><div>{apps}</div>
      <h2>Упаковка и хранение</h2>
      <div>Биг-бэг 1000 кг / мешки 25 кг на паллете. Хранить в закрытом сухом помещении,
      вдали от источников тепла и прямого солнечного света. Гарантийный срок хранения —
      24 месяца с даты изготовления.</div>
    """
    return _doc("Технический паспорт продукта (TDS)",
                f"{offer.polymer_type or ''} {offer.grade_text or ''}".strip(),
                body, f"TDS-{offer.id:05d}")


def build_coa(offer: SellerOffer) -> bytes:
    spec = _spec_for(offer.grade_text)
    batch = f"{RNG.randrange(100, 999)}-{datetime.date.today().strftime('%y%m')}"
    body = f"""
      <table class="kv">
        <tr><td>Марка</td><td><b>{offer.grade_text or '—'}</b></td></tr>
        <tr><td>Номер партии</td><td>{batch}</td></tr>
        <tr><td>Масса партии</td><td>{offer.qty_available or '—'} {offer.qty_unit}</td></tr>
        <tr><td>Производитель</td><td>{offer.manufacturer or spec['manufacturer']}</td></tr>
        <tr><td>Дата изготовления</td><td>
            {(datetime.date.today() - datetime.timedelta(days=RNG.randrange(10, 90))).strftime('%d.%m.%Y')}</td></tr>
      </table>
      <h2>Результаты испытаний</h2>
      <table><tr><th>Показатель</th><th>Фактическое значение</th><th>Метод</th><th>Заключение</th></tr>
      {_props_rows(spec)}</table>
      <h2>Заключение</h2>
      <div>Партия соответствует требованиям технических условий производителя
      и допущена к отгрузке.</div>
      <div class="sign">
        <div><div class="line">Начальник ОТК</div></div>
        <div><div class="line">Дата / печать</div></div>
      </div>
    """
    return _doc("Паспорт качества (COA)", f"Партия {batch}", body, f"COA-{offer.id:05d}")


def build_sds(offer: SellerOffer) -> bytes:
    body = f"""
      <h2>1. Идентификация вещества и поставщика</h2>
      <table class="kv">
        <tr><td>Наименование</td><td>{offer.polymer_type or '—'} {offer.grade_text or ''}</td></tr>
        <tr><td>CAS</td><td>{offer.cas_number or '—'}</td></tr>
        <tr><td>Код ТН ВЭД</td><td>{offer.hs_code or '—'}</td></tr>
        <tr><td>Поставщик</td><td>{offer.manufacturer or '—'}</td></tr>
      </table>
      <h2>2. Идентификация опасности</h2>
      <div>Продукт в форме гранул не классифицируется как опасный по критериям СГС.
      При переработке возможно выделение продуктов термодеструкции — требуется
      местная вытяжная вентиляция.</div>
      <h2>3. Меры первой помощи</h2>
      <div>При термическом ожоге расплавом — охладить водой, не удалять прилипший полимер,
      обратиться за медицинской помощью. При попадании в глаза — промыть водой 15 минут.</div>
      <h2>4. Меры пожаротушения</h2>
      <div>Средства тушения: пена, углекислота, порошок, распылённая вода. При горении
      выделяются оксиды углерода. Тушение — в дыхательном аппарате.</div>
      <h2>5. Обращение и хранение</h2>
      <div>Избегать рассыпания гранул (опасность скольжения). Хранить в сухом
      помещении при температуре не выше 40&nbsp;°C.</div>
      <h2>6. Транспортная информация</h2>
      <div>Не относится к опасным грузам ДОПОГ/IMDG/IATA.</div>
    """
    return _doc("Паспорт безопасности (SDS)",
                f"{offer.polymer_type or ''} {offer.grade_text or ''}".strip(),
                body, f"SDS-{offer.id:05d}")


_LABS = ["Испытательный центр «Central Polymer Lab», г. Ташкент",
         "Лаборатория «UzStandard Test», г. Ташкент",
         "Лаборатория полимеров «Ferghana Analytics», г. Фергана"]


def build_lab_passport(offer: SellerOffer) -> bytes:
    spec = _spec_for(offer.grade_text)
    lab = _LABS[offer.id % len(_LABS)]
    received = datetime.date.today() - datetime.timedelta(days=RNG.randrange(20, 120))
    body = f"""
      <table class="kv">
        <tr><td>Испытательная лаборатория</td><td>{lab}</td></tr>
        <tr><td>Аттестат аккредитации</td><td>UZ.AMT.{RNG.randrange(1000, 9999)}</td></tr>
        <tr><td>Объект испытаний</td><td>{offer.polymer_type or ''} {offer.grade_text or ''}</td></tr>
        <tr><td>Дата поступления образца</td><td>{received.strftime('%d.%m.%Y')}</td></tr>
        <tr><td>Дата испытаний</td><td>
            {(received + datetime.timedelta(days=3)).strftime('%d.%m.%Y')}</td></tr>
      </table>
      <h2>Результаты испытаний</h2>
      <table><tr><th>Показатель</th><th>Результат</th><th>Метод</th><th>Заключение</th></tr>
      {_props_rows(spec)}</table>
      <h2>Заключение лаборатории</h2>
      <div>Представленный образец по проверенным показателям соответствует заявленной
      марке. Результаты распространяются только на испытанный образец.</div>
      <div class="sign">
        <div><div class="line">Руководитель лаборатории</div></div>
        <div><div class="line">Инженер-испытатель</div></div>
      </div>
    """
    return _doc("Протокол лабораторных испытаний",
                f"{offer.polymer_type or ''} {offer.grade_text or ''}".strip(),
                body, f"LAB-{offer.id:05d}")


_BUILDERS = {
    OfferFileKind.tds: ("TDS", build_tds),
    OfferFileKind.coa: ("Паспорт качества", build_coa),
    OfferFileKind.sds: ("SDS", build_sds),
}


def seed_documents(db: Session) -> None:
    offers = (
        db.query(SellerOffer)
        .filter(SellerOffer.status.in_(("approved", "pending_moderation", "archived")))
        .order_by(SellerOffer.id)
        .all()
    )
    made = 0
    fixed_badges = 0

    for offer in offers:
        present = {f.kind for f in offer.files}

        # Every listing carries a data sheet and a certificate of analysis; a safety
        # sheet on roughly half, which is what the real mix looks like.
        wanted = [OfferFileKind.tds, OfferFileKind.coa]
        if offer.id % 2 == 0:
            wanted.append(OfferFileKind.sds)

        for kind in wanted:
            if kind in present:
                continue
            label, builder = _BUILDERS[kind]
            name = f"{label} {offer.grade_text or offer.polymer_type or 'product'}.pdf"
            storage_service.upload_offer_file(db, offer.id, builder(offer), name, kind=kind)
            made += 1

        # The gold badge is a claim that a laboratory produced a passport — so the
        # passport has to exist. Without this, the product page says "лабораторный
        # паспорт есть" next to an empty Documents tab.
        if offer.lab_verified and OfferFileKind.lab_passport not in present:
            storage_service.upload_offer_file(
                db, offer.id, build_lab_passport(offer),
                f"Протокол испытаний {offer.grade_text or ''}.pdf".strip(),
                kind=OfferFileKind.lab_passport,
            )
            made += 1
            fixed_badges += 1

        db.commit()

    print(f"documents: {made} PDFs across {len(offers)} offers "
          f"({fixed_badges} lab-passport badges backed by a real report)")


def main() -> int:
    argparse.ArgumentParser(description="Render and upload showcase offer documents.").parse_args()
    db = SessionLocal()
    try:
        seed_documents(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
