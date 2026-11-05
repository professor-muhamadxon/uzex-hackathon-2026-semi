# Analitik savollar — tekshiruvchi varaqasi / Аналитические вопросы — лист проверяющего

Kutilgan qiymatlar agent kodidan mustaqil SQL/Python bilan hisoblangan (`scripts/analytics_test.py`).
Ожидаемые значения посчитаны независимым SQL/Python, не кодом агента.

Baholash qoidasi: javobda barça kalit raqamlar bölişi, bashoratda esa maʼlumot yöqligi haqida ogohlantiriş bölişi şart. / Правило: в ответе должны быть все ключевые числа; в прогнозе — обязательное предупреждение об отсутствии данных.

Natija / Результат: **20/20**

## 1. USD kursi butun davr tahlili

- **RU:** Проанализируй курс доллара за весь период
- **UZ:** Barcha davr bo‘yicha dollar kursini tahlil qil
- **Kutilgan javob / Ожидаемый ответ:** Boshlanish 10 829.1 so‘m → oxiri 13 357.84 so‘m, o‘zgarish +23.35%; maksimum 13 500.03 so‘m (22.09.2026); trend — barqaror o‘sish.
- **Kalit qiymatlar / Ключевые значения:** `10 829.1`, `13 357.84`, `13 500.03`, `22.09.2026`, `23.35`
- **Agent:** RU: ✅ (0.11 s) · UZ: ✅ (0.09 s)

## 2. USD kursi 2024 tahlili

- **RU:** Анализ курса доллара за 2024 год
- **UZ:** 2024-yil dollar kursi tahlili
- **Kutilgan javob / Ожидаемый ответ:** 2024: minimum 11 657.83 (09.03.2024), maksimum 12 410.16 (31.12.2024), o‘rtacha ≈ 11 945.86 so‘m.
- **Kalit qiymatlar / Ключевые значения:** `11 657.83`, `09.03.2024`, `12 410.16`, `31.12.2024`, `11 945.86`
- **Agent:** RU: ✅ (0.11 s) · UZ: ✅ (0.07 s)

## 3. 2025 bitimlar tahlili

- **RU:** Аналитика сделок за 2025 год
- **UZ:** 2025-yil bitimlar tahlili
- **Kutilgan javob / Ожидаемый ответ:** Jami 52 060 836 360 057.12 so‘m (annulsiz); eng faol oy 2025-10 (17 808 bitim); summa bo‘yicha eng past oy 2025-02.
- **Kalit qiymatlar / Ключевые значения:** `52 060 836 360 057.12`, `2025-10`, `17 808`, `2025-02`
- **Agent:** RU: ✅ (0.09 s) · UZ: ✅ (0.09 s)

## 4. Bitimlar soni dinamikasi

- **RU:** Анализ количества сделок за весь период
- **UZ:** Bitimlar soni dinamikasini tahlil qil
- **Kutilgan javob / Ожидаемый ответ:** Jami 500 000 bitim; yillar: 2022 — 84 299, 2023 — 93 985, 2024 — 106 647, 2025 — 115 763, 2026 — 99 306; eng yuqori oy 2026-10 (18 333).
- **Kalit qiymatlar / Ключевые значения:** `500 000`, `84 299`, `93 985`, `106 647`, `115 763`, `99 306`, `2026-10`, `18 333`
- **Agent:** RU: ✅ (0.09 s) · UZ: ✅ (0.08 s)

## 5. Paxta narxi dinamikasi

- **RU:** Проанализируй динамику цены хлопка
- **UZ:** Paxta narxi dinamikasini tahlil qiling
- **Kutilgan javob / Ожидаемый ответ:** Paxta (so‘m/kg, oylik o‘rtachalar o‘rtachasi): 2022 — 5 827.69, 2023 — 6 703.04, 2024 — 7 344.2, 2025 — 8 739.13, 2026 — 9 665.5; barqaror o‘sish.
- **Kalit qiymatlar / Ключевые значения:** `5 827.69`, `6 703.04`, `7 344.2`, `8 739.13`, `9 665.5`
- **Agent:** RU: ✅ (0.09 s) · UZ: ✅ (0.09 s)

## 6. Bug‘doy hajmi 2024

- **RU:** Анализ объёма продаж пшеницы в тоннах за 2024 год
- **UZ:** 2024-yil bug‘doy savdo hajmi tahlili tonnada
- **Kutilgan javob / Ожидаемый ответ:** Bug‘doy 2024: jami 2 087 277 tonna (annulsiz); eng katta hajm oyi 2024-07.
- **Kalit qiymatlar / Ключевые значения:** `2 087 277`, `2024-07`
- **Agent:** RU: ✅ (0.09 s) · UZ: ✅ (0.08 s)

## 7. 2024 va 2025 taqqoslash

- **RU:** Сравни общую сумму сделок 2024 и 2025 годов
- **UZ:** 2024 va 2025 yillarda jami summani solishtiring
- **Kutilgan javob / Ожидаемый ответ:** 2024: 42 724 135 079 483.66 so‘m → 2025: 52 060 836 360 057.12 so‘m, o‘zgarish +21.9%.
- **Kalit qiymatlar / Ключевые значения:** `42 724 135 079 483.66`, `52 060 836 360 057.12`, `21.9`
- **Agent:** RU: ✅ (0.10 s) · UZ: ✅ (0.11 s)

## 8. Annul ulushi 2025

- **RU:** Какой процент сделок аннулирован в 2025 году?
- **UZ:** 2025-yilda bekor qilingan bitimlar ulushi necha foiz?
- **Kutilgan javob / Ожидаемый ответ:** 2025-yilda bekor qilingan bitimlar: 8 085 ta, ya’ni 6.98%.
- **Kalit qiymatlar / Ключевые значения:** `6.98`, `8 085`
- **Agent:** RU: ✅ (0.19 s) · UZ: ✅ (0.32 s)

## 9. USD bashorati noyabr 2026

- **RU:** Прогноз курса доллара на ноябрь
- **UZ:** Dollar kursi bashorati noyabr oyi uchun
- **Kutilgan javob / Ожидаемый ответ:** ⚠️ 2026-11 uchun ma’lumot yo‘qligi aytilishi SHART; taxmin ≈ 13 612.58 so‘m (95% oraliq 13 419.26 – 13 805.9).
- **Kalit qiymatlar / Ключевые значения:** `13 612.58`, `13 419.26`, `13 805.9`, ⚠️ ogohlantiriş
- **Agent:** RU: ✅ (0.23 s) · UZ: ✅ (0.16 s)

## 10. Bitimlar soni bashorati 2027

- **RU:** Прогноз количества сделок на 2027 год
- **UZ:** 2027-yil uchun bitimlar soni bashorati
- **Kutilgan javob / Ожидаемый ответ:** ⚠️ 2027-yil uchun ma’lumot yo‘qligi aytilishi SHART; 2027-yil jami taxmin ≈ 207 317.43 bitim.
- **Kalit qiymatlar / Ключевые значения:** `207 317.43`, ⚠️ ogohlantiriş
- **Agent:** RU: ✅ (0.25 s) · UZ: ✅ (0.27 s)
