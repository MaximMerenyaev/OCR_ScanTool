import pytesseract
from PIL import Image
import os
import sys


class TesseractConfig:
    """Конфигурация для Tesseract OCR"""

    def __init__(
            self,
            tesseract_path: str = None,
            language: str = "rus",
            psm: int = 3,
            oem: int = 3,
            config_extra: str = ""
    ):
        """
        Инициализация конфигурации Tesseract

        Args:
            tesseract_path: Путь к исполняемому файлу tesseract.exe
                           (для Windows, если не в PATH)
            language: Код языка ('rus', 'eng', 'rus+eng')
            psm: Page Segmentation Mode (0-14)
            oem: OCR Engine Mode (0-3)
            config_extra: Дополнительные параметры конфигурации
        """
        # Настройка пути к Tesseract
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        elif sys.platform == "win32":
            # Автопоиск стандартных путей на Windows
            default_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                r".\Tesseract-OCR\tesseract.exe",
            ]
            for path in default_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    print(f"Tesseract найден: {path}")
                    break

        self.language = language
        self.psm = psm
        self.oem = oem
        self.config_extra = config_extra

        self._check_installation()

    def _check_installation(self):
        """Проверка установки Tesseract"""
        try:
            version = pytesseract.get_tesseract_version()
            print(f"Tesseract version: {version}")

            # Проверка языков
            langs = pytesseract.get_languages()
            print(f"Доступные языки: {langs}")

            if self.language not in langs and self.language != "eng":
                print(f"ВНИМАНИЕ: Язык '{self.language}' может быть не установлен")

        except Exception as e:
            print(f"Ошибка проверки Tesseract: {e}")
            print("Убедитесь, что Tesseract установлен и добавлен в PATH")

    def ocr(self, image: Image.Image, language: str = None) -> str:
        """
        Распознавание текста из изображения

        Args:
            image: PIL Image объект
            language: Код языка (переопределяет настройку по умолчанию)

        Returns:
            Распознанный текст
        """
        lang = language or self.language

        # Формирование конфигурации
        config = f"--psm {self.psm} --oem {self.oem}"
        if self.config_extra:
            config += f" {self.config_extra}"

        try:
            text = pytesseract.image_to_string(
                image,
                lang=lang,
                config=config
            )
            return text.strip()
        except pytesseract.TesseractNotFoundError:
            raise RuntimeError(
                "Tesseract не найден. Установите его: "
                "https://github.com/UB-Mannheim/tesseract/wiki"
            )
        except Exception as e:
            raise RuntimeError(f"Ошибка OCR: {e}")

    def get_image_data(self, image: Image.Image, language: str = None) -> dict:
        """
        Получение детальной информации об распознавании

        Returns:
            dict с данными: текст, блоки, уверенность и т.д.
        """
        lang = language or self.language

        config = f"--psm {self.psm} --oem {self.oem}"
        if self.config_extra:
            config += f" {self.config_extra}"

        return pytesseract.image_to_data(
            image,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT
        )

    def get_model_info(self) -> dict:
        """Информация о конфигурации"""
        try:
            version = str(pytesseract.get_tesseract_version())
        except Exception:
            version = "unknown"

        return {
            "engine": "Tesseract OCR",
            "version": version,
            "language": self.language,
            "psm": self.psm,
            "oem": self.oem,
            "config_extra": self.config_extra,
            "tesseract_path": pytesseract.pytesseract.tesseract_cmd
        }

    def get_available_languages(self) -> list:
        """Получение списка доступных языков"""
        try:
            return pytesseract.get_languages()
        except Exception:
            return []


# Глобальный экземпляр с настройками по умолчанию
tesseract_ocr = TesseractConfig(
    tesseract_path=None,  # Автопоиск
    language="rus",
    psm=3,  # Fully automatic page segmentation, but no OSD
    oem=3,  # Default, based on what is available
    config_extra=""
)