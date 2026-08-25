# 08. Утилиты

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-utils>
> Source last updated: 2026-08-18T12:00:17.323Z

---

> Чтобы использовать API необходимо получить партнерский токен  
>  Тестовая URL <https://testapi3.didox.uz/>  
>  Прод партнерский URL <https://api-partners.didox.uz/>

> Для получения партнеского токена нкобходимо обратиться к Аккаунт менеджеру:  
>  <https://t.me/Didox_account> ; +998 50 122 05 18  
>  Канал по изменениям и обновлениям в API Didox:  
>  <https://t.me/didoxapiupdates>

# 1. Список товаров (услуг) без НДС

### Тип: _GET_

### Endpoint: `/v1/utils/without-vat-products/:lang`

### Краткое описание: Возвращает список товаров (услуг) без НДС.

* Headers
* Параметры
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
page | - | Порядковый номер страницы (начинается с 1)  
size | - | Количество товаров на одной странице (максимум 1000)  
LgotaName | lgota | Наименование льготы  
newLgotaId | lgota | Код льготы по НДС (новый)  
TasnifCode | code | Код ИКПУ в [tasnif.soliq.uz](<http://tasnif.soliq.uz>)  
TasnifName | name | Наименование кода ИКПУ в [tasnif.soliq.uz](<http://tasnif.soliq.uz>)  
lang | ru\uz | (Required) Язык (ru - русский; uz - узбекский)
```json
{
    "rows": [
        {
            "catalogCode": "03004110005011002",
            "catalogName": "Темир, парентерал препаратлар (Темир препаратлари) -B03AC",
            "lgotaId": 7531,
            "newLgotaId": 102870,
            "lgotaName": "(ст.243 НК) пункт 13. лекарственных средств, ветеринарных лекарственных средств, изделий медицинского и ветеринарного назначения;",
            "dateBegin": "2020-01-01 00:00:00",
            "dateEnd": "2029-12-31 00:00:00"
        }
    ],
    "totalCount": 1
}
```  
  
# 2. Список товаров (услуг) (НДС 0%)

### Тип: _GET_

### Endpoint: `/v1/utils/zero-vat-products/:lang`

### Краткое описание: Возвращает список организаций, реализующих товары (услуги) без НДС

* Headers
* Параметры
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
page | - | Порядковый номер страницы (начинается с 1)  
size | - | Количество товаров на одной странице (максимум 1000)  
LgotaName | lgota | Наименование льготы  
newLgotaId | lgota | Код льготы по НДС (новый)  
TasnifCode | code | Код ИКПУ в [tasnif.soliq.uz](<http://tasnif.soliq.uz>)  
TasnifName | name | Наименование кода ИКПУ в [tasnif.soliq.uz](<http://tasnif.soliq.uz>)  
lang | ru\uz | (Required) Язык (ru - русский; uz - узбекский)
```json
{
    "rows": [
        {
            "catalogCode": "03004110005011002",
            "catalogName": "Темир, парентерал препаратлар (Темир препаратлари) -B03AC",
            "lgotaId": 7531,
            "newLgotaId": 102870,
            "lgotaName": "(ст.243 НК) пункт 13. лекарственных средств, ветеринарных лекарственных средств, изделий медицинского и ветеринарного назначения;",
            "dateBegin": "2020-01-01 00:00:00",
            "dateEnd": "2029-12-31 00:00:00"
        }
    ],
    "totalCount": 1
}
```  
  
# 3. Список организаций, реализующие без НДС (или 0%)

### Тип: _GET_

### Endpoint: `/v1/utils/privileged-seller-companies/:lang`

### Краткое описание: Возвращает список организаций, реализующие без НДС (или 0%).

* Headers
* Параметры
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
page | - | Порядковый номер страницы (начинается с 1)  
size | - | Количество товаров на одной странице (максимум 1000)  
Tin | - | ИНН или ПИНФЛ  
LgotaName | name | Название льготы  
newLgotaId | lgota | Код льготы по НДС (новый)  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)  
name | name | Название организации
```json
{
    "rows": [
        {
            "tin": "201513558",
            "name": "\"O`ZBEKISTON RESPUBLIKASI DAVLAT AKTIVLARINI BOSHQARISH AGE",
            "lgotaId": 126,
            "newLgotaId": 100261,
            "lgotaName": "ПКМ-414 от 03.09.1999 г.Пункт 4. Освободить с 1 января 2000 года до 1 января 2027 года бюджетные органзации, получающие дополнительные доходы от всех видов налогов взимаемых в бюджет.",
            "dateBegin": "2000-01-01T00:00:00",
            "dateEnd": "2026-12-31T00:00:00"
        },
        {
            "tin": "201513558",
            "name": "\"O`ZBEKISTON RESPUBLIKASI DAVLAT AKTIVLARINI BOSHQARISH AGE",
            "lgotaId": null,
            "newLgotaId": 104109,
            "lgotaName": "(ст. 483 НК) ч 38.  Освободить до 1 января 2024 года бюджетные органзации, получающие дополнительные доходы от всех видов налогов (кроме Соц.Нал.) взимаемых в бюджет. ",
            "dateBegin": "2023-01-01T00:00:00",
            "dateEnd": "2023-12-31T00:00:00"
        }
    ],
    "totalCount": 2
}
```  
  
# 4. Список организаций, приобретающие без НДС (или 0%)

### Тип: _GET_

### Endpoint: `/v1/utils/privileged-buyer-companies/:lang`

### Краткое описание: Возвращает список товаров (услуг), оказывающихся по ставке НДС 0%.

* Headers
* Параметры
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
page | - | Порядковый номер страницы (начинается с 1)  
size | - | Количество товаров на одной странице (максимум 1000)  
Tin | - | ИНН или ПИНФЛ  
LgotaName | name | Название льготы  
newLgotaId | lgota | Код льготы по НДС (новый)  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)  
name | name | Название организации
```json
{
    "rows": [
        {
            "tin": "205529921",
            "name": "SOS O'ZBEKISTON BOLALAR MAHALLALARI UTSHF",
            "lgotaId": 7349,
            "newLgotaId": 103935,
            "lgotaName": "ПКМ-585 от 31.12.1997 г. Пункт 3. Б) 1 часть  предоставить Международному обществу «SOS — Киндердорф Интернешнл» и Ассоциации «SOS — Детские деревни Узбекистана» льготы, которые предоставляются всем другим общественным и благотворительным организациям, действующим на территории Республики Узбекистан;",
            "dateBegin": "1997-12-31T00:00:00",
            "dateEnd": "2026-12-31T00:00:00"
        }
    ],
    "totalCount": 1
}
```  
  
# 5.Список товаров, не относимых в зачёт

### Тип: _GET_

### Endpoint: `/v1/utils/not-included-products/:lang`

### Краткое описание: Возвращает список товаров, не относимых в зачёт.

* Headers
* Параметры
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
page |  | Порядковый номер страницы (начинается с 1)  
size |  | Количество товаров на одной странице (максимум 1000)  
SearchText |  | Название ИКПУ
```json
{
    "rows": [
        {
            "catalogCode": "02203001001025006",
            "catalogName": "Pivo CRAFT LAGER ok pasterizatsiyalangan zichligi 12,5% alk 4.6, Shisha butilka  0,5 litr"
        }
    ],
    "totalCount": 1
}
```  
  
# 6. Список услуг по возмещению

### Тип: _GET_

### Endpoint: `/v1/utils/compensation-works/:lang`

### Краткое описание: Возвращает список услуг по возмещению.

* Headers
* Параметры
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
page |  | Порядковый номер страницы (начинается с 1)  
size |  | Количество товаров на одной странице (максимум 1000)  
SearchText |  | Название ИКПУ  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)
```json
{
    "rows": [
        {
            "catalogCode": "02203001001025006",
            "catalogName": "Pivo CRAFT LAGER ok pasterizatsiyalangan zichligi 12,5% alk 4.6, Shisha butilka  0,5 litr"
        }
    ],
    "totalCount": 1
}
```  
  
# 7. Список предприятий с выявленными несоответствиями в товарах

### Тип: _GET_

### Endpoint: `/v1/utils/non-conformity-goods-companies/:lang`

### Краткое описание: Возвращает список предприятий с выявленными несоответствиями в товарах.

* Headers
* Параметры
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
page |  | Порядковый номер страницы (начинается с 1)  
size |  | Количество товаров на одной странице (максимум 1000)  
tin |  | ИНН  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)
```json
[
    {
        "tin": "304965204",
        "name": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"OMAD-FAYZ\"",
        "dateOper": "2022-04-22T00:00:00"
    }
]
```  
  
# 8. Список льгот по НДС у товаров/услуг

### Тип: _POST_

### Endpoint: `v1/utils/product-privileges/:lang?checkDate=`

### Краткое описание: Проверяет, имеют ли товары/услуги льготы по НДС. Параметр checkDate (дата проверки) передается в формате yyyy-MM-dd.

* Headers
* Параметры
* Body:
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
checkDate |  | Format: yyyy-MM-dd  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)
```json
[
   "02402001001008004",
   "09901001002000000"
]
```
```json
{
    "09901001002000000": {
        "withoutVat": [],
        "zeroVat": [
            {
                "lgotaId": 103317,
                "lgotaName": "(ст.264 НК) ч. 3. Оборот по реализации услуг, оказываемых населению по водоснабжению, канализации, санитарной очистке, теплоснабжению, включая приобретение таких услуг товариществами собственников жилья от лица населения, а также подразделениями Министерства обороны Республики Узбекистан и Национальной гвардии Республики Узбекистан для населения, проживающего в домах ведомственного жилищного фонда, облагаются налогом по нулевой ставке."
            }
        ],
        "notIncludedProduct": false,
        "compensationWork": false
    },
    "02402001001008004": {
        "withoutVat": [],
        "zeroVat": [],
        "notIncludedProduct": false,
        "compensationWork": false
    }
}
```  
  
# 9. Список льгот по НДС для организаций Плательщиков НДС

### Тип: _POST_

### Endpoint: `v1/utils/company-privileges/:lang?checkDate=`

### Краткое описание: Проверяет, имеет ли компания льготы по НДС. Параметр checkDate (дата проверки) передается в формате yyyy-MM-dd.

* Headers
* Параметры
* Body:
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
checkDate |  | Format: yyyy-MM-dd  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)
```json
[
  "302936161"
]
```
```json
{
    "302936161": {
        "sellerWithoutVat": [
            {
                "lgotaId": 102387,
                "lgotaName": "УП-5099 от 30.06.2017 г пункт 5 абзац 2 Освободить сроком до 1 января 2028 года резидентов Инновационного центра от уплаты всех видов налогов и обязательных отчислений в государсвенные целевые фонды, а текже единого социального платежа.",
                "buyerTins": null,
                "catalogCodes": [
                    "08523001014000000"
                ]
            },
            {
                "lgotaId": 104084,
                "lgotaName": "ПП-357 22.08.2022 г. п.14 Определить, что льготы по налогу на добавленную стоимость, предусмотренные абзацем вторым пункта 5 Указа Президента Республики Узбекистан от 30 июня 2017 года № УП-5099 «О мерах по коренному улучшению условий для развития отрасли информационных технологий в республике» применяются также при приобретении услуг в сфере информационных технологий у нерезидентов республики.",
                "buyerTins": null,
                "catalogCodes": null
            }
        ],
        "sellerZeroVat": [],
        "buyerWithoutVat": [],
        "buyerZeroVat": []
    }
}
```  
  
### Response : _405_

# 10. Список льгот по НДС для организаций Налог с оборота

### Тип: _POST_

### Endpoint: `v1/utils/companies-privileges/:lang`

### Краткое описание: Проверяет, имеют ли компания льготы по НДС. Параметр checkDate (дата проверки) передается в формате yyyy-MM-dd.

* Headers
* Параметры
* Body:
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
checkDate |  | Format: yyyy-MM-dd  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)
```json
{
    "check_date": "2025-07-02",
    "tax_ids_or_pinfls": [
        "308294697"
    ]
}
```
```json
{
    "308294697": [
        {
            "lgotaId": 102385,
            "lgotaName": "УП-5099 от 30.06.2017 г пункт 5 абзац 2 Освободить сроком до 1 января 2028 года резидентов Инновационного центра от уплаты всех видов налогов и обязательных отчислений в государсвенные целевые фонды, а текже единого социального платежа.",
            "buyerTins": null,
            "catalogCodes": [
                "08523001014000000"
            ]
        }
    ]
}
```  
  
# 11. Список видов дохода

### Тип: _GET_

### Endpoint: `/v1/utils/income-types/:lang`

### Краткое описание: Возвращает список видов дохода.

* Headers
* Параметры
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)
```json
[
    {
        "code": 1,
        "name": "Стоимость переданных товаров (услуг) участнику при его выходе из состава участников или при уменьшении доли участия, либо выкупе юридическим лицом у участника доли участия"
    },
    {
        "code": 2,
        "name": "Стоимость переданных товаров (услуг) акционеру при выкупе юридическим лицом, также при ликвидации юридического лица - эмитентом у акционера акций, выпущенных этим эмитентом"
    },
    {
        "code": 3,
        "name": "Передача товаров (услуг) в счёт оплаты труда физических лиц или выплаты дивидендов"
    },
    {
        "code": 4,
        "name": "Передача товаров и иного имущества на давальческой основе"
    },
    {
        "code": 5,
        "name": "Стоимость ваучеров, предоставляющих право на получение реализованных или безвозмездно переданных товаров (услуг)"
    },
    {
        "code": 6,
        "name": "Стоимость реализованных основных средств и другого имущества"
    },
    {
        "code": 7,
        "name": "Доходы от продажи предприятия как имущественного комплекса"
    }
]
```  
  
# 12. Список прочих видов доходов

### Тип: _GET_

### Endpoint: `/v1/utils/other-income-product-classes/:lang`

### Краткое описание: Возвращает список прочих видов доходов.

* Headers
* Параметры
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
lang | ru/uz | (Required) Язык (ru - русский; uz - узбекский)
```json
[
    {
        "code": "11801001001000000",
        "name": "Доходы по долгосрочным контрактам"
    },
    {
        "code": "11801001002000000",
        "name": "Доходы по операциям РЕПО"
    },
    {
        "code": "11801001003000000",
        "name": "Доходы по операциям ценных бумаг и (или) финансовым инструментам срочных сделок"
    },
    {
        "code": "11801001004000000",
        "name": "Доходы от выбытия основных средств и иного имущества"
    },
    {
        "code": "11801001005000000",
        "name": "Безвозмездно полученное имущество (полученные услуги)"
    },
    {
        "code": "11801001006000000",
        "name": "Доходы в виде стоимости излишков товарно-материальных запасов и прочего имущества, выявленных в результате инвентаризации"
    },
    {
        "code": "11801001007000000",
        "name": "Доходы от списания обязательств в порядке, установленном законодательством"
    },
    {
        "code": "11801001008000000",
        "name": "Доходы, полученные по договору уступки права требования"
    },
    {
        "code": "11801001009000000",
        "name": "Доходы в виде возмещения ранее вычтенных расходов или убытков"
    },
    {
        "code": "11801001010000000",
        "name": "Штрафы, пени и иные санкции за нарушение договорных обязательств, а также суммы возмещения убытков (ущерба)"
    },
    {
        "code": "11801001011000000",
        "name": "Превышение положительной курсовой разницы над отрицательной по валютным счетам"
    },
    {
        "code": "11801001012000000",
        "name": "Суммы восстановленных расходов"
    },
    {
        "code": "11801001013000000",
        "name": "Доходы, полученные в связи с уменьшением уставного фонда (уставного капитала) юридического лица, в случае отказа акционера, участника от получения стоимости своей доли (части доли) в пользу этого юридического лица"
    },
    {
        "code": "11801001014000000",
        "name": "Доходы в виде прибыли контролируемой иностранной компании в случаях и в порядке, установленных разделом VII Налогового кодекса"
    },
    {
        "code": "11801001015000000",
        "name": "Дивиденды"
    },
    {
        "code": "11801001016000000",
        "name": "Проценты"
    },
    {
        "code": "11801001017000000",
        "name": "Прочие доходы"
    }
]
```  
  
# 13. Список всех ж/д станций

### Тип: _GET_

### Endpoint: `v1/utils/stations`

### Краткое описание: Возвращает список всех ж/д станций.

* Headers
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
[
    {
        "stationId": "721501",
        "name": "ЧИPЧИK"
    },
    {
        "stationId": "721605",
        "name": "APAHЧИ"
    },
    {
        "stationId": "731503",
        "name": "KAHИMEX"
    },
    {
        "stationId": "725907",
        "name": "ШAPK"
    },
    {
        "stationId": "726100",
        "name": "БEKAБAД"
    }
]
```  
  
