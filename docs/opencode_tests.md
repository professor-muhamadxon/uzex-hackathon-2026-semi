# UZEX AI Hackathon 2026 — 50 ta qabul testi

**Loyiha:** UZEX AI Agent — Telegram bot, FastAPI va CLI  
**Sana:** 2026-11-05  
**Baza:** `data/uzex.duckdb` — 500 000 bitim, 6 616 kontrakt, 14 392 kompaniya, 1 765 kunlik USD kursi  
**Maʼlumot davri:** 03.01.2022 – 30.10.2026  
**Muhit:** Python 3.12.14, DuckDB 2.0, aiogram 3.31, FastAPI 0.162

## 1. Hujjat nima uchun

Bu hujjat agentning javoblarini **mustaqil tekshirish** uchun 50 ta testni belgilaydi. Har bir testda savol, kutilgan qiymat va shu qiymat qaysi SQL bilan hisoblanganligi koʻrsatilgan. Kutilgan qiymatlar agentning shablonlari bilan emas, bazaga toʻgʻridan-toʻgʻri yozilgan **mustaqil SQL** orqali olindi — shuning uchun test agentning oʻz xatosini takrorlamaydi.

Testlar hakamlar savol beradigan uchta kanalni ham qamraydi: Telegram bot, `POST /ask` va CLI. Javob matni emas, **undagi raqamlar va faktlar** tekshiriladi.

## 2. Baholash mezonlari bilan bogʻliqlik

| Hackathon mezoni | Ball | Bu hujjatda qanday qoplanadi |
|---|---:|---|
| Javobning toʻgʻriligi | 60 | A–F boʻlimlari: 41 ta hisob-kitob va fakt testi |
| Prototip sifati | 20 | Telegram, web va CLI bir xil agentni ishlatadi; javobda hisoblash izohi va manba koʻrsatiladi |
| Yechim tavsifi | 20 | Har testda ishlatilgan SQL va qoidalar ochiq keltirilgan |
| Gallyutsinatsiya | diskvalifikatsiya | G boʻlimi: 6 ta tuzoq — mavjud boʻlmagan davr, koʻrsatkich, kompaniya va INN |

## 3. Hisoblash qoidalari

Quyidagi qoidalar barcha testlarga tegishli:

- **Annul qilingan bitimlar** (`status = 'Аннулирован(Не оплачен)'`) summa, hajm va reytinglarda hisobga olinmaydi; ular alohida eslatiladi.
- **Bitimlar soni** soʻralganda barcha holatlar (annul ham) kiradi — bu reyestrdagi jismoniy qatorlar soni.
- **USD** — `amount` maydoni, yaʼni shartnoma valyutasidagi summa; soʻm ekvivalenti har bir bitim sanasidagi kurs boʻyicha hisoblanadi.
- **Dollar kursi** — `usd_rates` jadvalidagi kunlik rasmiy kurs; sanada kurs boʻlmasa, undan oldingi oxirgi kurs olinadi.
- **Tovar** — TNVED kodi boʻyicha aniqlanadi, shuning uchun nomning turlicha yozilishi natijani buzmaydi.
- **Prognoz** — faqat statistik taxmin; maʼlumot yoʻqligi haqida ogohlantirish majburiy.

## 4. Qanday tekshiriladi

```powershell
# CLI (Windows konsolida UTF-8 uchun -X utf8):
.venv\Scripts\python.exe -X utf8 -m app.cli "2025-yilda jami savdo summasi qancha?"

# Web:
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d '{"question":"2025-yilda jami savdo summasi qancha?"}'

# Telegram: @uzex_hackathon_2026_bot ga savol yuboriladi.
```

Har bir test uchun kutilgan qiymatni mustaqil tekshirish SQL'i ilovada (7-boʻlim) berilgan. `{A}` belgisi quyidagi shartni bildiradi:

```sql
{A}  →  status <> 'Аннулирован(Не оплачен)'
```

