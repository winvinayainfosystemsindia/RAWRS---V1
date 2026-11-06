"""Task 2 licence audit: compare permissive replacements with the current engines.

    python scripts/licence_bench.py ocr --pdf PDF --gold DOCX [--engines docling,surya,glm,tesseract]
    python scripts/licence_bench.py alt --gold-dir DIR --models qwen2.5vl:3b,qwen3-vl:4b

Every score here is an estimate: similarity to an independent human-remediated
version (docs/LICENSING_AUDIT.md). It is not reviewer behaviour.
- OCR: word 4-gram recall and precision of each engine's page text against the
  human-remediated DOCX text (multiset overlap), plus seconds per page.
- Alt text: each Ollama vision model describes the figures embedded in the
  human-remediated DOCX files, using RAWRS's production prompt and parser
  (src/ai/providers/ollama.py). The score is content-word overlap with the
  human alt text, and whether RAWRS can parse the reply at all.
The gold DOCX files are copyrighted: run this in the Codespace, delete them
afterwards, and never commit them or the output JSON.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

os.environ.setdefault("RAWRS_OCR_CACHE", "off")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STOP = set("the and for are with that this from into over under its their than then them they these those has have was were been being which while what when where who whom why how not but all any each one two three also can may such per via of to in on at by an or as is be it a".split())


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def ngram_scores(candidate: str, gold: str, n: int = 4) -> dict:
    def grams(text: str) -> Counter:
        w = _words(text)
        return Counter(tuple(w[i:i + n]) for i in range(len(w) - n + 1))

    c, g = grams(candidate), grams(gold)
    hit = sum((c & g).values())
    return {"recall": hit / max(1, sum(g.values())), "precision": hit / max(1, sum(c.values()))}


def docx_text(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    parts += [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    return "\n".join(parts)


# --------------------------------------------------------------------- OCR

def _png(pdf: Path, page: int, dpi: int) -> bytes:
    import fitz

    with fitz.open(pdf) as d:
        return d[page - 1].get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def _ollama(model: str, prompt: str, png: bytes | None, num_predict: int | None = None, timeout: float = 1800) -> str:
    import base64

    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if num_predict:
        # A 200 DPI page image alone is ~4,050 tokens; Ollama's default 4,096 context
        # leaves no room for the reading, so every page ran to the cap (measured 6m33s each).
        payload["options"].update(num_predict=num_predict, num_ctx=16384)
    if png is not None:
        payload["images"] = [base64.b64encode(png).decode("ascii")]
    req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["response"]


def _ollama_size(model: str) -> int | None:
    with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=5) as r:
        for m in json.loads(r.read()).get("models", []):
            if m.get("name") == model:
                return m.get("size")
    return None


def ocr_engine(engine: str, pdf: Path, pages: list[int]) -> list[str]:
    if engine == "docling":
        from src.ocr.docling_engine import ocr_page_texts

        texts = ocr_page_texts(pdf)
        return [texts[p - 1] if p - 1 < len(texts) else "" for p in pages]
    if engine == "surya":
        from src.ocr.surya_config import build_recognition_predictor, render_page_to_image
        from src.ocr.surya_engine import page_result_to_text

        predictor = build_recognition_predictor()
        return [page_result_to_text(predictor([render_page_to_image(pdf, p)], full_page=True)[0]) for p in pages]
    if engine == "glm":
        # Same model and prompt as src/ocr/reread.py, on the whole page.
        return [_ollama("glm-ocr:q8_0", "Text Recognition:", _png(pdf, p, 200), 4096) for p in pages]
    if engine == "tesseract":
        out = []
        for p in pages:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(_png(pdf, p, 300))
            out.append(subprocess.run(["tesseract", f.name, "-", "-l", "eng"], capture_output=True, text=True).stdout)
            os.unlink(f.name)
        return out
    raise SystemExit(f"unknown engine {engine}")


def run_ocr(args) -> dict:
    import fitz

    pdf, gold = Path(args.pdf), docx_text(Path(args.gold))
    with fitz.open(pdf) as d:
        pages = list(range(1, d.page_count + 1))
    rows = {}
    for engine in args.engines.split(","):
        start = time.perf_counter()
        try:
            texts = ocr_engine(engine, pdf, pages)
        except Exception as exc:  # report a failed engine, keep the others
            rows[engine] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
            print(engine, "FAILED", rows[engine]["error"], flush=True)
            continue
        seconds = time.perf_counter() - start
        scores = ngram_scores("\n".join(texts), gold)
        rows[engine] = {**scores, "seconds": seconds, "seconds_per_page": seconds / len(pages),
                        "empty_pages": sum(1 for t in texts if not t.strip()), "pages": len(pages),
                        "ollama_bytes": _ollama_size("glm-ocr:q8_0") if engine == "glm" else None}
        print(engine, json.dumps(rows[engine]), flush=True)
        _save(args.out, {"pdf": pdf.name, "gold": Path(args.gold).name, "engines": rows})
    return {"pdf": pdf.name, "gold": Path(args.gold).name, "engines": rows}


def _save(out: str, result: dict) -> None:
    # After every engine or model: an idle Codespace shutdown must not lose finished work.
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- alt text

def gold_figures(docx: Path) -> list[tuple[str, bytes, str]]:
    """(name, image bytes, human alt text) for every described picture, in order."""
    z = zipfile.ZipFile(docx)
    xml = z.read("word/document.xml").decode("utf-8")
    rels = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', z.read("word/_rels/document.xml.rels").decode("utf-8")))
    out = []
    for i, drawing in enumerate(re.findall(r"<w:drawing>.*?</w:drawing>", xml, re.S)):
        descr = re.search(r'<wp:docPr [^>]*descr="([^"]*)"', drawing)
        blip = re.search(r'r:embed="([^"]+)"', drawing)
        if descr and descr.group(1).strip() and blip and blip.group(1) in rels:
            human = re.sub(r"&quot;", '"', re.sub(r"&amp;", "&", descr.group(1)))
            out.append((f"{docx.stem[:30]}#{i + 1}", z.read("word/" + rels[blip.group(1)].lstrip("/")), human))
    return out


def figure_contexts(docx: Path) -> dict:
    """name -> (label, caption, nearby text) for each picture, like production's
    context: the caption and the closest paragraphs (up to 5), never the alt text."""
    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    texts = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip() for p in paras]
    out, number = {}, 0
    for k, para in enumerate(paras):
        for _ in re.findall(r"<w:drawing>", para):
            number += 1
            order = sorted(range(max(0, k - 3), min(len(paras), k + 4)), key=lambda j: abs(j - k))
            near = [texts[j] for j in order if texts[j]][:5]
            caption = next((x for x in near if re.match(r"(fig(ure)?|table|chart|diagram|exhibit)\.?\s*\d", x, re.I)), "")
            label = re.match(r"\S+\s*[\d.]+", caption).group(0) if caption else "Unknown"
            out[f"{docx.stem[:30]}#{number}"] = (label, caption or "None provided", near)
    return out


def content_words(text: str) -> set[str]:
    return {w for w in _words(text) if len(w) > 2 and w not in STOP}


def run_alt(args) -> dict:
    from PIL import Image

    from src.ai.alt_text_generator import AltTextGenerationError
    from src.ai.providers.qwen import _PROMPT_TEMPLATE, _parse_response

    from src.ai.providers.ollama import _GENERATE_TIMEOUT_SECONDS

    figures = [f for d in sorted(Path(args.gold_dir).glob("*.docx")) for f in gold_figures(d)]
    contexts = {} if args.no_context else {k: v for d in sorted(Path(args.gold_dir).glob("*.docx"))
                                           for k, v in figure_contexts(d).items()}
    # Resume: an idle Codespace shutdown kills the run, so keep every figure already scored.
    out = Path(args.out)
    result = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"figures": len(figures), "models": {}}
    for model in args.models.split(","):
        items = result["models"].get(model, {}).get("items", [])
        done = {i["figure"] for i in items}
        for name, data, human in figures:
            if name in done:
                continue
            label, caption, near = contexts.get(name, ("Unknown", "None provided", []))
            prompt = _PROMPT_TEMPLATE.format(figure_label=label, caption=caption, nearby_text="; ".join(near) or "None")
            buf = io.BytesIO()
            Image.open(io.BytesIO(data)).convert("RGB").save(buf, "PNG")
            start = time.perf_counter()
            try:
                # Production's own limit: a figure slower than this fails for the user too.
                raw, timed_out = _ollama(model, prompt, buf.getvalue(), timeout=_GENERATE_TIMEOUT_SECONDS), False
            except TimeoutError:
                raw, timed_out = "", True
            seconds = time.perf_counter() - start
            try:
                description, parsed = _parse_response(raw).description, True
            except AltTextGenerationError:
                description, parsed = raw.strip(), False
            h, m = content_words(human), content_words(description)
            items.append({"figure": name, "seconds": seconds, "parsed": parsed, "timed_out": timed_out,
                          "description": description, "human": human,
                          "recall": len(h & m) / max(1, len(h)), "precision": len(h & m) / max(1, len(m))})
            print(model, name, f"{seconds:.0f}s parsed={parsed} timed_out={timed_out} recall={items[-1]['recall']:.2f}", flush=True)
            result["models"][model] = {"items": items, "partial": True}
            _save(args.out, result)
        n = len(items)
        result["models"][model] = {
            "parsed": sum(i["parsed"] for i in items), "n": n, "timed_out": sum(i.get("timed_out", False) for i in items),
            "mean_recall": sum(i["recall"] for i in items) / n, "mean_precision": sum(i["precision"] for i in items) / n,
            "median_seconds": sorted(i["seconds"] for i in items)[n // 2], "ollama_bytes": _ollama_size(model), "items": items}
        _save(args.out, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("ocr")
    o.add_argument("--pdf", required=True)
    o.add_argument("--gold", required=True)
    o.add_argument("--engines", default="docling,surya,glm,tesseract")
    a = sub.add_parser("alt")
    a.add_argument("--gold-dir", required=True)
    a.add_argument("--models", required=True)
    a.add_argument("--no-context", action="store_true", help="as the 2026-11-04 run: no caption or nearby text")
    for p in (o, a):
        p.add_argument("--out", required=True)
    args = parser.parse_args()
    _save(args.out, run_ocr(args) if args.cmd == "ocr" else run_alt(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
