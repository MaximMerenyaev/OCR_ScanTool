"""
Модуль анализа текста:
  - Статистика (слова, предложения, читаемость)
  - Ключевые слова (TF на леммах через pymorphy3)
  - Именованные сущности — NER (natasha)
  - Тональность (rubert-tiny-sentiment-balanced)
"""

import re
import os
from collections import Counter


# ── Стоп-слова ───────────────────────────────────────────────
STOPWORDS = {
    "и","в","во","не","что","он","на","я","с","со","как","а","то","все","она",
    "так","его","но","да","ты","к","у","же","вы","за","бы","по","только","ее",
    "мне","было","вот","от","меня","еще","нет","о","из","ему","теперь","когда",
    "даже","ну","вдруг","ли","если","уже","или","ни","быть","был","него","до",
    "вас","нибудь","опять","уж","вам","ведь","там","потом","себя","ничего","ей",
    "может","они","тут","где","есть","надо","ней","для","мы","тебя","их","чем",
    "была","сам","чтоб","без","будто","чего","раз","тоже","себе","под","будет",
    "ж","тогда","кто","этот","того","потому","этого","какой","этом","перед","иногда",
    "лучше","чуть","том","нельзя","такой","им","более","всегда","конечно","всю",
    "между","при","об","через","это","эту","этой","этих","эти","та","те","тех",
    "тем","ту","свою","своей","своих","свои","своего","своем","своему","своими",
    "также","около","можно","всего","здесь","один","почти","мой","чтобы","нас",
    "про","очень","еще","уже","при","из","со","по","до","за","на","в","к","с",
    "об","не","ни","же","ли","бы","во","над","перед","после","согласно","для",
    "что","который","которая","которое","которые","этот","эта","такой","такая",
}


def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def tokenize_words(text: str) -> list:
    return re.findall(r'[а-яёА-ЯЁa-zA-Z]{2,}', text)


def tokenize_sentences(text: str) -> list:
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s for s in parts if len(s.strip()) > 3]


def syllable_count_ru(word: str) -> int:
    return len(re.findall(r'[аеёиоуыэюяАЕЁИОУЫЭЮЯ]', word))


# ─────────────────────────────────────────────────────────────

