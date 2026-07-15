import os
import json
import re
import random
import aiohttp
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import dateparser

# ================= НАСТРОЙКИ =================
TOKEN = os.environ.get('TOKEN', '8951461242:AAFYgVpzrJwkTuyazSP5_M1oz0zcl4pxGAw')
DATA_FILE = "prono_data.json"
WEATHER_CITY = "Samara"  # Измените на ваш город

# ================= ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ =================
planner_data = []
next_id = 1
users_data = {}

# ================= ЛИЧНОСТЬ PRONO =================
CONVERSATIONAL_RESPONSES = {
    "привет": ["Привет! Я Prono. Готов организовать твое будущее! Как настроение? 😊", "Здравствуй! Рад тебя видеть. Что запланируем?", "Привет-привет! Я уже настроил свои внутренние часы. Чем могу помочь?"],
    "как дела": ["Мои схемы работают идеально! А у тебя как?", "Отлично! Освободил 5 минут в твоем расписании, чтобы спросить: как ты?", "Всегда в боевой готовности!"],
    "устал": ["Понимаю. Давай добавлю в расписание '15 минут на отдых'? Ты это заслужил(а)! ", "Не забывай, что даже самым эффективным людям нужен перерыв. Выпей воды!", "Записываю в черновик: 'Отдых'. Заботься о себе!"],
    "спасибо": ["Всегда пожалуйста! Я здесь, чтобы твоя жизнь была в порядке. ✨", "Рад стараться! Обращайся в любое время.", "Для меня это честь! Твое время — мой приоритет."],
    "шутк": ["Почему планировщик не ходит на свидания? Потому что у него всё расписано! 😄", "Знаешь, в чем разница между мной и будильником? Я не даю тебе по мне ударить.", "Мой любимый цвет — цвет успешно выполненного списка задач! 🟩"],
    "грустно": ["Мне жаль это слышать. Помни: после самого загруженного дня всегда наступает спокойная ночь. Я рядом! 🤗", "Хочешь, я найду в твоем расписании окно для чего-то приятного?"],
    "скучно": ["Может, самое время добавить что-то интересное в расписание? Кино, прогулка, хобби?", "Скука — это знак, что пора сделать что-то новое! Что давно откладывал(а)?"]
}

def get_conversational_reply(text):
    text_lower = text.lower()
    for keyword, responses in CONVERSATIONAL_RESPONSES.items():
        if keyword in text_lower:
            return random.choice(responses)
    return None

def get_greeting_by_time():
    hour = datetime.now().hour
    if 6 <= hour < 12:
        return "Доброе утро! ☀️"
    elif 12 <= hour < 18:
        return "Добрый день! ☕"
    elif 18 <= hour < 23:
        return "Добрый вечер! 🌆"
    else:
        return "Доброй ночи! 🌙"

# ================= РАБОТА С ФАЙЛАМИ =================
def load_data():
    global planner_data, next_id, users_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            planner_data = data.get('items', [])
            next_id = data.get('next_id', 1)
            users_data = data.get('users', {})
    else:
        planner_data, users_data = [], {}

