# 02. Регистрация

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-registration>
> Source last updated: 2026-07-20T09:17:31.892Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена необходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

# Регистрация по ключу ЭЦП

Регистрация пользователя состоит из двух шагов:

  1. **Прикрепить timestamp** к подписи ЭЦП → `POST /v1/dsvs/timestamp`
  2. **Зарегистрировать пользователя** с этой подписью → `POST /v1/auth/signup`


> **Аутентификация.** Каждый запрос к API должен содержать заголовок с партнёрским токеном:
```
Partner-Authorization: <PARTNER_TOKEN>
```

* * *

# Шаг 1 — Прикрепить timestamp

Создайте подпись через E-IMZO (см. [«Создание подписи», п. 3](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)), возьмите из ответа `pkcs7_64` и `signature_hex` и отправьте их сюда.

POST   `/v1/dsvs/timestamp`

**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`pkcs7` | `string` | ✅ | Значение `pkcs7_64` из ответа E-IMZO  
`signatureHex` | `string` | ✅ | Значение `signature_hex` из ответа E-IMZO  
  
* Запрос
* cURL
* Ответ `200`
```json
{
  "pkcs7": "<PKCS7_64>",
  "signatureHex": "<SIGNATURE_HEX>"
}
```
```bash
curl -X POST https://api-partners.didox.uz/v1/dsvs/timestamp \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{ "pkcs7": "<PKCS7_64>", "signatureHex": "<SIGNATURE_HEX>" }'
```
```json
{
  "timeStampTokenB64": "MIAGCSqGSIb3DQEHAqCAMIACAQExEDAOBgoqhlwDDwEDAgEB...",
  "success": true,
  "isAttachedPkcs7": true
}
```

> Поле `timeStampTokenB64` — это подпись с прикреплённым timestamp. Её вы передаёте в поле `signature` на Шаге 2.

* * *

# Шаг 2 — Зарегистрировать пользователя

Отправляем данные пользователя вместе с подписью (ИНН/ПИНФЛ, подписанный через E-IMZO с timestamp). В ответ приходит **токен пользователя** (UUID), действительный **360 минут**.

POST   `/v1/auth/signup`

**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`signature` | `string` (base64) | ✅ | Подписанный ИНН/ПИНФЛ с timestamp (результат Шага 1)  
`email` | `string` | ✅ | Email пользователя  
`password` | `string` | ✅ | Пароль для входа без ЭЦП. **Мин. 8 символов** : буквы, цифры и спецсимволы  
`mobile` | `string` | ✅ | Номер телефона  
  
* Запрос
* cURL
* Ответ `200`
```json
{
  "email": "user@example.com",
  "mobile": "998901234567",
  "password": "P@ssw0rd!",
  "signature": "MIAGCSqGSIb3DQEHAqCAMIACAQExEDAOBgoqhlwDDwEDAgEB..."
}
```
```bash
curl -X POST https://api-partners.didox.uz/v1/auth/signup \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "mobile": "998901234567",
    "password": "P@ssw0rd!",
    "signature": "<SIGNATURE_BASE64>"
  }'
```
```json
{
  "token": "9a7ec227-9751-4c5e-98fb-442b3edd1e7f"
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Пользователь уже зарегистрирован | `{ "taxId": ["validation.unique"] }`  
`422` | Пароль не соответствует требованиям или нет обязательных полей | Текст ошибки валидации  
`401` | Недействительная подпись | `Unauthorized. Invalid signature`
