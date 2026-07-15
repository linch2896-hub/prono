from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
import json
import os
import re
import dateparser
import random

# Токен от BotFather
TOKEN = "8951461242:AAFYgVpzrJwkTuyazSP5_M1oz0zcl4pxGAw"

# Файл для хранения данных
DATA_FILE = "prono_data.json"
USER_FILE = "prono_users.json"

# Глобальные переменные
planner_data = []
next_id = 1
users_data = {}

# ============ ЛИЧНОСТЬ PRONO ============

CONVERSATIONAL_RESPONSES = {
    "привет": [
        "Привет! Я Prono. Готов организовать твое блестящее будущее! Как настроение? 😊",
        "Здравствуй! Рад тебя видеть. Что запланируем на сегодня?",
        "Привет-привет! Я уже настроил свои внутренние часы. Чем могу помочь?"
    ],
    "как дела": [
        "Мои схемы работают идеально, все данные в порядке! А у тебя как?",
        "Отлично! Я только что освободил 5 минут в твоем расписании, чтобы спросить: как ты?",
        "Всегда в боевой готовности! Готов планировать, считать и поддерживать."
    ],
    "устал": [
        "Понимаю. Давай я добавлю в твое расписание '15 минут на отдых'? Ты это заслужил(а)! ☕",
        "Эй, не забывай, что даже самым эффективным людям нужен перерыв. Выпей воды и отдышись!",
        "Записываю в черновик: 'Отдых'. Не забывай заботиться о себе, я тут, чтобы снять с тебя часть забот."
    ],
    "спасибо": [
        "Всегда пожалуйста! Я здесь, чтобы твоя жизнь была в порядке. ✨",
        "Рад стараться! Обращайся в любое время.",
        "Для меня это честь! Твое время — мой приоритет."
    ],
    "шутк": [
        "Почему планировщик не ходит на свидания? Потому что у него всё расписано! 😄",
        "Знаешь, в чем разница между мной и будильником? Я не даю тебе по мне ударить.",
        "Мой любимый цвет — цвет успешно выполненного списка задач! 🟩"
    ],
    "грустно": [
        "Мне жаль это слышать. Помни: после самого загруженного дня всегда наступает спокойная ночь. Я рядом! 🤗",
        "Хочешь, я найду в твоем расписании окно для чего-то приятного? Ты заслуживаешь радости."
    ],
    "скучно": [
        "Может, самое время добавить что-то интересное в расписание? Кино, прогулка, хобби?",
        "Скука — это знак, что пора сделать что-то новое! Что давно откладывал(а)?",
        "У меня есть идея: добавь задачу 'Придумать что-то крутое' на сегодня! 😊"
    ]
}

def get_conversational_reply(text):
    text_lower = text.lower()
    for keyword, responses in CONVERSATIONAL_RESPONSES.items():
        if keyword in text_lower:
            return random.choice(responses)
    return None

# ============ РАБОТА С ФАЙЛАМИ ============

def load_data():
    global planner_data, next_id, users_data
    
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            planner_data = data.get('items', [])
            next_id = data.get('next_id', 1)
    else:
        planner_data = []
        next_id = 1
    
    if os.path.exists(USER_FILE):
        with open(USER_FILE, 'r', encoding='utf-8') as f:
            users_data = json.load(f)
    else:
        users_data = {}

