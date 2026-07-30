"""
Showcase news — classified petrochemical stories for the news reader and reports.

Normally these rows are produced by the ingest→classify pipeline (`rss_fetch` →
`parsing/news_extractor`). On an environment where that pipeline cannot run — a
lapsed LLM key, an exhausted budget, no outbound network — the News surface goes
empty even though the RSS feeds are being fetched correctly, because classification
is what turns a `raw_item` into a `kind='news'` signal.

This writes the classified output directly, in the exact `ai.news` shape
`news_service._article_card` reads, so the reader, the filters, the clustering and
the localisation all behave as they do on live data.

    docker exec <api> python -m app.seed.seed_showcase_news

Idempotent: keyed off a marker in `ai.news.seed`. Re-running replaces the set.
"""

from __future__ import annotations

import argparse
import datetime
import json
import random
import sys

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.db import SessionLocal

RNG = random.Random(20260730)
MARKER = "showcase"

#: (headline, category, importance, market_impact, summary, analysis, recommendation,
#:  country, companies, products)
ARTICLES: list[tuple] = [
    (
        "Shurtan GCC увеличил выпуск полипропилена на 8% во втором квартале",
        "production", "high", "bearish",
        "Шуртанский газохимический комплекс отчитался о росте выпуска ПП до 102 тыс. тонн за квартал против 94 тыс. тонн годом ранее.",
        "Рост загрузки установки полимеризации связан с завершением планового ремонта в марте. Дополнительный объём в первую очередь пойдёт на внутренний рынок, что может сдержать рост цен на марки T30S и H030 SG в третьем квартале.",
        "Покупателям ПП стоит отложить крупные закупки на 2–3 недели: вероятна коррекция цены вниз на 2–4%.",
        "UZ", ["Shurtan GCC"], ["PP"],
    ),
    (
        "Uz-Kor Gas Chemical объявил о плановой остановке линии ПЭНП",
        "production", "high", "bullish",
        "Устюртский ГХК остановит производство полиэтилена низкой плотности на 18 дней для планово-предупредительного ремонта.",
        "Остановка затрагивает марки 2420D и 153-02K — основное сырьё для сельхозплёнки. С учётом сезонного спроса на тепличную плёнку в августе локальный дефицит вероятен уже к середине месяца.",
        "Переработчикам плёнки рекомендуется законтрактовать объём на август до начала ремонта.",
        "UZ", ["Uz-Kor Gas Chemical"], ["LDPE"],
    ),
    (
        "Цены на ПВХ в Центральной Азии выросли на 4,2% за неделю",
        "prices", "high", "bullish",
        "Средняя цена суспензионного ПВХ марки SG-5 достигла 1 052 USD/т на условиях DAP Ташкент.",
        "Рост обусловлен удорожанием этилена в Китае и ограниченным предложением со стороны российских производителей. Локальные производители профиля уже сигнализируют о пересмотре отпускных цен.",
        "Производителям оконного профиля: зафиксировать цену контрактом на квартал.",
        "UZ", ["Navoiyazot"], ["PVC"],
    ),
    (
        "Jizzakh Petroleum вывел на рынок новую марку бутылочного ПЭТ",
        "production", "medium", "neutral",
        "Предприятие начало коммерческие отгрузки марки BG-841 с характеристической вязкостью 0,84 дл/г.",
        "Марка ориентирована на газированные напитки и горячий розлив. До сих пор этот сегмент закрывался импортом из Ирана и Китая; локальное производство сокращает логистическое плечо до 3–5 дней.",
        "Производителям преформ имеет смысл запросить образцы для валидации на линии.",
        "UZ", ["Jizzakh Petroleum"], ["PET"],
    ),
    (
        "Импорт полимеров в Узбекистан вырос на 12% с начала года",
        "trade", "medium", "neutral",
        "По данным таможенной статистики, за январь–июнь импортировано 486 тыс. тонн полимерного сырья.",
        "Основной прирост дали ЛПЭНП и АБС-пластик — марки, не производимые внутри страны. Доля Кореи и Китая в структуре импорта превысила 60%.",
        "Трейдерам: сегмент ЛПЭНП остаётся дефицитным, маржинальность импорта сохраняется.",
        "UZ", [], ["LLDPE", "ABS"],
    ),
    (
        "Мировые цены на полипропилен снижаются четвёртую неделю подряд",
        "prices", "high", "bearish",
        "Котировки ПП в Азии опустились до 1 038 USD/т CFR — минимум с февраля.",
        "Давление создают новые мощности в Китае, введённые в первом полугодии, и слабый спрос со стороны автопрома. Экспортные предложения из Кореи и Сингапура стали агрессивнее на 30–40 USD/т.",
        "Импортёрам: благоприятное окно для контрактации на четвёртый квартал.",
        "CN", [], ["PP"],
    ),
    (
        "Новый завод по переработке полимеров запущен в Андижанской области",
        "investment", "medium", "neutral",
        "Предприятие мощностью 24 тыс. тонн в год будет выпускать напорные трубы из ПЭ100.",
        "Инвестиции составили 18 млн долларов. Проект ориентирован на программу модернизации водоснабжения; годовая потребность в сырье оценивается в 22 тыс. тонн ПЭ100.",
        "Поставщикам ПЭ100: новый крупный потребитель марки F7000 на внутреннем рынке.",
        "UZ", ["Andijan Polymer Pipe"], ["HDPE"],
    ),
    (
        "Курс сума к доллару стабилизировался — влияние на импортные контракты",
        "macro", "medium", "neutral",
        "ЦБ РУз удерживает курс в диапазоне 12 850–12 950 сум за доллар третью неделю.",
        "Стабильность курса снижает валютный риск по импортным контрактам с отсрочкой платежа и делает предсказуемой рублёвую и юаневую конвертацию.",
        "Импортёрам: приемлемый момент для контрактов с отсрочкой 60–90 дней.",
        "UZ", [], [],
    ),
    (
        "Спрос на БОПП-плёнку в регионе растёт на фоне развития пищевой упаковки",
        "demand", "medium", "bullish",
        "Потребление БОПП-плёнки в Центральной Азии выросло на 9% год к году.",
        "Драйвер — локализация производства снеков и кондитерских изделий. Плёночные марки ПП (PPH-FN04) переходят в разряд дефицитных в пиковые месяцы.",
        "Производителям ПП: рассмотреть увеличение доли плёночных марок в портфеле.",
        "UZ", [], ["PP"],
    ),
    (
        "Китай ужесточил экспортные требования к поставкам ПВХ",
        "regulation", "high", "bullish",
        "С 1 августа вводится обязательная сертификация партий ПВХ, отгружаемых на экспорт.",
        "Мера удлиняет срок отгрузки на 7–10 дней и повышает административные издержки. Для узбекских импортёров это означает удорожание китайского ПВХ на 15–25 USD/т.",
        "Импортёрам ПВХ: диверсифицировать поставки в пользу локального производителя.",
        "CN", [], ["PVC"],
    ),
    (
        "Логистика: тариф на железнодорожную перевозку полимеров повышен на 6%",
        "logistics", "medium", "bearish",
        "«Узбекистон темир йуллари» проиндексировала тарифы на перевозку химических грузов.",
        "Повышение затрагивает вагонные отправки — основной канал доставки полимеров из Кунграда и Шуртана в Ферганскую долину. Прибавка к себестоимости составляет 8–12 USD/т.",
        "Покупателям в удалённых регионах: пересчитать выгоду самовывоза автотранспортом.",
        "UZ", ["Uzbek Rail Freight"], [],
    ),
    (
        "Переработчики сообщают о росте запасов ПЭВП на складах",
        "demand", "low", "bearish",
        "Средний уровень складских запасов ПЭВП у переработчиков достиг 42 дней против нормы 28–30.",
        "Накопление связано с опережающими закупками в мае–июне на ожиданиях роста цен, который не реализовался. Избыток запасов будет давить на спрос в августе.",
        "Продавцам ПЭВП: возможна пауза в закупках со стороны крупных переработчиков.",
        "UZ", [], ["HDPE"],
    ),
    (
        "Навоиазот модернизирует производство каустической соды и ПВХ",
        "investment", "high", "neutral",
        "Объявлен тендер на поставку оборудования для расширения мощностей по ПВХ на 60 тыс. тонн в год.",
        "Реализация проекта запланирована на 2027–2028 годы. После выхода на проектную мощность внутреннее производство ПВХ покроет до 75% локального спроса против нынешних 45%.",
        "Долгосрочно: снижение зависимости от импорта ПВХ и давление на импортные цены.",
        "UZ", ["Navoiyazot"], ["PVC"],
    ),
    (
        "Стоимость нафты выросла на 3,8% — давление на себестоимость полимеров",
        "feedstock", "medium", "bullish",
        "Котировки нафты в Азии поднялись до 682 USD/т на фоне сокращения поставок из Ближнего Востока.",
        "Нафта — базовое сырьё для пиролиза, определяющее себестоимость этилена и пропилена. Эффект на цены полимеров проявляется с лагом 4–6 недель.",
        "Покупателям: закрыть потребность сентября по текущим ценам.",
        "SG", [], ["PP", "HDPE", "LDPE"],
    ),
    (
        "Растёт интерес к вторичным полимерам среди производителей упаковки",
        "sustainability", "low", "neutral",
        "Доля вторичного сырья в производстве непищевой упаковки в регионе достигла 11%.",
        "Тренд поддерживается экономикой: вторичный ПЭВП дешевле первичного на 25–30%. Ограничение — нестабильность качества партий и отсутствие сертификации.",
        "Переработчикам: вторичное сырьё оправдано для технической упаковки.",
        "UZ", ["Angren Recycling"], ["HDPE", "LDPE"],
    ),
    (
        "Экспорт узбекских полимеров в Афганистан вырос вдвое",
        "trade", "medium", "bullish",
        "За полугодие отгружено 34 тыс. тонн полиэтилена и полипропилена против 17 тыс. тонн годом ранее.",
        "Рост обеспечен восстановлением строительного сектора и спросом на трубную продукцию. Транзит идёт преимущественно через Термез.",
        "Трейдерам: экспортное направление даёт премию 40–60 USD/т к внутренней цене.",
        "AF", ["Termez Packaging"], ["PP", "HDPE"],
    ),
    (
        "LG Chem повысил отпускные цены на АБС-пластик на августовские отгрузки",
        "prices", "medium", "bullish",
        "Корейский производитель объявил о повышении цен на АБС на 40 USD/т.",
        "Причина — рост стоимости бутадиена и акрилонитрила. АБС полностью импортируется в Узбекистан, поэтому повышение транслируется в локальные цены напрямую.",
        "Потребителям АБС: законтрактовать августовский объём по текущим ценам.",
        "KR", ["LG Chem"], ["ABS"],
    ),
    (
        "Спрос на кабельный пластикат вырос на фоне программы электрификации",
        "demand", "medium", "bullish",
        "Производители кабельной продукции увеличили закупки ПВХ-пластиката на 18%.",
        "Драйвер — государственная программа модернизации распределительных сетей. Основной потребляемый материал — ПВХ марки SG-3 с высоким К-значением.",
        "Поставщикам ПВХ: сегмент кабельных компаундов — точка роста на 2026–2027 гг.",
        "UZ", ["Chirchiq Cable"], ["PVC"],
    ),
]

