import shutil
import tempfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Brand, Comment, Like, Photo, Region, Report
from .plates import format_plate, is_valid_plate, normalize_plate, region_code

MEDIA = tempfile.mkdtemp()
PLATE_TAG = '<span class="plate">01 KG 123 ABC</span>'


def make_image(w=800, h=600):
    buf = BytesIO()
    Image.new("RGB", (w, h), (120, 160, 200)).save(buf, "JPEG")
    return SimpleUploadedFile("car.jpg", buf.getvalue(), content_type="image/jpeg")


class PlateTests(TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_plate("01 KG 123 abc"), "01123ABC")
        self.assertEqual(normalize_plate("01KG123ABC"), "01123ABC")
        self.assertEqual(normalize_plate("01 123 АВС"), "01123ABC")  # кириллица
        self.assertEqual(normalize_plate("  "), "")

    def test_format_and_region(self):
        self.assertEqual(format_plate("01123ABC"), "01 KG 123 ABC")
        self.assertEqual(format_plate("B1234AB"), "B1234AB")
        self.assertEqual(region_code("08123ABC"), "08")
        self.assertIsNone(region_code("XYZ"))

    def test_valid(self):
        self.assertTrue(is_valid_plate("01123ABC"))
        self.assertFalse(is_valid_plate("ABC"))
        self.assertFalse(is_valid_plate("ABCDEF"))


