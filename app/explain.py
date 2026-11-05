"""Human-readable "how was this computed" line shown inside every answer.

Written in legacy Uzbek Latin / Russian; the script converter adapts Uzbek text to the
script of the question (new Latin or Cyrillic) afterwards.
"""

from __future__ import annotations

UZ_METRIC = {
    "amount": "bitimlar summasi yig‘indisi (so‘mda; dollar bitimlari har bitim sanasidagi kurs bo‘yicha so‘mga o‘girilgan)",
    "usd": "eksport bitimlarining dollardagi summasi yig‘indisi; so‘m ekvivalenti har bitim sanasidagi kurs bo‘yicha",
    "count": "bitimlar soni",
    "volume": "hajm = miqdor (lotlar) × lotdagi birlik, o‘lchov birligi bo‘yicha alohida yig‘indi",
    "avg_price": "birlik narxi = summa ÷ (miqdor × lot); bitimlar bo‘yicha o‘rtacha, min va max",
}
RU_METRIC = {
    "amount": "сумма сделок (в сумах; долларовые сделки пересчитаны по курсу на дату каждой сделки)",
    "usd": "сумма экспортных сделок в долларах; эквивалент в сумах — по курсу на дату каждой сделки",
    "count": "количество сделок",
    "volume": "объём = количество (лотов) × единиц в лоте, суммируется отдельно по единицам измерения",
    "avg_price": "цена за единицу = сумма ÷ (количество × лот); среднее, min и max по сделкам",
}
UZ_GROUP = {"company": "kompaniyalar (INN)", "product": "tovarlar (TN VED kodi)", "region": "viloyatlar", "broker": "brokerlar"}
RU_GROUP = {"company": "компаниям (ИНН)", "product": "товарам (код ТН ВЭД)", "region": "регионам", "broker": "брокерам"}


