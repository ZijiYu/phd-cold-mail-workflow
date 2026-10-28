"""FastAPI app: REST API + dashboard UI.

Security model (local, single user):
  - binds to 127.0.0.1 by default;
  - every /api route needs the API token (Authorization: Bearer <token> or
    X-API-Token). The token lives in <state_dir>/api_token; the UI gets it
    embedded in the page, which other origins cannot read;
  - requests whose Host header is not a loopback name are rejected, which
    blocks DNS-rebinding attacks from web pages in the same browser.
"""

from __future__ import annotations

import os
import secrets
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .gmail import GmailClient, GmailError, Transport, urllib_transport
from .store import Store, StoreError
from .sync import GmailState, push_draft, sync_campaign

STATIC = Path(__file__).resolve().parent.parent / "static"
LOOPBACK = {"localhost", "127.0.0.1", "[::1]", "::1"}


def load_or_create_token(state_dir: Path) -> str:
    p = Path(state_dir) / "api_token"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token + "\n")
    return token


# ------------------------------------------------------------------ schemas

class TargetCreate(BaseModel):
    target_id: str = Field(..., examples=["lakeview--dana-whitfield"])
    professor: str
    institution: str
    department: str = ""
    program_id: str = ""
    email: str = ""
    homepage_url: str = ""
    status: str = "researching"
    model_config = {"extra": "allow"}


class TargetPatch(BaseModel):
    """Any tracker column. Status changes are validated (e.g. closed needs close_reason);
    setting status=sent fills sent_at / last_contact_at / follow_up_due when blank."""
    model_config = {"extra": "allow", "json_schema_extra": {"examples": [{"status": "approved"}, {"status": "closed", "close_reason": "not recruiting"}]}}


class CampaignCreate(BaseModel):
    id: str = Field(..., examples=["fall-2027"], description="Folder name under the data folder")


class DraftCreate(BaseModel):
    kind: str = Field("first", pattern="^(first|followup|reply)$")


class DraftUpdate(BaseModel):
    subject: str
    body: str


class SyncRequest(BaseModel):
    target_ids: Optional[list[str]] = None


# ------------------------------------------------------------------ app