## 5. Umumiy natija

**50/50 test oʻtdi.** Tekshiruv 2026-11-05 da joriy ishchi daraxtda oʻtkazildi; har bir savol agentga bir marta berildi.

| Boʻlim | Testlar | Oʻtdi | Vaqt (jami) |
|---|---:|---:|---:|
| A. Summa va bitim soni | 9 | 9/9 | 1.1 s |
| B. Eksport va hajm | 5 | 5/5 | 0.7 s |
| C. Reytinglar | 7 | 7/7 | 1.7 s |
| D. Kesimlar va tahlil | 6 | 6/6 | 0.9 s |
| E. Kontrakt, bitim, kompaniya va broker | 8 | 8/8 | 1.2 s |
| F. Dollar kursi | 6 | 6/6 | 0.9 s |
| G. Tuzoqlar: maʼlumot yoʻqligi | 6 | 6/6 | 0.6 s |
| H. Barqarorlik | 3 | 3/3 | 0.7 s |
| **Jami** | **50** | **50/50** | **7.9 s** |

## 6.1 A. Summa va bitim soni (9 test)

Jami summalar, bitimlar soni, chorak va davr chegaralari.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **A1** | 2025-yilda jami savdo summasi qancha? | UZ-Lat | **52 060 836 360 057.12** soʻm | ✅ 0.54 s · `total` |
| **A2** | Общая сумма сделок за 2024 год | RU | **42 724 135 079 483.66** soʻm | ✅ 0.07 s · `total` |
| **A3** | Общая сумма сделок за 2022 год | RU | **27 965 891 730 951.99** soʻm | ✅ 0.08 s · `total` |
| **A4** | 2023-yilda nechta bitim tuzilgan? | UZ-Lat | **93 985** ta | ✅ 0.06 s · `total` |
| **A5** | Сколько сделок было в 2022 году? | RU | **84 299** ta | ✅ 0.07 s · `total` |
| **A6** | 2025 йилда пахта бўйича жами сумма қанча? | UZ-Kiril | **16 957 079 437 704.36** soʻm | ✅ 0.12 s · `product_stats` |
| **A7** | Сумма сделок в III квартале 2025 года | RU | **16 028 849 158 920.42** soʻm | ✅ 0.06 s · `total` |
| **A8** | Ötgan yili jami savdo summasi qança? | UZ-Yangi | **52 060 836 360 057.12** soʻm | ✅ 0.08 s · `total` |
| **A9** | 2025-yilda bekor qilingan bitimlar soni | UZ-Lat | **8 085** ta | ✅ 0.06 s · `total` |

**Izohlar:**

- **A1** — Annul qilingan bitimlar hisobga olinmaydi.
- **A3** — Maʼlumotlarning birinchi yili.
- **A4** — Bitimlar sonida barcha holatlar (annul ham) hisobga olinadi.
- **A6** — Kirill yozuvi; paxta = TNVED 520100.
- **A7** — Chorak chegarasi: 01.07–30.09.
- **A8** — Yangi alifbo; «ötgan yili» = 2025 (maʼlumot 30.10.2026 gacha).
- **A9** — Faqat annul qilingan bitimlar.

## 6.2 B. Eksport va hajm (5 test)

Eksport dollarda, yetakchi eksportchilar, tonna hajmi.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **B1** | 2025-yilda eksport summasi qancha dollar? | UZ-Lat | **203 892 531.64** USD | ✅ 0.07 s · `export_stats` |
| **B2** | Экспорт за 2024 год в долларах | RU | **202 495 621** USD | ✅ 0.07 s · `export_stats` |
| **B3** | Ўтган йили экспорт неча доллар бўлган? | UZ-Kiril | **203 892 531.64** USD | ✅ 0.12 s · `export_stats` |
| **B4** | 2025-yilda eng ko'p eksport qilgan 5 sotuvchi kompaniya | UZ-Lat | 1) "ТИШИЛ СТЕЕЛ" МЧЖ — **49 131 606.37**<br>2) TIZAHI METALL MCHJ — **46 887 231.29**<br>3) "СОТЎТО МЕТАЛЛ" МЧЖ — **40 277 736.13**<br>4) "ФАЮМ АГРО" МЧЖ — **16 529 491.06**<br>5) SUSHUCHIR AGRO MCHJ — **16 226 918.18** | ✅ 0.15 s · `top` |
| **B5** | Сколько тонн пшеницы продано в 2024 году? | RU | **2 087 277** тонна | ✅ 0.26 s · `product_stats` |