def explain(result, p) -> str:
    uz = p.lang == "uz"
    intent = result.intent
    metric = p.metric if p.metric in UZ_METRIC else "amount"
    m = (UZ_METRIC if uz else RU_METRIC)[metric]
    group = (UZ_GROUP if uz else RU_GROUP).get(p.group or "company", "")

    if intent in {"total", "region_stats"}:
        text = m
    elif intent == "export_stats":
        text = (UZ_METRIC if uz else RU_METRIC)["usd"]
    elif intent == "top":
        asc = bool(getattr(p, "order_asc", False))
        order_uz, order_ru = ("o‘sish", "возрастанию") if asc else ("kamayish", "убыванию")
        tie_uz = "; teng qiymatlarda INN bo‘yicha tartiblandi" if asc else ""
        tie_ru = "; при равных значениях — по ИНН" if asc else ""
        text = (f"bitimlar {group} bo‘yicha guruhlandi va «{m}» bo‘yicha {order_uz} tartibida saralandi{tie_uz}"
                if uz else f"сделки сгруппированы по {group} и отсортированы по {order_ru} показателя «{m}»{tie_ru}")
    elif intent == "company_profile":
        text = ("kompaniya sotuvchi yoki xaridor bo‘lgan bitimlar INN bo‘yicha tanlandi; soni, summasi va asosiy tovarlari hisoblandi"
                if uz else "выбраны сделки, где компания (по ИНН) — продавец или покупатель; посчитаны количество, сумма и основные товары")
    elif intent == "product_stats":
        text = ("tovar TN VED kodi bo‘yicha aniqlandi (bir xil tovar turli yozilgan bo‘lsa ham); summa, hajm, birlik narxi va sotuvchilar hisoblandi"
                if uz else "товар определён по коду ТН ВЭД (даже если записан по-разному); посчитаны сумма, объём, цена за единицу и продавцы")
    elif intent in {"contract_info", "deal_info"}:
        text = ("reyestrdagi yozuv o‘zgarishsiz ko‘rsatildi; birlik narxi = summa ÷ (miqdor × lot)"
                if uz else "показана запись реестра без изменений; цена за единицу = сумма ÷ (количество × лот)")
    elif intent in {"status_stats", "status_share"}:
        text = ("bitimlar guruhlandi; ulush = guruhdagi bitimlar ÷ jami bitimlar × 100"
                if uz else "сделки сгруппированы; доля = сделки группы ÷ все сделки × 100")
    elif intent == "broker_stats":
        text = ("broker sotuvchi yoki xaridor tomonida qatnashgan bitimlar (har bitim bir marta) hisoblandi"
                if uz else "учтены сделки, где брокер на стороне продавца или покупателя (каждая сделка один раз)")
    elif intent == "list_deals":
        text = "filtrga mos oxirgi bitimlar sana bo‘yicha saralandi" if uz else "последние сделки по фильтру, отсортированы по дате"
    elif intent == "usd_rate":
        text = ("kunlik rasmiy kurs (1 USD uchun so‘m); sanada kurs bo‘lmasa — undan oldingi oxirgi kurs"
                if uz else "дневной курс из таблицы курсов (сум за 1 USD); если на дату курса нет — последний предыдущий")
    elif intent == "extreme_deal":
        kind = (result.meta or {}).get("kind")
        if kind in {"max", "min"}:
            text = ("bitimlar so‘mdagi summa bo‘yicha saralanib, birinchisi olindi (bekor qilinganlarsiz)"
                    if uz else "сделки отсортированы по сумме в сумах, взята первая (без аннулированных)")
        else:
            text = ("bitimlar sana va vaqt bo‘yicha saralanib, birinchisi olindi"
                    if uz else "сделки отсортированы по дате и времени, взята первая")
    elif intent == "analysis":
        text = ("ma’lumotlar oylar bo‘yicha jamlandi; boshlang‘ich/oxirgi qiymat, min/max, o‘rtacha, tebranish, yillar bo‘yicha o‘zgarish va "
                "chiziqli trend (regressiya qiyaligi, R²) SQL’da hisoblandi"
                if uz else "данные агрегированы по месяцам; начало/конец, min/max, среднее, колеблемость, изменения по годам и "
                "линейный тренд (наклон регрессии, R²) вычислены в SQL")
    elif intent == "forecast":
        text = ("so‘nggi 12 oylik qiymatlarga chiziqli regressiya (y = a + b·oy) moslandi va keyingi oylarga davom ettirildi; "
                "95% oraliq = ±1.96 × qoldiqlar standart og‘ishi. Bu taxmin, haqiqiy ma’lumot emas"
                if uz else "по последним 12 месяцам построена линейная регрессия (y = a + b·месяц) и продолжена вперёд; "
                "95% интервал = ±1.96 × стандартное отклонение остатков. Это оценка, а не фактические данные")
    elif intent == "breakdown":
        text = ("bitimlar tanlangan kesim bo‘yicha guruhlandi va ko‘rsatkich har guruh uchun SQL'da hisoblandi; ulush = guruh ÷ jami × 100"
                if uz else "сделки сгруппированы по выбранному срезу, показатель посчитан в SQL для каждой группы; доля = группа ÷ итого × 100")
    elif intent == "delivery":
        text = ("«Поставлено» ustuni bo‘yicha: yetkazilmagan = sotilgan lotlar − yetkazilgan lotlar (to‘langan va ijro etilgan bitimlar)"
                if uz else "по полю «Поставлено»: недопоставлено = куплено лотов − поставлено лотов (оплаченные и исполненные сделки)")
    elif intent == "overview":
        text = ("aylanma = bekor qilinmagan bitimlarning so‘mdagi summasi (USD bitimlari bitim kunidagi rasmiy kurs bo‘yicha o‘girilgan); "
                "hududlar — sotuvchi ombori viloyati; faol kompaniya — sotuvchi yoki xaridor sifatida qatnashgan bitimlar soni"
                if uz else "оборот = сумма неаннулированных сделок в сумах (сделки в USD пересчитаны по официальному курсу на дату сделки); "
                "регион — склад продавца; активность компании — число сделок как продавца или покупателя")
    elif intent == "deal_summary":
        text = ("bitimlar soni (barcha holatlar), umumiy summa va o‘rtacha summa (bekor qilinganlarsiz): o‘rtacha = umumiy summa ÷ bekor qilinmagan bitimlar soni"
                if uz else "количество сделок (все статусы), общая и средняя сумма (без аннулированных): средняя = общая сумма ÷ число неаннулированных сделок")
    elif intent == "avg_deal":
        text = ("bitimlar so‘mdagi summasining o‘rtachasi va medianasi (bekor qilinganlarsiz)"
                if uz else "среднее и медиана суммы сделки в сумах (без аннулированных)")
    elif intent == "contracts_count":
        text = ("kontrakt kartochkalari ro‘yxatdan o‘tgan sanasi bo‘yicha sanaldi"
                if uz else "карточки контрактов подсчитаны по дате регистрации")
    elif intent == "distinct_parties":
        text = ("noyob INNlar soni sanaldi (bir kompaniya bir marta)"
                if uz else "подсчитано число уникальных ИНН (каждая компания один раз)")
    elif intent == "compare_periods":
        text = ("bitimlar davr bo‘yicha guruhlandi; o‘zgarish % = (joriy − oldingi) ÷ oldingi × 100"
                if uz else "сделки сгруппированы по периодам; изменение % = (текущий − предыдущий) ÷ предыдущий × 100")
    elif intent == "generic":
        text = ("savol bo‘yicha SQL so‘rov tuzildi, tekshirildi (faqat o‘qish) va natijasi o‘zgarishsiz ko‘rsatildi"
                if uz else "по вопросу составлен SQL-запрос, проверен (только чтение), результат показан без изменений")
    else:
        text = m
    source = "manba — birja bitimlari reyestri" if uz else "источник — реестр биржевых сделок"
    if intent == "usd_rate":
        source = "manba — USD kurslari jadvali" if uz else "источник — таблица курсов USD"
    label = "🔎 Qanday hisoblandi" if uz else "🔎 Как посчитано"
    return f"{label}: {text}; {source}."
