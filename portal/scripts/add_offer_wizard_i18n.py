"""One-shot: insert the `offerWizard` tree into every locale, right after `offers`.

Written as a script rather than three hand-edits so the three files cannot drift
in key SHAPE — a missing key is a runtime error in this app, and the eye is bad
at diffing 140 keys across three JSONs.
"""

from __future__ import annotations

import collections
import json
import pathlib

LOCALES = pathlib.Path(__file__).resolve().parent.parent / "src/shared/i18n/locales"

CITIES = [
    "Ташкент",
    "Ташкентская область",
    "Самарканд",
    "Бухара",
    "Наманган",
    "Андижан",
    "Фергана",
    "Навои",
    "Карши",
    "Термез",
    "Нукус",
    "Ургенч",
    "Джизак",
    "Гулистан",
]

CITY_UZ = [
    "Toshkent",
    "Toshkent viloyati",
    "Samarqand",
    "Buxoro",
    "Namangan",
    "Andijon",
    "Farg‘ona",
    "Navoiy",
    "Qarshi",
    "Termiz",
    "Nukus",
    "Urganch",
    "Jizzax",
    "Guliston",
]

CITY_EN = [
    "Tashkent",
    "Tashkent Region",
    "Samarkand",
    "Bukhara",
    "Namangan",
    "Andijan",
    "Fergana",
    "Navoi",
    "Karshi",
    "Termez",
    "Nukus",
    "Urgench",
    "Jizzakh",
    "Gulistan",
]

