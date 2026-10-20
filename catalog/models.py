from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse

from .plates import format_plate


class Region(models.Model):
    code = models.CharField("Код", max_length=3, unique=True)
    name = models.CharField("Название", max_length=100)

    class Meta:
        ordering = ["code"]
        verbose_name = "регион"
        verbose_name_plural = "регионы"

    def __str__(self):
        return f"{self.code} — {self.name}"


class Brand(models.Model):
    name = models.CharField("Марка", max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "марка"
        verbose_name_plural = "марки"

    def __str__(self):
        return self.name


class CarModel(models.Model):
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="models")
    name = models.CharField("Модель", max_length=80)
    slug = models.SlugField(max_length=90)

    class Meta:
        ordering = ["brand__name", "name"]
        unique_together = [("brand", "slug")]
        verbose_name = "модель"
        verbose_name_plural = "модели"

    def __str__(self):
        return f"{self.brand.name} {self.name}"


class PhotoQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(status=Photo.Status.APPROVED)


class Photo(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "На модерации"
        APPROVED = "approved", "Опубликовано"
        REJECTED = "rejected", "Отклонено"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="photos"
    )
    plate = models.CharField("Госномер", max_length=12, db_index=True)
    region = models.ForeignKey(
        Region, null=True, blank=True, on_delete=models.SET_NULL, related_name="photos",
        verbose_name="Регион",
    )
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="photos",
        verbose_name="Марка",
    )
    car_model = models.ForeignKey(
        CarModel, null=True, blank=True, on_delete=models.SET_NULL, related_name="photos",
        verbose_name="Модель",
    )
    image = models.ImageField("Фото", upload_to="photos/%Y/%m/")
    thumb = models.ImageField("Миниатюра", upload_to="thumbs/%Y/%m/")
    description = models.CharField("Описание", max_length=300, blank=True)
    city = models.CharField("Город / место съёмки", max_length=100, blank=True)
    shot_date = models.DateField("Дата съёмки", null=True, blank=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    reject_reason = models.CharField("Причина отклонения", max_length=200, blank=True)
    views = models.PositiveIntegerField(default=0)
    likes_count = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    moderated_at = models.DateTimeField(null=True, blank=True)

    objects = PhotoQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "фото"
        verbose_name_plural = "фото"

    def __str__(self):
        return f"{self.plate_display} (#{self.pk})"

    @property
    def plate_display(self):
        return format_plate(self.plate)

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED

    def get_absolute_url(self):
        return reverse("catalog:photo", args=[self.pk])


@receiver(post_delete, sender=Photo)
def _delete_files(sender, instance, **kwargs):
    for field in (instance.image, instance.thumb):
        if field:
            field.delete(save=False)


class Comment(models.Model):
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments"
    )
    text = models.TextField("Комментарий", max_length=1000)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "комментарий"
        verbose_name_plural = "комментарии"

    def __str__(self):
        return f"{self.user} → #{self.photo_id}"


class Like(models.Model):
    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("photo", "user")]
        verbose_name = "лайк"
        verbose_name_plural = "лайки"


class Report(models.Model):
    class Reason(models.TextChoices):
        OWNER = "owner", "Я владелец авто и прошу убрать фото"
        PRIVACY = "privacy", "Видны лица или личные данные"
        WRONG = "wrong", "Неверный номер или марка"
        BAD = "bad", "Неприемлемое содержимое"
        COPYRIGHT = "copyright", "Нарушение авторских прав"
        OTHER = "other", "Другое"

    photo = models.ForeignKey(Photo, on_delete=models.CASCADE, related_name="reports")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reports",
    )
    reason = models.CharField("Причина", max_length=12, choices=Reason.choices)
    text = models.TextField("Пояснение", max_length=1000, blank=True)
    contact = models.CharField("Контакт для связи", max_length=120, blank=True)
    resolved = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "жалоба"
        verbose_name_plural = "жалобы"

    def __str__(self):
        return f"{self.get_reason_display()} — #{self.photo_id}"
