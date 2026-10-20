from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Count, F, Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import CommentForm, PhotoUploadForm, ReportForm
from .models import Brand, CarModel, Comment, Like, Photo, Region, Report
from .plates import format_plate, normalize_plate

User = get_user_model()
PAGE_SIZE = 24


def _photos():
    return Photo.objects.approved().select_related("brand", "car_model", "region", "user")


def _page(request, qs, per_page=PAGE_SIZE):
    return Paginator(qs, per_page).get_page(request.GET.get("page"))


def _throttle(key, limit, seconds):
    """Простое ограничение частоты. True — лимит превышен."""
    cache.add(key, 0, seconds)
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, seconds)
        return False


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


is_staff = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="accounts:login")


# ───────────────────────── главная и поиск ─────────────────────────

def home(request):
    week_ago = timezone.now() - timedelta(days=7)
    ctx = {
        "latest": _photos()[:12],
        "top": _photos().filter(created_at__gte=week_ago).order_by("-likes_count", "-views")[:6],
        "brands": Brand.objects.annotate(
            n=Count("photos", filter=Q(photos__status=Photo.Status.APPROVED))
        ).filter(n__gt=0).order_by("-n")[:12],
        "regions": Region.objects.annotate(
            n=Count("photos", filter=Q(photos__status=Photo.Status.APPROVED))
        ).filter(n__gt=0).order_by("-n")[:10],
        "total_photos": Photo.objects.approved().count(),
        "total_plates": Photo.objects.approved().values("plate").distinct().count(),
        "total_users": User.objects.filter(photos__status=Photo.Status.APPROVED).distinct().count(),
    }
    return render(request, "catalog/home.html", ctx)


def search(request):
    q = request.GET.get("q", "").strip()
    region = request.GET.get("region", "").strip()
    brand = request.GET.get("brand", "").strip()
    norm = normalize_plate(q)

    qs = _photos()
    if norm:
        qs = qs.filter(plate__contains=norm)
    if region:
        qs = qs.filter(region__code=region)
    if brand:
        qs = qs.filter(brand__slug=brand)
    searched = bool(norm or region or brand)
    if not searched:
        qs = qs.none()

    plates = []
    if searched and norm:
        rows = (
            qs.order_by().values("plate").annotate(n=Count("id"), last=Max("created_at"))
            .order_by("-last")[:30]
        )
        plates = [{"plate": r["plate"], "display": format_plate(r["plate"]), "n": r["n"]} for r in rows]

    ctx = {
        "q": q,
        "norm": norm,
        "searched": searched,
        "page": _page(request, qs),
        "plates": plates,
        "regions": Region.objects.all(),
        "brands": Brand.objects.all(),
        "sel_region": region,
        "sel_brand": brand,
    }
    return render(request, "catalog/search.html", ctx)


# ───────────────────────── номера и фото ─────────────────────────

def plate_detail(request, plate):
    norm = normalize_plate(plate)
    photos = _photos().filter(plate=norm)
    if not photos.exists():
        raise Http404
    first = photos.first()
    brands = sorted({f"{p.brand} {p.car_model or ''}".strip() for p in photos if p.brand})
    ctx = {
        "plate": norm,
        "display": format_plate(norm),
        "page": _page(request, photos),
        "count": photos.count(),
        "brands": brands,
        "region": first.region,
    }
    return render(request, "catalog/plate.html", ctx)


def photo_detail(request, pk):
    photo = get_object_or_404(Photo.objects.select_related("brand", "car_model", "region", "user"), pk=pk)
    if not photo.is_approved and not (
        request.user.is_authenticated and (request.user.is_staff or request.user == photo.user)
    ):
        raise Http404

    if photo.is_approved:
        viewed = request.session.get("viewed", [])
        if photo.pk not in viewed:
            Photo.objects.filter(pk=photo.pk).update(views=F("views") + 1)
            photo.views += 1
            request.session["viewed"] = (viewed + [photo.pk])[-200:]

    liked = request.user.is_authenticated and photo.likes.filter(user=request.user).exists()
    ctx = {
        "photo": photo,
        "comments": photo.comments.filter(is_visible=True).select_related("user"),
        "comment_form": CommentForm(),
        "liked": liked,
        "same_plate": _photos().filter(plate=photo.plate).exclude(pk=photo.pk)[:6],
        "similar": (
            _photos().filter(car_model=photo.car_model).exclude(pk=photo.pk)[:6]
            if photo.car_model_id else []
        ),
    }
    return render(request, "catalog/photo.html", ctx)


@login_required
def upload(request):
    since = timezone.now() - timedelta(days=1)
    used = Photo.objects.filter(user=request.user, created_at__gte=since).count()
    if used >= settings.UPLOADS_PER_DAY:
        messages.error(request, f"Достигнут лимит: {settings.UPLOADS_PER_DAY} фото в сутки.")
        return redirect("catalog:profile", username=request.user.username)

    form = PhotoUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        auto = settings.AUTO_APPROVE_STAFF and request.user.is_staff
        photo = form.save(request.user, approved=auto)
        if auto:
            messages.success(request, "Фото опубликовано.")
        else:
            messages.success(request, "Фото загружено и появится на сайте после проверки модератором.")
        return redirect(photo)
    return render(request, "catalog/upload.html", {"form": form})