RU = {
    "title": "Добавление товара: химическая продукция",
    "editTitle": "Редактирование товара",
    "subtitle": "Безопасная и профессиональная торговля химическим сырьём в Узбекистане и за рубежом",
    "stepOf": "Шаг {{current}} из {{total}}",
    "steps": {
        "basics": "Информация",
        "ai": "AI проверка",
        "availability": "Наличие / Под заказ",
        "documents": "Документы",
        "lab": "Лабораторные данные",
        "terms": "Условия продажи",
        "publish": "Публикация",
    },
    "trust": {
        "safe": "Безопасно",
        "legal": "Легально",
        "professional": "Профессионально",
        "international": "Международный стандарт",
    },
    "assurance": {
        "deals": {
            "title": "Безопасные сделки",
            "body": "Escrow, проверенные компании, юридическая защита",
        },
        "trade": {
            "title": "Легальная торговля",
            "body": "Проверка по реестрам РУз, контроль опасных веществ",
        },
        "lab": {
            "title": "Лабораторное сопровождение",
            "body": "Помощь в получении паспорта качества через IMEX AI",
        },
        "b2b": {
            "title": "Профессиональный B2B",
            "body": "Запросы RFQ, D-Doc, контракты, образцы",
        },
        "global": {
            "title": "Выход на международные рынки",
            "body": "Единые стандарты качества и доверия",
        },
    },
    "basics": {
        "title": "Основная информация",
        "heading": "Добавить товар",
        "productName": "Название товара",
        "productPlaceholder": "Выберите товар",
        "productOther": "Другое (ввести вручную)",
        "productRequired": "Выберите товар",
        "productManual": "Название товара вручную",
        "productManualPlaceholder": "Например, PP H030 GP",
        "productManualRequired": "Укажите название товара",
        "grade": "Марка",
        "gradePlaceholder": "Например, H030 GP",
        "cas": "CAS Number (если есть)",
        "hs": "HS Code (если есть)",
        "manufacturer": "Производитель",
        "manufacturerPlaceholder": "Например, Sibur",
        "originCountry": "Страна происхождения",
        "category": "Категория",
        "categoryUnset": "Не указана",
        "photos": "Фото товара",
        "catalogUnavailable": "Каталог недоступен",
        "catalogUnavailableBody": "Выберите «Другое» и введите название товара вручную.",
    },
    "ai": {
        "title": "AI проверка товара",
        "running": "AI анализирует товар…",
        "finished": "Анализ завершён",
        "rows": {
            "substance": "Определяем химическое вещество",
            "cas": "Проверяем CAS Number",
            "hs": "Проверяем HS Code",
            "dangerList": "Проверяем перечень опасных веществ РУз",
            "circulation": "Проверяем требования к обороту",
            "done": "Анализ завершён",
        },
        "clearTitle": "Товар не регулируется",
        "clearBody": "Данный товар не входит в перечень регулируемых или опасных химических веществ Республики Узбекистан.",
        "regulated": {
            "free": "Оборот не ограничен.",
            "docs_required": "Для публикации потребуются документы на вещество.",
            "license_required": "Для публикации потребуется действующая лицензия компании.",
            "prohibited": "Оборот этого вещества запрещён — опубликовать товар нельзя.",
        },
        "unknownTitle": "Вещество не определено",
        "unknownBody": "Мы не нашли вещество в реестре. Проверка ограничений не выполнена — укажите CAS и HS Code как можно точнее.",
    },
    "availability": {
        "title": "Наличие / Под заказ",
        "kind": "Тип предложения",
        "inStockHint": "Товар есть на складе",
        "onOrderHint": "Производство по требованию",
        "inStockNote": "Товар доступен для немедленной отгрузки",
        "onOrderNote": "Цена и объём согласуются по запросу — укажите срок производства",
        "qty": "Количество в наличии",
        "qtyRequired": "Укажите количество",
        "price": "Цена (за единицу)",
        "priceRequired": "Укажите цену",
        "warehouse": "Склад / Местоположение",
        "warehouseManual": "Укажите местоположение",
        "warehouseRequired": "Укажите местоположение",
        "cityOther": "Другое",
        "cities": dict(zip(CITIES, CITIES, strict=True)),
        "dispatch": {
            "label": "Срок отгрузки",
            "1-2": "1–2 дня",
            "3-7": "3–7 дней",
            "7-14": "7–14 дней",
            "14-30": "14–30 дней",
            "30-60": "30–60 дней",
        },
    },
    "documents": {
        "title": "Документы",
        "heading": "Обязательные документы",
        "kinds": {
            "sds": "SDS (Safety Data Sheet)",
            "tds": "TDS (Technical Data Sheet)",
            "coa": "Certificate of Analysis (если есть)",
        },
        "short": {"sds": "SDS", "tds": "TDS", "coa": "COA"},
        "pick": "Выбрать файл",
        "attached": "Документ прикреплён",
        "dropLabel": "Перетащите файлы или нажмите для загрузки",
        "dropHint": "PDF, JPG, PNG (до {{mb}} MB)",
        "trustNote": "Наличие документов повышает доверие покупателей",
        "missingTitle": "Не хватает обязательных документов",
        "tooLarge": "Файл слишком большой — до {{mb}} МБ.",
        "allSlotsFull": "Все три слота уже заполнены.",
    },
    "lab": {
        "title": "Лабораторные данные",
        "heading": "Лабораторный паспорт",
        "headingHint": "Паспорт качества подтверждает характеристики материала",
        "hasPassport": "У меня есть паспорт",
        "noPassport": "Нет паспорта",
        "passportLabel": "Загруженный паспорт качества (COA)",
        "passportRequired": "Прикрепите паспорт или выберите «Нет паспорта»",
        "offerIntro": "При необходимости мы можем получить лабораторную сертификацию через IMEX AI",
        "offerWeWill": "Мы свяжемся с вами и поможем:",
        "points": {
            "accredited": "подобрать аккредитованную лабораторию",
            "cost": "согласовать стоимость и сроки",
            "testing": "организовать проведение испытаний",
            "passport": "получить официальный паспорт качества",
        },
        "requestCta": "Запросить лабораторную сертификацию",
    },
    "terms": {
        "title": "Условия продажи",
        "samplesHint": "Образцы помогают покупателю принять решение быстрее",
        "samplesYes": "Доступны",
        "samplesNo": "Не предоставляются",
        "sampleFee": "Условия предоставления образцов",
        "fee": {"free": "Бесплатно", "paid": "Платно"},
        "samplePriceRequired": "Укажите стоимость образца",
        "sampleDispatch": "Срок отправки",
        "sampleBands": {"1-3": "1–3 дня", "3-7": "3–7 дней", "7-14": "7–14 дней"},
        "acceptsRfq": "Принимаю запросы RFQ",
        "acceptsContract": "Готов подписать договор через D-Doc",
        "acceptsEscrow": "Принимаю Escrow-платежи",
    },
    "extra": {
        "title": "Дополнительная информация",
        "description": "Описание товара",
        "descriptionPlaceholder": "Опишите материал, его свойства и применение",
        "keyProperties": "Ключевые свойства",
        "keyPropertiesPlaceholder": "Например, MFI: 3.0 г/10мин",
        "applications": "Применение",
        "applicationsPlaceholder": "Например, литьё под давлением",
    },
    "preview": {
        "title": "Предварительный просмотр",
        "noPhoto": "Фото не добавлено",
        "country": "Страна",
        "qty": "Количество",
        "onRequest": "По запросу",
        "samplesAvailable": "Образцы доступны",
        "dDoc": "D-Doc",
        "escrow": "Escrow",
        "publish": "Опубликовать товар",
        "publishing": "Публикация…",
        "uploading": "Загрузка файлов {{done}} / {{total}}",
    },
    "done": {
        "title": "Товар опубликован!",
        "bodyLive": "Ваш товар размещён на платформе IMEX AI и доступен покупателям.",
        "bodyModeration": "Ваш товар отправлен на модерацию. Как только его проверят, он появится в маркете IMEX AI.",
        "idLabel": "ID объявления",
        "copyId": "Скопировать ID",
        "toOffers": "Перейти к моим товарам",
        "createAnother": "Создать ещё один товар",
    },
}

