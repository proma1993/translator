from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
import logging
import uuid
import time
from typing import Dict, Any
from datetime import datetime
from queue import Queue
from threading import Thread
import requests
import base64
import urllib3

# Отключаем предупреждения о небезопасных запросах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

app = Flask(__name__)

# Очередь задач и хранилище результатов
translation_queue = Queue()
translation_results = {}

# Конфигурация GigaChat
GIGACHAT_CREDENTIALS = os.getenv('GIGACHAT_CREDENTIALS')
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1"

def get_gigachat_token():
    """
    Получает токен доступа для GigaChat API
    """
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    
    # Проверяем наличие учетных данных
    if not GIGACHAT_CREDENTIALS:
        logger.error("Отсутствуют учетные данные GigaChat")
        raise ValueError("GIGACHAT_CREDENTIALS не установлен")
    
    # Логируем начало запроса (без учетных данных)
    logger.info("Начало запроса токена")
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Authorization": f"Basic {GIGACHAT_CREDENTIALS}",
        "RqUID": str(uuid.uuid4())  # Добавляем уникальный идентификатор запроса
    }
    
    data = {
        "scope": "GIGACHAT_API_PERS"
    }
    
    try:
        logger.info("Отправка запроса на получение токена")
        response = requests.post(url, headers=headers, data=data, verify=False)
        
        # Логируем ответ для отладки
        logger.info(f"Статус ответа: {response.status_code}")
        logger.debug(f"Заголовки ответа: {response.headers}")
        logger.debug(f"Тело ответа: {response.text}")
        
        response.raise_for_status()
        return response.json()["access_token"]
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при получении токена: {str(e)}")
        if hasattr(e.response, 'text'):
            logger.error(f"Тело ответа с ошибкой: {e.response.text}")
        raise

def process_translations():
    """
    Фоновый процесс для обработки переводов из очереди
    """
    while True:
        try:
            # Получаем задачу из очереди
            task_id, text, source_lang, target_lang, style = translation_queue.get()
            logger.info(f"Обработка задачи {task_id}")
            
            # Выполняем перевод
            result = translate_text(text, source_lang, target_lang, style)
            
            # Сохраняем результат
            translation_results[task_id] = {
                'status': 'completed',
                'result': result
            }
            
            # Удаляем старые результаты (старше 1 часа)
            current_time = time.time()
            old_tasks = [task_id for task_id, task in translation_results.items() 
                        if task.get('timestamp', current_time) < current_time - 3600]
            for task_id in old_tasks:
                del translation_results[task_id]
                
        except Exception as e:
            logger.error(f"Ошибка в фоновом процессе: {str(e)}")
        finally:
            translation_queue.task_done()

# Запускаем фоновый процесс
translation_thread = Thread(target=process_translations, daemon=True)
translation_thread.start()

# Поддерживаемые языки и примеры фраз
SUPPORTED_LANGUAGES = {
    'ru': {
        'name': 'Русский',
        'examples': {
            'formal': [
                'Здравствуйте! Не могли бы Вы подсказать, как пройти к библиотеке?',
                'Позвольте поинтересоваться, как прошла Ваша встреча?',
                'Прошу прощения за беспокойство, не подскажете ли время?'
            ],
            'informal': [
                'Привет! Как дела?',
                'Слушай, что нового?',
                'Не подскажешь, который час?'
            ],
            'slang': [
                'Как жизнь, братан?',
                'Че как, нормально?',
                'Как сам?'
            ],
            'old_fashioned': [
                'Сударь, не соблаговолите ли указать путь к библиотеке?',
                'Как Ваше драгоценное здравие?',
                'Позвольте справиться о Вашем самочувствии'
            ]
        }
    },
    'en': {
        'name': 'English',
        'examples': {
            'formal': [
                'Good evening! Could you please tell me how to get to the library?',
                'May I inquire how your meeting went?',
                'I apologize for the interruption, but could you tell me the time?'
            ],
            'informal': [
                'Hey! How are you?',
                "What's new?",
                'What time is it?'
            ],
            'slang': [
                "How's it hanging?",
                "What's up, buddy?",
                "How you doing?"
            ],
            'old_fashioned': [
                'Pray tell, good sir, might you direct me to the library?',
                'How fare thee on this fine day?',
                'Might I inquire after your wellbeing?'
            ]
        }
    }
}