def save_data():
    data = {
        'items': planner_data, 'next_id': next_id,
        'users': users_data
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================= ПАРСЕР ЗАДАЧ =================
def parse_user_input(text):
    result = {'date': None, 'time_start': None, 'time_end': None, 'task_text': text, 'priority': 'normal', 'category': None}
    
    if any(word in text.lower() for word in ['важно', 'срочно', '🔥', '!']):
        result['priority'] = 'high'
    
    category_match = re.search(r'#(\w+)', text)
    if category_match:
        result['category'] = category_match.group(1)
    
    time_pattern = r'в\s*(\d{1,2}:\d{2})'
    time_match = re.search(time_pattern, text)
    if not time_match:
        time_pattern = r'(\d{1,2}:\d{2})'
        time_match = re.search(time_pattern, text)
    
    if time_match:
        result['time_start'] = time_match.group(1)
        text = text.replace(time_match.group(0), '', 1).strip()
        time_pattern2 = r'(?:до|по|-)\s*(\d{1,2}:\d{2})'
        time_match2 = re.search(time_pattern2, text)
        if time_match2:
            result['time_end'] = time_match2.group(1)
            text = text.replace(time_match2.group(0), '', 1).strip()

    date_keywords = ['сегодня', 'завтра', 'послезавтра', 'в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу', 'в субботу', 'в воскресенье']
    date_found = False
    for keyword in date_keywords:
        if keyword in text.lower():
            parsed_date = dateparser.parse(keyword, languages=['ru'])
            if parsed_date:
                result['date'] = parsed_date.strftime('%Y-%m-%d')
                text = re.sub(keyword, '', text, flags=re.IGNORECASE).strip()
                date_found = True
                break
    
    if not date_found:
        date_pattern = r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)'
        date_match = re.search(date_pattern, text, re.IGNORECASE)
        if date_match:
            parsed_date = dateparser.parse(date_match.group(0), languages=['ru'])
            if parsed_date:
                result['date'] = parsed_date.strftime('%Y-%m-%d')
                text = text.replace(date_match.group(0), '', 1).strip()
                date_found = True
        
        if not date_found:
            date_pattern2 = r'(\d{1,2})\.(\d{1,2})'
            date_match2 = re.search(date_pattern2, text)
            if date_match2:
                day, month = int(date_match2.group(1)), int(date_match2.group(2))
                if 1 <= day <= 31 and 1 <= month <= 12:
                    result['date'] = f"2026-{month:02d}-{day:02d}"
                    text = text.replace(date_match2.group(0), '', 1).strip()

    text = re.sub(r'#\w+', '', text).strip()
    text = re.sub(r'^\s*(на|в|во)\s+', '', text, flags=re.IGNORECASE).strip()
    result['task_text'] = text
    return result

