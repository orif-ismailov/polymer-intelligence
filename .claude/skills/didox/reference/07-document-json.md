# 07. JSON документов

> Verbatim mirror of <https://api-docs.didox.uz/ru/integrators-property-documents>
> Source last updated: 2026-08-06T09:55:23.694Z

---

# 1. Счёт фактура

Счёт фактура - это документ налогового учета передаваемый при продажи товаров или услуг. Документ составляется согласно порядку законам Республики Узбекистан. Счёт фактуру можно отправить текущей датой или же датой ниже отправки самого документа. В документе участвуют 2 стороны: Отправитель и покупатель (Контрагент)

Для связки Договора НК и Счёт фактуры необходимо передавать в JSON документа ID Договора НК в поле  
**"didoxcontractid": ""** (служебное поле Didox: используется только для привязки, в тело документа не попадает)

> **Важно (новые требования роуминга).** Принимающая сторона проверяет структуру строго:
> 
>   1. **Лишние поля запрещены.** Всё, чего нет в примере ниже, передавать нельзя (в т.ч. `WithoutExcise`, `Expansion`, `Id`, `MeasureId`, `SellerDepartmentId`, `BuyerDepartmentId`).
>   2. **Неиспользуемый объект передаётся целиком как`null`**, а не пустым объектом `{}` с пустыми строками. Это касается:  
>  `FacturaRentDoc`, `OldFacturaDoc`, `ItemReleasedDoc`, `FacturaInvestmentObjectDoc`, `FacturaEmpowermentDoc`, `ForeignCompany`.
>   3. **Точность числовых значений:** поле «Количество» (`Count`) — до **6** знаков после запятой; все остальные числовые поля (`Summa`, `DeliverySum`, `VatRate`, `VatSum`, `ExciseRate`, `ExciseSum`, `DeliverySumWithVat`, `LgotaVatSum`, `BaseSumma`, `ProfitRate`) — до **2** знаков после запятой. Разделитель дробной части — точка, разделители разрядов не допускаются.
>   4. **Формат дат** — исключительно `yyyy-MM-dd` (например `2026-08-04`), без времени и без указания часового пояса. Относится ко всем полям с датами: `FacturaDate`, `ContractDate`, `OldFacturaDate`, `EmpowermentDateOfIssue`, `RentFrom`, `RentTo`.
>   5. `WithoutVat` передаётся только когда `ProductList.HasVat = true`; при `HasVat = false` поле не передаётся.
>   6. `Director` у поставщика и покупателя — **обязательное к заполнению** поле.
>   7. **Односторонний ЭСФ** (передан `SingleSidedType`): покупателя нет — `Buyer` передаётся как `null`, `BuyerTin` — пустая строка.
> 


### Пример Cчёт фактуры в структуре JSON:

* SubTypes
* SingleTypes
* Origin
* LgotaType
* JSON
* Response _200_

Код | Наименование  
---|---  
0 | Стандартный  
1 | Дополнительный  
2 | Возмещение расходов (газ, электроэнергия и др.)  
3 | Без оплаты  
4 | Исправленный  
5 | Исправленный (возмещение затрат)  
6 | Дополнительная (возмещение затрат)  
8 | Исправленный (без оплаты)  
9 | Дополнительный (без оплаты)  
  
Код | Наименование  
---|---  
1 | На физ. лицо  
2 | Экспорт услуг (За территории Республики Узбекистан)  
3 | На импорт  
5 | Финансовые услуги  
6 | Реализация ниже рыночной стоимости  
7 | Реализация ниже таможенной стоимости  
8 | Экспорт услуг (На территории Республики Узбекистан)  
9 | Прочие доходы  
10 | Подача подакцизных товаров на переработку  
11 | Использование подакцизных товаров для собственных нужд  
12 | Разница между ценой и себестоимостью подакцизных товаров  
13 | Потери и порча подакцизных товаров  
  
Код | Наименование  
---|---  
1 | Собственное производство  
2 | Купля-продажа  
3 | Оказание услуг  
4 | Не участвую  
  
Код | Наименование  
---|---  
1 | Льгота по НДС  
2 | Льгота по налогу с оборота  
  
1 * - Отметка обязательных строк для успешного создания счет-фактуры  
2 ** - Отметка обязательных к заполнению полей для успешного создания счет-фактуры
```json
{
    "Version": 1,  //Версия JSON-структуры. Текущее значение: 1 *
    "WaybillLocalIds": [],  //массив ID ТТН. Если ТТН нет - пустой массив
    "HasMarking": false,  //true - если реализуется маркируемая продукция
    "HasRent": false,  //true - если счёт-фактура на услуги по аренде. ИКПУ:10701001010000000,10701001004000000
    "FacturaRentDoc": null,  //Данные аренды. null - если HasRent = false. Иначе {"RentId":"","RentFrom":"","RentTo":""}
    "FacturaType": 0,  //Тип счета-фактуры (см. SubTypes) *
    "ProductList": {  //*
        "HasCommittent": true,  //Счет-фактура является трехсторонним ЭСФ по договору комиссии, т.е. в списке товаров имеются позиции, для которых указан комитент
        "HasLgota": true,  //true - если хотя бы для одного товара указана льгота (по НДС или налогу с оборота)
        "Tin": "310529901",  //ИНН либо ПИНФЛ поставщика **
        "HideReportCommittent": true,  //true - не включать позиции комитента в отчётность поставщика
        "HasExcise": false,  //В списке товаров имеются позиции с акцизным налогом
        "HasVat": true,  //В списке товаров имеются позиции с НДС
        "Products": [  //*
            {
                "OrdNo": 1,  //Порядковый номер *
                "LgotaId": "100001",  //Код льготы (по НДС или налогу с оборота). null - если не используется
                "CommittentName": "\"GAMMA TRADE\" LTD",  //Наименование комитента. "" - если HasCommittent = false
                "CommittentTin": "300555666",  //Комитент: ИНН юр.лица либо ПИНФЛ. "" - если HasCommittent = false
                "CommittentVatRegCode": "",  //Регистрационный код плательщика НДС комитента
                "CommittentVatRegStatus": null,  //Статус рег.кода плательщика НДС комитента. null - если не заполнен
                "Name": "Транспортно-экспедиционные услуги по маршруту Город-1 (UZ) - Город-2 (DE)",  //Наименование товара (продукта, услуги) **
                "CatalogCode": "10112008001000001",  //Код ИКПУ **
                "CatalogName": "Транспортно-логистические услуги Оказание международных транспортных перевозок",  //Название ИКПУ **
                "Marks": null,  //Маркировки. null - если HasMarking = false
                "Barcode": "",  //Штрих-код
                "PackageCode": "1209782",  //Код упаковки **
                "PackageName": "услуга (сум)",  //Название упаковки **
                "Count": 1,  //Количество. До 6 знаков после запятой *
                "Summa": "10000000.00",  //Цена за единицу. До 2 знаков после запятой *
                "DeliverySum": "10000000.00",  //Стоимость поставки (Count * Summa) **
                "VatRate": "0",  //Ставка НДС *
                "VatSum": "0.00",  //Сумма НДС *
                "ExciseRate": 0,  //Ставка акцизного налога. 0 - если HasExcise = false
                "ExciseSum": 0,  //Сумма акцизного налога. 0 - если HasExcise = false
                "DeliverySumWithVat": "10000000.00",  //Стоимость поставки с учётом НДС (DeliverySum + VatSum) **
                "WithoutVat": false,  //true - если "Без НДС". Передаётся только при HasVat = true *
                "LgotaType": 1,  //Тип льготы: 1 - льгота по НДС, 2 - льгота по налогу с оборота. null - если LgotaId = null
                "LgotaName": "(ст.263 НК) пункт 1. услуг по международной перевозке товаров...",  //Текст названия льготы. null - если LgotaId = null
                "LgotaVatSum": 1200000.00,  //Льготная сумма: для льгот по НДС - 12% от DeliverySum, для льгот по налогу с оборота - 0. null - если LgotaId = null
                "WarehouseId": null,  //ID склада
                "Origin": 3  //Происхождение товара (см. Origin) **
            }
        ]
    },
    "FacturaDoc": {  //*
        "FacturaNo": "SF-0000001",  //Номер счета-фактуры **
        "FacturaDate": "2026-08-04"  //Дата счета-фактуры (yyyy-MM-dd) **
    },
    "ContractDoc": {  //*
        "ContractNo": "D-000123",  //Номер договора **
        "ContractDate": "2026-03-26"  //Дата договора (yyyy-MM-dd) **
    },
    "ContractId": null,  //ID договора зарегистрированного в my.soliq.uz. null - если не используется
    "LotId": "",  //ID лота. "" - если не используется
    "OldFacturaDoc": null,  //Данные исправляемой/дополняемой СФ. null - если FacturaType = 0. Иначе {"OldFacturaId":"","OldFacturaNo":"","OldFacturaDate":""}
    "SellerTin": "310529901",  //Поставщик: ИНН юр.лица либо ПИНФЛ **
    "Seller": {  //Данные поставщика **
        "Name": "\"DIDOX TECH\" MCHJ",  //Наименование **
        "BranchCode": "",  //Код филиала
        "BranchName": "",  //Наименование филиала
        "VatRegCode": "326080220838",  //Регистрационный код плательщика НДС **
        "Account": "20208000905656222001",  //Расчётный счёт **
        "BankId": "00401",  //МФО *
        "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",  //Адрес **
        "Director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",  //Директор **
        "Accountant": "KARIMOVA ROKSANA NEMATJONOVNA",  //Бухгалтер
        "VatRegStatus": 20  //Статус рег.кода плательщика НДС **
    },
    "ItemReleasedDoc": null,  //Отпустивший товары. null - если не используется. Иначе {"ItemReleasedPinfl":"","ItemReleasedFio":""}
    "BuyerTin": "302936161",  //Покупатель: ИНН юр.лица либо ПИНФЛ. "" - при одностороннем ЭСФ **
    "Buyer": {  //Данные покупателя. null - при одностороннем ЭСФ (передан SingleSidedType) *
        "Name": "\"VENKON GROUP\" MCHJ",  //Наименование **
        "BranchCode": "",  //Код филиала
        "BranchName": "",  //Наименование филиала
        "VatRegCode": "326040002521",  //Регистрационный код плательщика НДС **
        "Account": "20208000400308125001",  //Расчётный счёт **
        "BankId": "00974",  //МФО *
        "Address": "Фидойилар МФЙ, Махтумкули кучаси",  //Адрес **
        "Director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //Директор **
        "Accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //Бухгалтер
        "VatRegStatus": 20  //Статус рег.кода плательщика НДС **
    },
    "FacturaInvestmentObjectDoc": null,  //Данные объекта в рамках инвестиционной программы. null - если не используется. Иначе {"ObjectId":"","ObjectName":""}
    "FacturaEmpowermentDoc": null,  //Доверенность. null - если не используется. Иначе {"EmpowermentNo":"","EmpowermentDateOfIssue":"","AgentFio":"","AgentPinfl":""}
    "ForeignCompany": null  //Иностранная компания. null - если не используется. Иначе {"CountryId":"","Name":"","Address":"","Bank":"","Account":""}
}
```

### Дополнительные поля (передавать только когда применимо)
```json
{
    "SingleSidedType": 1,  //Тип одностороннего ЭСФ (см. SingleTypes). Передаётся только для односторонних СФ - покупателя нет, документ подписывает только поставщик
    "BuyerTin": "",  //При одностороннем ЭСФ - пустая строка
    "Buyer": null,  //При одностороннем ЭСФ - null
    "OldFacturaDoc": {  //Обязательно при FacturaType != 0 (исправленный/дополнительный)
        "OldFacturaId": "",  //ID прошлой счета-фактуры **
        "OldFacturaNo": "",  //Номер прошлой счета-фактуры **
        "OldFacturaDate": ""  //Дата прошлой счета-фактуры (yyyy-MM-dd) **
    },
    "FacturaRentDoc": {  //Обязательно при HasRent = true
        "RentId": "",  //ID договора аренды **
        "RentFrom": "",  //Начало периода аренды (yyyy-MM-dd) **
        "RentTo": ""  //Конец периода аренды (yyyy-MM-dd) **
    },
    "FacturaEmpowermentDoc": {  //Доверенность покупателя. Если объект передаётся - все поля обязательны
        "EmpowermentNo": "",  //№ доверенности **
        "EmpowermentDateOfIssue": "",  //Дата доверенности (yyyy-MM-dd) **
        "AgentFio": "",  //ФИО доверенного лица **
        "AgentPinfl": ""  //ПИНФЛ доверенного лица **
    },
    "ItemReleasedDoc": {  //Отпустивший товары. Если объект передаётся - все поля обязательны
        "ItemReleasedPinfl": "",  //ПИНФЛ отпустившего товары **
        "ItemReleasedFio": ""  //ФИО отпустившего товары **
    },
    "FacturaInvestmentObjectDoc": {  //Объект инвестиционной программы. Если объект передаётся - все поля обязательны
        "ObjectId": "",  //ID объекта **
        "ObjectName": ""  //Наименование объекта **
    },
    "ForeignCompany": {  //Иностранная компания (экспорт/импорт)
        "CountryId": "",  //ID страны **
        "Name": "",  //Название организации **
        "Address": "",  //Адрес
        "Bank": "",  //Банк
        "Account": ""  //Расчётный счёт
    }
}
```
```json
{
    "pending_document": {
        "document_json": {
            "version": 1,
            "waybilllocalids": [],
            "hasmarking": false,
            "hasrent": false,
            "facturarentdoc": null,
            "facturatype": 0,
            "productlist": {
                "hascommittent": true,
                "haslgota": true,
                "tin": "310529901",
                "hidereportcommittent": true,
                "hasexcise": false,
                "hasvat": true,
                "products": [
                    {
                        "ordno": 1,
                        "lgotaid": "100001",
                        "committentname": "\"GAMMA TRADE\" LTD",
                        "committenttin": "300555666",
                        "committentvatregcode": "",
                        "committentvatregstatus": null,
                        "name": "Транспортно-экспедиционные услуги по маршруту Город-1 (UZ) - Город-2 (DE)",
                        "catalogcode": "10112008001000001",
                        "catalogname": "Транспортно-логистические услуги Оказание международных транспортных перевозок",
                        "marks": null,
                        "barcode": "",
                        "packagecode": "1209782",
                        "packagename": "услуга (сум)",
                        "count": 1,
                        "summa": "10000000.00",
                        "deliverysum": "10000000.00",
                        "vatrate": "0",
                        "vatsum": "0.00",
                        "exciserate": 0,
                        "excisesum": 0,
                        "deliverysumwithvat": "10000000.00",
                        "withoutvat": false,
                        "lgotatype": 1,
                        "lgotaname": "(ст.263 НК) пункт 1. услуг по международной перевозке товаров...",
                        "lgotavatsum": 1200000.00,
                        "warehouseid": null,
                        "origin": 3
                    }
                ]
            },
            "facturadoc": {
                "facturano": "SF-0000001",
                "facturadate": "2026-08-04"
            },
            "contractdoc": {
                "contractno": "D-000123",
                "contractdate": "2026-03-26"
            },
            "contractid": null,
            "lotid": "",
            "oldfacturadoc": null,
            "sellertin": "310529901",
            "seller": {
                "name": "\"DIDOX TECH\" MCHJ",
                "branchcode": "",
                "branchname": "",
                "vatregcode": "326080220838",
                "account": "20208000905656222001",
                "bankid": "00401",
                "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",
                "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
                "accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
                "vatregstatus": 20
            },
            "itemreleaseddoc": null,
            "buyertin": "302936161",
            "buyer": {
                "name": "\"VENKON GROUP\" MCHJ",
                "branchcode": "",
                "branchname": "",
                "vatregcode": "326040002521",
                "account": "20208000400308125001",
                "bankid": "00974",
                "address": "Фидойилар МФЙ, Махтумкули кучаси",
                "director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
                "accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
                "vatregstatus": 20
            },
            "facturainvestmentobjectdoc": null,
            "facturaempowermentdoc": null,
            "foreigncompany": null
        }
    },
    "_id": "11ef000000000000000000000000aaa1",
    "created_date": "2026-08-04 16:30:07"
}
```

