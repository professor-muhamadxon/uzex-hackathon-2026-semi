# UZEX AI Agent

UZEX birja bitimlari (2022–2026, 500 000 ta yozuv) bo‘yicha o‘zbek va rus tillarida
savollarga javob beradigan lokal AI-agent. Javoblar **faqat ma’lumotlar bazasidan**
olinadi: har bir raqam DuckDB’da hisoblanadi, LLM esa faqat savolni SQL’ga aylantiradi.
Ma’lumot topilmasa, agent ochiqchasiga “topilmadi” / “не найдено” deb javob beradi.

Interfeyslar: **Telegram bot**, **CLI**, **FastAPI**.

---

## Tez boshlash (macOS / Linux)

Talab: Python 3.12+ (3.13/3.15 emas, chunki ba’zi kutubxonalar hali mos emas).

```bash
cd UzExHackaton

# 1. Virtual muhit
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. CSV -> DuckDB (bir marta, ~1–2 daqiqa)
python scripts/build_db.py

# 3. Terminalda savol berish
python -m app.cli "2025-yilda jami savdo summasi qancha?"
python -m app.cli --debug "Eng ko‘p paxta sotgan 5 kompaniya"
python -m app.cli            # interaktiv rejim
```

`scripts/build_db.py` `data/uzex_spot_data/` dagi CSV’lardan `data/uzex.duckdb`
faylini yaratadi (500 000 bitim, 6 616 kontrakt, 14 392 kompaniya, 120 broker).

### Smoke test

```bash
.venv/bin/python scripts/smoke_test.py
```

33 ta o‘zbekcha va ruscha savol tekshiriladi (jadval, top, region, eksport,
kontrakt, bitim, broker, kompaniya, “topilmadi” holatlari).

---

## Telegram bot

1. [@BotFather](https://t.me/BotFather) orqali bot yarating va tokenni oling.
2. `.env` faylini to‘ldiring:

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
```

3. Botni ishga tushiring:

```bash
.venv/bin/python -m app.bot
```

Bot polling rejimida ishlaydi — public IP, domen yoki HTTPS shart emas.
Kompyuter yoniq turganda bot javob beradi.

---

## FastAPI

```bash
.venv/bin/uvicorn app.api:app --host 0.0.0.0 --port 8000
```

```bash
curl -s http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"2025-yilda qancha paxta sotilgan?"}'
```

Health check: `GET /health`.

---

## Arxitektura

```
Savol
  -> til aniqlash (uz / ru)
  -> qoidaviy parser: intent, davr, tovar, region, kompaniya, broker, kontrakt
  -> tayyor SQL shablon (asosiy yo‘l)
       -> DuckDB (aniq SUM / COUNT / GROUP BY / valyuta konvertatsiyasi)
  -> agar intent noma’lum bo‘lsa: LLM NL->SQL (ixtiyoriy)
       -> sqlglot validatsiya -> faqat SELECT -> bajarish -> xato bo‘lsa 1 marta repair
  -> deterministik javob shabloni (o‘zbekcha / ruscha)
  -> manba: bitim va kontrakt raqamlari
