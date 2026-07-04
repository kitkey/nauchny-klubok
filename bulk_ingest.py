"""Прогон всего пайплайна S0→persist по папке PDF: построить граф знаний из документов.

Пайплайн на каждый документ: ingest(PDF→текст) → chunk → [roles] → extract(n-арные факты)
→ link(дедуп/канон/конфликты/сшивка) → [verify] → persist(Neo4j + Mongo + vector-index).

Примеры:
  python bulk_ingest.py --dir ./docs --graph "Мой корпус"
  python bulk_ingest.py --dir ./docs --graph "Корпус" --provider yandex --limit 50 --lang ru
  python bulk_ingest.py --dir ./docs --graph "Корпус" --full   # с roles+verify (медленнее, полнее)

Провайдер:
  openrouter (по умолч.) — OPENROUTER_API_KEY
  yandex — YANDEX_API_KEY + YANDEX_FOLDER_ID (DeepSeek V4 Flash, reasoning-off)
"""
from __future__ import annotations

import argparse
import glob
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from p2kg.config import Config
from p2kg.context import Deps
from p2kg.embedder import OpenRouterEmbedder
from p2kg.llm import steps as _steps
from p2kg.llm.client import LLMClient
from p2kg.llm.prompts import PromptManager
from p2kg.pipeline import process_source
from p2kg.stores.docstore import MongoDocStore
from p2kg.stores.graphstore import Neo4jGraph

_STEPS = list(_steps.STEP_CONFIG.keys())


def _load_env() -> None:
    """Тонкий загрузчик .env (без зависимостей)."""
    p = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def build_deps(args, gid: str) -> Deps:
    cfg = Config.from_env()
    cfg.output_language = args.lang
    cfg.chunk_token_budget = args.chunk
    cfg.resolve_mode = "embed" if not args.full else "llm"
    cfg.skip_roles = not args.full
    cfg.skip_verify = not args.full
    cfg.use_llm_section_roles = args.full

    if args.provider == "yandex":
        folder = os.environ["YANDEX_FOLDER_ID"]
        _steps.STEP_CONFIG["extract.frame"] = _steps.Step(prompt="extract/frame", max_tokens=8000)
        cfg.models = {s: f"gpt://{folder}/deepseek-v4-flash/latest" for s in _STEPS}
        llm = LLMClient(api_key=os.environ["YANDEX_API_KEY"],
                        base_url="https://llm.api.cloud.yandex.net/v1",
                        openrouter=False, max_concurrency=args.concurrency)
    else:
        llm = LLMClient(api_key=os.environ["OPENROUTER_API_KEY"],
                        provider_order=["Wafer", "GMICloud", "Baidu"], max_concurrency=args.concurrency)

    auth = (os.environ.get("NEO4J_USER", "neo4j"), os.environ.get("NEO4J_PASSWORD", "password"))
    return Deps(llm=llm, embed=OpenRouterEmbedder(), prompts=PromptManager(), cfg=cfg,
                graph=Neo4jGraph(cfg.neo4j_uri, auth=auth, graph_id=gid),
                docs=MongoDocStore(cfg.mongo_uri))


def register_graph(name: str) -> str:
    """Зарегистрировать граф в control-plane (чтобы он был виден в UI) и вернуть его id."""
    from p2kg.api.control import MongoControl
    return MongoControl(os.environ.get("MONGO_URI", "mongodb://localhost:27017")).create_graph(name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="папка с PDF")
    ap.add_argument("--graph", required=True, help="имя графа (появится в UI)")
    ap.add_argument("--provider", choices=["openrouter", "yandex"], default="openrouter")
    ap.add_argument("--lang", default="ru", help="язык statement/ответов")
    ap.add_argument("--limit", type=int, default=0, help="сколько документов взять (0 = все)")
    ap.add_argument("--chunk", type=int, default=6000, help="размер чанка в токенах")
    ap.add_argument("--concurrency", type=int, default=20, help="одновременных LLM-вызовов")
    ap.add_argument("--parallel-docs", type=int, default=10, help="документов параллельно")
    ap.add_argument("--full", action="store_true", help="полный режим (roles+verify), медленнее, полнее")
    args = ap.parse_args()
    _load_env()

    pdfs = sorted(glob.glob(os.path.join(args.dir, "**", "*.pdf"), recursive=True))
    if args.limit:
        pdfs = pdfs[:args.limit]
    if not pdfs:
        print("PDF не найдены в", args.dir)
        return

    gid = register_graph(args.graph)
    deps = build_deps(args, gid)
    print(f"граф={gid}  документов={len(pdfs)}  провайдер={args.provider}  chunk={args.chunk}  full={args.full}")

    def ingest(p):
        n = os.path.basename(p)
        t = time.time()
        try:
            st = process_source(deps, p, paper_ref=n)
            return n, len(st.facts), len(st.entities), int(time.time() - t), None
        except Exception as e:  # noqa: BLE001
            return n, 0, 0, int(time.time() - t), repr(e)[:100]

    t0 = time.time()
    tf = te = ok = 0
    with ThreadPoolExecutor(max_workers=args.parallel_docs) as ex:
        for i, fut in enumerate(as_completed([ex.submit(ingest, p) for p in pdfs]), 1):
            n, f, e, s, err = fut.result()
            tf += f; te += e; ok += (0 if err else 1)
            print(f"[{i}/{len(pdfs)}] {'ERR' if err else 'OK '} {n[:44]:44} {f:4}f {e:4}e {s}s {err or ''}", flush=True)
    print(f"\nГОТОВО: ok={ok}/{len(pdfs)}  фактов={tf}  сущностей={te}  время={int(time.time()-t0)}s  graph_id={gid}")
    print(f"Открой http://localhost:8000 и выбери граф «{args.graph}».")


if __name__ == "__main__":
    main()