UZ = {
    "title": "Tovar qo‘shish: kimyoviy mahsulot",
    "editTitle": "Tovarni tahrirlash",
    "subtitle": "O‘zbekistonda va chet elda kimyoviy xomashyo bilan xavfsiz va professional savdo",
    "stepOf": "{{total}} dan {{current}}-qadam",
    "steps": {
        "basics": "Ma’lumot",
        "ai": "AI tekshiruvi",
        "availability": "Mavjud / Buyurtma asosida",
        "documents": "Hujjatlar",
        "lab": "Laboratoriya ma’lumotlari",
        "terms": "Sotuv shartlari",
        "publish": "E’lon qilish",
    },
    "trust": {
        "safe": "Xavfsiz",
        "legal": "Qonuniy",
        "professional": "Professional",
        "international": "Xalqaro standart",
    },
    "assurance": {
        "deals": {
            "title": "Xavfsiz bitimlar",
            "body": "Escrow, tekshirilgan kompaniyalar, huquqiy himoya",
        },
        "trade": {
            "title": "Qonuniy savdo",
            "body": "O‘zbekiston reyestrlari bo‘yicha tekshiruv, xavfli moddalar nazorati",
        },
        "lab": {
            "title": "Laboratoriya yordami",
            "body": "IMEX AI orqali sifat pasportini olishda ko‘maklashamiz",
        },
        "b2b": {
            "title": "Professional B2B",
            "body": "RFQ so‘rovlari, D-Doc, shartnomalar, namunalar",
        },
        "global": {
            "title": "Xalqaro bozorlarga chiqish",
            "body": "Yagona sifat va ishonch standartlari",
        },
    },
    "basics": {
        "title": "Asosiy ma’lumot",
        "heading": "Tovar qo‘shish",
        "productName": "Tovar nomi",
        "productPlaceholder": "Tovarni tanlang",
        "productOther": "Boshqa (qo‘lda kiritish)",
        "productRequired": "Tovarni tanlang",
        "productManual": "Tovar nomini qo‘lda kiriting",
        "productManualPlaceholder": "Masalan, PP H030 GP",
        "productManualRequired": "Tovar nomini kiriting",
        "grade": "Marka",
        "gradePlaceholder": "Masalan, H030 GP",
        "cas": "CAS Number (agar bo‘lsa)",
        "hs": "HS Code (agar bo‘lsa)",
        "manufacturer": "Ishlab chiqaruvchi",
        "manufacturerPlaceholder": "Masalan, Sibur",
        "originCountry": "Kelib chiqish mamlakati",
        "category": "Kategoriya",
        "categoryUnset": "Ko‘rsatilmagan",
        "photos": "Tovar rasmlari",
        "catalogUnavailable": "Katalog mavjud emas",
        "catalogUnavailableBody": "«Boshqa»ni tanlang va tovar nomini qo‘lda kiriting.",
    },
    "ai": {
        "title": "Tovarni AI tekshiruvi",
        "running": "AI tovarni tahlil qilmoqda…",
        "finished": "Tahlil yakunlandi",
        "rows": {
            "substance": "Kimyoviy moddani aniqlaymiz",
            "cas": "CAS Number tekshirilmoqda",
            "hs": "HS Code tekshirilmoqda",
            "dangerList": "O‘zbekiston xavfli moddalar ro‘yxati tekshirilmoqda",
            "circulation": "Muomala talablari tekshirilmoqda",
            "done": "Tahlil yakunlandi",
        },
        "clearTitle": "Tovar tartibga solinmaydi",
        "clearBody": "Ushbu tovar O‘zbekiston Respublikasining tartibga solinadigan yoki xavfli kimyoviy moddalar ro‘yxatiga kirmaydi.",
        "regulated": {
            "free": "Muomala cheklanmagan.",
            "docs_required": "E’lon qilish uchun moddaga oid hujjatlar talab qilinadi.",
            "license_required": "E’lon qilish uchun kompaniyaning amaldagi litsenziyasi talab qilinadi.",
            "prohibited": "Ushbu moddaning muomalasi taqiqlangan — tovarni e’lon qilib bo‘lmaydi.",
        },
        "unknownTitle": "Modda aniqlanmadi",
        "unknownBody": "Moddani reyestrdan topa olmadik. Cheklovlar tekshirilmadi — CAS va HS Code’ni imkon qadar aniq ko‘rsating.",
    },
    "availability": {
        "title": "Mavjud / Buyurtma asosida",
        "kind": "Taklif turi",
        "inStockHint": "Tovar omborda mavjud",
        "onOrderHint": "Talab bo‘yicha ishlab chiqarish",
        "inStockNote": "Tovar darhol jo‘natishga tayyor",
        "onOrderNote": "Narx va hajm so‘rov bo‘yicha kelishiladi — ishlab chiqarish muddatini ko‘rsating",
        "qty": "Mavjud miqdor",
        "qtyRequired": "Miqdorni kiriting",
        "price": "Narx (birlik uchun)",
        "priceRequired": "Narxni kiriting",
        "warehouse": "Ombor / Joylashuv",
        "warehouseManual": "Joylashuvni kiriting",
        "warehouseRequired": "Joylashuvni kiriting",
        "cityOther": "Boshqa",
        "cities": dict(zip(CITIES, CITY_UZ, strict=True)),
        "dispatch": {
            "label": "Jo‘natish muddati",
            "1-2": "1–2 kun",
            "3-7": "3–7 kun",
            "7-14": "7–14 kun",
            "14-30": "14–30 kun",
            "30-60": "30–60 kun",
        },
    },
    "documents": {
        "title": "Hujjatlar",
        "heading": "Majburiy hujjatlar",
        "kinds": {
            "sds": "SDS (Safety Data Sheet)",
            "tds": "TDS (Technical Data Sheet)",
            "coa": "Certificate of Analysis (agar bo‘lsa)",
        },
        "short": {"sds": "SDS", "tds": "TDS", "coa": "COA"},
        "pick": "Faylni tanlash",
        "attached": "Hujjat biriktirildi",
        "dropLabel": "Fayllarni tashlang yoki yuklash uchun bosing",
        "dropHint": "PDF, JPG, PNG ({{mb}} MB gacha)",
        "trustNote": "Hujjatlarning mavjudligi xaridorlar ishonchini oshiradi",
        "missingTitle": "Majburiy hujjatlar yetishmayapti",
        "tooLarge": "Fayl juda katta — {{mb}} MB gacha.",
        "allSlotsFull": "Uchala slot ham to‘ldirilgan.",
    },
    "lab": {
        "title": "Laboratoriya ma’lumotlari",
        "heading": "Laboratoriya pasporti",
        "headingHint": "Sifat pasporti material tavsiflarini tasdiqlaydi",
        "hasPassport": "Menda pasport bor",
        "noPassport": "Pasport yo‘q",
        "passportLabel": "Yuklangan sifat pasporti (COA)",
        "passportRequired": "Pasportni biriktiring yoki «Pasport yo‘q»ni tanlang",
        "offerIntro": "Zarur bo‘lsa, IMEX AI orqali laboratoriya sertifikatini olishimiz mumkin",
        "offerWeWill": "Biz siz bilan bog‘lanamiz va yordam beramiz:",
        "points": {
            "accredited": "akkreditatsiyalangan laboratoriyani tanlash",
            "cost": "narx va muddatlarni kelishish",
            "testing": "sinovlarni tashkil etish",
            "passport": "rasmiy sifat pasportini olish",
        },
        "requestCta": "Laboratoriya sertifikatini so‘rash",
    },
    "terms": {
        "title": "Sotuv shartlari",
        "samplesHint": "Namunalar xaridorga tezroq qaror qabul qilishga yordam beradi",
        "samplesYes": "Mavjud",
        "samplesNo": "Taqdim etilmaydi",
        "sampleFee": "Namuna taqdim etish shartlari",
        "fee": {"free": "Bepul", "paid": "Pullik"},
        "samplePriceRequired": "Namuna narxini kiriting",
        "sampleDispatch": "Jo‘natish muddati",
        "sampleBands": {"1-3": "1–3 kun", "3-7": "3–7 kun", "7-14": "7–14 kun"},
        "acceptsRfq": "RFQ so‘rovlarini qabul qilaman",
        "acceptsContract": "D-Doc orqali shartnoma imzolashga tayyorman",
        "acceptsEscrow": "Escrow to‘lovlarini qabul qilaman",
    },
    "extra": {
        "title": "Qo‘shimcha ma’lumot",
        "description": "Tovar tavsifi",
        "descriptionPlaceholder": "Material, uning xossalari va qo‘llanilishini tavsiflang",
        "keyProperties": "Asosiy xossalar",
        "keyPropertiesPlaceholder": "Masalan, MFI: 3.0 g/10min",
        "applications": "Qo‘llanilishi",
        "applicationsPlaceholder": "Masalan, bosim ostida quyish",
    },
    "preview": {
        "title": "Dastlabki ko‘rinish",
        "noPhoto": "Rasm qo‘shilmagan",
        "country": "Mamlakat",
        "qty": "Miqdor",
        "onRequest": "So‘rov bo‘yicha",
        "samplesAvailable": "Namunalar mavjud",
        "dDoc": "D-Doc",
        "escrow": "Escrow",
        "publish": "Tovarni e’lon qilish",
        "publishing": "E’lon qilinmoqda…",
        "uploading": "Fayllar yuklanmoqda {{done}} / {{total}}",
    },
    "done": {
        "title": "Tovar e’lon qilindi!",
        "bodyLive": "Tovaringiz IMEX AI platformasida joylashtirildi va xaridorlarga ochiq.",
        "bodyModeration": "Tovaringiz moderatsiyaga yuborildi. Tekshiruvdan so‘ng u IMEX AI bozorida paydo bo‘ladi.",
        "idLabel": "E’lon ID’si",
        "copyId": "ID nusxasini olish",
        "toOffers": "Mening tovarlarimga o‘tish",
        "createAnother": "Yana bir tovar qo‘shish",
    },
}