# ================= ПОГОДА =================
async def get_weather(city="Moscow"):
    """Получает погоду с wttr.in (бесплатно, без API ключа)"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://wttr.in/{city}?format=j1"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    current = data['current_condition'][0]
                    temp = current['temp_C']
                    desc = current['lang_ru'][0]['value'] if 'lang_ru' in current else current['weatherDesc'][0]['value']
                    humidity = current['humidity']
                    wind = current['windspeedKmph']
                    
                    today_forecast = data['weather'][0]
                    max_temp = today_forecast['maxtempC']
                    min_temp = today_forecast['mintempC']
                    
                    return {
                        'temp': temp,
                        'desc': desc,
                        'humidity': humidity,
                        'wind': wind,
                        'max_temp': max_temp,
                        'min_temp': min_temp
                    }
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        return None

def get_weather_advice(weather, tasks):
    """Генерирует советы на основе погоды и задач"""
    if not weather:
        return ""
    
    advice = []
    temp = int(weather['temp'])
    desc = weather['desc'].lower()
    
    outdoor_keywords = ['прогулк', 'встреч', 'спорт', 'тренировк', 'бег', 'велосипед', 'поход', 'парк', 'улиц', 'двор']
    has_outdoor_task = any(any(keyword in task['text'].lower() for keyword in outdoor_keywords) 
                          for task in tasks if not task.get('done', False))
    
    if 'дожд' in desc or 'ливен' in desc or 'морос' in desc:
        advice.append("☔ Будет дождь — возьми зонт!")
        if has_outdoor_task:
            advice.append("⚠️ У тебя задачи на улице, учти погоду!")
    
    if 'снег' in desc or 'метел' in desc:
        advice.append("❄️ Будет снег — одевайся теплее!")
    
    if temp < -10:
        advice.append("🥶 Сильный мороз! Одевайся максимально тепло.")
    elif temp < 0:
        advice.append("🥶 На улице мороз — не забудь шапку и перчатки!")
    elif temp < 10:
        advice.append("🧥 Прохладно — возьми куртку!")
    elif temp > 30:
        advice.append("🔥 Очень жарко! Избегай физических нагрузок на улице.")
        if has_outdoor_task:
            advice.append(" Пей больше воды и делай перерывы в тени!")
    elif temp > 25:
        advice.append("☀️ Жарко! Не забудь воду и головной убор.")
        if has_outdoor_task:
            advice.append("💧 Пей больше воды, если будешь на улице!")
    
    if int(weather['wind']) > 25:
        advice.append(" Сильный ветер — будь осторожен!")
    elif int(weather['wind']) > 15:
        advice.append("🌬️ Ветрено — возьми ветровку.")
    
    if int(weather['humidity']) > 85:
        advice.append("💧 Высокая влажность — может быть душно.")
    
    return "\n".join(advice) if advice else ""

# ================= УВЕДОМЛЕНИЯ =================
async def send_notification(context, item, prefix):
    priority_emoji = "🔥" if item.get('priority') == 'high' else ""
    category_text = f" #{item['category']}" if item.get('category') else ""
    message = f"{prefix} Напоминание от Prono!\n\n{priority_emoji} 📝 {item['text']}{category_text}"
    if item['type'] == 'event':
        message += f"\n⏰ {item['time_start']} - {item['time_end']}"
    else:
        message += f"\n🕐 {item['time_start']}"
    try:
        await context.bot.send_message(chat_id=item['chat_id'], text=message)
    except:
        pass

async def check_upcoming_tasks(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    current_time = now.strftime('%H:%M')
    current_date = now.strftime('%Y-%m-%d')
    
    for item in planner_data:
        if item.get('done', False) or item.get('chat_id') is None:
            continue
        
        if (item['date'] == current_date and item['time_start'] == current_time and not item.get('notified', False)):
            await send_notification(context, item, "⏰")
            item['notified'] = True
            save_data()
        
        if (item['date'] == current_date and not item.get('notified_15', False)):
            task_time = datetime.strptime(f"{current_date} {item['time_start']}", '%Y-%m-%d %H:%M')
            time_diff = task_time - now
            if time_diff.total_seconds() <= 900 and time_diff.total_seconds() > 0:
                await send_notification(context, item, "⏱️ За 15 минут:")
                item['notified_15'] = True
                save_data()
        
        if (item['date'] == current_date and not item.get('notified_60', False)):
            task_time = datetime.strptime(f"{current_date} {item['time_start']}", '%Y-%m-%d %H:%M')
            time_diff = task_time - now
            if time_diff.total_seconds() <= 3600 and time_diff.total_seconds() > 900:
                await send_notification(context, item, "⏰ За 1 час:")
                item['notified_60'] = True
                save_data()

# ================= БРИФИНГИ =================
async def send_morning_briefing(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    if now.hour != 8 or now.minute > 2:
        return
    
    current_date = now.strftime('%Y-%m-%d')
    today_tasks = [item for item in planner_data if item['date'] == current_date and not item['done']]
    
    if not today_tasks:
        return
    
    today_tasks.sort(key=lambda x: x['time_start'])
    
    # Получаем погоду
    weather = await get_weather(WEATHER_CITY)
    
    for chat_id in set(item['chat_id'] for item in today_tasks):
        user_tasks = [t for t in today_tasks if t['chat_id'] == chat_id]
        if not user_tasks:
            continue
        
        greeting = get_greeting_by_time()
        msg = f"{greeting} Сегодня у тебя {len(user_tasks)} задач:\n\n"
        for task in user_tasks[:5]:
            priority = "" if task.get('priority') == 'high' else "⏳"
            msg += f"{priority} {task['time_start']} — {task['text']}\n"
        
        if len(user_tasks) > 5:
            msg += f"\n...и ещё {len(user_tasks) - 5} задач."
        
        # Добавляем погоду и советы
        if weather:
            msg += f"\n\n🌤️ <b>Погода:</b> {weather['temp']}°C, {weather['desc']}\n"
            msg += f"📈 {weather['min_temp']}°C ... {weather['max_temp']}°C\n"
            advice = get_weather_advice(weather, user_tasks)
            if advice:
                msg += f"\n💡 <b>Советы:</b>\n{advice}"
        
        msg += "\n\nТы со всем справишься! 💪"
        
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
        except:
            pass

async def send_evening_briefing(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    if now.hour != 21 or now.minute > 2:
        return
    
    current_date = now.strftime('%Y-%m-%d')
    today_tasks = [item for item in planner_data if item['date'] == current_date]
    done_tasks = [t for t in today_tasks if t.get('done', False)]
    
    for chat_id in set(item['chat_id'] for item in today_tasks):
        user_today = [t for t in today_tasks if t['chat_id'] == chat_id]
        user_done = [t for t in done_tasks if t['chat_id'] == chat_id]
        
        if not user_today:
            continue
        
        total = len(user_today)
        completed = len(user_done)
        rate = (completed / total * 100) if total > 0 else 0
        
        msg = f"🌙 День завершён!\n\n"
        msg += f"✅ Выполнено: {completed} из {total}\n"
        msg += f"📈 Эффективность: {rate:.0f}%\n\n"
        
        if rate >= 80:
            msg += " Отличная работа! Ты молодец!"
        elif rate >= 50:
            msg += "👍 Хороший результат!"
        else:
            msg += "💪 Не переживай, завтра будет лучше!"
        
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except:
            pass

async def send_weekly_report(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    if now.weekday() != 6 or now.hour != 20 or now.minute > 2:
        return
    
    week_ago = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    today = now.strftime('%Y-%m-%d')
    
    week_tasks = [item for item in planner_data if week_ago <= item['date'] <= today]
    
    for chat_id in set(item['chat_id'] for item in week_tasks):
        user_tasks = [t for t in week_tasks if t['chat_id'] == chat_id]
        if not user_tasks:
            continue
        
        total = len(user_tasks)
        completed = len([t for t in user_tasks if t.get('done', False)])
        rate = (completed / total * 100) if total > 0 else 0
        
        msg = f"📊 <b>Итоги недели</b>\n\n"
        msg += f" Всего задач: {total}\n"
        msg += f"✅ Выполнено: {completed}\n"
        msg += f"📈 Эффективность: {rate:.0f}%\n\n"
        
        if rate >= 80:
            msg += "🏆 Ты настоящий мастер планирования!"
        elif rate >= 50:
            msg += "👍 Хорошая неделя! Продолжай!"
        else:
            msg += "💪 Не сдавайся! Каждая неделя — новый шанс!"
        
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
        except:
            pass

# ================= КОМАНДЫ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = update.effective_user.first_name
    
    if chat_id not in users_data:
        users_data[chat_id] = {'name': name, 'tasks_created': 0, 'tasks_completed': 0, 'xp': 0, 'level': 1}
        save_data()
    
    greeting = get_greeting_by_time()
    text = (f"{greeting} {name}! Я <b>Prono</b> — твой личный помощник.\n\n"
            f"🎯 <b>Уровень {users_data[chat_id]['level']}</b> |  {users_data[chat_id]['xp']} XP\n\n"
            f"📋 <b>Команды:</b>\n"
            f"/today — задачи на сегодня\n"
            f"/list — все задачи\n"
            f"/done 1 — выполнить задачу\n"
            f"/delete 1 — удалить\n"
            f"/stats — статистика\n"
            f"/level — уровень и XP\n"
            f"/weather — погода и советы\n"
            f"/help — все команды\n\n"
            f"💬 Просто напиши задачу: 'Завтра в 14:00 встреча'")
    await update.message.reply_text(text, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "📋 <b>Все команды Prono:</b>\n\n"
    text += "<b>Задачи:</b>\n"
    text += "Просто напиши: 'Завтра в 14:00 встреча'\n"
    text += "Добавь 'важно' или 🔥 для приоритета\n"
    text += "Добавь #категория для сортировки\n\n"
    text += "<b>Управление:</b>\n"
    text += "/today — задачи на сегодня\n"
    text += "/list — все задачи\n"
    text += "/done [ID] — выполнить\n"
    text += "/delete [ID] — удалить\n"
    text += "/snooze [ID] [мин] — отложить\n\n"
    text += "<b>Статистика:</b>\n"
    text += "/stats — твоя статистика\n"
    text += "/level — уровень и XP\n\n"
    text += "<b>Погода:</b>\n"
    text += "/weather — прогноз и советы\n\n"
    text += "<b>Общение:</b>\n"
    text += "Напиши 'привет', 'как дела', 'я устал'\n"
    
    await update.message.reply_text(text, parse_mode='HTML')

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("⏳ Загружаю погоду...")
    
    weather = await get_weather(WEATHER_CITY)
    
    if not weather:
        await update.message.reply_text("❌ Не удалось получить данные о погоде.")
        return
    
    msg = f"️ <b>Погода в {WEATHER_CITY}:</b>\n\n"
    msg += f"🌡️ Сейчас: {weather['temp']}°C\n"
    msg += f"📊 {weather['desc']}\n"
    msg += f"📈 Макс: {weather['max_temp']}°C / Мин: {weather['min_temp']}°C\n"
    msg += f"💧 Влажность: {weather['humidity']}%\n"
    msg += f"💨 Ветер: {weather['wind']} км/ч\n\n"
    
    # Советы на основе задач
    today = datetime.now().strftime('%Y-%m-%d')
    today_tasks = [t for t in planner_data if t['date'] == today and t.get('chat_id') == chat_id and not t.get('done', False)]
    
    advice = get_weather_advice(weather, today_tasks)
    if advice:
        msg += f"💡 <b>Советы на сегодня:</b>\n{advice}"
    else:
        msg += "️ Погода хорошая, наслаждайся днём!"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global next_id
    user_text = update.message.text.strip()
    chat_id = update.effective_chat.id
    
    if not user_text:
        return

    chat_reply = get_conversational_reply(user_text)
    parsed = parse_user_input(user_text)
    
    if parsed['date'] and parsed['time_start'] and len(parsed['task_text']) > 2:
        if not parsed['time_end']:
            parsed['time_end'] = parsed['time_start']
            item_type = 'task'
        else:
            item_type = 'event'
        
        item = {
            'id': next_id, 'type': item_type, 'date': parsed['date'],
            'time_start': parsed['time_start'], 'time_end': parsed['time_end'],
            'text': parsed['task_text'], 'priority': parsed['priority'],
            'category': parsed['category'], 'done': False,
            'notified': False, 'notified_15': False, 'notified_60': False,
            'chat_id': chat_id
        }
        planner_data.append(item)
        next_id += 1
        if chat_id in users_data:
            users_data[chat_id]['tasks_created'] = users_data[chat_id].get('tasks_created', 0) + 1
            save_data()
        save_data()
        
        date_obj = datetime.strptime(parsed['date'], '%Y-%m-%d')
        priority_text = " 🔥 ВАЖНО" if parsed['priority'] == 'high' else ""
        category_text = f" #{parsed['category']}" if parsed['category'] else ""
        
        response = f"✅ Задача #{item['id']} добавлена!{priority_text}\n📅 {date_obj.strftime('%d.%m.%Y')} в {parsed['time_start']}\n {parsed['task_text']}{category_text}\n\nЯ напомню тебе за час, за 15 минут и точно вовремя! 😉"
        
        keyboard = [
            [InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{item['id']}"),
             InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{item['id']}")],
            [InlineKeyboardButton("⏱️ +10 мин", callback_data=f"snooze_{item['id']}_10"),
             InlineKeyboardButton("📅 Завтра", callback_data=f"tomorrow_{item['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(response, reply_markup=reply_markup)
    elif chat_reply and not parsed['date']:
        await update.message.reply_text(chat_reply)
    else:
        await update.message.reply_text("Хм, я не совсем понял. Мы просто болтаем или ты хочешь что-то запланировать? 🤔\nНапиши: 'Завтра в 10:00 купить хлеб' или просто 'как дела?'")

async def show_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    today = datetime.now().strftime('%Y-%m-%d')
    user_items = [item for item in planner_data if item['date'] == today and not item['done'] and item.get('chat_id') == chat_id]
    if not user_items:
        await update.message.reply_text("📭 На сегодня задач нет! Наслаждайся свободным временем. ️")
        return
    user_items.sort(key=lambda x: x['time_start'])
    message = f"📋 Твой план на сегодня ({datetime.now().strftime('%d.%m')}):\n\n"
    for item in user_items:
        priority = "🔥" if item.get('priority') == 'high' else "⏳"
        time_str = f"{item['time_start']}-{item['time_end']}" if item['type'] == 'event' else item['time_start']
        message += f"{priority} ⏰ {time_str} | {item['text']}\n"
    
    keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_today")]]
    await update.message.reply_text(message + "\nТы со всем справишься! 💪", reply_markup=InlineKeyboardMarkup(keyboard))

async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_items = [item for item in planner_data if not item['done'] and item.get('chat_id') == chat_id]
    if not user_items:
        await update.message.reply_text("📭 У тебя нет активных задач. Идеальный порядок! ✨")
        return
    user_items.sort(key=lambda x: (x['date'], x['time_start']))
    message = "📋 Твои ближайшие планы:\n\n"
    for item in user_items[:15]:
        date_obj = datetime.strptime(item['date'], '%Y-%m-%d')
        priority = "" if item.get('priority') == 'high' else ""
        time_str = f"{item['time_start']}-{item['time_end']}" if item['type'] == 'event' else item['time_start']
        message += f"{priority} 📅 {date_obj.strftime('%d.%m')} ⏰ {time_str} | {item['text']}\n"
    await update.message.reply_text(message)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in users_data:
        await update.message.reply_text("Пока нет статистики. Добавь первую задачу!")
        return
    stats = users_data[chat_id]
    created = stats.get('tasks_created', 0)
    completed = stats.get('tasks_completed', 0)
    xp = stats.get('xp', 0)
    level = stats.get('level', 1)
    success_rate = (completed / created * 100) if created > 0 else 0
    
    message = f"📊 <b>Твоя статистика:</b>\n\n"
    message += f"🎯 <b>Уровень {level}</b> | ✨ {xp} XP\n"
    message += f"✅ Выполнено: {completed}\n"
    message += f"📝 Всего создано: {created}\n"
    message += f"📈 Эффективность: {success_rate:.1f}%\n\n"
    
    next_level_xp = level * 100
    xp_to_next = next_level_xp - xp
    message += f"🎯 До следующего уровня: {xp_to_next} XP\n\n"
    
    if success_rate >= 80:
        message += "🏆 Ты настоящий мастер планирования!"
    elif success_rate >= 50:
        message += "👍 Хороший результат! Продолжай!"
    else:
        message += "💪 Не сдавайся! Каждое выполненное дело — это победа!"
    
    await update.message.reply_text(message, parse_mode='HTML')

async def show_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in users_data:
        await update.message.reply_text("Пока нет данных. Добавь задачу!")
        return
    
    stats = users_data[chat_id]
    xp = stats.get('xp', 0)
    level = stats.get('level', 1)
    
    level_names = {
        1: "🌱 Новичок",
        2: "📚 Ученик",
        3: "⚡ Активист",
        4: "📋 Организатор",
        5: "🎯 Мастер планирования",
        6: "👑 Легенда продуктивности"
    }
    
    level_name = level_names.get(level, f"Уровень {level}")
    next_level_xp = level * 100
    progress = (xp / next_level_xp) * 100
    
    msg = f"🎯 <b>Твой прогресс:</b>\n\n"
    msg += f"<b>{level_name}</b>\n"
    msg += f"✨ XP: {xp} / {next_level_xp}\n"
    msg += f"📊 Прогресс: {progress:.0f}%\n\n"
    
    if xp >= next_level_xp:
        msg += "🎉 Поздравляю! Ты достиг нового уровня!"
    
    await update.message.reply_text(msg, parse_mode='HTML')

# ================= ОБРАБОТКА КНОПОК =================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global next_id
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    
    if data.startswith('done_'):
        task_id = int(data.split('_')[1])
        for item in planner_data:
            if item['id'] == task_id and item.get('chat_id') == chat_id:
                item['done'] = True
                if chat_id in users_data:
                    users_data[chat_id]['tasks_completed'] = users_data[chat_id].get('tasks_completed', 0) + 1
                    users_data[chat_id]['xp'] = users_data[chat_id].get('xp', 0) + 10
                    
                    xp = users_data[chat_id]['xp']
                    level = users_data[chat_id]['level']
                    if xp >= level * 100:
                        users_data[chat_id]['level'] = level + 1
                        save_data()
                        await query.edit_message_text(f"✅ Задача #{task_id} выполнена! +10 XP\n🎉 Новый уровень: {users_data[chat_id]['level']}!")
                        return
                
                save_data()
                await query.edit_message_text(f"✅ Задача #{task_id} выполнена! +10 XP")
                return
        await query.edit_message_text("Задача не найдена.")
    
    elif data.startswith('delete_'):
        task_id = int(data.split('_')[1])
        for i, item in enumerate(planner_data):
            if item['id'] == task_id and item.get('chat_id') == chat_id:
                planner_data.pop(i)
                save_data()
                await query.edit_message_text(f"🗑️ Задача #{task_id} удалена")
                return
        await query.edit_message_text("Задача не найдена.")
    
    elif data.startswith('snooze_'):
        parts = data.split('_')
        task_id = int(parts[1])
        minutes = int(parts[2])
        for item in planner_data:
            if item['id'] == task_id and item.get('chat_id') == chat_id:
                new_time = datetime.now() + timedelta(minutes=minutes)
                item['date'] = new_time.strftime('%Y-%m-%d')
                item['time_start'] = new_time.strftime('%H:%M')
                item['time_end'] = new_time.strftime('%H:%M')
                item['notified'] = False
                item['notified_15'] = False
                item['notified_60'] = False
                save_data()
                await query.edit_message_text(f"️ Задача #{task_id} отложена на {minutes} минут. Напомню в {item['time_start']}")
                return
        await query.edit_message_text("Задача не найдена.")
    
    elif data.startswith('tomorrow_'):
        task_id = int(data.split('_')[1])
        for item in planner_data:
            if item['id'] == task_id and item.get('chat_id') == chat_id:
                tomorrow = datetime.now() + timedelta(days=1)
                item['date'] = tomorrow.strftime('%Y-%m-%d')
                item['notified'] = False
                item['notified_15'] = False
                item['notified_60'] = False
                save_data()
                await query.edit_message_text(f"📅 Задача #{task_id} перенесена на завтра ({tomorrow.strftime('%d.%m')})")
                return
        await query.edit_message_text("Задача не найдена.")
    
    elif data == 'refresh_today':
        await show_today(update, context)

# ================= ЗАПУСК =================
def main():
    load_data()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("today", show_today))
    app.add_handler(CommandHandler("list", show_list))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("level", show_level))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Напоминания о задачах
    app.job_queue.run_repeating(check_upcoming_tasks, interval=60, first=10)
    
    # Брифинги
    app.job_queue.run_repeating(send_morning_briefing, interval=60, first=10)
    app.job_queue.run_repeating(send_evening_briefing, interval=60, first=10)
    app.job_queue.run_repeating(send_weekly_report, interval=60, first=10)
    
    print("🤖 Prono (полная версия с погодой) запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
