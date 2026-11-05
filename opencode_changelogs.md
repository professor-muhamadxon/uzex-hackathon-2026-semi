# OpenCode changelog

> Bu fayl OpenCode agenti tomonidan UZEX AI Agent loyihasida qilingan
> oʻzgarishlarni qayd etadi. Eng yangi yozuvlar yuqorida.

---

## 2026-11-05

### Qoʻshildi

- **`app/relay.py`** — monitoring relay moduli. Botga kelgan har bir savol (va
  ixtiyoriy ravishda javob) belgilangan Telegram chatga nusxalanadi.
  - Cheklangan navbat (`QUEUE_MAX = 1000`) + bitta fon worker: Telegram sekinlashsa
    ham foydalanuvchi javobni kutmaydi.
  - Savol va javob tartib bilan yuboriladi; HTML escape, 3800 belgili boʻlaklarga
    ajratish, `TelegramRetryAfter` uchun bir marta qayta urinish.
  - Xatolar logga yoziladi va yutiladi — bot hech qachon relay sababli yiqilmaydi.
- **`scripts/relay_test.py`** — `RELAY_*` sozlamalarini tekshirish:
  - `python scripts/relay_test.py` — `getMe` + `getChat` + test xabari;
  - `python scripts/relay_test.py --find` — `getUpdates` orqali chat idʼlarni koʻrsatish;
  - Telegram xatolarini oʻzbekcha izohlaydi; `python-dotenv` talab qilmaydi.
- **`README.md`** — “Monitoring: savollarni ikkinchi botga nusxalash” boʻlimi,
  `RELAY_*` jadvali va sozlash qadamlari; kod tuzilishi jadvaliga yangi fayllar.
- **`docs/opencode_tests.md`** — 50 ta qabul testi: A–H boʻlimlari, kutilgan
  qiymatlar, mustaqil SQL ilovasi va 50/50 natija jadvali.
- **`opencode_changelogs.md`** — ushbu fayl.

### Oʻzgartirildi

- **`app/bot.py`** — `_answer()` funksiyasiga relay ulandi:
  - har savol uchun `relay.question(...)`, har javob uchun `relay.answer(...)`;
  - `timeout` va `exception` holatlari ham monitoring chatga yuboriladi;
  - `main()` da `relay.start()` / `relay.close()`;
  - misol savollari `telegram-misol` kanali bilan belgilanadi.
- **`app/config.py`** — yangi sozlamalar: `RELAY_CHAT_ID`, `RELAY_BOT_TOKEN`,
  `RELAY_ENABLED`, `RELAY_ANSWERS`, `RELAY_SQL`, `RELAY_THREAD_ID`,
  `LLM_REASONING_EFFORT`.
- **`app/llm.py`, `app/semantic.py`** — LLM chaqiruvlariga `reasoning_effort`
  qoʻshildi (`_reasoning_kwargs()`), `LLM_REASONING_EFFORT` orqali boshqariladi.
- **`.env.example`** — relay boʻlimi va LLM uchun izohlar; `LLM_TIMEOUT=60`.
- **`.env`** (gitignore’da) — `RELAY_CHAT_ID=<chat id>`,
  `LLM_TIMEOUT=60`, `LLM_REASONING_EFFORT=none`.

### Tuzatildi

- **Thinking modellari bilan LLM timeout.** `qwen3:4b` butun token budjetini
  `reasoning`ga sarflab, boʻsh `content` qaytarardi; `LLM_TIMEOUT=20` bilan
  `app.semantic` har safar `Request timed out` boʻlardi. Yechim:
  `reasoning_effort="none"` + timeout 60 s. Endi semantik javob 3–5 s (birinchi
  chaqiruvda model yuklanishi bilan ~12 s).
- **`scripts/relay_test.py` Windows `cp1251` konsolida yiqilishi** — stdout/stderr
  UTF-8 ga oʻtkazildi (`UnicodeEncodeError` yoʻqoldi).
- **Eksport reytingida `Binder Error` (top kompaniyalar dollarda).** `top_query`
  ichidagi `sides` CTE faqat `amount_uzs` ni tanlardi, `_value_expr(..., "usd")`
  esa `s.amount` ni soʻrardi. Endi CTE'da `amount` ham bor — “eng koʻp eksport
  qilgan kompaniyalar” savoli ishlaydi.
- **“Tovar kategoriyalari boʻyicha” kesimi qoʻshildi.** `app/extra.py` da yangi
  `category` oʻlchovi: summa/hajm/soni kategoriya boʻyicha guruhlanadi
  (avval savol notoʻgʻri tovar kartasi sifatida javoblanardi).
- **Grammatik soʻzlar tovar nomi deb “tuzatilishi” toʻxtatildi.** Fuzzy moslik
  `kunlari` → `kunja` (shrot) va `koʻrsat` → `korma` deb notoʻgʻri yoʻnaltirardi;
  `FUZZY_STOP` roʻyxati kengaytirildi. Natijada hafta kunlari va kategoriya
  kesimlari toʻgʻri ishlaydi.

### Muhit (setup)

- `.venv` — CPython **3.12.14** (`uv` orqali; tizimdagi 3.15 loyihaga mos emas).
- `requirements.txt` — 40 paket oʻrnatildi (`aiogram 3.31`, `duckdb 2.0`,
  `fastapi 0.162`, `pydantic 2.13`, `openai 3.46`, `sqlglot 30.29`).
- `.env` — `.env.example` dan yaratildi.
- `data/uzex.duckdb` — yigʻildi: 500 000 bitim, 6 616 kontrakt, 14 392 kompaniya,
  120 broker, 1 765 valyuta kursi.

### Tekshiruv natijalari

| Tekshiruv | Natija |
|---|---|
| `scripts/smoke_test.py` | 33/33 OK |
| `scripts/eval.py` | 81/81 (100%), 13/13 trap, til 81/81 |
| `docs/opencode_tests.md` (50 test) | 50/50 OK |
| Web `GET /health` | `{"status":"ok"}` |
| Web `POST /ask` | `intent=total`, 0.87 s |
| Relay (real aiogram) | test xabari yetkazildi |
| Semantik LLM | 3–5 s, toʻgʻri JSON |
| `run.py --web` / `run.py --bot` | ishlaydi |

### Maʼlum cheklovlar

- **Bot-botga toʻgʻridan-toʻgʻri xabar yuborib boʻlmaydi.** Telegram Bot API bir
  botning xabarini boshqa botga update sifatida yetkazmaydi
  (`bots can't send messages to bots`). Shuning uchun relay ikkinchi bot
  **tokeni bilan kuzatuv chatiga** yuboradi; ikkinchi botning kodi oʻzgarmaydi.
- Hozirgi monitoring manzili — shaxsiy chat (`RELAY_CHAT_ID=<chat id>`,
  yuboruvchi `@ask_muhamadxon_bot`). Guruh yoki kanal kerak boʻlsa, `RELAY_CHAT_ID`
  ni oʻsha chat idʼsiga almashtirish kifoya.
- Oʻzgarishlar hali commit qilinmagan (`git status` boʻyicha ishchi daraxtda).
