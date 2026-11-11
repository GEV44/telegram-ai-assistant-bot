"""User-facing strings in English, Russian and Armenian."""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Hi! I'm the virtual assistant of {business}. Ask me anything about us, or use /book to make an appointment.",
        "help": "I can answer questions, book an appointment (/book), take your contact for a call back (/lead) or call a human (/human). /cancel stops the current dialog.",
        "ask_service": "Which service would you like?",
        "bad_service": "Please pick one of the services from the list.",
        "ask_date": "Choose a date:",
        "bad_date": "That date is not available. Please pick one of the suggested dates.",
        "no_dates": "Sorry, there are no free dates in the coming days. Use /human and we will find a time for you.",
        "ask_time": "Free times on {date}:",
        "bad_time": "That time is not free. Please pick one of the suggested times.",
        "no_slots": "That day just filled up. Please choose another date.",
        "ask_name": "What is your name?",
        "bad_name": "Please enter your name (at least 2 letters).",
        "ask_phone": "Your phone number, so we can confirm the visit?",
        "bad_phone": "That doesn't look like a phone number. Example: +374 77 123456",
        "confirm_summary": "Please confirm:\n{service}\n{date} at {time}\n{name}, {phone}",
        "confirm_yes": "Confirm",
        "confirm_no": "Cancel",
        "booked": "Done! You are booked: {service}, {date} at {time}. See you at {business}!",
        "slot_taken": "Sorry, that time was just taken. Please choose another one.",
        "cancelled": "Okay, cancelled. Ask me anything or type /book any time.",
        "lead_saved": "Thank you, {name}! We will contact you shortly.",
        "handoff_ok": "I have passed your request to a human. They will reply here as soon as possible.",
        "rate_limited": "You are writing too fast. Please wait a minute and try again.",
        "no_answer": "I don't have a reliable answer to that. I can connect you with a human (/human) or leave your contact for a call back (/lead).",
        "services_title": "Our services:",
        "hours_text": "Working hours: {open} - {close}, {days}.",
        "days": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "not_admin": "This command is for the owner only.",
        "export_empty": "Nothing to export yet.",
    },
    "ru": {
        "welcome": "Здравствуйте! Я виртуальный помощник {business}. Спросите меня о чём угодно или нажмите /book, чтобы записаться.",
        "help": "Я отвечаю на вопросы, записываю на приём (/book), принимаю контакты для обратного звонка (/lead) и зову человека (/human). /cancel прерывает диалог.",
        "ask_service": "Какая услуга вас интересует?",
        "bad_service": "Выберите, пожалуйста, услугу из списка.",
        "ask_date": "Выберите дату:",
        "bad_date": "Эта дата недоступна. Выберите одну из предложенных.",
        "no_dates": "К сожалению, в ближайшие дни нет свободных дат. Нажмите /human, и мы подберём время.",
        "ask_time": "Свободное время на {date}:",
        "bad_time": "Это время занято. Выберите одно из предложенных.",
        "no_slots": "На этот день места только что закончились. Выберите другую дату.",
        "ask_name": "Как вас зовут?",
        "bad_name": "Введите имя (минимум 2 буквы).",
        "ask_phone": "Ваш номер телефона для подтверждения визита?",
        "bad_phone": "Это не похоже на номер телефона. Пример: +374 77 123456",
        "confirm_summary": "Подтвердите, пожалуйста:\n{service}\n{date} в {time}\n{name}, {phone}",
        "confirm_yes": "Подтвердить",
        "confirm_no": "Отмена",
        "booked": "Готово! Вы записаны: {service}, {date} в {time}. Ждём вас в {business}!",
        "slot_taken": "Это время только что заняли. Выберите другое.",
        "cancelled": "Хорошо, отменено. Задайте вопрос или напишите /book в любой момент.",
        "lead_saved": "Спасибо, {name}! Мы скоро с вами свяжемся.",
        "handoff_ok": "Я передал ваш запрос человеку. Он ответит здесь как можно скорее.",
        "rate_limited": "Вы пишете слишком быстро. Подождите минуту и попробуйте снова.",
        "no_answer": "У меня нет надёжного ответа на этот вопрос. Могу позвать человека (/human) или записать ваш контакт для звонка (/lead).",
        "services_title": "Наши услуги:",
        "hours_text": "Часы работы: {open} - {close}, {days}.",
        "days": "пн,вт,ср,чт,пт,сб,вс",
        "not_admin": "Эта команда только для владельца.",
        "export_empty": "Пока нечего экспортировать.",
    },
    "hy": {
        "welcome": "Բարև ձեզ։ Ես {business}-ի վիրտուալ օգնականն եմ։ Հարցրեք ինչ ուզում եք կամ սեղմեք /book՝ գրանցվելու համար։",
        "help": "Ես պատասխանում եմ հարցերին, գրանցում եմ այցի (/book), ընդունում եմ կոնտակտ հետ զանգի համար (/lead) և կանչում եմ մարդու (/human)։ /cancel-ը դադարեցնում է զրույցը։",
        "ask_service": "Ո՞ր ծառայությունն է ձեզ հետաքրքրում։",
        "bad_service": "Խնդրում ենք ընտրել ծառայություն ցուցակից։",
        "ask_date": "Ընտրեք ամսաթիվը՝",
        "bad_date": "Այս ամսաթիվը հասանելի չէ։ Ընտրեք առաջարկվածներից։",
        "no_dates": "Ցավոք, առաջիկա օրերին ազատ ամսաթվեր չկան։ Սեղմեք /human, և մենք ժամ կընտրենք։",
        "ask_time": "Ազատ ժամերը {date}-ին՝",
        "bad_time": "Այս ժամը զբաղված է։ Ընտրեք առաջարկվածներից։",
        "no_slots": "Այդ օրվա տեղերը նոր ավարտվեցին։ Ընտրեք այլ ամսաթիվ։",
        "ask_name": "Ինչպե՞ս եք կոչվում։",
        "bad_name": "Մուտքագրեք անունը (առնվազն 2 տառ)։",
        "ask_phone": "Ձեր հեռախոսահամարը՝ այցը հաստատելու համար։",
        "bad_phone": "Սա հեռախոսահամարի չի նման։ Օրինակ՝ +374 77 123456",
        "confirm_summary": "Խնդրում ենք հաստատել՝\n{service}\n{date}, {time}\n{name}, {phone}",
        "confirm_yes": "Հաստատել",
        "confirm_no": "Չեղարկել",
        "booked": "Պատրաստ է։ Դուք գրանցված եք՝ {service}, {date}, {time}։ Սպասում ենք ձեզ՝ {business}։",
        "slot_taken": "Այս ժամը նոր զբաղեցրին։ Ընտրեք մեկ այլ ժամ։",
        "cancelled": "Լավ, չեղարկված է։ Հարցրեք կամ գրեք /book ցանկացած պահի։",
        "lead_saved": "Շնորհակալություն, {name}։ Մենք շուտով կկապվենք ձեզ հետ։",
        "handoff_ok": "Ես ձեր հարցումը փոխանցեցի մարդու։ Նա կպատասխանի այստեղ հնարավորինս շուտ։",
        "rate_limited": "Դուք չափազանց արագ եք գրում։ Սպասեք մեկ րոպե և կրկին փորձեք։",
        "no_answer": "Այս հարցի համար վստահելի պատասխան չունեմ։ Կարող եմ կանչել մարդու (/human) կամ գրանցել ձեր կոնտակտը (/lead)։",
        "services_title": "Մեր ծառայությունները՝",
        "hours_text": "Աշխատանքային ժամեր՝ {open} - {close}, {days}։",
        "days": "երկ,երք,չրք,հնգ,ուրբ,շբթ,կիր",
        "not_admin": "Այս հրամանը միայն սեփականատիրոջ համար է։",
        "export_empty": "Դեռ արտահանելու բան չկա։",
    },
}

_YES = {"yes", "y", "ok", "okay", "confirm", "да", "ок", "подтверждаю", "այո", "հաստատում եմ"}
_NO = {"no", "n", "cancel", "нет", "отмена", "ոչ", "չեղարկել"}


def t(lang: str, key: str, **kwargs: Any) -> str:
    """Translate ``key``; unknown languages fall back to English."""
    table = MESSAGES.get(lang, MESSAGES["en"])
    template = table.get(key) or MESSAGES["en"][key]
    return template.format(**kwargs) if kwargs else template


def is_yes(text: str) -> bool:
    low = text.strip().lower().rstrip("!.")
    return low in _YES or low in {m["confirm_yes"].lower() for m in MESSAGES.values()}


def is_no(text: str) -> bool:
    low = text.strip().lower().rstrip("!.")
    return low in _NO or low in {m["confirm_no"].lower() for m in MESSAGES.values()}