**Izohlar:**

- **B1** — Dollar summasi — shartnoma valyutasidagi amount.
- **B3** — Kirill; «ўтган йили» = 2025.
- **B4** — Sotuvchi tomoni, dollar summasi.
- **B5** — Hajm birlik boʻyicha; eng katta birlik — tonna.

## 6.3 C. Reytinglar (7 test)

Tovar, viloyat, broker va kompaniyalar boʻyicha top-5.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **C1** | Eng ko'p sotilgan 5 tovar (2025) | UZ-Lat | 1) Хлопок-сырец (спот) — **16 957 079 437 704.36**<br>2) Пшеница продовольственная — **9 243 437 724 773**<br>3) Масло хлопковое — **3 464 342 324 683**<br>4) КАТОД МЕДНЫЙ — **3 441 760 869 559.05**<br>5) Дизельное топливо — **2 554 988 955 086** | ✅ 0.18 s · `top` |
| **C2** | 2025-yilda eng katta summa qaysi viloyatda? | UZ-Lat | 1) Toshkent shahri — **9 949 843 736 776.88**<br>2) Namangan viloyati — **6 420 937 519 362.9**<br>3) Xorazm viloyati — **4 886 254 813 143.98**<br>4) Buxoro viloyati — **4 533 561 328 058.01**<br>5) Sirdaryo viloyati — **4 230 385 197 942.2** | ✅ 0.17 s · `top` |
| **C3** | Какой регион лидирует по количеству сделок в 2024 году? | RU | 1) Toshkent shahri — **21 247**<br>2) Namangan viloyati — **13 580**<br>3) Toshkent viloyati — **9 180**<br>4) Buxoro viloyati — **7 883**<br>5) Samarqand viloyati — **7 696** | ✅ 0.16 s · `top` |
| **C4** | Qaysi broker eng ko'p bitim qilgan? | UZ-Lat | 1) "Gucham Broker" MChJ — **32 422**<br>2) KAZEHI BROKER MCHJ — **20 808**<br>3) FIPI BROKER MCHJ — **20 141**<br>4) PASUR BROKER MCHJ — **19 099**<br>5) "Shofin Broker" MChJ — **18 567** | ✅ 0.64 s · `top` |
| **C5** | Кто крупнейший покупатель хлопка в 2025 году? | RU | 1) "Zoket Invest" OK — **883 326 387 289.11**<br>2) "Fo‘sor Qurilish" MChJ — **361 055 951 430.58**<br>3) HO‘CHAL GROUP MCHJ — **217 842 128 638.13**<br>4) "Moto Group" MChJ — **186 501 264 633.85**<br>5) YOVOL TRADE MCHJ — **167 597 339 441.72** | ✅ 0.24 s · `top` |
| **C6** | 2024-yilda paxta sotgan top-5 kompaniya | UZ-Lat | 1) SITO‘TOM TEKSTIL MCHJ — **1 208 765 957 994.71**<br>2) "Mo‘sho‘n Tekstil" MChJ — **990 853 727 236.58**<br>3) "Nutunim Fermer" MChJ — **983 121 345 888.54**<br>4) "Lidayo‘ Agro" MChJ — **852 600 092 625.72**<br>5) KO‘VIZ FERMER MCHJ — **774 866 842 963.62** | ✅ 0.18 s · `top` |
| **C7** | Топ-5 покупателей пшеницы в 2024 году | RU | 1) "Zoket Invest" OK — **438 527 862 760**<br>2) "Fo‘sor Qurilish" MChJ — **198 860 054 227**<br>3) HO‘CHAL GROUP MCHJ — **103 690 172 377**<br>4) YOVOL TRADE MCHJ — **66 602 520 528**<br>5) "Moto Group" MChJ — **64 693 201 903** | ✅ 0.15 s · `top` |

