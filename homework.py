import logging
import os
import sys
import time
import requests
import telegram

from dotenv import load_dotenv

load_dotenv()

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(stream_handler)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s, %(levelname)s, %(message)s')
logger = logging.getLogger(__name__)


PRACTICUM_TOKEN = (
    'y0_AgAAAABwOAJIAAYckQAAAAD8G0SKAADH7acoGXFHppWDgaU5dJrUAKAeDw')
TELEGRAM_TOKEN = '7012715028:AAEthinu8RGPzOnGo5S-ZmglHl7tMht-qYs'
TELEGRAM_CHAT_ID = 5039839197

RETRY_PERIOD = 6
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

last_error_message = None
last_error_time = 0


def check_tokens():
    """
    Проверяет наличие необходимых переменных окружения для работы программы.
    Переменные окружения, которые проверяются: PRACTICUM_TOKEN,
    TELELEGRAM_TOKEN, TELEGRAM_CHAT_ID.
    """
    missing_tokens = []
    if not PRACTICUM_TOKEN:
        missing_tokens.append('PRACTICUM_TOKEN')
    if not TELEGRAM_TOKEN:
        missing_tokens.append('TELEGRAM_TOKEN')
    if not TELEGRAM_CHAT_ID:
        missing_tokens.append('TELEGRAM_CHAT_ID')

    if missing_tokens:
        for token in missing_tokens:
            logger.critical(f'Missing required variable: {token}')
        return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    try:
        bot.send_message(chat_id=chat_id, text=message)
        logging.debug(f'Сообщение успешно отправлено в Telegram: {message}')
    except Exception as e:
        logging.error(f'Ошибка при отправке сообщения в Telegram: {e}')


def get_api_answer(timestamp):
    """Делает запрос к API для получения статусов домашних работ."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
        # Проверка статуса ответа
        if response.status_code != 200:
            # Логирование ошибки, если статус ответа не равен 200
            logger.error(
                f'API returned non-200 status code: {response.status_code}')
            # Генерация исключения, чтобы уведомить вызывающий код об ошибке
            raise Exception(
                f'API returned non-200 status code: {response.status_code}')
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f'API returned non-200 status code: {e}')
        return {'error': 'API returned non-200 status code', 'details': str(e)}
    except requests.RequestException as e:
        logger.error(f'API request error: {e}')
        return {'error': 'API request error', 'details': str(e)}


def check_response(response):
    """Проверяет ответ API на корректность структуры данных."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не является словарем')
    homeworks = response.get('homeworks')
    if homeworks is None:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')
    if not isinstance(homeworks, list):
        raise TypeError('Домашние работы не представлены в виде списка')
    return homeworks


def parse_status(homework):
    """
    Извлекает статус конкретной домашней работы.
    И формирует сообщение о ее статусе.
    """
    if 'homework_name' not in homework:
        raise KeyError(
            'В информации о домашней работе отсутствует ключ "homework_name"')
    if 'status' not in homework:
        raise KeyError(
            'В информации о домашней работе отсутствует ключ "status"')

    homework_name = homework['homework_name']
    status = homework.get('status')

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус домашней работы: {status}')

    verdict = HOMEWORK_VERDICTS.get(status, 'Неизвестный статус работы')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical(
            'One of the required environment variables is missing')
        sys.exit(1)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                for homework in homeworks:
                    message = parse_status(homework)
                    send_message(bot, message)
            timestamp = response.get('current_date', timestamp)
        except requests.exceptions.HTTPError as e:
            logger.error(f'Error fetching homework status: {e}')
            send_message(bot, 'Произошла ошибка при получении данных от API.'
                         'Попробуем снова через некоторое время.')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
