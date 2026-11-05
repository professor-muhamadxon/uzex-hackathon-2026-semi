# claude_tests: 50 ta yangi savol (rus, o‘zbek kirill, o‘zbek lotin)

Sana: 2026-11-05 19:18. Agent: LLM o‘chiq (`llm_enabled=False`), `RAG_ENABLED` .env bo‘yicha.
Kutilgan qiymatlar agent kodidan **mustaqil** SQL bilan to‘g‘ridan-to‘g‘ri bazadan hisoblangan (`scripts/claude_tests.py`). Summa va narxlarda annul qilingan bitimlar hisobga olinmaydi, bitimlar sonida hisobga olinadi. Viloyat filtri sotuvchi ombori viloyatini bildiradi. «Ijro etilgan» = «Исполнен» + «Исполнен(Частично)» (agent shuni javobda ko‘rsatadi).

## Natija

| Guruh | Savollar | To‘g‘ri |
|---|---:|---:|
| ru | 17 | 17 |
| uz-cyr | 17 | 17 |
| uz-lat | 16 | 16 |
| shundan tuzoq (ma’lumotda javob yo‘q) | 8 | 8 |
| **Jami** | **50** | **50** |

Javob tili/yozuvi to‘g‘ri: 50/50. Tasdiqlanmagan raqamli javoblar: 0. O‘rtacha vaqt: 0.16 s, eng uzog‘i: 0.37 s.

## Savollar

| № | Til | Savol | Kutilgan | Natija |
|---:|---|---|---|---|
| 1 | ru | Сколько сделок было в Самаркандской области в 2023 году? | 7 839 | ✅ |
| 2 | ru | Сколько сделок в Хорезмской области в 2025 году? | 7 622 | ✅ |
| 3 | ru | Какова общая сумма сделок в 2022 году? | 27 965 891 730 951 | ✅ |
| 4 | ru | Какова общая сумма сделок в 2026 году? | 48 800 447 257 149 | ✅ |
| 5 | ru | Сколько сделок со статусом «Исполнен» в 2024 году? | 94 481 | ✅ |
| 6 | ru | Сколько сделок было аннулировано в 2023 году? | 6 313 | ✅ |
| 7 | ru | Сколько сделок по нефтепродуктам в 2024 году? | 17 235 | ✅ |
| 8 | ru | Какая общая сумма сделок по металлопродукции в 2025 году? | 4 702 799 941 555 | ✅ |
| 9 | ru | Сколько сделок в Ферганской области за 2022 год? | 4 206 | ✅ |
| 10 | ru | Сколько контрактов зарегистрировано в 2023 году? | 1 062 | ✅ |
| 11 | ru | Какой курс доллара на 15 мая 2024 года? | 11 866 | ✅ |
| 12 | ru | Сколько сделок в Ташкентской области в 2024 году? | 9 180 | ✅ |
| 13 | ru | Сколько сделок в Бухарской области в первом квартале 2025 года? | 1 009 | ✅ |
| 14 | ru | Сколько сделок было в марте 2024 года? | 5 253 | ✅ |
| 15 | ru | Какая сумма сделок в 2028 году? | topilmadi (tuzoq) | ✅ |
| 16 | ru | Какая чистая прибыль у продавцов? | topilmadi (tuzoq) | ✅ |
| 17 | ru | Сколько сделок по золоту в 2024 году? | topilmadi (tuzoq) | ✅ |
| 18 | uz-cyr | 2024 йилда Фарғона вилоятида нечта битим бўлган? | 4 566 | ✅ |
| 19 | uz-cyr | 2023 йилда Бухоро вилоятида нечта битим бўлган? | 7 387 | ✅ |
| 20 | uz-cyr | 2025 йилда жами савдо суммаси қанча? | 52 060 836 360 057 | ✅ |
| 21 | uz-cyr | 2022 йилда жами савдо суммаси қанча? | 27 965 891 730 951 | ✅ |
| 22 | uz-cyr | 2025 йилда нечта битим бекор қилинган? | 8 085 | ✅ |
| 23 | uz-cyr | 2024 йилда нечта битим ижро этилган? | 99 324 | ✅ |
| 24 | uz-cyr | 2024 йилда нефть маҳсулотлари бўйича нечта битим бўлган? | 17 235 | ✅ |
| 25 | uz-cyr | 2023 йилда Навоий вилоятида нечта битим бўлган? | 4 425 | ✅ |
| 26 | uz-cyr | 2026 йилда нечта битим тузилган? | 99 306 | ✅ |
| 27 | uz-cyr | 2022 йилда Қашқадарё вилоятида нечта битим бўлган? | 6 342 | ✅ |
| 28 | uz-cyr | 2025 йил май ойида нечта битим тузилган? | 6 657 | ✅ |
| 29 | uz-cyr | 2024 йилда Хоразм вилоятида битимлар суммаси қанча? | 4 181 188 234 646 | ✅ |
| 30 | uz-cyr | 2025 йил 1-чоракда нечта битим тузилган? | 17 807 | ✅ |
| 31 | uz-cyr | 2024 йил 10 июнда доллар курси қанча? | 11 866 | ✅ |
| 32 | uz-cyr | 2027 йилда нечта битим бўлади? | topilmadi (tuzoq) | ✅ |
| 33 | uz-cyr | Тошкентда бугун об-ҳаво қандай? | topilmadi (tuzoq) | ✅ |
| 34 | uz-cyr | Олтин бўйича 2024 йилда нечта битим бўлган? | topilmadi (tuzoq) | ✅ |
| 35 | uz-lat | 2023-yilda Namangan viloyatida nechta bitim bo‘lgan? | 12 223 | ✅ |
| 36 | uz-lat | 2024-yilda Samarqand viloyatida nechta bitim bo‘lgan? | 7 696 | ✅ |
| 37 | uz-lat | 2023-yilda jami savdo summasi qancha? | 34 187 428 452 052 | ✅ |
| 38 | uz-lat | 2026-yilda jami savdo summasi qancha? | 48 800 447 257 149 | ✅ |
| 39 | uz-lat | 2025-yilda nechta bitim bekor qilingan? | 8 085 | ✅ |
| 40 | uz-lat | 2023-yilda nechta bitim ijro etilgan? | 87 672 | ✅ |
| 41 | uz-lat | 2025-yilda neft mahsulotlari bo‘yicha nechta bitim bo‘lgan? | 18 597 | ✅ |
| 42 | uz-lat | 2022-yilda Andijon viloyatida nechta bitim bo‘lgan? | 4 611 | ✅ |
| 43 | uz-lat | 2025-yil iyul oyida nechta bitim tuzilgan? | 8 877 | ✅ |
| 44 | uz-lat | 2024-yilda kimyo mahsulotlari bo‘yicha nechta bitim bo‘lgan? | 6 703 | ✅ |
| 45 | uz-lat | 2025-yilda Surxondaryo viloyatida bitimlar summasi qancha? | 2 609 757 408 693 | ✅ |
| 46 | uz-lat | 2024-yil 2-chorakda nechta bitim tuzilgan? | 19 334 | ✅ |
| 47 | uz-lat | 2025-yil 3-martda dollar kursi qancha? | 12 513 | ✅ |
| 48 | uz-lat | 2023-yilda ro‘yxatdan o‘tgan kontraktlar soni nechta? | 1 062 | ✅ |
| 49 | uz-lat | Eng ko‘p foyda ko‘rgan kompaniya qaysi? | topilmadi (tuzoq) | ✅ |
| 50 | uz-lat | 2019-yilda nechta bitim bo‘lgan? | topilmadi (tuzoq) | ✅ |

## Xatolar

Xato yo‘q.
