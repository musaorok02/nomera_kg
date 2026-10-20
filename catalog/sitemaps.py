from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Photo


class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return ["catalog:home", "catalog:new", "catalog:top", "catalog:directory", "catalog:stats"]

    def location(self, item):
        return reverse(item)


class PlateSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7
    limit = 5000

    def items(self):
        return list(
            Photo.objects.approved().order_by().values_list("plate", flat=True).distinct()
        )

    def location(self, item):
        return reverse("catalog:plate", args=[item])


class PhotoSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    limit = 5000

    def items(self):
        return Photo.objects.approved().order_by("-created_at")

    def lastmod(self, obj):
        return obj.moderated_at or obj.created_at