# 14. Информация о конкретной ж/д станции

### Тип: _GET_

### Endpoint: `v1/utils/stations/:stationId`

### Краткое описание: Возвращает информации о конкретной ж/д станции.

* Headers
* Параметры
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение | Описание  
---|---|---  
stationid | id | ID станции
```json
{
    "stationId": "721501",
    "name": "ЧИPЧИK"
}
```  
  
# 15. Информация по транспорту

### Тип: _GET_

### Endpoint: `/v1/utils/waybills/transport?tinOrPinfl=ИНН`

### Краткое описание: Возвращает список транспорта по ИНН/ПИНФЛ

* Headers
* Параметры
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение  
---|---  
tinOrPinfl | ИНН организации
```json
[
    {
        "regNo": "01 X xxx XX",
        "model": "MATIZ",
        "ownershipType": 1,
        "transportType": 2
    }
]
```  
  
# 16. Информация по ИНН/ПИНФЛ

### Тип: _GET_

### Endpoint: `/v1/utils/info/{TinOrPinfl}`

### Краткое описание: Возвращает информацию по ИНН или ПИНФЛ пользователя

* Headers
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "ns10Code": 26,
    "ns11Code": 8,
    "shortName": "\"DIDOX TECH\" MCHJ",
    "tin": "310529901",
    "name": "\"DIDOX TECH\" MAS'ULIYATI CHEKLANGAN JAMIYAT",
    "regDate": "01.06.2023",
    "na1Code": 12,
    "na1Name": "Общество с огр. ответствен.",
    "statusCode": 0,
    "statusName": "Действующие и имеющие налоговые обязательства",
    "mfo": "00401",
    "account": "20208000905656222001",
    "address": "Фидойилар МФЙ, Махтумкули кучаси, 114а-уй  ",
    "oked": "62090",
    "directorTin": "494899720",
    "directorPinfl": "32901930460050",
    "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
    "accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
    "isBudget": 0,
    "isItd": false,
    "personalNum": null,
    "selfEmployment": false,
    "privateNotary": false,
    "peasantFarm": false,
    "VATRegCode": "326080220838",
    "VATRegStatus": 20,
    "bankAccount": "20208000905656222001",
    "bankCode": "00401",
    "shortname": "\"DIDOX TECH\" MCHJ",
    "fullname": "\"DIDOX TECH\" MAS'ULIYATI CHEKLANGAN JAMIYAT",
    "fullName": "\"DIDOX TECH\" MAS'ULIYATI CHEKLANGAN JAMIYAT"
}
```  
  
# 17. Информация по областям

### Тип: _GET_

### Endpoint: `/v1/utils/waybills/regions`

### Краткое описание: Возвращает информацию по областям

* Headers
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
[
    {
        "code": 1730,
        "name": "Fergana region",
        "nameUzCyrl": "Фарғона вилояти",
        "nameUzLatn": "Farg'ona viloyati",
        "nameRu": "Ферганская область",
        "regionId": 30,
        "districtCode": 0,
        "active": 1
    }
]
```  
  
