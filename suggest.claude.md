# UZEX AI Hackathon — Claude tavsiyalari

> `readme.challange.md` dagi rejaga qöşimça: nimani kuçaytiriş, nimadan ehtiyot böliş va
> qolgan vaqtni qanday taqsimlaş kerak. Sana: 2026-11-05, 12:50 (muddat — 18:00 gaça).

Arxitektura tanlovi (template SQL + NL→SQL fallback + DuckDB + validator + aiogram) töğri.
Quyidagi tavsiyalar şu arxitekturani **diskvalifikatsiyadan himoyalaş** va **ballni oşiriş**ga qaratilgan.

---

## 0. Eng muhim 5 ta qoida (agar faqat şuni öqisangiz)

1. **LLM javob matnida raqam yozmaydi.** Raqam, nom, INN, kod — faqat SQL natijasidan
   dastur orqali shablonga qöyiladi. LLM faqat boğlovçi matnni yozadi yoki umuman
   işlatilmaydi.
2. **“Bugun” = 30.10.2026**, haqiqiy sana emas. “Ötgan oy”, “bu yil”, “в прошлом квартале”
   maʼlumotlar oxirgi sanasiga nisbatan hisoblanadi.
3. **Topilmasa — topilmadi.** Fuzzy-match past işonç bilan boşqa kompaniyani “topib” bermasin.
4. **Javobda filtrlarni ayting:** davr, holat (annul qilinganlar kiritilganmi), valyuta, kurs sanasi.
5. **18:00 dan tekşiruv boşlanadi va prototip muzlatiladi.** 18:00 dan keyin özgartiriş mumkin emas,
   bot esa doim işlab turişi şart — noutbukda emas, VPS'da.

---

## 0.1. Saytdan aniqlangan qöşimça talablar (hackathon.uzex.uz/saralash)

| Talab | Rejaga taʼsiri |
|---|---|
| Topşiriş — Google Forma: prototip havolasi, jamoa aʼzolari (≤3), yeçim tavsifi, rahbar telefoni | Tavsif **formaga matn** sifatida kiradi — `SOLUTION.md` dan qisqa variantni oldindan tayyorlang |
| 18:00 gaça formani qayta yuboriş mumkin | **Birinçi versiyani 16:30 da yuboring**, keyin yangilang — kech qoliş xavfi yöqoladi |
| 18:00 dan keyin prototipni özgartiriş mumkin emas | 17:30 dan keyin faqat kritik bug fix; 18:00 da deploy tegilmaydi |
| Komissiya 18:00 dan boşlab tekşiradi | Bot 17:45 da işlayotgan, monitoring (masalan, har 5 daqiqada `/health`) bilan |
| Javob tili = savol tili | Til aniqlaş majburiy, aralaş javob — kamçilik |
| Prototip sifati: “javob nimaga asoslangani körinadi”, RU/UZ, qulay va tez | Asos (filtr, davr, qatorlar soni) **javobning özida**, tugma ortida emas; SQL — tugmada |
| Tavsif: texnologiyalar va **javoblar qanday tekşirilgani** | Validator, test töplami va aniqlik foizini alohida bandda yozing |
| Telegram şart emas, veb-servis ham böladi | Bot + oddiy veb-sahifa — ikkalasi bitta agent'ga ulanadi |
| Kod/prototipni boşqalarga bermaslik — mosliklar tekşiriladi | Repo yopiq (private) bölsin |
| 10 savol × 6 ball, savollar oldindan eʼlon qilinmaydi | Keng intent qamrovi + NL→SQL fallback muhim |
| Dataset README'da har maydon RU/UZ tavsiflangan | Schema card'ni şu README'dan yiğing — ustun nomlarining özbekça/ruscha sinonimlari tayyor |

---

## 1. Vaqt rejasi (bugun, ~5 soat)

| Vaqt | Iş | Natija |
|---|---|---|
| 13:00–13:45 | ETL + normalizatsiya + semantic view'lar | `uzex.duckdb`, `deals_enriched` |
| 13:45–15:00 | 10–12 ta intent + SQL şablonlari + javob şablonlari | CLI'da 20 ta savolga javob |
| 15:00–15:45 | Validator + “topilmadi” mantiqi + NL→SQL fallback | gallyutsinatsiya testi |
| 15:45–16:30 | Telegram bot + VPS'ga deploy (Docker yoki systemd) | işlayotgan havola |
| 16:30 | **Formani birinçi marta yuboriş** (havola + qisqa tavsif) | xavfsizlik nuqtasi |
| 16:30–17:20 | 40 ta test savol, xatolarni tuzatiş | regressiya natijasi |
| 17:20–17:40 | Yeçim tavsifi (20 ball), formani qayta yuboriş | `SOLUTION.md` + sxema |
| 17:40–18:00 | Kod muzlatiladi, faqat monitoring | **18:00 dan keyin özgartiriş yöq** |

