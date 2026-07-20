"""HTTP layer over the services. F2a: upload -> calculate -> download.
F2b: read/write company formula configs and add canonical fields.

This module is the server process's entry point, so — exactly like
conftest.py for the test process — it loads .env here, once, via
python-dotenv. No library module (services/, integrations/, models/)
imports dotenv itself; they all just read os.environ.

The API reimplements no calculation, mapping, or validation logic. Every
route is an adapter: validate the request, call the existing services,
shape the response. In particular, all config validation and file writing
lives in services/config_store.py — the routes only translate its errors
into HTTP status codes.
"""

import os
import secrets
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from integrations.llm_gateway_client import LlmGatewayClient, LlmGatewayError
from services.config_store import (
    ConfigConflict,
    ConfigError,
    ConfigNotFound,
    ConfigStore,
    ConfigValidation,
)
from services.excel_writer import write_company_result
from services.orchestrator import process_file

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

_DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_ALLOWED_ORIGINS = "http://localhost:5173,http://localhost:3000"
_DEFAULT_DOWNLOAD_TTL_SECONDS = 3600


def _max_upload_bytes() -> int:
    return int(os.environ.get("API_MAX_UPLOAD_BYTES", _DEFAULT_MAX_UPLOAD_BYTES))


def _download_ttl_seconds() -> int:
    return int(os.environ.get("API_DOWNLOAD_TTL_SECONDS", _DEFAULT_DOWNLOAD_TTL_SECONDS))