**Izohlar:**

- **C1** — TNVED boʻyicha guruhlash (nomi turlicha yozilgan tovarlar birlashadi).
- **C3** — Sonlarda barcha holatlar.
- **C4** — Broker sotuvchi yoki xaridor tomonida; har bitim bir marta.
- **C5** — Xaridor tomoni.
- **C6** — Sotuvchi tomoni.

## 6.4 D. Kesimlar va tahlil (6 test)

Kategoriya kesimi, hafta kunlari, oʻrtacha narx, ulush.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **D1** | 2024-yilda tovar kategoriyalari bo'yicha summani ko'rsat | UZ-Lat | 1) Сельскохозяйственная продукция — **22 395 334 020 986.54**<br>2) Продовольственные товары — **5 709 199 033 592.48**<br>3) Нефтепродукты — **4 849 455 786 383**<br>4) Металлопродукция — **4 082 884 183 373.15**<br>5) Полимерная продукция — **2 903 085 223 316**<br>6) Химическая продукция — **1 480 257 137 044**<br>7) Строительные материалы — **1 277 331 120 831**<br>8) Промышленные товары — **26 588 573 957.5** | ✅ 0.12 s · `breakdown` |
| **D2** | Hafta kunlari bo'yicha bitimlar soni qanday taqsimlangan? | UZ-Lat | 1) chorshanba — **106 039**<br>2) seshanba — **104 066**<br>3) payshanba — **103 759**<br>4) dushanba — **93 485**<br>5) juma — **92 651** | ✅ 0.09 s · `breakdown` |
| **D3** | Сколько сделок в выходные дни? | RU | **0** ta bitim (dam olish kunlari savdo yoʻq) | ✅ 0.12 s · `breakdown` |
| **D4** | 2024-yilda paxtaning o'rtacha narxi qancha? | UZ-Lat | **7 722.22** soʻm | ✅ 0.27 s · `product_stats` |
| **D5** | Сколько уникальных покупателей было в 2024 году? | RU | **13 040** ta | ✅ 0.13 s · `distinct_parties` |
| **D6** | Bekor qilingan bitimlar ulushi necha foiz? | UZ-Lat | **6.74**% | ✅ 0.15 s · `status_share` |

**Izohlar:**

- **D1** — Kesim oʻlchovi — category; 8 kategoriya.
- **D2** — Barcha davr; shanba va yakshanba — 0.
- **D3** — Dam olish kunlari savdo yoʻq — javob 0.
- **D4** — unit_price — shartnoma valyutasida; paxta uchun soʻm/kg.
- **D6** — Barcha davr.

## 6.5 E. Kontrakt, bitim, kompaniya va broker (8 test)

Kartochkalar va aniq identifikatorlar.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **E1** | Информация о контракте 100001 | RU | **Профиль алюминиевый** | ✅ 0.14 s · `contract_info` |
| **E2** | 100001-kontrakt haqida ma'lumot | UZ-Lat | **Профиль алюминиевый** | ✅ 0.12 s · `contract_info` |
| **E3** | Сделка 500000 | RU | **"Tiso Energo" MChJ** | ✅ 0.11 s · `deal_info` |
| **E4** | 925910430 INN bo'yicha ma'lumot | UZ-Lat | **SITO‘TOM TEKSTIL MCHJ** | ✅ 0.16 s · `company_profile` |
| **E5** | SITO TOM TEKSTIL MCHJ haqida ma'lumot | UZ-Lat | **SITO‘TOM TEKSTIL MCHJ** | ✅ 0.20 s · `company_profile` |
| **E6** | Сколько сделок по брокеру BK001 в 2024 году? | RU | **1 124** ta | ✅ 0.17 s · `broker_stats` |
| **E7** | Broker BK001 bo'yicha statistika | UZ-Lat | **4 282** ta | ✅ 0.18 s · `broker_stats` |
| **E8** | Сколько контрактов зарегистрировано в 2024 году? | RU | **1 507** ta | ✅ 0.13 s · `contracts_count` |

