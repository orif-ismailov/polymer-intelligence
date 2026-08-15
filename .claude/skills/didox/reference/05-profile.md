# 05. Профиль

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-profile>
> Source last updated: 2026-08-04T08:54:41.795Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена нкобходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

# Профиль

Методы для работы с данными профиля, ИКПУ-кодами, филиалами, складами и ролями.

> **Аутентификация.** Все методы раздела требуют двух заголовков:
```
Partner-Authorization: <PARTNER_TOKEN>
user-key: <USER_TOKEN>
```

\# | Метод | Эндпоинт | Назначение  
---|---|---|---  
1 | `GET` | `/v1/profile` | Данные текущего профиля  
2 | `POST` | `/v1/profile/update` | Изменение профиля  
3 | `GET` | `/v1/profile/operators` | Операторы по ИНН  
4 | `GET` | `/v1/profile/branches` | Филиалы по ИНН  
5 | `GET` | `/v1/profile/productClassCodes` | Привязанные ИКПУ  
6 | `POST` | `/v1/profile/productClasses` | Привязать ИКПУ  
7 | `DELETE` | `/v1/profile/productClasses/{classCode}` | Отвязать ИКПУ  
8 | `GET` | `/v1/profile/productClassCodes` | Поиск по ИКПУ  
9 | `GET` | `/v1/profile/vatRegStatus/{taxId}` | Статус рег.кода НДС  
10 | `GET` | `/v1/profile/{taxId}/productClasses/check/{code}/{lang}` | Упаковки по ИКПУ  
11 | `GET` | `/v1/profile/warehouses/{taxId}` | Склады по ИНН/ПИНФЛ  
12 | `GET` | `/v1/profile/taxpayerType/{taxId}/{lang}` | Тип налогоплательщика  
13 | `PUT` | `/v1/profile/company/users` | Настройка ролей  
  
> **Форматы ошибок.** Методы раздела возвращают ошибки в одном из двух видов:
> 
> Общая ошибка обработки запроса:
```
{ "success": false, "error": "<текст ошибки>" }
```
> 
> Ошибка проверки переданных данных — объект, где ключ является именем поля:
```
{ "<имя поля>": ["<текст ошибки>"] }
```

* * *

# 1. Данные текущего профиля

GET   `/v1/profile`

Возвращает данные текущего профиля.

> По умолчанию возвращаются данные **покупателя**. Для данных **продавца** передайте `isSeller=true`. При этом меняются значения полей `VATRegCode`, `VATRegStatus`, `VATRegStatusCode`.

**Query-параметры**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`isSeller` | `boolean` | ⬜ | `true` — данные продавца; не указан или `false` — данные покупателя  
  