# 18. Информация по районам

### Тип: _GET_

### Endpoint: `/v1/utils/waybills/districts?regionId={regionId}`

### Краткое описание: Возвращает информацию по районам

* Headers
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
[
    {
        "soato": 1730230,
        "name": "Uzbekistan region",
        "nameUzCyrl": "Ўзбекистон тумани",
        "nameUzLatn": "O'zbekiston tumani",
        "nameRu": "Узбекистанский район",
        "regionId": 30,
        "districtCode": 17,
        "active": 1
    }
]
```  
  
# 19. Получения данных ТТН по ЖД ID

### Тип: _GET_

### Endpoint: `/v1/utils/waybills/railwaydoc?railwayDocId=123123`

### Краткое описание: Возвращает информацию ТТН по ЖД ID

* Headers
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "railwayDocId": 123123,
    "waybillNo": "AA 715877",
    "ducumentCreatedDate": "2022-05-20T00:00:00Z",
    "consignor": {
        "tinOrPinfl": "311952123",
        "name": "OLMALIQ AKSIYADORLIK JAMIYATI"
    },
    "consignee": {
        "tinOrPinfl": "201514314",
        "name": "test name"
    },
    "carrier": {
        "tinOrPinfl": "201051951",
        "name": "TEMIR YO`LLARI aksiyadorlik jamiyati"
    },
    "trainDirection": "Ахангаран - Канимех",
    "loadingPoint": {
        "stationId": "723009",
        "stationName": "Ахангаран",
        "railwayLine": null
    },
    "unloadingPoint": {
        "stationId": "731503",
        "stationName": "Канимех",
        "railwayLine": null
    },
    "wagons": [
        {
            "number": "76004639",
            "type": 7,
            "products": [
                {
                    "productGngCode": "28070000",
                    "productGngName": "Серная кислота; олеум",
                    "productEtsngCode": "481232",
                    "productEtsngName": "Кислота серная",
                    "weightBrutto": 61,
                    "weightNetto": 61
                }
            ]
        }
    ],
    "totalDistance": 616,
    "totalDeliveryCost": 5000000
}
```  
  
# 20. Проверка покуптаеля на участие в программе инвестий

### Тип: _GET_

### Endpoint: `/v1/utils/investment-object/202366012`

### Краткое описание: Проверяет buyerTin на участие в программе инвестиции и возвращает true/false

* Headers
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "isInvestmentObjectBuyer": false
}
```  
  
