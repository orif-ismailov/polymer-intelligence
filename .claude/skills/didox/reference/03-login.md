# 03. Логин

> Verbatim mirror of <https://api-docs.didox.uz/ru/home>
> Source last updated: 2026-07-21T06:48:41.384Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена необходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

# Авторизация (получение токена)

Токен пользователя можно получить тремя способами. Во всех запросах обязателен заголовок партнёрской авторизации:
```http
Partner-Authorization: <PARTNER_TOKEN>
```

Способ | Эндпоинт | Когда использовать  
---|---|---  
По ЭЦП | `POST /v1/auth/{taxId}/token/{locale}` | Вход по ключу E-IMZO  
По паролю | `POST /v1/auth/{taxId}/password/{locale}` | Вход без ЭЦП (пароль задан при регистрации)  
Вход в компанию | `POST /v1/auth/company/{companyTaxId}/login/{locale}` | Физлицо входит в компанию по своему токену  
  
> Все токены выдаются в формате **UUID** и действительны **360 минут**.

* * *

# Способ 1 — Токен по ЭЦП

POST   `/v1/auth/{taxId}/token/{locale}`

Последовательность подготовки подписи (через E-IMZO):

  1. [Получить список ключей](https://api-docs.didox.uz/ru/integrators-eimzo#h-1-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B0-%D0%B4%D0%BE%D1%81%D1%82%D1%83%D0%BF%D0%BD%D1%8B%D1%85-%D0%BA%D0%BB%D1%8E%D1%87%D0%B5%D0%B9-%D0%BD%D0%B0-%D0%BB%D0%BE%D0%BA%D0%B0%D0%BB%D1%8C%D0%BD%D0%BE%D0%BC-%D0%B4%D0%B8%D1%81%D0%BA%D0%B5)
  2. [Получить `keyId`](https://api-docs.didox.uz/ru/integrators-eimzo#h-2-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-keyid)
  3. [Создать подпись](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8) — первым аргументом передать ИНН в base64
  4. [Прикрепить timestamp к подписи](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)
  5. Взять из ответа значение `timeStampTokenB64` и передать его в поле `signature`.


**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`taxId` | ✅ | ИНН/ПИНФЛ пользователя  
`locale` | ⬜ | Язык интерфейса: `ru` (по умолчанию) или `uz`  
  
**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подпись с прикреплённым timestamp (`timeStampTokenB64`)  
  
* Запрос
* cURL
* Ответ `200`
```json
{
  "signature": "<timeStampTokenB64>"
}
```
```bash
curl -X POST https://api-partners.didox.uz/v1/auth/{taxId}/token/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{ "signature": "<timeStampTokenB64>" }'
```
```json
{
  "token": "87138df4-9426-49d7-a409-3ed986c49bb5",
  "related_companies": null,
  "related_branches": null
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Пользователь не зарегистрирован | `User not registered`  
`401` | Недействительная подпись | `Unauthorized. Invalid signature`  
  
* * *

# Способ 2 — Токен по паролю

POST   `/v1/auth/{taxId}/password/{locale}`

Вход без ЭЦП по паролю, заданному при регистрации. При входе по ИНН физлица в `related_companies` возвращаются компании, привязанные к нему (ИНН, название, коды полномочий).

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`taxId` | ✅ | ИНН/ПИНФЛ пользователя  
`locale` | ⬜ | Язык интерфейса: `ru` (по умолчанию) или `uz`  
  
**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`password` | `string` | ✅ | Пароль пользователя  
  
* Запрос
* cURL
* Ответ `200`
```json
{
  "password": "<PASSWORD>"
}
```
```bash
curl -X POST https://api-partners.didox.uz/v1/auth/{taxId}/password/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{ "password": "<PASSWORD>" }'
```
```json
{
  "token": "f2782e75-c37b-4b17-bdb9-b53de8b29b89",
  "taxId": "123456789",
  "pinfl": null,
  "name": "OOO EXAMPLE",
  "related_companies": null,
  "related_branches": null
}
```

> **⚠️ Защита от перебора пароля.** Неверные попытки ограничены:  
>  • **3** попытки в минуту → блок на **10 минут**  
>  • **10** попыток → блок на **24 часа**  
>  • **25** попыток → **постоянная** блокировка учётной записи

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Пользователь не зарегистрирован | `User not registered`  
`422` | Неверный пароль | `Incorrect login`  
`423` | Учётная запись заблокирована | `{ "message": "Пользователь заблокирован. Обратитесь в техподдержку" }`  
`429` | Слишком много попыток входа | `{ "message": "Слишком много попыток. Попробуйте через XX минут. YY секунд" }`  
  
* * *

# Способ 3 — Вход в компанию под физлицом

POST   `/v1/auth/company/{companyTaxId}/login/{locale}`

Физическое лицо входит в компанию, используя **свой** токен (полученный Способом 1 или 2). В ответ приходит токен с полномочиями (`permissions`) в этой компании.

**Параметры пути**

Параметр | Обяз. | Описание  
---|---|---  
`companyTaxId` | ✅ | ИНН компании  
`locale` | ⬜ | Язык интерфейса: `ru` (по умолчанию) или `uz`  
  
**Заголовки**

Заголовок | Обяз. | Описание  
---|---|---  
`Partner-Authorization` | ✅ | Партнёрский токен  
`user-key` | ✅ | Токен физлица (из Способа 1 или 2)  
  
**Тело запроса** _(опционально)_

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`branchNum` | `string` | ⬜ | Номер филиала для входа  
  
* cURL
* Ответ `200`
```bash
curl -X POST https://api-partners.didox.uz/v1/auth/company/{companyTaxId}/login/ru \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
  "token": "<token>",
  "permissions": {
    "tin": "<company_tax_id>",
    "roles": [11, 12, 21, 22, 41, 42, 51, 52]
  }
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Компания не зарегистрирована | `Company not registered`  
`422` | Не удалось зарегистрировать компанию | `Failed to register company`  
`401` | Ошибка входа в компанию | `Failed to login in company. Reason: ...`