Agar vaqt yetmasa — **NL→SQL fallback'ni qisqartiring, validator va “topilmadi”ni emas.**
Noaniq savolga “topilmadi” deyiş — 0 ball; xato raqam aytiş — saralaşdan çiqiş.

---

## 2. Gallyutsinatsiyaga qarşi himoya (asosiy xavf)

### 2.1. Javobni “slot-filling” bilan yiğiş

```
SQL natija (dict)  →  javob şabloni (UZ/RU)  →  [ixtiyoriy] LLM faqat ravonlaştiradi
```

```python
TEMPLATES = {
  "total_amount": {
    "uz": "{period} davrida {product} böyiça jami bitimlar summasi: {amount} {currency} "
          "({count} ta bitim, holat: {status_filter}).",
    "ru": "За период {period} общая сумма сделок по {product}: {amount} {currency} "
          "({count} сделок, статус: {status_filter}).",
  },
}
```

### 2.2. Validator (har javobga majburiy)

1. Javobdan barça raqamlarni regex bilan ajratiş (`\d[\d\s]*[.,]?\d*`).
2. Har bir raqam SQL natijasidagi qiymatlardan birining formatlangan körinişiga mos kelişi kerak
   (yaxlitlaş toleransi ±0.01).
3. Javobdagi kompaniya/tovar nomlari — `participants`/`contracts` dagi aniq qiymatlar bölişi kerak.
4. Mos kelmasa → LLM matnini taşlab, **sof şablon javob** qaytariş.
5. Natija böş bölsa → “topilmadi” şabloni (LLM'ga umuman bormaydi).

### 2.3. LLM sozlamalari

- `temperature=0`, structured output (JSON schema).
- LLM'ga **hech qaçon** xom qatorlarni yubormang — faqat schema card va qiymat luğati.
- Hisoblangan hosilalar (foiz, örtaça, farq) — Python/SQL'da, LLM'da emas.

---

## 3. “Topilmadi” mantiqini 3 turga ajrating

| Tur | Misol | Javob |
|---|---|---|
| Davr dataset'dan taşqarida | “2021-yil…”, “2026-yil dekabr” | “Maʼlumotlar 03.01.2022–30.10.2026 oraliğini qamraydi” |
| Entity topilmadi | yöq kompaniya, yöq tovar | “«X» nomli qatnaşçi maʼlumotlarda topilmadi” |
| Maydon yöq | “marja qança?”, “yetkazib beriş muddati?” | “Bu körsatkiç maʼlumotlarda mavjud emas” |
| Natija böş | filtr töğri, lekin 0 qator | “Şu şartlar böyiça bitimlar topilmadi” |

Komissiya ataylab “tuzoq” savollar beradi — bu turlar bal oladi.

---

## 4. Entity linking: özbek/rus/kirill/lotin xususiyatlari

### 4.1. Normalizatsiya funksiyasi (kompaniya va tovar uçun bitta)

```python
def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    s = translit_cyr2lat(s)          # ҳ→h, ў→o, қ→q, ғ→g, ш→sh, ч→ch, ...
    s = re.sub(r"[ʻʼ'’`´]", "", s)    # apostrof turlari
    s = re.sub(r"\b(mchj|мчж|ооо|xk|хк|aj|аж|ao|ао|ok|чп|xususiy korxona)\b", "", s)
    s = re.sub(r"[\"«»“”()\-.,]", " ", s)
    return re.sub(r"\s+", " ", s).strip()
