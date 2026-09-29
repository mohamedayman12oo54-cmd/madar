"""Phase 5 — Content + the internal Video abstraction."""
import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase

from academics.models import Grade
from environments.tenancy_testing import TenantTestCase

from .models import ContentItem
from .video import VideoRefError, describe_video, validate_video

URL = "/api/v1/content/"
YT = "dQw4w9WgXcQ"  # a syntactically valid 11-char id


def item_url(pk):
    return f"{URL}{pk}/"


class VideoAbstractionTests(SimpleTestCase):
    def test_youtube_ref_builds_a_nocookie_embed_url(self):
        info = describe_video("youtube", YT)
        self.assertEqual(info["provider"], "youtube")
        self.assertEqual(info["embed_url"], f"https://www.youtube-nocookie.com/embed/{YT}")
        self.assertTrue(info["thumbnail_url"].endswith(f"/{YT}/hqdefault.jpg"))

    def test_vimeo_ref_builds_an_embed_url(self):
        info = describe_video("vimeo", "123456789")
        self.assertEqual(info["embed_url"], "https://player.vimeo.com/video/123456789")
        self.assertIsNone(info["thumbnail_url"])

    def test_no_provider_or_empty_ref_means_no_video(self):
        self.assertIsNone(describe_video("none", ""))
        self.assertIsNone(describe_video("youtube", ""))
        self.assertIsNone(describe_video("nonexistent", "x"))

    def test_only_strict_ids_are_accepted_never_urls_or_odd_strings(self):
        bad_youtube = [
            "https://evil.example/x", "javascript:alert(1)", YT + "?autoplay=1", YT[:-1], YT + "x",
            "../../etc/passwd", "<script>alert(1)</script>", "", "  ",
        ]
        for bad in bad_youtube:
            with self.subTest(provider="youtube", ref=bad):
                with self.assertRaises(VideoRefError):
                    validate_video("youtube", bad)
        for bad in ("abc", "12345", "1234567890123", "https://vimeo.com/123456", "123456/../x"):
            with self.subTest(provider="vimeo", ref=bad):
                with self.assertRaises(VideoRefError):
                    validate_video("vimeo", bad)

    def test_unsupported_provider_rejected_and_none_forbids_a_ref(self):
        with self.assertRaises(VideoRefError):
            validate_video("dailymotion", "abc")
        with self.assertRaises(VideoRefError):
            validate_video("none", "something")
        self.assertEqual(validate_video("none", ""), "")


class ContentApiTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.grade_b = Grade.objects.create(environment=self.env_b, name="أول")

    def post(self, **body):
        return self.client_a.post(URL, body, **self.with_env(self.env_a.id))

    def test_create_text_only_content(self):
        r = self.post(title="ملخص الوحدة الأولى", description="نص")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.json()["video"])
        self.assertIsNone(r.json()["grade"])

    def test_create_with_video_returns_provider_neutral_embed_and_hides_the_raw_ref(self):
        r = self.post(title="فيديو", video_provider="youtube", video_ref=YT, grade_id=self.grade.id)
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["video"]["provider"], "youtube")
        self.assertIn(YT, body["video"]["embed_url"])
        self.assertNotIn("video_ref", body)
        self.assertNotIn("video_provider", body)
        self.assertEqual(body["grade"]["id"], self.grade.id)

    def test_url_instead_of_an_id_is_rejected(self):
        r = self.post(title="x", video_provider="youtube", video_ref="https://www.youtube.com/watch?v=" + YT)
        self.assertEqual(r.status_code, 400)
        self.assertIn("video_ref", r.json()["fields"])
        self.assertFalse(ContentItem.objects.exists())

    def test_ref_without_a_provider_rejected(self):
        r = self.post(title="x", video_ref=YT)
        self.assertEqual(r.status_code, 400)

    def test_blank_title_rejected(self):
        self.assertEqual(self.post(title="  ").status_code, 400)

    def test_cannot_attach_another_teachers_grade(self):
        r = self.post(title="x", grade_id=self.grade_b.id)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ContentItem.objects.exists())

    def test_list_scoped_filterable_and_searchable(self):
        ContentItem.objects.create(environment=self.env_a, title="جبر", grade=self.grade)
        ContentItem.objects.create(environment=self.env_a, title="هندسة")
        ContentItem.objects.create(environment=self.env_b, title="جبر لآخر", grade=self.grade_b)
        all_a = self.client_a.get(URL, **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual({c["title"] for c in all_a}, {"جبر", "هندسة"})
        by_grade = self.client_a.get(f"{URL}?grade_id={self.grade.id}", **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual([c["title"] for c in by_grade], ["جبر"])
        found = self.client_a.get(f"{URL}?search=هند", **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual([c["title"] for c in found], ["هندسة"])

    def test_patch_title_keeps_the_existing_video(self):
        c = ContentItem.objects.create(environment=self.env_a, title="قديم", video_provider="youtube", video_ref=YT)
        r = self.client_a.patch(item_url(c.id), {"title": "جديد"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        c.refresh_from_db()
        self.assertEqual((c.title, c.video_provider, c.video_ref), ("جديد", "youtube", YT))

    def test_patch_can_remove_the_video(self):
        c = ContentItem.objects.create(environment=self.env_a, title="t", video_provider="youtube", video_ref=YT)
        r = self.client_a.patch(item_url(c.id), {"video_provider": "none"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        c.refresh_from_db()
        self.assertEqual((c.video_provider, c.video_ref), ("none", ""))

    def test_patch_with_an_invalid_ref_is_rejected_and_changes_nothing(self):
        c = ContentItem.objects.create(environment=self.env_a, title="t", video_provider="youtube", video_ref=YT)
        r = self.client_a.patch(item_url(c.id), {"video_ref": "not-valid"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        c.refresh_from_db()
        self.assertEqual(c.video_ref, YT)

    def test_delete(self):
        c = ContentItem.objects.create(environment=self.env_a, title="t")
        self.assertEqual(self.client_a.delete(item_url(c.id), **self.with_env(self.env_a.id)).status_code, 204)

    def test_cannot_read_update_or_delete_another_teachers_content(self):
        c = ContentItem.objects.create(environment=self.env_a, title="سري")
        self.assert_cross_tenant_denied("get", item_url(c.id))
        self.assert_cross_tenant_denied("patch", item_url(c.id), body={"title": "x"})
        self.assert_cross_tenant_denied("delete", item_url(c.id))
        self.assertTrue(ContentItem.objects.filter(pk=c.id).exists())

    def test_own_header_but_someone_elses_id_is_404(self):
        c = ContentItem.objects.create(environment=self.env_a, title="سري")
        self.assertEqual(self.client_b.get(item_url(c.id), **self.with_env(self.env_b.id)).status_code, 404)

    def test_stored_markup_is_returned_as_inert_json_text(self):
        """Stored user text is never rendered server-side; the API returns it
        verbatim inside JSON (XSS is prevented at render time by React's
        escaping — see the frontend's ContentPage, which never uses
        dangerouslySetInnerHTML)."""
        payload = "<img src=x onerror=alert(1)>"
        r = self.post(title=payload)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(json.loads(r.content)["title"], payload)
        self.assertEqual(r["Content-Type"], "application/json")

    def test_model_level_clean_rejects_a_cross_environment_grade(self):
        with self.assertRaises(DjangoValidationError):
            ContentItem(environment=self.env_a, title="x", grade=self.grade_b).clean()