@require_POST
@login_required
def delete_photo(request, pk):
    photo = get_object_or_404(Photo, pk=pk)
    if request.user != photo.user and not request.user.is_staff:
        raise Http404
    photo.delete()
    messages.success(request, "Фото удалено.")
    return redirect("catalog:profile", username=request.user.username)


@require_POST
@login_required
def toggle_like(request, pk):
    photo = get_object_or_404(Photo.objects.approved(), pk=pk)
    like, created = Like.objects.get_or_create(photo=photo, user=request.user)
    if not created:
        like.delete()
    photo.likes_count = photo.likes.count()
    photo.save(update_fields=["likes_count"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"liked": created, "count": photo.likes_count})
    return redirect(photo)


@require_POST
@login_required
def add_comment(request, pk):
    photo = get_object_or_404(Photo.objects.approved(), pk=pk)
    if _throttle(f"comment:{request.user.pk}", 10, 300):
        messages.error(request, "Слишком часто. Подождите несколько минут.")
        return redirect(photo)
    form = CommentForm(request.POST)
    if form.is_valid():
        Comment.objects.create(photo=photo, user=request.user, text=form.cleaned_data["text"].strip())
        photo.comments_count = photo.comments.filter(is_visible=True).count()
        photo.save(update_fields=["comments_count"])
        messages.success(request, "Комментарий добавлен.")
    else:
        messages.error(request, "Комментарий не должен быть пустым или длиннее 1000 символов.")
    return redirect(photo)


def report_photo(request, pk):
    photo = get_object_or_404(Photo.objects.approved(), pk=pk)
    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _throttle(f"report:{_client_ip(request)}", 5, 3600):
            messages.error(request, "Слишком много жалоб с вашего адреса. Попробуйте позже.")
            return redirect(photo)
        report = form.save(commit=False)
        report.photo = photo
        if request.user.is_authenticated:
            report.user = request.user
        report.save()
        messages.success(request, "Спасибо! Жалоба отправлена модераторам.")
        return redirect(photo)
    return render(request, "catalog/report.html", {"photo": photo, "form": form})


# ───────────────────────── ленты и каталог ─────────────────────────

def feed_new(request):
    return render(request, "catalog/photo_list.html", {
        "title": "Новые фото", "page": _page(request, _photos()),
    })


def feed_top(request):
    period = request.GET.get("period", "week")
    days = {"day": 1, "week": 7, "month": 30}.get(period)
    qs = _photos()
    if days:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=days))
    else:
        period = "all"
    qs = qs.order_by("-likes_count", "-views", "-created_at")
    return render(request, "catalog/photo_list.html", {
        "title": "Лучшие фото", "page": _page(request, qs), "period": period, "show_period": True,
    })


def directory(request):
    ok = Q(photos__status=Photo.Status.APPROVED)
    ctx = {
        "brands": Brand.objects.annotate(n=Count("photos", filter=ok)).order_by("name"),
        "regions": Region.objects.annotate(n=Count("photos", filter=ok)),
    }
    return render(request, "catalog/directory.html", ctx)


def brand_detail(request, slug):
    brand = get_object_or_404(Brand, slug=slug)
    ok = Q(photos__status=Photo.Status.APPROVED)
    ctx = {
        "title": brand.name,
        "page": _page(request, _photos().filter(brand=brand)),
        "models": brand.models.annotate(n=Count("photos", filter=ok)).order_by("name"),
        "brand": brand,
    }
    return render(request, "catalog/photo_list.html", ctx)


def model_detail(request, brand_slug, model_slug):
    model = get_object_or_404(CarModel.objects.select_related("brand"), brand__slug=brand_slug, slug=model_slug)
    ctx = {
        "title": f"{model.brand.name} {model.name}",
        "page": _page(request, _photos().filter(car_model=model)),
        "brand": model.brand,
    }
    return render(request, "catalog/photo_list.html", ctx)


def region_detail(request, code):
    region = get_object_or_404(Region, code=code)
    ctx = {
        "title": f"Регион {region.code} — {region.name}",
        "page": _page(request, _photos().filter(region=region)),
    }
    return render(request, "catalog/photo_list.html", ctx)


def profile(request, username):
    owner = get_object_or_404(User, username=username)
    qs = Photo.objects.filter(user=owner).select_related("brand", "car_model")
    is_owner = request.user.is_authenticated and request.user == owner
    if not is_owner:
        qs = qs.filter(status=Photo.Status.APPROVED)
    approved = Photo.objects.approved().filter(user=owner)
    ctx = {
        "owner": owner,
        "is_owner": is_owner,
        "page": _page(request, qs),
        "photo_count": approved.count(),
        "plate_count": approved.values("plate").distinct().count(),
        "likes_total": sum(approved.values_list("likes_count", flat=True)),
    }
    return render(request, "catalog/profile.html", ctx)


