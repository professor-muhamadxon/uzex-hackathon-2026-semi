# UZEX AI Hackathon — Saralash bosqichi: suhbat konspekti va qarorlar

> Bu fayl loyiha ustida ishlash jarayonidagi asosiy suhbat, tahlil va qabul qilingan
> texnik qarorlarni hujjatlashtiradi. Sana: 2026-11-05.

---

## 1. Vazifa (hackathon.uzex.uz/saralash)

**Maqsad:** birja bitimlari haqidagi savollarga rus va o‘zbek tillarida javob beradigan
AI-agent yaratish. Telegram-bot yoki veb-servis bo‘lishi mumkin.

### Asosiy talablar

| Talab | Izoh |
|---|---|
| Aniq va ma’lumotga asoslangan javob | raqamlar, nomlar, kodlar aniq bo‘lishi shart |
| Javob bo‘lmasa — ochiq aytish | “ma’lumotlarda topilmadi”; o‘ylab topish taqiqlanadi |
| Har bir javobga 90 soniya | komissiya 10 ta savol beradi |
| Savollar tili | rus yoki o‘zbek |
| Prototip | o‘rnatish va ro‘yxatdan o‘tishsiz ishlashi kerak |
| Muddat | 5-noyabr, 18:00 gacha prototip havolasi |
| Baholash (100 ball) | to‘g‘ri javoblar 60, prototip sifati 20, yechim tavsifi 20 |

**Muhim:** agent ma’lumotda yo‘q joyda raqam, kompaniya yoki tovar aytsa — jamoa
saralashdan chiqariladi (hallucination = diskvalifikatsiya).

---

## 2. Ma’lumotlar tahlili

Papka: `data/uzex_spot_data/`

| Fayl | Hajm | Mazmuni |
|---|---:|---|
| `deals_2022.csv` … `deals_2026.csv` | 500 000 bitim | 03.01.2022 – 30.10.2026 |
| `contracts.csv` | 6 616 | shartnoma kartochkalari |
| `participants.csv` | 14 392 | kompaniyalar (INN unikal) |
| `brokers.csv` | 120 | broker idoralari |
| `usd_rates.csv` | 1 765 | har kunlik USD kursi (so‘m) |

### Format xususiyatlari

- UTF-8, ajratuvchi vergul, matnda vergul bo‘lsa qo‘shtirnoq ichida.
- Sanalar `DD.MM.YYYY`, vaqt Toshkent vaqti.
- Pul summalari va narxlar **bo‘shliq bilan minglarga ajratilgan**, kasr nuqta bilan:
  `304 547 938.4`, `3 731.07`. `float()` dan oldin bo‘shliqni olib tashlash shart.
- `Лот` — bir lotdagi birlik soni (1, 12, 100, 1000).
- Bitim raqamlari yillar bo‘yicha davom etadi, ayrim raqamlar tashlab ketilgan.
- Holatlar 30.10.2026 holatiga qayd etilgan.

### Hisoblash formulalari

```
Hajm (birlikda)   = Количество × Лот
Birlik narxi      = Сумма сделки ÷ (Количество × Лот)
Eksport (so‘m)    = Сумма сделки × bitim sanasidagi USD kursi
```

### Join sxemasi

```
deals.Номер контракта   → contracts.Номер контракта
deals.ИНН продавца      → participants.ИНН
deals.ИНН покупателя    → participants.ИНН
deals.Брокер продавца   → brokers.Код брокера
deals.Брокер покупателя → brokers.Код брокера
deals.Дата сделки       → usd_rates.Дата
```

### Ma’lumot sifatidagi muammolar

1. **Region ikki tilda:** `deals` — o‘zbekcha (`Namangan viloyati`), `contracts` —
   ruscha (`Наманганская область`). Join faqat ID orqali.
2. **Tovar nomlari xilma-xil:** `1 сорт` / `1-сорта`, `II сорт` / `второй сорт`,
   `ПОЛИЭТИЛЕН` / `Полиэтилен`, `Хлопок сырец` / `Хлопок-сырец`.