def save_data():
    data = {
        'items': planner_data,
        'next_id': next_id
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_users():
    with open(USER_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)

# ============ УМНЫЙ ПАРСЕР ============

def parse_user_input(text):
    result = {
        'date': None,
        'time_start': None,
        'time_end': None,
        'task_text': text,
        'priority': 'normal',
        'category': None
    }
    
    # Проверяем приоритет
    if any(word in text.lower() for word in ['важно', 'срочно', '🔥', '!']):
        result['priority'] = 'high'
    
    # Проверяем категорию (#работа, #дом, etc.)
    category_match = re.search(r'#(\w+)', text)
    if category_match:
        result['category'] = category_match.group(1)
    
    # Ищем время
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

    # Ищем дату
    date_keywords = ['сегодня', 'завтра', 'послезавтра', 'в понедельник', 'во вторник', 
                     'в среду', 'в четверг', 'в пятницу', 'в субботу', 'в воскресенье']
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

    # Убираем категорию из текста
    text = re.sub(r'#\w+', '', text).strip()
    text = re.sub(r'^\s*(на|в|во)\s+', '', text, flags=re.IGNORECASE).strip()
    result['task_text'] = text
    return result

# ============ ПРОВЕРКА НАПОМИНАНИЙ ============

async def send_notification(context, item, prefix):
    priority_emoji = "" if item.get('priority') == 'high' else ""
    category_text = f" #{item['category']}" if item.get('category') else ""
    
    message = (
        f"{prefix} Напоминание от Prono!\n\n"
        f"{priority_emoji} 📝 {item['text']}{category_text}"
    )
    
    if item['type'] == 'event':
        message += f"\n⏰ {item['time_start']} - {item['time_end']}"
    else:
        message += f"\n🕐 {item['time_start']}"
    
    await context.bot.send_message(
        chat_id=item['chat_id'],
        text=message
    )

async def check_upcoming_tasks(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет напоминания каждую минуту"""
    now = datetime.now()
    current_time = now.strftime('%H:%M')
    current_date = now.strftime('%Y-%m-%d')
    
    for item in planner_data:
        if item.get('done', False) or item.get('chat_id') is None:
            continue
        
        # Точное время
        if (item['date'] == current_date and 
            item['time_start'] == current_time and 
            not item.get('notified', False)):
            
            await send_notification(context, item, "⏰")
            item['notified'] = True
            save_data()
        
        # За 15 минут
        if (item['date'] == current_date and not item.get('notified_15', False)):
            task_time = datetime.strptime(f"{current_date} {item['time_start']}", '%Y-%m-%d %H:%M')
            time_diff = task_time - now
            if time_diff.total_seconds() <= 900 and time_diff.total_seconds() > 0:
                await send_notification(context, item, "⏱️ За 15 минут:")
                item['notified_15'] = True
                save_data()
        
        # За 1 час
        if (item['date'] == current_date and not item.get('notified_60', False)):
            task_time = datetime.strptime(f"{current_date} {item['time_start']}", '%Y-%m-%d %H:%M')
            time_diff = task_time - now
            if time_diff.total_seconds() <= 3600 and time_diff.total_seconds() > 900:
                await send_notification(context, item, "⏰ За 1 час:")
                item['notified_60'] = True
                save_data()

# ============ КОМАНДЫ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in users_data:
        users_data[chat_id] = {
            'name': user.first_name,
            'tasks_created': 0,
            'tasks_completed': 0
        }
        save_users()
    
    name = users_data[chat_id].get('name', user.first_name)
    
    await update.message.reply_text(
        f"👋 Привет, {name}! Я **Prono** — твой личный помощник для планирования.\n\n"
        "Я предвижу твоё будущее и забочусь о нём! ✨\n\n"
        " **Как добавить задачу:**\n"
        "Просто напиши: 'Завтра в 14:00 встреча с врачом'\n\n"
        "🔥 **Приоритет:** добавь слово 'важно' или '🔥'\n"
        "📁 **Категория:** добавь #работа, #дом, #личное\n\n"
        "💬 **Со мной можно болтать!** Напиши 'как дела?' или 'я устал'\n\n"
        "📋 **Команды:**\n"
        "/today — задачи на сегодня\n"
        "/list — все задачи\n"
        "/done 1 — отметить задачу выполненной\n"
        "/delete 1 — удалить задачу\n"
        "/snooze 1 10 — отложить на 10 минут\n"
        "/find слово — поиск задач\n"
        "/stats — твоя статистика\n"
        "/history — выполненные задачи\n"
        "/setname Имя — изменить имя"
    )

async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text("Напиши имя после команды. Пример: /setname Анна")
        return
    
    name = " ".join(context.args)
    users_data[chat_id] = users_data.get(chat_id, {})
    users_data[chat_id]['name'] = name
    save_users()
    
    await update.message.reply_text(f"Отлично! Теперь я буду обращаться к тебе как {name}! 😊")

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
            'id': next_id,
            'type': item_type,
            'date': parsed['date'],
            'time_start': parsed['time_start'],
            'time_end': parsed['time_end'],
            'text': parsed['task_text'],
            'priority': parsed['priority'],
            'category': parsed['category'],
            'done': False,
            'notified': False,
            'notified_15': False,
            'notified_60': False,
            'chat_id': chat_id
        }
        
        planner_data.append(item)
        next_id += 1
        
        # Обновляем статистику
        if chat_id in users_data:
            users_data[chat_id]['tasks_created'] = users_data[chat_id].get('tasks_created', 0) + 1
            save_users()
        
        save_data()
        
        date_obj = datetime.strptime(parsed['date'], '%Y-%m-%d')
        date_display = date_obj.strftime('%d.%m.%Y')
        
        priority_text = " 🔥 ВАЖНО" if parsed['priority'] == 'high' else ""
        category_text = f" #{parsed['category']}" if parsed['category'] else ""
        
        if item_type == 'task':
            response = f"✅ Задача #{item['id']} добавлена!{priority_text}\n {date_display} в {parsed['time_start']}\n📝 {parsed['task_text']}{category_text}\n\nЯ напомню тебе за час, за 15 минут и точно вовремя! 😉"
        else:
            response = f"✅ Событие #{item['id']} запланировано!{priority_text}\n📅 {date_display} с {parsed['time_start']} до {parsed['time_end']}\n📝 {parsed['task_text']}{category_text}\n\nОтличный план!"
        
        await update.message.reply_text(response)
        
    elif chat_reply and not parsed['date']:
        await update.message.reply_text(chat_reply)
        
    else:
        await update.message.reply_text(
            "Хм, я не совсем понял. Мы просто болтаем или ты хочешь что-то запланировать? 🤔\n\n"
            "Если это задача, попробуй:\n"
            "• 'Завтра в 10:00 важно купить хлеб'\n"
            "• 'В пятницу в 18:00 #спорт тренировка'\n\n"
            "А если просто хочешь пообщаться, напиши 'как дела?' или 'расскажи шутку'!"
        )

async def show_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    today = datetime.now().strftime('%Y-%m-%d')
    
    user_items = [item for item in planner_data 
                  if item['date'] == today and not item['done'] and item.get('chat_id') == chat_id]
    
    if not user_items:
        await update.message.reply_text("📭 На сегодня задач нет! Наслаждайся свободным временем, ты это заслужил(а). ☀️")
        return
    
    user_items.sort(key=lambda x: x['time_start'])
    name = users_data.get(chat_id, {}).get('name', 'друг')
    
    message = f"📋 {name}, твой план на сегодня ({datetime.now().strftime('%d.%m')}):\n\n"
    for item in user_items:
        priority = "🔥" if item.get('priority') == 'high' else ""
        category = f" #{item['category']}" if item.get('category') else ""
        time_str = f"{item['time_start']}-{item['time_end']}" if item['type'] == 'event' else item['time_start']
        message += f"{priority} ⏰ {time_str} | {item['text']}{category}\n"
    
    await update.message.reply_text(message + f"\n{name}, ты со всем справишься! 💪")

async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    user_items = [item for item in planner_data 
                  if not item['done'] and item.get('chat_id') == chat_id]
    
    if not user_items:
        await update.message.reply_text(" У тебя нет активных задач. Идеальный порядок! ✨")
        return
    
    user_items.sort(key=lambda x: (x['date'], x['time_start']))
    name = users_data.get(chat_id, {}).get('name', 'друг')
    
    message = f"📋 {name}, твои ближайшие планы:\n\n"
    for item in user_items[:15]:
        date_obj = datetime.strptime(item['date'], '%Y-%m-%d')
        priority = "🔥" if item.get('priority') == 'high' else ""
        category = f" #{item['category']}" if item.get('category') else ""
        time_str = f"{item['time_start']}-{item['time_end']}" if item['type'] == 'event' else item['time_start']
        message += f"{priority} 📅 {date_obj.strftime('%d.%m')} ⏰ {time_str} | {item['text']}{category}\n"
    
    if len(user_items) > 15:
        message += f"\n...и еще {len(user_items) - 15} задач. Ты настоящий герой планирования!"
        
    await update.message.reply_text(message)

async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text("Укажи ID задачи. Пример: /done 1")
        return
    
    try:
        task_id = int(context.args[0])
    except:
        await update.message.reply_text("ID должен быть числом")
        return
    
    for item in planner_data:
        if item['id'] == task_id and item.get('chat_id') == chat_id:
            item['done'] = True
            save_data()
            
            # Обновляем статистику
            if chat_id in users_data:
                users_data[chat_id]['tasks_completed'] = users_data[chat_id].get('tasks_completed', 0) + 1
                save_users()
            
            await update.message.reply_text(f"✅ Задача #{task_id} отмечена как выполненная! Молодец! 🎉")
            return
    
    await update.message.reply_text(f"❌ Задача #{task_id} не найдена")

async def delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text("Укажи ID задачи. Пример: /delete 1")
        return
    
    try:
        task_id = int(context.args[0])
    except:
        await update.message.reply_text("ID должен быть числом")
        return
    
    for i, item in enumerate(planner_data):
        if item['id'] == task_id and item.get('chat_id') == chat_id:
            planner_data.pop(i)
            save_data()
            await update.message.reply_text(f"🗑️ Задача #{task_id} удалена")
            return
    
    await update.message.reply_text(f"❌ Задача #{task_id} не найдена")

async def snooze_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if len(context.args) < 2:
        await update.message.reply_text("Пример: /snooze 1 10 (отложить задачу 1 на 10 минут)")
        return
    
    try:
        task_id = int(context.args[0])
        minutes = int(context.args[1])
    except:
        await update.message.reply_text("ID и минуты должны быть числами")
        return
    
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
            
            await update.message.reply_text(f"⏱️ Задача #{task_id} отложена на {minutes} минут. Напомню в {item['time_start']}")
            return
    
    await update.message.reply_text(f"❌ Задача #{task_id} не найдена")

async def find_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text("Напиши слово для поиска. Пример: /find встреча")
        return
    
    search_word = " ".join(context.args).lower()
    
    found = [item for item in planner_data 
             if search_word in item['text'].lower() and 
             not item['done'] and 
             item.get('chat_id') == chat_id]
    
    if not found:
        await update.message.reply_text(f"❌ Не найдено задач со словом '{search_word}'")
        return
    
    message = f"🔍 Найдено задач: {len(found)}\n\n"
    for item in found[:10]:
        date_obj = datetime.strptime(item['date'], '%Y-%m-%d')
        message += f"#{item['id']} 📅 {date_obj.strftime('%d.%m')} ⏰ {item['time_start']} | {item['text']}\n"
    
    await update.message.reply_text(message)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if chat_id not in users_data:
        await update.message.reply_text("Пока нет статистики. Добавь первую задачу!")
        return
    
    stats = users_data[chat_id]
    name = stats.get('name', 'друг')
    created = stats.get('tasks_created', 0)
    completed = stats.get('tasks_completed', 0)
    
    success_rate = (completed / created * 100) if created > 0 else 0
    
    message = (
        f" {name}, твоя статистика:\n\n"
        f"✅ Выполнено задач: {completed}\n"
        f" Всего создано: {created}\n"
        f"📈 Эффективность: {success_rate:.1f}%\n\n"
    )
    
    if success_rate >= 80:
        message += "🏆 Ты настоящий мастер планирования!"
    elif success_rate >= 50:
        message += "👍 Хороший результат! Продолжай в том же духе!"
    else:
        message += "💪 Не сдавайся! Каждое выполненное дело — это победа!"
    
    await update.message.reply_text(message)

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    completed = [item for item in planner_data 
                 if item['done'] and item.get('chat_id') == chat_id]
    
    if not completed:
        await update.message.reply_text(" Пока нет выполненных задач. Вперёд к достижениям!")
        return
    
    completed.sort(key=lambda x: x['date'], reverse=True)
    
    message = "✅ Твои выполненные задачи:\n\n"
    for item in completed[:10]:
        date_obj = datetime.strptime(item['date'], '%Y-%m-%d')
        message += f"📅 {date_obj.strftime('%d.%m')} | {item['text']}\n"
    
    await update.message.reply_text(message)

# ============ ЗАПУСК ============

def main():
    load_data()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", show_today))
    app.add_handler(CommandHandler("list", show_list))
    app.add_handler(CommandHandler("done", mark_done))
    app.add_handler(CommandHandler("delete", delete_task))
    app.add_handler(CommandHandler("snooze", snooze_task))
    app.add_handler(CommandHandler("find", find_tasks))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("setname", set_name))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Проверка напоминаний каждую минуту
    app.job_queue.run_repeating(
        check_upcoming_tasks,
        interval=60,
        first=10,
        data={'chat_id': None}
    )
    
    print(" Prono запущен со всеми функциями!")
    print("⏰ Напоминания: точно вовремя, за 15 мин, за 1 час")
    print(" Статистика, поиск, категории, приоритеты — всё работает!")
    app.run_polling()

if __name__ == '__main__':
    main()