# Стили перевода и их описания
TRANSLATION_STYLES = {
    'formal': {
        'name': 'Деловой',
        'instruction': '''
Use formal business English:
- Use complete sentences with proper grammar
- Address people with respect (Sir, Madam, Mr., Ms.)
- Avoid contractions (use "cannot" instead of "can't")
- Use polite phrases ("would you be so kind", "please", "thank you")
- Maintain professional distance
- Use sophisticated business vocabulary
- Keep tone professional and courteous
- Use formal greetings and closings
'''
    },
    'informal': {
        'name': 'Разговорный',
        'instruction': '''
Use casual, friendly English:
- Use common expressions and simple words
- Contractions are fine (can't, don't, I'm)
- Be friendly but respectful
- Use direct questions and statements
- Keep sentences short and simple
- Use casual greetings (Hi, Hey)
- Add friendly fillers (well, you know, like)
- Keep tone warm and approachable
'''
    },
    'slang': {
        'name': 'Сленг',
        'instruction': '''
Используй современный молодежный сленг и неформальную речь:
- При переводе с русского на английский используй фразы типа: "Wanna", "Let's", "How about"
- При переводе с английского на русский используй фразы типа: "Го", "Погнали", "Давай"
- Короткие, рубленые фразы
- Свободная грамматика
- Дружеский, фамильярный тон
- Используй современный сленг и разговорные выражения
- Сохраняй направление перевода и контекст оригинального сообщения
- В романтическом контексте используй соответствующие выражения

Use modern casual language with slang:
- When translating from Russian to English use phrases like: "Wanna", "Let's", "How about"
- When translating from English to Russian use phrases like: "Го", "Погнали", "Давай"
- Short, punchy sentences
- Very relaxed grammar
- Friendly and familiar tone
- Use modern slang and expressions
- Maintain the translation direction and context of the original message
- In romantic context use appropriate expressions
'''
    },
    'old_fashioned': {
        'name': 'Классический',
        'instruction': '''
Use traditional, elegant English:
- Use formal, antiquated expressions
- Traditional forms of address (Sir, Madam, My good man)
- Complex sentence structures
- Elaborate politeness
- Use archaic words and phrases
- Maintain dignified, respectful tone
- Use classical literary expressions
- Keep style sophisticated and refined
'''
    }
}

def translate_text(text: str, source_lang: str, target_lang: str, style: str) -> Dict[str, Any]:
    """
    Выполняет перевод текста с использованием GigaChat API
    """
    logger.info(f"Начало перевода текста с {source_lang} на {target_lang} в стиле {style}")
    logger.info(f"Исходный текст: {text}")
    
    # Формируем промпт с учетом стиля
    style_instruction = TRANSLATION_STYLES[style]['instruction']
    
    # Добавляем примеры для конкретного стиля
    style_examples = SUPPORTED_LANGUAGES[source_lang]['examples'][style]
    target_examples = SUPPORTED_LANGUAGES[target_lang]['examples'][style]
    
    examples = []
    for i, (src, tgt) in enumerate(zip(style_examples[:2], target_examples[:2])):
        examples.extend([
            f"Example {i+1}:",
            f"Source: {src}",
            f"Target: {tgt}"
        ])
    examples_text = "\n".join(examples)
    
    prompt = f"""You are a professional translator. Your task is to translate the following text from {SUPPORTED_LANGUAGES[source_lang]['name']} to {SUPPORTED_LANGUAGES[target_lang]['name']} using the specified style. DO NOT ask questions, DO NOT add explanations, just translate the text.

Style instructions:
{style_instruction}

Here are some examples of translations in this style:
{examples_text}

Text to translate:
{text}

IMPORTANT: 
1. Return ONLY the translation itself
2. DO NOT ask questions about why this style was chosen
3. DO NOT add any explanations or comments
4. DO NOT add asterisks, quotes, or any other formatting
5. DO NOT suggest alternative translations
6. The response should contain only the translated text"""

    logger.info(f"Сформированный промпт: {prompt}")

    try:
        # Получаем токен доступа
        access_token = get_gigachat_token()
        
        # Выполняем перевод
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "RqUID": str(uuid.uuid4())
        }
        
        data = {
            "model": "GigaChat",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "top_p": 0.9,
            "n": 1,
            "stream": False
        }
        
        logger.info("Отправка запроса на перевод")
        logger.info(f"Данные запроса: {data}")
        
        response = requests.post(
            f"{GIGACHAT_API_URL}/chat/completions",
            headers=headers,
            json=data,
            verify=False
        )
        
        # Логируем ответ для отладки
        logger.info(f"Статус ответа: {response.status_code}")
        logger.info(f"Заголовки ответа: {response.headers}")
        logger.info(f"Тело ответа: {response.text}")
        
        response.raise_for_status()
        result = response.json()
        translated_text = result['choices'][0]['message']['content'].strip()
        
        logger.info(f"Получен перевод: {translated_text}")
        return {'translated_text': translated_text}
        
    except Exception as e:
        logger.error(f"Ошибка при переводе: {str(e)}")
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            logger.error(f"Тело ответа с ошибкой: {e.response.text}")
        return {'error': str(e)}