# 2. Счет-фактура (ФАРМ)

Счёт фактура (ФАРМ) - это документ налогового учета передаваемый при продажи товаров или услуг. Документ составляется согласно порядку законам Республики Узбекистан. Счёт фактуру (ФАРМ) можно отправить текущей датой или же датой ниже отправки самого документа. В документе участвуют 2 стороны: Отправитель и покупатель (Контрагент)

Структура полностью совпадает со Счёт фактурой выше, отличия:

  * `ProductList.HasMedical` = `true`;
  * в каждой позиции добавляются `Serial`, `BaseSumma`, `ProfitRate`, `DispenseType`.


> **Важно (новые требования роуминга).** Принимающая сторона проверяет структуру строго:
> 
>   1. **Лишние поля запрещены.** Всё, чего нет в примере ниже, передавать нельзя (в т.ч. `WithoutExcise`, `Expansion`, `Id`, `MeasureId`, `SellerDepartmentId`, `BuyerDepartmentId`).
>   2. **Неиспользуемый объект передаётся целиком как`null`**, а не пустым объектом `{}` с пустыми строками. Это касается:  
>  `FacturaRentDoc`, `OldFacturaDoc`, `ItemReleasedDoc`, `FacturaInvestmentObjectDoc`, `FacturaEmpowermentDoc`, `ForeignCompany`.
>   3. **Точность числовых значений:** поле «Количество» (`Count`) — до **6** знаков после запятой; все остальные числовые поля (`Summa`, `DeliverySum`, `VatRate`, `VatSum`, `ExciseRate`, `ExciseSum`, `DeliverySumWithVat`, `LgotaVatSum`, `BaseSumma`, `ProfitRate`) — до **2** знаков после запятой. Разделитель дробной части — точка, разделители разрядов не допускаются.
>   4. **Формат дат** — исключительно `yyyy-MM-dd` (например `2026-08-04`), без времени и без указания часового пояса. Относится ко всем полям с датами: `FacturaDate`, `ContractDate`, `OldFacturaDate`, `EmpowermentDateOfIssue`, `RentFrom`, `RentTo`.
>   5. `WithoutVat` передаётся только когда `ProductList.HasVat = true`; при `HasVat = false` поле не передаётся.
>   6. `Director` у поставщика и покупателя — **обязательное к заполнению** поле.
>   7. **Односторонний ЭСФ** (передан `SingleSidedType`): покупателя нет — `Buyer` передаётся как `null`, `BuyerTin` — пустая строка.
> 


### Пример Cчёт фактуры (ФАРМ) в структуре JSON:

* SubTypes
* SingleTypes
* DispenseTypes
* JSON
* Response _200_

Код | Наименование  
---|---  
0 | Стандартный  
1 | Дополнительный  
2 | Возмещение расходов (газ, электроэнергия и др.)  
3 | Без оплаты  
4 | Исправленный  
5 | Исправленный (возмещение затрат)  
6 | Дополнительная (возмещение затрат)  
8 | Исправленный (без оплаты)  
9 | Дополнительный (без оплаты)  
  
Код | Наименование  
---|---  
1 | На физ. лицо  
2 | Экспорт услуг (За территории Республики Узбекистан)  
3 | На импорт  
5 | Финансовые услуги  
6 | Реализация ниже рыночной стоимости  
7 | Реализация ниже таможенной стоимости  
8 | Экспорт услуг (На территории Республики Узбекистан)  
9 | Прочие доходы  
  
Код | Наименование  
---|---  
1 | По рецепту  
2 | Без рецепта  
  
1 * - Отметка обязательных строк для успешного создания счет-фактуры  
2 ** - Отметка обязательных к заполнению полей для успешного создания счет-фактуры
```json
{
    "Version": 1,  //Версия JSON-структуры. Текущее значение: 1 *
    "WaybillLocalIds": [],  //массив ID ТТН. Если ТТН нет - пустой массив
    "HasMarking": false,  //true - если реализуется маркируемая продукция
    "HasRent": false,  //true - если счёт-фактура на услуги по аренде
    "FacturaRentDoc": null,  //Данные аренды. null - если HasRent = false
    "FacturaType": 0,  //Тип счета-фактуры (см. SubTypes) *
    "ProductList": {  //*
        "HasMedical": true,  //true - реализуется медицинская продукция. Для ФАРМ всегда true **
        "HasCommittent": false,  //Счет-фактура является трехсторонним ЭСФ по договору комиссии
        "HasLgota": false,  //true - если хотя бы для одного товара указана льгота (по НДС или налогу с оборота)
        "Tin": "310529901",  //ИНН либо ПИНФЛ поставщика **
        "HideReportCommittent": false,  //true - не включать позиции комитента в отчётность поставщика
        "HasExcise": false,  //В списке товаров имеются позиции с акцизным налогом
        "HasVat": true,  //В списке товаров имеются позиции с НДС
        "Products": [  //*
            {
                "OrdNo": 1,  //Порядковый номер *
                "LgotaId": null,  //Код льготы (по НДС или налогу с оборота). null - если не используется
                "CommittentName": "",  //Наименование комитента
                "CommittentTin": "",  //Комитент: ИНН юр.лица либо ПИНФЛ
                "CommittentVatRegCode": "",  //Регистрационный код плательщика НДС комитента
                "CommittentVatRegStatus": null,  //Статус рег.кода плательщика НДС комитента
                "Serial": "SER-000123",  //Серия товара **
                "BaseSumma": "80000.00",  //Базовая цена **
                "ProfitRate": "25.00",  //% добавленной стоимости **
                "DispenseType": 2,  //Отпуск лекарственных средств (см. DispenseTypes) **
                "Name": "Препарат «Пример» 500 мг, таблетки №20",  //Наименование товара (продукта, услуги) **
                "CatalogCode": "02100000000000001",  //Код ИКПУ **
                "CatalogName": "Лекарственное средство (пример)",  //Название ИКПУ **
                "Marks": null,  //Маркировки. null - если HasMarking = false
                "Barcode": "",  //Штрих-код
                "PackageCode": "1500001",  //Код упаковки **
                "PackageName": "упаковка",  //Название упаковки **
                "Count": 1,  //Количество. До 6 знаков после запятой *
                "Summa": "100000.00",  //Цена за единицу. До 2 знаков после запятой *
                "DeliverySum": "100000.00",  //Стоимость поставки (Count * Summa) **
                "VatRate": "12",  //Ставка НДС *
                "VatSum": "12000.00",  //Сумма НДС *
                "ExciseRate": 0,  //Ставка акцизного налога
                "ExciseSum": 0,  //Сумма акцизного налога
                "DeliverySumWithVat": "112000.00",  //Стоимость поставки с учётом НДС **
                "WithoutVat": false,  //true - если "Без НДС". Передаётся только при HasVat = true *
                "LgotaType": null,  //Тип льготы: 1 - льгота по НДС, 2 - льгота по налогу с оборота
                "LgotaName": null,  //Текст названия льготы
                "LgotaVatSum": null,  //Льготная сумма. null - если LgotaId = null
                "WarehouseId": null,  //ID склада
                "Origin": 2  //Происхождение товара (см. Origin) **
            }
        ]
    },
    "FacturaDoc": {  //*
        "FacturaNo": "SF-FARM-0000001",  //Номер счета-фактуры **
        "FacturaDate": "2026-08-04"  //Дата счета-фактуры (yyyy-MM-dd) **
    },
    "ContractDoc": {  //*
        "ContractNo": "D-000456",  //Номер договора **
        "ContractDate": "2026-08-04"  //Дата договора (yyyy-MM-dd) **
    },
    "ContractId": null,  //ID договора зарегистрированного в my.soliq.uz. null - если не используется
    "LotId": "",  //ID лота. "" - если не используется
    "OldFacturaDoc": null,  //null - если FacturaType = 0
    "SellerTin": "310529901",  //Поставщик: ИНН юр.лица либо ПИНФЛ **
    "Seller": {  //Данные поставщика **
        "Name": "\"DIDOX TECH\" MCHJ",  //Наименование **
        "BranchCode": "",  //Код филиала
        "BranchName": "",  //Наименование филиала
        "VatRegCode": "326080220838",  //Регистрационный код плательщика НДС **
        "Account": "20208000905656222001",  //Расчётный счёт **
        "BankId": "00401",  //МФО *
        "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",  //Адрес **
        "Director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",  //Директор **
        "Accountant": "KARIMOVA ROKSANA NEMATJONOVNA",  //Бухгалтер
        "VatRegStatus": 20  //Статус рег.кода плательщика НДС **
    },
    "ItemReleasedDoc": null,  //null - если не используется
    "BuyerTin": "302936161",  //Покупатель: ИНН юр.лица либо ПИНФЛ. "" - при одностороннем ЭСФ **
    "Buyer": {  //Данные покупателя. null - при одностороннем ЭСФ (передан SingleSidedType) *
        "Name": "\"VENKON GROUP\" MCHJ",  //Наименование **
        "BranchCode": "",  //Код филиала
        "BranchName": "",  //Наименование филиала
        "VatRegCode": "326040002521",  //Регистрационный код плательщика НДС **
        "Account": "20208000400308125001",  //Расчётный счёт **
        "BankId": "00974",  //МФО *
        "Address": "Фидойилар МФЙ, Махтумкули кучаси",  //Адрес **
        "Director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //Директор **
        "Accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //Бухгалтер
        "VatRegStatus": 20  //Статус рег.кода плательщика НДС **
    },
    "FacturaInvestmentObjectDoc": null,  //null - если не используется
    "FacturaEmpowermentDoc": null,  //null - если не используется
    "ForeignCompany": null  //null - если не используется
}
```

### Дополнительные поля (передавать только когда применимо)
```json
{
    "SingleSidedType": 1,  //Тип одностороннего ЭСФ (см. SingleTypes). Передаётся только для односторонних СФ - покупателя нет, документ подписывает только поставщик
    "BuyerTin": "",  //При одностороннем ЭСФ - пустая строка
    "Buyer": null,  //При одностороннем ЭСФ - null
    "OldFacturaDoc": {  //Обязательно при FacturaType != 0 (исправленный/дополнительный)
        "OldFacturaId": "",  //ID прошлой счета-фактуры **
        "OldFacturaNo": "",  //Номер прошлой счета-фактуры **
        "OldFacturaDate": ""  //Дата прошлой счета-фактуры (yyyy-MM-dd) **
    },
    "FacturaRentDoc": {  //Обязательно при HasRent = true
        "RentId": "",  //ID договора аренды **
        "RentFrom": "",  //Начало периода аренды (yyyy-MM-dd) **
        "RentTo": ""  //Конец периода аренды (yyyy-MM-dd) **
    },
    "FacturaEmpowermentDoc": {  //Доверенность покупателя. Если объект передаётся - все поля обязательны
        "EmpowermentNo": "",  //№ доверенности **
        "EmpowermentDateOfIssue": "",  //Дата доверенности (yyyy-MM-dd) **
        "AgentFio": "",  //ФИО доверенного лица **
        "AgentPinfl": ""  //ПИНФЛ доверенного лица **
    },
    "ItemReleasedDoc": {  //Отпустивший товары. Если объект передаётся - все поля обязательны
        "ItemReleasedPinfl": "",  //ПИНФЛ отпустившего товары **
        "ItemReleasedFio": ""  //ФИО отпустившего товары **
    },
    "FacturaInvestmentObjectDoc": {  //Объект инвестиционной программы. Если объект передаётся - все поля обязательны
        "ObjectId": "",  //ID объекта **
        "ObjectName": ""  //Наименование объекта **
    },
    "ForeignCompany": {  //Иностранная компания (экспорт/импорт)
        "CountryId": "",  //ID страны **
        "Name": "",  //Название организации **
        "Address": "",  //Адрес
        "Bank": "",  //Банк
        "Account": ""  //Расчётный счёт
    }
}
```
```json
{
    "pending_document": {
        "document_json": {
            "version": 1,
            "waybilllocalids": [],
            "hasmarking": false,
            "hasrent": false,
            "facturarentdoc": null,
            "facturatype": 0,
            "productlist": {
                "hasmedical": true,
                "hascommittent": false,
                "haslgota": false,
                "tin": "310529901",
                "hidereportcommittent": false,
                "hasexcise": false,
                "hasvat": true,
                "products": [
                    {
                        "ordno": 1,
                        "lgotaid": null,
                        "committentname": "",
                        "committenttin": "",
                        "committentvatregcode": "",
                        "committentvatregstatus": null,
                        "serial": "SER-000123",
                        "basesumma": "80000.00",
                        "profitrate": "25.00",
                        "dispensetype": 2,
                        "name": "Препарат «Пример» 500 мг, таблетки №20",
                        "catalogcode": "02100000000000001",
                        "catalogname": "Лекарственное средство (пример)",
                        "marks": null,
                        "barcode": "",
                        "packagecode": "1500001",
                        "packagename": "упаковка",
                        "count": 1,
                        "summa": "100000.00",
                        "deliverysum": "100000.00",
                        "vatrate": "12",
                        "vatsum": "12000.00",
                        "exciserate": 0,
                        "excisesum": 0,
                        "deliverysumwithvat": "112000.00",
                        "withoutvat": false,
                        "lgotatype": null,
                        "lgotaname": null,
                        "lgotavatsum": null,
                        "warehouseid": null,
                        "origin": 2
                    }
                ]
            },
            "facturadoc": {
                "facturano": "SF-FARM-0000001",
                "facturadate": "2026-08-04"
            },
            "contractdoc": {
                "contractno": "D-000456",
                "contractdate": "2026-08-04"
            },
            "contractid": null,
            "lotid": "",
            "oldfacturadoc": null,
            "sellertin": "310529901",
            "seller": {
                "name": "\"DIDOX TECH\" MCHJ",
                "branchcode": "",
                "branchname": "",
                "vatregcode": "326080220838",
                "account": "20208000905656222001",
                "bankid": "00401",
                "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",
                "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
                "accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
                "vatregstatus": 20
            },
            "itemreleaseddoc": null,
            "buyertin": "302936161",
            "buyer": {
                "name": "\"VENKON GROUP\" MCHJ",
                "branchcode": "",
                "branchname": "",
                "vatregcode": "326040002521",
                "account": "20208000400308125001",
                "bankid": "00974",
                "address": "Фидойилар МФЙ, Махтумкули кучаси",
                "director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
                "accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
                "vatregstatus": 20
            },
            "facturainvestmentobjectdoc": null,
            "facturaempowermentdoc": null,
            "foreigncompany": null
        }
    },
    "_id": "11ef000000000000000000000000aaa2",
    "created_date": "2026-08-04 16:30:07"
}
```

# 3. Гибридная счет-фактура

### Пример Гибридная счет-фактура в структуре JSON:

Гибридная счет-фактура - это документ налогового учета передаваемый при продажи товаров или услуг. Документ составляется согласно порядку законам Республики Узбекистан.

* SubTypes
* JSON
* Response _200_