# 21. Получение лотов и расчетных счетов по программе инвестиций

### Тип: _GET_

### Endpoint: `/v1/utils/investment-object?sellerTin=&buyerTin=&objectId=`

### Краткое описание: Возвращаются разрешенные для использования лоты и расчетные счета по программе инвестиций

* Headers
* Параметры
* Response : _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token  
  
Параметр | Значение  
---|---  
sellerTin | ИНН продавца  
buyerTin | ИНН покупателя  
objectId | ID объекта
```json
{
    "objectId": "2201031310141001",
    "objectName": "test",
    "lots": [
        {
            "lotPrefix": null,
            "lotNumber": "12431006009377"
        }
    ],
    "accounts": [
        "100010860044017096521075149",
        "100011860064017096521075014"
    ]
}
```  
  
# 22. Получения авто в разделе “Мои авто”

### Тип: _GET_

### Endpoint: `v1/utils/transport`

### Краткое описание: Получения авто в разделе “Мои авто”

* Headers
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
[
    {
        "id": 23500,
        "regNo": "40 P 755 UI",
        "model": "BMW",
        "ownershipType": 1,
        "transportType": 7,
        "tinOrPinfl": "302936161",
        "isFeatured": false,
        "ownerName": "\"VENKON GROUP\" MCHJ"
    }
]
```  
  
# 23. Получение авто в разделе “Авто партнера”

### Тип: _GET_

### Endpoint: `v1/utils/transport/partners`

### Краткое описание: Получение авто в разделе “Авто партнера”

* Headers
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
[
    {
        "id": 23500,
        "regNo": "40 P 755 UI",
        "model": "BMW",
        "ownershipType": 1,
        "transportType": 7,
        "tinOrPinfl": "302936161",
        "isFeatured": false,
        "ownerName": "\"VENKON GROUP\" MCHJ"
    }
]
```  
  
