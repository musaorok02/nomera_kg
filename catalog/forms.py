from uuid import uuid4

from django import forms
from django.conf import settings
from django.utils import timezone
from PIL import Image

from .images import process_upload
from .models import CarModel, Comment, Photo, Region, Report
from .plates import is_valid_plate, normalize_plate, region_code


class PhotoUploadForm(forms.ModelForm):
    plate = forms.CharField(
        label="Госномер", max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "01 KG 123 ABC", "autocomplete": "off"}),
    )

    class Meta:
        model = Photo
        fields = ["image", "plate", "brand", "car_model", "region", "city", "shot_date", "description"]
        widgets = {
            "shot_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.TextInput(attrs={"placeholder": "Например: на парковке у Ала-Арча"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["car_model"].queryset = CarModel.objects.select_related("brand")
        for name in ("brand", "car_model", "region"):
            self.fields[name].empty_label = "— не указано —"

    def clean_plate(self):
        plate = normalize_plate(self.cleaned_data["plate"])
        if not is_valid_plate(plate):
            raise forms.ValidationError("Не похоже на госномер. Пример: 01 KG 123 ABC.")
        return plate

    def clean_image(self):
        image = self.cleaned_data["image"]
        limit = settings.MAX_UPLOAD_MB * 1024 * 1024
        if image.size > limit:
            raise forms.ValidationError(f"Файл больше {settings.MAX_UPLOAD_MB} МБ.")
        image.seek(0)
        try:
            with Image.open(image) as img:
                if img.width < 400 or img.height < 300:
                    raise forms.ValidationError("Слишком маленькое фото (минимум 400×300).")
                if img.width * img.height > 60_000_000:
                    raise forms.ValidationError("Слишком большое разрешение фото.")
        finally:
            image.seek(0)
        return image

    def clean_shot_date(self):
        value = self.cleaned_data.get("shot_date")
        if value and value > timezone.localdate():
            raise forms.ValidationError("Дата съёмки не может быть в будущем.")
        return value

    def clean(self):
        data = super().clean()
        brand, model = data.get("brand"), data.get("car_model")
        if model and not brand:
            data["brand"] = model.brand
        elif model and brand and model.brand_id != brand.id:
            self.add_error("car_model", "Эта модель не относится к выбранной марке.")
        if not data.get("region") and data.get("plate"):
            code = region_code(data["plate"])
            if code:
                data["region"] = Region.objects.filter(code=code).first()
        return data

    def save(self, user, approved=False):
        photo = super().save(commit=False)
        main, thumb = process_upload(self.cleaned_data["image"], settings.WATERMARK_TEXT)
        photo.user = user
        photo.plate = self.cleaned_data["plate"]
        photo.brand = self.cleaned_data.get("brand")
        photo.region = self.cleaned_data.get("region")
        photo.status = Photo.Status.APPROVED if approved else Photo.Status.PENDING
        if approved:
            photo.moderated_at = timezone.now()
        name = f"{uuid4().hex}.jpg"
        photo.image.save(name, main, save=False)
        photo.thumb.save(name, thumb, save=False)
        photo.save()
        return photo


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3, "placeholder": "Ваш комментарий…"})}
        labels = {"text": ""}


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "text", "contact"]
        widgets = {"text": forms.Textarea(attrs={"rows": 4})}
        help_texts = {"contact": "Email или телефон, если нужен ответ (необязательно)."}