**Izohlar:**

- **E1** — Kontrakt kartasi: tovar nomi.
- **E3** — Bitim kartasi: sotuvchi nomi.
- **E4** — Ishtirokchi nomi.
- **E5** — Nom boʻyicha qidiruv (nomda ʻ belgisi bor).
- **E6** — Ikkala tomon ham; barcha holatlar.
- **E7** — Barcha davr; annul qilinganlar hisobga olinmaydi.
- **E8** — contracts_full.registration_date.

## 6.6 F. Dollar kursi (6 test)

Sana boʻyicha kurs, min/max/oʻrtacha, oʻsish foizi, prognoz.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **F1** | Курс доллара на 01.06.2024 | RU | **11 870.86** soʻm/USD | ✅ 0.11 s · `usd_rate` |
| **F2** | 15.03.2025 dagi dollar kursi qancha? | UZ-Lat | **12 589.97** soʻm/USD | ✅ 0.13 s · `usd_rate` |
| **F3** | Barcha davr bo'yicha dollar kursini tahlil qil | UZ-Lat | min **10 829.1**; maks. **13 500.03** | ✅ 0.18 s · `analysis` |
| **F4** | Анализ курса доллара за 2025 год | RU | min **12 181.16**; maks. **12 666.9**; oʻrt. **12 428.46** | ✅ 0.18 s · `analysis` |
| **F5** | 2027-yil uchun dollar kursini bashorat qil | UZ-Lat | «2027-yil uchun maʼlumotlar berilmagan» + **statistik taxmin** ekani ogohlantiriladi | ✅ 0.15 s · `forecast` |
| **F6** | На сколько процентов вырос курс доллара за весь период? | RU | **23.35**% | ✅ 0.20 s · `analysis` |

**Izohlar:**

- **F1** — Sanadagi yoki undan oldingi oxirgi kurs.
- **F3** — Butun davr: minimum va maksimum.
- **F4** — 2025: min / max / oʻrtacha.
- **F5** — Faqat statistik taxmin va ogohlantirish; aniq raqam deb eʼlon qilinmaydi.
- **F6** — Birinchi va oxirgi kurs orasidagi oʻsish.

## 6.7 G. Tuzoqlar: maʼlumot yoʻqligi (6 test)

Chegaradan tashqari davr, mavjud boʻlmagan koʻrsatkich, kompaniya va INN.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **G1** | 2021-yilda jami savdo summasi qancha? | UZ-Lat | Raqam oʻylab topilmaydi: *Maʼlumot yoʻq* deb javob beriladi | ✅ 0.11 s · `not_found` |
| **G2** | Сделки за декабрь 2026 года | RU | Raqam oʻylab topilmaydi: *Maʼlumot yoʻq* deb javob beriladi | ✅ 0.11 s · `not_found` |
| **G3** | Какая маржа у продавцов хлопка? | RU | Raqam oʻylab topilmaydi: *Koʻrsatkich yoʻq* deb javob beriladi | ✅ 0.11 s · `not_found` |
| **G4** | Zumrad Super Trade MCHJ 2025 yilda qancha sotgan? | UZ-Lat | Raqam oʻylab topilmaydi: *Kompaniya yoʻq* deb javob beriladi | ✅ 0.13 s · `not_found` |
| **G5** | ИНН 111111111 сколько сделок? | RU | Raqam oʻylab topilmaydi: *Bunday INN yoʻq* deb javob beriladi | ✅ 0.05 s · `not_found` |
| **G6** | kompyuter butun davr boyicha necha foizda oshgan? | UZ-Lat | Raqam oʻylab topilmaydi: *Tovar yoʻq* deb javob beriladi | ✅ 0.12 s · `not_found` |

