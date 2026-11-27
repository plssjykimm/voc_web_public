import logging
from collections import defaultdict
from datetime import date
from functools import wraps
from pathlib import PureWindowsPath
from urllib.parse import urlencode
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import VocForm, upload_mime
from .models import Attachment, Equipment, History, User, Voc, VocType


STATUSES = ("접수", "보류", "완료", "수용 불가")
TRANSITIONS = {"접수": ("보류", "완료", "수용 불가"), "보류": ("접수", "완료", "수용 불가")}
FILTERS = ("q", "status", "kind", "equipment", "mine", "start", "end")
logger = logging.getLogger(__name__)


def member_view(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role not in ("reporter", "developer"):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapped


def query_values(request, names):
    return {name: request.GET[name] for name in names if request.GET.get(name)}


def filtered(request, names):
    filters = query_values(request, names)
    records = Voc.objects.all()
    for name in ("start", "end"):
        if name in filters:
            try:
                bound = date.fromisoformat(filters[name])
            except ValueError:
                return records.none()
            lookup = "registered__gte" if name == "start" else "registered__lte"
            records = records.filter(**{lookup: bound})
    for name in ("kind", "equipment"):
        if name in filters:
            value = filters[name]
            if name == "equipment" and value == "common":
                records = records.filter(equipment__isnull=True)
                continue
            if not value.isascii() or not value.isdigit() or len(value) > 18:
                return records.none()
            lookup = "kind_id" if name == "kind" else "equipment__pk"
            records = records.filter(**{lookup: value})
    if "status" in filters:
        records = records.filter(status=filters["status"])
    if filters.get("mine") == "1":
        records = records.filter(reporter=request.user)
    if "q" in filters:
        needle = filters["q"].strip()
        lookup = Q(title__icontains=needle) | Q(screen__icontains=needle)
        number = needle.removeprefix("#")
        if number.isascii() and number.isdigit() and len(number) <= 18:
            lookup |= Q(pk=int(number))
        records = records.filter(lookup)
    return records


@require_GET
@member_view
def vocs(request):
    records = filtered(request, FILTERS).select_related("kind", "reporter").prefetch_related("equipment")
    page = Paginator(records.order_by("-registered", "-created", "-pk"), 20).get_page(request.GET.get("page"))
    return render(request, "vocs.html", {
        "page": page, "statuses": STATUSES, "kinds": VocType.objects.order_by("position", "pk"),
        "equipment": Equipment.objects.order_by("name"), "query": urlencode(query_values(request, FILTERS)),
        "back_query": urlencode(query_values(request, FILTERS + ("page",))),
    })


def store_voc(user, data):
    saved = []
    try:
        with transaction.atomic():
            reporter = User.objects.select_for_update().get(pk=data["reporter"].pk, is_active=True,
                                                          role__in=("reporter", "developer"))
            voc = Voc.objects.create(reporter=reporter, creator=user, status="접수",
                                     **{k: data[k] for k in ("registered", "kind", "title", "body", "screen")})
            voc.equipment.set(data["equipment"])
            for upload in data["files"]:
                name = PureWindowsPath(upload.name).name
                item = Attachment(voc=voc, kind="file", name=name, size=upload.size, mime=upload_mime(upload))
                item.file.save(uuid4().hex, upload, save=False)
                saved.append((item.file.storage, item.file.name))
                item.save()
            for kind, address in data["links"]:
                Attachment.objects.create(voc=voc, kind=kind, name=address[:255], address=address)
            History.objects.create(voc=voc, before="", after="접수", reason="", actor=user)
        return voc
    except Exception:
        for storage, key in saved:
            try:
                storage.delete(key)
            except OSError:
                logger.exception("첨부 저장 취소 중 파일 정리에 실패했습니다.")
        raise


@require_http_methods(["GET", "POST"])
@member_view
def new(request):
    form = VocForm(request.POST if request.method == "POST" else None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            voc = store_voc(request.user, form.cleaned_data)
        except User.DoesNotExist:
            form.add_error("reporter", "활성 회원을 선택해 주세요.")
        except OSError:
            form.add_error(None, "파일을 저장하지 못했습니다. 첨부파일을 다시 선택해 주세요.")
        else:
            return redirect("detail", pk=voc.pk)
    return render(request, "new.html", {"form": form})


def detail_response(request, pk, error="", http_status=200):
    voc = get_object_or_404(Voc.objects.select_related("kind", "reporter", "creator").prefetch_related("equipment"), pk=pk)
    items = list(Attachment.objects.filter(voc=voc).order_by("pk"))
    for item in items:
        item.previewable = item.kind == "file" and item.mime in ("image/png", "image/jpeg", "image/gif", "image/webp")
    history = list(History.objects.filter(voc=voc).select_related("actor").order_by("-pk"))
    reason = history[0].reason if history and voc.status in ("보류", "수용 불가") else ""
    return render(request, "detail.html", {
        "voc": voc, "attachments": items, "history": history, "current_reason": reason, "error": error,
        "transitions": TRANSITIONS.get(voc.status, ()) if request.user.role == "developer" else (),
        "today": timezone.localdate().isoformat(), "back_query": urlencode(query_values(request, FILTERS + ("page",))),
    }, status=http_status)


@require_GET
@member_view
def detail(request, pk):
    return detail_response(request, pk)


@require_POST
@member_view
def transition(request, pk):
    if request.user.role != "developer":
        raise PermissionDenied
    current = get_object_or_404(Voc, pk=pk)
    target = request.POST.get("status", "")
    reason = request.POST.get("reason", "").strip() if target in ("보류", "수용 불가") else ""
    completed = None
    if str(current.version) == request.POST.get("version"):
        if target not in TRANSITIONS.get(current.status, ()):
            return detail_response(request, pk, "현재 상태에서 선택할 수 없는 처리입니다.", 400)
        if target in ("보류", "수용 불가") and not reason:
            return detail_response(request, pk, "처리 사유를 입력해 주세요.", 400)
        if target == "완료":
            try:
                completed = date.fromisoformat(request.POST.get("completed", ""))
            except ValueError:
                return detail_response(request, pk, "완료일을 입력해 주세요.", 400)
        with transaction.atomic():
            changed = Voc.objects.filter(pk=pk, version=current.version, status=current.status).update(
                status=target, version=F("version") + 1
            )
            if changed:
                History.objects.create(voc=current, before=current.status, after=target, actor=request.user,
                                       reason=reason, completed=completed)
        if changed:
            query = urlencode(query_values(request, FILTERS + ("page",)))
            return redirect(reverse("detail", args=[pk]) + ("?" + query if query else ""))
    latest = History.objects.select_related("actor").filter(voc_id=pk).latest("pk")
    return detail_response(request, pk, f"{latest.actor.name}님이 먼저 처리했습니다. 현재 상태는 {latest.after}입니다.", 409)


@require_GET
@member_view
def attachment(request, pk):
    item = get_object_or_404(Attachment, pk=pk, kind="file")
    try:
        opened = item.file.open("rb")
    except FileNotFoundError:
        raise Http404("첨부파일을 찾을 수 없습니다.")
    preview = request.GET.get("preview") == "1" and item.mime in ("image/png", "image/jpeg", "image/gif", "image/webp")
    response = FileResponse(opened, content_type=item.mime if preview else "application/octet-stream",
                            as_attachment=not preview, filename=item.name)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
@member_view
def dashboard(request):
    dimensions = ("start", "end", "equipment")
    params = query_values(request, dimensions)
    records = filtered(request, dimensions)
    grouped = records.order_by().values("kind_id", "status").annotate(n=Count("pk"))
    counts = defaultdict(int)
    totals = defaultdict(int)
    for group in grouped:
        counts[group["kind_id"], group["status"]] = group["n"]
        totals[group["status"]] += group["n"]
    total = sum(totals.values())
    rate = f'{totals["완료"] / total:.1%}' if total else "—"

    def list_link(**extra):
        query = urlencode({**params, **extra})
        return reverse("vocs") + ("?" + query if query else "")

    cards = [{"name": "전체", "count": total, "url": list_link()}]
    cards.extend({"name": state, "count": totals[state], "url": list_link(status=state)} for state in STATUSES)
    rows = []
    for kind in VocType.objects.order_by("position", "pk"):
        segments = [{"status": state, "count": counts[kind.pk, state], "url": list_link(kind=kind.pk, status=state)}
                    for state in STATUSES]
        rows.append({"name": kind.name, "total": sum(s["count"] for s in segments), "segments": segments})
    max_total = max((row["total"] for row in rows), default=0)
    for row in rows:
        for segment in row["segments"]:
            segment["width"] = format(100 * segment["count"] / max_total, ".4f") if max_total else "0"

    equipment_counts = (
        records.values("equipment__id", "equipment__name")
        .annotate(count=Count("pk", distinct=True))
        .order_by("-count", "equipment__name", "equipment__id")
    )
    equipment_rows = []
    for group in equipment_counts:
        key = str(group["equipment__id"] or "common")
        if params.get("equipment", key) != key:
            continue
        equipment_rows.append({
            "name": group["equipment__name"] or "공통",
            "count": group["count"],
            "url": list_link(equipment=key),
        })
    assignments = sum(row["count"] for row in equipment_rows)
    gradient = []
    offset = 0
    for index, row in enumerate(equipment_rows):
        row["color"] = f"hsl({(205 + 137 * index) % 360} 64% 43%)"
        end = offset + row["count"]
        gradient.append(f'{row["color"]} {offset / assignments:.8f}turn {end / assignments:.8f}turn')
        offset = end
    return render(request, "dashboard.html", {
        "cards": cards, "rate": rate, "rate_url": list_link(status="완료"), "rows": rows, "max_total": max_total,
        "statuses": STATUSES, "equipment": Equipment.objects.order_by("name"),
        "equipment_rows": equipment_rows, "equipment_gradient": ", ".join(gradient), "voc_total": total,
    })