def stats(request):
    ok = Q(photos__status=Photo.Status.APPROVED)
    approved = Photo.objects.approved()
    ctx = {
        "total_photos": approved.count(),
        "total_plates": approved.values("plate").distinct().count(),
        "total_comments": Comment.objects.filter(is_visible=True, photo__status=Photo.Status.APPROVED).count(),
        "regions": Region.objects.annotate(n=Count("photos", filter=ok)).filter(n__gt=0).order_by("-n"),
        "brands": Brand.objects.annotate(n=Count("photos", filter=ok)).filter(n__gt=0).order_by("-n")[:15],
        "top_plates": [
            {"plate": r["plate"], "display": format_plate(r["plate"]), "n": r["n"]}
            for r in approved.order_by().values("plate").annotate(n=Count("id")).order_by("-n")[:15]
        ],
        "top_users": User.objects.annotate(
            n=Count("photos", filter=Q(photos__status=Photo.Status.APPROVED))
        ).filter(n__gt=0).order_by("-n")[:10],
    }
    for key in ("regions", "brands"):
        items = list(ctx[key])
        peak = items[0].n if items else 1
        for item in items:
            item.pct = round(item.n * 100 / peak)
        ctx[key] = items
    return render(request, "catalog/stats.html", ctx)


# ───────────────────────── модерация ─────────────────────────

@is_staff
def moderation(request):
    tab = request.GET.get("tab", "pending")
    if tab == "reports":
        qs = Report.objects.filter(resolved=False).select_related("photo", "user")
    else:
        tab = "pending"
        qs = Photo.objects.filter(status=Photo.Status.PENDING).select_related("user", "brand", "car_model").order_by("created_at")
    return render(request, "catalog/moderation.html", {"tab": tab, "page": _page(request, qs, 20)})


@require_POST
@is_staff
def moderate_photo(request, pk):
    photo = get_object_or_404(Photo, pk=pk)
    action = request.POST.get("action")
    if action == "approve":
        photo.status = Photo.Status.APPROVED
        photo.reject_reason = ""
    elif action == "reject":
        photo.status = Photo.Status.REJECTED
        photo.reject_reason = request.POST.get("reason", "").strip()[:200]
    else:
        raise Http404
    photo.moderated_at = timezone.now()
    photo.save(update_fields=["status", "reject_reason", "moderated_at"])
    messages.success(request, f"Фото #{photo.pk}: {photo.get_status_display().lower()}.")
    return redirect(request.POST.get("next") or "catalog:moderation")


@require_POST
@is_staff
def moderate_report(request, pk):
    report = get_object_or_404(Report.objects.select_related("photo"), pk=pk)
    action = request.POST.get("action")
    if action == "remove_photo":
        photo = report.photo
        photo.status = Photo.Status.REJECTED
        photo.reject_reason = "Удалено по жалобе"
        photo.moderated_at = timezone.now()
        photo.save(update_fields=["status", "reject_reason", "moderated_at"])
        report.photo.reports.update(resolved=True)
        messages.success(request, "Фото скрыто, жалобы закрыты.")
    elif action == "dismiss":
        report.resolved = True
        report.save(update_fields=["resolved"])
        messages.success(request, "Жалоба закрыта.")
    else:
        raise Http404
    return redirect("/moderation/?tab=reports")


# ───────────────────────── JSON API ─────────────────────────

def _photo_json(p):
    return {
        "id": p.pk,
        "plate": p.plate,
        "plate_display": p.plate_display,
        "brand": p.brand.name if p.brand else None,
        "model": p.car_model.name if p.car_model else None,
        "region": p.region.code if p.region else None,
        "thumb": p.thumb.url,
        "url": p.get_absolute_url(),
        "likes": p.likes_count,
        "created_at": p.created_at.isoformat(),
    }


@require_GET
def api_search(request):
    norm = normalize_plate(request.GET.get("q", ""))
    if len(norm) < 2:
        return JsonResponse({"query": norm, "results": []})
    photos = _photos().filter(plate__contains=norm)[:20]
    return JsonResponse({"query": norm, "results": [_photo_json(p) for p in photos]})


@require_GET
def api_plate(request, plate):
    norm = normalize_plate(plate)
    photos = list(_photos().filter(plate=norm)[:100])
    if not photos:
        return JsonResponse({"plate": norm, "found": False, "photos": []}, status=404)
    return JsonResponse({
        "plate": norm, "display": format_plate(norm), "found": True,
        "count": len(photos), "photos": [_photo_json(p) for p in photos],
    })


@require_GET
def api_models(request):
    try:
        brand_id = int(request.GET.get("brand", ""))
    except ValueError:
        return JsonResponse({"models": []})
    items = CarModel.objects.filter(brand_id=brand_id).values("id", "name")
    return JsonResponse({"models": list(items)})
