# UZEX AI-agent: qilingan ishlar hisoboti

Sana: 2026-11-05. Holat: 18:00 (muddat tugadi).
Tayyorladi: Qo‘qon universiteti Andijon filiali (KUAF) ishtirokchilari.
Repo: https://github.com/professor-muhamadxon/uzex-hackathon-2026-semi

## 1. Maqsad

Birja bitimlari reyestri (500 000 bitim, 03.01.2022 – 30.10.2026) bo‘yicha rus va o‘zbek tilidagi savollarga
**aniq, ma’lumotga asoslangan** javob beradigan agent. Ma’lumotda yo‘q narsani to‘qib chiqarish taqiqlangan
(gallyutsinatsiya = diskvalifikatsiya), shuning uchun asosiy qoida: **LLM raqam yozmaydi**.

## 2. Arxitektura (qisqa)

savol → til va yozuvni aniqlash → qoidalar bilan tahlil (davr, holat, tovar, viloyat, kompaniya, maqsad)
→ tayyor SQL shablon → DuckDB (faqat o‘qish) → javob shabloni → raqamlarni tekshirish → savol yozuviga moslash.

- Hamma raqam, nom va kod SQL natijasidan olinadi, matn shablondan.
- Ma’lumot bo‘lmasa: "topilmadi" (davr tashqarida, kompaniya yo‘q, ko‘rsatkich yo‘q, natija bo‘sh).
- LLM hozir **o‘chiq** (`LLM_ENABLED=0`). Tizim LLM'siz to‘liq ishlaydi.

## 3. Qilingan ishlar (bosqichlar bo‘yicha)

### 3.1. Asos
- CSV → DuckDB (`app/etl.py`, `scripts/build_db.py`): 500 000 bitim, 6 616 kontrakt, 14 392 kompaniya, 120 broker, 1 765 kurs.
- Parser, SQL shablonlar, formatter, CLI, FastAPI, Telegram bot (aiogram).

### 3.2. Aniqlikni oshirish
- **Nisbiy sanalar** (30.10.2026 ga nisbatan): o‘tgan yil/oy/hafta, choraklar, yarim yillik, "oxirgi N oy", "yanvar–mart".
- **Annul qilingan bitimlar:** summa, hajm va narxda hisobga olinmaydi; bitimlar sonida hisobga olinadi. Javobda aytiladi.
- **Holatlar lug‘ati:** "ijro etilgan", "to‘langan", "bekor qilingan" va boshqalar.
- **Kompaniyani topish:** INN bo‘yicha aniq; nom bo‘yicha faqat farqlovchi so‘zlar mos kelganda. Mavjud bo‘lmagan kompaniya "topib berilmaydi".
- **Yangi alifbo** (ö ğ ç ş) va o‘zbek kirill to‘g‘ri tushuniladi (avval ў, й harflari yo‘qolardi).
- **Savol tilida javob:** eski lotin, yangi alifbo yoki kirill; holat, viloyat, birlik va tovar nomlari ham savol tiliga o‘giriladi (`app/script.py`, `app/localize.py`).

### 3.3. Ishonchlilik
- **Raqam tekshiruvi** (`app/validator.py`): javobdagi har raqam va sana SQL natijasi yoki savoldagi filtr bilan solishtiriladi.
- **Har javobda "Qanday hisoblandi"** qatori, filtrlar, tashlab yuborilgan annul bitimlar soni va manba (`app/explain.py`).
- SQL xavfsizligi: faqat o‘qish, ruxsat etilgan jadvallar, 10 s timeout.

### 3.4. Yangi savol turlari
- USD kursi (sana/davr), eng katta/kichik/birinchi/oxirgi bitim, noyob xaridor va sotuvchilar soni.
- Yillar va oylar bo‘yicha taqqoslash, ulushlar (holat, kontrakt shakli/turi, savdo turi).
- O‘rtacha bitim summasi, ro‘yxatdan o‘tgan kontraktlar soni, yetkazib berish (yetkazilmagan lotlar).
- Eng arzon/qimmat viloyat va tovar, eng faol xaridorlar.
- **Kesimlar** (`breakdown`): viloyat, tovar yoki hafta kuni bo‘yicha; kompaniyalar soni viloyat bo‘yicha.

### 3.5. Tahlil va bashorat (`app/analytics.py`)
- **Tahlil:** boshlanish/oxirgi qiymat, min/max (sanasi bilan), o‘rtacha, tebranish, yillar bo‘yicha o‘zgarish, chiziqli trend va R².
- **Bashorat** (faqat "bashorat/prognoz/прогноз" so‘zi bilan): oxirgi 12 oy bo‘yicha chiziqli regressiya, 95% oraliq.
  Javob **doim** ogohlantirish bilan boshlanadi: ko‘rsatilgan davr uchun ma’lumot berilmagan (ma’lumot 30.10.2026 gacha), bu statistik taxmin.
- Bashorat so‘zi bo‘lmagan kelajak savollari ("2027-yilda nechta bitim bo‘ladi?") "topilmadi" oladi.
- Bashorat hisobi alohida Python bilan tekshirilgan, natija bir xil.

### 3.6. Xato yozuvga chidamlilik
- "binzin" → "benzin": eng yaqin tovar nomi olinadi va javobda aytiladi (ℹ️ qatori).
- Ikki tovar teng mos kelsa yoki so‘z umuman noma’lum bo‘lsa (masalan "kompyuter"): "topilmadi", taxmin qilinmaydi.
- "Necha foizda oshgan?" turidagi savollar o‘sish foizi sifatida javob oladi (narx, kurs, soni, summa).

