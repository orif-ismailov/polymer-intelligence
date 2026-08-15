# 10. Шаблоны документов

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-document-template>
> Source last updated: 2026-06-16T06:11:44.614Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена нкобходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

# 1. Список шаблонов договоров

### Тип: _GET_

### Endpoint: `/v1/document-template?size=<integer>&page=<integer>&docType=<string>`

### Краткое описание: Возвращает список созданных шаблонов договоров. Параметры page, size используются для пагинации.

* Headers
* Параметры:
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
size | `<integer>` | Количество результатов на странице  
page | `<integer>` | Номер страницы  
docType | `<string>` | Тип документа. На текущий момент поддерживается только "007" - Договор
```json
{
  "current_page": 1,
  "data": [
    {
      "id": 31,
      "user_tax_id_or_pinfl": "302936161",
      "doctype": "007",
      "name": "Shablonishe ",
      "is_default": 0,
      "created_at": "2022-04-12 13:39:43",
      "updated_at": "2022-04-12 13:39:43"
    },
    {
      "id": 137,
      "user_tax_id_or_pinfl": "302936161",
      "doctype": "007",
      "name": "тест",
      "is_default": 0,
      "created_at": "2022-11-08 15:50:49",
      "updated_at": "2022-11-08 15:50:49"
    },
    {
      "id": 138,
      "user_tax_id_or_pinfl": "302936161",
      "doctype": "007",
      "name": "тест1111",
      "is_default": 0,
      "created_at": "2022-11-08 15:51:19",
      "updated_at": "2022-11-08 15:51:19"
    },
    {
      "id": 140,
      "user_tax_id_or_pinfl": "302936161",
      "doctype": "007",
      "name": "Shablonishe 2",
      "is_default": 0,
      "created_at": "2022-12-03 04:50:29",
      "updated_at": "2022-12-03 04:50:29"
    }
  ],
  "first_page_url": "https://devapi.goodsign.biz/v1/document-template?page=1",
  "from": 1,
  "last_page": 1,
  "last_page_url": "https://devapi.goodsign.biz/v1/document-template?page=1",
  "next_page_url": null,
  "path": "https://devapi.goodsign.biz/v1/document-template",
  "per_page": "20",
  "prev_page_url": null,
  "to": 4,
  "total": 4
}
```  
  
# 2. Получение шаблона договора

### Тип: _GET_

### Endpoint: `/v1/document-template/:id`

### Краткое описание: Возвращает шаблон договора по указанному ID.

* Headers
* Параметры:
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
id | `<integer>` | ID шаблона
```json
{
  "data": {
    "doctype": "007",
    "is_default": 0,
    "name": "Shablonishe ",
    "parts": [
      {
        "id": 627,
        "title": "Test",
        "body": "Test2",
        "ordno": 1
      }
    ],
    "created_at": "2022-04-12 13:39:43",
    "updated_at": "2022-04-12 13:39:43"
  }
}
```  
  
# 3. Создание шаблона договора

### Тип: _POST_

### Endpoint: `/v1/document-template`

### Краткое описание: Создание нового шаблона договора.

* Headers
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
  "doctype": "007",
  "name": "Shablonishe ",
  "parts": [
    {
      "body": "тесттесттест",
      "title": "тесттесттесттесттесттесттесттесттест"
    },
    {
      "body": "тесттесттест",
      "title": "тесттесттесттесттесттесттесттесттест"
    }
  ]
}
```  
  
# 4. Обновление шаблона договора

### Тип: _PUT_

### Endpoint: `/v1/document-template/:id`

### Краткое описание: Обновление существующего шаблона договора по указанному ID.

* Headers
* Параметры:
* Body
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
id | `<integer>` | ID шаблона
```json
{
    "doctype": "007",
    "name": "Шаблон",
    "parts": [
        {
            "body": "тесттесттесттесттесттесттесттесттест",
            "title": "тесттесттест"
        }
    ]
}
```
```json
{}
```  
  
# 5. Удаление шаблона договора

### Тип: _DELETE_

### Endpoint: `/v1/document-template/:id`

### Краткое описание: Удаление шаблона договора по указанному ID.

* Headers
* Параметры:
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
id | `<integer>` | ID шаблона
```json
{}
```