def _allowed_origins() -> list[str]:
    raw = os.environ.get("API_ALLOWED_ORIGINS", _DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


# --- one-time download registry -------------------------------------------
# token -> {"path": str, "download_name": str, "expires_at": float}. No
# history is persisted; an entry lives only long enough to serve its file
# once (deleted after it streams) or until its TTL sweeps it away.
_DOWNLOADS: dict[str, dict] = {}


def _sweep_expired_downloads() -> None:
    now = time.time()
    for token in [t for t, e in _DOWNLOADS.items() if e["expires_at"] <= now]:
        entry = _DOWNLOADS.pop(token, None)
        if entry:
            _safe_unlink(entry["path"])


def _safe_unlink(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _register_download(path: str, download_name: str) -> str:
    token = secrets.token_urlsafe(24)
    _DOWNLOADS[token] = {
        "path": path,
        "download_name": download_name,
        "expires_at": time.time() + _download_ttl_seconds(),
    }
    return token


def _save_upload_tempfile(content: bytes) -> str:
    """Persist an upload to a temp file and return its path. Isolated in one
    helper so the calculate route can clean it up in a finally block, and so
    tests can observe the path to assert it was deleted."""
    with NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(content)
        return tmp.name


def get_llm_client() -> Optional[LlmGatewayClient]:
    """Dependency hook. Returning None lets process_file build a real
    gateway client from env. Tests override this to inject a stub, so the
    suite never touches the network."""
    return None


def get_config_store() -> ConfigStore:
    """Dependency hook resolving the config directory (SSO_CONFIG_DIR / repo
    root). Tests override this to point at a temp copy so they never mutate
    the real repo config files."""
    return ConfigStore()


# --- F2b request bodies ---------------------------------------------------
# `sign`/`polarity` are plain strings (not Literals) so an invalid VALUE flows
# to the config-store's domain validation and returns a 400, rather than
# FastAPI's structural 422.


class ComponentBody(BaseModel):
    field: str
    sign: str
    required: bool


class SaveCompanyBody(BaseModel):
    display_name: str
    components: list[ComponentBody]


class CreateCompanyBody(BaseModel):
    company_id: str
    display_name: str
    components: list[ComponentBody]


class AddCanonicalFieldBody(BaseModel):
    key: str
    aliases_th: list[str] = []
    expected_group: Optional[str] = None
    polarity: str


def _components_to_config_shape(components: list[ComponentBody]) -> list[dict]:
    # API exposes {field, sign, required}; on-disk config uses {key, sign, required}.
    return [{"key": c.field, "sign": c.sign, "required": c.required} for c in components]


def _company_to_api(config) -> dict:
    return {
        "company_id": config.company_id,
        "display_name": config.display_name,
        "version": config.version,
        "components": [
            {"field": c.key, "sign": c.sign, "required": c.required} for c in config.components
        ],
    }


def _raise_for_config_error(err: ConfigError) -> None:
    if isinstance(err, ConfigNotFound):
        raise HTTPException(status_code=404, detail=str(err) or "ไม่พบข้อมูล")
    if isinstance(err, ConfigConflict):
        raise HTTPException(status_code=409, detail=str(err) or "ข้อมูลซ้ำ")
    if isinstance(err, ConfigValidation):
        raise HTTPException(status_code=400, detail=str(err) or "ข้อมูลไม่ถูกต้อง")
    raise HTTPException(status_code=400, detail="ข้อมูลไม่ถูกต้อง")


def create_app() -> FastAPI:
    app = FastAPI(title="SSO Calculation Service", version="F2a")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    @app.get("/api/companies")
    def list_companies(store: ConfigStore = Depends(get_config_store)) -> dict:
        return {"companies": store.list_companies()}

    @app.get("/api/companies/{company_id}")
    def get_company(company_id: str, store: ConfigStore = Depends(get_config_store)) -> dict:
        try:
            return _company_to_api(store.get_company(company_id))
        except ConfigError as err:
            _raise_for_config_error(err)

    @app.put("/api/companies/{company_id}")
    def save_company(
        company_id: str,
        body: SaveCompanyBody,
        store: ConfigStore = Depends(get_config_store),
    ) -> dict:
        try:
            config = store.save_company(
                company_id, body.display_name, _components_to_config_shape(body.components)
            )
            return _company_to_api(config)
        except ConfigError as err:
            _raise_for_config_error(err)

    @app.post("/api/companies", status_code=201)
    def create_company(
        body: CreateCompanyBody,
        store: ConfigStore = Depends(get_config_store),
    ) -> dict:
        try:
            config = store.create_company(
                body.company_id, body.display_name, _components_to_config_shape(body.components)
            )
            return _company_to_api(config)
        except ConfigError as err:
            _raise_for_config_error(err)

    @app.get("/api/canonical-fields")
    def list_canonical_fields(store: ConfigStore = Depends(get_config_store)) -> dict:
        # Identity-polarity fields (employee_id/employee_name) are excluded:
        # they are row metadata, never selectable as formula components.
        return {"canonical_fields": store.list_canonical_fields()}

    @app.post("/api/canonical-fields", status_code=201)
    def add_canonical_field(
        body: AddCanonicalFieldBody,
        store: ConfigStore = Depends(get_config_store),
    ) -> dict:
        try:
            field = store.add_canonical_field(
                body.key, body.aliases_th, body.expected_group, body.polarity
            )
            return {"canonical_field": field}
        except ConfigError as err:
            _raise_for_config_error(err)

    @app.post("/api/calculate")
    async def calculate(
        file: UploadFile = File(...),
        company_id: str = Form(...),
        llm_client: Optional[LlmGatewayClient] = Depends(get_llm_client),
        store: ConfigStore = Depends(get_config_store),
    ) -> dict:
        known_ids = {c["company_id"] for c in store.list_companies()}
        if company_id not in known_ids:
            raise HTTPException(status_code=400, detail=f"ไม่พบบริษัท '{company_id}'")

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400, detail="รองรับเฉพาะไฟล์ .xlsx หรือ .xls เท่านั้น"
            )

        content = await file.read()
        if len(content) > _max_upload_bytes():
            raise HTTPException(
                status_code=413,
                detail=f"ไฟล์มีขนาดใหญ่เกินกำหนด (สูงสุด {_max_upload_bytes() // (1024 * 1024)} MB)",
            )
        if not content:
            raise HTTPException(status_code=400, detail="ไฟล์ว่างเปล่า")

        _sweep_expired_downloads()

        upload_path = _save_upload_tempfile(content)
        try:
            result = process_file(
                upload_path, company_id, llm_client=llm_client, config_dir=store.base_dir
            )
        except LlmGatewayError:
            raise HTTPException(status_code=502, detail="เชื่อมต่อ LLM Gateway ไม่สำเร็จ")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดระหว่างประมวลผลไฟล์")
        finally:
            _safe_unlink(upload_path)

        if result.status == "needs_review":
            return {"status": "needs_review", "report_th": result.review_report_th}

        company_result = result.company_result
        output_path = _save_output_tempfile(company_result)
        download_name = f"{Path(file.filename or 'result').stem}_sso_result.xlsx"
        token = _register_download(output_path, download_name)

        return {
            "status": "ok",
            "summary": {
                "company": {
                    "company_id": company_result.audit.company_id,
                    "display_name": company_result.audit.display_name,
                },
                "employee_count": len(company_result.employees),
                "total_base": str(company_result.total_base),
                "total_contribution": str(company_result.total_contribution),
            },
            "employees": [
                {
                    "employee_id": e.employee_id,
                    "employee_name": e.employee_name,
                    "base": str(e.base),
                    "contribution": str(e.contribution),
                }
                for e in company_result.employees
            ],
            "download_token": token,
        }

    @app.get("/api/download/{token}")
    def download(token: str) -> FileResponse:
        _sweep_expired_downloads()
        entry = _DOWNLOADS.get(token)
        if entry is None or not os.path.exists(entry["path"]):
            raise HTTPException(status_code=404, detail="ไม่พบไฟล์ผลลัพธ์ หรือหมดอายุแล้ว")

        def _cleanup() -> None:
            _DOWNLOADS.pop(token, None)
            _safe_unlink(entry["path"])

        return FileResponse(
            entry["path"],
            media_type=_XLSX_MEDIA_TYPE,
            filename=entry["download_name"],
            background=BackgroundTask(_cleanup),
        )

    return app


def _save_output_tempfile(company_result) -> str:
    with NamedTemporaryFile(delete=False, suffix="_sso_result.xlsx") as tmp:
        output_path = tmp.name
    write_company_result(company_result, output_path)
    return output_path


app = create_app()
