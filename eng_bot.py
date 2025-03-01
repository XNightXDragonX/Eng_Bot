import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import psycopg2
import random


TOKEN = '8097822589:AAFoWYW8lffV4Ihj9CKwhuAGLp6WIfVTJfc'
DB_CONFIG = {
    'dbname': 'Eng_Bot',
    'user': 'postgres',
    'password': 'Fedia_38_2025',
    'host': 'localhost'
}

bot = telebot.TeleBot(TOKEN)


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()


    cur.execute("""
        CREATE TABLE IF NOT EXISTS common_words (
            id SERIAL PRIMARY KEY,
            word_rus VARCHAR(50) NOT NULL,
            word_eng VARCHAR(50) NOT NULL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_words (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            word_rus VARCHAR(50) NOT NULL,
            word_eng VARCHAR(50) NOT NULL
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id BIGINT PRIMARY KEY,
            correct_answers INTEGER DEFAULT 0,
            total_attempts INTEGER DEFAULT 0
        )
    """)
    

    cur.execute("SELECT COUNT(*) FROM common_words")
    if cur.fetchone()[0] == 0:
        common_words = [
            ('красный', 'red'), ('синий', 'blue'), ('зеленый', 'green'),
            ('я', 'I'), ('ты', 'you'), ('он', 'he'), ('она', 'she'),
            ('большой', 'big'), ('маленький', 'small'), ('дом', 'house')
        ]
        cur.executemany(
            "INSERT INTO common_words (word_rus, word_eng) VALUES (%s, %s)",
            common_words
        )
    
    conn.commit()
    cur.close()
    conn.close()


def get_answer_options(correct_answer, all_words):
    options = [correct_answer]
    while len(options) < 4:
        word = random.choice(all_words)
        if word not in options:
            options.append(word)
    random.shuffle(options)
    return options


def create_keyboard(options, callback_prefix):
    keyboard = InlineKeyboardMarkup(row_width=2)
    for option in options:
        keyboard.add(InlineKeyboardButton(
            text=option,
            callback_data=f"{callback_prefix}|{option}"
        ))
    keyboard.add(
        InlineKeyboardButton(text="Добавить слово", callback_data="command|add"),
        InlineKeyboardButton(text="Удалить слово", callback_data="command|delete")
    )
    return keyboard


def create_start_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton('/start'))
    return keyboard


@bot.message_handler(commands=['start'])
def start(message):
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT user_id FROM user_stats WHERE user_id = %s", (user_id,))
    user_exists = cur.fetchone()
    
    if not user_exists:
        cur.execute(
            "INSERT INTO user_stats (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (user_id,)
        )
        conn.commit()
        
        bot.send_message(
            user_id,
            "Добро пожаловать! Нажмите кнопку ниже, чтобы начать.",
            reply_markup=create_start_keyboard()
        )
    else:
        bot.send_message(
            user_id,
            "Добро пожаловать! Выберите действие:\n"
            "/learn - учить слова\n"
            "/add - добавить слово\n"
            "/delete - удалить слово",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )
    
    cur.close()
    conn.close()


def learn_words(user_id):
    conn = get_db_connection()
    cur = conn.cursor()


    cur.execute("SELECT word_rus, word_eng FROM common_words")
    common_words = cur.fetchall()
    cur.execute("SELECT word_rus, word_eng FROM user_words WHERE user_id = %s", (user_id,))
    user_words = cur.fetchall()
    
    all_words = common_words + user_words
    if not all_words:
        bot.send_message(user_id, "Словарь пуст. Добавьте слова через /add")
        cur.close()
        conn.close()
        return
    
    word_rus, word_eng = random.choice(all_words)
    all_eng_words = [w[1] for w in all_words]
    options = get_answer_options(word_eng, all_eng_words)
    
    bot.send_message(
        user_id,
        f"Как переводится слово: {word_rus}?",
        reply_markup=create_keyboard(options, f"answer|{word_rus}|{word_eng}")
    )
    
    cur.close()
    conn.close()

@bot.message_handler(commands=['learn'])
def start_learn(message):
    if message.from_user.is_bot:
        return
    learn_words(message.from_user.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('answer|') or call.data.startswith('command|'))