```

Muhim qoidalar:

- **LLM arifmetika qilmaydi.** Barcha raqamlar DuckDB’dan.
- **Har bir savol uchun 90 soniya limit.** Shablon SQL millisekundlarda ishlaydi.
- **Hallucination’ga qarshi:** javobda faqat SQL natijasidagi qiymatlar; natija bo‘sh
  bo‘lsa — “topilmadi”.
- **Valyuta:** eksport bitimlari USD’da; `amount_uzs` bitim sanasidagi kurs bilan
  hisoblangan. Jami so‘m summasi va USD summasi alohida ko‘rsatiladi.
- **Hajm:** `volume = quantity * lot`; turli o‘lchov birliklari bo‘yicha alohida
  guruhlanadi (kg, tonna, dona, ...).

### Kod tuzilishi

| Fayl | Vazifa |
|---|---|
| `app/etl.py` | CSV -> DuckDB, `deals_enriched`, `contracts_full`, indekslar |
| `app/parser.py` | til, intent, davr, holat, tovar, region, kompaniya, broker |
| `app/catalog.py` | tovar sinonimlari, region aliaslari, fuzzy kompaniya/broker |
| `app/sql.py` | tayyor SQL shablonlar va `QueryResult` |
| `app/validator.py` | LLM SQL’ini tekshirish (SELECT-only, oq ro‘yxat) |
| `app/llm.py` | OpenAI-mos NL->SQL (Ollama yoki cloud) |
| `app/formatter.py` | ikki tilli javob shabloni, raqam/valyuta formatlash |
| `app/agent.py` | orkestratsiya: shablon -> LLM fallback -> javob |
| `app/cli.py` | terminal interfeysi |
| `app/api.py` | FastAPI `/ask`, `/health` |
| `app/bot.py` | aiogram 3 Telegram bot (polling) |
| `scripts/build_db.py` | bazani yig‘ish |
| `scripts/smoke_test.py` | 33 ta end-to-end test |

### Ma’lumotlar sxemasi (asosiy)

`deals_enriched`: `deal_id`, `deal_date`, `amount`, `amount_uzs`, `volume`,
`unit_price`, `currency`, `status`, `contract_type`, `contract_form`,
`trade_type`, `region_uz`, `tnved_code`, `category`, `seller_inn`, `buyer_inn`,
`seller_broker`, `buyer_broker`, `contract_id`, `unit`, `lot`.

`contracts_full`, `participants`, `brokers`, `usd_rates`, `region_map` — yordamchi
jadvalalar.

---

## LLM fallback (ixtiyoriy)

Dastlab LLM o‘chirilgan holda ham barcha asosiy savollar ishlaydi. Noma’lum
savollarni qoplash uchun `.env`da OpenAI-mos endpoint sozlang:

```env
LLM_ENABLED=1
LLM_BASE_URL=http://localhost:11434/v1   # Ollama
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5-coder:7b
LLM_TIMEOUT=45
```

Cloud misoli:

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

LLM javob bersa ham, SQL validatsiyadan o‘tmaguncha bajarilmaydi. LLM ishlamasa
yoki noto‘g‘ri SQL qaytarsa, agent “aniqlashtiring” deb javob beradi — hech qachon
o‘ylab topilgan raqam bermaydi.

---

## Hosting (keyingi bosqich)

Eng oddiy variant — VPS’da `systemd` + polling:

```ini
# /etc/systemd/system/uzex-bot.service
[Unit]
Description=UZEX Telegram bot
After=network.target

[Service]
WorkingDirectory=/opt/uzex
ExecStart=/opt/uzex/.venv/bin/python -m app.bot
Restart=always
EnvironmentFile=/opt/uzex/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now uzex-bot
```

Docker bilan ham mumkin: `Dockerfile` va `docker-compose.yml` tayyor.

```bash
cp .env.example .env      # tokenni yozing
docker compose up -d --build
docker compose logs -f
```

Image ichida `python scripts/build_db.py` avtomatik bajariladi. Bot polling
rejimida ishlagani uchun ingress/HTTPS talab qilinmaydi; FastAPI kerak bo‘lsa,
`docker-compose.yml`dagi `command` va `ports` qatorlarini ochib qo‘ying.

---

## Cheklovlar

- Ma’lumotlar 30.10.2026 holatiga ko‘ra; keyingi yangilanishlar CSV’larni
  almashtirib, `python scripts/build_db.py`ni qayta ishga tushirish orqali.
- Murakkab, bir necha shartli savollar LLM fallback’siz “topilmadi” bo‘lishi mumkin.
- Kompaniya nomlari kirill/lotin aralash; fuzzy matching ishlatiladi, lekin juda
  qisqa yoki umumiy nomlarda INN bilan aniqlashtirish tavsiya etiladi.
- Telegram tokeni `.env`da saqlanadi va repoga qo‘shilmaydi.

## Quick start (`run.sh` / `run.py`)

```bash
./run.sh              # venv + deps + DB (first run), then web (http://localhost:8000) + Telegram bot
./run.sh --web        # only the web app
./run.sh --bot        # only the bot (needs TELEGRAM_BOT_TOKEN in .env)
./run.sh --port 9000  # another web port
./run.sh --check      # smoke tests + eval
./run.sh --bg         # background (nohup); stop with ./run.sh --stop
```

`run.py` restarts a crashed web app or bot automatically and refuses to start a second bot
instance (Telegram allows only one poller per token). Logs: `logs/web.out`, `logs/bot.out`,
`logs/qa.jsonl`.