class TextAnalysisConfig:

    def __init__(
            self,
            sentiment_model_path: str = "./models/rubert-tiny-sentiment",
            use_gpu: bool = True,
            top_keywords: int = 15,
            top_entities: int = 30,
    ):
        self.sentiment_model_path = sentiment_model_path
        self.use_gpu = use_gpu
        self.top_keywords = top_keywords
        self.top_entities = top_entities

        self.morph = None
        self.natasha_models = None
        self.sentiment_pipeline = None
        self.load_error = {}

    # ── Загрузка ─────────────────────────────────────────────

    def load_morph(self):
        try:
            import pymorphy3
            self.morph = pymorphy3.MorphAnalyzer()
            print("OK: pymorphy3")
        except ImportError:
            self.load_error['morph'] = "pip install pymorphy3"
            print("WARNING: pymorphy3 не установлен")

    def load_natasha(self):
        try:
            from natasha import (
                Segmenter, MorphVocab, NewsEmbedding,
                NewsMorphTagger, NewsNERTagger,
                DatesExtractor, MoneyExtractor, Doc,
            )
            emb = NewsEmbedding()
            mv  = MorphVocab()
            self.natasha_models = {
                'segmenter':  Segmenter(),
                'morph_vocab': mv,
                'morph_tagger': NewsMorphTagger(emb),
                'ner_tagger':   NewsNERTagger(emb),
                'dates':  DatesExtractor(mv),
                'money':  MoneyExtractor(mv),
                'Doc':    Doc,
            }
            print("OK: natasha")
        except ImportError:
            self.load_error['natasha'] = "pip install natasha"
            print("WARNING: natasha не установлена")
        except Exception as e:
            self.load_error['natasha'] = str(e)
            print(f"WARNING: natasha: {e}")

    def load_sentiment(self):
        try:
            import torch
            from transformers import pipeline

            device = 0 if (self.use_gpu and torch.cuda.is_available()) else -1
            model_id = (
                self.sentiment_model_path
                if os.path.exists(self.sentiment_model_path)
                else "cointegrated/rubert-tiny-sentiment-balanced"
            )
            self.sentiment_pipeline = pipeline(
                "text-classification",
                model=model_id,
                tokenizer=model_id,
                device=device,
                truncation=True,
                max_length=512,
            )
            print("OK: sentiment модель")
        except Exception as e:
            self.load_error['sentiment'] = str(e)
            print(f"WARNING: sentiment: {e}")

    def load_all(self):
        print("=" * 40)
        print("ЗАГРУЗКА TEXT ANALYSIS")
        print("=" * 40)
        self.load_morph()
        self.load_natasha()
        self.load_sentiment()
        print("=" * 40)

    # ── 1. Статистика ────────────────────────────────────────

    def compute_statistics(self, text: str) -> dict:
        words     = tokenize_words(text)
        sentences = tokenize_sentences(text)
        word_count  = len(words)
        sent_count  = max(len(sentences), 1)
        unique_words = len(set(w.lower() for w in words))
        avg_word_len = round(sum(len(w) for w in words) / max(word_count, 1), 1)
        avg_sent_len = round(word_count / sent_count, 1)
        lexical_div  = round(unique_words / max(word_count, 1) * 100, 1)

        total_syl = sum(syllable_count_ru(w) for w in words)
        flesch = 206.835 - 1.3 * (word_count / sent_count) - 60.1 * (total_syl / max(word_count, 1))
        flesch = round(max(0.0, min(100.0, flesch)), 1)

        if flesch >= 70:
            r_label, r_color = "Легко читается", "#10B981"
        elif flesch >= 50:
            r_label, r_color = "Средняя сложность", "#F59E0B"
        elif flesch >= 30:
            r_label, r_color = "Сложный текст", "#EF4444"
        else:
            r_label, r_color = "Очень сложный", "#7C3AED"

        freq = Counter(
            w.lower() for w in words
            if w.lower() not in STOPWORDS and len(w) > 2
        )
        top_words = [{"word": w, "count": c} for w, c in freq.most_common(10)]

        return {
            "chars": len(text),
            "chars_no_spaces": len(text.replace(' ', '')),
            "words": word_count,
            "sentences": sent_count,
            "unique_words": unique_words,
            "avg_word_length": avg_word_len,
            "avg_sentence_length": avg_sent_len,
            "lexical_diversity": lexical_div,
            "readability_score": flesch,
            "readability_label": r_label,
            "readability_color": r_color,
            "top_words": top_words,
        }

    # ── 2. Ключевые слова ────────────────────────────────────

    def extract_keywords(self, text: str) -> list:
        words = [
            w.lower() for w in tokenize_words(text)
            if w.lower() not in STOPWORDS and len(w) > 2
        ]
        if not words:
            return []

        if self.morph:
            lemmas = [self.morph.parse(w)[0].normal_form for w in words]
        else:
            lemmas = words

        freq  = Counter(lemmas)
        total = max(sum(freq.values()), 1)

        return [
            {"word": lem, "count": cnt, "score": round(cnt / total * 100, 2)}
            for lem, cnt in freq.most_common(self.top_keywords)
            if cnt >= 2
        ]

    # ── 3. NER ───────────────────────────────────────────────

    def extract_entities(self, text: str) -> dict:
        result = {"PER": [], "ORG": [], "LOC": [], "DATE": [], "MONEY": []}
        if not self.natasha_models:
            return result
        try:
            nm  = self.natasha_models
            doc = nm['Doc'](text[:6000])
            doc.segment(nm['segmenter'])
            doc.tag_morph(nm['morph_tagger'])
            doc.tag_ner(nm['ner_tagger'])

            seen = set()
            for span in doc.spans:
                tag  = span.type
                norm = span.text.strip()
                if tag in result and norm not in seen and len(norm) > 1:
                    result[tag].append(norm)
                    seen.add(norm)

            for match in nm['dates'].findall(text[:6000]):
                val = str(match.fact)
                if val not in result['DATE']:
                    result['DATE'].append(val)

            for match in nm['money'].findall(text[:6000]):
                val = str(match.fact)
                if val not in result['MONEY']:
                    result['MONEY'].append(val)

        except Exception as e:
            print(f"NER error: {e}")

        for key in result:
            result[key] = result[key][:self.top_entities]
        return result

    # ── 4. Тональность ──────────────────────────────────────

    def analyze_sentiment(self, text: str) -> dict:
        if not self.sentiment_pipeline:
            return {
                "label": "unavailable",
                "label_ru": "Недоступно",
                "score": 0.0,
                "color": "#6B7280",
                "error": self.load_error.get('sentiment', ''),
            }
        try:
            res   = self.sentiment_pipeline(text[:1000])[0]
            label = res['label'].upper()
            mapping = {
                "POSITIVE": ("positive", "Позитивный", "#10B981"),
                "NEUTRAL":  ("neutral",  "Нейтральный", "#6B7280"),
                "NEGATIVE": ("negative", "Негативный",  "#EF4444"),
                "LABEL_0":  ("negative", "Негативный",  "#EF4444"),
                "LABEL_1":  ("neutral",  "Нейтральный", "#6B7280"),
                "LABEL_2":  ("positive", "Позитивный",  "#10B981"),
            }
            key, label_ru, color = mapping.get(label, ("neutral", "Нейтральный", "#6B7280"))
            return {"label": key, "label_ru": label_ru, "score": round(res['score'], 3), "color": color}
        except Exception as e:
            return {"label": "error", "label_ru": "Ошибка", "score": 0.0, "color": "#6B7280", "error": str(e)}

    # ── Главный метод ────────────────────────────────────────

    def analyze(self, text: str) -> dict:
        text = clean_text(text)
        if not text or len(text.split()) < 3:
            return {"error": "Текст слишком короткий (минимум 3 слова)"}
        return {
            "statistics": self.compute_statistics(text),
            "keywords":   self.extract_keywords(text),
            "entities":   self.extract_entities(text),
            "sentiment":  self.analyze_sentiment(text),
        }

    def get_model_info(self) -> dict:
        return {
            "morph_loaded":     self.morph is not None,
            "natasha_loaded":   self.natasha_models is not None,
            "sentiment_loaded": self.sentiment_pipeline is not None,
            "errors":           self.load_error,
        }


# Глобальный экземпляр
text_analyzer = TextAnalysisConfig(
    sentiment_model_path="./models/rubert-tiny-sentiment",
    use_gpu=True,
    top_keywords=15,
    top_entities=30,
)