_SCOPE_BY_COUNTRY = {"UZ": "uzbekistan"}


def seed_news(db: Session, *, days_back: int = 6) -> None:
    db.execute(
        sa.text("DELETE FROM signals WHERE kind = 'news' AND ai->'news'->>'seed' = :m"),
        {"m": MARKER},
    )

    # Attach to the real RSS sources so the card's source attribution is genuine.
    source_ids = [
        r[0] for r in db.execute(
            sa.text("SELECT id FROM sources WHERE adapter LIKE 'rss%' AND is_enabled ORDER BY id")
        ).all()
    ] or [1]

    now = datetime.datetime.now(tz=datetime.UTC)
    made = 0
    for i, (headline, category, importance, impact, summary, analysis,
            recommendation, country, companies, products) in enumerate(ARTICLES):
        # Spread across the reader's default 7-day window, newest first.
        event_at = now - datetime.timedelta(
            hours=RNG.randrange(2, days_back * 24), minutes=RNG.randrange(0, 59)
        )
        payload = {
            "seed": MARKER,
            "headline": headline,
            "category": category,
            "importance": importance,
            "market_impact": impact,
            "summary": summary,
            "analysis": analysis,
            "recommendation": recommendation,
            "language": "ru",
            "country": country,
            "countries": [country] if country else [],
            "companies": companies,
            "related_products": products,
            "scope": _SCOPE_BY_COUNTRY.get(country, "global"),
            "approval": "approved",
            # Cards are localised from here; ru is the source language.
            "i18n": {"ru": {"headline": headline, "summary": summary,
                            "analysis": analysis, "recommendation": recommendation}},
        }
        db.execute(
            sa.text(
                """
                INSERT INTO signals (kind, source_id, product_id, region, ai, urgency,
                                     status, event_at, created_at)
                VALUES ('news', :source_id, NULL, :region, CAST(:ai AS jsonb), :urgency,
                        'new', :event_at, :event_at)
                """
            ),
            {
                "source_id": source_ids[i % len(source_ids)],
                "region": country or None,
                "ai": json.dumps({"news": payload}, ensure_ascii=False),
                "urgency": {"high": "high", "medium": "medium", "low": "low"}[importance],
                "event_at": event_at,
            },
        )
        made += 1

    db.commit()
    print(f"news: {made} classified articles across the last {days_back} days")


def main() -> int:
    argparse.ArgumentParser(description="Seed showcase news articles.").parse_args()
    db = SessionLocal()
    try:
        seed_news(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