def handle_answer(call):
    if call.from_user.is_bot:
        return
    
    user_id = call.from_user.id
    callback_type = call.data.split('|')[0]
    

    if callback_type == "command":
        command = call.data.split('|')[1]
        if command == "add":
            bot.answer_callback_query(call.id, "Добавление слова")
            bot.send_message(user_id, "Введите слово на русском и его перевод через запятую (пример: дом, house)")
            bot.register_next_step_handler_by_chat_id(user_id, process_add_word)
        elif command == "delete":
            bot.answer_callback_query(call.id, "Удаление слова")
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT word_rus, word_eng FROM user_words WHERE user_id = %s", (user_id,))
            words = cur.fetchall()
            
            if not words:
                bot.send_message(user_id, "У вас нет личных слов для удаления")
                cur.close()
                conn.close()
                return
            
            keyboard = InlineKeyboardMarkup()
            for word_rus, word_eng in words:
                keyboard.add(InlineKeyboardButton(
                    text=f"{word_rus} ({word_eng})",
                    callback_data=f"delete|{word_rus}|{word_eng}"
                ))
            bot.send_message(user_id, "Выберите слово для удаления:", reply_markup=keyboard)
            
            cur.close()
            conn.close()
        return
    

    _, word_rus, correct_answer, chosen_answer = call.data.split('|')
    
    conn = get_db_connection()
    cur = conn.cursor()
    

    cur.execute(
        "UPDATE user_stats SET total_attempts = total_attempts + 1 WHERE user_id = %s",
        (user_id,)
    )
    
    if chosen_answer == correct_answer:
        cur.execute(
            "UPDATE user_stats SET correct_answers = correct_answers + 1 WHERE user_id = %s",
            (user_id,)
        )
        bot.answer_callback_query(call.id, "Правильно!")
        bot.send_message(user_id, "Отлично! Попробуем следующее слово.")
        learn_words(user_id)
    else:
        bot.answer_callback_query(call.id, "Неправильно!")
        bot.send_message(user_id, "Попробуйте снова.")

        all_words = []
        cur.execute("SELECT word_rus, word_eng FROM common_words")
        all_words.extend(cur.fetchall())
        cur.execute("SELECT word_rus, word_eng FROM user_words WHERE user_id = %s", (user_id,))
        all_words.extend(cur.fetchall())
        all_eng_words = [w[1] for w in all_words]
        options = get_answer_options(correct_answer, all_eng_words)
        bot.send_message(
            user_id,
            f"Как переводится слово: {word_rus}?",
            reply_markup=create_keyboard(options, f"answer|{word_rus}|{correct_answer}")
        )
    
    conn.commit()
    cur.close()
    conn.close()


@bot.message_handler(commands=['add'])
def add_word(message):
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    bot.send_message(user_id, "Введите слово на русском и его перевод через запятую (пример: дом, house)")
    bot.register_next_step_handler(message, process_add_word)

def process_add_word(message):
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    try:
        word_rus, word_eng = [w.strip() for w in message.text.split(',')]
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "SELECT word_rus, word_eng FROM user_words WHERE user_id = %s AND (word_rus = %s OR word_eng = %s)",
            (user_id, word_rus, word_eng)
        )
        user_word_exists = cur.fetchone()
        
        cur.execute(
            "SELECT word_rus, word_eng FROM common_words WHERE word_rus = %s OR word_eng = %s",
            (word_rus, word_eng)
        )
        common_word_exists = cur.fetchone()
        
        if user_word_exists or common_word_exists:
            bot.send_message(
                user_id,
                "Такое слово уже добавлено. Пожалуйста, введите другое слово (на русском и английском через запятую)."
            )
            bot.register_next_step_handler_by_chat_id(user_id, process_add_word)
        else:
            cur.execute(
                "INSERT INTO user_words (user_id, word_rus, word_eng) VALUES (%s, %s, %s)",
                (user_id, word_rus, word_eng)
            )
            conn.commit()
            bot.send_message(user_id, "Слово успешно добавлено!")
        
    except Exception as e:
        bot.send_message(user_id, "Ошибка формата. Используйте: слово, перевод")
        bot.register_next_step_handler_by_chat_id(user_id, process_add_word)
    finally:
        cur.close()
        conn.close()


@bot.message_handler(commands=['delete'])
def delete_word(message):
    if message.from_user.is_bot:
        return
    
    user_id = message.from_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT word_rus, word_eng FROM user_words WHERE user_id = %s", (user_id,))
    words = cur.fetchall()
    
    if not words:
        bot.send_message(user_id, "У вас нет личных слов для удаления")
        return
    
    keyboard = InlineKeyboardMarkup()
    for word_rus, word_eng in words:
        keyboard.add(InlineKeyboardButton(
            text=f"{word_rus} ({word_eng})",
            callback_data=f"delete|{word_rus}|{word_eng}"
        ))
    bot.send_message(user_id, "Выберите слово для удаления:", reply_markup=keyboard)
    
    cur.close()
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete|'))
def handle_delete(call):
    if call.from_user.is_bot:
        return
    
    user_id = call.from_user.id
    _, word_rus, word_eng = call.data.split('|')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM user_words WHERE user_id = %s AND word_rus = %s AND word_eng = %s",
        (user_id, word_rus, word_eng)
    )
    conn.commit()
    bot.answer_callback_query(call.id, "Слово удалено!")
    bot.send_message(user_id, "Слово успешно удалено!")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    init_db()
    bot.polling(none_stop=True)