import json
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.analyzer import analyze_practice
from src.auth import get_admin_client, get_current_user, require_admin
from src.call_log import append_call_note
from src.clay import trigger_enrichment
from src.email_gen import generate_email_draft
from src.email_poll import poll_replies
from src.email_send import send_email
from src.models import Practice
from src.places import get_place, search_places
from src.scriptgen import generate_script
from src.settings import settings as app_settings
from src.storage import (
    get_practice,
    insert_email_message,
    list_email_messages,
    list_outbound_message_ids,
    query_practices,
    update_practice_analysis,
    update_practice_fields,
    upsert_practices,
)

app = FastAPI(title="HV Sales Intel", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def bootstrap_admin_on_startup():
    """If no admin exists and BOOTSTRAP_ADMIN_* env vars are set, seed one."""
    from src.settings import settings
    if not (settings.supabase_url and settings.supabase_service_role_key):
        return
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    try:
        client = get_admin_client()
        existing = client.table("profiles").select("id").eq("role", "admin").execute()
        if existing.data:
            return
        created = client.auth.admin.create_user({
            "email": settings.bootstrap_admin_email,
            "password": settings.bootstrap_admin_password,
            "email_confirm": True,
            "user_metadata": {"name": "Bootstrap Admin"},
        })
        client.table("profiles").update({"role": "admin"}).eq("id", created.user.id).execute()
        print(f"[bootstrap] Seeded admin: {settings.bootstrap_admin_email}")
    except Exception as e:
        print(f"[bootstrap] Skipped ({e!r})")


STATUS_ORDER = [
    "NEW", "RESEARCHED", "SCRIPT READY", "CONTACTED",
    "FOLLOW UP", "MEETING SET", "PROPOSAL", "CLOSED WON", "CLOSED LOST",
]


def _should_auto_advance(current: str, target: str) -> bool:
    try:
        return STATUS_ORDER.index(target) > STATUS_ORDER.index(current)
    except ValueError:
        return False


class CreateUserRequest(BaseModel):
    email: str
    name: str
    password: str
    role: str = "rep"


@app.get("/api/admin/users")
def list_users(admin: dict = Depends(require_admin)):
    """List all profiles with per-user touched-practice count."""
    client = get_admin_client()
    profiles_res = client.table("profiles").select("*").execute()
    counts_res = client.table("practices").select("last_touched_by").execute()
    counts: dict[str, int] = {}
    for row in counts_res.data or []:
        uid = row.get("last_touched_by")
        if uid:
            counts[uid] = counts.get(uid, 0) + 1
    users = []
    for p in profiles_res.data or []:
        users.append({**p, "practices_touched": counts.get(p["id"], 0)})
    return {"users": users}


@app.post("/api/admin/users")
def create_user(body: CreateUserRequest, admin: dict = Depends(require_admin)):
    if body.role not in ("admin", "rep"):
        raise HTTPException(status_code=400, detail="role must be 'admin' or 'rep'")
    client = get_admin_client()
    try:
        created = client.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
            "user_metadata": {"name": body.name},
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    user_id = created.user.id
    if body.role == "admin":
        client.table("profiles").update({"role": "admin"}).eq("id", user_id).execute()
    profile = client.table("profiles").select("*").eq("id", user_id).single().execute()
    return profile.data


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete self")
    client = get_admin_client()
    try:
        client.auth.admin.delete_user(user_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


class ResetPasswordRequest(BaseModel):
    new_password: str


@app.post("/api/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    admin: dict = Depends(require_admin),
):
    client = get_admin_client()
    try:
        client.auth.admin.update_user_by_id(user_id, {"password": body.new_password})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


# ======================= Email outreach endpoints =======================

def _email_configured() -> bool:
    return bool(
        app_settings.ms_tenant_id
        and app_settings.ms_client_id
        and app_settings.ms_client_secret
        and app_settings.ms_refresh_token
        and app_settings.ms_sender_email
    )


class EmailDraftPatch(BaseModel):
    subject: str | None = None
    body: str | None = None


def _parse_draft(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


@app.get("/api/practices/{place_id}/email/draft")
async def get_email_draft_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(404, "Practice not found")

    cached = _parse_draft(practice.get("email_draft"))
    if cached:
        return cached

    draft = await generate_email_draft(
        name=practice["name"],
        category=practice.get("category"),
        summary=practice.get("summary"),
        pain_points=practice.get("pain_points"),
        sales_angles=practice.get("sales_angles"),
    )
    update_practice_fields(
        place_id,
        {
            "email_draft": json.dumps(draft),
            "email_draft_updated_at": datetime.now(timezone.utc).isoformat(),
        },
        touched_by=user["id"],
    )
    return draft


@app.post("/api/practices/{place_id}/email/draft")
async def regenerate_email_draft_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(404, "Practice not found")

    draft = await generate_email_draft(
        name=practice["name"],
        category=practice.get("category"),
        summary=practice.get("summary"),
        pain_points=practice.get("pain_points"),
        sales_angles=practice.get("sales_angles"),
    )
    update_practice_fields(
        place_id,
        {
            "email_draft": json.dumps(draft),
            "email_draft_updated_at": datetime.now(timezone.utc).isoformat(),
        },
        touched_by=user["id"],
    )
    return draft


@app.patch("/api/practices/{place_id}/email/draft")
def patch_email_draft_endpoint(
    place_id: str,
    body: EmailDraftPatch,
    user: dict = Depends(get_current_user),
):
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(404, "Practice not found")

    current = _parse_draft(practice.get("email_draft")) or {"subject": "", "body": ""}
    if body.subject is not None:
        current["subject"] = body.subject
    if body.body is not None:
        current["body"] = body.body

    update_practice_fields(
        place_id,
        {
            "email_draft": json.dumps(current),
            "email_draft_updated_at": datetime.now(timezone.utc).isoformat(),
        },
        touched_by=user["id"],
    )
    return current


@app.post("/api/practices/{place_id}/email/send")
async def send_email_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    if not _email_configured():
        raise HTTPException(503, "Email not configured")

    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(404, "Practice not found")

    email_to = practice.get("email")
    if not email_to:
        raise HTTPException(400, "Email address required")

    draft = _parse_draft(practice.get("email_draft"))
    if not draft or not draft.get("subject") or not draft.get("body"):
        raise HTTPException(400, "No draft to send")

    try:
        result = await send_email(email_to, draft["subject"], draft["body"])
    except Exception as e:
        insert_email_message(
            practice_id=practice["id"],
            user_id=user["id"],
            direction="out",
            subject=draft["subject"],
            body=draft["body"],
            message_id=None,
            in_reply_to=None,
            error=str(e),
        )
        raise HTTPException(500, f"Send failed: {e}") from e

    row = insert_email_message(
        practice_id=practice["id"],
        user_id=user["id"],
        direction="out",
        subject=draft["subject"],
        body=draft["body"],
        message_id=result.get("message_id"),
        in_reply_to=None,
        error=None,
    )

    current_status = practice.get("status", "NEW")
    fields: dict = {}
    if _should_auto_advance(current_status, "CONTACTED"):
        fields["status"] = "CONTACTED"
    update_practice_fields(place_id, fields, touched_by=user["id"])

    return row


@app.get("/api/practices/{place_id}/email/messages")
def list_email_messages_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(404, "Practice not found")
    return {"messages": list_email_messages(practice["id"])}


@app.post("/api/practices/{place_id}/email/poll")
async def poll_email_replies_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    if not _email_configured():
        raise HTTPException(503, "Email not configured")

    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(404, "Practice not found")

    email_addr = practice.get("email")
    if not email_addr:
        raise HTTPException(400, "Practice has no email address")

    outbound = list_outbound_message_ids(practice["id"])
    since = (
        datetime.now(timezone.utc)
        - timedelta(days=app_settings.email_reply_lookback_days)
    ).isoformat()

    replies = await poll_replies(
        practice_email=email_addr,
        outbound_message_ids=outbound,
        since_iso=since,
    )

    existing = list_email_messages(practice["id"])
    existing_ids = {m.get("message_id") for m in existing if m.get("message_id")}

    new_rows: list[dict] = []
    for reply in replies:
        if reply["message_id"] in existing_ids:
            continue
        inserted = insert_email_message(
            practice_id=practice["id"],
            user_id=None,
            direction="in",
            subject=reply.get("subject"),
            body=reply.get("body"),
            message_id=reply.get("message_id"),
            in_reply_to=reply.get("in_reply_to"),
            error=None,
        )
        if inserted:
            new_rows.append(inserted)

    if new_rows:
        current_status = practice.get("status", "NEW")
        fields: dict = {}
        if _should_auto_advance(current_status, "FOLLOW UP"):
            fields["status"] = "FOLLOW UP"
        update_practice_fields(place_id, fields, touched_by=user["id"])

    return {
        "new_messages": new_rows,
        "total": len(list_email_messages(practice["id"])),
    }


@app.post("/api/practices/{place_id}/email/mark-replied")
def mark_email_replied_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(404, "Practice not found")

    row = insert_email_message(
        practice_id=practice["id"],
        user_id=None,
        direction="in",
        subject=None,
        body=f"[manually marked as replied by {user.get('name') or user['email']}]",
        message_id=None,
        in_reply_to=None,
        error=None,
    )

    current_status = practice.get("status", "NEW")
    fields: dict = {}
    if _should_auto_advance(current_status, "FOLLOW UP"):
        fields["status"] = "FOLLOW UP"
    update_practice_fields(place_id, fields, touched_by=user["id"])

    return row


def _strip_joined(row: dict) -> dict:
    """Drop keys the Practice model doesn't know about (joins + attribution flat names)."""
    allowed = set(Practice.model_fields.keys())
    return {k: v for k, v in row.items() if k in allowed}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return user


@app.get("/api/practices")
def list_practices(
    city: str | None = Query(None),
    category: str | None = Query(None),
    min_rating: float | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    rows = query_practices(city=city, category=category, min_rating=min_rating, limit=limit)
    return {"practices": rows, "count": len(rows)}


class SearchRequest(BaseModel):
    query: str
    refresh: bool = False


@app.post("/api/practices/search")
async def search(body: SearchRequest, user: dict = Depends(get_current_user)):
    practices = await search_places(body.query)
    upserted = upsert_practices(practices, touched_by=user["id"])

    # Re-fetch from DB so the response carries joined attribution
    # (last_touched_by_name, last_touched_at). Falls back to the in-memory
    # Practice objects if the DB isn't configured.
    enriched: list[dict] = []
    for p in practices:
        row = get_practice(p.place_id)
        enriched.append(row if row else p.model_dump())

    return {
        "practices": enriched,
        "count": len(practices),
        "upserted": upserted,
    }


@app.get("/api/practices/{place_id}")
def get_single(place_id: str, user: dict = Depends(get_current_user)):
    row = get_practice(place_id)
    if not row:
        raise HTTPException(status_code=404, detail="Practice not found")
    return row


class AnalyzeRequest(BaseModel):
    force: bool = False
    rescan: bool = False


@app.post("/api/practices/{place_id}/analyze")
async def analyze(
    place_id: str,
    body: AnalyzeRequest | None = None,
    user: dict = Depends(get_current_user),
):
    force = body.force if body else False
    rescan = body.rescan if body else False

    existing = get_practice(place_id)
    if existing and existing.get("lead_score") is not None and not force and not rescan:
        return existing

    current_record = existing
    if existing and rescan:
        refreshed = await get_place(place_id, fallback=Practice(**_strip_joined(existing)))
        if refreshed:
            upsert_practices([refreshed], touched_by=user["id"])
            current_record = get_practice(place_id) or refreshed.model_dump()

    if current_record:
        name = current_record["name"]
        website = current_record.get("website")
        category = current_record.get("category")
        city = current_record.get("city")
        state = current_record.get("state")
    else:
        name = place_id
        website = None
        category = None
        city = None
        state = None

    analysis = await analyze_practice(place_id, name, website, category, city=city, state=state)

    if current_record:
        current_status = current_record.get("status", "NEW")
        if _should_auto_advance(current_status, "RESEARCHED"):
            analysis["status"] = "RESEARCHED"

    updated = update_practice_analysis(place_id, analysis, touched_by=user["id"])
    if updated:
        return updated

    if current_record:
        return {**current_record, **analysis}
    return {"place_id": place_id, "name": name, **analysis}


@app.post("/api/practices/{place_id}/rescan")
async def rescan_practice(place_id: str, user: dict = Depends(get_current_user)):
    existing = get_practice(place_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Practice not found")

    refreshed = await get_place(place_id, fallback=Practice(**_strip_joined(existing)))
    if not refreshed:
        return existing

    upsert_practices([refreshed], touched_by=user["id"])
    return get_practice(place_id) or refreshed.model_dump()


@app.get("/api/practices/{place_id}/script")
async def get_script(place_id: str, user: dict = Depends(get_current_user)):
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    if practice.get("call_script"):
        return json.loads(practice["call_script"])

    script = await generate_script(
        name=practice["name"],
        category=practice.get("category"),
        summary=practice.get("summary"),
        pain_points=practice.get("pain_points"),
        sales_angles=practice.get("sales_angles"),
    )

    update_practice_fields(place_id, {"call_script": json.dumps(script)}, touched_by=user["id"])

    current_status = practice.get("status", "NEW")
    if _should_auto_advance(current_status, "SCRIPT READY"):
        update_practice_fields(place_id, {"status": "SCRIPT READY"}, touched_by=user["id"])

    return script


@app.post("/api/practices/{place_id}/script")
async def regenerate_script_endpoint(place_id: str, user: dict = Depends(get_current_user)):
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    script = await generate_script(
        name=practice["name"],
        category=practice.get("category"),
        summary=practice.get("summary"),
        pain_points=practice.get("pain_points"),
        sales_angles=practice.get("sales_angles"),
    )

    update_practice_fields(place_id, {"call_script": json.dumps(script)}, touched_by=user["id"])
    return script


class PatchPracticeRequest(BaseModel):
    status: str | None = None
    notes: str | None = None
    email: str | None = None


@app.patch("/api/practices/{place_id}")
def patch_practice(
    place_id: str,
    body: PatchPracticeRequest,
    user: dict = Depends(get_current_user),
):
    fields: dict = {}
    if body.status is not None:
        if body.status not in STATUS_ORDER:
            raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
        fields["status"] = body.status
    if body.notes is not None:
        fields["notes"] = body.notes
    if body.email is not None:
        fields["email"] = body.email
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = update_practice_fields(place_id, fields, touched_by=user["id"])
    if not updated:
        raise HTTPException(status_code=404, detail="Practice not found")
    return updated


# ======================= Call log + Salesforce sync =======================


class CallLogRequest(BaseModel):
    note: str = ""


@app.post("/api/practices/{place_id}/call/log")
async def call_log_endpoint(
    place_id: str,
    body: CallLogRequest,
    user: dict = Depends(get_current_user),
):
    try:
        practice, warning = await append_call_note(place_id, body.note, user)
    except LookupError:
        raise HTTPException(404, "Practice not found")
    return {"practice": practice, "sf_warning": warning}


# ======================= Clay owner enrichment =======================


@app.post("/api/practices/{place_id}/enrich")
async def enrich_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    existing = get_practice(place_id)
    if not existing:
        raise HTTPException(404, "Practice not found")

    from src.models import Practice as _P

    try:
        trigger_result = await trigger_enrichment(_P(**existing))
    except Exception as e:
        final = update_practice_fields(
            place_id, {"enrichment_status": "failed"}, touched_by=None
        )
        return {"practice": final, "clay_warning": f"Enrichment trigger failed: {e}"}

    if trigger_result.get("skipped"):
        return {"practice": existing, "clay_warning": "Clay not configured. Enrichment skipped."}

    updated = update_practice_fields(place_id, {"enrichment_status": "pending"}, touched_by=None)
    return {"practice": updated, "clay_warning": None}