@app.route('/')
def index():
    # Преобразуем данные для отображения в шаблоне
    display_languages = {k: v['name'] for k, v in SUPPORTED_LANGUAGES.items()}
    # Передаем только имена стилей без инструкций и примеров
    display_styles = {k: v['name'] for k, v in TRANSLATION_STYLES.items()}
    return render_template('index.html',
                         languages=display_languages,
                         styles=display_styles)

@app.route('/translate', methods=['POST'])
def translate():
    start_time = time.time()
    logger.info("Получен новый запрос на перевод")
    
    data = request.get_json()
    logger.debug(f"Полученные данные: {data}")
    
    if not all(key in data for key in ['text', 'source_lang', 'target_lang', 'style']):
        logger.error("Отсутствуют обязательные параметры")
        return jsonify({'error': 'Missing required parameters'}), 400
    
    if data['source_lang'] not in SUPPORTED_LANGUAGES or data['target_lang'] not in SUPPORTED_LANGUAGES:
        logger.error(f"Неподдерживаемый язык: source={data['source_lang']}, target={data['target_lang']}")
        return jsonify({'error': 'Unsupported language'}), 400
    
    if data['style'] not in TRANSLATION_STYLES:
        logger.error(f"Неподдерживаемый стиль: {data['style']}")
        return jsonify({'error': 'Unsupported translation style'}), 400
    
    # Ограничиваем длину входного текста
    text = data['text']
    if len(text) > 1000:
        text = text[:1000]
        logger.warning(f"Входной текст обрезан до 1000 символов")
    
    # Создаем ID для задачи
    task_id = str(uuid.uuid4())
    
    # Добавляем задачу в очередь
    translation_queue.put((
        task_id,
        text,
        data['source_lang'],
        data['target_lang'],
        data['style']
    ))
    
    # Сохраняем информацию о задаче
    translation_results[task_id] = {
        'status': 'pending',
        'timestamp': time.time()
    }
    
    logger.info(f"Задача {task_id} добавлена в очередь")
    
    return jsonify({
        'task_id': task_id,
        'status': 'pending'
    })

@app.route('/status/<task_id>', methods=['GET'])
def get_translation_status(task_id):
    """
    Проверка статуса перевода
    """
    if task_id not in translation_results:
        return jsonify({'error': 'Task not found'}), 404
    
    task = translation_results[task_id]
    
    if task['status'] == 'completed':
        # Если перевод готов, возвращаем результат
        result = task['result']
        # Удаляем результат из хранилища
        del translation_results[task_id]
        return jsonify(result)
    
    # Если перевод еще выполняется
    return jsonify({
        'status': 'pending',
        'task_id': task_id
    })

if __name__ == '__main__':
    app.run(debug=True) 