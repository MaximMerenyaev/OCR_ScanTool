from fastapi import FastAPI, UploadFile, File, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import json as json_module
import asyncio
import concurrent.futures
import base64
import io
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from PIL import Image
from summarizer_config import summarizer
from vlm_ocr_config import vlm_ocr
from tesseract_config import tesseract_ocr
from layout_config import layout_detector
from text_analysis_config import text_analyzer
from postprocessing import postprocess
from img_preprocess_utils import preprocess_for_ocr
from pdf_processor import get_pdf_page_count, pdf_page_to_image
from history_db import init_db, save_document, get_history, get_document, delete_document
import time
import csv as csv_module

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 60)
    print("ЗАГРУЗКА МОДЕЛЕЙ")
    print("=" * 60)
    try:
        summarizer.load_model()
        print("OK: Суммаризация готова")
    except Exception as e:
        print(f"WARNING: Суммаризация: {e}")
    try:
        vlm_ocr.load_model()
        print("OK: VLM OCR готов")
    except Exception as e:
        print(f"WARNING: VLM OCR: {e}")
    try:
        layout_detector.load_model()
        print("OK: Layout Detector готов")
    except Exception as e:
        print(f"WARNING: Layout Detector: {e}")
    try:
        text_analyzer.load_all()
    except Exception as e:
        print(f"WARNING: Text Analyzer: {e}")
    init_db()
    print("OK: История (SQLite) готова")
    print("=" * 60)
    yield


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class AnalyzeRequest(BaseModel):
    text: str
    language: str = "rus"


class SummarizeRequest(BaseModel):
    text: str


def _image_to_base64(image: Image.Image, max_width: int = 1200) -> str:
    """Конвертирует PIL Image в base64 PNG, масштабируя если нужно."""
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


def _run_ocr(image: Image.Image, ocr_engine: str, language: str, text_mode: str) -> tuple[str, str]:
    """Синхронная OCR — запускается в ThreadPoolExecutor."""
    if ocr_engine == "vlm":
        text = vlm_ocr.ocr(image, language=language, text_mode=text_mode)
        engine_name = "Qwen2-VL"
    else:
        text = tesseract_ocr.ocr(image, language=language)
        engine_name = "Tesseract"
    return text, engine_name


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/process")
async def process_image(
        file: UploadFile = File(...),
        ocr_engine: str = Form(default="tesseract"),
        language: str = Form(default="rus"),
        text_mode: str = Form(default="printed"),
        preprocessing: str = Form(default="none"),
):
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))

        if preprocessing != "none":
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                image = await loop.run_in_executor(
                    pool, lambda: preprocess_for_ocr(image, mode=preprocessing)
                )

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            text, engine_name = await loop.run_in_executor(
                pool, lambda: _run_ocr(image, ocr_engine, language, text_mode)
            )

        text = postprocess(text, engine=ocr_engine)
        return {"text": text, "engine": ocr_engine, "engine_name": engine_name, "language": language}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка OCR: {str(e)}")