@override_settings(MEDIA_ROOT=MEDIA, WATERMARK_TEXT="test.kg")
class SiteTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        call_command("seed_data", verbosity=0)
        self.user = User.objects.create_user("alice", "a@example.com", "pass12345!")
        self.staff = User.objects.create_user("mod", "m@example.com", "pass12345!", is_staff=True)

    def upload(self, user, plate="01 KG 123 ABC", **extra):
        self.client.force_login(user)
        data = {"image": make_image(), "plate": plate, **extra}
        return self.client.post(reverse("catalog:upload"), data)

    def test_seed(self):
        self.assertTrue(Region.objects.filter(code="01", name="Бишкек").exists())
        self.assertTrue(Brand.objects.filter(slug="toyota").exists())

    def test_pages_open(self):
        for name in ("home", "new", "top", "directory", "stats", "rules", "privacy", "about", "search"):
            self.assertEqual(self.client.get(reverse(f"catalog:{name}")).status_code, 200, name)
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)

    def test_upload_requires_login(self):
        resp = self.client.get(reverse("catalog:upload"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_upload_goes_to_moderation_and_is_hidden(self):
        resp = self.upload(self.user)
        photo = Photo.objects.get()
        self.assertRedirects(resp, photo.get_absolute_url())
        self.assertEqual(photo.status, Photo.Status.PENDING)
        self.assertEqual(photo.plate, "01123ABC")
        self.assertEqual(photo.region.code, "01")  # определён по номеру
        self.assertTrue(photo.image.name.endswith(".jpg") and photo.thumb.name.endswith(".jpg"))
        self.client.logout()
        self.assertEqual(self.client.get(photo.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("catalog:search"), {"q": "123"}), PLATE_TAG)
        self.assertEqual(self.client.get(reverse("catalog:plate", args=["01123ABC"])).status_code, 404)

    def test_staff_upload_auto_approved(self):
        self.upload(self.staff, plate="02KG777AAA")
        self.assertEqual(Photo.objects.get().status, Photo.Status.APPROVED)

    def test_bad_uploads(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("catalog:upload"), {"image": make_image(), "plate": "!!"})
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse("catalog:upload"), {"image": make_image(100, 100), "plate": "01KG123ABC"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Photo.objects.count(), 0)

    def test_moderation_flow_and_search(self):
        self.upload(self.user, brand=Brand.objects.get(slug="toyota").pk)
        photo = Photo.objects.get()

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("catalog:moderation")).status_code, 302)
        self.assertEqual(
            self.client.post(reverse("catalog:moderate_photo", args=[photo.pk]), {"action": "approve"}).status_code, 302
        )
        photo.refresh_from_db()
        self.assertEqual(photo.status, Photo.Status.PENDING)

        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("catalog:moderation")).status_code, 200)
        self.client.post(reverse("catalog:moderate_photo", args=[photo.pk]), {"action": "approve"})
        photo.refresh_from_db()
        self.assertEqual(photo.status, Photo.Status.APPROVED)

        self.client.logout()
        for q in ("01 KG 123 ABC", "123abc", "01123"):
            self.assertContains(self.client.get(reverse("catalog:search"), {"q": q}), PLATE_TAG)
        self.assertContains(self.client.get(reverse("catalog:plate", args=["01123ABC"])), PLATE_TAG)
        self.assertEqual(self.client.get(reverse("catalog:photo", args=[photo.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("catalog:brand", args=["toyota"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("catalog:region", args=["01"])).status_code, 200)

        api = self.client.get(reverse("catalog:api_plate", args=["01 KG 123 ABC"])).json()
        self.assertTrue(api["found"])
        self.assertEqual(self.client.get(reverse("catalog:api_search"), {"q": "123"}).json()["results"][0]["plate"], "01123ABC")

    def test_reject(self):
        self.upload(self.user)
        photo = Photo.objects.get()
        self.client.force_login(self.staff)
        self.client.post(reverse("catalog:moderate_photo", args=[photo.pk]), {"action": "reject", "reason": "размыто"})
        photo.refresh_from_db()
        self.assertEqual((photo.status, photo.reject_reason), (Photo.Status.REJECTED, "размыто"))

    def _approved(self):
        self.upload(self.staff, plate="01KG555BBB")
        return Photo.objects.get()

    def test_like_toggle_and_comment(self):
        photo = self._approved()
        self.client.force_login(self.user)
        self.client.post(reverse("catalog:like", args=[photo.pk]))
        photo.refresh_from_db()
        self.assertEqual(photo.likes_count, 1)
        resp = self.client.post(reverse("catalog:like", args=[photo.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.json(), {"liked": False, "count": 0})
        self.assertEqual(Like.objects.count(), 0)

        self.client.post(reverse("catalog:comment", args=[photo.pk]), {"text": "Классная машина"})
        photo.refresh_from_db()
        self.assertEqual(photo.comments_count, 1)
        self.assertContains(self.client.get(photo.get_absolute_url()), "Классная машина")
        self.client.post(reverse("catalog:comment", args=[photo.pk]), {"text": "   "})
        self.assertEqual(Comment.objects.count(), 1)

    def test_like_requires_login(self):
        photo = self._approved()
        self.client.logout()
        resp = self.client.post(reverse("catalog:like", args=[photo.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Like.objects.count(), 0)

    def test_report_and_takedown(self):
        photo = self._approved()
        self.client.logout()
        resp = self.client.post(
            reverse("catalog:report", args=[photo.pk]), {"reason": "owner", "text": "Моя машина", "contact": "x@y.kg"}
        )
        self.assertEqual(resp.status_code, 302)
        report = Report.objects.get()
        self.assertFalse(report.resolved)

        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("catalog:moderation"), {"tab": "reports"}), "Моя машина")
        self.client.post(reverse("catalog:moderate_report", args=[report.pk]), {"action": "remove_photo"})
        photo.refresh_from_db()
        self.assertEqual(photo.status, Photo.Status.REJECTED)
        report.refresh_from_db()
        self.assertTrue(report.resolved)

    def test_delete_by_owner_only(self):
        photo = self._approved()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse("catalog:delete", args=[photo.pk])).status_code, 404)
        self.client.force_login(self.staff)
        self.client.post(reverse("catalog:delete", args=[photo.pk]))
        self.assertEqual(Photo.objects.count(), 0)

    def test_register_and_profile(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "bob", "email": "bob@example.com", "password1": "Str0ng-pass!", "password2": "Str0ng-pass!",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="bob").exists())
        self.assertEqual(self.client.get(reverse("catalog:profile", args=["bob"])).status_code, 200)
