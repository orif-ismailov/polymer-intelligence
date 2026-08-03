"""
Showcase content for the role-specific company profiles (migrations 0031-0033).

Pure data, no DB — the mechanics live in `seed_showcase_profiles.py`, the same
split as `showcase_data.py` / `seed_showcase.py`.

Every list value here is a member of the option vocabulary the registration
wizard writes (`portal/src/features/company-wizard/model/constants.ts`), so the
profile screens render translated labels instead of raw strings. A value invented
here would show up in the UI as itself, which is exactly the "generated without
purpose" look these profiles are meant to avoid.
"""

from __future__ import annotations

# ── Manufacturer profiles ─────────────────────────────────────────────────────
# production_type ∈ PRODUCTION_TYPES · main_products ∈ MAIN_PRODUCT_OPTIONS
# markets ∈ MARKET_OPTIONS · export_countries ∈ EXPORT_COUNTRY_OPTIONS
# iso_certification ∈ ISO_OPTIONS · financial_requirements keys ∈ FINANCIAL_REQUIREMENT_KEYS
# additional_requirements ∈ ADDITIONAL_REQUIREMENT_KEYS

MANUFACTURER_PROFILES: dict[str, dict[str, object]] = {
    "shurtan": {
        "production_type": "polymers",
        "main_products": "pp",
        "annual_capacity_tons": 125_000,
        "production_lines": 4,
        "employees": 2_400,
        "markets": ["domestic", "export"],
        "export_countries": ["KZ", "RU", "TJ", "TM"],
        "founded_year": 2001,
        "iso_certification": "iso_9001",
        "moq_tons": 20,
        "min_annual_volume_tons": 500,
        "financial_requirements": {
            "bank_guarantee": True, "letter_of_credit": True,
            "payment_deferral": False, "prepayment": True,
        },
        "additional_requirements": ["financial_reporting", "market_experience", "end_products_info"],
        "additional_other": "Приоритет — переработчики с собственным производством в Узбекистане.",
    },
    "uzkor": {
        "production_type": "polymers",
        "main_products": "hdpe",
        "annual_capacity_tons": 387_000,
        "production_lines": 6,
        "employees": 1_450,
        "markets": ["domestic", "export"],
        "export_countries": ["CN", "RU", "KZ", "TR", "TJ"],
        "founded_year": 2011,
        "iso_certification": "iso_14001",
        "moq_tons": 25,
        "min_annual_volume_tons": 1_000,
        "financial_requirements": {
            "bank_guarantee": True, "letter_of_credit": True,
            "payment_deferral": True, "prepayment": False,
        },
        "additional_requirements": ["financial_reporting", "licenses_certificates", "market_experience"],
        "additional_other": "Годовые контракты с квартальным пересмотром цены.",
    },
    "jizzakh": {
        "production_type": "petrochemicals",
        "main_products": "pet",
        "annual_capacity_tons": 100_000,
        "production_lines": 2,
        "employees": 780,
        "markets": ["domestic", "export"],
        "export_countries": ["KZ", "TJ", "KG", "other"],
        "founded_year": 2017,
        "iso_certification": "iso_22000",
        "moq_tons": 20,
        "min_annual_volume_tons": 600,
        "financial_requirements": {
            "bank_guarantee": False, "letter_of_credit": True,
            "payment_deferral": True, "prepayment": True,
        },
        "additional_requirements": ["end_products_info", "production_photos"],
        "additional_other": "Пищевой допуск обязателен для преформ и бутылочных марок.",
    },
    "navoiyazot": {
        "production_type": "petrochemicals",
        "main_products": "pvc",
        "annual_capacity_tons": 96_000,
        "production_lines": 3,
        "employees": 5_600,
        "markets": ["domestic"],
        "export_countries": [],
        "founded_year": 1996,
        "iso_certification": "iso_9001",
        "moq_tons": 25,
        "min_annual_volume_tons": 400,
        "financial_requirements": {
            "bank_guarantee": True, "letter_of_credit": False,
            "payment_deferral": False, "prepayment": True,
        },
        "additional_requirements": ["licenses_certificates", "financial_reporting"],
        "additional_other": None,
    },
}

#: Converters — same shape, smaller numbers, mostly domestic. Keyed by company slug.
CONVERTER_PROFILES: dict[str, tuple[str, str, int, int, int, int, str]] = {
    # slug: (production_type, main_products, capacity_t, lines, employees, founded, iso)
    "tashkent_plastic": ("compounds", "hdpe", 18_000, 5, 240, 2012, "iso_9001"),
    "andijan_pipe": ("compounds", "hdpe", 24_000, 4, 185, 2015, "iso_9001"),
    "fergana_film": ("compounds", "ldpe", 12_500, 6, 160, 2016, "none"),
    "bukhara_sacks": ("compounds", "pp", 15_000, 8, 320, 2014, "none"),
    "namangan_house": ("other", "pp", 6_400, 12, 140, 2017, "none"),
    "samarkand_pet": ("compounds", "pet", 21_000, 3, 210, 2019, "iso_22000"),
    "chirchiq_cable": ("compounds", "pvc", 9_800, 4, 175, 2013, "iso_9001"),
    "nukus_agrofilm": ("compounds", "ldpe", 8_600, 3, 95, 2018, "none"),
    "olmaliq_pipe": ("compounds", "hdpe", 19_500, 5, 205, 2016, "iso_9001"),
    "termez_pack": ("compounds", "pp", 11_200, 4, 130, 2019, "none"),
    "urgench_irrigation": ("compounds", "hdpe", 14_000, 3, 118, 2020, "none"),
    "qarshi_profile": ("compounds", "pvc", 10_400, 4, 145, 2018, "none"),
    "angren_recycling": ("recycling", "hdpe", 7_200, 2, 88, 2022, "iso_14001"),
}