@app.post("/process-stream")
async def process_image_stream(
        file: UploadFile = File(...),
        ocr_engine: str = Form(default="tesseract"),
        language: str = Form(default="rus"),
        text_mode: str = Form(default="printed"),
        preprocessing: str = Form(default="none"),
):
    """OCR с прогрессом через Server-Sent Events."""
    contents = await file.read()

    async def event_stream():
        def send(stage: str, progress: int, message: str, data: dict = None):
            payload = {"stage": stage, "progress": progress, "message": message}
            if data:
                payload.update(data)
            return f"data: {json_module.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            yield send("load", 5, "Загрузка изображения...")
            await asyncio.sleep(0)

            image = Image.open(io.BytesIO(contents))
            yield send("load", 15, f"Изображение {image.width}×{image.height} px")
            await asyncio.sleep(0)

            if preprocessing != "none":
                label = "шумоподавление" if preprocessing == "basic" else "выравнивание + шумоподавление"
                yield send("preprocess", 25, f"Предобработка: {label}...")
                await asyncio.sleep(0)
                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    image = await loop.run_in_executor(
                        pool, lambda: preprocess_for_ocr(image, mode=preprocessing)
                    )

            if ocr_engine == "vlm":
                if vlm_ocr.model is None:
                    yield send("error", 0, "VLM OCR модель не загружена")
                    return
                yield send("ocr", 40, "Qwen2-VL: генерация текста (может занять время)...")
                await asyncio.sleep(0)
            else:
                yield send("ocr", 40, "Tesseract: распознавание...")
                await asyncio.sleep(0)

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                text, engine_name = await loop.run_in_executor(
                    pool, lambda: _run_ocr(image, ocr_engine, language, text_mode)
                )

            yield send("post", 85, "Постобработка текста...")
            await asyncio.sleep(0)
            text = postprocess(text, engine=ocr_engine)

            yield send("done", 100, "Готово", {
                "text": text,
                "engine": ocr_engine,
                "engine_name": engine_name,
                "language": language,
            })

        except Exception as e:
            yield send("error", 0, f"Ошибка: {str(e)}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/process-pdf-stream")
async def process_pdf_stream(
        file: UploadFile = File(...),
        ocr_engine: str = Form(default="tesseract"),
        language: str = Form(default="rus"),
        text_mode: str = Form(default="printed"),
        preprocessing: str = Form(default="none"),
        dpi: int = Form(default=200),
):
    """Обработка PDF: конвертация страниц и OCR с прогрессом через SSE."""
    contents = await file.read()

    async def event_stream():
        def send(stage: str, progress: int, message: str, data: dict = None):
            payload = {"stage": stage, "progress": progress, "message": message}
            if data:
                payload.update(data)
            return f"data: {json_module.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            yield send("pdf_load", 3, "Чтение PDF...")
            await asyncio.sleep(0)

            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                total_pages = await loop.run_in_executor(
                    pool, lambda: get_pdf_page_count(contents)
                )

            if total_pages == 0:
                yield send("error", 0, "Не удалось определить количество страниц PDF")
                return

            yield send("pdf_info", 8, f"PDF загружен: {total_pages} стр.", {"total_pages": total_pages})
            await asyncio.sleep(0)

            if ocr_engine == "vlm" and vlm_ocr.model is None:
                yield send("error", 0, "VLM OCR модель не загружена")
                return

            for page_idx in range(total_pages):
                page_num = page_idx + 1
                base_progress = 10 + int(page_idx / total_pages * 88)
                next_progress = 10 + int(page_num / total_pages * 88)

                yield send(
                    "page_start",
                    base_progress,
                    f"Стр. {page_num}/{total_pages}: конвертация...",
                    {"page": page_idx, "total_pages": total_pages},
                )
                await asyncio.sleep(0)

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    image = await loop.run_in_executor(
                        pool, lambda pn=page_num: pdf_page_to_image(contents, pn, dpi=dpi)
                    )

                if image is None:
                    yield send(
                        "page_error",
                        base_progress,
                        f"Стр. {page_num}: ошибка конвертации",
                        {"page": page_idx, "total_pages": total_pages},
                    )
                    continue

                if preprocessing != "none":
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        image = await loop.run_in_executor(
                            pool, lambda img=image: preprocess_for_ocr(img, mode=preprocessing)
                        )

                yield send(
                    "page_ocr",
                    base_progress + (next_progress - base_progress) // 2,
                    f"Стр. {page_num}/{total_pages}: OCR...",
                    {"page": page_idx, "total_pages": total_pages},
                )
                await asyncio.sleep(0)

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    text, engine_name = await loop.run_in_executor(
                        pool, lambda img=image: _run_ocr(img, ocr_engine, language, text_mode)
                    )

                text = postprocess(text, engine=ocr_engine)
                image_b64 = _image_to_base64(image)

                yield send(
                    "page_done",
                    next_progress,
                    f"Стр. {page_num}/{total_pages} готова",
                    {
                        "page": page_idx,
                        "total_pages": total_pages,
                        "text": text,
                        "image_base64": image_b64,
                        "engine_name": engine_name,
                    },
                )
                await asyncio.sleep(0)

            yield send("done", 100, f"PDF обработан: {total_pages} стр.", {"total_pages": total_pages})

        except Exception as e:
            yield send("error", 0, f"Ошибка обработки PDF: {str(e)}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/summarize")