Код | Наименование  
---|---  
0 | Стандартный  
1 | Дополнительный  
4 | Исправленный  
  
1 * - Отметка обязательных строк для успешного создания гибридной счет-фактуры
```json
{
    "HasMedicalEquipment": false,
    "HybridInvoiceType": 4, //*
    "HybridInvoiceDoc": {
        "No": "тест", *
        "Date": "2025-10-20" //*
    },
    "ContractDoc": {
        "No": "тест", //*
        "Date": "2025-10-20" //*
    },
    "OldHybridInvoiceDoc": null,
    "Seller": {
        "TinOrPinfl": "302936161", //*
        "TaxpayerType": 20, //*
        "BranchCode": "",
        "Name": "\"VENKON GROUP\" MCHJ", //*
        "VatRegCode": "326040002521", //*
        "AccountNumber": "20208000400308125001", //*
        "BankMfo": "00974", *
        "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй", //*
        "Director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
        "Accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
        "BranchName": "",
        "VatRegStatus": 20 //*
    },
    "ItemReleased": null,
    "Buyer": {
        "TinOrPinfl": "310529901", //*
        "TaxpayerType": 20, //*
        "BranchCode": "",
        "Name": "\"DIDOX TECH\" MCHJ", //*
        "VatRegCode": "326080220838", //*
        "AccountNumber": "20208000905656222001", //*
        "BankMfo": "00401", //*
        "Address": "г. Ташкент, ЯШНАБАДСКИЙ РАЙОН, Фидойилар МФЙ, Махтумкули кучаси, 114а-уй  ", //*
        "Director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
        "Accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
        "BranchName": "",
        "VatRegStatus": 20 //*
    },
    "HasBarcode": false,
    "HasCommittent": false,
    "HasTaxRelief": false,
    "HasExcise": false,
    "HasMarking": false,
    "Roadway": {
        "ProductGroups": [
            {
                "ProductInfo": {
                    "Products": [
                        {
                            "OrdNo": 1, //*
                            "Committent": null,
                            "TaxRelief": null,
                            "Marks": null,
                            "Excise": null,
                            "Name": "ноутбук", //*
                            "CatalogCode": "08471001001000000", //*
                            "CatalogName": "Ноутбук", //*
                            "PackageCode": "1501886", //*
                            "PackageName": "шт.", //*
                            "Barcode": "",
                            "Amount": 1, //*
                            "Price": 1, //*
                            "DeliverySum": 1, //*
                            "Vat": {
                                "Rate": 12, //*
                                "Sum": 0.12 //*
                            },
                            "DeliverySumWithVat": 1.12, //*
                             "Origin": 4 //*
                        }
                    ],
                    "TotalDeliverySum": "1.00", //*
                    "TotalVatSum": "0.12", //*
                    "TotalDeliverySumWithVat": "1.12" //*
                },
                "LoadingPoint": {
                    "RegionName": "Ферганская область", //*
                    "RegionId": 30, //*
                    "DistrictName": "Алтыарыкский район", //*
                    "DistrictCode": 12, //*
                    "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй" //*
                },
                "UnloadingPoint": {
                    "RegionName": "Ферганская область", //*
                    "RegionId": 30, //*
                    "DistrictName": "Алтыарыкский район", //*
                    "DistrictCode": 12, //*
                    "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй" //*
                }
            }
        ],
        "OtherCarOwners": null,
        "Truck": {
            "RegNo": "01 386 EJA", //*
            "Model": "NEXIA 3" //*
        },
        "Trailer": null,
        "Carriages": [],
        "Driver": {
            "Pinfl": "61403016600061", //*
            "FullName": "KULDASHEVA YEKATERINA MAKSIMOVNA" //*
        }
    },
    "FreightForwarder": null,
    "Carrier": {
        "TinOrPinfl": "302936161", //*
        "Name": "\"VENKON GROUP\" MCHJ", //*
        "BranchCode": "",
        "BranchName": ""
    },
    "Client": null,
    "Payer": null,
    "TransportType": 1,
    "ResponsibleToGoods": {
        "TinOrPinfl": "61403016600061", //*
        "Name": "KULDASHEVA YEKATERINA MAKSIMOVNA" //*
    },
    "TotalDistance": 1,
    "TotalDeliveryCost": "1",
    "TotalWeightBrutto": 0.12121,
    "TotalWeightNetto": 0.00123,
    "Empowerment": null
}
```
```json
{
    "document_json": {
        "hasmedicalequipment": false,
        "hybridinvoicetype": 0,
        "hybridinvoicedoc": {
            "no": "тест",
            "date": "2025-10-17"
        },
        "contractdoc": {
            "no": "1",
            "date": "2025-08-27"
        },
        "oldhybridinvoicedoc": null,
        "seller": {
            "tinorpinfl": "302936161",
            "taxpayertype": 20,
            "branchcode": null,
            "name": "\"VENKON GROUP\" MCHJ",
            "vatregcode": "326040002521",
            "accountnumber": "20208000400308125001",
            "bankmfo": "00974",
            "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",
            "director": "111",
            "accountant": "1111",
            "branchname": null,
            "vatregstatus": 20
        },
        "itemreleased": null,
        "buyer": {
            "tinorpinfl": "310529901",
            "taxpayertype": 20,
            "branchcode": null,
            "name": "\"DIDOX TECH\" MCHJ",
            "vatregcode": "326080220838",
            "accountnumber": "20208000905656222001",
            "bankmfo": "00401",
            "address": "г. Ташкент, ЯШНАБАДСКИЙ РАЙОН, Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",
            "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
            "accountant": "KARIMOVA ROKSANA NEMATJONOVNA",
            "branchname": null,
            "vatregstatus": 20
        },
        "hasbarcode": false,
        "hascommittent": false,
        "hastaxrelief": false,
        "hasexcise": false,
        "hasmarking": false,
        "roadway": {
            "productgroups": [
                {
                    "productinfo": {
                        "products": [
                            {
                                "ordno": 1,
                                "committent": null,
                                "taxrelief": null,
                                "marks": null,
                                "excise": null,
                                "name": "ноутбук",
                                "catalogcode": "08471001001000000",
                                "catalogname": "Ноутбук",
                                "packagecode": "1501886",
                                "packagename": "шт.",
                                "barcode": null,
                                "amount": 1,
                                "price": 1,
                                "deliverysum": 1,
                                "vat": {
                                    "rate": 12,
                                    "sum": 0.12
                                },
                                "deliverysumwithvat": 1.12,
                                "origin": 1
                            }
                        ],
                        "totaldeliverysum": "1.00",
                        "totalvatsum": "0.12",
                        "totaldeliverysumwithvat": "1.12"
                    },
                    "loadingpoint": {
                        "regionname": "Ферганская область",
                        "regionid": 30,
                        "districtname": "Алтыарыкский район",
                        "districtcode": 12,
                        "address": "1, 1555"
                    },
                    "unloadingpoint": {
                        "regionname": "Ферганская область",
                        "regionid": 30,
                        "districtname": "Алтыарыкский район",
                        "districtcode": 12,
                        "address": "2, 2"
                    }
                }
            ],
            "othercarowners": null,
            "truck": {
                "regno": "01 351 VFA",
                "model": "MALIBU 2"
            },
            "trailer": null,
            "carriages": [],
            "driver": {
                "pinfl": "61403016600061",
                "fullname": "KULDASHEVA YEKATERINA MAKSIMOVNA"
            }
        },
        "freightforwarder": null,
        "carrier": {
            "tinorpinfl": "302936161",
            "name": "\"VENKON GROUP\" MCHJ",
            "branchcode": null,
            "branchname": null
        },
        "client": null,
        "payer": null,
        "transporttype": 1,
        "responsibletogoods": {
            "tinorpinfl": "61403016600061",
            "name": "KULDASHEVA YEKATERINA MAKSIMOVNA"
        },
        "totaldistance": 1,
        "totaldeliverycost": "1",
        "totalweightbrutto": 0.12121,
        "totalweightnetto": 0.00123,
        "empowerment": null,
        "hybridinvoiceid": "68f62b1a8014ea98dba9ebaf"
    }
}
```

# 4. ТТН (Товарно-транспортная накладная)

Это накладная, предназначенная для учёта движения товарно-материальных ценностей при их перемещении с участием транспортных средств и является основанием для списания у грузоотправителя и оприходования их у грузополучателя.

Дополниетельное поле SkuId. Данное поле добавляется только в случае если грузополучатель 309376127 "UZUM MARKET" MCHJ XK. В стандартный JSON добавляется extended_json.

### Пример ТТН в структуре JSON:

* SubTypes
* JSON
* Response _200_

Код | Наименование  
---|---  
0 | Стандартный  
1 | Дополнительный  
4 | Исправленный  
  
