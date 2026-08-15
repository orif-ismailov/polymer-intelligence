# 01. Работа с E-IMZO

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-eimzo>
> Source last updated: 2026-07-03T12:56:27.856Z

---

> Для корректной интеграции необходимо установить и запустить приложение E-IMZO (<https://e-imzo.uz/>)  
>  При установленном E-IMZO доступна документация по адресу <https://127.0.0.1:64443/apidoc.html>

# E-IMZO (ЭЦП ключ .pfx)

## 1. Получение списка доступных ключей на локальном диске

Для получения списка доступных ключей на локальном диске необходимо:

  1. Установить соединение к веб-сокету wss://127.0.0.1:64443/service/cryptapi


Headers:
```
Host:127.0.0.1:64443
Origin:https://{your web site}
```

  2. В установленном соединении отправить сообщение:


```json
{
    "plugin":"pfx",
    "name":"list_all_certificates"
}
```

Получаем ответ:
```json
{
    "certificates": [
        {
            "disk": "C:\\",
            "path": "",
            "name": "DS242141224",
            "alias": "cn=fio,name=имя,surname=фамилия,l=район,st=город,c=uz,o=название компании,uid=324543543,1.2.860.3.16.1.2=32610793225581,t=direktor,1.2.860.3.16.1.1=242141224,businesscategory=masʼuliyati cheklangan jamiyat,serialnumber=71c4eb12,validfrom=2022.04.25 17:42:58,validto=2024.04.25 23:59:59"
        }
    ],
    "success": true
}
```

## 2. Получение keyId

Для получения ID ключа необходимо:

  1. Установить соединение к веб-сокету wss://127.0.0.1:64443/service/cryptapi  
Headers:


```
Host:127.0.0.1:64443
Origin:https://{your web site}
```

  2. Получить список ключей ([Первый пункт на странице](https://api-docs.didox.uz/ru/integrators-eimzo#h-1-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B0-%D0%B4%D0%BE%D1%81%D1%82%D1%83%D0%BF%D0%BD%D1%8B%D1%85-%D0%BA%D0%BB%D1%8E%D1%87%D0%B5%D0%B9-%D0%BD%D0%B0-%D0%BB%D0%BE%D0%BA%D0%B0%D0%BB%D1%8C%D0%BD%D0%BE%D0%BC-%D0%B4%D0%B8%D1%81%D0%BA%D0%B5))
  3. Отправить сообщение, в arguments передавать массив из значений ключа, полученные в списке ключей


```json
{
    "plugin": "pfx",
    "name": "load_key",
    "arguments": [
        "C:\\", // значение disk
        "", // значение path 
        "DS242141224", // значение name
        "cn=fio,name=имя,surname=фамилия,l=район,st=город,c=uz,o=название компании,uid=324543543,1.2.860.3.16.1.2=32610793225581,t=direktor,1.2.860.3.16.1.1=242141224,businesscategory=masʼuliyati cheklangan jamiyat,serialnumber=71c4eb12,validfrom=2022.04.25 17:42:58,validto=2024.04.25 23:59:59" // значение alias
    ]
}
```

Получаем ответ:
```json
{
    "keyId": "4523456aec67ds568234f9500d151222",
    "type": "PFX_KEY_STORE",
    "success": true
}
```

## 3. Создание подписи

Для создания подписи необходимо:

  1. Установить соединение к веб-сокету wss://127.0.0.1:64443/service/cryptapi  
Headers:


```
Host:127.0.0.1:64443
Origin:https://{your web site}
```

  2. Получить keyId ([Второй пункт на странице](https://api-docs.didox.uz/ru/integrators-eimzo#h-2-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-keyid))
  3. Отправить сообщение, в arguments передавать массив значений:  
a. Данные для подписи в base64  
b. keyId // полученный во втором шаге  
с. "no"


```json
{
    "plugin": "pkcs7",
    "name": "create_pkcs7",
    "arguments": [
        "MjA3MTE5OTYz", // JSON документа или инн в base64
        "4523456aec67ds568234f9500d151222", // keyId
        "no"
    ]
}
```

Получаем ответ:
```json
{
    "pkcs7_64": "MIAGCSqGSIb3DQEHAqCAMI...",
    "signer_serial_number": "7283d8ca",
    "signature_hex": "5b1433b23cddfd877d4a6ef4d7715d4f98c39d90c16d12340f23dbefff68ad75bdb922740ced53d45670dd8f73e1d0334cd689ed014d0bcd49798c017c98b80c",
    "success": true
}
```

## 4. Прикрепление timestamp к подписи

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена нкобходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

  1. Создать подпись ([Третий пункт на странице](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8))
  2. В полученном ответе взять значения pkcs7_64 и signature_hex
  3. Отправить значения в /v1/dsvs/timestamp  
Body:


```json
{
  "pkcs7": pkcs7_64 // Значение поля pkcs7_64
  "signatureHex": signature_hex // Значение поля signature_hex
}
```

Получаем ответ:
```json
{
    "timeStampTokenB64": "MIAGCSqGSIb3DQEHAqEQG5ojtL3W8Ir4Qc17fInWcTykUVTxTYNHgwJH9HqMyVF+ioItlTSF9J+oiurr...",
    "success": true,
    "isAttachedPkcs7": true
}
```

# Шаги (ЭЦП ключ .pfx):

## 1. Логин под компанией по ЭЦП

  1. [Получить список ключей](https://api-docs.didox.uz/ru/integrators-eimzo#h-1-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B0-%D0%B4%D0%BE%D1%81%D1%82%D1%83%D0%BF%D0%BD%D1%8B%D1%85-%D0%BA%D0%BB%D1%8E%D1%87%D0%B5%D0%B9-%D0%BD%D0%B0-%D0%BB%D0%BE%D0%BA%D0%B0%D0%BB%D1%8C%D0%BD%D0%BE%D0%BC-%D0%B4%D0%B8%D1%81%D0%BA%D0%B5)
  2. [Получить keyId](https://api-docs.didox.uz/ru/integrators-eimzo#h-2-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-keyid)
  3. [Создать подпись](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)  
Первым аргументов передать инн в base64
  4. [Прикрепить timestamp к подписи](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)
  5. Получить значение timeStampTokenB64 с респонса 4го шага
  6. Отправить значение timeStampTokenB64 на эндпоинт POST /v1/auth/ИНН_КОМПАНИИ/token/ru  
Body:


```json
{
    "signature": timeStampTokenB64 // значение с 5го шага
}
```

### Пример получение данных:

### Response : _200_
```json
{
    "token": "87138df4-9426-49d7-a409-3ed986c49bb5",
    "related_companies": null,
    "related_branches": null
}
```

## 2. Подписание исходящего документа

  1. [Получить список ключей](https://api-docs.didox.uz/ru/integrators-eimzo#h-1-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B0-%D0%B4%D0%BE%D1%81%D1%82%D1%83%D0%BF%D0%BD%D1%8B%D1%85-%D0%BA%D0%BB%D1%8E%D1%87%D0%B5%D0%B9-%D0%BD%D0%B0-%D0%BB%D0%BE%D0%BA%D0%B0%D0%BB%D1%8C%D0%BD%D0%BE%D0%BC-%D0%B4%D0%B8%D1%81%D0%BA%D0%B5)
  2. [Получить keyId](https://api-docs.didox.uz/ru/integrators-eimzo#h-2-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-keyid)
  3. Получить значение data->json с респонса GET /v1/documents/айди_документа?owner=1
  4. Преобразовать data->json с 3го шага в base64
  5. [Создать подпись](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)  
Первым аргументов передать base64 с 4го шага
  6. [Прикрепить timestamp к подписи](https://api-docs.didox.uz/ru/integrators-eimzo#h-4-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)
  7. Получить значение timeStampTokenB64 с респонса 6го шага
  8. Отправить значение timeStampTokenB64 на эндпоинт POST /v1/documents/айди_документа/sign  
Body:


```json
{
    "signature": timeStampTokenB64 // значение с 7го шага
}
```

### Пример получение данных:

### Response : _200_
```json
{
    "data": true
}
```

# E-IMZO (USB токен)

> Для корректной работы необходимо подключить USB токен к компьютеру

## 1. Получение списка доступных USB токенов

Для получения списка доступных USB токенов необходимо:

  1. Установить соединение к веб-сокету wss://127.0.0.1:64443/service/cryptapi


Headers:
```
Host:127.0.0.1:64443
Origin:https://{your web site}
```

  2. В установленном соединении отправить сообщение:


```json
{
    "plugin": "ckc",
    "name": "list_ckc"
}
```

Получаем ответ:
```json
{
  "devices": [
    {
      "type": "EIMZO",
      "deviceID": "FeiTian Ltd JavaCard Token V1.0 0"
    }
  ],
  "success": true,
  "status": 1
}
```

## 2. Создание подписи

Для создания подписи необходимо:

  1. Установить соединение к веб-сокету wss://127.0.0.1:64443/service/cryptapi  
Headers:


```
Host:127.0.0.1:64443
Origin:https://{your web site}
```

  2. Отправить сообщение


```json
{
    "plugin": "pkcs7",
    "name": "create_pkcs7",
    "arguments": [
        "MjA3MTE5OTYz", // Данные в base64
        "ckc",
        "no"
    ]
}
```

Получаем ответ:
```json
{
    "pkcs7_64": "MIAGCS...",
    "signer_serial_number": "78fc0c10",
    "signature_hex": "909899b066ba948d049a4e174bb41dc1f3436c74dab386844938c781015d1aa5375395ba3f8ced7a2d06f78919881d5e50408a730fd977e8f5564435cc0c065b",
    "success": true,
    "status": 1
}
```

## 3. Прикрепление timestamp к подписи

  1. После создания подписи, в полученном ответе взять значения pkcs7_64 и signature_hex
  2. Отправить значения в /v1/dsvs/timestamp  
Body:


```json
{
  "pkcs7": pkcs7_64 // Значение поля pkcs7_64
  "signatureHex": signature_hex // Значение поля signature_hex
}
```

Получаем ответ:
```json
{
    "timeStampTokenB64": "MIAGCSqGSIb3DQEHAqEQG5ojtL3W8Ir4Qc17fInWcTykUVTxTYNHgwJH9HqMyVF+ioItlTSF9J+oiurr...",
    "success": true,
    "isAttachedPkcs7": true
}
```

# Шаги (USB токен):

## 1. Логин под компанией по USB токен

  1. [Получить список USB токенов](https://api-docs.didox.uz/ru/integrators-eimzo#h-1-%D0%BF%D0%BE%D0%BB%D1%83%D1%87%D0%B5%D0%BD%D0%B8%D0%B5-%D1%81%D0%BF%D0%B8%D1%81%D0%BA%D0%B0-%D0%B4%D0%BE%D1%81%D1%82%D1%83%D0%BF%D0%BD%D1%8B%D1%85-usb-%D1%82%D0%BE%D0%BA%D0%B5%D0%BD%D0%BE%D0%B2)
  2. [Создать подпись](https://api-docs.didox.uz/ru/integrators-eimzo#h-2-%D1%81%D0%BE%D0%B7%D0%B4%D0%B0%D0%BD%D0%B8%D0%B5-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)  
Первым аргументов передать инн в base64
  3. [Прикрепить timestamp к подписи](https://api-docs.didox.uz/ru/integrators-eimzo#h-3-%D0%BF%D1%80%D0%B8%D0%BA%D1%80%D0%B5%D0%BF%D0%BB%D0%B5%D0%BD%D0%B8%D0%B5-timestamp-%D0%BA-%D0%BF%D0%BE%D0%B4%D0%BF%D0%B8%D1%81%D0%B8)
  4. Получить значение timeStampTokenB64 с респонса 4го шага
  5. Отправить значение timeStampTokenB64 на эндпоинт POST /v1/auth/ИНН_КОМПАНИИ/token/ru  
Body:


```json
{
    "signature": timeStampTokenB64 // значение с 5го шага
}
```

### Пример получение данных:

### Response : _200_
```json
{
    "token": "87138df4-9426-49d7-a409-3ed986c49bb5",
    "related_companies": null,
    "related_branches": null
}
```
