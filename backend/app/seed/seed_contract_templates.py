"""Contract template seed (R3 Stage B — TB1.1).

Seeds the initial supply-contract template (`SUPPLY_V1`). The body HTML lives in
`data/contract_templates/` and is uploaded to S3 (`body_storage_path`); the row is
inserted idempotently (`ON CONFLICT (code) DO NOTHING`).

WARNING: the bundled body is a DEV placeholder (lorem/структура). The production
contract text is supplied by the legal team and is a launch blocker (TB4.4) — swap
the file + bump `version` before go-live.

Usage:
    python -m app.seed.seed_contract_templates
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.domains.contracts.models import ContractTemplate
from app.services import storage_service

_DATA_DIR = Path(__file__).parent / "data" / "contract_templates"

_SUPPLY_V1_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "product",
        "qty",
        "unit",
        "price",
        "currency",
        "incoterms",
        "payment_terms",
        "delivery_window",
    ],
    "properties": {
        "product": {"type": "string", "title": "Товар"},
        "qty": {"type": "string", "title": "Количество"},
        "unit": {"type": "string", "title": "Ед. изм.", "enum": ["kg", "t", "pcs"]},
        "price": {"type": "string", "title": "Цена"},
        "currency": {"type": "string", "title": "Валюта", "enum": ["UZS", "USD", "EUR", "RUB", "CNY"]},
        "incoterms": {
            "type": "string",
            "title": "Incoterms",
            "enum": ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP"],
        },
        "payment_terms": {"type": "string", "title": "Условия оплаты"},
        "delivery_window": {"type": "string", "title": "Срок поставки"},
        "special_conditions": {"type": "string", "title": "Особые условия"},
    },
}


#: SUPPLY_V2 = V1 plus the cabinet credentials. A NEW row rather than a version bump
#: on V1: `contracts.template_version` records what the parties signed, and re-rendering
#: an existing contract would move `document_sha256` — which is bound into the E-IMZO
#: sign challenge and re-checked nightly. Both new fields are OPTIONAL, so every
#: contract drafted without them stays valid and `render._fill` prints "" for a missing
#: key.
_SUPPLY_V2_SCHEMA: dict[str, object] = {
    **_SUPPLY_V1_SCHEMA,
    "properties": {
        **_SUPPLY_V1_SCHEMA["properties"],  # type: ignore[dict-item]
        "portal_login": {"type": "string", "title": "Логин в кабинете"},
        "portal_password": {"type": "string", "title": "Пароль кабинета"},
    },
}


#: The letter is rendered from the sample request, not typed by anyone, so its
#: "variables" are documentation of what the renderer supplies rather than a form
#: schema. Kept in the same shape as SUPPLY_V1 so one template table serves both.
_SAMPLE_LETTER_V1_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["product", "sample_qty", "seller_terms"],
    "properties": {
        "product": {"type": "string", "title": "Материал"},
        "sample_qty": {"type": "string", "title": "Количество пробы"},
        "sample_price": {"type": "string", "title": "Стоимость пробы"},
        "delivery_address": {"type": "string", "title": "Адрес доставки"},
        "offer_id": {"type": "string", "title": "Объявление"},
        "letter_number": {"type": "string", "title": "Номер письма"},
        "sample_public_id": {"type": "string", "title": "Заявка"},
        "seller_terms": {"type": "string", "title": "Условия поставщика"},
    },
}


def _enum(title: str, labels: dict[str, str], *, group: str, default: str | None = None,
          when: dict[str, str] | None = None, hidden: bool = False) -> dict[str, object]:
    spec: dict[str, object] = {
        "type": "string", "title": title, "enum": list(labels), "x-enum-labels": labels,
        "x-group": group,
    }
    if default is not None:
        spec["default"] = default
    if when:
        spec["x-when"] = when
    if hidden:
        spec["x-hidden"] = True
    return spec


def _text(title: str, *, group: str, default: str | None = None,
          when: dict[str, str] | None = None, kind: str | None = None) -> dict[str, object]:
    spec: dict[str, object] = {"type": "string", "title": title, "x-group": group}
    if default is not None:
        spec["default"] = default
    if when:
        spec["x-when"] = when
    if kind:
        spec["x-input"] = kind
    return spec


#: The switches of the real MGBUS supply contracts (docs/deals_documents/). Each
#: enum picks a clause in `supply_mgbus_ru.html`; defaults are the figures those
#: contracts carry. `x-group` places a field on the form, `x-when` shows it only
#: when another field has a value, `x-hidden` fixes it per template.
def _mgbus_schema(kind: str) -> dict[str, object]:
    frame = {"contract_kind": "frame"}
    one_off = {"contract_kind": "one_off"}
    subject: dict[str, object] = {
        "goods_description": _text("Предмет договора", group="subject",
                                   default="Сырье в ассортименте", when=frame),
        "amount_limit": _text("Общая сумма договора, сум с НДС", group="subject",
                              kind="number", when=frame),
        "product": _text("Товар", group="subject", when=one_off),
        "qty": _text("Количество", group="subject", kind="number", when=one_off),
        "unit": _enum("Ед. изм.", {"kg": "кг", "t": "т", "pcs": "шт"}, group="subject",
                      default="kg", when=one_off),
        "unit_price": _text("Цена за единицу, сум", group="subject", kind="number",
                            when=one_off),
        # The user's call, not ours: with VAT keeps the agreed total round (as
        # the real specifications do) but the ЭСФ may differ by a few soum;
        # without VAT matches the ЭСФ to the tiyin.
        "price_basis": _enum("Цена указана", {"with_vat": "С НДС", "without_vat": "Без НДС"},
                             group="subject", default="with_vat", when=one_off),
        "vat_rate": _enum("НДС", {"12": "12%", "0": "0%", "none": "Без НДС"},
                          group="subject", default="12", when=one_off),
    }
    required = (
        ["goods_description", "amount_limit"]
        if kind == "frame"
        else ["product", "qty", "unit", "unit_price"]
    )
    properties: dict[str, object] = {
        "contract_number": _text("Номер договора", group="parties"),
        "contract_date": _text("Дата договора", group="parties", kind="date"),
        "contract_kind": _enum("Вид договора", {"frame": "Рамочный", "one_off": "Разовый"},
                               group="subject", default=kind, hidden=True),
        "initiator_side": _enum("Мы в этом договоре", {"supplier": "Поставщик", "buyer": "Покупатель"},
                                group="parties", default="supplier"),
        "supplier_authority": _enum(
            "Поставщик действует на основании",
            {"charter": "Устава", "power_of_attorney": "Доверенности"},
            group="parties", default="charter",
        ),
        "supplier_power_of_attorney": _text(
            "Доверенность поставщика (№ и дата)", group="parties",
            when={"supplier_authority": "power_of_attorney"},
        ),
        "buyer_authority": _enum(
            "Покупатель действует на основании",
            {"charter": "Устава", "power_of_attorney": "Доверенности"},
            group="parties", default="charter",
        ),
        "buyer_power_of_attorney": _text(
            "Доверенность покупателя (№ и дата)", group="parties",
            when={"buyer_authority": "power_of_attorney"},
        ),
        **subject,
        "payment_mode": _enum("Оплата", {"prepay": "100% предоплата", "schedule": "По графику"},
                              group="payment", default="prepay"),
        "payment_schedule": _text("График платежей", group="payment",
                                  when={"payment_mode": "schedule"}, kind="multiline"),
        "refuse_after_days": _text("Просрочка оплаты, после которой поставщик вправе отказаться, банк. дней",
                                   group="payment", default="1", kind="number"),
        "delivery_days": _text("Срок поставки после оплаты, банк. дней", group="delivery",
                               default="5", kind="number"),
        "delivery_basis": _enum(
            "Базис поставки",
            {"supplier_warehouse": "Самовывоз со склада поставщика",
             "pickup_address": "Самовывоз по адресу",
             "supplier_delivers": "Доставка поставщиком"},
            group="delivery", default="supplier_warehouse",
        ),
        "pickup_days": _text("Срок самовывоза после извещения, дней", group="delivery",
                             default="5", kind="number"),
        "delivery_address": _text("Адрес", group="delivery",
                                  when={"delivery_basis": "pickup_address|supplier_delivers"}),
        "delivery_note": _text("Дополнительно о доставке", group="delivery", kind="multiline"),
        "packaging": _enum("Тара и упаковка",
                           {"none": "Не указывать", "bulk": "Без упаковки, наливом",
                            "in_containers": "В таре, включена в цену"},
                           group="extra", default="none"),
        "quality_section": _enum("Раздел «Качество»", {"no": "Нет", "yes": "Да"},
                                 group="extra", default="no"),
        "penalty_delivery_pct": _text("Пеня за просрочку поставки, % в день", group="penalties",
                                      default="0,1"),
        "penalty_delivery_cap": _text("…но не более, % от суммы договора", group="penalties",
                                      default="10"),
        "penalty_payment_pct": _text("Пеня за просрочку оплаты, % в день", group="penalties",
                                     default="0,5"),
        "penalty_payment_cap": _text("…но не более, % от просроченной суммы", group="penalties",
                                     default="50"),
        "refusal_fine_pct": _text("Штраф за невыборку оплаченной продукции, %",
                                  group="penalties", default="5"),
    }
    return {
        "type": "object",
        "required": ["contract_number", "contract_date", *required],
        "properties": properties,
        # JSONB keeps no key order, and the form must read top to bottom the way
        # the contract does — so the order is stated, not inherited.
        "x-order": list(properties),
    }


#: Code → (kind, names). Both share one body: the legal text is one text, and the
#: kind is a switch fixed per template rather than a second copy to keep in step.
_MGBUS_TEMPLATES: dict[str, tuple[str, str, str, str]] = {
    "SUPPLY_FRAME_V1": ("frame", "Договор поставки — рамочный",
                        "Yetkazib berish shartnomasi — ramkaviy", "Supply contract — framework"),
    "SUPPLY_ONE_OFF_V1": ("one_off", "Договор поставки — разовый",
                          "Yetkazib berish shartnomasi — bir martalik", "Supply contract — one-off"),
}


def seed_contract_templates(db: Session | None = None) -> list[ContractTemplate]:
    """Seed the contract templates (idempotent). Returns rows created this run."""
    own = db is None
    session = db or SessionLocal()
    created: list[ContractTemplate] = []
    try:
        existing = session.execute(
            select(ContractTemplate).where(ContractTemplate.code == "SUPPLY_V1")
        ).scalar_one_or_none()
        if existing is None:
            html = (_DATA_DIR / "supply_v1_ru.html").read_text(encoding="utf-8")
            path = storage_service.store_contract_template("SUPPLY_V1", 1, html)
            template = ContractTemplate(
                code="SUPPLY_V1",
                name_ru="Договор поставки (полимеры)",
                name_uz="Yetkazib berish shartnomasi (polimerlar)",
                name_en="Supply contract (polymers)",
                body_storage_path=path,
                variables_schema=_SUPPLY_V1_SCHEMA,
                version=1,
                # Superseded by the MGBUS-based templates below (24.09.2026).
                is_active=False,
            )
            session.add(template)
            session.flush()
            created.append(template)

        existing_v2 = session.execute(
            select(ContractTemplate).where(ContractTemplate.code == "SUPPLY_V2")
        ).scalar_one_or_none()
        if existing_v2 is None:
            html_v2 = (_DATA_DIR / "supply_v2_ru.html").read_text(encoding="utf-8")
            path_v2 = storage_service.store_contract_template("SUPPLY_V2", 1, html_v2)
            template_v2 = ContractTemplate(
                code="SUPPLY_V2",
                name_ru="Договор поставки (полимеры, с доступом в кабинет)",
                name_uz="Yetkazib berish shartnomasi (kabinetga kirish bilan)",
                name_en="Supply contract (with cabinet access)",
                body_storage_path=path_v2,
                variables_schema=_SUPPLY_V2_SCHEMA,
                version=1,
                is_active=False,
            )
            session.add(template_v2)
            session.flush()
            created.append(template_v2)

        mgbus_html = (_DATA_DIR / "supply_mgbus_ru.html").read_text(encoding="utf-8")
        for code, (kind, name_ru, name_uz, name_en) in _MGBUS_TEMPLATES.items():
            if session.execute(
                select(ContractTemplate).where(ContractTemplate.code == code)
            ).scalar_one_or_none() is not None:
                continue
            row = ContractTemplate(
                code=code,
                name_ru=name_ru,
                name_uz=name_uz,
                name_en=name_en,
                body_storage_path=storage_service.store_contract_template(code, 1, mgbus_html),
                variables_schema=_mgbus_schema(kind),
                version=1,
                is_active=True,
            )
            session.add(row)
            session.flush()
            created.append(row)
            # The dev placeholders step aside the moment their replacement exists —
            # never before, so no deployment is ever left with nothing to pick.
            # Only on this first creation: a template staff re-enable stays on.
            for legacy in session.execute(
                select(ContractTemplate).where(ContractTemplate.code.in_(("SUPPLY_V1", "SUPPLY_V2")))
            ).scalars():
                legacy.is_active = False
            session.flush()

        # The specification to a framework contract — its own form, the AKFA
        # «Спецификация № 01». Rendered by `contracts.specifications`.
        if session.execute(
            select(ContractTemplate).where(ContractTemplate.code == "SPECIFICATION_V1")
        ).scalar_one_or_none() is None:
            spec_html = (_DATA_DIR / "specification_mgbus_ru.html").read_text(encoding="utf-8")
            spec_row = ContractTemplate(
                code="SPECIFICATION_V1",
                kind="specification",
                name_ru="Спецификация к договору поставки",
                name_uz="Yetkazib berish shartnomasiga spetsifikatsiya",
                name_en="Specification to a supply contract",
                body_storage_path=storage_service.store_contract_template(
                    "SPECIFICATION_V1", 1, spec_html
                ),
                variables_schema={"type": "object", "properties": {}},
                version=1,
                is_active=True,
            )
            session.add(spec_row)
            session.flush()
            created.append(spec_row)

        # The commitment letter shares this table (`kind` discriminates) and the
        # same pure renderer. A second table plus a second `{{ key }}` substituter
        # would have been two things to keep in step for no gain.
        existing_letter = session.execute(
            select(ContractTemplate).where(ContractTemplate.code == "SAMPLE_LETTER_V1")
        ).scalar_one_or_none()
        if existing_letter is None:
            letter_html = (_DATA_DIR / "sample_letter_v1_ru.html").read_text(encoding="utf-8")
            letter_path = storage_service.store_contract_template("SAMPLE_LETTER_V1", 1, letter_html)
            letter = ContractTemplate(
                code="SAMPLE_LETTER_V1",
                kind="sample_letter",
                name_ru="Письмо-обязательство (проба)",
                name_uz="Majburiyat xati (namuna)",
                name_en="Sample commitment letter",
                body_storage_path=letter_path,
                variables_schema=_SAMPLE_LETTER_V1_SCHEMA,
                version=1,
                is_active=True,
            )
            session.add(letter)
            session.flush()
            created.append(letter)
        if own:
            session.commit()
    finally:
        if own:
            session.close()
    return created


if __name__ == "__main__":  # pragma: no cover
    rows = seed_contract_templates()
    print(f"seed_contract_templates: created {len(rows)} template(s)")