1 * - Передавать полный JSON для успешного создания ТТН, * отмечены обязательные к заполнению поля
```json
{
    "WaybillLocalType": 0, // Тип ТТН
    "DeliveryType": 2, // Тип перевозки *
    "WaybillDoc": { // Информация по ТТН
        "WaybillNo": "ТестТТН", // Номер ТТН  *
        "WaybillDate": "2025-01-24" // Дата ТТН  *
    },
    "ContractDoc": { // Информация по договору
        "ContractNo": "ТестТТН", // Номер договора  *
        "ContractDate": "2025-01-24" // Дата договора  *
    },
    "OldWaybillDoc": null, // Информация по старой ТТН
    "HasCommittent": false, // Есть комитент true/false  *
    "SingleSidedType": 0, // 0 - двусторонний документ, 1 - односторонний документ 
    "Consignor": { // Информация по грузоотправителю
        "TinOrPinfl": "310529901", // ИНН/ПИНФЛ грузоотправителя  *
        "Name": "\"DIDOX TECH\" MCHJ", // Название грузоотправителя  *
        "BranchCode": "", // Код филиала грузоотправителя
        "BranchName": "" // Название филиала грузоотправителя
    },
    "Consignee": { // Информация по грузополучателю (если односторонний ТТН передавать null)
        "TinOrPinfl": "309376127", // ИНН/ПИНФЛ грузополучателю  *
        "Name": "\"UZUM MARKET\" MCHJ XK", // Название грузополучателю  *
        "BranchCode": "", // Код филиала грузополучателю
        "BranchName": "" // Название филиала грузополучателю
    },
    "FreightForwarder": : { // Информация по экспедитору, если нет, то передавать null
        "TinOrPinfl": "302936161", // ИНН/ПИНФЛ экспедитора  *
        "Name": "\"VENKON GROUP\" MCHJ", // Название экспедитора  *
        "BranchCode": "", // Код филиала экспедитора
        "BranchName": "" // Название филиала экспедитора
    },
    "Carrier": { // Информация по грузоперевозчику
        "TinOrPinfl": "302936161", // Информация по грузоперевозчику  *
        "Name": "\"VENKON GROUP\" MCHJ", // Название грузоперевозчика  *
        "BranchCode": "", // Код филиала грузоперевозчика
        "BranchName": "" // Название филиала грузоперевозчика
    },
    "Client": { // Информация по клиенту, если нет, то передавать null
        "TinOrPinfl": "310529901", // ИНН/ПИНФЛ клиента  *
        "Name": "\"DIDOX TECH\" MCHJ", // Название клиента  *
        "ContractNo": "45", // Номер договора
        "ContractDate": "2024-04-01", // Дата договора
        "BranchCode": "", // Код филиала клиента
        "BranchName": "" // Название филиала клиента
    },
    "Payer": { // Информация по заказчику, если нет, то передавать null
        "TinOrPinfl": "310529901", // ИНН/ПИНФЛ заказчика  *
        "Name": "\"DIDOX TECH\" MCHJ", // Название заказчика  *
        "ContractNo": "45", // Номер договора
        "ContractDate": "2024-04-01", // Дата договора
        "BranchCode": "", // Код филиала заказчика
        "BranchName": "" // Название филиала заказчика
    },
    "TransportType": 1, // Тип транспорта  *
    "Roadway": { // Информация по грузуперевозке
        "OtherCarOwners": null, // Владелец транспорта
        "Truck": {
            "RegNo": "01 386 EJA", // Номер автомобиля  *
            "Model": "NEXIA 3" // Модель автомобиля  *
        },
        "Trailer": { // Информация по полуприцепу, если нет, то передавать null
            "RegNo": "string", // Номер полуприцепа
            "Model": "string" // Модель полуприцепа
        }, 
        "Carriages": [], // Информация по прицепу
        "Driver": { // Информация по водителю
            "pinfl": "30606950270086", // ПИНФЛ водителя  *
            "FullName": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI" // ФИО водителя  *
        },
        "ProductGroups": [ // Информация по грузу
            {
                "LoadingPoint": { // Адрес погрузки
                    "regionId": 26, // ID региона  *
                    "regionName": "город Ташкент", // Название региона  *
                    "districtCode": 3, // Код района  *
                    "districtName": "Юнусабадский район", // Название района  *
                    "mahallaId": null, // ID махалли  *
                    "mahallaName": null, // Название махалли  *
                    "address": "123, 123", // Адрес  *
                    "longitude": null, // Широта
                    "latitude": null // Долгота
                },
                "LoadingTrustee": { // Отв. лицо грузоотправителя
                    "pinfl": "401001900234031", // ПИНФЛ  *
                    "fullName": "FIO" // ФИО  *
                },
                "UnloadingPoint": { // Адрес доставки
                    "regionId": 26, // ID региона  *
                    "regionName": "город Ташкент", // Название региона  *
                    "districtCode": 3, // Код района  *
                    "districtName": "Юнусабадский район", // Название района  *
                    "mahallaId": null, // ID махалли  *
                    "mahallaName": null, // Название махалли  *
                    "address": "321, 321", // Адрес  *
                    "longitude": null, // Широта
                    "latitude": null // Долгота
                },
                "UnloadingTrustee": { // Отв. лицо грузополучателя
                    "Pinfl": "401001900234031", // ПИНФЛ  *
                    "FullName": "FIO" // ФИО  *
                },
                "UnloadingEmpowerment": { // Доверенность, если нет, то передавать null
                    "EmpowermentId": "ID", // ID  доверенности
                    "EmpowermentNo": "12", // Номер доверенности  *
                    "EmpowermentDateOfIssue": "2024-04-16", // Дата доверенности (от)  *
                    "EmpowermentDateOfExpire": "2024-04-17" // Дата доверенности (до)  *
                },
                "ProductInfo": {
                    "TotalDeliverySum": 100, // Сумма доставки  *
                    "TotalWeightBrutto": 10, // Сумма брутто  *
                    "products": [
                        {
                            "ordNo": 1, // Порядковый номер
                            "CommittentTinOrPinfl": "", // ИНН/ПИНФЛ комитента
                            "CommittentName": "", // Название комитента
                            "CatalogCode": "00102001001000000", // ИКПУ  *
                            "CatalogName": "Живые быки", // Название ИКПУ  *
                            "ProductName": "test", // Название товара  *
                            "PackageCode": "1378367", // Код упаковки  *
                            "PackageName": "шт.", // Название упаковки  *
                            "Amount": "4", // Количество  *
                            "Price": "5", // Цена за ед.  *
                            "DeliverySum": "20.00", // Сумма доставки  *
                            "WeightBrutto": "500", // Вес брутто
                            "WeightNetto": "499" // Вес нетто
                        }
                    ]
                }
            }
        ]
    },
    "Railway": { // Информация по ж/д перевозке, если нет, то передавать null
        "traindirection": "направление", // Направление поезда  *
        "railwaydocid": null, // ID ж/д документа
        "hasrailwayline": true, // Есть ж/д линия true/false  *
        "productgroups": [
            {
                "loadingpoint": { // Пункт погрузки
                    "stationid": "742003",  // ID станции  *
                    "stationname": "Андижан II", // Название станции  *
                    "railwayline": {
                        "id": "22",  // ID ж/д линии  *
                        "name": "СП АО Бухарагипс", // Название ж/д линии  *
                        "address": "г.Каган ул.Кончилар 1" // Адрес ж/д линии  *
                    }
                },
                "loadingtrustee": null,
                "unloadingpoint": {
                    "stationid": "743801", // ID станции  *
                    "stationname": "Жалакудук", // Название станции  *
                    "railwayline": null // Ж/д линия
                },
                "unloadingtrustee": null,
                "unloadingempowerment": null,
                "productinfo": {
                    "products": [
                        {
                            "ordno": 1,
                            "committenttinorpinfl": "",
                            "committentname": "",
                            "catalogcode": "08471001001000000",
                            "catalogname": "Ноутбук",
                            "productname": "тест",
                            "packagecode": "1501886",
                            "packagename": "шт.",
                            "amount": "11",
                            "price": "11",
                            "deliverysum": "121.00",
                            "weightbrutto": 0,
                            "weightnetto": 0
                        }
                    ],
                    "totaldeliverysum": 121,  // Общая сумма доставки  *
                    "totalweightbrutto": 0 // Общий вес брутто  *
                },
                "wagondoc": {
                    "number": "тест", // Номер вагона  *
                    "type": "тест", // Тип вагона  *
                }
            }
        ]
    },
    "ResponsiblePerson": { // Ответственное лицо за доставку груза, если нет, то передавать null
        "Pinfl": "string", // ПИНФЛ  *
        "FullName": "string" // ФИО  *
    },
    "ResponsibleCompany": { // Ответственная организация за доставку груза, если нет, то передавать null
        "Tin": "string", // ИНН организации за доставку груза  *
        "Name": "string", // Название организации за доставку груза  *
        "BranchCode": "", // Код филиала организации за доставку груза
        "BranchName": "" // Название филиала организации за доставку груза
    },
    "TotalDistance": "10.00", // Общее расстояние (км)  *
    "DeliveryCost": "10", // Цена доставки за 1 км  *
    "TotalDeliveryCost": "100.00", // Общая стоимость доставки  *
}
```
```json
{
    "document_json": {
    "WaybillLocalType": 0, // Тип ТТН
    "DeliveryType": 2, // Тип перевозки *
    "WaybillDoc": { // Информация по ТТН
        "WaybillNo": "ТестТТН", // Номер ТТН  *
        "WaybillDate": "2025-01-24" // Дата ТТН  *
    },
    "ContractDoc": { // Информация по договору
        "ContractNo": "ТестТТН", // Номер договора  *
        "ContractDate": "2025-01-24" // Дата договора  *
    },
    "OldWaybillDoc": null, // Информация по старой ТТН
    "HasCommittent": false, // Есть комитент true/false  *
    "SingleSidedType": 0, // 0 - двусторонний документ, 1 - односторонний документ 
    "Consignor": { // Информация по грузоотправителю
        "TinOrPinfl": "310529901", // ИНН/ПИНФЛ грузоотправителя  *
        "Name": "\"DIDOX TECH\" MCHJ", // Название грузоотправителя  *
        "BranchCode": "", // Код филиала грузоотправителя
        "BranchName": "" // Название филиала грузоотправителя
    },
    "Consignee": { // Информация по грузополучателю (если односторонний ТТН передавать null)
        "TinOrPinfl": "309376127", // ИНН/ПИНФЛ грузополучателю  *
        "Name": "\"UZUM MARKET\" MCHJ XK", // Название грузополучателю  *
        "BranchCode": "", // Код филиала грузополучателю
        "BranchName": "" // Название филиала грузополучателю
    },
    "FreightForwarder": : { // Информация по экспедитору, если нет, то передавать null
        "TinOrPinfl": "302936161", // ИНН/ПИНФЛ экспедитора  *
        "Name": "\"VENKON GROUP\" MCHJ", // Название экспедитора  *
        "BranchCode": "", // Код филиала экспедитора
        "BranchName": "" // Название филиала экспедитора
    },
    "Carrier": { // Информация по грузоперевозчику
        "TinOrPinfl": "302936161", // Информация по грузоперевозчику  *
        "Name": "\"VENKON GROUP\" MCHJ", // Название грузоперевозчика  *
        "BranchCode": "", // Код филиала грузоперевозчика
        "BranchName": "" // Название филиала грузоперевозчика
    },
    "Client": { // Информация по клиенту, если нет, то передавать null
        "TinOrPinfl": "310529901", // ИНН/ПИНФЛ клиента  *
        "Name": "\"DIDOX TECH\" MCHJ", // Название клиента  *
        "ContractNo": "45", // Номер договора
        "ContractDate": "2024-04-01", // Дата договора
        "BranchCode": "", // Код филиала клиента
        "BranchName": "" // Название филиала клиента
    },
    "Payer": { // Информация по заказчику, если нет, то передавать null
        "TinOrPinfl": "310529901", // ИНН/ПИНФЛ заказчика  *
        "Name": "\"DIDOX TECH\" MCHJ", // Название заказчика  *
        "ContractNo": "45", // Номер договора
        "ContractDate": "2024-04-01", // Дата договора
        "BranchCode": "", // Код филиала заказчика
        "BranchName": "" // Название филиала заказчика
    },
    "TransportType": 1, // Тип транспорта  *
    "Roadway": { // Информация по грузуперевозке
        "OtherCarOwners": null, // Владелец транспорта
        "Truck": {
            "RegNo": "01 386 EJA", // Номер автомобиля  *
            "Model": "NEXIA 3" // Модель автомобиля  *
        },
        "Trailer": { // Информация по полуприцепу, если нет, то передавать null
            "RegNo": "string", // Номер полуприцепа
            "Model": "string" // Модель полуприцепа
        }, 
        "Carriages": [], // Информация по прицепу
        "Driver": { // Информация по водителю
            "pinfl": "30606950270086", // ПИНФЛ водителя  *
            "FullName": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI" // ФИО водителя  *
        },
        "ProductGroups": [ // Информация по грузу
            {
                "LoadingPoint": { // Адрес погрузки
                    "regionId": 26, // ID региона  *
                    "regionName": "город Ташкент", // Название региона  *
                    "districtCode": 3, // Код района  *
                    "districtName": "Юнусабадский район", // Название района  *
                    "mahallaId": null, // ID махалли  *
                    "mahallaName": null, // Название махалли  *
                    "address": "123, 123", // Адрес  *
                    "longitude": null, // Широта
                    "latitude": null // Долгота
                },
                "LoadingTrustee": { // Отв. лицо грузоотправителя
                    "pinfl": "401001900234031", // ПИНФЛ  *
                    "fullName": "FIO" // ФИО  *
                },
                "UnloadingPoint": { // Адрес доставки
                    "regionId": 26, // ID региона  *
                    "regionName": "город Ташкент", // Название региона  *
                    "districtCode": 3, // Код района  *
                    "districtName": "Юнусабадский район", // Название района  *
                    "mahallaId": null, // ID махалли  *
                    "mahallaName": null, // Название махалли  *
                    "address": "321, 321", // Адрес  *
                    "longitude": null, // Широта
                    "latitude": null // Долгота
                },
                "UnloadingTrustee": { // Отв. лицо грузополучателя
                    "Pinfl": "401001900234031", // ПИНФЛ  *
                    "FullName": "FIO" // ФИО  *
                },
                "UnloadingEmpowerment": { // Доверенность, если нет, то передавать null
                    "EmpowermentId": "ID", // ID  доверенности
                    "EmpowermentNo": "12", // Номер доверенности  *
                    "EmpowermentDateOfIssue": "2024-04-16", // Дата доверенности (от)  *
                    "EmpowermentDateOfExpire": "2024-04-17" // Дата доверенности (до)  *
                },
                "ProductInfo": {
                    "TotalDeliverySum": 100, // Сумма доставки  *
                    "TotalWeightBrutto": 10, // Сумма брутто  *
                    "products": [
                        {
                            "ordNo": 1, // Порядковый номер
                            "CommittentTinOrPinfl": "", // ИНН/ПИНФЛ комитента
                            "CommittentName": "", // Название комитента
                            "CatalogCode": "00102001001000000", // ИКПУ  *
                            "CatalogName": "Живые быки", // Название ИКПУ  *
                            "ProductName": "test", // Название товара  *
                            "PackageCode": "1378367", // Код упаковки  *
                            "PackageName": "шт.", // Название упаковки  *
                            "Amount": "4", // Количество  *
                            "Price": "5", // Цена за ед.  *
                            "DeliverySum": "20.00", // Сумма доставки  *
                            "WeightBrutto": "500", // Вес брутто
                            "WeightNetto": "499" // Вес нетто
                        }
                    ]
                }
            }
        ]
    },
    "Railway": { // Информация по ж/д перевозке, если нет, то передавать null
        "traindirection": "направление", // Направление поезда  *
        "railwaydocid": null, // ID ж/д документа
        "hasrailwayline": true, // Есть ж/д линия true/false  *
        "productgroups": [
            {
                "loadingpoint": { // Пункт погрузки
                    "stationid": "742003",  // ID станции  *
                    "stationname": "Андижан II", // Название станции  *
                    "railwayline": {
                        "id": "22",  // ID ж/д линии  *
                        "name": "СП АО Бухарагипс", // Название ж/д линии  *
                        "address": "г.Каган ул.Кончилар 1" // Адрес ж/д линии  *
                    }
                },
                "loadingtrustee": null,
                "unloadingpoint": {
                    "stationid": "743801", // ID станции  *
                    "stationname": "Жалакудук", // Название станции  *
                    "railwayline": null // Ж/д линия
                },
                "unloadingtrustee": null,
                "unloadingempowerment": null,
                "productinfo": {
                    "products": [
                        {
                            "ordno": 1,
                            "committenttinorpinfl": "",
                            "committentname": "",
                            "catalogcode": "08471001001000000",
                            "catalogname": "Ноутбук",
                            "productname": "тест",
                            "packagecode": "1501886",
                            "packagename": "шт.",
                            "amount": "11",
                            "price": "11",
                            "deliverysum": "121.00",
                            "weightbrutto": 0,
                            "weightnetto": 0
                        }
                    ],
                    "totaldeliverysum": 121,  // Общая сумма доставки  *
                    "totalweightbrutto": 0 // Общий вес брутто  *
                },
                "wagondoc": {
                    "number": "тест", // Номер вагона  *
                    "type": "тест", // Тип вагона  *
                }
            }
        ]
    },
    "ResponsiblePerson": { // Ответственное лицо за доставку груза, если нет, то передавать null
        "Pinfl": "string", // ПИНФЛ  *
        "FullName": "string" // ФИО  *
    },
    "ResponsibleCompany": { // Ответственная организация за доставку груза, если нет, то передавать null
        "Tin": "string", // ИНН организации за доставку груза  *
        "Name": "string", // Название организации за доставку груза  *
        "BranchCode": "", // Код филиала организации за доставку груза
        "BranchName": "" // Название филиала организации за доставку груза
    },
    "TotalDistance": "10.00", // Общее расстояние (км)  *
    "DeliveryCost": "10", // Цена доставки за 1 км  *
    "TotalDeliveryCost": "100.00", // Общая стоимость доставки  *
}
```

# 5. Акт

Акт выполненных работ - это документ, который составляется исполнителем заказчику с целью подтверждения факта выполнения работ либо оказания услуг по договору между ними. Акт может быть связан вместе с документом “Cчёт фактура”

### Пример Акта в структуре JSON:

* JSON
* Response _200_
```json
{
    "actdoc": { // Данные акта выполненных работ
        "actno": "test", // Номер акта *
        "actdate": "2026-04-24", // Дата акта *
        "acttext": "..." // Текст акта (описание выполненных работ и сторон)
    },

    "contractdoc": { // Данные договора
        "contractno": "test", // Номер договора *
        "contractdate": "2026-04-24" // Дата договора *
    },

    "sellertin": "sellertin", // ИНН исполнителя (продавца) *
    "sellerbranchcode": "", // Код филиала исполнителя
    "sellerbranchname": "", // Название филиала исполнителя
    "sellername": "sellername", // Название исполнителя *

    "buyertin": "buyertin", // ИНН заказчика (покупателя) *
    "buyername": "buyername", // Название заказчика *
    "buyerbranchcode": "", // Код филиала заказчика
    "buyerbranchname": "", // Название филиала заказчика

    "productlist": { // Список работ/услуг (или товаров)
        "products": [ // Перечень позиций
            {
                "ordno": 1, // Порядковый номер *
                "catalogcode": null, // Код каталога 
                "name": "test", // Наименование услуги/товара *
                "packagecode": null, // Код упаковки/единицы измерения, обязательное, если выбран catalogcode *
                "count": "16", // Количество * 
                "summa": "12", // Цена за единицу *
                "totalsum": "215.04", // Общая сумма (возможно с НДС) *
                "measureid": "46", // Идентификатор единицы измерения, обязательное, если не выбран catalogcode *
                "packagename": null, // Название единицы измерения, обязательное, если выбран catalogcode *
                "catalogname": null // Название из каталога
            }
        ],
        "tin": "tin" // ИНН владельца списка (обычно продавец) *
    },
    "extended_json": { // Расширенная версия данных (детализированная структура)
        "actdoc": { // Повтор данных акта
            "actno": "test", // Номер акта *
            "actdate": "2026-04-24", // Дата акта *
            "acttext": "..." // Текст акта
        },

        "contractdoc": { // Повтор данных договора
            "contractno": "test", // Номер договора *
            "contractdate": "2026-04-24" // Дата договора * 
        },

        "sellertin": "sellertin", // ИНН исполнителя *
        "sellerbranchcode": "", // Код филиала
        "sellerbranchname": "", // Название филиала
        "sellername": "sellername", // Название исполнителя *
        "buyertin": "buyertin", // ИНН заказчика *
        "buyername": "buyername", // Название заказчика *
        "buyerbranchcode": "", // Код филиала
        "buyerbranchname": "", // Название филиала
        "productlist": { // Расширенный список позиций
            "products": [
                {
                    "ordno": 1, // Порядковый номер *
                    "catalogcode": null, // Код каталога 
                    "name": "test", // Наименование *
                "packagecode": null, // Код упаковки/единицы измерения, обязательное, если выбран catalogcode *
                    "count": "16", // Количество *
                    "summa": "12", // Цена за единицу *
                    "totalsumwithoutvat": "192.00", // Сумма без НДС 
                    "vatrate": "12", // Ставка НДС (%)
                    "vatsum": "23.04", // Сумма НДС 
                    "totalsum": "215.04", // Итоговая сумма с НДС *
                "measureid": "46", // Идентификатор единицы измерения, обязательное, если не выбран catalogcode *
                "packagename": null, // Название единицы измерения, обязательное, если выбран catalogcode *
                    "withoutvat": false, // Признак "без НДС" 
                    "catalogname": null // Название из каталога
                }
            ],
            "hasvat": true, // Признак наличия НДС
            "tin": "tin" // ИНН владельца списка *
        }
    }
}
```
```json
{
    "pending_document": {
        "document_json": {
            "actdoc": {
                "actno": "test",
                "actdate": "2026-04-24",
                "acttext": "..."
            },
            "contractdoc": {
                "contractno": "test",
                "contractdate": "2026-04-24"
            },
            "sellertin": "sellertin",
            "sellerbranchcode": "",
            "sellerbranchname": "",
            "sellername": "sellername",
            "buyertin": "buyertin",
            "buyername": "buyername",
            "buyerbranchcode": "",
            "buyerbranchname": "",
            "productlist": {
                "products": [
                    {
                        "ordno": 1,
                        "catalogcode": null,
                        "name": "test",
                        "packagecode": null,
                        "count": "16",
                        "summa": "12",
                        "totalsum": "215.04",
                        "measureid": "46",
                        "packagename": null,
                        "catalogname": null
                    }
                ],
                "tin": "tin",
                "actproductid": "69eeff6b124dbfd29165eb6d"
            },
            "actid": "69eeff2b434dbfd29165eb6c"
        }
    },
    "_id": "bc3a753a420011f18de2fa163ea3fd69",
    "created_date": "2026-04-27 11:17:15"
}
```

