from huggingface_hub import hf_hub_download
from PIL import Image
import os
import torch


# Цвета и русские названия для каждого класса блоков
LAYOUT_CLASSES = {
    "title":        {"color": "#E74C3C", "label": "Заголовок"},
    "plain text":   {"color": "#3498DB", "label": "Текст"},
    "abandon":      {"color": "#95A5A6", "label": "Разное"},
    "figure":       {"color": "#2ECC71", "label": "Изображение"},
    "figure_caption": {"color": "#27AE60", "label": "Подпись рис."},
    "table":        {"color": "#F39C12", "label": "Таблица"},
    "table_caption": {"color": "#E67E22", "label": "Подпись табл."},
    "table_footnote": {"color": "#D35400", "label": "Сноска табл."},
    "isolate_formula": {"color": "#9B59B6", "label": "Формула"},
    "formula_caption": {"color": "#8E44AD", "label": "Подпись форм."},
}

DEFAULT_COLOR = "#1ABC9C"


class LayoutConfig:
    """Конфигурация DocLayout-YOLO для анализа структуры документа"""

    def __init__(
            self,
            model_path: str = "./models/doclayout_yolo_docstructbench_imgsz1024.pt",
            conf_threshold: float = 0.25,
            iou_threshold: float = 0.45,
            img_size: int = 1024,
            use_gpu: bool = True,
    ):
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.device = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
        self.model = None
        self.load_error = None

    def download_model(self) -> bool:
        """Скачать модель с HuggingFace если её нет локально"""
        if os.path.exists(self.model_path):
            return True

        os.makedirs(os.path.dirname(self.model_path) or ".", exist_ok=True)
        print("Скачивание DocLayout-YOLO с HuggingFace...")
        try:
            path = hf_hub_download(
                repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
                filename="doclayout_yolo_docstructbench_imgsz1024.pt",
                local_dir=os.path.dirname(self.model_path) or "./models",
            )
            print(f"Модель скачана: {path}")
            return True
        except Exception as e:
            self.load_error = f"Ошибка скачивания: {e}"
            print(f"❌ {self.load_error}")
            return False

    def load_model(self) -> bool:
        """Загрузка модели"""
        try:
            from doclayout_yolo import YOLOv10
        except ImportError:
            self.load_error = "Установите: pip install doclayout-yolo"
            print(f"❌ {self.load_error}")
            return False

        if not self.download_model():
            return False

        try:
            print(f"Загрузка DocLayout-YOLO: {self.model_path} [{self.device}]")
            self.model = YOLOv10(self.model_path)
            print("✅ DocLayout-YOLO готов")
            self.load_error = None
            return True
        except Exception as e:
            self.load_error = str(e)
            print(f"❌ Ошибка загрузки: {e}")
            return False

    def detect(self, image: Image.Image) -> list[dict]:
        """
        Детектирование блоков на изображении.
        Возвращает список блоков:
        [
          {
            "class_name": "table",
            "label": "Таблица",
            "color": "#F39C12",
            "confidence": 0.91,
            "bbox": {"x": 10, "y": 20, "w": 300, "h": 150}  # пиксели оригинала
          }, ...
        ]
        """
        if self.model is None:
            raise RuntimeError("Модель не загружена")

        results = self.model.predict(
            image,
            imgsz=self.img_size,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False,
        )

        blocks = []
        if not results:
            return blocks

        result = results[0]
        names = result.names  # {0: 'title', 1: 'plain text', ...}

        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = names.get(cls_id, "unknown").lower()
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            meta = LAYOUT_CLASSES.get(cls_name, {"color": DEFAULT_COLOR, "label": cls_name.capitalize()})

            blocks.append({
                "class_name": cls_name,
                "label": meta["label"],
                "color": meta["color"],
                "confidence": round(conf, 3),
                "bbox": {
                    "x": round(x1),
                    "y": round(y1),
                    "w": round(x2 - x1),
                    "h": round(y2 - y1),
                }
            })

        # Сортируем сверху вниз, слева направо
        blocks.sort(key=lambda b: (b["bbox"]["y"], b["bbox"]["x"]))
        return blocks

    def get_model_info(self) -> dict:
        return {
            "engine": "DocLayout-YOLO",
            "model_path": self.model_path,
            "device": self.device,
            "is_loaded": self.model is not None,
            "load_error": self.load_error,
            "conf_threshold": self.conf_threshold,
            "iou_threshold": self.iou_threshold,
        }


# Глобальный экземпляр
layout_detector = LayoutConfig(
    model_path="./models/doclayout_yolo_docstructbench_imgsz1024.pt",
    conf_threshold=0.25,
    iou_threshold=0.45,
    img_size=1024,
    use_gpu=True,
)