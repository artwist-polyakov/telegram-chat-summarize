FROM python:3.10-slim

# Установка рабочей директории
WORKDIR /app

# Копирование requirements.txt
COPY requirements.txt /app/requirements.txt

# Установка зависимостей
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копирование остальной части проекта в рабочую директорию
COPY . /app/

# Запуск приложения
CMD ["python", "main.py"]