# 24. Для создания транспорта. Если транспорт принадлежит партнёру, сохранится транспорт как партнерский.

### Тип: _GET_

### Endpoint: `v1/utils/transport/check`

### Краткое описание: Для создания транспорта. Если транспорт принадлежит партнёру, сохранится транспорт как партнерский.

* Headers
* Body
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "tinOrPinfl": [
        "310529901",
        "302936161"
    ],
    "regNumber": [
        "95 X 622 OB",
        "40 P 755 UI"
    ]
}
```
```json
{
    "success": true,
    "data": {
        "40 P 755 UI": {
            "id": 23504,
            "regNo": "40 P 755 UI",
            "model": "BMW",
            "ownershipType": 1,
            "transportType": 7,
            "isFeatured": false,
            "ownerName": "\"DIDOX TECH\" MCHJ"
        },
        "95 X 622 OB": {
            "id": 23410,
            "regNo": "95 X 622 OB",
            "model": "Mercedes",
            "ownershipType": 2,
            "transportType": 13,
            "isFeatured": false,
            "ownerName": "\"VENKON GROUP\" MCHJ"
        }
    },
    "error": null
}
```  
  
# 25. Удаления транспорта в разделе "Мои авто" и "Авто партнера"

### Тип: _DELETE_

### Endpoint: `v1/utils/transport/{waybillTransportId}/delete`

### Краткое описание: Удаления транспорта в разделе "Мои авто" и "Авто партнера"

* Headers
* Response _204_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json

```  
  
