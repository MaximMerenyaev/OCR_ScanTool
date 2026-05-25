"""
Постобработка OCR-текста:
  - Нормализация пробелов и переносов строк
  - Склейка перенесённых слов (при- / вет → привет)
  - Нормализация пунктуации
  - Удаление артефактов сканирования
  - Восстановление абзацев
"""

import re


def fix_hyphenation(text: str) -> str:
    """Склейка слов разбитых переносом строки: 'при-\nвет' → 'привет'"""
    # Перенос с дефисом в конце строки
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    return text


def normalize_whitespace(text: str) -> str:
    """Нормализация пробелов внутри строк"""
    lines = text.split('\n')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    return '\n'.join(lines)


def fix_punctuation(text: str) -> str:
    """Нормализация пунктуации"""
    # Пробел перед знаком препинания
    text = re.sub(r'\s+([.,!?;:»)])', r'\1', text)
    # Пробел после открывающей скобки/кавычки
    text = re.sub(r'([(«])\s+', r'\1', text)
    # Двойные пробелы после знаков препинания → один
    text = re.sub(r'([.,!?;:])\s{2,}', r'\1 ', text)
    # Пробел перед знаком % и №
    text = re.sub(r'(\d)\s+([%№])', r'\1\2', text)
    return text


def fix_ocr_artifacts(text: str) -> str:
    """Удаление типичных артефактов сканирования"""
    # Строки из одних спецсимволов / мусора
    lines = text.split('\n')
    clean = []
    for line in lines:
        stripped = line.strip()
        # Строка только из спецсимволов (не буквы/цифры)
        if stripped and not re.search(r'[а-яёА-ЯЁa-zA-Z0-9]', stripped):
            continue
        clean.append(line)
    return '\n'.join(clean)


def restore_paragraphs(text: str) -> str:
    """
    Восстановление абзацев:
    Одиночные переносы строки внутри абзаца объединяются,
    двойные — сохраняются как разделители абзацев.
    """
    # Нормализуем: 3+ пустых строки → 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Разбиваем на абзацы по двойным переносам
    paragraphs = re.split(r'\n{2,}', text)
    result = []

    for para in paragraphs:
        lines = para.split('\n')
        merged_lines = []
        buffer = ''

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if buffer:
                    merged_lines.append(buffer)
                    buffer = ''
                continue

            # Признаки что строка является заголовком или отдельной строкой:
            # — короткая строка (< 40 симв)
            # — заканчивается на знак препинания завершающий предложение
            # — начинается с цифры (нумерованный список)
            is_standalone = (
                len(stripped) < 40 or
                stripped[-1] in '.!?:' or
                re.match(r'^\d+[.)]\s', stripped) or
                re.match(r'^[—•\-]\s', stripped)
            )

            if is_standalone:
                if buffer:
                    merged_lines.append(buffer)
                    buffer = ''
                merged_lines.append(stripped)
            else:
                # Склеиваем строки внутри абзаца
                if buffer:
                    # Если предыдущая строка не заканчивалась на знак препинания
                    # или дефис — добавляем пробел
                    if buffer[-1] not in '-—':
                        buffer += ' ' + stripped
                    else:
                        buffer = buffer.rstrip('-—') + stripped
                else:
                    buffer = stripped

        if buffer:
            merged_lines.append(buffer)

        if merged_lines:
            result.append('\n'.join(merged_lines))

    return '\n\n'.join(result)


def fix_common_ocr_errors(text: str) -> str:
    """
    Исправление типичных OCR-ошибок для русского текста.
    Только однозначные замены чтобы не испортить текст.
    """
    # Латинские буквы похожие на кириллицу в русском контексте
    # (только если окружены кириллицей)
    replacements = [
        # о латинское → о кириллическое между кириллическими буквами
        (r'(?<=[а-яёА-ЯЁ])o(?=[а-яёА-ЯЁ])', 'о'),
        (r'(?<=[а-яёА-ЯЁ])e(?=[а-яёА-ЯЁ])', 'е'),
        (r'(?<=[а-яёА-ЯЁ])c(?=[а-яёА-ЯЁ])', 'с'),
        (r'(?<=[а-яёА-ЯЁ])p(?=[а-яёА-ЯЁ])', 'р'),
        (r'(?<=[а-яёА-ЯЁ])a(?=[а-яёА-ЯЁ])', 'а'),
        (r'(?<=[а-яёА-ЯЁ])x(?=[а-яёА-ЯЁ])', 'х'),
        # Буква ё часто распознаётся как е — не трогаем (слишком много false positive)
        # 0 vs О в начале русского слова
        (r'\b0(?=[а-яёА-ЯЁ])', 'О'),
        # l vs 1 — только в числах (не трогаем)
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def postprocess(text: str, engine: str = "tesseract") -> str:
    """
    Главная функция постобработки.

    Args:
        text: Сырой OCR-текст
        engine: 'tesseract' или 'vlm' — влияет на набор применяемых правил
    """
    if not text or not text.strip():
        return text

    text = fix_hyphenation(text)
    text = normalize_whitespace(text)
    text = fix_ocr_artifacts(text)
    text = fix_common_ocr_errors(text)
    text = fix_punctuation(text)
    text = restore_paragraphs(text)

    return text.strip()