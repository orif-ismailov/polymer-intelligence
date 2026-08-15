# 04. Аккаунт

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-account>
> Source last updated: 2026-07-21T07:00:12.890Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена необходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

# Аккаунт

Методы для чтения и изменения данных текущего профиля. Оба запроса требуют двух заголовков:

Заголовок | Описание  
---|---  
`Partner-Authorization` | Партнёрский токен  
`user-key` | Токен пользователя (см. раздел «Авторизация»)  
  
Метод | Эндпоинт | Назначение  
---|---|---  
Получить аккаунт | `GET /v1/account` | Данные текущего аккаунта  
Обновить аккаунт | `POST /v1/account/update` | Изменение данных аккаунта  
  
* * *

# Получение данных аккаунта

GET   `/v1/account`

Возвращает данные текущего аккаунта.

* cURL
* Ответ `200`
```bash
curl https://api-partners.didox.uz/v1/account \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>"
```
```json
{
  "mobile": "998933800525",
  "email": "info@venkon.uz",
  "notifications": 0,
  "messengers": []
}
```

**Поля ответа**

Поле | Тип | Описание  
---|---|---  
`mobile` | `string` | Номер телефона  
`email` | `string` | Email  
`notifications` | `integer` | Уведомления: `1` — включены, `0` — выключены  
`messengers` | `array` | Привязанные мессенджеры  
  
* * *

# Изменение данных аккаунта

POST   `/v1/account/update`

Обновляет данные текущего профиля.

**Тело запроса**

Поле | Тип | Обяз. | Описание  
---|---|---|---  
`mobile` | `string` | ⬜ | Номер телефона  
`email` | `string` | ⬜ | Email  
`password` | `string` | ⬜ | Новый пароль  
`notifications` | `integer` | ⬜ | Уведомления: `1` — включить, `0` — выключить  
  
* Запрос
* cURL
* Ответ `200`
```json
{
  "mobile": "<mobile_number>",
  "email": "<email>",
  "password": "<new_password>",
  "notifications": 1
}
```
```bash
curl -X POST https://api-partners.didox.uz/v1/account/update \
  -H "Partner-Authorization: <PARTNER_TOKEN>" \
  -H "user-key: <USER_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{ "mobile": "<mobile_number>", "email": "<email>", "notifications": 1 }'
```
```json
{
  "mobile": "<mobile_number>",
  "email": "<email>",
  "notifications": 1,
  "password": "<new_password>"
}
```

## Возможные ошибки

Код | Причина | Тело ответа  
---|---|---  
`422` | Не удалось обновить аккунт | `{ "success": false, "error": "Account not updated" }`