3. **Kirill/lotin aralash kompaniya nomlari** (`"ҲАРАЙЎМ КИМЁ" МЧЖ`,
   `XUSIT POLIMER MCHJ`). INN — ishonchli kalit.
4. **Valyuta:** eksport bitimlari dollarda; “so‘mda jami” savolida konvertatsiya shart.
5. **Annul qilingan bitimlar** (`Аннулирован(Не оплачен)`) — “jami” hisoblashda
   qo‘shish/qo‘shmaslik savol mazmuniga bog‘liq; javobda filtr ko‘rsatilishi kerak.
6. **Holatlar:** `Новый`, `Не подписан`, `Заключен`, `Ждёт оплату`, `Оплачен`,
   `Исполнен`, `Исполнен(Частично)`, `Аннулирован(Не оплачен)`.

---

## 3. Muhokama qilingan yechimlar

### Savol: “Rank algoritmi va LLM bilan hal qilsa bo‘ladimi? RAG + vector DB semantik tahlil bilan?”

**Xulosa:** faqat RAG/vector DB bilan emas. Savollarning aksariyati aniq
hisob-kitob (`SUM`, `COUNT`, `GROUP BY`, sana filtri, valyuta konvertatsiyasi)
talab qiladi. Vektor qidiruv matn o‘xshashligini topadi, lekin agregatsiya qilmaydi.

To‘g‘ri formula:

> **LLM = tilni tushunish + reja + javob shakllantirish**
> **RAG/ranking = kompaniya/tovar nomlarini topish (entity linking)**
> **SQL/DuckDB = aniq raqam va agregatsiya**
> **Validator = javobdagi har bir raqam hisob natijasida borligini tekshirish**

500 000 bitim qatorini vectorga indekslash mantiqsiz — faqat kontraktlar,
kompaniyalar, tovar nomlari va brokerlarni indekslash kerak (~20–25 ming hujjat).

### 5 ta texnologik yechim

| # | Yechim | Mohiyati | Baho |
|---|---|---|---|
| 1 | **NL→SQL + Semantic Layer (DuckDB)** | savol → SQL → DuckDB → javob | ⭐⭐⭐⭐⭐ |
| 2 | **Hybrid RAG + SQL** | BM25 + vector + reranker; entity ID → SQL | ⭐⭐⭐⭐⭐ |
| 3 | GraphRAG / Neo4j | entity va aloqalar grafi | ⭐⭐⭐ |
| 4 | Agentic tool-calling | LLM tool’larni chaqiradi | ⭐⭐⭐⭐ |
| 5 | Intent + template SQL | niyat/slot → tayyor SQL | ⭐⭐⭐⭐ |

### Tanlangan arxitektura

**#5 (asosiy) + #1 (fallback) + #2 (entity linking)**

```
Savol → til aniqlash → intent/slot → template SQL
      → (topilmasa) NL→SQL → DuckDB → validator → javob + manba
```

---

## 4. System 1 / System 2 va SQL generator haqida qarorlar

| Vazifa | Model |
|---|---|
| Til aniqlash, intent, entity | System 1 (tez) |
| Oddiy SQL | System 1 + template |
| Murakkab SQL (ko‘p join), repair, “javob bormi?” | System 2 (reasoning) |
| Javobni shakllantirish | System 1 |

**Qoida:** LLM hisoblamaydi — raqamni DuckDB hisoblaydi. LLM faqat SQL yozadi va
javobni tushunarli qiladi.

**SQL generator pipeline:**

```
LLM → JSON {sql, assumptions, confidence}
 → sqlglot sintaksis
 → SELECT-only / whitelist
 → EXPLAIN
 → read-only execute (timeout)
 → natija tekshiruvi
 → xato bo‘lsa repair (max 2)
 → baribir bo‘lmasa: “topilmadi”
```

Qo‘shimcha usullar: semantic view’lar, schema card + qiymat lug‘ati, structured
output, execution-guided repair, self-consistency (2–3 SQL natijasini solishtirish).

---

## 5. Lokal agent + Telegram bot muhokamasi