async def summarize_text(request: SummarizeRequest):
    try:
        text = request.text

        if not text or not text.strip():
            return {"summary": "Текст пустой."}

        if len(text.split()) < 10:
            return {"summary": "Текст слишком короткий (минимум 10 слов)."}

        if summarizer.model is None:
            raise HTTPException(status_code=500, detail="Модель суммаризации не загружена")

        summary = summarizer.summarize(text, use_hf_params=True)
        return {"summary": summary}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@app.post("/detect-layout")
async def detect_layout(file: UploadFile = File(...)):
    """Анализ структуры документа — возвращает блоки с bounding box и классами."""
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))

        if layout_detector.model is None:
            raise HTTPException(status_code=500, detail="Layout Detector не загружен")

        blocks = layout_detector.detect(image)
        return {
            "blocks": blocks,
            "image_width": image.width,
            "image_height": image.height,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")


@app.post("/analyze-text")
async def analyze_text_endpoint(request: SummarizeRequest):
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Текст пустой")
        result = text_analyzer.analyze(request.text)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка анализа: {str(e)}")


@app.get("/api/model-info")
async def get_model_info():
    return {
        "summarizer": summarizer.get_model_info(),
        "vlm_ocr": vlm_ocr.get_model_info() if vlm_ocr.model else None,
        "tesseract_ocr": tesseract_ocr.get_model_info(),
        "layout_detector": layout_detector.get_model_info(),
    }


@app.post("/compare-stream")
async def compare_stream(
        file: UploadFile = File(...),
        language: str = Form(default="rus"),
        text_mode: str = Form(default="printed"),
        preprocessing: str = Form(default="none"),
):
    """Сравнение Tesseract и Qwen2-VL на одном изображении через SSE."""
    contents = await file.read()

    async def event_stream():
        def send(stage: str, progress: int, message: str, data: dict = None):
            payload = {"stage": stage, "progress": progress, "message": message}
            if data:
                payload.update(data)
            return f"data: {json_module.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            yield send("load", 5, "Загрузка изображения...")
            await asyncio.sleep(0)
            image = Image.open(io.BytesIO(contents))
            yield send("load", 10, f"Изображение {image.width}×{image.height} px")
            await asyncio.sleep(0)

            if preprocessing != "none":
                yield send("preprocess", 15, "Предобработка...")
                await asyncio.sleep(0)
                loop = asyncio.get_running_loop()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    image = await loop.run_in_executor(pool, lambda: preprocess_for_ocr(image, mode=preprocessing))

            loop = asyncio.get_running_loop()

            # Tesseract
            yield send("tesseract_start", 20, "Tesseract: распознавание...")
            await asyncio.sleep(0)
            t0 = time.time()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                tess_text = await loop.run_in_executor(pool, lambda: tesseract_ocr.ocr(image, language=language))
            tess_text = postprocess(tess_text, engine="tesseract")
            tess_time = round(time.time() - t0, 2)
            yield send("tesseract_done", 50, f"Tesseract готов ({tess_time} с)",
                       {"tesseract_text": tess_text, "tesseract_time": tess_time})
            await asyncio.sleep(0)

            # VLM
            if vlm_ocr.model is None:
                yield send("vlm_done", 100, "Qwen2-VL не загружен",
                           {"vlm_text": "", "vlm_error": "Модель не загружена", "vlm_time": 0})
            else:
                yield send("vlm_start", 55, "Qwen2-VL: генерация текста...")
                await asyncio.sleep(0)
                t0 = time.time()
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    vlm_text = await loop.run_in_executor(
                        pool, lambda: vlm_ocr.ocr(image, language=language, text_mode=text_mode)
                    )
                vlm_text = postprocess(vlm_text, engine="vlm")
                vlm_time = round(time.time() - t0, 2)
                yield send("vlm_done", 95, f"Qwen2-VL готов ({vlm_time} с)",
                           {"vlm_text": vlm_text, "vlm_time": vlm_time})
                await asyncio.sleep(0)

            yield send("done", 100, "Сравнение завершено")

        except Exception as e:
            yield send("error", 0, f"Ошибка: {str(e)}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/export/docx")
async def export_docx_endpoint(request: Request):
    """Экспорт распознанного текста в .docx файл."""
    data = await request.json()
    text: str = data.get("text", "")
    filename: str = data.get("filename", "ocr_result")

    from docx import Document as DocxDocument
    doc = DocxDocument()
    doc.core_properties.title = filename

    for para in text.split("\n\n"):
        stripped = para.strip()
        if stripped:
            doc.add_paragraph(stripped)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ").strip() or "ocr_result"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
    )