# 6. Доверенность

Доверенность - этот документ оформляется в случае когда компания (А) передает товар компании (Б) Физическому лицу  
В данном документе учувствуют 3 стороны, 2 юр. лица и 1 физлицо.

### Пример Доверенности в структуре JSON:

* JSON
* Response _200_
```json
{
    "EmpowermentDoc": {
        "EmpowermentNo": "текст",  //Номер доверенности *
        "EmpowermentDateOfIssue": "2025-02-07",  //Дата выдачи доверенности *
        "EmpowermentDateOfExpire": "2025-02-14"  //Дата окончания действия доверенности *
    },
    "ContractDoc": {
        "ContractNo": "текст",  //Номер договора *
        "ContractDate": "2025-02-07"  //Дата договора *
    },
    "Agent": {
        "JobTitle": null,  //Должность
        "Fio": "MAMATQULOV SANJAR XAMZALI O‘G‘LI",  //ФИО Дов. лица *
        "Passport": {
            "Number": null, //Серия и номер паспорта
            "IssuedBy": null,  //Кем выдан
            "DateOfIssue": null  //Дата выдачи
        },
        "AgentTin": "50106026830029"  //ПИНФЛ Дов. лица *
    },
    "SellerTin": "302936161",  //Покупатель:ИНН юр.лица либо ПИНФЛ *
    "Seller": {
        "Name": "\"VENKON GROUP\" MCHJ", //Наименование покупателя*
        "BranchCode": "",  //Код филиала
        "BranchName": "",  //Наименование филиала
        "Account": "20208000400308125001",  //Расчетный счет *
        "BankId": "00974",  //МФО *
        "Address": "Фидойилар МФЙ, Махтумкули кучаси,  ",  //Адрес *
        "Director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //Директор
        "Accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA" //Главный бухгалтер
    },
    "BuyerTin": "310529901",  //Продавец:ИНН юр.лица либо ПИНФЛ *
    "ProductList": {
        "Tin": "310529901",  //Продавец:ИНН юр.лица либо ПИНФЛ *
        "HasExcise": false,  //Акцизный товар
        "HasVat": true,  //НДС
        "Products": [
            {
                "OrdNo": 1,  //Порядковый номер
                "CatalogCode": "08471001001000000",  //Код ИКПУ
                "CatalogName": "Ноутбук",  //Наименование ИКПУ
                "Name": "тест",  //Наименование товара *
                "MeasureId": "1",  //Единица измерения *
                "Count": "10"  //Количество *
            }
        ]
    },
    "Buyer": {
        "Name": "\"DIDOX TECH\" MCHJ",  //Наименование поставщика *
        "BranchCode": "",  //Код филиала
        "BranchName": "",  //Наименование филиала
        "Account": "20208000400308125001",  //Расчетный счет *
        "BankId": "00974",  //МФО *
        "Address": "Фидойилар МФЙ, Махтумкули кучаси,  ",  //Адрес *
        "Director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //Директор
        "Accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA" //Главный бухгалтер
    }
}
```
```json
{
    "document_json": {
        "empowermentdoc": {
            "empowermentno": "текст",
            "empowermentdateofissue": "2025-02-07",
            "empowermentdateofexpire": "2025-02-14"
        },
        "contractdoc": {
            "contractno": "текст",
            "contractdate": "2025-02-07"
        },
        "agent": {
            "jobtitle": null,
            "fio": "MAMATQULOV SANJAR XAMZALI O‘G‘LI",
            "passport": {
                "number": null,
                "issuedby": null,
                "dateofissue": null
            },
            "agenttin": "50106026830029",
            "agentempowermentid": "67a5d628b90ad5bf983f00c7"
        },
        "sellertin": "302936161",
        "seller": {
            "name": "\"VENKON GROUP\" MCHJ",
            "branchcode": "",
            "branchname": "",
            "account": "20208000400308125001",
            "bankid": "00974",
            "address": "Фидойилар МФЙ, Махтумкули кучаси,  ",
            "director": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
            "accountant": "MUKUMOVA SHAKHNOZA RUSTAMOVNA"
        },
        "buyertin": "310529901",
        "productlist": {
            "tin": "310529901",
            "hasexcise": false,
            "hasvat": true,
            "products": [
                {
                    "ordno": 1,
                    "catalogcode": "08471001001000000",
                    "catalogname": "Ноутбук",
                    "name": "тест",
                    "measureid": "1",
                    "count": "10"
                }
            ],
            "empowermentproductid": "67a5d629f51e54040a84fa04"
        },
        "buyer": {
            "name": "\"DIDOX TECH\" MCHJ",
            "branchcode": "",
            "branchname": "",
            "account": "20208000905656222001",
            "bankid": "00401",
            "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",
            "director": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
            "accountant": "KARIMOVA ROKSANA NEMATJONOVNA"
        },
        "empowermentid": "67a5d628f51e54040a84fa01"
    }
}
```

# 7. Договор НК