**Izohlar:**

- **G1** — Maʼlumot 03.01.2022 dan boshlanadi.
- **G2** — Maʼlumot 30.10.2026 da tugaydi.
- **G3** — Marja maʼlumotlarda yoʻq — hisoblab boʻlmaydi.
- **G4** — Bunday kompaniya reyestrda yoʻq.
- **G5** — Bunday INN yoʻq.
- **G6** — Kompyuter tovari maʼlumotlarda yoʻq.

## 6.8 H. Barqarorlik (3 test)

Kirill yozuvi, yangi alifbo va imlo xatolari.

| № | Savol | Til | Kutilgan javob | Holat |
|---|---|---|---|---|
| **H1** | 2024-yilda şakar qança sotilgan? | UZ-Yangi | **93 378** тонна | ✅ 0.24 s · `product_stats` |
| **H2** | Тошкент шаҳрида 2024 йилда нечта битим бўлган? | UZ-Kiril | **21 247** ta | ✅ 0.22 s · `total` |
| **H3** | benzin butun davr boyicha necha foizda oshgan? | UZ-Lat | **61.09**% | ✅ 0.19 s · `analysis` |

**Izohlar:**

- **H1** — Yangi alifbo; shakar = TNVED 170199.
- **H2** — Kirill; viloyat nomi mosligi.
- **H3** — Imlo xatolari; TNVED 271012, tonna.

## 7. Ilova: kutilgan qiymatlarning mustaqil SQL'i

Quyidagi SQL'lar DuckDB'da toʻgʻridan-toʻgʻri bajarilgan; agent kodi ishlatilmagan.