def create_app(data_dir: Path, state_dir: Path, gmail_transport: Transport = urllib_transport,
               allowed_hosts: set[str] | None = None, today: date | None = None) -> FastAPI:
    store = Store(data_dir)
    state_dir = Path(state_dir)
    gmail = GmailClient(state_dir, gmail_transport)
    gstate = GmailState(state_dir)
    token = load_or_create_token(state_dir)
    hosts = LOOPBACK | (allowed_hosts or set())
    today_fn = (lambda: today) if today else date.today

    app = FastAPI(
        title="PhD Outreach Dashboard API",
        version="1.0",
        description="Read and update the outreach campaign (programs, professors, drafts) and its Gmail state. "
                    "Authenticate with `Authorization: Bearer <token>`; the token is in the dashboard's state folder (`api_token`). "
                    "This API never sends email.",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.store, app.state.gmail, app.state.gstate, app.state.token = store, gmail, gstate, token

    @app.middleware("http")
    async def host_guard(request: Request, call_next):
        raw = request.headers.get("host") or ""
        host = raw.split("]")[0] + "]" if raw.startswith("[") else raw.split(":")[0]
        if host not in hosts:
            return JSONResponse({"detail": f"host {host!r} not allowed"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(StoreError)
    async def store_error(_, exc: StoreError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(GmailError)
    async def gmail_error(_, exc: GmailError):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    bearer = HTTPBearer(auto_error=False, description="API token from <state_dir>/api_token")

    def auth(request: Request, creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> None:
        supplied = (creds.credentials if creds else "") or request.headers.get("x-api-token", "")
        if not supplied or not secrets.compare_digest(supplied, token):
            raise HTTPException(401, "missing or invalid API token", headers={"WWW-Authenticate": "Bearer"})

    api = APIRouter(prefix="/api", dependencies=[Depends(auth)])

    # ------------------------------------------------------- campaigns
    @api.get("/campaigns", tags=["campaigns"], summary="List campaigns (folders with a targets.csv)")
    def list_campaigns():
        return store.campaigns()

    @api.post("/campaigns", tags=["campaigns"], status_code=201, summary="Create an empty campaign, e.g. fall-2027")
    def create_campaign(body: CampaignCreate):
        return store.create_campaign(body.id)

    @api.get("/campaigns/{campaign}/summary", tags=["campaigns"], summary="Counts, due follow-ups, issues, schools")
    def summary(campaign: str):
        return store.summary(campaign, today_fn())

    @api.get("/campaigns/{campaign}/programs", tags=["campaigns"], summary="Rows of programs.csv")
    def programs(campaign: str):
        return store.programs(campaign)

    # ------------------------------------------------------- targets
    @api.get("/campaigns/{campaign}/targets", tags=["targets"], summary="List professors")
    def targets(campaign: str, status: str = Query("", description="comma-separated statuses"),
                program_id: str = "", q: str = Query("", description="search name, school, email, anchor")):
        rows = store.targets(campaign, status, program_id, q)
        synced = gstate.campaign(campaign)
        for r in rows:
            s = synced.get(r["target_id"], {})
            r["_suggestion"] = s.get("suggestion")
        return rows

    @api.post("/campaigns/{campaign}/targets", tags=["targets"], status_code=201, summary="Add a professor")
    def create_target(campaign: str, body: TargetCreate):
        return store.create_target(campaign, body.model_dump())

    @api.get("/campaigns/{campaign}/targets/{target_id}", tags=["targets"], summary="One professor with issues and Gmail state")
    def get_target(campaign: str, target_id: str):
        row = store.target(campaign, target_id)
        return {
            "target": row,
            "issues": [i for i in store.summary(campaign, today_fn())["issues"] if i["target_id"] == target_id],
            "drafts": store.drafts(campaign, target_id),
            "gmail": gstate.get(campaign, target_id),
        }

    @api.patch("/campaigns/{campaign}/targets/{target_id}", tags=["targets"], summary="Update tracker fields")
    def patch_target(campaign: str, target_id: str, body: TargetPatch):
        fields = body.model_dump()
        if fields.get("status") == "approved" and store.target(campaign, target_id).get("status") != "approved":
            blockers = store.approval_blockers(campaign, target_id)
            if blockers:
                raise StoreError("首封草稿还不能定稿：" + "；".join(blockers), 422)
        row = store.update_target(campaign, target_id, fields, today_fn())
        if "status" in fields or any(k in fields for k in ("follow_up_due", "follow_up_count")):
            rec = gstate.get(campaign, target_id)
            if rec.get("suggestion"):
                gstate.update(campaign, target_id, suggestion=None)
        return row

    @api.delete("/campaigns/{campaign}/targets/{target_id}/suggestion", tags=["gmail"], status_code=204,
                summary="Dismiss the pending Gmail suggestion without applying it")
    def dismiss_suggestion(campaign: str, target_id: str):
        store.target(campaign, target_id)
        gstate.update(campaign, target_id, suggestion=None)

    # ------------------------------------------------------- drafts
    @api.get("/campaigns/{campaign}/targets/{target_id}/drafts", tags=["drafts"], summary="List a professor's drafts")
    def list_drafts(campaign: str, target_id: str):
        return store.drafts(campaign, target_id)

    @api.post("/campaigns/{campaign}/targets/{target_id}/drafts", tags=["drafts"], status_code=201, summary="Create a draft file")
    def new_draft(campaign: str, target_id: str, body: DraftCreate):
        return store.create_draft(campaign, target_id, body.kind)

    @api.get("/campaigns/{campaign}/targets/{target_id}/drafts/{name}", tags=["drafts"], summary="Read a draft")
    def read_draft(campaign: str, target_id: str, name: str):
        return store.read_draft(campaign, target_id, name)

    @api.put("/campaigns/{campaign}/targets/{target_id}/drafts/{name}", tags=["drafts"], summary="Save subject and body")
    def write_draft(campaign: str, target_id: str, name: str, body: DraftUpdate):
        saved = store.write_draft(campaign, target_id, name, body.subject, body.body)
        row = store.target(campaign, target_id)
        if row.get("status") == "researching" and body.body.strip():
            store.update_target(campaign, target_id, {"status": "drafted"}, today_fn())
        return saved

    @api.post("/campaigns/{campaign}/targets/{target_id}/drafts/{name}/check", tags=["drafts"],
              summary="Run the skill's draft checks (check_draft.py) on a draft")
    def check(campaign: str, target_id: str, name: str,
              kind: Optional[str] = Query(None, pattern="^(first|followup|thankyou|other)$")):
        return store.check_draft(campaign, target_id, name, kind)

    @api.post("/campaigns/{campaign}/targets/{target_id}/drafts/{name}/gmail", tags=["gmail"],
              summary="Save the draft into Gmail drafts (never sends)")
    def to_gmail(campaign: str, target_id: str, name: str):
        return push_draft(store, gmail, gstate, campaign, target_id, name)

    # ------------------------------------------------------- gmail
    @api.get("/gmail/status", tags=["gmail"], summary="Whether a Google client is configured and Gmail is connected")
    def gmail_status():
        return gmail.status()

    @api.post("/gmail/connect", tags=["gmail"], summary="Start Google OAuth; returns the URL to open")
    def gmail_connect(request: Request):
        redirect_uri = str(request.base_url).rstrip("/") + "/auth/google/callback"
        return {"auth_url": gmail.start_auth(redirect_uri), "redirect_uri": redirect_uri}

    @api.post("/gmail/disconnect", tags=["gmail"], summary="Revoke and delete the local Gmail token")
    def gmail_disconnect():
        gmail.disconnect()
        return gmail.status()

    @api.post("/campaigns/{campaign}/gmail/sync", tags=["gmail"],
              summary="Look for sends, replies, auto-replies and bounces; returns suggestions to confirm")
    def gmail_sync(campaign: str, body: SyncRequest | None = None):
        return sync_campaign(store, gmail, gstate, campaign, (body.target_ids if body else None), today_fn())

    @api.get("/campaigns/{campaign}/targets/{target_id}/thread", tags=["gmail"],
             summary="Messages in the latest Gmail thread with this professor")
    def thread(campaign: str, target_id: str):
        rec = gstate.get(campaign, target_id)
        msgs = (rec.get("incoming") or []) + (rec.get("outgoing") or [])
        if not msgs:
            return {"messages": [], "note": "还没有同步到与该教授的邮件；先点“同步 Gmail”。"}
        latest = max(msgs, key=lambda m: m["timestamp"])
        return {"thread_id": latest["thread_id"], "messages": gmail.thread(latest["thread_id"])}

    app.include_router(api)

    # ------------------------------------------------------- oauth callback + UI
    @app.get("/auth/google/callback", include_in_schema=False)
    def oauth_callback(code: str = "", state: str = "", error: str = ""):
        if error:
            return RedirectResponse(f"/#gmail-error={error}")
        try:
            gmail.finish_auth(code, state)
        except GmailError as e:
            return RedirectResponse(f"/#gmail-error={str(e)[:200]}")
        return RedirectResponse("/#gmail=connected")

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def index():
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__API_TOKEN__", token), headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