@app.post("/extract-table")
async def extract_table(
        file: UploadFile = File(...),
        language: str = Form(default="rus"),
):
    """Извлечение таблицы из изображения через pytesseract TSV."""
    import pytesseract

    contents = await file.read()
    image = Image.open(io.BytesIO(contents))

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        data = await loop.run_in_executor(
            pool,
            lambda: pytesseract.image_to_data(
                image, lang=language, config="--psm 6",
                output_type=pytesseract.Output.DICT
            )
        )

    words = []
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        conf = int(data["conf"][i])
        if txt and conf > 0:
            words.append({
                "text": txt,
                "left": data["left"][i],
                "top": data["top"][i],
                "height": data["height"][i],
            })

    if not words:
        return {"rows": [], "csv": ""}

    words.sort(key=lambda w: (w["top"], w["left"]))
    row_thr = max(10, min(w["height"] for w in words) // 2)

    rows, cur_row = [], [words[0]]
    for w in words[1:]:
        if abs(w["top"] - cur_row[0]["top"]) <= row_thr:
            cur_row.append(w)
        else:
            rows.append(sorted(cur_row, key=lambda x: x["left"]))
            cur_row = [w]
    rows.append(sorted(cur_row, key=lambda x: x["left"]))

    text_rows = [[w["text"] for w in row] for row in rows]

    buf = io.StringIO()
    writer = csv_module.writer(buf)
    writer.writerows(text_rows)

    return {"rows": text_rows, "csv": buf.getvalue()}


# ── История ─────────────────────────────────────────────────

@app.get("/history")
async def history_list():
    return get_history(limit=100)


@app.post("/history/save")
async def history_save(request: Request):
    data = await request.json()

    thumb_b64 = ""
    raw_image: str = data.get("image", "")
    if raw_image:
        try:
            img_bytes = base64.b64decode(raw_image.split(",", 1)[-1])
            img = Image.open(io.BytesIO(img_bytes))
            if img.width > 240:
                ratio = 240 / img.width
                img = img.resize((240, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=72)
            thumb_b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            print(f"history image thumb warning: {e}")

    doc_id = save_document(
        filename=data.get("filename", "unknown"),
        ocr_engine=data.get("engine", ""),
        language=data.get("language", ""),
        text=data.get("text", ""),
        page_count=data.get("page_count", 1),
        image=thumb_b64,
    )
    return {"id": doc_id}


@app.get("/history/{doc_id}")
async def history_get(doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return doc


@app.delete("/history/{doc_id}")
async def history_delete(doc_id: int):
    delete_document(doc_id)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    print("Запуск сервера...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
