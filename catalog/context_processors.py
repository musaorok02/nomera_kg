from django.conf import settings


def site(request):
    ctx = {"SITE_NAME": settings.SITE_NAME, "MAX_UPLOAD_MB": settings.MAX_UPLOAD_MB}
    user = getattr(request, "user", None)
    if user is not None and user.is_staff:
        from .models import Photo, Report

        ctx["pending_count"] = Photo.objects.filter(status=Photo.Status.PENDING).count()
        ctx["open_reports"] = Report.objects.filter(resolved=False).count()
    return ctx