Договор НК - Этот документ рассчитан для отправки Договоров, шаблон предоставляемый Роуминговым центром [my.soliq.uz](<http://my.soliq.uz>) . Документ синхронизируется с Другими операторами и Роуминговым центром [my.soliq.uz](<http://my.soliq.uz>)

### Пример Договора НК в структуре JSON:

* JSON
* Response _200_
```json
{
    "ContractDoc": {
        "ContractName": "тест",  //Наименование договора *
        "ContractNo": "тест",  //Номер договора *
        "ContractDate": "2025-02-07",  //Дата договора *
        "ContractExpireDate": "2025-02-07",  //Дата окончания договора *
        "ContractPlace": "тест"  //Место заключения договора *
    },
    "Owner": {
        "Tin": "310529901",  //Поставщик:ИНН юр.лица либо ПИНФЛ *
        "Name": "\"DIDOX TECH\" MCHJ",  //Наименование поставщика *
        "BranchCode": "",  //Код филиала
        "BranchName": "",  //Наименование филиала
        "FizTin": "32901930460050",  //ПИНФЛ физ. лица  *
        "Fio": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",  //ФИО физ. лица *
        "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",  //Адрес
        "WorkPhone": "998933800525",  //Рабочий телефон
        "Mobile": "998933800525",  //Мобильный телефон
        "Oked": 62090,  //ОКЭД
        "Account": "20208000905656222001",  //Расчетный счет
        "BankId": "00401"  //МФО
    },
    "Clients": [
        {
            "BranchCode": "",  //Код филиала
            "BranchName": "",  //Наименование филиала
            "Tin": "302936161",  //Покупатель:ИНН юр.лица либо ПИНФЛ *
            "Name": "\"VENKON GROUP\" MCHJ",  //Наименование покупателя *
            "FizTin": "41101926570017",  //ПИНФЛ физ. лица *
            "Fio": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //ФИО физ. лица *
            "Address": "Фидойилар МФЙ, Махтумкули кучаси,  ",  //Адрес
            "WorkPhone": "",  //Рабочий телефон
            "Mobile": "",  //Мобильный телефон
            "Oked": "62010",  //ОКЭД
            "Account": "20208000400308125001",  //Расчетный счет
            "BankId": "00974"  //МФО
        }
    ],
    "Parts": [  //Разделы договора
        {
            "ordno": 1,  //Порядковый номер *
            "title": "тест1",  //Название раздела *
            "body": "тест2"  //Текст раздела *
        }
    ],
    "Products": [  //Товары/услуги договора
        {
            "OrdNo": 1,  //Порядковый номер *
            "Name": "тест",  //Наименование товара *
            "CatalogCode": "08471001001000000",  //Код ИКПУ *
            "CatalogName": "Ноутбук",  //Наименование ИКПУ *
            "Barcode": "",  //Штрихкод
            "MeasureId": null,  //Единица измерения *
            "PackageCode": "1501886",  //Код упаковки *
            "PackageName": "шт.",  //Наименование упаковки
            "Count": "10",  //Количество
            "Summa": "10",  //Цена за единицу *
            "DeliverySum": "100.00",  //Сумма поставки *
            "VatRate": "12",  //Ставка НДС *
            "VatSum": "12.00",  //Сумма НДС *
            "DeliverySumWithVat": "112.00",  //Сумма поставки с НДС *
            "WithoutVat": false  //true – если поставляется без НДС, false – если с НДС
        }
    ],
    "HasVat": true  //true – если в списке товаров договора имеются позиции с НДС, false – если нет
}
```
```json
{
    "document_json": {
        "didoxorderid": "",
        "contractdoc": {
            "contractname": "тест",
            "contractno": "тест",
            "contractdate": "2025-02-07",
            "contractexpiredate": "2025-02-07",
            "contractplace": "тест"
        },
        "owner": {
            "tin": "310529901",
            "name": "\"DIDOX TECH\" MCHJ",
            "branchcode": "",
            "branchname": "",
            "fiztin": "32901930460050",
            "fio": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
            "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",
            "workphone": "998933800525",
            "mobile": "998933800525",
            "oked": 62090,
            "account": "20208000905656222001",
            "bankid": "00401"
        },
        "clients": [
            {
                "branchcode": "",
                "branchname": "",
                "tin": "302936161",
                "name": "\"VENKON GROUP\" MCHJ",
                "fiztin": "41101926570017",
                "fio": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
                "address": "Фидойилар МФЙ, Махтумкули кучаси,  ",
                "workphone": "",
                "mobile": "",
                "oked": "62010",
                "account": "20208000400308125001",
                "bankid": "00974"
            }
        ],
        "parts": [
            {
                "ordno": 1,
                "title": "тест1",
                "body": "тест2"
            }
        ],
        "products": [
            {
                "ordno": 1,
                "name": "тест",
                "catalogcode": "08471001001000000",
                "catalogname": "Ноутбук",
                "barcode": "",
                "measureid": null,
                "packagecode": "1501886",
                "packagename": "шт.",
                "count": "10",
                "summa": "10",
                "deliverysum": "100.00",
                "vatrate": "12",
                "vatsum": "12.00",
                "exciserate": 0,
                "excisesum": 0,
                "deliverysumwithvat": "112.00",
                "withoutvat": false
            }
        ],
        "hasvat": true,
        "contractid": "67a5e8d8727ad501d5f2a795",
        "sellertin": "310529901",
        "buyertin": null
    }
}
```

# 8. Произвольный документ

Произвольный документ - Это внутренний документ Didox, в котором доступна возможность загружать любой файл в PDF формате размером не больше 10мб. Данный документ не синхронизируется с другими операторами и Роуминговым центром

### Пример Произвольного документ в структуре JSON:

* SubTypes
* JSON
* Response _200_

Код | Наименование  
---|---  
1 | Акт сверки  
2 | Письмо  
3 | Договор  
4 | Счет на оплату  
5 | Акт выполненных работ  
6 | Другое  
7 | Заявка  
8 | Спецификация  
9 | Доп. соглашение  
10 | Акт приема-передачи
```json
{
    "data": {
        "Document": {
            "DocumentNo": "тест",  //Номер документа *
            "DocumentDate": "2025-02-07",  //Дата документа *
            "DocumentName": "тест"  //Наименование документа
        },
        "Subtype": 6,
        "ContractDoc": {
            "ContractNo": "тест",  //Номер договора
            "ContractDate": "2025-02-07"  //Дата договора
        },
        "SellerTin": "310529901",  //Поставщик:ИНН юр.лица либо ПИНФЛ *
        "Seller": {
            "Name": "\"DIDOX TECH\" MCHJ",  //Наименование поставщика *
            "BranchCode": "",  //Код филиала
            "BranchName": "",  //Наименование филиала
            "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй"  //Адрес *
        },
        "BuyerTin": "302936161",  //Покупатель:ИНН юр.лица либо ПИНФЛ *
        "Buyer": {
            "Name": "\"VENKON GROUP\" MCHJ",  //Наименование покупателя *
            "Address": "Фидойилар МФЙ, Махтумкули кучаси,  ",  //Адрес *
            "BranchCode": "",  //Код филиала
            "BranchName": ""  //Наименование филиала
        }
    },
    "document": "data:application/pdf;base64,JVBERi0xLjQKJdPr6eEKMSAwIG9iago8PC9UaXRsZSAoYWJv..."  //PDF файл в формате base64
}
```
```json
{
    "document_json": {
        "didoxorderid": "",
        "document": {
            "documentno": "тест",
            "documentdate": "2025-02-07",
            "documentname": "тест"
        },
        "contractdoc": {
            "contractno": "тест",
            "contractdate": "2025-02-07"
        },
        "subtype": 6,      
        "sellertin": "310529901",
        "seller": {
            "name": "\"DIDOX TECH\" MCHJ",
            "branchcode": "",
            "branchname": "",
            "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй"
        },
        "buyertin": "302936161",
        "buyer": {
            "name": "\"VENKON GROUP\" MCHJ",
            "address": "Фидойилар МФЙ, Махтумкули кучаси,  ",
            "branchcode": "",
            "branchname": ""
        },
        "haspostcard": false,
        "documentid": "67a5f6addb36e626d6f58ef1",
        "url": "https://api.didox.uz/file/11efe54b9c2ffa44ab361e0008000075",
        "hash": "dcb1980370561c1246098bb8d3ca2a59"
    }
}
```  
  
# 9. Акт сверки

Акт сверки - это документ, составляемый двумя сторонами (между двумя юрлицами или юрлицом и ИП) с целью согласования платежей и внесения ясности, нет ли задолженности одного юрлица (или ИП) перед другим.

### Пример Акта сверки в структуре JSON:

* JSON
* Response _200_
```json
{
    "VerificationActDoc": {
        "VerificationActNo": "тест",  //Номер акта сверки *
        "VerificationActDate": "2025-02-07",  //Дата акта сверки *
        "VerificationActText": "Мы, нижеподписавшиеся, MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI от имени \"DIDOX TECH\" MCHJ, с одной стороны, 
        и MUKUMOVA SHAKHNOZA RUSTAMOVNA от имени \"VENKON GROUP\" MCHJ, с другой стороны, составили настоящий акт сверки о том, 
        что состояние взаимных расчётов по данным учёта следующее:"  //Текст акта сверки*
    },
    "VerificationActContracts": [
        {
            "ContractDate": "2025-02-07",  //Дата договора *
            "ContractNo": "тест1",  //Номер договора *
            "OpenBalance": {  //Сальдо начальное по договору
                "OwnerDebit": "1",  //Дебет по данным владельца *
                "OwnerCredit": "2",  //Кредит по данным владельца *
                "PartnerDebit": "2.00",  //Дебет по данным партнёра
                "PartnerCredit": "1.00"  //Кредит по данным партнёра
            },
            "CloseBalance": {  //Сальдо конечное по договору
                "OwnerDebit": "0.00",  //Дебет по данным владельца
                "OwnerCredit": "2.00",  //Кредит по данным владельца
                "PartnerDebit": "2.00",  //Дебет по данным партнёра
                "PartnerCredit": "0.00"  //Кредит по данным партнёра
            },
            "TotalBalance": {  //Итого по договору
                "OwnerDebit": "3.00",  //Дебет по данным владельца
                "OwnerCredit": "4.00",  //Кредит по данным владельца
                "PartnerDebit": "4.00",  //Дебет по данным партнёра
                "PartnerCredit": "3.00"  //Кредит по данным партнёра
            },
            "VerificationActContractItems": [
                {
                    "OwnerOperationDate": "2025-02-07",  //Дата операции первой стороны *
                    "OwnerOperationName": "тест2",  //Наименование операции *
                    "OwnerDebit": "3", //Дебет *
                    "OwnerCredit": "4",  //Кредит *
                    "PartnerOperationDate": "2025-02-07",  //Дата операции второй стороны *
                    "PartnerOperationName": "2",  //Наименование операции *
                    "PartnerDebit": "4.00",  //Дебет
                    "PartnerCredit": "3.00"  //Кредит
                }
            ]
        }
    ],
    "OwnerTin": "310529901",  //Владелец: ИНН юр.лица либо ПИНФЛ *
    "OwnerName": "\"DIDOX TECH\" MCHJ",  //Наименование *
    "OwnerBranchCode": "",  //Код филиала
    "OwnerBranchName": "",  //Наименование филиала
    "OwnerFizTin": "32901930460050",  //ПИНФЛ физ.лица *
    "OwnerFizFio": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI", //ФИО физ.лица *
    "PartnerTin": "302936161",  //Партнёр: ИНН юр.лица либо ПИНФЛ *
    "PartnerName": "\"VENKON GROUP\" MCHJ",  //Наименование *
    "PartnerFizTin": "41101926570017",  //ПИНФЛ физ.лица *
    "PartnerFizFio": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",  //ФИО физ.лица *
    "TurnoverBalance": {  //Обороты за период
        "OwnerDebit": "3.00",  //Дебет по данным владельца
        "OwnerCredit": "4.00",  //Кредит по данным владельца
        "PartnerDebit": "4.00",  //Дебет по данным партнёра
        "PartnerCredit": "3.00"  //Кредит по данным партнёра
    },
    "CloseBalance": {  //Сальдо конечное
        "OwnerDebit": "0.00",  //Дебет по данным владельца
        "OwnerCredit": "2.00",  //Кредит по данным владельца
        "PartnerDebit": "2.00",  //Дебет по данным партнёра
        "PartnerCredit": "0.00"  //Кредит по данным партнёра
    },
    "OpenBalance": {  //Сальдо начальное
        "OwnerCredit": "0.00",  //Кредит по данным владельца
        "OwnerDebit": "0.00",  //Дебет по данным владельца
        "PartnerCredit": "0.00",  //Кредит по данным партнёра
        "PartnerDebit": "0.00"  //Дебет по данным партнёра
    }
}
```
```json
{
    "document_json": {
        "verificationactid": "67a5f83e727ad501d5f2c832",
        "verificationactdoc": {
            "verificationactno": "тест",
            "verificationactdate": "2025-02-07",
            "verificationacttext": "Мы, нижеподписавшиеся, MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI от имени \"DIDOX TECH\" MCHJ, с одной стороны, и MUKUMOVA SHAKHNOZA RUSTAMOVNA от имени \"VENKON GROUP\" MCHJ, с другой стороны, составили настоящий акт сверки о том, что состояние взаимных расчётов по данным учёта следующее:"
        },
        "verificationactcontracts": [
            {
                "contractdate": "2025-02-07",
                "contractno": "тест1",
                "openbalance": {
                    "ownerdebit": "1",
                    "ownercredit": "2",
                    "partnerdebit": "2.00",
                    "partnercredit": "1.00"
                },
                "closebalance": {
                    "ownerdebit": "0.00",
                    "ownercredit": "2.00",
                    "partnerdebit": "2.00",
                    "partnercredit": "0.00"
                },
                "totalbalance": {
                    "ownerdebit": "3.00",
                    "ownercredit": "4.00",
                    "partnerdebit": "4.00",
                    "partnercredit": "3.00"
                },
                "verificationactcontractitems": [
                    {
                        "owneroperationdate": "2025-02-07",
                        "owneroperationname": "тест2",
                        "ownerdebit": "3",
                        "ownercredit": "4",
                        "partneroperationdate": "2025-02-07",
                        "partneroperationname": "2",
                        "partnerdebit": "4.00",
                        "partnercredit": "3.00"
                    }
                ]
            }
        ],
        "ownertin": "310529901",
        "ownername": "\"DIDOX TECH\" MCHJ",
        "ownerbranchcode": "",
        "ownerbranchname": "",
        "ownerfiztin": "32901930460050",
        "ownerfizfio": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
        "partnertin": "302936161",
        "partnername": "\"VENKON GROUP\" MCHJ",
        "partnerfiztin": "41101926570017",
        "partnerfizfio": "MUKUMOVA SHAKHNOZA RUSTAMOVNA",
        "turnoverbalance": {
            "ownerdebit": "3.00",
            "ownercredit": "4.00",
            "partnerdebit": "4.00",
            "partnercredit": "3.00"
        },
        "closebalance": {
            "ownerdebit": "0.00",
            "ownercredit": "2.00",
            "partnerdebit": "2.00",
            "partnercredit": "0.00"
        },
        "openbalance": {
            "ownercredit": "0.00",
            "ownerdebit": "0.00",
            "partnercredit": "0.00",
            "partnerdebit": "0.00"
        }
    }
}
```

# 10. Акт приёма передачи

Это документ, в котором подробно характеризуется передаваемый или получаемый товар или какие-либо материальные ценности, а так же отображается их общая денежная стоимость. Документ является двусторонним.

### Пример Акта приёма передачи в структуре JSON:

* JSON
* Response _200_
```json
{
    "AcceptanceTransferActDoc": {
        "AcceptanceTransferActNo": "тест",  //Номер акта приема-передачи
        "AcceptanceTransferActDate": "2025-02-10"  //Дата акта приема-передачи
    },
    "ContractDoc": {
        "ContractNo": "тест",  //Номер договора
        "ContractDate": "2025-02-10"  //Дата договора
    },
    "SellerPinfl": "30606950270086",  //ПИНФЛ продавца
    "Seller": {
        "Name": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI",  //Наименование продавца
        "BankId": "",
        "Account": "",
        "Address": "Мирзо-Улугбекский район ТУРОН МФЙ, ПАРКЕНТ ДАХАСИ,  uy:14 xonadon:18"  //Адрес продавца
    },
    "BuyerTinOrPinfl": "302936161",  //ИНН/ПИНФЛ покупателя
    "Buyer": {
        "Name": "\"VENKON GROUP\" MCHJ",  //Наименование покупателя
        "VatRegCode": "326040002521",  //Регистрационный номер плательщика НДС
        "VatRegStatus": 20,  //Статус плательщика НДС
        "Account": "20208000400308125001",  //Расчетный счет покупателя
        "BankId": "00974",  //МФО банка покупателя
        "Address": "Фидойилар МФЙ, Махтумкули кучаси,  ",  //Адрес покупателя
        "BranchCode": "",  //Код филиала
        "BranchName": ""  //Наименование филиала
    },
    "totalPrice": "1.00",  //Общая сумма
    "Products": [
        {
            "OrdNo": 1,  //Порядковый номер
            "CatalogCode": "00701001001004001",  //Код ИКПУ
            "CatalogName": "Картошка Семенная картошка Семенная картошка",  //Наименование ИКПУ
            "Name": "тест",  //Наименование товара
            "MeasureId": "1",  //Единица измерения
            "PackageCode": "",  //Код упаковки
            "PackageName": "",  //Наименование упаковки
            "Count": "1",  //Количество
            "Summa": "1",  //Цена
            "DeliverySum": "1.00",  //Сумма доставки 
            "TotalPrice": ""  //Общая сумма
        }
    ]
}
```
```json
{
    "document_json": {
        "acceptancetransferactdoc": {
            "acceptancetransferactno": "тест",
            "acceptancetransferactdate": "2025-02-10"
        },
        "contractdoc": {
            "contractno": "тест",
            "contractdate": "2025-02-10"
        },
        "sellerpinfl": "30606950270086",
        "seller": {
            "name": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI",
            "bankid": "",
            "account": "",
            "address": "Мирзо-Улугбекский район ТУРОН МФЙ, ПАРКЕНТ ДАХАСИ,  uy:14 xonadon:18"
        },
        "buyertinorpinfl": "302936161",
        "buyer": {
            "name": "\"VENKON GROUP\" MCHJ",
            "vatregcode": "326040002521",
            "vatregstatus": 20,
            "account": "20208000400308125001",
            "bankid": "00974",
            "address": "Фидойилар МФЙ, Махтумкули кучаси,  ",
            "branchcode": "",
            "branchname": ""
        },
        "totalprice": "1.00",
        "products": [
            {
                "id": "",
                "ordno": 1,
                "catalogcode": "00701001001004001",
                "catalogname": "Картошка Сергеевна картошка Семенная картошка",
                "name": "тест",
                "measureid": "1",
                "packagecode": "",
                "packagename": "",
                "count": "1",
                "summa": "1",
                "deliverysum": "1.00",
                "totalprice": ""
            }
        ],
        "acceptancetransferactid": "67a992894b6a23ea04b5a472"
    }
}
```

# 11. Многосторонний произвольный документ

Многосторонний произвольный документ - Это внутренний документ Didox, в котором доступна возможность загружать любой файл в PDF формате размером не больше 10мб. Данный документ не синхронизируется с другими операторами и Роуминговым центром

### Пример Многостороннего произвольного документ в структуре JSON:

* JSON
* Response _200_
```json
{
    "data": {
        "Document": {
            "DocumentNo": "тест",  //Номер документа *
            "DocumentDate": "2025-02-10",  //Дата документа
            "DocumentName": "тест"  //Наименование документа
        },
        "ContractDoc": {
            "ContractNo": "тест",  //Номер договора *
            "ContractDate": "2025-02-10"  //Дата договора
        },
        "Owner": {
            "Tin": "310529901",  //Поставщик:ИНН юр.лица либо ПИНФЛ *
            "Name": "\"DIDOX TECH\" MCHJ",  //Наименование поставщика *
            "BranchCode": "",  //Код филиала
            "BranchName": "",  //Наименование филиала
            "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй"  //Адрес поставщика
        },
        "Clients": [
            {
                "Tin": "302936161",  //Покупатель 1:ИНН юр.лица либо ПИНФЛ *
                "Name": "\"VENKON GROUP\" MCHJ",  //Наименование покупателя 1 *
                "Address": "Фидойилар МФЙ, Махтумкули кучаси,  "  //Адрес покупателя 1
            },
            {
                "Tin": "207119963",  //Покупатель 2:ИНН юр.лица либо ПИНФЛ
                "Name": "\"WEBMEDIA INFORMATION\" MCHJ",  //Наименование покупателя 2 *
                "Address": "Bogʻi boʻston MFY,  Bog‘ishamol ko'chasi, 3 tor ko'chasi , 29-uy  "  //Адрес покупателя 2
            }
        ]
    },
    "document": "data:application/pdf;base64,JVBERi0xLjQKJdPr6eEKMSAwIG9iago8PC..."  //PDF файл в формате base64
}
```
```json
{
    "document_json": {
        "didoxorderid": "",
        "document": {
            "documentno": "тест",
            "documentdate": "2025-02-10",
            "documentname": "тест"
        },
        "contractdoc": {
            "contractno": "тест",
            "contractdate": "2025-02-10"
        },
        "owner": {
            "tin": "310529901",
            "name": "\"DIDOX TECH\" MCHJ",
            "branchcode": "",
            "branchname": "",
            "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй"
        },
        "clients": [
            {
                "tin": "302936161",
                "name": "\"VENKON GROUP\" MCHJ",
                "address": "Фидойилар МФЙ, Махтумкули кучаси,  "
            },
            {
                "tin": "207119963",
                "name": "\"WEBMEDIA INFORMATION\" MCHJ",
                "address": "Bogʻi boʻston MFY,  Bog‘ishamol ko'chasi, 3 tor ko'chasi , 29-uy  "
            }
        ],
        "documentid": "67a993e48b63152c473cc6a8",
        "url": "https://api.didox.uz/file/11efe773145b9766a8d01e0008000075",
        "hash": "dcb1980370561c1246098bb8d3ca2a59"
    }
}
```

# 12. Протокол собрания учредителей

Протокол собрания учредителей - Это внутренний документ Didox, документальный способ фиксации результатов собрания собственников ООО по принятию решений относительно компании, таких, как принятие/увольнение директора, смена юридического адреса, распределение чистой прибыли, выплата дивидендов и т.д. Данный документ не синхронизируется с другими операторами и Роуминговым центром

### Пример Протокол собрания учредителей в структуре JSON:

* JSON
* Response _200_
```json
{
    "documentdoc": {
        "documentname": "тест",  //Название документа
        "documentno": "тест1",  //Номер документа
        "documentplace": "тест2",  //Место составления
        "documentdate": "2025-02-10"  //Дата составления
    },
    "company": {
        "tin": "310529901",  //Поставщик:ИНН юр.лица либо ПИНФЛ *
        "name": "\"DIDOX TECH\" MCHJ",  //Поставщик:Наименование юр.лица либо ФИО ФЛ *
        "fiztin": "32901930460050",  //Покупатель:ПИНФЛ *
        "fio": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",  //Покупатель:ФИО *
        "bankid": "00401",  //МФО банка
        "oked": 62090,  //ОКЭД
        "account": "20208000905656222001",  //Расчетный счет
        "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",  //Юридический адрес
        "workphone": "998933800525",  //Телефон
        "mobile": "998933800525"  //Мобильный телефон
    },
    "participants": [
        {
            "tin": "30606950270086",  //ПИНФЛ
            "name": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI",  //ФИО
            "companyTaxId": "",  //ИНН юр.лица
            "companyname": "",  //Наименование юр.лица
            "share": "60",  //Доля
            "citizenship": "РУз",  //Гражданство
            "ischairman": true,  //Председатель
            "issecretary": false  //Секретарь
        },
        {
            "tin": "50106026830029",  //ПИНФЛ
            "name": "MAMATQULOV SANJAR XAMZALI O‘G‘LI",  //ФИО
            "companyTaxId": "302936161",  //ИНН юр.лица
            "companyname": "\"VENKON GROUP\" MAS'ULIYATI CHEKLANGAN JAMIYAT",  //Наименование юр.лица
            "share": "40",  //Доля
            "citizenship": "РУз",  //Гражданство
            "ischairman": false,  //Председатель
            "issecretary": true  //Секретарь
        }
    ],
    "parts": [
        {
            "ordno": 1,  //Порядковый номер
            "title": "На собрании присутствуют Участники \"DIDOX TECH\" MCHJ физические лица",  //Наименование
            "body": "1. гр-н РУз  SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI, владеющий 60% доли в уставном капитале Общества\n2. \"VENKON GROUP\" MAS'ULIYATI CHEKLANGAN JAMIYAT (ИНН: 302936161) 
            владеющее 40% доли в уставном капитале Общества, 
            в лице MAMATQULOV SANJAR XAMZALI O‘G‘LI\n"  //Содержание
        }
    ]
}
```
```json
{
    "document_json": {
        "documentdoc": {
            "documentname": "тест",
            "documentno": "тест1",
            "documentplace": "тест2",
            "documentdate": "2025-02-10"
        },
        "company": {
            "tin": "310529901",
            "name": "\"DIDOX TECH\" MCHJ",
            "fiztin": "32901930460050",
            "fio": "MAXMUDOV BEHRUZJON RAVSHAN O‘G‘LI",
            "bankid": "00401",
            "oked": 62090,
            "account": "20208000905656222001",
            "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси, 114а-уй",
            "workphone": "998933800525",
            "mobile": "998933800525"
        },
        "participants": [
            {
                "tin": "30606950270086",
                "name": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI",
                "companyname": "",
                "share": "60",
                "citizenship": "РУз",
                "ischairman": true,
                "issecretary": false,
                "companytaxid": ""
            },
            {
                "tin": "50106026830029",
                "name": "MAMATQULOV SANJAR XAMZALI O‘G‘LI",
                "companyname": "\"VENKON GROUP\" MAS'ULIYATI CHEKLANGAN JAMIYAT",
                "share": "40",
                "citizenship": "РУз",
                "ischairman": false,
                "issecretary": true,
                "companytaxid": "302936161"
            }
        ],
        "parts": [
            {
                "ordno": 1,
                "title": "На собрании присутствуют Участники \"DIDOX TECH\" MCHJ физические лица",
                "body": "1. гр-н РУз  SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI, владеющий 60% доли в уставном капитале Общества\n2. \"VENKON GROUP\" MAS'ULIYATI CHEKLANGAN JAMIYAT (ИНН: 302936161) владеющее 40% доли в уставном капитале Общества, в лице MAMATQULOV SANJAR XAMZALI O‘G‘LI\n"
            }
        ],
        "documentid": "11efe7743de95b8abf151e0008000075"
    }
}
```

# 13. Письмо НК

Письмо НК

### Пример структуры JSON:

* JSON
* Response _200_
```json
{
    "LetterDoc": {
        "No": "тест",
        "Date": "2025-09-19"
    },
    "Sender": {
        "TinOrPinfl": "302936161",
        "BranchCode": "",
        "BranchName": "",
        "Name": "\"VENKON GROUP\" MCHJ",
        "Address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси,",
        "Head": {
            "Pinfl": "30606950270086",
            "FullName": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI",
            "Position": "Сотрудник"
        },
        "Email": "",
        "Website": null,
        "BankId": "00974",
        "BankAccount": "20208000400308125001",
        "LogoBase64": "",
        "Phones": [
            "(+998 93) 541-28-73"
        ]
    },
    "Recipient": {
        "TinOrPinfl": "50106026830029",
        "Name": "MAMATQULOV SANJAR XAMZALI O‘G‘LI",
        "Address": "город Алмалык Ташкентская область, г.Алмалык, Юлдуз, Иванова, дом 20",
        "BranchCode": "",
        "BranchName": ""
    },
    "HtmlContent": "<div style=\"\n    font-family: 'Roboto', sans-serif;\n    font-size: 16px;\n    line-height: 1.5;\n  \"><p style=\"margin: 0 0 10px 0; \">Тест</p></div>",
    "Attachments": [
        {
            "Filename": "рыба.pdf",
            "MimeType": "application/pdf",
            "Size": 77123,
            "Description": "",
            "ContentBase64": "JVBERi0xLjQNJeLjz9MNCjYgMCBvYmogPDwvTGluZWFyaXplZCAxL0wgNzcxMjMvTyA4L0UgNzI5MDcvTiAxL1QgNzY5NTcvSCBbIDg5NiAyMDNdPj4NZW5kb2JqDSAgICAgICAgICAgICAgICAgICAgDQp4cmVmDQo2IDMwDQowMDAwMDAwMDE2IDAwMDAwIG4NCjAwMDAwMDEwOTkgMDAwMDAgbg0KMDAwMDAwMTE3NSAwMDAwMCBuDQowMDAwMDAxMzU3IDAwMDAwIG4NCjAwMDAwMDE0N..."
        }
    ]
}
```
```json
{
    "pending_document": {
        "document_json": {
            "letterdoc": {
                "no": "тест",
                "date": "2025-09-19"
            },
            "sender": {
                "tinorpinfl": "302936161",
                "branchcode": "",
                "branchname": "",
                "name": "\"VENKON GROUP\" MCHJ",
                "address": "ГОРОД ТАШКЕНТ ЯШНАБАДСКИЙ РАЙОН Фидойилар МФЙ, Махтумкули кучаси,",
                "head": {
                    "pinfl": "30606950270086",
                    "fullname": "SAYFULLAYEV SIROJBEK OYBEK O‘G‘LI",
                    "position": "Сотрудник"
                },
                "email": "",
                "website": null,
                "bankid": "00974",
                "bankaccount": "20208000400308125001",
                "logobase64": "",
                "phones": [
                    "(+998 93) 541-28-73"
                ]
            },
            "recipient": {
                "tinorpinfl": "50106026830029",
                "name": "MAMATQULOV SANJAR XAMZALI O‘G‘LI",
                "address": "город Алмалык Ташкентская область, г.Алмалык, Юлдуз, Иванова, дом 20",
                "branchcode": "",
                "branchname": ""
            },
            "htmlcontent": "<div style=\"font-family:Roboto, sans-serif;font-size:16px;line-height:1.5;\"><p style=\"margin:0 0 10px 0;\">Тест</p></div>",
            "attachments": [
                {
                    "filename": "рыба.pdf",
                    "mimetype": "application/pdf",
                    "size": 77123,
                    "description": "",
                    "contentbase64": "JVBERi0xLjQNJeLjz9MNCjYgMCBvYmogPDwvTGluZWFyaXplZCAxL0wgNzcxMjMvTyA4L0UgNzI5MDcvTiAxL1QgNzY5NTcvSCBbIDg5NiAyMDNdPj4NZW5kb2JqDSAgICAgICAgICAgICAgICAgICAgDQp4cmVmDQo2IDMwDQowMDAwMDAwMDE2IDAwMDAwIG4NCjAwMDAwMDEwOTkgMDAwMDAgbg0KMDAwMDAwMTE3NSAwMDAwMCBuDQowMDAwMDAxMzU3IDAwMDAwIG4NCjAwMDAwMDE0NzMgMDAwMDAgbg0KMDAwMDAwMTYwNyAwMDAwMCBuDQowMDAwMDAxODkwIDAwMDAwIG4NCjAwMDAwMDIwMTkgMDAwMDAgbg0KMDA..."
                }
            ],
            "letterid": "68ccfbd43c68f71252944533"
        }
    },
    "_id": "11f095241b940c8ebbb93aefc31432bf",
    "created_date": "2025-09-19 11:44:36"
}
```

# 14. Гибридная счет-фактура

### Пример гибридной счет-фактуры:

* JSON
* Response _200_
```json
{
    "HasMedicalEquipment": false, // Признак наличия медицинского оборудования
    "HybridInvoiceType": 0, // Тип гибридного счета-фактуры (код/перечисление)
    "HybridInvoiceDoc": { // Данные текущего гибридного счета-фактуры
        "No": "тест", // Номер документа
        "Date": "2026-04-21" // Дата документа
    },
    "ContractDoc": { // Данные договора
        "No": "тест", // Номер договора
        "Date": "2026-04-21" // Дата договора
    },
    "OldHybridInvoiceDoc": null, // Предыдущий гибридный счет-фактура (если есть)

    "Seller": { // Продавец (отправитель)
        "TinOrPinfl": "310529901", // ИНН или ПИНФЛ
        "TaxpayerType": 10, // Тип налогоплательщика (код)
        "BranchCode": "", // Код филиала
        "Name": "\"DIDOX TECH\" MCHJ", // Название организации
        "VatRegCode": "", // Код регистрации по НДС
        "AccountNumber": "20208000905656222001", // Расчетный счет
        "BankMfo": "00401", // МФО банка
        "Address": "12312312231", // Адрес
        "Director": "Директор", // Руководитель
        "Accountant": "Бухгалтер", // Бухгалтер
        "BranchName": "", // Название филиала
        "VatRegStatus": "" // Статус НДС
    },

    "ItemReleased": { // Лицо, отпустившее товар
        "Pinfl": "ПИНФЛ", // ПИНФЛ
        "FullName": "ФИО" // ФИО
    },

    "Buyer": { // Покупатель (получатель)
        "TinOrPinfl": "302936161", // ИНН или ПИНФЛ
        "TaxpayerType": 30, // Тип налогоплательщика
        "BranchCode": "", // Код филиала
        "Name": "\"VENKON GROUP\" MCHJ", // Название
        "VatRegCode": "", // Код НДС
        "AccountNumber": "20208000400308125001", // Счет
        "BankMfo": "00974", // МФО
        "Address": "г. Ташкент, ЯШНАБАДСКИЙ РАЙОН...", // Адрес
        "Director": "Director", // Директор
        "Accountant": "Accountant", // Бухгалтер
        "BranchName": "", // Название филиала
        "VatRegStatus": "" // Статус НДС
    },

    "HasBarcode": false, // Есть ли штрихкод у товаров
    "HasCommittent": false, // Есть ли комитент (доверитель)
    "HasTaxRelief": false, // Есть ли налоговые льготы
    "HasExcise": false, // Есть ли акциз
    "HasMarking": false, // Есть ли маркировка
    "Roadway": { // Транспортная часть (перевозка)
        "ProductGroups": [ // Группы товаров
            {
                "ProductInfo": { // Информация по товарам
                    "Products": [ // Список товаров
                        {
                            "OrdNo": 1, // Порядковый номер
                            "Committent": null, // Комитент
                            "TaxRelief": null, // Льготы
                            "Marks": null, // Маркировка
                            "Excise": null, // Акциз
                            "Name": "тест", // Название товара
                            "CatalogCode": "08471001001000000", // Код каталога
                            "CatalogName": "Ноутбук", // Название из каталога
                            "PackageCode": "1501886", // Код упаковки
                            "PackageName": "шт.", // Единица измерения
                            "Barcode": "", // Штрихкод
                            "Amount": "12", // Количество
                            "Price": "34", // Цена за единицу
                            "DeliverySum": "408.00", // Сумма без НДС
                            "Vat": { // НДС
                                "Rate": "12", // Ставка НДС (%)
                                "Sum": "48.96" // Сумма НДС
                            },
                            "DeliverySumWithVat": "456.96", // Сумма с НДС
                            "Origin": 4 // Происхождение товара (код)
                        }
                    ],
                    "TotalDeliverySum": "408.00", // Общая сумма без НДС
                    "TotalVatSum": "48.96", // Общая сумма НДС
                    "TotalDeliverySumWithVat": "456.96" // Общая сумма с НДС
                },
                "LoadingPoint": { // Точка загрузки
                    "RegionName": "город Ташкент", // Регион
                    "RegionId": 26, // Код региона
                    "DistrictName": "Мирзо-Улугбекский район", // Район
                    "DistrictCode": 2, // Код района
                    "Address": "Шастри, Паркент" // Адрес загрузки
                },
                "UnloadingPoint": { // Точка разгрузки
                    "RegionName": "город Ташкент", // Регион
                    "RegionId": 26, // Код региона
                    "DistrictName": "Мирзо-Улугбекский район", // Район
                    "DistrictCode": 2, // Код района
                    "Address": "street123, adres 123" // Адрес разгрузки
                }
            }
        ],
        "OtherCarOwners": null, // Другие владельцы транспорта
        "Truck": { // Основной транспорт
            "RegNo": "01 350 AAA", // Госномер
            "Model": "MALIBU 2" // Модель
        },
        "Trailer": null, // Прицеп, если нет, то передавать null
        "Carriages": [], // Дополнительные перевозки/рейсы, если нет, то передавать null или []
        "Driver": { // Водитель
            "Pinfl": "ПИНФЛ", // ПИНФЛ
            "FullName": "ФИО" // ФИО
        }
    },

    "FreightForwarder": null, // Экспедитор, если нет, то передавать null
    "Carrier": { // Перевозчик
        "TinOrPinfl": "ИНН", // ИНН/ПИНФЛ
        "Name": "тест", // Название
        "BranchCode": "", // Код филиала
        "BranchName": "" // Название филиала
    },
    "Client": null, // Клиент (если отличается от покупателя), если нет, то передавать null
    "Payer": null, // Плательщик (если отличается), если нет, то передавать null

    "TransportType": 1, // Тип транспорта (код)
    "ResponsibleToGoods": { // Ответственный за груз
        "TinOrPinfl": "ПИНФЛ", // ИНН/ПИНФЛ
        "Name": "ФИО" // ФИО
    },

    "TotalDistance": "11", // Общая дистанция перевозки
    "TotalDeliveryCost": "22", // Стоимость доставки
    "TotalWeightBrutto": "22", // Вес брутто
    "TotalWeightNetto": "11", // Вес нетто

    "Empowerment": null, // Доверенность/уполномочивание
}
```
```json
{
    "pending_document": {
        "document_json": {
            "hasmedicalequipment": false,
            "hybridinvoicetype": 0,
            "hybridinvoicedoc": {
                "no": "тест",
                "date": "2026-04-21"
            },
            "contractdoc": {
                "no": "тест",
                "date": "2026-04-21"
            },
            "oldhybridinvoicedoc": null,
            "seller": {
                "tinorpinfl": "310529901",
                "taxpayertype": 10,
                "branchcode": "",
                "name": "\"DIDOX TECH\" MCHJ",
                "vatregcode": "",
                "accountnumber": "20208000905656222001",
                "bankmfo": "00401",
                "address": "12312312231",
                "director": "Директор",
                "accountant": "Бухгалтер",
                "branchname": "",
                "vatregstatus": ""
            },
            "itemreleased": {
                "pinfl": "pinfl",
                "fullname": "fullname"
            },
            "buyer": {
                "tinorpinfl": "302936161",
                "taxpayertype": 30,
                "branchcode": "",
                "name": "name",
                "vatregcode": "",
                "accountnumber": "20208000400308125001",
                "bankmfo": "00974",
                "address": "г. Ташкент, ЯШНАБАДСКИЙ РАЙОН, Фидойилар МФЙ, Махтумкули кучаси,  ",
                "director": "director",
                "accountant": "accountant",
                "branchname": "",
                "vatregstatus": ""
            },
            "hasbarcode": false,
            "hascommittent": false,
            "hastaxrelief": false,
            "hasexcise": false,
            "hasmarking": false,
            "roadway": {
                "productgroups": [
                    {
                        "productinfo": {
                            "products": [
                                {
                                    "ordno": 1,
                                    "committent": null,
                                    "taxrelief": null,
                                    "marks": null,
                                    "excise": null,
                                    "name": "тест",
                                    "catalogcode": "08471001001000000",
                                    "catalogname": "Ноутбук",
                                    "packagecode": "1501886",
                                    "packagename": "шт.",
                                    "barcode": "",
                                    "amount": "12",
                                    "price": "34",
                                    "deliverysum": "408.00",
                                    "vat": {
                                        "rate": "12",
                                        "sum": "48.96"
                                    },
                                    "deliverysumwithvat": "456.96",
                                    "origin": 4
                                }
                            ],
                            "totaldeliverysum": "408.00",
                            "totalvatsum": "48.96",
                            "totaldeliverysumwithvat": "456.96"
                        },
                        "loadingpoint": {
                            "regionname": "город Ташкент",
                            "regionid": 26,
                            "districtname": "Мирзо-Улугбекский район",
                            "districtcode": 2,
                            "address": "Шастри, Паркент"
                        },
                        "unloadingpoint": {
                            "regionname": "город Ташкент",
                            "regionid": 26,
                            "districtname": "Мирзо-Улугбекский район",
                            "districtcode": 2,
                            "address": "street123, adres 123"
                        }
                    }
                ],
                "othercarowners": null,
                "truck": {
                    "regno": "01 350 AAA",
                    "model": "MALIBU 2"
                },
                "trailer": null,
                "carriages": [],
                "driver": {
                    "pinfl": "pinfl",
                    "fullname": "fullname"
                }
            },
            "freightforwarder": null,
            "carrier": {
                "tinorpinfl": "tinorpinfl",
                "name": "name",
                "branchcode": "",
                "branchname": ""
            },
            "client": null,
            "payer": null,
            "transporttype": 1,
            "responsibletogoods": {
                "tinorpinfl": "tinorpinfl",
                "name": "name"
            },
            "totaldistance": "11",
            "totaldeliverycost": "22",
            "totalweightbrutto": "22",
            "totalweightnetto": "11",
            "empowerment": null,
            "hybridinvoiceid": "69eb5d0644272587b581ae2f"
        }
    },
    "_id": "2d58b0ac3fd611f1891eb690e2d076a6",
    "created_date": "2026-04-24 17:07:34"
}
```

# 15. Гибридная счет-фактура (ФАРМ)

### Пример гибридной счет-фактуры(ФАРМ):

* JSON
* Response _200_
```json
{
    "HasMedicalEquipment": true, // Признак наличия медицинских товаров/оборудования
    "HybridInvoiceType": 0, // Тип гибридного счета-фактуры (код)
    "HybridInvoiceDoc": { // Текущий гибридный счет-фактура
        "No": "тест", // Номер документа
        "Date": "2026-04-21" // Дата документа
    },
    "ContractDoc": { // Договор
        "No": "тест", // Номер договора
        "Date": "2026-04-21" // Дата договора
    },
    "OldHybridInvoiceDoc": null, // Предыдущий счет-фактура (если есть)

    "Seller": { // Продавец
        "TinOrPinfl": "tinorpinfl", // ИНН или ПИНФЛ
        "TaxpayerType": 10, // Тип налогоплательщика
        "BranchCode": "", // Код филиала
        "Name": "name", // Название организации
        "VatRegCode": "", // Код регистрации по НДС
        "AccountNumber": "AccountNumber", // Расчетный счет
        "BankMfo": "00401", // МФО банка
        "Address": "12312312231", // Адрес
        "Director": "Director", // Руководитель
        "Accountant": "Accountant", // Бухгалтер
        "BranchName": "", // Название филиала
        "VatRegStatus": "" // Статус НДС
    },

    "ItemReleased": null, // Лицо, отпустившее товар (если не указано)

    "Buyer": { // Покупатель
        "TinOrPinfl": "tinorpinfl", // ИНН или ПИНФЛ
        "TaxpayerType": 30, // Тип налогоплательщика
        "BranchCode": "", // Код филиала
        "Name": "name", // Название
        "VatRegCode": "", // Код НДС
        "AccountNumber": "20208000400308125001", // Счет
        "BankMfo": "00974", // МФО
        "Address": "Address", // Адрес
        "Director": "director", // Руководитель
        "Accountant": "Accountant", // Бухгалтер
        "BranchName": "", // Название филиала
        "VatRegStatus": "" // Статус НДС
    },

    "HasBarcode": false, // Наличие штрихкодов
    "HasCommittent": false, // Наличие комитента
    "HasTaxRelief": true, // Признак применения налоговых льгот
    "HasMarking": false, // Признак наличия маркировки

    "Roadway": { // Блок перевозки
        "ProductGroups": [ // Группы товаров
            {
                "ProductInfo": { // Информация по товарам
                    "Products": [ // Список товаров
                        {
                            "OrdNo": 1, // Порядковый номер
                            "Committent": null, // Комитент
                            
                            "Medical": { // Медицинские параметры (так как HasMedicalEquipment = true)
                                "BaseSumma": "31", // Базовая стоимость (для расчета)
                                "ProfitRate": "2", // Норма прибыли (% или коэффициент)
                                "Serial": "фывй", // Серийный номер
                                "DispenseType": 1 // Тип отпуска (код)
                            },

                            "TaxRelief": { // Налоговая льгота
                                "Id": "102387", // Идентификатор льготы
                                "Name": "УП-5099 ...", // Описание/основание льготы
                                "VatSum": "87.27", // Сумма НДС под льготой
                                "Type": 1 // Тип льготы (код)
                            },

                            "Marks": null, // Маркировка
                            "Excise": null, // Акциз

                            "Name": "тест123", // Название товара
                            "CatalogCode": "08471001001000000", // Код каталога
                            "CatalogName": "Ноутбук", // Название из каталога

                            "PackageCode": "1501886", // Код упаковки
                            "PackageName": "шт.", // Единица измерения

                            "Barcode": "", // Штрихкод

                            "Amount": "23", // Количество
                            "Price": "31.62", // Цена за единицу

                            "DeliverySum": "727.26", // Сумма без НДС

                            "Vat": { // НДС
                                "Rate": "12", // Ставка НДС
                                "Sum": "87.27" // Сумма НДС
                            },

                            "DeliverySumWithVat": "814.53", // Сумма с НДС
                            "Origin": 4 // Происхождение товара (код)
                        }
                    ],

                    "TotalDeliverySum": "727.26", // Общая сумма без НДС
                    "TotalVatSum": "87.27", // Общая сумма НДС
                    "TotalDeliverySumWithVat": "814.53" // Общая сумма с НДС
                },

                "LoadingPoint": { // Точка загрузки
                    "RegionName": "город Ташкент", // Регион
                    "RegionId": 26, // Код региона
                    "DistrictName": "Яшнободский район", // Район
                    "DistrictCode": 8, // Код района
                    "Address": "qwe, 123" // Адрес
                },

                "UnloadingPoint": { // Точка разгрузки
                    "RegionName": "город Ташкент", // Регион
                    "RegionId": 26, // Код региона
                    "DistrictName": "Мирзо-Улугбекский район", // Район
                    "DistrictCode": 2, // Код района
                    "Address": "street123, adres 123" // Адрес
                }
            }
        ],

        "OtherCarOwners": null, // Другие владельцы транспорта

        "Truck": { // Основной транспорт
            "RegNo": "01 351 AAA", // Госномер
            "Model": "MALIBU 2" // Модель
        },

        "Trailer": null, // Прицеп, если нет, то передавать null
        "Carriages": [], // Дополнительные перевозки, если нет, то передавать null или []

        "Driver": { // Водитель
            "Pinfl": "pinfl", // ПИНФЛ
            "FullName": "FullName" // ФИО
        }
    },

    "FreightForwarder": null, // Экспедитор, если нет, то передавать null
    "Carrier": { // Перевозчик
        "TinOrPinfl": "tinorpinfl", // ИНН/ПИНФЛ
        "Name": "name", // Название
        "BranchCode": "", // Код филиала
        "BranchName": "" // Название филиала
    },

    "Client": null, // Клиент, если нет, то передавать null
    "Payer": null, // Плательщик, если нет, то передавать null

    "TransportType": 1, // Тип транспорта

    "ResponsibleToGoods": { // Ответственный за груз
        "TinOrPinfl": "TinOrPinfl", // ИНН/ПИНФЛ
        "Name": "Name" // ФИО/название
    },

    "TotalDistance": "12", // Общая дистанция
    "TotalDeliveryCost": "21", // Стоимость доставки
    "TotalWeightBrutto": "21", // Вес брутто
    "TotalWeightNetto": "2", // Вес нетто

    "Empowerment": null // Доверенность
}
```
```json
{
    "pending_document": {
        "document_json": {
            "hasmedicalequipment": true,
            "hybridinvoicetype": 0,
            "hybridinvoicedoc": {
                "no": "тест",
                "date": "2026-04-21"
            },
            "contractdoc": {
                "no": "тест",
                "date": "2026-04-21"
            },
            "oldhybridinvoicedoc": null,
            "seller": {
                "tinorpinfl": "tinorpinfl",
                "taxpayertype": 10,
                "branchcode": "",
                "name": "name",
                "vatregcode": "",
                "accountnumber": "accountnumber",
                "bankmfo": "00401",
                "address": "12312312231",
                "director": "director",
                "accountant": "Accountant",
                "branchname": "",
                "vatregstatus": ""
            },
            "itemreleased": null,
            "buyer": {
                "tinorpinfl": "tinorpinfl",
                "taxpayertype": 30,
                "branchcode": "",
                "name": "name",
                "vatregcode": "",
                "accountnumber": "20208000400308125001",
                "bankmfo": "00974",
                "address": "Address",
                "director": "director",
                "accountant": "Accountant",
                "branchname": "",
                "vatregstatus": ""
            },
            "hasbarcode": false,
            "hascommittent": false,
            "hastaxrelief": true,
            "hasmarking": false,
            "roadway": {
                "productgroups": [
                    {
                        "productinfo": {
                            "products": [
                                {
                                    "ordno": 1,
                                    "committent": null,
                                    "medical": {
                                        "basesumma": "31",
                                        "profitrate": "2",
                                        "serial": "фывй",
                                        "dispensetype": 1
                                    },
                                    "taxrelief": {
                                        "id": "102387",
                                        "name": "УП-5099 от 30.06.2017 г пункт 5 абзац 2 Освободить сроком до 1 января 2028 года резидентов Инновационного центра от уплаты всех видов налогов и обязательных отчислений в государсвенные целевые фонды, а текже единого социального платежа.",
                                        "vatsum": "87.27",
                                        "type": 1
                                    },
                                    "marks": null,
                                    "excise": null,
                                    "name": "тест123",
                                    "catalogcode": "08471001001000000",
                                    "catalogname": "Ноутбук",
                                    "packagecode": "1501886",
                                    "packagename": "шт.",
                                    "barcode": "",
                                    "amount": "23",
                                    "price": "31.62",
                                    "deliverysum": "727.26",
                                    "vat": {
                                        "rate": "12",
                                        "sum": "87.27"
                                    },
                                    "deliverysumwithvat": "814.53",
                                    "origin": 4
                                }
                            ],
                            "totaldeliverysum": "727.26",
                            "totalvatsum": "87.27",
                            "totaldeliverysumwithvat": "814.53"
                        },
                        "loadingpoint": {
                            "regionname": "город Ташкент",
                            "regionid": 26,
                            "districtname": "Яшнободский район",
                            "districtcode": 8,
                            "address": "qwe, 123"
                        },
                        "unloadingpoint": {
                            "regionname": "город Ташкент",
                            "regionid": 26,
                            "districtname": "Мирзо-Улугбекский район",
                            "districtcode": 2,
                            "address": "street123, adres 123"
                        }
                    }
                ],
                "othercarowners": null,
                "truck": {
                    "regno": "01 351 AAA",
                    "model": "MALIBU 2"
                },
                "trailer": null,
                "carriages": [],
                "driver": {
                    "pinfl": "pinfl",
                    "fullname": "fullname"
                }
            },
            "freightforwarder": null,
            "carrier": {
                "tinorpinfl": "tinorpinfl",
                "name": "name",
                "branchcode": "",
                "branchname": ""
            },
            "client": null,
            "payer": null,
            "transporttype": 1,
            "responsibletogoods": {
                "tinorpinfl": "tinorpinfl",
                "name": "name"
            },
            "totaldistance": "12",
            "totaldeliverycost": "21",
            "totalweightbrutto": "21",
            "totalweightnetto": "2",
            "empowerment": null,
            "hybridinvoiceid": "69eeee0c44271587b581af1a"
        }
    },
    "_id": "61fc89b041f611f18aa4b690e2d076a6",
    "created_date": "2026-04-27 10:03:08"
}
```

# 16. Доверенность (новая)

### Пример создания доверенности:

* JSON
* Response _200_
```json
{
    "EmpowermentV2Id": "string", // Идентификатор доверенности (если переоформление)
    "EmpowermentType": 0, // Тип доверенности (код)
    "OldEmpowermentDoc": { // Предыдущая доверенность (если переоформление)
        "EmpowermentV2Id": "string", // ID предыдущей доверенности
        "No": "string", // Номер предыдущей доверенности
        "DateOfIssue": "2024-01-01", // Дата выдачи предыдущей доверенности
        "DateOfExpire": "2024-01-01" // Дата окончания предыдущей доверенности
    },
    "EmpowermentDoc": { // Текущая доверенность
        "No": "string", // Номер доверенности
        "DateOfIssue": "2024-01-01", // Дата выдачи доверенности
        "DateOfExpire": "2024-01-01" // Дата окончания доверенности
    },
    "ContractDoc": { // Договор
        "No": "string", // Номер договора
        "Date": "2024-01-01" // Дата договора
    },
    "Seller": { // Продавец
        "TinOrPinfl": "string", // ИНН или ПИНФЛ
        "Name": "string", // Название организации
        "BranchCode": "string", // Код филиала
        "BranchName": "string", // Название филиала
        "Address": "string", // Адрес
        "Director": { // Руководитель
            "Pinfl": "string", // ПИНФЛ руководителя
            "FullName": "string" // ФИО руководителя
        }
    },
    "Buyer": { // Покупатель
        "TinOrPinfl": "string", // ИНН или ПИНФЛ
        "Name": "string", // Название организации
        "BranchCode": "string", // Код филиала
        "BranchName": "string", // Название филиала
        "Address": "string", // Адрес
        "Director": { // Руководитель
            "Pinfl": "string", // ПИНФЛ руководителя
            "FullName": "string" // ФИО руководителя
        },
        "Accountant": { // Бухгалтер
            "Pinfl": "string", // ПИНФЛ бухгалтера
            "FullName": "string" // ФИО бухгалтера
        }
    },
    "Agent": { // Доверенное лицо (агент)
        "Pinfl": "string", // ПИНФЛ агента
        "FullName": "string" // ФИО агента
    },
    "Products": [ // Список товаров
        {
            "OrdNo": 0, // Порядковый номер
            "Name": "string", // Название товара
            "CatalogCode": "string", // Код каталога
            "CatalogName": "string", // Название из каталога
            "PackageCode": "string", // Код упаковки
            "PackageName": "string", // Единица измерения
            "Amount": 0.0 // Количество
        }
    ]
}
```
```json
{
    "pending_document": {
        "document_json": {
            "empowermentv2id": "string",
            "empowermenttype": 0,
            "oldempowermentdoc": {
                "empowermentv2id": "string",
                "no": "string",
                "dateofissue": "2024-01-01",
                "dateofexpire": "2024-01-01"
            },
            "empowermentdoc": {
                "no": "string",
                "dateofissue": "2024-01-01",
                "dateofexpire": "2024-01-01"
            },
            "contractdoc": {
                "no": "string",
                "date": "2024-01-01"
            },
            "seller": {
                "tinorpinfl": "string",
                "name": "string",
                "branchcode": "string",
                "branchname": "string",
                "address": "string",
                "director": {
                    "pinfl": "string",
                    "fullname": "string"
                }
            },
            "buyer": {
                "tinorpinfl": "string",
                "name": "string",
                "branchcode": "string",
                "branchname": "string",
                "address": "string",
                "director": {
                    "pinfl": "string",
                    "fullname": "string"
                },
                "accountant": {
                    "pinfl": "string",
                    "fullname": "string"
                }
            },
            "agent": {
                "pinfl": "string",
                "fullname": "string"
            },
            "products": [
                {
                    "ordno": 0,
                    "name": "string",
                    "catalogcode": "string",
                    "catalogname": "string",
                    "packagecode": "string",
                    "packagename": "string",
                    "amount": 0.0
                }
            ]
        }
    },
    "_id": "string",
    "created_date": "2024-01-01 00:00:00"
}
```