* cURL
* Ответ `200`
```bash
curl "https://api-partners.didox.uz/v1/profile?isSeller=true" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "vatRate": null,
    "fullName": "\"WEBMEDIA INFORMATION\" MCHJ",
    "shortName": "\"WEBMEDIA INFORMATION\" MCHJ",
    "itemReleasedFio": "",
    "vat": 0,
    "excise": false,
    "logo": null,
    "account": "20208000604919341001",
    "bankCode": "01071",
    "oked": "63110",
    "address": "ГОРОД ТАШКЕНТ ЯККАСАРАЙСКИЙ РАЙОН Хамид Сулаймон МФЙ, Глинка кучаси, 41а-уй  ",
    "regionId": 26,
    "districtId": "2604",
    "phone": "999999999999",
    "mobile": "999999999999",
    "email": "m1kadosgs@gmail.com",
    "accountant": "ISMAILOV ABROR BAXRAMJONOVICH",
    "director": "ISMAILOV ABROR BAXRAMJONOVICH",
    "directorTin": "491479350",
    "directorPinfl": "30902890231313",
    "notifications": 1,
    "isPremium": 0,
    "additionalAccounts": [],
    "mfo": "01071",
    "additionalMfos": [],
    "company": "\"WEBMEDIA INFORMATION\" MCHJ",
    "vatRegCode": "326020089828",
    "pinfl": null,
    "partner": null,
    "origin": null,
    "incomingDraftsVisibility": null,
    "autofillDocThruContractId": false,
    "type": null,
    "useCodesFromDb": true,
    "balance": "0.00",
    "blockAds": 0,
    "updates": [],
    "tin": "207119963",
    "name": "\"WEBMEDIA INFORMATION\" MCHJ",
    "VATRegStatus": 20,
    "vatCode": "326020089828",
    "offerSigned": 1,
    "messengers": {
        "telegram": "https://t.me/didoxdev_bot?start=ru_e0c557b85c50465cacddf09dba48aace"
    }
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`401` | Недействительный или отсутствующий `user-key` | `Unauthorized. Invalid user key`  
  
* * *

# 2. Изменение данных профиля

POST   `/v1/profile/update`

Обновляет данные текущего профиля. Передавайте только те поля, которые нужно изменить.

> Если пользователь авторизован в контексте **филиала** , изменения применяются к данным филиала.

* Запрос
* Ответ `200`
```json
{
    "firstName": "ABROR",
    "lastName": "ISMAILOV",
    "phone": "999999999999",
    "mobile": "999999999999",
    "notifications": 1,
    "mfo": "01071",
    "account": "20208000604919341001",
    "oked": "63110",
    "director": "ISMAILOV ABROR BAXRAMJONOVICH",
    "accountant": "ISMAILOV ABROR BAXRAMJONOVICH",
    "districtId": "2604",
    "regionId": 26,
    "vatRegCode": "326020089828",
    "vatRate": null,
    "itemReleasedFio": "",
    "itemReleasedPinfl": null,
    "vat": 0,
    "excise": false,
    "address": "ГОРОД ТАШКЕНТ ЯККАСАРАЙСКИЙ РАЙОН Хамид Сулаймон МФЙ, Глинка кучаси, 41а-уй  ",
    "directorTin": "491479350",
    "offerDocumentId": "11eeab9ca946744ab7392e037d118d7e",
    "offerSigned": 1,
    "additionalAccounts": [],
    "pinfl": null,
    "directorPinfl": "30902890231313",
    "origin": null,
    "companyTaxId": "207119963",
    "companyName": "\"WEBMEDIA INFORMATION\" MCHJ",
    "name": "\"WEBMEDIA INFORMATION\" MCHJ",
    "bankId": "01071",
    "tin": "207119963",
    "regCode": "326020089828",
    "vatCode": "326020089828",
    "bankAccount": "20208000604919341001",
    "bankCode": "01071",
    "additionalMfos": []
}
```
```json
{
    "id": 0,
    "taxId": "207119963",
    "company": "\"WEBMEDIA INFORMATION\" MCHJ",
    "firstName": "ABROR",
    "lastName": "ISMAILOV",
    "phone": "999999999999",
    "mobile": "999999999999",
    "email": "m1kadosgs@gmail.com",
    "admin": "999999999",
    "updated": "2024-02-14 10:51:46",
    "created": "2024-02-13 16:33:44",
    "notifications": 1,
    "mfo": "01071",
    "account": "20208000604919341001",
    "oked": "63110",
    "director": "ISMAILOV ABROR BAXRAMJONOVICH",
    "accountant": "ISMAILOV ABROR BAXRAMJONOVICH",
    "districtId": "2604",
    "regionId": 26,
    "vatRegCode": "326020089828",
    "status": 1,
    "isPremium": 0,
    "vatRate": null,
    "itemReleasedFio": "",
    "itemReleasedPinfl": null,
    "vat": 0,
    "excise": false,
    "address": "ГОРОД ТАШКЕНТ ЯККАСАРАЙСКИЙ РАЙОН Хамид Сулаймон МФЙ, Глинка кучаси, 41а-уй  ",
    "fullName": "\"WEBMEDIA INFORMATION\" MCHJ",
    "shortName": "\"WEBMEDIA INFORMATION\" MCHJ",
    "uzcardSignDate": null,
    "directorTin": "491479350",
    "offerDocumentId": "11eeab9ca946744ab7392e037d118d7e",
    "offerSigned": 1,
    "additionalAccounts": [],
    "pinfl": null,
    "directorPinfl": "30902890231313",
    "partner": null,
    "origin": null,
    "categorySeller": null,
    "realizationPurpose": null,
    "incomingDraftsVisibility": null,
    "autofillDocThruContractId": false,
    "type": null,
    "useCodesFromDb": true,
    "user_id": 0,
    "companyTaxId": "207119963",
    "companyName": "\"WEBMEDIA INFORMATION\" MCHJ",
    "name": "\"WEBMEDIA INFORMATION\" MCHJ",
    "bankId": "01071",
    "tin": "207119963",
    "shortname": "\"WEBMEDIA INFORMATION\" MCHJ",
    "fullname": "\"WEBMEDIA INFORMATION\" MCHJ",
    "regCode": "326020089828",
    "vatCode": "326020089828",
    "bankAccount": "20208000604919341001",
    "bankCode": "01071",
    "additionalMfos": []
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Не удалось обновить профиль | `{ "success": false, "error": "User not updated" }`  
  
> В поле `error` возвращается текст конкретной ошибки; `"User not updated"` — значение по умолчанию.

* * *

# 3. Операторы, привязанные к ИНН

GET   `/v1/profile/operators`

Возвращает операторов, привязанных к текущему профилю, в виде пар «ИНН оператора → название».

* cURL
* Ответ `200`
```bash
curl https://api-partners.didox.uz/v1/profile/operators \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
  "202530465": "soliqservis.uz",
  "302563857": "Faktura.uz",
  "302936161": "Didox.uz"
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Не удалось получить операторов | `{ "success": false, "error": "<текст ошибки>" }`  
  
* * *

# 4. Филиалы по ИНН

GET   `/v1/profile/branches`

Возвращает список филиалов по ИНН.

**Query-параметры**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`tin` | `string` | ✅ | ИНН компании. Только цифры, длина от 9 до 14  
  
* cURL
* Ответ `200`
```bash
curl "https://api-partners.didox.uz/v1/profile/branches?tin=310529901" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
[
    {
        "id": 230384,
        "ns10Code": 14,
        "ns10Name": "Наманган вилояти",
        "ns11Code": 16,
        "ns11Name": "Чуст тумани",
        "tin": "310529901",
        "name": "\"DIDOX TECH\" MCHJ",
        "branchName": "Чуст филиал",
        "branchNum": "00001",
        "isDeleted": 0,
        "createdDate": "07.02.2024",
        "deletedDate": null,
        "directorTin": "583845972",
        "directorName": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI",
        "directorPinfl": 30606950270086,
        "pinfl": null,
        "accountantTin": "582876777",
        "accountantName": "XVAN VLADIMIR VIKTOROVICH",
        "accountantPinfl": 32903986520045,
        "mfo": "01076",
        "account": "11111222223333344444",
        "latitude": "41.32128348829411",
        "longitude": "69.25460790022818",
        "clientIp": null,
        "url": null,
        "lang": null,
        "source": null,
        "address": "Тошкент, Махтумкули 1А"
    }
]
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Параметр `tin` не передан или имеет неверный формат | `{ "tin": ["<текст ошибки>"] }`  
`422` | Не удалось получить филиалы | `{ "success": false, "error": "<текст ошибки>" }`  
  
* * *

# 5. Привязанные ИКПУ к профилю

GET   `/v1/profile/productClassCodes`

Возвращает ИКПУ-коды, привязанные к текущему профилю. Ответ постраничный.

* cURL
* Ответ `200`
```bash
curl https://api-partners.didox.uz/v1/profile/productClassCodes \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "current_page": 1,
    "data": [
        {
            "classCode": "11703002001000000",
            "internationalCode": null,
            "className": "Услуги игровых и компьютерных залов всех видов, в том числе по работе с документами (ламинирование, копирование, сканирование, набор текста, печать, переплет и прочие)",
            "className_ru": "Услуги игровых и компьютерных залов всех видов, в том числе по работе с документами (ламинирование, копирование, сканирование, набор текста, печать, переплет и прочие)",
            "usePackage": 1,
            "packages": [
                { "code": "1503980", "name_ru": "услуга (раз)", "name": "услуга (раз)" },
                { "code": "1503982", "name_ru": "услуга (сум)", "name": "услуга (сум)" },
                { "code": "1524875", "name_ru": "шт.", "name": "шт." }
            ],
            "origin": { "id": 3, "name": "Оказание услуг" }
        }
    ]
}
```

* * *

# 6. Привязать ИКПУ код к пользователю

POST   `/v1/profile/productClasses`

Добавляет ИКПУ-код к текущему профилю.

**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`classCode` | `string` | ✅ | Код ИКПУ  
  
* Запрос
* cURL
* Ответ `200`
```json
{
    "classCode": "08418001001013043"
}
```
```bash
curl -X POST https://api-partners.didox.uz/v1/profile/productClasses \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{ "classCode": "08418001001013043" }'
```
```json
{
    "success": true,
    "error": []
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Поле `classCode` не передано | `{ "classCode": ["<текст ошибки>"] }`  
`422` | Не удалось привязать код | `{ "success": false, "error": "<текст ошибки>" }`  
  
* * *

# 7. Отвязать ИКПУ код от пользователя

DELETE   `/v1/profile/productClasses/{classCode}`

Удаляет ИКПУ-код у текущего профиля.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`classCode` | ✅ | Код ИКПУ  
  
* cURL
* Ответ `200`
```bash
curl -X DELETE https://api-partners.didox.uz/v1/profile/productClasses/08418001001013043 \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "success": true,
    "error": []
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Не удалось отвязать код | `{ "success": false, "error": "<текст ошибки>" }`  
  
* * *

# 8. Поиск по добавленным ИКПУ

GET   `/v1/profile/productClassCodes`

Поиск классов продуктов, которые можно привязать к пользователю.

**Заголовки**

Заголовок | Обяз. | Описание  
---|---|---  
`Partner-Authorization` | ✅ | Партнёрский токен  
`user-key` | ✅ | Токен пользователя  
`Accept-Language` | ⬜ | Язык результата: `ru` или `uz`  
  
**Query-параметры**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`page` | `integer` | ⬜ | Номер страницы  
`search` | `string` | ⬜ | Текст для поиска  
  
* cURL
* Ответ `200`
```bash
curl "https://api-partners.didox.uz/v1/profile/productClassCodes?page=1&search=фото" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>" \
  -H "Accept-Language: ru"
```
```json
{
    "current_page": 1,
    "data": [
        {
            "classCode": "11702004001000000",
            "internationalCode": null,
            "className": "Фото и видео услуги (все виды услуг)",
            "className_ru": "Фото и видео услуги (все виды услуг)",
            "usePackage": 1,
            "packages": [
                { "code": "1478243", "name_ru": "услуга (сум)", "name": "услуга (сум)" },
                { "code": "1478244", "name_ru": "услуга (раз)", "name": "услуга (раз)" },
                { "code": "1503851", "name_ru": "шт.", "name": "шт." },
                { "code": "1503864", "name_ru": "квадратный метр", "name": "квадратный метр" }
            ],
            "origin": { "id": 3, "name": "Оказание услуг" }
        }
    ],
    "first_page_url": "https://api-partners.didox.uz/v1/profile/productClassCodes/?page=1",
    "from": 1,
    "last_page": 1,
    "last_page_url": "https://api-partners.didox.uz/v1/profile/productClassCodes/?page=1",
    "next_page_url": null,
    "path": "https://api-partners.didox.uz/v1/profile/productClassCodes/",
    "per_page": 20,
    "prev_page_url": null,
    "to": 1,
    "total": 1
}
```

* * *

# 9. Статус рег.кода плательщика НДС

GET   `/v1/profile/vatRegStatus/{taxId}`

Возвращает статус рег.кода плательщика НДС по ИНН или ПИНФЛ.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`taxId` | ✅ | ИНН (9 цифр) или ПИНФЛ (14 цифр)  
  
**Query-параметры**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`document_date` | `string` | ⬜ | Дата в формате `2021-12-22`. Значения `vatRegCode` и `vatRegStatus` возвращаются по состоянию на эту дату  
`isSeller` | `boolean` | ⬜ | `true` — получить статус для роли продавца. Влияет на результат, см. ниже  
  
**Поля ответа**

Поле | Тип | Описание  
---|---|---  
`status` | `string` | `success` — данные получены, `failed` — получить не удалось  
`vatRegCode` | `string` | Регистрационный код плательщика НДС. `null`, если статус не определён  
`vatRegStatus` | `integer` | Статус сертификата НДС (см. справочник). `null`, если статус не определён  
`vatRegStatusCode` | `string` | Детальный признак состояния из четырёх флагов (см. ниже)  
  
* Статус сертификата НДС
* Детальный признак `vatRegStatusCode`
* Как `isSeller` влияет на результат

Поле `vatRegStatus`.

Код | Статус  
---|---  
20 | Сертификат активный  
21 | Сертификат неактивный  
22 | Сертификат временно приостановлен  
`null` | Рег.код НДС отсутствует либо статус не определён для запрошенной роли  
  
> Не путайте со справочником **типа налогоплательщика** (коды 10, 30, 40, 50, 60) — он используется в методе «Тип налогоплательщика по ИНН или ПИНФЛ».

Строка из четырёх цифр — по одному флагу на позицию, `1` — да, `0` — нет:

Позиция | Флаг | Значение  
---|---|---  
1 | Плательщик НДС | Зарегистрирован как плательщик НДС  
2 | Добросовестный | Отнесён к добросовестным налогоплательщикам  
3 | Активный | Сертификат активен  
4 | Приостановлен | Действие сертификата приостановлено  
  
**Пример:** `1100` — плательщик НДС, добросовестный, сертификат не активен и не приостановлен.

Один и тот же `vatRegStatusCode` даёт разный `vatRegStatus` в зависимости от роли:

`vatRegStatusCode` | Без `isSeller` | С `isSeller=true`  
---|---|---  
`1110` | 20 | 20  
`1010` | `null` | 20  
`1101` | 22 | 22  
`1001` | `null` | 22  
`1100` | `null` | 21  
`1000` | `null` | 21  
прочие | `null` | `null`  
  
> Если запрашиваете статус для стороны **поставщика** , передавайте `isSeller=true` — иначе в части случаев вернётся `null` вместо реального статуса. Когда `vatRegStatus` равен `null`, поле `vatRegCode` также возвращается как `null`.

* cURL
* Ответ `200`
* Ответ `200` (статус не определён)
* Ответ `200` (данные не получены)
```bash
curl "https://api-partners.didox.uz/v1/profile/vatRegStatus/207119963?document_date=2021-12-22&isSeller=true" \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "status": "success",
    "vatRegCode": "326020089828",
    "vatRegStatus": 20,
    "vatRegStatusCode": "1110"
}
```
```json
{
    "status": "success",
    "vatRegCode": null,
    "vatRegStatus": null,
    "vatRegStatusCode": "1100"
}
```
```json
{
    "status": "failed"
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | `taxId` не передан или содержит не 9 и не 14 цифр | `{ "data": null, "error": { "message": "taxId должен содержать либо 9, либо 14 цифр.", "reason": "taxId должен содержать либо 9, либо 14 цифр." } }`  
  
> **Важно.** Если данные получить не удалось, метод возвращает **код`200`** с телом `{ "status": "failed" }`. Всегда проверяйте поле `status`, а не только HTTP-код.

* * *

# 10. Список упаковок по коду ИКПУ

GET   `/v1/profile/{taxId}/productClasses/check/{code}/{lang}`

Возвращает список упаковок (packages) по коду ИКПУ.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`taxId` | ✅ | ИНН пользователя  
`code` | ✅ | Код ИКПУ  
`lang` | ⬜ | Язык результата  
  
> **Важно.** Значение `lang` на результат не влияет — названия упаковок всегда возвращаются на русском языке.

* cURL
* Ответ `200`
```bash
curl https://api-partners.didox.uz/v1/profile/207119963/productClasses/check/08418001001013043/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
[
    {
        "code": "1533212",
        "name": "шт. (потребительская коробка) "
    }
]
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Не удалось получить упаковки | `{ "success": false, "error": "<текст ошибки>" }`  
  
* * *

# 11. Склады по ИНН или ПИНФЛ

GET   `/v1/profile/warehouses/{taxId}`

Возвращает склады по указанному ИНН или ПИНФЛ.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`taxId` | ⬜ | ИНН или ПИНФЛ пользователя. Если не указан — возвращаются склады текущего профиля  
  
* cURL
* Ответ `200`
```bash
curl https://api-partners.didox.uz/v1/profile/warehouses/207119963 \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
[
    {
        "id": 21,
        "warehouseNumber": 51,
        "warehouseName": "warehouseName-1",
        "warehouseAddress": "ул. Кзыл Арват, пр. 1, дом 1-3-5/2"
    },
    {
        "id": 41,
        "warehouseNumber": 57,
        "warehouseName": "warehouseName-57",
        "warehouseAddress": "ул. Нукус, дом 98, кв. 33"
    },
    {
        "id": 61,
        "warehouseNumber": 345,
        "warehouseName": "dfgd test",
        "warehouseAddress": "ул. Кзыл Арват, пр. 1, дом 1-3-5/2"
    }
]
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Не удалось получить склады | `{ "success": false, "error": "Failed to get warehouses" }`  
  
* * *

# 12. Тип налогоплательщика по ИНН или ПИНФЛ

GET   `/v1/profile/taxpayerType/{taxId}/{lang}`

Возвращает тип налогоплательщика по ИНН или ПИНФЛ. Справочник кодов совпадает со справочником из п. 9.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`taxId` | ✅ | ИНН (9 цифр) или ПИНФЛ (14 цифр)  
`lang` | ⬜ | Язык названия: `ru` (по умолчанию) или `uz`  
  
**Query-параметры**

Параметр | Тип | Обяз. | Описание  
---|---|---|---  
`date` | `string` | ⬜ | Дата в формате `17.01.2022`  
  
**Справочник статусов**

Код | Статус  
---|---  
10 | Плательщик НДС  
20 | Плательщик НДС+ (сертификат активный)  
21 | Плательщик НДС+ (сертификат неактивный)  
22 | Плательщик НДС+ (сертификат временно неактивный)  
30 | Плательщик налога с оборота  
40 | Некоммерческое юридическое лицо  
50 | Индивидуальный предприниматель  
60 | Физическое лицо  
  
* cURL
* Ответ `200`
```bash
curl https://api-partners.didox.uz/v1/profile/taxpayerType/207119963/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
    "code": 20,
    "name": "Плательщик НДС+ (сертификат активный)"
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | `taxId` не передан или содержит не 9 и не 14 цифр | `{ "data": null, "error": { "message": "taxId должен содержать либо 9, либо 14 цифр.", "reason": "taxId должен содержать либо 9, либо 14 цифр." } }`  
`500` | Не удалось получить тип налогоплательщика | `{ "success": "false", "reason": "<текст ошибки>", "data": null }`  
  
* * *

# 13. Настройка ролей

PUT   `/v1/profile/company/users`

Проставление ролей НК и Didox сотруднику компании.

**Порядок действий:**

  1. Сформировать JSON с ролями **НК** и подписать его через E-IMZO с прикреплённым timestamp.
  2. Сформировать JSON с ролями **Didox** и подписать его тем же способом.
  3. Передать обе подписи в итоговом запросе.


**Тело итогового запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`gnkpermissions` | `string` (base64) | ✅ | Подпись JSON с ролями НК (`timeStampTokenB64`)  
`internalpermissions` | `string` (base64) | ✅ | Подпись JSON с ролями Didox (`timeStampTokenB64`)  
`is_director` | `integer` | ⬜ | Признак директора: `1` или `0` (по умолчанию `0`)  
  
* Роли НК
* Роли Didox

Код | Наименование  
---|---  
11 | Отправка / отмена ЭСФ  
12 | Подтверждение / отклонение ЭСФ  
21 | Отправка / отмена доверенностей  
22 | Подтверждение / отклонение доверенностей  
41 | Отправка / отмена актов  
42 | Подтверждение / отклонение актов  
51 | Отправка / отмена договоров (НК)  
52 | Подтверждение / отклонение договоров (НК)  
61 | Отправка / отмена актов сверки  
62 | Подтверждение / отклонение актов сверки  
91 | Отправка / отмена актов приема-передачи  
92 | Подтверждение / отклонение актов приема-передачи  
101 | Отправка / отмена ТТН (новый)  
102 | Подтверждение / отклонение ТТН (новый)  
  
Код | Наименование  
---|---  
2 | Подтверждение / отклонение E-POS заявок  
8 | Просмотр E-POS заявок  
18 | Просмотр ЭСФ  
28 | Просмотр доверенностей  
38 | Просмотр ТТН  
48 | Просмотр актов  
49 | Создание актов  
58 | Просмотр договоров  
59 | Создание договоров  
68 | Просмотр актов сверки  
81 | Отправка / отмена произвольных документов  
82 | Подтверждение / отклонение произвольных документов  
88 | Просмотр произвольных документов  
89 | Создание произвольных документов  
108 | Просмотр ТТН (новый)  
111 | Отправка / отмена договора УзБат  
118 | Просмотр договоров УзБат  
119 | Создание договора УзБат  
128 | Просмотр акта Gross  
131 | Отправка / отмена многосторонних произвольных документов  
132 | Подтверждение / отклонение многосторонних произвольных документов  
138 | Просмотр многосторонних произвольных документов  
139 | Создание многосторонних произвольных документов  
151 | Отправка / отмена Протокола собрания учредителей  
152 | Подтверждение / отклонение Протокола собрания учредителей  
158 | Просмотр Протокола собрания учредителей  
159 | Создание Протокола собрания учредителей  
191 | Отправка / отмена заказов  
192 | Подтверждение / отклонение заказов  
198 | Просмотр заказов  
199 | Создание заказов  
  
* Шаг 1 — JSON с ролями НК
* Шаг 2 — JSON с ролями Didox
* Шаг 3 — Итоговый запрос
* Ответ `200`
```json
{
   "tin": "<ИНН компании>",
   "fio": "<ФИО сотрудника>",
   "fiztin": "<ПИНФЛ сотрудника>",
   "roles": [11, 12, 41, 42]
}
```
```json
{
   "tin": "<ИНН компании>",
   "fio": "<ФИО сотрудника>",
   "fiztin": "<ПИНФЛ сотрудника>",
   "roles": [18, 48, 58]
}
```
```json
{
    "gnkpermissions": "<timeStampTokenB64 подписи из Шага 1>",
    "internalpermissions": "<timeStampTokenB64 подписи из Шага 2>",
    "is_director": 0
}
```
```json
{
    "status": "success"
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Не передано поле `gnkpermissions` и/или `internalpermissions` | `{ "gnkpermissions": ["<текст ошибки>"], "internalpermissions": ["<текст ошибки>"] }`  
`422` | Не удалось выдать полномочия | `{ "success": false, "error": "<текст ошибки>" }`
