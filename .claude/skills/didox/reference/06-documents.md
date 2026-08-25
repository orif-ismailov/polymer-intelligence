# 06. Документы

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-documents>
> Source last updated: 2026-08-19T06:26:59.239Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена нкобходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

# Документы

Методы для получения, создания, подписания, отклонения и удаления документов.

> **Аутентификация.** Все методы раздела требуют двух заголовков:
```
Partner-Authorization: <PARTNER_TOKEN>
user-key: <USER_TOKEN>
```

* Чтение
* Создание и редактирование
* Подписание и статусы
* ТТН — ответственное лицо
* Справочные данные

\# | Метод | Эндпоинт | Назначение  
---|---|---|---  
1 | `GET` | `/v2/documents` | Список документов  
2 | `GET` | `/v2/documents/statistics/all` | Счётчики документов  
3 | `GET` | `/v1/documents/{id}` | Подробная информация о документе  
4 | `GET` | `/v1/documents/{id}/privileges/{locale}` | Список льгот в документе  
16 | `GET` | `/v1/documents/view/{id}/html\|pdf/{locale}` | Печатная форма  
17 | `GET` | `/v1/documents/{id}/archive` | Архив с документом  
22 | `GET` | `/v2/documents?status=60` | Список ЭСФ на доверенные лица  
  
\# | Метод | Эндпоинт | Назначение  
---|---|---|---  
5 | `POST` | `/v1/documents/{docType}/create/{locale}` | Создание документа (черновик)  
6 | `POST` | `/v1/documents/{id}/update/{docType}` | Обновление черновика  
7 | `POST` | `/v1/documents/{id}/delete/draft` | Удаление черновика  
  
\# | Метод | Эндпоинт | Назначение  
---|---|---|---  
8 | `POST` | `/v1/documents/{id}/tosign` | Получение данных для подписания  
9 | `POST` | `/v1/documents/{id}/sign` | Подписание исходящего документа  
10 | `POST` | `/v1/documents/{id}/sign` | Подписание входящего документа  
11 | `POST` | `/v1/documents/{id}/reject` | Отклонение (отказ) документа  
12 | `POST` | `/v1/documents/{id}/delete` | Удаление (отмена) документа  
  
\# | Метод | Эндпоинт | Назначение  
---|---|---|---  
13 | `POST` | `/v1/documents/{id}/give` | Подтверждение доставки  
14 | `POST` | `/v1/documents/{id}/tillreturn` | Возврат на этапе принятого ТТН  
15 | `POST` | `/v1/documents/{id}/return` | Возврат доставленного товара  
  
\# | Метод | Эндпоинт | Назначение  
---|---|---|---  
18 | `GET` | `/v1/documents/contract/{contractId}/info/{locale}` | Данные по договору для СФ  
19 | `GET` | `/v1/documents/exchange` | Информация о лоте  
20 | `GET` | `/v1/documents/exchange/types` | Типы сделки по лоту  
21 | `GET` | `/v1/documents/exchange/lotswithtypes/{locale}` | Префикс типа сделки  
  
* * *

# 1. Список документов

GET   `/v2/documents`

Возвращает список документов с постраничной разбивкой.

> **Обязательно передайте`page` и `limit`.**

**Query-параметры**