EN = {
    "title": "Add a product: chemical goods",
    "editTitle": "Edit product",
    "subtitle": "Safe, professional trade in chemical feedstock in Uzbekistan and abroad",
    "stepOf": "Step {{current}} of {{total}}",
    "steps": {
        "basics": "Details",
        "ai": "AI check",
        "availability": "Stock / On order",
        "documents": "Documents",
        "lab": "Laboratory data",
        "terms": "Sales terms",
        "publish": "Publish",
    },
    "trust": {
        "safe": "Safe",
        "legal": "Legal",
        "professional": "Professional",
        "international": "International standard",
    },
    "assurance": {
        "deals": {
            "title": "Safe deals",
            "body": "Escrow, verified companies, legal protection",
        },
        "trade": {
            "title": "Legal trade",
            "body": "Checks against Uzbek registries, hazardous-substance control",
        },
        "lab": {
            "title": "Laboratory support",
            "body": "Help getting a quality passport through IMEX AI",
        },
        "b2b": {
            "title": "Professional B2B",
            "body": "RFQs, D-Doc, contracts, samples",
        },
        "global": {
            "title": "Reach international markets",
            "body": "One standard of quality and trust",
        },
    },
    "basics": {
        "title": "Basic information",
        "heading": "Add a product",
        "productName": "Product name",
        "productPlaceholder": "Choose a product",
        "productOther": "Other (type it in)",
        "productRequired": "Choose a product",
        "productManual": "Product name",
        "productManualPlaceholder": "e.g. PP H030 GP",
        "productManualRequired": "Enter the product name",
        "grade": "Grade",
        "gradePlaceholder": "e.g. H030 GP",
        "cas": "CAS Number (if any)",
        "hs": "HS Code (if any)",
        "manufacturer": "Manufacturer",
        "manufacturerPlaceholder": "e.g. Sibur",
        "originCountry": "Country of origin",
        "category": "Category",
        "categoryUnset": "Not specified",
        "photos": "Product photos",
        "catalogUnavailable": "Catalog unavailable",
        "catalogUnavailableBody": "Choose “Other” and type the product name in.",
    },
    "ai": {
        "title": "AI product check",
        "running": "AI is analysing the product…",
        "finished": "Analysis complete",
        "rows": {
            "substance": "Identifying the chemical substance",
            "cas": "Checking the CAS Number",
            "hs": "Checking the HS Code",
            "dangerList": "Checking the Uzbek hazardous-substance list",
            "circulation": "Checking circulation requirements",
            "done": "Analysis complete",
        },
        "clearTitle": "Product is not regulated",
        "clearBody": "This product is not on the Republic of Uzbekistan's list of regulated or hazardous chemical substances.",
        "regulated": {
            "free": "Circulation is unrestricted.",
            "docs_required": "Publishing will require documents for the substance.",
            "license_required": "Publishing will require a valid company licence.",
            "prohibited": "Circulation of this substance is prohibited — it cannot be published.",
        },
        "unknownTitle": "Substance not identified",
        "unknownBody": "We could not find the substance in the registry, so restrictions were not checked — give the CAS and HS Code as precisely as you can.",
    },
    "availability": {
        "title": "Stock / On order",
        "kind": "Offer type",
        "inStockHint": "Goods are in the warehouse",
        "onOrderHint": "Produced on demand",
        "inStockNote": "The goods are ready for immediate dispatch",
        "onOrderNote": "Price and volume are agreed on request — state the lead time",
        "qty": "Quantity in stock",
        "qtyRequired": "Enter the quantity",
        "price": "Price (per unit)",
        "priceRequired": "Enter the price",
        "warehouse": "Warehouse / Location",
        "warehouseManual": "Enter the location",
        "warehouseRequired": "Enter the location",
        "cityOther": "Other",
        "cities": dict(zip(CITIES, CITY_EN, strict=True)),
        "dispatch": {
            "label": "Dispatch time",
            "1-2": "1–2 days",
            "3-7": "3–7 days",
            "7-14": "7–14 days",
            "14-30": "14–30 days",
            "30-60": "30–60 days",
        },
    },
    "documents": {
        "title": "Documents",
        "heading": "Required documents",
        "kinds": {
            "sds": "SDS (Safety Data Sheet)",
            "tds": "TDS (Technical Data Sheet)",
            "coa": "Certificate of Analysis (if any)",
        },
        "short": {"sds": "SDS", "tds": "TDS", "coa": "COA"},
        "pick": "Choose a file",
        "attached": "Document attached",
        "dropLabel": "Drop files here, or click to upload",
        "dropHint": "PDF, JPG, PNG (up to {{mb}} MB)",
        "trustNote": "Documents make buyers trust the listing",
        "missingTitle": "Required documents are missing",
        "tooLarge": "File is too large — up to {{mb}} MB.",
        "allSlotsFull": "All three slots are already filled.",
    },
    "lab": {
        "title": "Laboratory data",
        "heading": "Laboratory passport",
        "headingHint": "A quality passport backs up what the material is",
        "hasPassport": "I have a passport",
        "noPassport": "No passport",
        "passportLabel": "Uploaded quality passport (COA)",
        "passportRequired": "Attach the passport, or choose “No passport”",
        "offerIntro": "If you need one, we can arrange laboratory certification through IMEX AI",
        "offerWeWill": "We will get in touch and help you:",
        "points": {
            "accredited": "pick an accredited laboratory",
            "cost": "agree the price and the timing",
            "testing": "arrange the testing",
            "passport": "obtain the official quality passport",
        },
        "requestCta": "Request laboratory certification",
    },
    "terms": {
        "title": "Sales terms",
        "samplesHint": "Samples help a buyer decide faster",
        "samplesYes": "Available",
        "samplesNo": "Not offered",
        "sampleFee": "Sample terms",
        "fee": {"free": "Free", "paid": "Paid"},
        "samplePriceRequired": "Enter the sample price",
        "sampleDispatch": "Dispatch time",
        "sampleBands": {"1-3": "1–3 days", "3-7": "3–7 days", "7-14": "7–14 days"},
        "acceptsRfq": "I accept RFQs",
        "acceptsContract": "Ready to sign a contract through D-Doc",
        "acceptsEscrow": "I accept escrow payments",
    },
    "extra": {
        "title": "Additional information",
        "description": "Product description",
        "descriptionPlaceholder": "Describe the material, its properties and its uses",
        "keyProperties": "Key properties",
        "keyPropertiesPlaceholder": "e.g. MFI: 3.0 g/10min",
        "applications": "Applications",
        "applicationsPlaceholder": "e.g. injection moulding",
    },
    "preview": {
        "title": "Preview",
        "noPhoto": "No photo added",
        "country": "Country",
        "qty": "Quantity",
        "onRequest": "On request",
        "samplesAvailable": "Samples available",
        "dDoc": "D-Doc",
        "escrow": "Escrow",
        "publish": "Publish product",
        "publishing": "Publishing…",
        "uploading": "Uploading files {{done}} / {{total}}",
    },
    "done": {
        "title": "Product published!",
        "bodyLive": "Your product is live on IMEX AI and visible to buyers.",
        "bodyModeration": "Your product went to moderation. Once it is reviewed it will appear on the IMEX AI market.",
        "idLabel": "Listing ID",
        "copyId": "Copy the ID",
        "toOffers": "Go to my products",
        "createAnother": "Add another product",
    },
}


def shape(tree: object, prefix: str = "") -> set[str]:
    """Every leaf path — what the three locales must agree on."""
    if not isinstance(tree, dict):
        return {prefix}
    return {p for key, value in tree.items() for p in shape(value, f"{prefix}.{key}")}


def main() -> None:
    trees = {"ru": RU, "uz": UZ, "en": EN}

    shapes = {lang: shape(tree) for lang, tree in trees.items()}
    if len({frozenset(s) for s in shapes.values()}) != 1:
        base = shapes["ru"]
        for lang, keys in shapes.items():
            missing = base - keys
            extra = keys - base
            if missing or extra:
                raise SystemExit(f"{lang}: missing={sorted(missing)} extra={sorted(extra)}")

    for lang, tree in trees.items():
        path = LOCALES / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=collections.OrderedDict)
        if "offerWizard" in data:
            data["offerWizard"] = tree
            merged = data
        else:
            merged = collections.OrderedDict()
            for key, value in data.items():
                merged[key] = value
                if key == "offers":
                    merged["offerWizard"] = tree
            if "offerWizard" not in merged:
                merged["offerWizard"] = tree
        path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{lang}: offerWizard written ({len(shape(tree))} keys)")


if __name__ == "__main__":
    main()