**Stsenariy:** foydalanuvchi botga savol yozadi → aiogram → lokal agent
(FastAPI + DuckDB + LLM) → javob.

### Xavflar

| Xavf | Yechim |
|---|---|
| Kompyuter o‘chsa, bot ishlamaydi | VPS yoki doim yoniq kompyuter, `restart: always` |
| Lokal model sifati past | 7B–14B quantized + template SQL + validator; gibrid cloud |
| Lokal model sekin | kichik kontekst, keshlash, System 1 |
| Telegram 4096 belgi | qisqa javob, fayl bilan batafsil |
| HTML/Markdown xatosi | `parse_mode=HTML` + escape |
| Token oshkorligi | `.env`, repoga qo‘ymaslik |
| Public botga spam | per-user rate limit |
| O‘zbek tili sifati | javob shablonlari; LLM faqat SQL |

**Muhim:** Telegram polling rejimida public IP/domen shart emas. Bot o‘zi Telegram
serverlariga ulanadi. Webhook uchun HTTPS va domen kerak.

---

## 6. Yakuniy tavsiya va qabul qilingan qaror

> **Python + FastAPI + DuckDB + template SQL + NL→SQL fallback + validator +
> aiogram, cloud LLM (asosiy) va lokal model (fallback), VPS’da polling.**

### Nega bu?

- 500k qator DuckDB uchun kichik — so‘rovlar millisekundlarda.
- Template SQL barqaror va hallucination’ni deyarli yo‘q qiladi.
- NL→SQL noma’lum savollarni qoplaydi.
- Validator har bir raqamni tekshiradi.
- Telegram bot o‘rnatishsiz/ro‘yxatdan o‘tishsiz ishlaydi.
- Keyinchalik vector DB / GraphRAG qo‘shish uchun arxitektura ochiq.

### Nimani qilmaslikka qaror qilindi

- GraphRAG / Neo4j — hozircha ortiqcha.
- 500k qatorni vectorga indekslash — mantiqsiz.
- Fine-tuning — vaqt va foyda nisbati past.
- Multi-agent loop — latency va xato.
- Faqat lokal 70B model — 90 soniyaga sig‘maydi.
- LLM’ga arifmetikani topshirish — diskvalifikatsiya xavfi.

---

## 7. Amaliy reja (bugungi ish)

1. **ETL:** CSV → DuckDB; `amount_uzs`, `volume`, `unit_price`, `deal_date`.
2. **Semantic view’lar:** `deals_enriched`, `contracts_full`, `company_stats`.
3. **Template SQL:** jami summa, bitim soni, top-N, kompaniya profili, tovar,
   kontrakt, eksport, holat, region, broker.
4. **NL→SQL fallback + validator.**
5. **Telegram bot:** `/start`, til aniqlash, “Tahlil qilinmoqda...”, manba.
6. **Lokal ishga tushirish:** CLI + FastAPI; keyin VPS/Docker.
7. **Test savollar to‘plami:** 30–50 ta RU/UZ savol, javoblarni tekshirish.

### Birinchi bosqich (hozir)

- Loyiha skeleti va `README.md`.
- `scripts/build_db.py` — DuckDB bazasini yig‘ish.
- `app/` — agent, intents, SQL shablonlari, validator.
- `app/cli.py` — kompyuterda terminaldan test qilish.
- `app/bot.py` — Telegram bot (token bo‘lsa ishlaydi).
- `app/api.py` — FastAPI (keyin host uchun).

---

## 8. Suhbat xronologiyasi (qisqa)

1. Foydalanuvchi hackathon sahifasini va `data/uzex_spot_data/` papkasini ko‘rsatdi,
   fayllarning birinchi 100 qatorini o‘qishni so‘radi.
2. Sayt talablari va CSV tuzilishi tahlil qilindi; join sxemasi, formatlash
   muammolari, valyuta va region nomuvofiqligi aniqlandi.
3. Foydalanuvchi “Rank algoritmi va LLM bilan hal qilish mumkinmi? RAG + vector DB
   semantik tahlil bilan” deb so‘radi.