```

- Lotin tomoni uçun ham eski (o‘, g‘, sh, ch), ham yangi (ö, ğ, ş, ç) yozuvni bitta
  kanonik şaklga keltiring — foydalanuvçi qaysi alifboda yozişini bilmaymiz.
- Tovar uçun qöşimça: rim raqamlari → arab (`II сорт` → `2 сорт`), `второй/1-сорта` → `N сорт`,
  `хлопок-сырец` → `хлопок сырец`.
- Kanonik ustunni DuckDB'da **oldindan** saqlang: `company_norm`, `product_norm`.

### 4.2. Qidiruv tartibi

```
INN aniq (savolda 9 xonali raqam) → norm aniq moslik → rapidfuzz (token_set_ratio ≥ 90)
→ 80–90: “«Y» nazarda tutilganmi?” emas, javobda topilgan aniq nomni körsating
→ < 80: topilmadi
```

Bir nechta nomzod bölsa — eng köp bitimlisini emas, **barçasini** (≤3) körsating yoki
INN böyiça ajratiş kerakligini ayting.

### 4.3. Til aniqlaş

Uç holat bor, ikkitasi emas:

- **Rus kirill** — standart.
- **Özbek kirill** (`ў қ ғ ҳ` harflari yoki özbekça qöşimçalar: `-нинг`, `-да`, `қанча`) — özbekça javob.
- **Özbek lotin** — özbekça javob.

**Javob yozuvi:** savol qaysi yozuvda bölsa, şunda javob bering (eski lotin `o‘/g‘`, yangi `ö/ğ`,
yoki kirill). Bu “aqlli” körinadi va tavsifda alohida plyus sifatida yoziladi.
Bunga `uzbek-script` skill'idagi `convert.py` (legacy↔new) tayyor işlatiladi.

---

## 5. Sana va valyuta

- **Kurs join'i — ASOF JOIN** (dam oliş kunlari kurs bölmasligi mumkin):

```sql
SELECT d.*, r.rate AS usd_rate
FROM deals d
ASOF LEFT JOIN usd_rates r ON d.deal_date >= r.rate_date;
```

- Javobda “sömga {sana} kursi böyiça” emas, “**har bir bitim öz sanasidagi kurs böyiça**”
  deb aniq yozing.
- Nisbiy sanalar parseri (UZ/RU): “ötgan yil/oy/hafta”, “1-çorak”, “yanvar–mart”,
  “в 2024 году”, “за последние 3 месяца”, “с 01.03.2025 по 15.04.2025”.
  Anker — `MAX(deal_date)` = 30.10.2026.
- Oy nomlari: özbek (yanvar…dekabr) + rus (январь/января/январе…) — barça kelişik şakllari.

---

## 6. Annul qilingan bitimlar va holatlar

- **Default:** “jami summa/hajm” → `Аннулирован` larsiz; “bitimlar soni” → barçasi.
  Qaysi biri tanlangan bölsa, javob oxirida bir qator bilan ayting.
- Agar savolda holat aytilsa (“ijro etilgan”, “исполненные”, “tölangan”) — holat luğati:

| Savoldagi söz | Holatlar |
|---|---|
| ijro etilgan / исполненные | `Исполнен`, `Исполнен(Частично)` |
| tölangan / оплаченные | `Оплачен`, `Исполнен`, `Исполнен(Частично)` |
| bekor qilingan / аннулированные | `Аннулирован(Не оплачен)` |
| tuzilgan / заключенные | `Заключен` va undan keyingi barça holatlar |

Bu luğatni oldindan kelişib oling va `SOLUTION.md` ga yozing.

---

## 7. Ehtimoliy savol turlari (intent'lar, ustuvorlik böyiça)

1. Davr böyiça jami summa / hajm / bitimlar soni (tovar, region, valyuta filtri bilan)
2. Top-N sotuvçi / xaridor / tovar / broker
3. Kompaniya profili (INN, nom, region, bitimlar soni, summa, asosiy tovarlar)
4. Tovar narxi: örtaça, min/max, oxirgi narx, dinamika (oyma-oy)
5. Aniq bitim yoki kontrakt raqami böyiça maʼlumot
6. Eksport bitimlari (USD) va ularning sömdagi ekvivalenti
7. Region böyiça statistika
8. Broker böyiça statistika
9. Holat taqsimoti (neça foizi annul qilingan)
10. Sanadagi USD kursi
11. Ikki davr / ikki kompaniya taqqoslaşi
12. “Eng birinçi/oxirgi bitim” turidagi savollar

1–6 ni şablon bilan 100% qoplang; qolganlari NL→SQL fallback'ga tuşsa ham bölaveradi.

---

## 8. Tezlik (90 soniya)

- Maqsad: **< 15 soniya**, 90 emas. Har bosqichga timeout: intent 5 s, SQL 10 s, LLM 20 s.
- DuckDB ulanişi işga tuşganda bir marta, `read_only=True`.
- LLM timeout bölsa → şablon javob; şablon ham bölmasa → “topilmadi”.
- Telegram'da darhol “⏳ Tahlil qilinmoqda…” yuborib, keyin `edit_message_text` bilan almaştiring.

---

## 9. Xavfsizlik va barqarorlik

- DuckDB: `read_only=True`, `SET enable_external_access=false`, `LIMIT 100` majburiy.
- sqlglot bilan faqat `SELECT`/`WITH`; `COPY`, `ATTACH`, `PRAGMA`, `INSTALL` taqiqlangan.
- Per-user rate limit (masalan, 1 savol / 3 s), global semafor (bir vaqtda ≤4 LLM çaqiruv).
- Barça savol/javob/SQL'ni `logs/qa.jsonl` ga yozing — 18:00 dan keyin tuzatib bölmaydi, lekin xakaton bosqiçi uçun foydali.
- Bot yiqilsa avtomatik qayta işga tuşsin: `restart: always` yoki `systemd Restart=always`.

---

## 10. Prototip sifati (20 ball)

- `/start` — 3–4 ta misol savol (UZ + RU), tugma körinişida.
- Javobning özida qisqa asos: “Manba: 2024-yil, holat: annulsiz, 1 284 ta bitim”. Ostida **“🔎 Qanday hisoblandi?”** inline tugmasi → SQL va filtrlar.
  Bu şaffoflik va işonçni körsatadi.
- Uzun natija (top-20, jadval) → qisqa javob + `.csv` fayl.
- Raqam formati: minglar böşliq bilan, valyuta aniq (`1 234 567,89 söm` / `1 234 567,89 сум`, `$`).
- Zaxira havola: FastAPI'da oddiy veb-sahifa (bitta input + javob) — Telegram bloklanib
  qolsa yoki komissiya brauzerdan tekşirmoqçi bölsa.

---

## 11. Test töplami (regressiya)

- 40 ta savol: 20 UZ (10 lotin, 5 kirill, 5 yangi alifbo) + 20 RU.
- Kamida **10 tasi tuzoq**: yöq kompaniya, 2021-yil, yöq maydon, xato yozilgan tovar nomi.
- “Oltin” javoblarni **bot kodidan mustaqil**, qölda yozilgan SQL bilan hisoblang.
- `scripts/eval.py` — barçasini yurgizib, raqam mosligi, “topilmadi” töğriligi va vaqtni çiqarsin.
- Har kod özgarişidan keyin qayta yurgizing.

---

## 12. Yeçim tavsifi (20 ball) — `SOLUTION.md` tuzilmasi

1. Muammo va talablar (1 abzas)
2. Arxitektura sxemasi (Mermaid): savol → til → intent → SQL → DuckDB → validator → javob
3. **Javoblar qanday tekşiriladi** (alohida baholanadi): şablon, validator, “topilmadi” turlari, read-only SQL
4. Maʼlumot tozalaş: normalizatsiya, transliteratsiya, ASOF kurs, holatlar luğati
5. Qabul qilingan farazlar (annul, “bugun” = 30.10.2026, kurs)
6. Test natijalari jadvali (40 savol: aniqlik %, örtaça vaqt)
7. Çeklovlar va keyingi qadamlar (vektor qidiruv, GraphRAG — kerak bölsa)

---

## 13. Qilmaslik kerak bölgan narsalar (qöşimça)

- Javobni “çiroyli” qiliş uçun LLM'ga raqamlarni qayta yozdirmang.
- Komissiya savollarini oldindan bilganday “hardcode” qilmang — tekşirib qolişsa ball kesiladi.
- Oxirgi soatda arxitekturani özgartirmang; faqat bug fix.
- Bot tokenini, API kalitni repoga yoki skrinşotga çiqarmang.
- Bitta LLM provayderga 100% boğlanmang: timeout'da şablon javob işlasin.

---

## 14. Qisqa checklist

- [ ] `MAX(deal_date)` = 30.10.2026 anker sifatida işlatilgan
- [ ] Javobdagi har raqam SQL natijasidan
- [ ] 4 xil “topilmadi” javobi
- [ ] Kirill / eski lotin / yangi lotin özbekça savollar tanilyapti
- [ ] ASOF kurs join
- [ ] Annul filtri javobda aytilyapti
- [ ] “Qanday hisoblandi?” tugmasi
- [ ] VPS'da `restart: always`
- [ ] 40 ta test, ≥90% töğri, örtaça < 15 s
- [ ] `SOLUTION.md` tayyor
- [ ] 16:30 da forma birinçi marta yuborilgan, 17:40 da yangilangan
- [ ] 18:00 dan keyin deploy'ga tegilmaydi