# ── Logistics profiles ────────────────────────────────────────────────────────
# All members of LOGISTICS_* vocabularies.

LOGISTICS_PROFILES: dict[str, dict[str, object]] = {
    "trans_asia": {
        "city": "Ташкент",
        "services": [
            "international_road", "multimodal", "customs_clearance",
            "import_clearance", "cargo_insurance", "warehouse", "container_transport",
        ],
        "from_countries": ["CN", "IR", "RU", "KZ", "TR"],
        "to_countries": ["UZ", "KZ", "TJ"],
        "popular_routes": ["shanghai_tashkent", "bandar_abbas_tashkent", "moscow_tashkent"],
        "cargo_types": [
            "petrochemicals_polymers", "chemical_products",
            "container_shipping", "big_bags",
        ],
        "capabilities": [
            "own_trucks", "storage_facilities", "customs_warehouse", "customs_brokers",
        ],
        "tariff_model": "per_container",
        "description": (
            "Мультимодальный оператор с собственным автопарком и таможенным складом "
            "в Ташкенте. Возим полимеры и химию из Китая, Ирана и России — контейнер, "
            "биг-бэг, наливом. Полное таможенное оформление, страхование груза на "
            "полную стоимость, доставка «дверь-дверь» с одним договором."
        ),
        "years_experience": 11,
        "projects_completed": 1_840,
    },
    "rail_freight": {
        "city": "Ташкент",
        "services": ["rail", "multimodal", "export_clearance", "consolidation", "container_transport"],
        "from_countries": ["RU", "KZ", "CN"],
        "to_countries": ["UZ", "KZ", "KG", "TM"],
        "popular_routes": ["moscow_tashkent", "kazan_tashkent", "shanghai_tashkent"],
        "cargo_types": ["petrochemicals_polymers", "liquid_bulk", "dangerous_goods_adr", "big_bags"],
        "capabilities": ["own_rail_wagons", "sea_containers", "storage_facilities", "customs_brokers"],
        "tariff_model": "per_ton",
        "description": (
            "Железнодорожный экспедитор: собственный парк крытых вагонов и "
            "контейнерных платформ. Специализация — вагонные нормы полимерного "
            "сырья из Кунграда и Шуртана, а также импорт из России и Казахстана. "
            "Консолидация сборных партий на терминале в Ташкенте."
        ),
        "years_experience": 14,
        "projects_completed": 2_260,
    },
}

# ── Laboratory profiles ───────────────────────────────────────────────────────

LABORATORY_PROFILES: dict[str, dict[str, object]] = {
    "cptl_lab": {
        "city": "Ташкент",
        "website": "https://cptl.uz",
        "email": "lab@cptl.uz",
        "phone": "+998712001133",
        "description": (
            "Испытательный центр полимерных материалов с аккредитацией O‘zAK. "
            "Полный цикл входного контроля: показатель текучести расплава (ISO 1133), "
            "плотность (ISO 1183), ИК-спектроскопия для идентификации марки, ДСК, "
            "определение содержания золы и влаги. Срок стандартного анализа — "
            "3 рабочих дня, экспресс — 24 часа. Протокол испытаний принимается "
            "таможенными органами и включается в паспорт партии."
        ),
        "accreditations": ["iso_17025", "national_accreditation", "gost_certified"],
        "methods": [
            "mfi", "density", "ftir", "dsc", "tga", "ash_content", "moisture",
            "tensile_strength", "elongation", "impact_strength", "vicat", "oit",
        ],
        "years_experience": 9,
        "studies_completed": 4_120,
        "avg_turnaround_days": 3,
    },
}

# ── Reviews ───────────────────────────────────────────────────────────────────
#: (rating, body) — written as a counterparty would after a closed deal.
REVIEW_TEXTS: list[tuple[int, str]] = [
    (5, "Отгрузили точно в срок, паспорт качества на каждую партию. Работаем второй год, расхождений по массе нетто не было ни разу."),
    (5, "Оперативно согласовали спецификацию и подготовили договор через ЭЦП за один день. Рекомендуем как надёжного поставщика."),
    (4, "Качество марки стабильное, ПТР в пределах паспорта. Единственное — отгрузка сдвинулась на два дня из-за подачи транспорта."),
    (5, "Приняли образцы, дали полный протокол испытаний. После валидации на линии перешли на регулярные закупки."),
    (4, "Цена выше рынка на пару процентов, но зато отсрочка платежа 30 дней и всегда есть остаток на складе."),
    (5, "Закрыли срочную потребность за три дня, когда встала линия. Отдельное спасибо за оперативность логистики."),
    (3, "Товар соответствует, но документы пришлось запрашивать дважды. По качеству претензий нет."),
    (5, "Прозрачная сделка через эскроу — средства раскрылись после подтверждения приёмки. Всё как договаривались."),
    (4, "Хорошая коммуникация, менеджер на связи. Хотелось бы более гибких условий по минимальной партии."),
    (5, "Работаем по годовому контракту, цена фиксируется поквартально. Ни одной срыва поставки за период."),
]