# 26. Получение льгот по ИНН, ИКПУ (Новый метод)

### Тип: _POST_

### Endpoint: `v1/utils/lgota/context-check/ru?checkDate={date}`

### Краткое описание: Метод для получения льгот по ИНН и ИКПУ

* Headers
* BODY
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "ownerTinOrPinfl": "310529901",
    "buyerTinOrPinfl": "302936161",
    "catalogCode": "02208001002090003",
    "vatReliefType": 0
}
```
```json
[
    {
        "Id": 102387,
        "Name": "УП-5099 от 30.06.2017 г пункт 5 абзац 2 Освободить сроком до 1 января 2028 года резидентов Инновационного центра от уплаты всех видов налогов и обязательных отчислений в государсвенные целевые фонды, а текже единого социального платежа.",
        "Type": 1
    },
    {
        "Id": 102387,
        "Name": "УП-5099 от 30.06.2017 г пункт 5 абзац 2 Освободить сроком до 1 января 2028 года резидентов Инновационного центра от уплаты всех видов налогов и обязательных отчислений в государсвенные целевые фонды, а текже единого социального платежа.",
        "Type": 1
    }
]
```  
  
# 27. Получение списка расчетных счетов по ИНН

### Тип: _GET_

### Endpoint: `v1/utils/bank-accounts/{tin}`

### Краткое описание: Получение списка расчетных счетов по ИНН

* Headers
* Response _200_

key | value  
---|---  
user-key | token  
Partner-Authorization | partner-token
```json
{
    "data": [
        {
            "bankId": "00974",
            "account": "20208000550408125001",
            "attribute": 1,
            "condition": 0
        },
        {
            "bankId": "00401",
            "account": "22620000200301235004",
            "attribute": 2,
            "condition": 0
        }
    ],
    "error": null
}
```
