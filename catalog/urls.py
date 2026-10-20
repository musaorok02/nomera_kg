from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("plate/<str:plate>/", views.plate_detail, name="plate"),
    path("photo/<int:pk>/", views.photo_detail, name="photo"),
    path("photo/<int:pk>/like/", views.toggle_like, name="like"),
    path("photo/<int:pk>/comment/", views.add_comment, name="comment"),
    path("photo/<int:pk>/report/", views.report_photo, name="report"),
    path("photo/<int:pk>/delete/", views.delete_photo, name="delete"),
    path("upload/", views.upload, name="upload"),
    path("new/", views.feed_new, name="new"),
    path("top/", views.feed_top, name="top"),
    path("catalog/", views.directory, name="directory"),
    path("brand/<slug:slug>/", views.brand_detail, name="brand"),
    path("brand/<slug:brand_slug>/<slug:model_slug>/", views.model_detail, name="model"),
    path("region/<str:code>/", views.region_detail, name="region"),
    path("user/<str:username>/", views.profile, name="profile"),
    path("stats/", views.stats, name="stats"),
    path("moderation/", views.moderation, name="moderation"),
    path("moderation/photo/<int:pk>/", views.moderate_photo, name="moderate_photo"),
    path("moderation/report/<int:pk>/", views.moderate_report, name="moderate_report"),
    path("api/search/", views.api_search, name="api_search"),
    path("api/models/", views.api_models, name="api_models"),
    path("api/plate/<str:plate>/", views.api_plate, name="api_plate"),
    path("rules/", TemplateView.as_view(template_name="pages/rules.html"), name="rules"),
    path("privacy/", TemplateView.as_view(template_name="pages/privacy.html"), name="privacy"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
]