| № | SQL |
|---|---|
| **A1** | `SELECT SUM(amount_uzs) FROM deals_enriched WHERE year(deal_date)=2025 AND status <> 'Аннулирован(Не оплачен)'` |
| **A2** | `SELECT SUM(amount_uzs) FROM deals_enriched WHERE year(deal_date)=2024 AND status <> 'Аннулирован(Не оплачен)'` |
| **A3** | `SELECT SUM(amount_uzs) FROM deals_enriched WHERE year(deal_date)=2022 AND status <> 'Аннулирован(Не оплачен)'` |
| **A4** | `SELECT COUNT(*) FROM deals_enriched WHERE year(deal_date)=2023` |
| **A5** | `SELECT COUNT(*) FROM deals_enriched WHERE year(deal_date)=2022` |
| **A6** | `SELECT SUM(amount_uzs) FROM deals_enriched WHERE tnved_code='520100' AND year(deal_date)=2025 AND status <> 'Аннулирован(Не оплачен)'` |
| **A7** | `SELECT SUM(amount_uzs) FROM deals_enriched WHERE deal_date BETWEEN DATE '2025-07-01' AND DATE '2025-09-30' AND status <> 'Аннулирован(Не оплачен)'` |
| **A8** | `SELECT SUM(amount_uzs) FROM deals_enriched WHERE year(deal_date)=2025 AND status <> 'Аннулирован(Не оплачен)'` |
| **A9** | `SELECT COUNT(*) FROM deals_enriched WHERE status='Аннулирован(Не оплачен)' AND year(deal_date)=2025` |
| **B1** | `SELECT SUM(amount) FROM deals_enriched WHERE contract_type='Экспортный' AND year(deal_date)=2025 AND status <> 'Аннулирован(Не оплачен)'` |
| **B2** | `SELECT SUM(amount) FROM deals_enriched WHERE contract_type='Экспортный' AND year(deal_date)=2024 AND status <> 'Аннулирован(Не оплачен)'` |
| **B3** | `SELECT SUM(amount) FROM deals_enriched WHERE contract_type='Экспортный' AND year(deal_date)=2025 AND status <> 'Аннулирован(Не оплачен)'` |
| **B4** | `SELECT p.name AS name, SUM(d.amount) AS value FROM deals_enriched d JOIN participants p ON p.inn = d.seller_inn WHERE d.contract_type='Экспортный' AND year(d.deal_date)=2025 AND d.status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 5` |
| **B5** | `SELECT unit AS name, SUM(volume) AS value FROM deals_enriched WHERE tnved_code='100199' AND year(deal_date)=2024 AND status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 1` |
| **C1** | `SELECT ANY_VALUE(contract_product_name) AS name, SUM(amount_uzs) AS value FROM deals_enriched WHERE year(deal_date)=2025 AND status <> 'Аннулирован(Не оплачен)' GROUP BY tnved_code ORDER BY value DESC LIMIT 5` |
| **C2** | `SELECT region_uz AS name, SUM(amount_uzs) AS value FROM deals_enriched WHERE year(deal_date)=2025 AND status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 5` |
| **C3** | `SELECT region_uz AS name, COUNT(*) AS value FROM deals_enriched WHERE year(deal_date)=2024 GROUP BY 1 ORDER BY value DESC LIMIT 5` |
| **C4** | `SELECT b.name AS name, COUNT(DISTINCT x.deal_id) AS value FROM (SELECT seller_broker AS code, deal_id FROM deals_enriched UNION ALL SELECT buyer_broker, deal_id FROM deals_enriched) x JOIN brokers b ON b.broker_code = x.code WHERE x.code IS NOT NULL GROUP BY 1 ORDER BY value DESC LIMIT 5` |
| **C5** | `SELECT p.name AS name, SUM(d.amount_uzs) AS value FROM deals_enriched d JOIN participants p ON p.inn = d.buyer_inn WHERE d.tnved_code='520100' AND year(d.deal_date)=2025 AND d.status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 5` |
| **C6** | `SELECT p.name AS name, SUM(d.amount_uzs) AS value FROM deals_enriched d JOIN participants p ON p.inn = d.seller_inn WHERE d.tnved_code='520100' AND year(d.deal_date)=2024 AND d.status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 5` |
| **C7** | `SELECT p.name AS name, SUM(d.amount_uzs) AS value FROM deals_enriched d JOIN participants p ON p.inn = d.buyer_inn WHERE d.tnved_code='100199' AND year(d.deal_date)=2024 AND d.status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 5` |
| **D1** | `SELECT category AS name, SUM(amount_uzs) AS value FROM deals_enriched WHERE year(deal_date)=2024 AND status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 8` |
| **D2** | `SELECT CASE isodow(deal_date) WHEN 1 THEN 'dushanba' WHEN 2 THEN 'seshanba' WHEN 3 THEN 'chorshanba' WHEN 4 THEN 'payshanba' WHEN 5 THEN 'juma' WHEN 6 THEN 'shanba' ELSE 'yakshanba' END AS name, COUNT(*) AS value FROM deals_enriched GROUP BY 1 ORDER BY value DESC LIMIT 7` |
| **D3** | `SELECT COUNT(*) FROM deals_enriched WHERE isodow(deal_date) IN (6,7)` |
| **D4** | `SELECT AVG(unit_price) FROM deals_enriched WHERE tnved_code='520100' AND year(deal_date)=2024 AND status <> 'Аннулирован(Не оплачен)'` |
| **D5** | `SELECT COUNT(DISTINCT buyer_inn) FROM deals_enriched WHERE year(deal_date)=2024` |
| **D6** | `SELECT ROUND(100.0*COUNT(*) FILTER (WHERE status='Аннулирован(Не оплачен)')/COUNT(*), 2) FROM deals_enriched` |
| **E1** | `SELECT product_name FROM contracts_full WHERE contract_id=100001` |
| **E2** | `SELECT product_name FROM contracts_full WHERE contract_id=100001` |
| **E3** | `SELECT p.name FROM deals_enriched d JOIN participants p ON p.inn=d.seller_inn WHERE d.deal_id=500000` |
| **E4** | `SELECT name FROM participants WHERE inn='925910430'` |
| **E5** | `SELECT name FROM participants WHERE inn='925910430'` |
| **E6** | `SELECT COUNT(*) FROM deals_enriched WHERE (seller_broker='BK001' OR buyer_broker='BK001') AND year(deal_date)=2024` |
| **E7** | `SELECT COUNT(*) FROM deals_enriched WHERE (seller_broker='BK001' OR buyer_broker='BK001') AND status <> 'Аннулирован(Не оплачен)'` |
| **E8** | `SELECT COUNT(*) FROM contracts_full WHERE year(registration_date)=2024` |
| **F1** | `SELECT rate FROM usd_rates WHERE rate_date <= DATE '2024-06-01' ORDER BY rate_date DESC LIMIT 1` |
| **F2** | `SELECT rate FROM usd_rates WHERE rate_date <= DATE '2025-03-15' ORDER BY rate_date DESC LIMIT 1` |
| **F3** | `SELECT MIN(rate), MAX(rate) FROM usd_rates` |
| **F4** | `SELECT MIN(rate), MAX(rate), ROUND(AVG(rate),2) FROM usd_rates WHERE year(rate_date)=2025` |
| **F5** | `—` |
| **F6** | `SELECT ROUND(100.0*(arg_max(rate,rate_date)-arg_min(rate,rate_date))/arg_min(rate,rate_date),2) FROM usd_rates` |
| **G1** | `—` |
| **G2** | `—` |
| **G3** | `—` |
| **G4** | `—` |
| **G5** | `—` |
| **G6** | `—` |
| **H1** | `SELECT unit AS name, SUM(volume) AS value FROM deals_enriched WHERE tnved_code='170199' AND year(deal_date)=2024 AND status <> 'Аннулирован(Не оплачен)' GROUP BY 1 ORDER BY value DESC LIMIT 1` |
| **H2** | `SELECT COUNT(*) FROM deals_enriched WHERE region_uz='Toshkent shahri' AND year(deal_date)=2024` |
| **H3** | `SELECT ROUND(100.0*(l-f)/f,2) FROM ( SELECT arg_min(v,m) f, arg_max(v,m) l FROM ( SELECT date_trunc('month',deal_date) m, AVG(unit_price) FILTER (WHERE status<>'Аннулирован(Не оплачен)') v FROM deals_enriched WHERE tnved_code='271012' AND unit='тонна' GROUP BY 1))` |

## 8. Maʼlum cheklovlar va tuzoq siyosati

- **Bot-botga toʻgʻridan-toʻgʻri xabar yubora olmaydi.** Monitoring relayi ikkinchi bot tokeni bilan kuzatuv chatiga nusxa yuboradi; ikkinchi botning kodi oʻzgarmaydi.
- **Davr chegarasi qatʼiy:** 2021-yil va 2026-yil dekabri uchun maʼlumot yoʻq; agent buni ochiq aytadi va raqam uydirmaydi (G1, G2).
- **Mavjud boʻlmagan koʻrsatkichlar** (marja, foyda, yetkazish muddati) hisoblanmaydi; agent mavjud koʻrsatkichlar roʻyxatini taklif qiladi (G3).
- **Prognoz** faqat trendga asoslangan taxmin; u haqiqiy maʼlumot sifatida taqdim etilmaydi (F5).
- **Imlo xatolari:** agent TNVED katalogi boʻyicha yaqin tovar nomini topadi, lekin noaniq holatda taxmin qilish oʻrniga aniqlashtirishni soʻraydi.
