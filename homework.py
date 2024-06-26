import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv
from telegram import TelegramError

load_dotenv()

logger = logging.getLogger(__name__)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s, %(levelname)s, %(message)s')
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет наличие переменных окружения для работы программы."""
    missing_tokens = []
    if not PRACTICUM_TOKEN:
        missing_tokens.append('PRACTICUM_TOKEN')
    if not TELEGRAM_TOKEN:
        missing_tokens.append('TELEGRAM_TOKEN')
    if not TELEGRAM_CHAT_ID:
        missing_tokens.append('TELEGRAM_CHAT_ID')

    if missing_tokens:
        missing_tokens = ', '.join(missing_tokens)
        error_message = 'Missing required variables: {missing_tokens}'
        logger.critical(error_message)
        raise EnvironmentError(error_message)


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    logger.debug(f'Начало отправки сообщения в Telegram: {message}')
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение успешно отправлено в Telegram: {message}')
    except TelegramError as e:
        logger.error(f'Ошибка при отправке сообщения в Telegram: {e}')


def get_api_answer(timestamp):
    """Делает запрос к API для получения статусов домашних работ."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException as e:
        error_message = (
            f'Failed to connect to API at {ENDPOINT}'
            f'with parameters {params}. '
            'Ensure network connectivity and that the parameters are correct. '
            'Sensitive information such as authentication '
            'tokens has been omitted from this error.'
        )
        raise ConnectionError(error_message) from e
    if response.status_code != 200:
        raise ValueError(
            f'API returned non-200 status code: {response.status_code}')
    return response.json()


def check_response(response):
    """Проверяет ответ API на корректность структуры данных.
    И уточняет тип некорректных данных.
    """
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API не является словарем, получен тип: {type(response)}')
    homeworks = response.get('homeworks')
    if homeworks is None:
        raise KeyError('В ответе API отсутствует ключ "homeworks"')
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Домашние работы не представлены в виде списка, получен тип: '
            f'{type(homeworks)}')
    current_date = response.get('current_date')
    if current_date is None:
        raise KeyError('В ответе API отсутствует ключ "current_date"')
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

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except EnvironmentError as e:
        logger.critical(e)
        sys.exit(1)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                homework = homeworks[0]
                message = parse_status(homework)
                send_message(bot, message)
                last_error_message = None
            else:
                logger.debug('No new homework statuses found')
            timestamp = response.get('current_date', timestamp)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != last_error_message:
                send_message(bot, message)
                last_error_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
