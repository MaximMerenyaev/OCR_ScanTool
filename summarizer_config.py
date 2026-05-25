from transformers import AutoTokenizer, T5ForConditionalGeneration
import os
import torch


class SummarizerConfig:
    """Конфигурация модели суммаризации на основе RuT5"""

    def __init__(
            self,
            model_path: str = "./models/rut5_base_headline_gen_telegram",
            max_input_length: int = 600,
            max_summary_length: int = 150,
            min_summary_length: int = 30,
            num_beams: int = 4,
            length_penalty: float = 2.0,
            repetition_penalty: float = 1.0,
            early_stopping: bool = False,
            no_repeat_ngram_size: int = 0,
            use_gpu: bool = True,
            use_half_precision: bool = True
    ):
        self.model_path = model_path
        self.max_input_length = max_input_length
        self.max_summary_length = max_summary_length
        self.min_summary_length = min_summary_length
        self.num_beams = num_beams
        self.length_penalty = length_penalty
        self.repetition_penalty = repetition_penalty
        self.early_stopping = early_stopping
        self.no_repeat_ngram_size = no_repeat_ngram_size
        self.use_gpu = use_gpu
        self.use_half_precision = use_half_precision

        self.device = self._select_device()
        self.tokenizer = None
        self.model = None
        self.load_error = None

    def _select_device(self) -> str:
        if not self.use_gpu:
            return "cpu"

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            print(f"GPU: {gpu_name} ({gpu_memory:.1f} GB)")
            return "cuda"

        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            print("Apple Silicon (MPS)")
            return "mps"

        print("CPU")
        return "cpu"

    def load_model(self):
        """Загрузка модели и токенизатора"""
        print(f"\nПроверка пути к модели: {self.model_path}")
        print(f"Путь существует: {os.path.exists(self.model_path)}")

        if not os.path.exists(self.model_path):
            error_msg = f"Модель не найдена: {self.model_path}"
            print(f"❌ {error_msg}")

            if os.path.exists("./models"):
                print(f"\nСодержимое ./models/:")
                for item in os.listdir("./models"):
                    print(f"  - {item}")

            self.load_error = error_msg
            return False

        print(f"\nЗагрузка модели: {self.model_path}")
        print(f"Устройство: {self.device}")

        try:
            print("Загрузка токенизатора...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            print("✅ Токенизатор загружен")

            dtype = torch.float16 if (self.use_half_precision and self.device == "cuda") else torch.float32
            print(f"Тип данных: {'float16' if dtype == torch.float16 else 'float32'}")

            print("Загрузка модели...")
            self.model = T5ForConditionalGeneration.from_pretrained(
                self.model_path,
                torch_dtype=dtype if self.device == "cuda" else torch.float32,
                low_cpu_mem_usage=True
            )

            self.model.to(self.device)
            self.model.eval()

            num_params = sum(p.numel() for p in self.model.parameters())
            print(f"✅ Модель загружена! Параметры: {num_params:,}")

            self.load_error = None
            return True

        except Exception as e:
            error_msg = f"Ошибка загрузки: {str(e)}"
            print(f"❌ {error_msg}")
            self.load_error = error_msg
            return False

    def summarize(self, text: str, use_hf_params: bool = True) -> str:
        if self.model is None or self.tokenizer is None:
            if self.load_error:
                raise RuntimeError(f"Модель не загружена: {self.load_error}")
            else:
                raise RuntimeError("Модель не загружена. Вызовите load_model()")

        try:
            inputs = self.tokenizer(
                text,
                max_length=self.max_input_length,
                truncation=True,
                return_tensors="pt"
            ).to(self.device)

            with torch.no_grad():
                if use_hf_params:
                    output_ids = self.model.generate(
                        input_ids=inputs["input_ids"],
                        max_length=self.max_summary_length,
                        min_length=self.min_summary_length,
                        num_beams=self.num_beams,
                        length_penalty=self.length_penalty,
                        early_stopping=self.early_stopping,
                    )
                else:
                    output_ids = self.model.generate(
                        input_ids=inputs["input_ids"]
                    )

            output_ids = output_ids[0]
            summary = self.tokenizer.decode(output_ids, skip_special_tokens=True)
            return summary.strip()

        except Exception as e:
            raise RuntimeError(f"Ошибка суммаризации: {str(e)}")

    def get_model_info(self) -> dict:
        info = {
            "model_path": self.model_path,
            "device": self.device,
            "is_loaded": self.model is not None,
            "load_error": self.load_error,
            "parameters": {
                "max_input_length": self.max_input_length,
                "max_summary_length": self.max_summary_length,
                "min_summary_length": self.min_summary_length,
                "num_beams": self.num_beams,
                "length_penalty": self.length_penalty,
                "repetition_penalty": self.repetition_penalty,
                "early_stopping": self.early_stopping,
            }
        }

        if self.device == "cuda" and torch.cuda.is_available():
            info["gpu_info"] = {
                "name": torch.cuda.get_device_name(0),
                "memory_allocated_mb": torch.cuda.memory_allocated() / 1024 ** 2,
            }

        return info


# Глобальный экземпляр с правильным путём к RuT5
summarizer = SummarizerConfig(
    model_path="./models/rut5_base_headline_gen_telegram",  # ← ИСПРАВЛЕНО
    max_input_length=600,
    max_summary_length=150,
    min_summary_length=30,
    num_beams=4,
    length_penalty=2.0,
    repetition_penalty=1.0,
    early_stopping=False,
    no_repeat_ngram_size=0,
    use_gpu=True,
    use_half_precision=True
)