4. 5 ta texnologik yechim, backend tili (Python) va gibrid yondashuv tavsiya qilindi.
5. System 1 / System 2 modellari va SQL generator bo‘yicha tavsiyalar berildi.
6. Lokal agent + Telegram bot stsenariysi, xavflar va deploy variantlari muhokama qilindi.
7. Yakuniy tavsiya: **Gibrid SQL-agent (template SQL + NL→SQL fallback + DuckDB +
   validator), Telegram bot, Python, VPS’da polling.**
8. Foydalanuvchi: “tayyorla, oldiniga tizim mening kompyuterimda ishlasin, keyin
   hostga joylaymiz; boshlashdan avval readme.challange.md faylga suhbatimizni
   yozib ol” — shu fayl yaratildi.

---

## 9. Qabul qilingan qarorlar (checklist)

- [x] Backend tili — Python.
- [x] Baza — DuckDB (lokal fayl).
- [x] Asosiy yo‘l — intent + template SQL.
- [x] Fallback — NL→SQL + validator.
- [x] Entity linking — normalizatsiya + fuzzy/transliteratsiya (vektor keyinroq).
- [x] LLM — cloud asosiy, lokal fallback.
- [x] Interfeys — Telegram bot (aiogram) + CLI + FastAPI.
- [x] Deploy — avval lokal, keyin VPS + Docker, polling.
- [ ] Hostga joylashtirish (keyingi bosqich).

---

## 10. Amalga oshirilgan ishlar (2026-11-05)

### Baza

- `data/uzex.duckdb` yig‘ildi: 500 000 bitim, 6 616 kontrakt, 14 392 kompaniya,
  120 broker, 1 765 USD kursi.
- `deals_enriched` jadvali: `amount_uzs`, `volume`, `unit_price`, `usd_rate`,
  TNVED, kategoriya, region va boshqa maydonlar.
- Barcha 500 000 bitim uchun `amount_uzs` va `volume` hisoblangan (null yo‘q).
- Indekslar: sana, kontrakt, sotuvchi/xaridor INN, holat, TNVED.

### Agent

- `app/parser.py` — til, intent, davr/oy, holat, tur/forma, tovar, region,
  kompaniya (INN va fuzzy), broker, kontrakt/bitim raqami.
- `app/sql.py` — jami, top (kompaniya/tovar/region/broker), kompaniya profili,
  tovar statistikasi, kontrakt/bitim kartochkasi, eksport, holat, ro‘yxat.
- `app/formatter.py` — o‘zbekcha/ruscha javob, raqamlar, valyuta, o‘lchov birligi,
  manba va filtr satri.
- `app/validator.py` — LLM SQL’i uchun SELECT-only va oq ro‘yxat tekshiruvi.
- `app/agent.py` — shablon SQL -> (topilmasa) LLM -> validator -> javob.
- Bo‘sh natija (0 bitim) avtomatik “topilmadi” deb qaytariladi.

### Interfeyslar

- `app/cli.py` — terminal, `--debug` bilan SQL/filtr ko‘rsatadi.
- `app/api.py` — FastAPI `/ask`, `/health`.
- `app/bot.py` — aiogram 3 polling, `/start`, `/help`, uz/ru salomlashish,
  uzun javoblarni 4000 belgidan bo‘lish.

### Testlar

- `scripts/smoke_test.py` — 33 ta UZ/RU savol: jami summa, bitim soni, paxta,
  top kompaniya/tovar/region/broker, kontrakt, bitim, annul, eksport, oy filtri,
  kompaniya profili, INN, “topilmadi” holatlari.
- Natija: **33/33 OK**.

### Ma’lum cheklovlar

- `TELEGRAM_BOT_TOKEN` hali kiritilmagan — botni ishga tushirish uchun token kerak.
- LLM fallback hali real endpoint bilan sinalmagan; shablonsiz savollar hozircha
  “aniqlashtiring” deb javob beradi.
- “Экспорт хлопка” kabi so‘rovlar 0 natija beradi, chunki ma’lumotlarda paxta
  faqat ichki bozorda sotilgan — agent buni “topilmadi” deb to‘g‘ri aytadi.
