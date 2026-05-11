"""
Standalone image verification UI (localhost + shared secret only).
Not registered with the main Academy application.
"""
from __future__ import annotations

import json
import os
import sys
import time

_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)

from csv_urls import iter_url_rows
from fetch_media import download_https
from gemini_verify import verify_image_bytes
from media_parts import bytes_to_verify_parts
from verification_config import (
    MAX_DOWNLOAD_BYTES,
    MAX_PDF_PAGES,
    PDF_PAGE_MAX_SIDE_PX,
    SYSTEM_INSTRUCTION,
    VERIFICATION_MODEL_ID,
)

load_dotenv()

BASE_DIR = _BASE


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _nd(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.2f}s"
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m}m {s:.1f}s"


def _sum_usage(target: dict, usage: dict | None) -> None:
    if not usage:
        return
    for k in ("prompt_token_count", "candidates_token_count", "total_token_count"):
        v = usage.get(k)
        if isinstance(v, int):
            target[k] = target.get(k, 0) + v


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )
    sk = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if not sk:
        raise RuntimeError("Set FLASK_SECRET_KEY (or SECRET_KEY) in the environment")
    app.secret_key = sk
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if _bool_env("SESSION_COOKIE_SECURE"):
        app.config["SESSION_COOKIE_SECURE"] = True

    access_secret = os.environ.get("IMAGE_VERIFICATION_SECRET", "").strip()
    if not access_secret:
        raise RuntimeError("Set IMAGE_VERIFICATION_SECRET in the environment")

    @app.before_request
    def _require_login():
        if request.endpoint in ("login", "static"):
            return None
        if session.get("iv_ok") == access_secret:
            return None
        if request.path.startswith("/static/"):
            return redirect(url_for("login"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        err = None
        if request.method == "POST":
            pw = (request.form.get("secret") or "").strip()
            if pw == access_secret:
                session["iv_ok"] = access_secret
                return redirect(url_for("index"))
            err = "Invalid secret"
        return render_template("login.html", error=err)

    @app.route("/logout", methods=["POST"])
    def logout():
        session.pop("iv_ok", None)
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/verify", methods=["POST"])
    def api_verify():
        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            return jsonify({"error": "GEMINI_API_KEY is not set"}), 500
        model = VERIFICATION_MODEL_ID.strip()
        system_instruction = SYSTEM_INSTRUCTION.strip()
        if not system_instruction:
            return jsonify({"error": "SYSTEM_INSTRUCTION is empty in verification_config.py"}), 500
        url_column = (request.form.get("url_column") or "").strip() or None
        f = request.files.get("csv")
        if not f or not f.filename:
            return jsonify({"error": "Upload a CSV file"}), 400
        raw = f.read()
        try:
            rows = list(iter_url_rows(raw, url_column=url_column))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not rows:
            return jsonify({"error": "No rows with a URL found in CSV"}), 400

        @stream_with_context
        def generate():
            t0 = time.perf_counter()
            yield _nd({"event": "prepare", "phase": "download", "message": "Downloading and analyzing files…"})

            planned: list[dict] = []
            nrows = len(rows)
            for i, (row_num, row_dict, url) in enumerate(rows, start=1):
                msg = f"Prepare {i}/{nrows}: {url[:80]}{'…' if len(url) > 80 else ''}"
                print(msg, flush=True)
                yield _nd(
                    {
                        "event": "prepare",
                        "phase": "download",
                        "current": i,
                        "rows": nrows,
                        "url": url,
                    }
                )
                try:
                    data, ct = download_https(url, MAX_DOWNLOAD_BYTES)
                    parts = bytes_to_verify_parts(
                        data=data,
                        url=url,
                        content_type=ct,
                        max_pdf_pages=MAX_PDF_PAGES,
                        pdf_page_max_side_px=PDF_PAGE_MAX_SIDE_PX,
                    )
                    planned.append(
                        {
                            "row_num": row_num,
                            "row_dict": row_dict,
                            "url": url,
                            "parts": parts,
                            "plan_error": None,
                        }
                    )
                except Exception as ex:
                    planned.append(
                        {
                            "row_num": row_num,
                            "row_dict": row_dict,
                            "url": url,
                            "parts": [],
                            "plan_error": str(ex),
                        }
                    )

            total_steps = sum(len(p["parts"]) for p in planned if not p.get("plan_error"))
            yield _nd(
                {
                    "event": "start",
                    "model": model,
                    "csv_rows": nrows,
                    "total_steps": total_steps,
                }
            )
            print(f"Verification: {total_steps} Gemini call(s) across {nrows} CSV row(s).", flush=True)

            aggregate = {"prompt_token_count": 0, "candidates_token_count": 0, "total_token_count": 0}
            step_i = 0
            for plan in planned:
                row_num = plan["row_num"]
                row_dict = plan["row_dict"]
                url = plan["url"]
                if plan.get("plan_error"):
                    err = plan["plan_error"]
                    print(f"Row {row_num}: plan failed — {err}", flush=True)
                    yield _nd(
                        {
                            "event": "row",
                            "payload": {
                                "row": row_num,
                                "url": url,
                                "row_data": row_dict,
                                "media_kind": "error",
                                "ok": False,
                                "error": err,
                                "valid": None,
                                "parts": [],
                            },
                        }
                    )
                    continue

                parts_in = plan["parts"]
                media_kind = (
                    "pdf"
                    if parts_in
                    and (
                        len(parts_in) > 1
                        or (parts_in[0][0].startswith("PDF page"))
                    )
                    else "image"
                )
                part_results: list[dict] = []

                for label, img_bytes, mime in parts_in:
                    step_i += 1
                    detail = f"Row {row_num} · {label}"
                    print(f"[{step_i}/{total_steps}] {detail}", flush=True)
                    yield _nd(
                        {
                            "event": "progress",
                            "step": step_i,
                            "total": total_steps,
                            "row": row_num,
                            "detail": detail,
                        }
                    )
                    try:
                        vr = verify_image_bytes(
                            api_key=api_key,
                            model=model,
                            system_instruction=system_instruction,
                            image_bytes=img_bytes,
                            mime_type=mime,
                        )
                        _sum_usage(aggregate, vr.get("usage_metadata"))
                        part_results.append(
                            {
                                "label": label,
                                "ok": True,
                                "valid": vr.get("valid"),
                                "notes": vr.get("notes"),
                                "tokens": vr.get("tokens"),
                                "usage_metadata": vr.get("usage_metadata"),
                                "parse_error": vr.get("parse_error"),
                                "error": None,
                            }
                        )
                    except Exception as ex:
                        part_results.append(
                            {
                                "label": label,
                                "ok": False,
                                "valid": None,
                                "notes": None,
                                "tokens": None,
                                "usage_metadata": None,
                                "parse_error": None,
                                "error": str(ex),
                            }
                        )

                valids = [p.get("valid") for p in part_results if p.get("ok")]
                if not part_results:
                    row_valid = None
                elif any(p.get("error") for p in part_results):
                    row_valid = None
                elif any(v is False for v in valids):
                    row_valid = False
                elif valids and all(v is True for v in valids):
                    row_valid = True
                else:
                    row_valid = None

                notes_merge = "; ".join(
                    f"{p['label']}: {p.get('notes') or p.get('error') or p.get('parse_error') or ''}"
                    for p in part_results
                )[:4000]

                row_payload = {
                    "row": row_num,
                    "url": url,
                    "row_data": row_dict,
                    "media_kind": media_kind,
                    "page_count": len(parts_in),
                    "ok": True,
                    "error": None,
                    "valid": row_valid,
                    "notes": notes_merge,
                    "parts": part_results,
                }
                vf = row_valid is True
                print(f"Row {row_num}: done — valid={vf} ({media_kind}, {len(parts_in)} part(s))", flush=True)
                yield _nd({"event": "row", "payload": row_payload})

            elapsed = time.perf_counter() - t0
            elapsed_human = _format_elapsed(elapsed)
            yield _nd(
                {
                    "event": "done",
                    "model": model,
                    "aggregate_token_hints": aggregate,
                    "elapsed_sec": round(elapsed, 3),
                    "elapsed_human": elapsed_human,
                }
            )
            print(f"Verification finished in {elapsed_human} ({elapsed:.3f}s wall clock).", flush=True)

        return Response(
            generate(),
            mimetype="application/x-ndjson",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def main():
    load_dotenv()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5055"))
    app = create_app()
    print(f"Image verification engine: http://{host}:{port}/  (bind {host} only — not exposed to LAN if 127.0.0.1)")
    app.run(host=host, port=port, debug=_bool_env("FLASK_DEBUG"))


if __name__ == "__main__":
    main()
