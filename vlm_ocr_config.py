from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info
import torch
import os
from PIL import Image
import base64
import io


class VLMOCRConfig:
    """Конфигурация для VLM OCR модели Qwen2-VL"""

    def __init__(
            self,
            model_path: str = "./models/Qwen2-VL-OCR-2B-Instruct",
            use_gpu: bool = True,
            use_half_precision: bool = True,
            max_new_tokens: int = 512,
            temperature: float = 0.0,
            do_sample: bool = False,
            top_p: float = 0.9,
            language: str = "rus"
    ):
        self.model_path = model_path
        self.use_gpu = use_gpu
        self.use_half_precision = use_half_precision
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.do_sample = do_sample
        self.top_p = top_p
        self.language = language

        self.langs_dict = {
            "rus": "Russian",
            "eng": "English",
            "deu": "German",
            "fra": "French",
            "spa": "Spanish",
            "ita": "Italian",
            "chi": "Chinese",
            "jpn": "Japanese",
            "kor": "Korean"
        }

        self.device = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
        self.processor = None
        self.model = None

    def load_model(self):
        """Загрузка модели и процессора"""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Модель не найдена: {self.model_path}")

        print(f"Загрузка VLM OCR модели: {self.model_path}")
        print(f"Устройство: {self.device}")

        try:
            if self.use_half_precision and self.device == "cuda":
                dtype = torch.float16
                print("Использование float16")
            else:
                dtype = torch.float32
                print("Использование float32")

            print("Загрузка модели...")
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.model_path,
                torch_dtype=dtype,
                device_map="auto" if self.device == "cuda" else None,
                trust_remote_code=True
            )

            if self.device != "cuda":
                self.model.to(self.device)

            self.model.eval()

            print("Загрузка процессора...")
            self.processor = AutoProcessor.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )

            num_params = sum(p.numel() for p in self.model.parameters())
            print(f"Модель загружена! Параметры: {num_params:,}")

            return True

        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _image_to_base64(self, image: Image.Image) -> str:
        """Конвертация PIL Image в base64 строку"""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    def ocr(self, image: Image.Image, language: str = None, prompt: str = None, text_mode: str = "printed") -> str:
        """
        Распознавание текста из изображения

        Args:
            image: PIL Image объект
            language: Код языка
            prompt: Кастомный промпт (если None, используется стандартный)
            text_mode: 'printed' — печатный текст, 'handwritten' — рукописный
        """
        if self.model is None or self.processor is None:
            raise RuntimeError("Модель не загружена")

        lang = language or self.language
        lang_name = self.langs_dict.get(lang, "Russian")

        if prompt is None:
            if text_mode == "handwritten":
                prompt = (
                    f"Carefully transcribe ALL handwritten text from this image in {lang_name}.\n"
                    "Preserve the original structure, line breaks and paragraph spacing.\n"
                    "Output ONLY the transcribed text. No explanations, no coordinates, no special tokens."
                )
            else:
                prompt = (
                    f"Read all the text in this image and write it out.\n"
                    f"Language: {lang_name}.\n"
                    "Output only the text. Keep all line breaks. No extra words."
                )

        image_base64 = self._image_to_base64(image)
        image_data_url = f"data:image/png;base64,{image_base64}"

        # Для печатного текста добавляем system-промпт — это критично для OCR модели
        if text_mode == "printed":
            messages = [
                {
                    "role": "system",
                    "content": "You are an OCR assistant. Your only job is to read and output text from images exactly as it appears."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image_data_url},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        else:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image_data_url},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

        # Параметры генерации: для печатного используем небольшое sampling
        # чтобы модель не застревала на пустом выводе
        gen_kwargs = dict(
            max_new_tokens=self.max_new_tokens,
        )
        if text_mode == "printed":
            gen_kwargs.update(
                temperature=0.1,
                do_sample=True,
                top_p=0.95,
                repetition_penalty=1.1,
            )
        else:
            gen_kwargs.update(
                temperature=self.temperature,
                do_sample=self.do_sample,
                top_p=self.top_p,
            )

        result = self._run_generate(messages, gen_kwargs)

        # Fallback: если модель вернула пустоту — пробуем упрощённый промпт
        if not result.strip() and text_mode == "printed":
            fallback_messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image_data_url},
                        {"type": "text", "text": "What text do you see in this image? Write it out."}
                    ]
                }
            ]
            result = self._run_generate(fallback_messages, gen_kwargs)

        result = self._strip_grounding_tokens(result)
        return result.strip()

    def _run_generate(self, messages: list, gen_kwargs: dict) -> str:
        """Вспомогательный метод — применяет шаблон, запускает generate, декодирует"""
        text_prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            generated_ids = self.model.generate(**inputs, **gen_kwargs)

        generated_ids_trimmed = [
            out_ids[len(in_ids):]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return output_text[0] if output_text else ""

    @staticmethod
    def _strip_grounding_tokens(text: str) -> str:
        """Удаляет токены bounding box если модель всё равно их вернула.
        Пример: <|box_start|>(23,10),(980,970)<|box_end|> → ''
        """
        import re
        # Убираем box-токены и координаты
        text = re.sub(r'<\|box_start\|>.*?<\|box_end\|>', '', text, flags=re.DOTALL)
        # Убираем одиночные im_end/im_start токены если skip_special_tokens их пропустил
        text = re.sub(r'<\|im_end\|>|<\|im_start\|>', '', text)
        # Убираем строки содержащие только координаты вида (N,N),(N,N)
        text = re.sub(r'^\s*\(\d+,\d+\),\(\d+,\d+\)\s*$', '', text, flags=re.MULTILINE)
        return text.strip()

    def get_model_info(self) -> dict:
        info = {
            "model_path": self.model_path,
            "device": self.device,
            "is_loaded": self.model is not None,
            "language": self.language,
        }

        if self.device == "cuda" and torch.cuda.is_available():
            info["gpu_info"] = {
                "name": torch.cuda.get_device_name(0),
                "memory_allocated_mb": torch.cuda.memory_allocated() / 1024 ** 2,
            }

        return info


# Глобальный экземпляр
vlm_ocr = VLMOCRConfig(
    model_path="./models/Qwen2-VL-OCR-2B-Instruct",
    use_gpu=True,
    use_half_precision=True,
    max_new_tokens=2048,
    temperature=0.0,
    do_sample=False,
    language="rus"
)