### 3.7. LLM ma’no qatlami (ixtiyoriy, hozir o‘chiq)
- `app/semantic.py`: shablonga tushmagan savollar uchun kichik LLM faqat qisqa JSON beradi (tur, ko‘rsatkich, kesim, tovar so‘zi).
- Har maydon qat’iy ro‘yxat bo‘yicha tekshiriladi, tovar katalogdan o‘tkaziladi, javobni baribir SQL shablon hisoblaydi.
- LLM SQL yozishi `LLM_SQL=1` bayrog‘i ortida, standart holatda o‘chiq.
- Soxta (mock) LLM bilan sinalgan. **Haqiqiy model yuklanmagan** (Ollama o‘rnatilgan, `qwen2.5-coder:7b` yuklanmagan).

### 3.8. Bot va veb
- Bot: "Xush kelibsiz" xabari, bot tavsifi, KUAF izohi, misol tugmalari, "⏳" xabari, SQL tugmasi, 3 soniyalik cheklov, katta natija uchun CSV.
- Veb-sahifa (`GET /`) va `POST /ask`, `GET /health`.
- Har savol va javob `logs/qa.jsonl` ga yoziladi.
- `run.py` (qulab tushganda qayta ishga tushiradi) va `run.sh` (venv, kutubxonalar, baza, ishga tushirish; `--web`, `--bot`, `--bg`, `--stop`, `--check`).
- `Dockerfile` va `docker-compose.yml` (bot va veb, `restart: always`). Docker bu kompyuterda sinalmagan.

## 4. Testlar (oxirgi yurgizish)

| To‘plam | Natija |
|---|---|
| `scripts/smoke_test.py` | 33/33 |
| `scripts/eval.py` (81 savol, shundan 13 tuzoq) | 81/81, tasdiqlanmagan raqam: 0 |
| `scripts/analytics_test.py` (10 savol × RU/UZ) | 20/20 (varaqa: `docs/ANALYTICS_TEST.md`) |

Kutilgan javoblar agent kodidan mustaqil SQL/Python bilan hisoblangan. Testlarni men ishlab chiqish davomida
yozganman, shuning uchun komissiyaning yangi savollarida aniqlik pastroq bo‘lishi mumkin.

Mustaqil SQL yordamida topilgan va tuzatilgan xatolar: annul bitimlar kesimda qo‘shilib ketgan; "Проанализируй…"
tahlil deb tanilmagan; yillik dollar o‘rtachasi oylik o‘rtachalarning o‘rtachasi bo‘lib chiqqan; "Farg‘ona"
ichidagi "argon" tovar deb tanilgan; "Kontrakt N" bitim deb o‘qilgan; "buyer" so‘rovida sotuvchilar chiqqan.

## 5. Ma’lum cheklovlar

- 40 ta yangi savollik sinovda tizim taxminan yarmiga ishonch bilan **boshqa savolga** javob bergan edi. Kesim va
  "qaysi viloyatda…" turidagilari tuzatildi, lekin quyidagilar hali shunday: "в срок" (muddatida to‘langan),
  "срок оплаты", "lot hajmi", "dizel va benzinni solishtir" (faqat benzin chiqadi), "qaysi oyda kurs eng yuqori",
  "bitta tovar sotuvchilari soni", "доля экспорта" (holatlar ulushi chiqadi), "eng uzoq muddatli kontrakt".
- Noma’lum tovar so‘zini rad etish hozir faqat o‘sish foizi savollarida ishlaydi.
- Benzin ikki birlikda sotiladi (tonna va litr). Javob eng ko‘p uchraydigan birlikni oladi va uni yozadi.
- Viloyat filtri sotuvchi ombori viloyatini bildiradi (javobda yoziladi), xaridor viloyatini emas.
- Bashorat oddiy chiziqli trend; mavsumiylik hisobga olinmagan.

## 6. Ochiq masalalar (18:00 holati)

1. **Bot va veb-ilova hozir ishlamayapti** (tekshirilganda `/health` javob bermadi, bot jarayoni yo‘q). Tekshiruv uchun ishga tushirish kerak: `./run.sh --bg`.
2. **Doimiy joy yo‘q:** hozircha hammasi shu kompyuterda. Kompyuter o‘chsa yoki uxlasa, tizim ham to‘xtaydi. Server (VPS) hal qilinmagan.
3. **LLM ishlamayapti:** model yuklanmagan; ma’no qatlami faqat soxta LLM bilan sinalgan.
4. Repo **ochiq (public)**: kod boshqalarga ko‘rinadi, o‘xshashlik tekshiruvida muammo bo‘lishi mumkin.

## 7. Ishga tushirish

```bash
./run.sh --check   # baza + testlar
./run.sh --bg      # veb (8000) va bot, fonda; to‘xtatish: ./run.sh --stop
python -m app.cli --debug "2025-yilda jami savdo summasi qancha?"
```

Asosiy fayllar: `app/parser.py` (tahlil), `app/sql.py`, `app/extra.py`, `app/analytics.py` (hisoblar),
`app/formatter.py`, `app/explain.py`, `app/localize.py`, `app/script.py` (javob), `app/validator.py` (tekshiruv),
`app/semantic.py` (ixtiyoriy LLM), `app/bot.py`, `app/api.py`, `SOLUTION.md` (yechim tavsifi).
