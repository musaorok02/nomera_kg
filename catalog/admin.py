from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Brand, CarModel, Comment, Like, Photo, Region, Report


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


class CarModelInline(admin.TabularInline):
    model = CarModel
    extra = 1
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CarModelInline]


@admin.register(CarModel)
class CarModelAdmin(admin.ModelAdmin):
    list_display = ("name", "brand")
    list_filter = ("brand",)
    search_fields = ("name", "brand__name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("preview", "plate", "brand", "car_model", "user", "status", "views", "created_at")
    list_filter = ("status", "region", "brand")
    search_fields = ("plate", "description", "user__username")
    list_select_related = ("brand", "car_model", "user")
    raw_id_fields = ("user",)
    readonly_fields = ("views", "likes_count", "comments_count", "created_at", "moderated_at")
    actions = ["approve", "reject"]

    @admin.display(description="Фото")
    def preview(self, obj):
        if obj.thumb:
            return format_html('<img src="{}" style="height:48px;border-radius:4px">', obj.thumb.url)
        return "—"

    @admin.action(description="Опубликовать выбранные")
    def approve(self, request, queryset):
        queryset.update(status=Photo.Status.APPROVED, moderated_at=timezone.now(), reject_reason="")

    @admin.action(description="Отклонить выбранные")
    def reject(self, request, queryset):
        queryset.update(status=Photo.Status.REJECTED, moderated_at=timezone.now())


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("photo", "user", "short", "is_visible", "created_at")
    list_filter = ("is_visible",)
    search_fields = ("text", "user__username")
    raw_id_fields = ("photo", "user")

    @admin.display(description="Текст")
    def short(self, obj):
        return obj.text[:60]


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("photo", "user", "created_at")
    raw_id_fields = ("photo", "user")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("photo", "reason", "contact", "resolved", "created_at")
    list_filter = ("resolved", "reason")
    raw_id_fields = ("photo", "user")
