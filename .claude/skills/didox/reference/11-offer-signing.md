# 11. Подписание оферты

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-newoffersign>
> Source last updated: 2026-06-16T06:11:58.220Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена нкобходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

## Подписание новой публичной оферты после регистрации

**Для успешного подписания оферты после регистрации необходимо:**

  1. Получить новую публичную оферту
  2. Создать прозвольный документ с прикрепленной новой публичной офертой
  3. Подписать созданный документ


# 1. Получение оферты

### Тип: _GET_

### Endpoint: `/v1/newoffer/base64`

### Краткое описание: Получение новой публичной оферты

* Headers
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
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...
```  
  
# 2. Создание прозвольного документ новой публичной офертой

### Тип: _POST_

### Endpoint: `/v1/documents/offer/create`

### Краткое описание: Создание произвольного документа

* Headers
* Body:
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "document": "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..."
}
```
```json
{
    "pending_document": {
        "document_json": {
            "buyertin": "302936161",
            "doc_type": "000",
            "hash": "9bd740994a98b81c1ad224cf87f3b88c",
            "ip": "218.31.172.64",
            "sellertin": "310529901",
            "seller": {
                "name": "\"Didox Tech\" Mchj",
                "address": "Фидойилар Мфй, Махтумкули Кучаси, 114А-Уй"
            },
            "buyer": {
                "name": "\"VENKON GROUP\" MCHJ",
                "address": "г. Ташкент, ЯШНАБАДСКИЙ РАЙОН, Фидойилар МФЙ, Махтумкули кучаси,  "
            },
            "document": {
                "documentno": "Публичная оферта",
                "documentdate": "2025-11-11"
            },
            "documentid": "e1d2af84bede11f09fe3deb29e51195f",
            "url": "http://0.0.0.0:8001/file/e1d2af84bede11f09fe3deb29e51195f"
        }
    },
    "_id": "e1d2af84bede11f09fe3deb29e51195f",
    "created_date": "2025-11-11 14:14:53"
}
```  
  
# 3. Подписание новой публичной оферты

  1. [Получить список ключей](https://api-docs.didox.uz/ru/integrators-eimzo#h-1-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B0-%D0%B4%D0%BE%D1%81%D1%82%D1%83%D0%BF%D0%BD%D1%8B%D1%85-%D0%BA%D0%BB%D1%8E%D1%87%D0%B5%D0%B9-%D0%BD%D0%B0-%D0%BB%D0%BE%D0%BA%D0%B0%D0%BB%D1%8C%D0%BD%D0%BE%D0%BC-%D0%B4%D0%B8%D1%81%D0%BA%D0%B5)
  2. [Получить keyId](https://api-docs.didox.uz/ru/integrators-eimzo#h-2-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-keyid)
  3. Преобразовать полученный json с 2го шага в base64
  4. [Создать подпись](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8) Первым аргументов передать base64 с 3го шага
  5. [Прикрепить timestamp к подписи](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)
  6. Отправить значение timeStampTokenB64 с респонса 5го шага на эндпоинт


### Тип: _POST_

### Endpoint: `/v1/documents/offer/sign`

### Краткое описание: Подписание оферты

* Headers
* Body:
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "signature": timeStampTokenB64 // значение с 6го шага
}
```
```json
{
    "data": {
        "status": "success"
    }
}
```