Параметр | Значение | Обяз. | Описание  
---|---|---|---  
`page` | `1-∞` | ✅ | Номер страницы  
`limit` | `1-100` | ✅ | Количество документов на странице (по умолчанию 20)  
`owner` | `1` / `0` | ⬜ | `1` — исходящие, `0` — входящие. Без параметра возвращаются исходящие  
`status` | код статуса | ⬜ | [Список статусов](https://api-docs.didox.uz/ru/integrators-catalogs#h-6-%D1%81%D1%82%D0%B0%D1%82%D1%83%D1%81%D1%8B-%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82%D0%BE%D0%B2). Можно указать несколько через запятую  
`doctype` | код типа | ⬜ | [Тип документа](https://api-docs.didox.uz/ru/integrators-property-documents)  
`partner` | ИНН | ⬜ | Фильтр по контрагенту  
`name` | номер | ⬜ | Номер документа  
`sum` | `1-∞` | ⬜ | Сумма документа  
`dateFromCreated` | `yyyy-mm-dd` | ⬜ | Дата создания документа, с  
`dateToCreated` | `yyyy-mm-dd` | ⬜ | Дата создания документа, по  
`dateFromUpdated` | `yyyy-mm-dd` | ⬜ | Дата обновления документа, с  
`dateToUpdated` | `yyyy-mm-dd` | ⬜ | Дата обновления документа, по  
`signDateFrom` | `yyyy-mm-dd` | ⬜ | Дата отправки документа в Didox, с  
`signDateTo` | `yyyy-mm-dd` | ⬜ | Дата отправки документа в Didox, по  
`docDateFromCreated` | `yyyy-mm-dd` | ⬜ | Дата документа, с  
`docDateToCreated` | `yyyy-mm-dd` | ⬜ | Дата документа, по  
`contractName` | номер | ⬜ | Номер договора  
`contractDate` | `yyyy-mm-dd` | ⬜ | Дата договора  
`hasCommittent` | `1` / `0` | ⬜ | Комиссионерский документ  
`hasLgota` | `1` / `0` | ⬜ | Документ с льготой  
`hasMarks` | `1` / `0` | ⬜ | Документ с маркировкой  
`oneside` | `1` / `0` | ⬜ | Односторонний документ  
  
> Если `status` не указан, возвращаются документы со статусами: Ожидают подписи партнера (1), Ожидает вашей подписи (2), Подписан (3), Отказ от подписи (4), Ожидают подписи агента (6), Подписан агентом (8), Недействительный (40).

* Постранично
* По статусу
* Входящие / исходящие
* По дате обновления
* По контрагенту
```http
GET /v2/documents?page=1&limit=5
GET /v2/documents?page=1&limit=10
```
```http
GET /v2/documents?status=1
GET /v2/documents?status=0,2
```
```http
GET /v2/documents?owner=1   # исходящие
GET /v2/documents?owner=0   # входящие
```
```http
GET /v2/documents?dateFromUpdated=2025-01-01
GET /v2/documents?dateToUpdated=2025-02-01
GET /v2/documents?dateFromUpdated=2025-01-01&dateToUpdated=2025-02-01
```
```http
GET /v2/documents?partner=303186914
```

* Ответ `200`
```json
{
    "data": [
        {
            "pid": 35673450,
            "doc_id": "11EFBD20AB80D1B080B2C6808E0C7050",
            "usersTaxId": "207119963",
            "name": "70",
            "doc_date": "2024-12-18",
            "doc_status": 1,
            "doctype": "002",
            "contract_number": "1",
            "contract_date": "2024-11-29",
            "owner": 1,
            "agent": 0,
            "partnerTin": "302936161",
            "partnerAllowProposals": 1,
            "partnerCompany": "\"VENKON GROUP\" MCHJ",
            "partnerPhone": "111111111111",
            "total_sum": 250,
            "total_delivery_sum": 3950,
            "total_vat_sum": 474,
            "total_delivery_sum_with_vat": 4424,
            "oneside": 0,
            "has_committent": 0,
            "has_vat": true,
            "has_lgota": 0,
            "has_marks": 0,
            "roaming_id": "676292c40b3f6b873039e5ec",
            "signed": "2024-12-18",
            "updated": "2024-12-18",
            "updated_date": "2024-12-18T09:15:59",
            "updated_unix": 1734513359,
            "created": "2024-12-18",
            "created_unix": 1734513348,
            "partiesID": "11EFBD20ABA750888555C6808E0C7050",
            "lgota_codes": "",
            "factura_type": 0,
            "sellerAccount": "20208000204919341001",
            "status_comment": null,
            "internal_status": null,
            "internal_comment": null,
            "internal_status_alarm": null,
            "mark_codes": null,
            "branch_num": null,
            "scoring": null
        }
    ],
    "total": 1,
    "next_page_url": null,
    "source": "search"
}
```

* * *

# 2. Счётчики документов

GET   `/v2/documents/statistics/all`

Возвращает количество документов по каждому статусу. Поддерживает те же фильтры, что и метод «Список документов».

Ключ в ответе — код статуса, значение — количество документов.

* cURL
* Ответ `200`
```bash
curl "https://api-partners.didox.uz/v2/documents/statistics/all?owner=1" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
  "1": 90,
  "3": 90
}
```

* * *

# 3. Подробная информация о документе

GET   `/v1/documents/{id}`

Возвращает полную информацию о документе: содержимое (`json`), метаданные (`document`), данные для подписания (`toSign`) и связанные документы.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`id` | ✅ | ID документа (32 символа)  
  
**Query-параметры**

Параметр | Значение | Обяз. | Описание  
---|---|---|---  
`owner` | `1` / `0` | ⬜ | `1` — как исходящий, `0` — как входящий  
  
**Ключевые поля ответа**

Поле | Описание  
---|---  
`data.json` | Содержимое документа  
`data.document` | Метаданные: статус, даты, подписи  
`data.toSign` | Данные для подписания  
`data.relatedDocuments` | Связанные документы  
  
* cURL
* Ответ `200`
```bash
curl "https://api-partners.didox.uz/v1/documents/11F092E3428D10C68F7B1E0008000075?owner=1" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "data": {
        "json": {
            "version": 1,
            "facturatype": "0",
            "facturaid": "68c933ffc446a09bba747505",
            "facturadoc": {
                "facturano": "Тест",
                "facturadate": "2025-09-08"
            },
            "contractdoc": {
                "contractno": "Тест",
                "contractdate": "2025-09-18"
            },
            "contractid": null,
            "facturaempowermentdoc": {
                "agentfacturaid": "68c9340a9523502f92de5a2d",
                "empowermentno": "",
                "empowermentdateofissue": "",
                "agentfio": ""
            },
            "itemreleaseddoc": {
                "itemreleasedfio": "",
                "itemreleasedpinfl": ""
            },
            "sellertin": "310529901",
            "buyertin": "302936161",
            "seller": {
                "name": "\"DIDOX TECH\" MCHJ",
                "branchcode": "",
                "branchname": "",
                "account": "20208000905656222001",
                "bankid": "00401",
                "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй  ",
                "mobile": null,
                "workphone": "",
                "oked": "62090",
                "districtid": "",
                "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
                "accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
                "vatregcode": "326080220838",
                "vatregstatus": 20,
                "taxgap": null
            },
            "buyer": {
                "name": "\"VENKON GROUP\" MCHJ",
                "branchcode": "",
                "branchname": "",
                "account": "20208000400308125001",
                "bankid": "00974",
                "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси,  ",
                "mobile": "",
                "workphone": "",
                "oked": "62010",
                "districtid": "",
                "director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
                "accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
                "vatregcode": "326040002521",
                "vatregstatus": 20,
                "taxgap": null
            },
            "productlist": {
                "facturaproductid": "68c9340a6a52131e969eb3c1",
                "tin": "310529901",
                "hasexcise": false,
                "hasvat": true,
                "hasmedical": false,
                "hascommittent": false,
                "haslgota": false,
                "products": [
                    {
                        "packagecode": 1505731,
                        "packagename": "кубический метр",
                        "ordno": "1",
                        "committentname": "",
                        "committenttin": "",
                        "committentvatregcode": "",
                        "committentvatregstatus": null,
                        "name": "тест",
                        "barcode": "",
                        "lgotaid": null,
                        "catalogcode": "10713007001000000",
                        "catalogname": "Возмещение затрат (расходов) за услуги холодного водоснабжения",
                        "measureid": "",
                        "count": "1",
                        "summa": "1",
                        "deliverysum": 1,
                        "vatrate": 12,
                        "vatsum": "0.12",
                        "deliverysumwithvat": "1.12",
                        "withoutvat": false,
                        "exciserate": "0",
                        "excisesum": "0",
                        "serial": "",
                        "basesumma": 0,
                        "profitrate": 0,
                        "warehouseid": null,
                        "origin": 3,
                        "marks": null,
                        "lgotaname": null,
                        "lgotavatsum": 0,
                        "lgotatype": null
                    }
                ]
            },
            "hasrent": false,
            "facturarentdoc": null
        },
        "document": {
            "doc_id": "11F092E3428D10C68F7B1E0008000075",
            "_id": "11F092E3428D10C68F7B1E0008000075",
            "id": "11F092E3428D10C68F7B1E0008000075",
            "name": "Тест СФ",
            "internal_status": null,
            "updated": "2025-09-16 14:56:23",
            "created": "2025-09-16 14:55:22",
            "doctype": "002",
            "factura_type": 0,
            "reverse_calc": false,
            "authorTaxId": null,
            "signature": "[{\"taxId\":\"310529901\",\"firstName\":\"BEHRUZJON\",\"lastName\":\"MAXMUDOV\",\"fullName\":\"MAXMUDOV BEHRUZJON RAVSHAN O\\u2018G\\u2018LI\",\"company\":\"DIDOX TECH MCHJ\",\"email\":\"\",\"serial\":\"78d0f645\",\"serialDec\":2026960453,\"signingTime\":\"2025.09.16 14:55:23\",\"pinfl\":null,\"operator\":\"didox.uz\",\"ip\":\"217.30.173.63\"}]",
            "sourceId": null,
            "additional": [],
            "extended_json": null,
            "status_comment": "Документ отменен",
            "status": 3,
            "doc_status": 3,
            "owner": 1,
            "internal_comment": null,
            "has_copy_restriction": false,
            "has_cancel_restriction": null,
            "factoringBlocks": [],
            "scoring": 0
        },
        "toSign": null,
        "isValid": true,
        "relatedDocuments": [],
        "requestToByResponse": null
    }
}
```

* * *

# 4. Список льгот в документе

GET   `/v1/documents/{id}/privileges/{locale}`

Возвращает информацию о льготах, применённых в документе.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`id` | ✅ | ID документа  
`locale` | ⬜ | Язык результата: `ru` или `uz`  
  
* cURL
* Ответ `200`
```bash
curl https://api-partners.didox.uz/v1/documents/{id}/privileges/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
[
    {
        "lgota_code": "102387",
        "lgota_name": "УП-5099 от 30.06.2017 г пункт 5 абзац 2 Освободить сроком до 1 января 2028 года резидентов Инновационного центра от уплаты всех видов налогов и обязательных отчислений в государсвенные целевые фонды, а текже единого социального платежа.",
        "product_name": "asd"
    }
]
```

* * *

# 5. Создание нового документа

POST   `/v1/documents/{docType}/create/{locale}`

Создаёт документ в черновиках. Структура тела запроса зависит от типа документа — см. ссылки в таблице ниже.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`docType` | ✅ | Код типа документа (см. таблицу)  
`locale` | ⬜ | Язык: `ru` или `uz`  
  
**Поддерживаемые типы документов**

Код | Тип документа  
---|---  
`002` | [Счёт-фактура без акта](https://api-docs.didox.uz/ru/integrators-property-documents#%D1%81%D1%87%D1%91%D1%82-%D1%84%D0%B0%D0%BA%D1%82%D1%83%D1%80%D0%B0)  
`008` | [Счёт-фактура (ФАРМ)](https://api-docs.didox.uz/ru/integrators-property-documents#h-2-%D1%81%D1%87%D0%B5%D1%82-%D1%84%D0%B0%D0%BA%D1%82%D1%83%D1%80%D0%B0-%D1%84%D0%B0%D1%80%D0%BC)  
`023` | [Гибридная счёт-фактура](https://api-docs.didox.uz/ru/integrators-property-documents#%D0%93%D0%B8%D0%B1%D1%80%D0%B8%D0%B4%D0%BD%D0%B0%D1%8F%D1%81%D1%87%D0%B5%D1%82-%D1%84%D0%B0%D0%BA%D1%82%D1%83%D1%80%D0%B0)  
`041` | [ТТН (товарно-транспортная накладная)](https://api-docs.didox.uz/ru/integrators-property-documents#h-3-%D1%82%D1%82%D0%BD-%D1%82%D0%BE%D0%B2%D0%B0%D1%80%D0%BD%D0%BE-%D1%82%D1%80%D0%B0%D0%BD%D1%81%D0%BF%D0%BE%D1%80%D1%82%D0%BD%D0%B0%D1%8F-%D0%BD%D0%B0%D0%BA%D0%BB%D0%B0%D0%B4%D0%BD%D0%B0%D1%8F)  
`005` | [Акт выполненных работ](https://api-docs.didox.uz/ru/integrators-property-documents#h-4-%D0%B0%D0%BA%D1%82)  
`006` | [Доверенность](https://api-docs.didox.uz/ru/integrators-property-documents#h-5-%D0%B4%D0%BE%D0%B2%D0%B5%D1%80%D0%B5%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D1%8C)  
`062` | [Доверенность (новая)](https://api-docs.didox.uz/ru/integrators-property-documents#h-16-%D0%B4%D0%BE%D0%B2%D0%B5%D1%80%D0%B5%D0%BD%D0%BD%D0%BE%D1%81%D1%82%D1%8C-%D0%BD%D0%BE%D0%B2%D0%B0%D1%8F)  
`007` | [Договор (ГНК)](https://api-docs.didox.uz/ru/integrators-property-documents#h-6-%D0%B4%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80-%D0%B3%D0%BD%D0%BA)  
`000` | [Произвольный документ](https://api-docs.didox.uz/ru/integrators-property-documents#h-6-%D0%BF%D1%80%D0%BE%D0%B8%D0%B7%D0%B2%D0%BE%D0%BB%D1%8C%D0%BD%D1%8B%D0%B9-%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82)  
`010` | [Многосторонний произвольный документ](https://api-docs.didox.uz/ru/integrators-property-documents#h-10-%D0%BC%D0%BD%D0%BE%D0%B3%D0%BE%D1%81%D1%82%D0%BE%D1%80%D0%BE%D0%BD%D0%BD%D0%B8%D0%B9-%D0%BF%D1%80%D0%BE%D0%B8%D0%B7%D0%B2%D0%BE%D0%BB%D1%8C%D0%BD%D1%8B%D0%B9-%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82)  
`052` | [Акт сверки](https://api-docs.didox.uz/ru/integrators-property-documents#h-8-%D0%B0%D0%BA%D1%82-%D1%81%D0%B2%D0%B5%D1%80%D0%BA%D0%B8)  
`054` | [Акт приёма-передачи](https://api-docs.didox.uz/ru/integrators-property-documents#h-9-%D0%B0%D0%BA%D1%82-%D0%BF%D1%80%D0%B8%D1%91%D0%BC%D0%B0-%D0%BF%D0%B5%D1%80%D0%B5%D0%B4%D0%B0%D1%87%D0%B8)  
`075` | [Протокол собрания учредителей](https://api-docs.didox.uz/ru/integrators-property-documents#h-11-%D0%BF%D1%80%D0%BE%D1%82%D0%BE%D0%BA%D0%BE%D0%BB-%D1%81%D0%BE%D0%B1%D1%80%D0%B0%D0%BD%D0%B8%D1%8F-%D1%83%D1%87%D1%80%D0%B5%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%D0%B9)  
`031` | [Письмо НК](https://api-docs.didox.uz/ru/integrators-property-documents#h-12-%D0%BF%D0%B8%D1%81%D1%8C%D0%BC%D0%BE-%D0%BD%D0%BA)  
  
* cURL
* Ответ `200`
* Ошибки
```bash
curl https://api-partners.didox.uz/v1/documents/{docType}/create/{locale} \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>" \ 
  -d '{JSON_DOC}'
```

Возвращается ID созданного черновика, дата создания и итоговый JSON документа.  
Например JSON ЭСФ:
```json
{
    "pending_document": {
        "document_json": {
            "facturaid": "68c933ffc446a09bba747505",
            "facturadoc": {
                "facturano": "Тест",
                "facturadate": "2025-09-08"
            },
            "contractdoc": {
                "contractno": "Тест",
                "contractdate": "2025-09-18"
            },
            "sellertin": "310529901",
            "buyertin": "302936161",
            "productlist": {
                "facturaproductid": "68c9340a6a52131e969eb3c1",
                "tin": "310529901",
                "hasvat": true,
                "products": [
                    {
                        "ordno": "1",
                        "catalogcode": "10713007001000000",
                        "catalogname": "Возмещение затрат (расходов) за услуги холодного водоснабжения",
                        "name": "тест",
                        "packagecode": 1505731,
                        "packagename": "кубический метр",
                        "count": "1",
                        "summa": "1",
                        "deliverysum": 1,
                        "vatrate": 12,
                        "vatsum": "0.12",
                        "deliverysumwithvat": "1.12"
                    }
                ]
            }
        }
    },
    "_id": "11f092e3428d10c68f7b1e0008000075",
    "created_date": "2025-09-16 14:55:22"
}
```

**Поля ответа**

Поле | Тип | Описание  
---|---|---  
`_id` | `string` | ID созданного документа. Используйте его в последующих запросах вместо `{id}`  
`created_date` | `string` | Дата и время создания в формате `Y-m-d H:i:s`  
`pending_document.document_json` | `object` | Итоговый JSON черновика с заполненными системными полями  
  
Код | Причина | Тело ответа  
---|---|---  
`403` | Нет полномочий на создание документа этого типа | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": { } } }`  
`422` | Неподдерживаемый тип документа | `{ "status": "error", "message": "Неподдерживаемый тип документа", "context": [] }`  
`422` | Не передан файл для произвольного документа | `{ "status": "error", "message": "Отсутствует документ", "context": [] }`  
`422` | Файл не в формате PDF | `{ "status": "error", "message": "Загружаемый файл должен быть в PDF формате", "context": [] }`  
  
* * *

# 6. Обновление черновика

POST   `/v1/documents/{id}/update/{docType}/{locale}`

Обновляет документ, находящийся в черновиках.

**Порядок действий:** получите JSON документа методом `GET /v1/documents/{id}?owner=0`, отредактируйте его и отправьте в теле запроса.

> Обновить можно только документ в статусе **Черновик (0)**. Для документа в любом другом статусе метод вернёт ошибку.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`id` | ✅ | ID документа  
`docType` | ✅ | Код типа документа  
`locale` | ⬜ | Язык: `ru` или `uz`  
  
**Тело запроса**

Для большинства типов документов в тело передаётся сам JSON документа (см. пример ниже).

Для **произвольных документов** структура другая:

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`document` | `string` (base64) / файл | ✅ | Файл документа, только формат **PDF**  
`data` | `object` | ✅ | JSON документа  
  
* cURL
* Запрос
* Запрос (произвольный документ)
* Ответ `200`
* Ошибки
```bash
curl https://api-partners.didox.uz/v1/documents/{id}/update/{docType}/{locale} \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>" \ 
  -d '{JSON_DOC}'
```
```json
{
    "ActDoc": {
        "ActNo": "тест",
        "ActDate": "2024-02-14",
        "ActText": "Мы, нижеподписавшиеся, \"\"DIDOX TECH\" MCHJ\" именуемое в дальнейшем Исполнитель, с одной стороны и \"\"VENKON GROUP\" MCHJ\" именуемое в дальнейшем Заказчик, с другой стороны составили настоящий Акт о том, что работы выполнены в соответствии с условиями Заказчика в полном объеме."
    },
    "ContractDoc": {
        "ContractNo": "тест",
        "ContractDate": "2024-02-14"
    },
    "SellerTin": "310529901",
    "ProductList": {
        "Tin": "310529901",
        "HasExcise": false,
        "HasVat": false,
        "Products": [
            {
                "OrdNo": 1,
                "CatalogCode": "00799999001000000",
                "CatalogName": "Тыква",
                "Name": "тест",
                "MeasureId": null,
                "PackageCode": "1356934",
                "PackageName": "миллиграмм",
                "Count": "10",
                "Summa": "10",
                "TotalSumWithoutVat": "100.00",
                "VatRate": 0,
                "VatSum": 0,
                "TotalSum": "100.00",
                "WithoutVat": true,
                "id": ""
            }
        ]
    },
    "SellerName": "\"DIDOX TECH\" MCHJ",
    "SellerBranchCode": "",
    "SellerBranchName": "",
    "BuyerTin": "302936161",
    "BuyerName": "\"VENKON GROUP\" MCHJ",
    "BuyerBranchCode": "",
    "BuyerBranchName": "",
    "Expansion": {
        "OrderNumber": ""
    },
    "actid": "65ccb7e9f625c47e587e2a82"
}
```
```json
{
    "document": "<PDF в base64>",
    "data": {
        "UniversalType": 1,
        "Subtype": 3,
        "DocumentDate": "2024-02-14",
        "DocumentNo": "тест"
    }
}
```
```json
{
    "data": {
        "pending_document": {
            "document_json": {
                "actid": "65ccb7e9f625c47e587e2a82",
                "actdoc": {
                    "actno": "тест",
                    "actdate": "2024-02-14",
                    "acttext": "Мы, нижеподписавшиеся, ..."
                },
                "contractdoc": {
                    "contractno": "тест",
                    "contractdate": "2024-02-14"
                },
                "sellertin": "310529901",
                "productlist": {
                    "tin": "310529901",
                    "hasexcise": false,
                    "hasvat": false,
                    "products": [
                        {
                            "id": "",
                            "ordno": 1,
                            "catalogcode": "00799999001000000",
                            "catalogname": "Тыква",
                            "name": "тест",
                            "measureid": null,
                            "packagecode": "1356934",
                            "packagename": "миллиграмм",
                            "count": "10",
                            "summa": "10",
                            "totalsumwithoutvat": "100.00",
                            "vatrate": 0,
                            "vatsum": 0,
                            "totalsum": "100.00",
                            "withoutvat": true
                        }
                    ],
                    "actproductid": "65ccb93cf625c47e587e2a85"
                },
                "sellername": "\"DIDOX TECH\" MCHJ",
                "sellerbranchcode": "",
                "sellerbranchname": "",
                "buyertin": "302936161",
                "buyername": "\"VENKON GROUP\" MCHJ",
                "buyerbranchcode": "",
                "buyerbranchname": "",
                "expansion": {
                    "ordernumber": ""
                }
            }
        },
        "_id": "11eecb38207d9204a6f82e037d118d7e",
        "created_date": "2024-02-14 17:54:01"
    }
}
```

**Поля ответа**

Поле | Тип | Описание  
---|---|---  
`data._id` | `string` | ID документа  
`data.created_date` | `string` | Дата и время **создания** документа (не обновления)  
`data.pending_document.document_json` | `object` | Итоговый JSON черновика после обновления  
  
Код | Причина | Тело ответа  
---|---|---  
`422` | Неподдерживаемый тип документа | `{ "data": { "status": "error", "message": "Неподдерживаемый тип документа", "context": [] } }`  
`422` | Документ не найден или не в статусе «Черновик» | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] } }`  
`422` | Не передан файл для произвольного документа | `{ "data": { "status": "error", "message": "Отсутствует документ", "context": [] } }`  
`422` | Файл не в формате PDF | `Загружаемый файл должен быть в PDF формате`  
`422` | Нет полномочий на обновление документа | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": { } } }`  
  
* * *

# 7. Удаление черновика

POST   `/v1/documents/{id}/delete/draft`

Удаляет документ из черновиков. Подпись не требуется.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`id` | ✅ | ID документа  
  
* cURL
* Ответ `200`
* Ошибки
```bash
curl -X POST https://api-partners.didox.uz/v1/documents/{id}/delete/draft \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "data": true
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | Документ не найден или не является черновиком | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] } }`  
  
* * *

# 8. Получение данных для подписания

POST   `/v1/documents/{id}/tosign`

Универсальный метод: возвращает данные, которые нужно подписать для выполнения конкретного действия над документом. Действие задаётся полем `action`.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`id` | ✅ | ID документа  
  
**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`action` | `string` | ✅ | Выполняемое действие (см. таблицу ниже)  
`comment` | `string` | ⬜ | Комментарий. Передаётся для действий отказа и возврата — попадает в поле `Notes` ответа  
  
**Доступные значения`action`**

`action` | Назначение | Применимо к  
---|---|---  
`accept` | Принятие (подтверждение) документа | Все типы  
`cancel` | Отмена документа | Все типы  
`reject` | Отказ от документа | Все типы  
`responsibleGive` | Подтверждение выдачи товара ответственным лицом | ТТН, гибридная ЭСФ  
`responsibleAccept` | Принятие ответственным лицом | ТТН, гибридная ЭСФ  
`responsibleTillReturn` | Возврат на этапе принятого документа | ТТН, гибридная ЭСФ  
`responsibleReturn` | Возврат доставленного товара | ТТН  
`consignorReturn` | Возврат грузоотправителю | ТТН  
`consignorReturnAccept` | Принятие возврата грузоотправителем | ТТН  
`accountantAccept` | Подписание бухгалтером | Доверенность (новая), `062`  
`agentAccept` | Подписание агентом | Доверенность (новая), `062`  
  
> Если передано неизвестное значение `action`, возвращается ошибка `Unsupported action`.  
>  Если действие не поддерживается для данного типа документа, возвращается `Not supported operation`.

> Формат поля `data` в ответе зависит от действия: это либо **объект** для подписания, либо **готовая строка подписи** в base64. Для некоторых сочетаний действия и типа документа поле возвращается пустым.

* accept
* cancel
* reject
* responsibleGive
* responsibleAccept
* responsibleTillReturn
* responsibleReturn
* consignorReturn
* consignorReturnAccept
* accountantAccept
* agentAccept

Запрос:
```json
{
   "action": "accept"
}
```

Ответ `200` — готовая подпись в base64:
```json
{
    "data": "MIAG..."
}
```

Запрос:
```json
{
   "action": "cancel"
}
```

Ответ `200` — объект для подписания. Состав полей зависит от типа документа:
```json
{
    "data": {
        "DocumentId": "11f092e3428d10c68f7b1e0008000075",
        "SellerTin": "302936161"
    }
}
```

Запрос:
```json
{
   "action": "reject",
   "comment": "test"
}
```

Ответ `200` — объект документа для подписания и комментарий в поле `Notes`:
```json
{
    "data": {
        "Act": {
            "actdoc": {
                "actno": "456",
                "actdate": "2026-04-01",
                "acttext": ""
            },
            "contractdoc": {
                "contractno": "22",
                "contractdate": "2026-01-23"
            },
            "sellertin": "313331311",
            "productlist": {
                "tin": "310595362",
                "hasexcise": false,
                "hasvat": true,
                "products": [
                    {
                        "ordno": 1,
                        "catalogcode": "10609001001000000",
                        "catalogname": "Бухгалтерские услуги",
                        "name": "Квартальный отчет",
                        "packagecode": "1492018",
                        "packagename": "услуга (сум)",
                        "count": "4",
                        "summa": "50000",
                        "totalsumwithoutvat": "200000.00",
                        "vatrate": "12",
                        "vatsum": "24000.00",
                        "totalsum": "224000.00",
                        "withoutvat": true
                    }
                ],
                "actproductid": "69ccfca9f26f6a14a221ced9"
            },
            "sellername": "Test name",
            "sellerbranchcode": "",
            "sellerbranchname": "",
            "buyertin": "310529901",
            "buyername": "ООО \"DIDOX TECH\"",
            "buyerbranchcode": "",
            "buyerbranchname": "",
            "actid": "69ccfca9f26f6a14a221ced8"
        },
        "Notes": "test"
    }
}
```

Запрос:
```json
{
    "action": "responsibleGive"
}
```

Ответ `200` для ТТН:
```json
{
    "data": {
        "WaybillLocalId": "6609276a2969e917fc002841",
        "WaybillLocalSignType": "ResponsiblePersonGiven",
        "ResponsiblePersonPinfl": "32703950230031"
    }
}
```

Ответ `200` для гибридной ЭСФ:
```json
{
    "data": {
        "HybridInvoiceId": "6609276a2969e917fc002841",
        "HybridInvoiceSignType": "ResponsibleToGoodsGiven",
        "ResponsibleToGoodsTinOrPinfl": "32703950230031"
    }
}
```

Запрос:
```json
{
   "action": "responsibleAccept"
}
```

Ответ `200` — готовая подпись в base64:
```json
{
    "data": "MIAG..."
}
```

Запрос:
```json
{
    "action": "responsibleTillReturn",
    "comment": "test"
}
```

Ответ `200` для ТТН:
```json
{
    "data": {
        "WaybillLocalId": "6609276a2969e917fc002841",
        "WaybillLocalSignType": "ResponsiblePersonTillReturned",
        "ResponsiblePersonPinfl": "32703950230031",
        "Notes": "test"
    }
}
```

Ответ `200` для гибридной ЭСФ:
```json
{
    "data": {
        "HybridInvoiceId": "6609276a2969e917fc002841",
        "HybridInvoiceSignType": "ResponsibleToGoodsTillReturned",
        "ResponsibleToGoodsTinOrPinfl": "32703950230031",
        "Notes": "test"
    }
}
```

Запрос:
```json
{
    "action": "responsibleReturn",
    "comment": "test"
}
```

Ответ `200`:
```json
{
    "data": {
        "WaybillLocalId": "6609276a2969e917fc002841",
        "WaybillLocalSignType": "ResponsiblePersonReturned",
        "ResponsiblePersonPinfl": "32703950230031",
        "Notes": "test"
    }
}
```

Запрос:
```json
{
    "action": "consignorReturn"
}
```

Ответ `200`:
```json
{
    "data": {
        "WaybillLocalId": "6609276a2969e917fc002841",
        "ConsignorTinOrPinfl": "302936161"
    }
}
```

Запрос:
```json
{
    "action": "consignorReturnAccept"
}
```

Ответ `200`:
```json
{
    "data": {
        "WaybillLocalId": "6609276a2969e917fc002841",
        "WaybillLocalSignType": "ConsignorReturnAccepted",
        "ConsignorTinOrPinfl": "302936161"
    }
}
```

Для новой доверенности (`doctype = 062`). Запрос:
```json
{
    "action": "accountantAccept"
}
```

Ответ `200`:
```json
{
    "data": "MIAG..."
}
```

Для новой доверенности (`doctype = 062`). Запрос:
```json
{
    "action": "agentAccept"
}
```

Ответ `200`:
```json
{
    "data": "MIAG..."
}
```

* * *

# 9. Подписание исходящего документа

POST   `/v1/documents/{id}/sign`

Подписание и отправка исходящего документа.

> Перед первым подписанием у пользователя (или компании) должна быть **подписана оферта** , иначе метод вернёт ошибку.

**Порядок действий:**

  1. [Получить список ключей](https://api-docs.didox.uz/ru/integrators-eimzo#h-1-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B0-%D0%B4%D0%BE%D1%81%D1%82%D1%83%D0%BF%D0%BD%D1%8B%D1%85-%D0%BA%D0%BB%D1%8E%D1%87%D0%B5%D0%B9-%D0%BD%D0%B0-%D0%BB%D0%BE%D0%BA%D0%B0%D0%BB%D1%8C%D0%BD%D0%BE%D0%BC-%D0%B4%D0%B8%D1%81%D0%BA%D0%B5).
  2. [Получить `keyId`](https://api-docs.didox.uz/ru/integrators-eimzo#h-2-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-keyid).
  3. Получить значение `json` из ответа `GET /v1/documents/{id}?owner=1`.
  4. Преобразовать полученный JSON в base64.
  5. [Создать подпись](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8) — первым аргументом передать base64 из шага 4.
  6. [Прикрепить timestamp к подписи](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8).
  7. Отправить значение `timeStampTokenB64` в теле запроса.


**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подпись с прикреплённым timestamp  
  
* Запрос
* Ответ `200`
* Ошибки
```json
{
    "signature": "<timeStampTokenB64>"
}
```
```json
{
    "data": true,
    "warningDetails": null
}
```

Если при подписании со стороны НК пришли предупреждения, в `warningDetails` возвращается объект:
```json
{
    "data": true,
    "warningDetails": {
        "id": "<x-trace-id>",
        "title": "warnings",
        "message": "<текст предупреждения>",
        "description": null
    }
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | Не передано поле `signature` | `{ "signature": ["<текст ошибки>"] }`  
`422` | Оферта не подписана | `{ "data": { "status": "error", "message": "Оферта не подписана", "context": { "offer": "required" } } }`  
`422` | Учётная запись отключена | `{ "data": { "status": "error", "message": "User status disabled", "context": [] } }`  
`422` | Ошибка валидации документа | `{ "data": { "status": "error", "message": "Ошибка валидации: <текст>", "context": [] } }`  
`422` | Ошибка сохранения | `{ "data": { "status": "error", "message": "Ошибка обновления в базе", "context": [] } }`  
`403` | Нет полномочий на отправку документа | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": { } } }`  
`503` | Внешний сервис недоступен или не ответил вовремя | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] }, "errorDetails": { } }`  
  
> При прочих ошибках в ответе может присутствовать блок `errorDetails` с расшифровкой:
```
{
  "id": "<x-trace-id>",
  "title": "<заголовок ошибки>",
  "message": "<исходный текст ошибки>",
  "description": "<пояснение, что делать>"
}
```
> 
> Язык `title` и `description` определяется заголовком `Accept-Language`. Если расшифровки для ошибки нет, поле равно `null`.

* * *

# 10. Подписание входящего документа

POST   `/v1/documents/{id}/sign`

Принятие (подтверждение) входящего документа. Используется тот же эндпоинт, что и для исходящих — различается только способ формирования подписи.

> **Требование:** версия E-IMZO от **6.3.5** и выше.

**Порядок действий:**

  1. Получить base64 документа: `GET /v1/documents/{id}/documentBase64`.
  2. Создать подпись из полученного base64.
  3. [Прикрепить timestamp](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8) к созданной подписи.
  4. Получить значение `toSign` из ответа `GET /v1/documents/{id}?owner=0`.
  5. Объединить подписи через `POST /v1/dsvs/signature/join`.
  6. Отправить значение `pkcs7B64` из ответа шага 5 в тело запроса подписания.


**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Объединённая подпись  
  
* Шаг 5 — объединение подписей
* Шаг 6 — подписание
* Ответ `200`
* Ошибки

`POST /v1/dsvs/signature/join`
```json
{
    "signature1": "<подпись из шага 4>",
    "signature2": "<подпись из шага 3>"
}
```

`POST /v1/documents/{id}/sign`
```json
{
    "signature": "<pkcs7B64 из шага 5>"
}
```
```json
{
    "data": true,
    "warningDetails": null
}
```

Совпадают с ошибками метода «Подписание исходящего документа» — см. раздел 9. Для входящих документов проверяется полномочие на подписание, а не на отправку.

* * *

# 11. Отклонение (отказ) документа

POST   `/v1/documents/{id}/reject`

Отказ от входящего документа.

**Порядок действий:**

  1. Получить данные для подписания: `POST /v1/documents/{id}/tosign` с телом `{ "action": "reject", "comment": "отказ..." }` — см. раздел 8.
  2. Подписать объект из поля `data` полученного ответа.
  3. [Прикрепить timestamp к подписи](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8).
  4. Отправить подпись и комментарий в теле запроса.


**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подпись с прикреплённым timestamp. Допускается также имя поля `pkcs7`  
`comment` | `string` | ✅ | Причина отказа. Должна совпадать с комментарием, переданным на шаге 1  
  
* Запрос
* Ответ `200`
* Ошибки
```json
{
    "comment": "отказ...",
    "signature": "<timeStampTokenB64>"
}
```
```json
{
    "data": true
}
```

Код | Причина | Тело ответа  
---|---|---  
`403` | Нет полномочий на отклонение документа | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": { } } }`  
`422` | Документ не найден или находится в статусе, из которого отказ невозможен | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] } }`  
  
* * *

# 12. Удаление (отмена) документа

POST   `/v1/documents/{id}/delete`

Отмена отправленного исходящего документа.

**Порядок действий:**

  1. Получить данные для подписания: `POST /v1/documents/{id}/tosign` с телом `{ "action": "cancel" }` — см. раздел 8.
  2. Подписать полученный объект и [прикрепить timestamp](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8).
  3. Отправить подпись в теле запроса.


**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подпись с прикреплённым timestamp. Допускается также имя поля `pkcs7`  
  
* Запрос
* Ответ `200`
* Ошибки
```json
{
    "signature": "<timeStampTokenB64>"
}
```
```json
{
    "data": true
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | Не передано поле `signature` | `{ "signature": ["<текст ошибки>"] }`  
`403` | Нет полномочий на удаление документа | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": { } } }`  
`422` | Документ не найден или не может быть отменён | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] } }`  
  
* * *

# 13. ТТН — подтверждение доставки

POST   `/v1/documents/{id}/give`

Подтверждение выдачи товара ответственным лицом.

> Документ должен находиться в статусе **Принято (отв. лицом)** — код `140` или `240`.

Данные для подписания получите через `POST /v1/documents/{id}/tosign` с `action: "responsibleGive"` — см. раздел 8.

**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подпись с прикреплённым timestamp  
  
* Запрос
* Ответ `200`
* Ошибки
```json
{
    "signature": "MIA..."
}
```
```json
{
    "data": true
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | Документ не найден или находится в неподходящем статусе | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] } }`  
  
* * *

# 14. ТТН — возврат на этапе принятого документа

POST   `/v1/documents/{id}/tillreturn`

Возврат груза ответственным лицом на этапе принятого документа.

> Документ должен находиться в статусе **Принято (отв. лицом)** — код `140` или `240`.

Данные для подписания получите через `POST /v1/documents/{id}/tosign` с `action: "responsibleTillReturn"` — см. раздел 8.

**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подпись с прикреплённым timestamp  
`comment` | `string` | ✅ | Причина возврата. Должна совпадать с комментарием, переданным при получении данных для подписания  
  
* Запрос
* Ответ `200`
* Ошибки
```json
{
    "signature": "MIA...",
    "comment": "test"
}
```
```json
{
    "data": true
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | Документ не найден или находится в неподходящем статусе | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] } }`  
  
* * *

# 15. ТТН — возврат доставленного товара

POST   `/v1/documents/{id}/return`

Возврат ТТН ответственным лицом на этапе доставленного товара получателю.

> Документ должен находиться в статусе **Доставлено получателю** (`160`) или **Груз возвращен (отв. лицом)** (`190`).

Данные для подписания получите через `POST /v1/documents/{id}/tosign` с `action: "responsibleReturn"` — см. раздел 8.

**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подпись с прикреплённым timestamp  
`comment` | `string` | ✅ | Причина возврата  
  
* Запрос
* Ответ `200`
* Ошибки
```json
{
    "signature": "MIA...",
    "comment": "test"
}
```
```json
{
    "data": true
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | Документ не найден или находится в неподходящем статусе | `{ "data": { "status": "error", "message": "<текст ошибки>", "context": [] } }`  
  
* * *

# 16. Печатная форма документа

Печатную форму можно получить в трёх форматах. Для каждого формата есть два варианта эндпоинта, различающихся способом авторизации.

Формат | Эндпоинт | Требуемые заголовки  
---|---|---  
HTML | `GET /v1/documents/view/{id}/html/{locale}` | `Partner-Authorization` \+ `user-key`  
HTML | `GET /v1/documents/{id}/html/{locale}` | `Partner-Authorization`  
PDF | `GET /v1/documents/view/{id}/pdf/{locale}` | `Partner-Authorization` \+ `user-key`  
PDF | `GET /v1/documents/{id}/pdf/{locale}` | `Partner-Authorization`  
PDF в base64 | `GET /v1/documents/{id}/file/true/{locale}` | `Partner-Authorization`  
  
> Варианты с `view/` проверяют, что документ относится к текущему пользователю и что у него есть право просмотра документов этого типа. Используйте их, если работаете от имени конкретного пользователя.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`id` | ✅ | ID документа  
`locale` | ⬜ | Язык печатной формы: `ru` или `uz`  
  
* HTML
* PDF
* PDF в base64
* Ошибки
```bash
curl https://api-partners.didox.uz/v1/documents/view/{id}/html/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```

Ответ `200` — готовая HTML-страница со встроенными стилями. Шаблон подбирается по типу документа:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Счет-фактура без акта</title>
    <style>/* стили печатной формы */</style>
</head>
<body>
    <div class="be__section">
        <div class="be__doc">
            <div class="be__signed">
                <div class="be__signed__title">Документ подписан:</div>
            </div>
            <div class="be__doc-id">
                <div class="be__doc-id__text">11EBB252759AB8E0ACC21E00610000B4</div>
                <div class="be__doc-id__title">идентификатор электронного документа</div>
            </div>
            <div class="be__factura-type">Стандартный</div>
            <div class="be__title">
                Счет-фактура<br>№ elastic-sign-2052 от 11.05.2021<br>к договору № 1 от 11.05.2021
            </div>
            <!-- реквизиты сторон, таблица товаров, подписи -->
        </div>
    </div>
</body>
</html>
```
```bash
curl https://api-partners.didox.uz/v1/documents/view/{id}/pdf/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>" \
  --output document.pdf
```

Ответ `200` — бинарный PDF-файл:
```text
Content-Type: application/pdf
Content-Disposition: inline; filename="document.pdf"

%PDF-1.7
3 0 obj
...
```

Если к документу приложен акт, в ответе присутствует дополнительный заголовок `PageCountWithoutAct` — количество страниц документа без акта.
```bash
curl https://api-partners.didox.uz/v1/documents/{id}/file/true/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>"
```

Ответ `200`:
```json
{
    "file": {
        "data": "JVBERi0xLjcKMyAwIG9iago...",
        "page_count_without_act": "3"
    }
}
```

Поле | Тип | Описание  
---|---|---  
`file.data` | `string` | Содержимое PDF в base64  
`file.page_count_without_act` | `string` | Количество страниц без акта. Пустая строка, если акта нет  
  
Код | Причина | Тело ответа  
---|---|---  
`422` | Документ не относится к текущему пользователю | `"Для вас такого документа не существует"`  
`422` | Нет права просмотра документов этого типа | `"<текст ошибки>"`  
`422` | Не удалось сформировать печатную форму | `"<текст ошибки>"`  
  
> Ошибки этого раздела возвращаются строкой, а не объектом.

* * *

# 17. Архив с информацией о документе

GET   `/v1/documents/{id}/archive`

Возвращает ZIP-архив, содержащий подписи, PDF и JSON документа. Архив отдаётся файлом напрямую в теле ответа.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`id` | ✅ | ID документа  
  
**Заголовки**

Заголовок | Обяз. | Описание  
---|---|---  
`Partner-Authorization` | ✅ | Партнёрский токен  
`user-key` | ✅ | Токен пользователя  
`Accept-Language` | ⬜ | Язык содержимого: `ru` или `uz`  
  
* cURL
* Ответ `200`
* Ошибки
```bash
curl https://api-partners.didox.uz/v1/documents/{id}/archive \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>" \
  -H "Accept-Language: ru" \
  --output document.zip
```

Файл в формате `.zip`.

Код | Причина | Тело ответа  
---|---|---  
`500` | Не удалось создать архив | `{ "data": null, "error": { "message": "Не удалось создать архив", "reason": "<текст ошибки>", "details": [] } }`  
  
* * *

# 18. Данные по договору для СФ

GET   `/v1/documents/contract/{contractId}/info/{locale}`

Возвращает данные договора, которые можно использовать для заполнения счёта-фактуры.

**Параметры пути**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`contractId` | `integer` | ✅ | ID договора. Только целое число  
`locale` | `string` | ⬜ | Язык результата: `ru` или `uz`. По умолчанию берётся из заголовка `Accept-Language`  
  
* cURL
* Ответ `200`
* Ошибки
```bash
curl https://api-partners.didox.uz/v1/documents/contract/10078617/info/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
  "contract_id": 10078617,
  "contract_status": 0,
  "external_id": "60a49633674901000148ba4a",
  "contract_place": "123",
  "contract_no": "123",
  "contract_date": 1621382400000,
  "contract_expire_date": 1621382400000,
  "owner": {
    "tin": "302936161",
    "name": "OOO \"VENKON GROUP\"",
    "address": "Toshkent shahri, Yakkasaroy tumani, Sh.Rustaveli ko'chasi, 53b-uy",
    "phone": "998901889455",
    "oked": null,
    "account": "20208000400308125001",
    "mfo": "00974",
    "bank_name": "00974",
    "fiz_tin": "451299778",
    "fiz_fio": "ISMAILOV ASQARJON BAXROMJONOVICH",
    "branch_num": null,
    "branch_name": null,
    "region_code": 26,
    "region_name_uz": "Тошкент шаҳар",
    "region_name_ru": "город Ташкент",
    "district_code": 4,
    "district_name_uz": "Яккасарой тумани",
    "district_name_ru": "Яккасарайский район"
  },
  "contragents": [
    {
      "tin": "207119963",
      "name": "WEBMEDIA INFORMATION",
      "address": "ОЛОЙ МАВЗЕСИ, 9-УЙ.",
      "phone": "998909331477",
      "oked": "63110",
      "account": "20208000304919341001",
      "mfo": "01075",
      "bank_name": "01075",
      "fiz_tin": "451299778",
      "fiz_fio": "ISMAILOV ASQARJON BAXROMJONOVICH",
      "branch_num": null,
      "branch_name": null,
      "region_code": null,
      "region_name_uz": null,
      "region_name_ru": null,
      "district_code": null,
      "district_name_uz": null,
      "district_name_ru": null
    }
  ],
  "products": [
    {
      "ord": 1,
      "product_name": "Помидоры",
      "product_name_full": null,
      "product_code": "70801002",
      "product_bar_code": null,
      "measure_id": 5,
      "item_sum": 15000,
      "count": 1,
      "excise_sum": 0,
      "vat_sum": 0,
      "total_sum": 15000,
      "delivery_sum": 15000,
      "vat_rate": -1
    }
  ],
  "contract_total_sum": 15000,
  "contract_date_string": "2021-05-19",
  "contract_expire_date_string": "2021-05-19"
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | `contractId` не передан или не является целым числом | `{ "contractId": ["<текст ошибки>"] }`  
`422` | Не удалось получить данные договора | `{ "error": "<текст ошибки>", "message": "<текст ошибки>" }`  
  
* * *

# 19. Информация о лоте

GET   `/v1/documents/exchange`

Возвращает информацию о биржевом лоте.

**Query-параметры**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`buyerTin` | `string` | ✅ | ИНН контрагента. Ровно **9 цифр**  
`lotId` | `string` | ✅ | ID лота вместе с префиксом типа сделки  
  
* cURL
* Ответ `200`
* Ошибки
```bash
curl "https://api-partners.didox.uz/v1/documents/exchange?buyerTin=200349889&lotId=SHAFFOF-24411010077892" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "lotId": "77892",
    "sellerTin": "200937838",
    "buyerTin": "200349889",
    "buyerAccount": "304510860354017045163118001",
    "contractNo": "дс 1 к дог СМ-2",
    "contractDate": "2024-12-31T00:00:00",
    "products": [
        {
            "ordNo": 1,
            "productName": "Услуга по ремонту и содержанию автомобильных дорог #44233100#",
            "measureId": "93",
            "count": 1,
            "summa": 234902000,
            "totalSum": 234902000,
            "planPositionId": 1,
            "productCode": "42.11.20.000-00006",
            "productProperties": "0;0;",
            "monthId": null
        }
    ]
}
```

Код | Причина | Тело ответа  
---|---|---  
`422` | `buyerTin` не передан или содержит не 9 цифр | `{ "buyerTin": ["<текст ошибки>"] }`  
`422` | Не передан `lotId` | `{ "lotId": ["<текст ошибки>"] }`  
`422` | Не удалось получить данные лота | `"<текст ошибки>"`  
  
* * *

# 20. Список типов сделки по лоту

GET   `/v1/documents/exchange/types`

Возвращает список типов сделок и соответствующих им префиксов ID лота. Параметров не требует.

* cURL
* Ответ `200`
* Ошибки
```bash
curl https://api-partners.didox.uz/v1/documents/exchange/types \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
[
  {
    "prefix": "CPR-",
    "name": "cooperation.uz"
  },
  {
    "prefix": "XT-",
    "name": "tender.mf.uz"
  },
  {
    "prefix": "DX-P-",
    "name": "Давлат харидлар, Тўғридан-тўғри"
  }
]
```

Код | Причина | Тело ответа  
---|---|---  
`422` | Не удалось получить список типов сделки | `"<текст ошибки>"`  
  
* * *

# 21. Получение префикса типа сделки

GET   `/v1/documents/exchange/lotswithtypes/{locale}`

Возвращает префикс и название типа сделки для указанного лота. В отличие от предыдущего метода, `lotId` здесь передаётся **без префикса**.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`locale` | ⬜ | Язык результата: `ru` или `uz`. По умолчанию берётся из заголовка `Accept-Language`  
  
**Query-параметры**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`buyerTin` | `string` | ✅ | ИНН контрагента. Ровно **9 цифр**  
`lotId` | `string` | ✅ | ID лота  
  
* cURL
* Ответ `200`
* Ошибки
```bash
curl "https://api-partners.didox.uz/v1/documents/exchange/lotswithtypes/ru?buyerTin=200349889&lotId=24411010077892" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
[
    {
        "lotId": "24411010077892",
        "prefix": "SHAFFOF-",
        "typeOfDealName": "Shaffof qurilish"
    }
]
```

Код | Причина | Тело ответа  
---|---|---  
`422` | `buyerTin` не передан или содержит не 9 цифр | `{ "buyerTin": ["<текст ошибки>"] }`  
`422` | Не передан `lotId` | `{ "lotId": ["<текст ошибки>"] }`  
`422` | Не удалось определить тип сделки | `"<текст ошибки>"`  
  
* * *

# 22. Список ЭСФ на доверенные лица

GET   `/v2/documents`

Возвращает список входящих ЭСФ, отправленных на доверенные лица. Используется тот же метод, что и «Список документов», с фиксированным набором фильтров.

**Запрос**
```http
GET /v2/documents?page=1&limit=20&owner=0&doctype=002,008,001&status=60
```

Параметр | Значение | Описание  
---|---|---  
`owner` | `0` | Только входящие документы  
`doctype` | `002,008,001` | Типы счетов-фактур  
`status` | `60` | Ожидают подписи агента  
  
**Дополнительные поля ответа**

Поле | Описание  
---|---  
`roaming_agent_id` | ID документа доверенного лица  
`agent_tin` | ИНН/ПИНФЛ доверенного лица  
`agent_fio` | ФИО доверенного лица  
  
* cURL
* Ответ `200`
```bash
curl "https://api-partners.didox.uz/v2/documents?page=1&limit=20&owner=0&doctype=002,008,001&status=60" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "data": [
        {
            "pid": 35595829,
            "doc_id": "11EEDB9F284AA68A9A3A2E037D118D7E",
            "usersTaxId": "207119963",
            "name": "no invoice",
            "doc_date": "2024-03-06",
            "doc_status": 60,
            "doctype": "002",
            "contract_number": "No contract",
            "contract_date": "2024-03-06",
            "owner": 0,
            "agent": 0,
            "partnerTin": "302936161",
            "partnerCompany": "\"VENKON GROUP\" MCHJ",
            "partnerPhone": "998909331477",
            "total_sum": 1,
            "total_delivery_sum": 1,
            "total_vat_sum": 0.12,
            "total_delivery_sum_with_vat": 1.12,
            "oneside": 0,
            "has_committent": 0,
            "has_vat": true,
            "has_lgota": 0,
            "has_marks": 0,
            "roaming_id": "65e83cd98d35d6386ac058fc",
            "roaming_agent_id": "65e83cd98d35d6386ac058fe",
            "agent_tin": "50310006540052",
            "agent_fio": "",
            "updated": "2024-03-06",
            "updated_date": "2024-03-06T09:52:42",
            "updated_unix": 1709718762,
            "created": "2024-03-06",
            "created_unix": 1709718711,
            "partiesID": "11EEDB9F2891E93C93342E037D118D7E",
            "lgota_codes": "",
            "factura_type": 0,
            "sellerAccount": "20208000400308125001",
            "status_comment": null,
            "internal_status": null,
            "internal_comment": null,
            "internal_status_alarm": null,
            "mark_codes": null,
            "signed": null,
            "branch_num": null
        }
    ],
    "total": 137,
    "next_page_url": "v2/documents?doctype=002%2C008%2C001&limit=10&owner=0&page=2&status=60",
    "source": "search"
}
```
