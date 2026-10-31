"""Educational-content sections: PDF files and written summaries (next to videos).

Security properties pinned here: validation beats the client, private storage, signed short-lived
viewing tickets with their OWN salt, re-authorisation on every request, tenant isolation, and the
guarantee that a student's video/quiz screens never receive a PDF or a summary."""
import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Enrollment, Grade, Group
from billing.models import Subscription
from environments.tenancy_testing import PASSWORD, TenantTestCase
from notifications.models import Notification

from .models import ContentItem
from .streaming import issue_ticket

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n" + b"\x00" * 256
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 512


def pdf(name="notes.pdf", data=PDF, content_type="application/pdf"):
    return SimpleUploadedFile(name, data, content_type=content_type)


class _Base(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(shutil.rmtree, self.media, True)

        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.student = self._student("201555800001", "201111000001", self.grade, [self.group])
        self.sc = self.student_client(self.student)

    def _student(self, phone, parent, grade, groups):
        s = self.make_student_in(self.env_a, phone, "طالب")
        s.set_password(PASSWORD)
        s.is_active = True
        s.is_verified = True
        s.save()
        enr = Enrollment.objects.create(environment=self.env_a, student=s, grade=grade, parent_phone=parent)
        enr.groups.set(groups)
        return s

    def student_client(self, user):
        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/", {"phone": user.phone, "password": PASSWORD}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        return c

    # -- teacher-side helpers ------------------------------------------------
    def create(self, kind, client=None, env=None, **extra):
        body = {"kind": kind, "title": "عنوان", "grade_ids": [self.grade.id], **extra}
        return (client or self.client_a).post(
            "/api/v1/content/", body, format="json", **self.with_env((env or self.env_a).id))

    def make(self, kind, **extra):
        r = self.create(kind, **extra)
        self.assertEqual(r.status_code, 201, r.content)
        return ContentItem.objects.get(pk=r.json()["id"])

    def upload(self, item, f=None, client=None, env=None):
        return (client or self.client_a).put(
            f"/api/v1/content/{item.id}/document/", {"file": f or pdf()},
            format="multipart", **self.with_env((env or self.env_a).id))

    def publish(self, item, client=None, env=None):
        return (client or self.client_a).post(
            f"/api/v1/content/{item.id}/publish/", **self.with_env((env or self.env_a).id))

    def pdf_item(self, published=True):
        item = self.make("pdf")
        self.assertEqual(self.upload(item).status_code, 200)
        if published:
            self.assertEqual(self.publish(item).status_code, 200)
        item.refresh_from_db()
        return item


class KindsAndSummaryTests(_Base):
    def test_existing_behaviour_is_unchanged_a_plain_create_is_a_video(self):
        r = self.client_a.post("/api/v1/content/", {"title": "درس"}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["kind"], "video")

    def test_a_summary_stores_text_verbatim_never_as_markup(self):
        body = "## عنوان\n- نقطة\n<script>alert(1)</script>"
        item = self.make("summary", body=body)
        self.assertEqual(item.body, body)          # stored as data; the client renders it as text
        self.assertEqual(item.video_provider, "none")

    def test_summary_length_is_capped(self):
        self.assertEqual(self.create("summary", body="س" * 20001).status_code, 400)

    def test_body_is_for_summaries_only(self):
        self.assertEqual(self.create("pdf", body="نص").status_code, 400)
        self.assertEqual(self.create("video", body="نص").status_code, 400)

    def test_kind_cannot_change_after_creation(self):
        item = self.make("summary", body="نص")
        r = self.client_a.patch(f"/api/v1/content/{item.id}/", {"kind": "video"}, format="json",
                                **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_list_rows_are_light_and_the_detail_carries_the_text(self):
        item = self.make("summary", body="النص الكامل")
        rows = self.client_a.get("/api/v1/content/?kind=summary", **self.with_env(self.env_a.id)).json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertTrue(rows[0]["has_body"])
        self.assertNotIn("body", rows[0])
        detail = self.client_a.get(f"/api/v1/content/{item.id}/", **self.with_env(self.env_a.id)).json()
        self.assertEqual(detail["body"], "النص الكامل")

    def test_unknown_kind_is_rejected(self):
        self.assertEqual(self.create("exam").status_code, 400)

    def test_list_can_be_filtered_by_kind(self):
        self.make("summary", body="نص")
        self.make("pdf")
        self.make("video")
        for kind in ("summary", "pdf", "video"):
            r = self.client_a.get(f"/api/v1/content/?kind={kind}", **self.with_env(self.env_a.id))
            self.assertEqual({row["kind"] for row in r.json()["results"] if True} if isinstance(r.json(), dict)
                             else {row["kind"] for row in r.json()}, {kind})
        self.assertEqual(self.client_a.get("/api/v1/content/?kind=zzz", **self.with_env(self.env_a.id)).status_code, 400)

    def test_publishing_needs_the_material_itself(self):
        empty_pdf = self.make("pdf")
        self.assertEqual(self.publish(empty_pdf).status_code, 400)
        empty_summary = self.make("summary")
        self.assertEqual(self.publish(empty_summary).status_code, 400)
        ok = self.make("summary", body="محتوى")
        self.assertEqual(self.publish(ok).status_code, 200)

    def test_the_notification_wording_follows_the_kind(self):
        item = self.make("summary", body="محتوى")
        self.publish(item)
        n = Notification.objects.get(content_item=item)
        self.assertEqual(n.title, "ملخص جديد")
        pdf_item = self.pdf_item()
        self.assertEqual(Notification.objects.get(content_item=pdf_item).title, "ملف جديد")


class PdfUploadValidationTests(_Base):
    def setUp(self):
        super().setUp()
        self.item = self.make("pdf")

    def test_a_real_pdf_uploads_to_private_random_storage(self):
        r = self.upload(self.item, pdf("../../../etc/passwd.pdf"))
        self.assertEqual(r.status_code, 200, r.content)
        self.item.refresh_from_db()
        name = self.item.document_file.name
        self.assertTrue(name.startswith(f"documents/{self.env_a.id}/"))
        self.assertNotIn("..", name)
        self.assertNotIn("passwd", name)
        self.assertNotIn("document_file", r.json())     # the stored path is never serialised
        self.assertNotIn(name, str(r.json()))

    def test_hostile_files_are_rejected_whatever_they_are_named(self):
        hostile = [
            pdf("evil.php", b"<?php system($_GET[0]); ?>"),
            pdf("evil.exe", b"MZ\x90\x00" + b"\x00" * 100),
            pdf("evil.pdf", b"#!/bin/sh\nrm -rf /"),
            pdf("evil.pdf", b"PK\x03\x04" + b"\x00" * 100),
            pdf("evil.pdf", b"\x7fELF" + b"\x00" * 100),
            pdf("evil.pdf", b"<html><script>alert(1)</script></html>"),
            pdf("notpdf.pdf", b"just some text"),
            pdf("evil.pdf.php", PDF),
            pdf("evil.txt", PDF),
            pdf("evil.pdf", PDF, "text/html"),
        ]
        for f in hostile:
            with self.subTest(name=f.name):
                self.assertEqual(self.upload(self.item, f).status_code, 400)
        self.item.refresh_from_db()
        self.assertFalse(self.item.document_file)

    def test_empty_and_oversized_files_are_rejected(self):
        self.assertEqual(self.upload(self.item, pdf("e.pdf", b"")).status_code, 400)
        with override_settings(DOCUMENT_MAX_BYTES=100):
            self.assertEqual(self.upload(self.item).status_code, 400)

    def test_replacing_deletes_the_old_blob(self):
        self.upload(self.item)
        self.item.refresh_from_db()
        first = self.item.document_file.path
        self.upload(self.item, pdf("second.pdf"))
        self.item.refresh_from_db()
        self.assertNotEqual(self.item.document_file.path, first)
        self.assertFalse(os.path.exists(first))

    def test_only_the_owning_teacher_and_never_a_student(self):
        self.assertEqual(self.upload(self.item, client=self.client_b, env=self.env_b).status_code, 404)
        self.assertEqual(self.upload(self.item, client=self.client_b).status_code, 403)
        self.assertEqual(self.upload(self.item, client=self.sc).status_code, 403)

    def test_a_pdf_cannot_be_put_on_a_video_and_a_video_cannot_be_put_on_a_pdf(self):
        video_item = self.make("video")
        self.assertEqual(self.upload(video_item).status_code, 400)
        r = self.client_a.put(f"/api/v1/content/{self.item.id}/video/",
                              {"video": SimpleUploadedFile("v.mp4", MP4, content_type="video/mp4")},
                              format="multipart", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        r = self.client_a.post(f"/api/v1/content/{self.item.id}/uploads/",
                               {"filename": "v.mp4", "total_bytes": 10}, format="json",
                               **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_deleting_the_file_removes_the_blob_and_unpublishes(self):
        item = self.pdf_item()
        path = item.document_file.path
        r = self.client_a.delete(f"/api/v1/content/{item.id}/document/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        item.refresh_from_db()
        self.assertFalse(os.path.exists(path))
        self.assertIsNone(item.published_at)


class PdfViewingSecurityTests(_Base):
    def setUp(self):
        super().setUp()
        self.item = self.pdf_item()

    def ticket(self, client, item=None, env=None):
        return client.post(f"/api/v1/content/{(item or self.item).id}/document-ticket/",
                           **self.with_env((env or self.env_a).id))

    def open(self, client, t):
        return client.get(f"/api/v1/content/document/?t={t}")

    def test_a_targeted_student_gets_a_ticket_and_the_pdf_inline(self):
        t = self.ticket(self.sc).json()["ticket"]
        r = self.open(APIClient(), t)                       # the ticket alone is the credential
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertEqual(r["Content-Disposition"], "inline")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", r["Cache-Control"])
        self.assertTrue(b"".join(r.streaming_content).startswith(b"%PDF-"))

    def test_the_teacher_can_preview_their_own_file(self):
        t = self.ticket(self.client_a).json()["ticket"]
        self.assertEqual(self.open(APIClient(), t).status_code, 200)

    def test_unpublished_untargeted_and_foreign_access_is_refused(self):
        draft = self.pdf_item(published=False)
        self.assertEqual(self.ticket(self.sc, draft).status_code, 404)
        other_grade = Grade.objects.create(environment=self.env_a, name="ثاني")
        outsider = self._student("201555800002", "201111000002", other_grade, [])
        self.assertEqual(self.ticket(self.student_client(outsider)).status_code, 404)
        self.assertEqual(self.ticket(self.client_b, env=self.env_b).status_code, 404)
        self.assertEqual(self.ticket(self.client_b).status_code, 403)
        self.assertEqual(self.ticket(APIClient()).status_code, 401)

    def test_forged_garbage_and_empty_tickets_are_refused(self):
        t = self.ticket(self.sc).json()["ticket"]
        for bad in ("", "garbage", t[:-3] + "xyz", t.upper(), f"{self.item.id}:1"):
            with self.subTest(t=bad[:12]):
                self.assertEqual(self.open(APIClient(), bad).status_code, 404)

    def test_a_video_ticket_cannot_open_a_document_and_vice_versa(self):
        video_ticket = issue_ticket(self.item.id, self.student.id)            # default (video) salt
        self.assertEqual(self.open(APIClient(), video_ticket).status_code, 404)
        doc_ticket = self.ticket(self.sc).json()["ticket"]
        self.assertEqual(APIClient().get(f"/api/v1/content/stream/?t={doc_ticket}").status_code, 404)

    def test_revoking_access_kills_an_unexpired_ticket(self):
        t = self.ticket(self.sc).json()["ticket"]
        ContentItem.objects.filter(pk=self.item.pk).update(published_at=None)
        self.assertEqual(self.open(APIClient(), t).status_code, 404)
        ContentItem.objects.filter(pk=self.item.pk).update(published_at=timezone.now())
        self.assertEqual(self.open(APIClient(), t).status_code, 200)
        Enrollment.objects.filter(student=self.student).update(is_active=False)
        self.assertEqual(self.open(APIClient(), t).status_code, 404)

    def test_a_ticket_expires(self):
        t = self.ticket(self.sc).json()["ticket"]
        with override_settings(VIDEO_PLAYBACK_TTL_SECONDS=-1):
            self.assertEqual(self.open(APIClient(), t).status_code, 404)

    def test_a_ticket_is_only_for_pdf_items(self):
        summary = self.make("summary", body="نص")
        self.publish(summary)
        self.assertEqual(self.ticket(self.sc, summary).status_code, 404)


class StudentSectionsTests(_Base):
    def test_videos_screens_never_receive_pdfs_or_summaries(self):
        self.pdf_item()
        s = self.make("summary", body="نص")
        self.publish(s)
        video = self.make("video")
        self.publish(video)
        ids = [v["id"] for v in self.sc.get("/api/v1/student/videos/", **self.with_env(self.env_a.id)).json()["results"]]
        self.assertEqual(ids, [video.id])
        for other in ContentItem.objects.exclude(pk=video.pk):
            self.assertEqual(self.sc.get(f"/api/v1/student/videos/{other.id}/", **self.with_env(self.env_a.id)).status_code, 404)
        home = self.sc.get("/api/v1/student/overview/", **self.with_env(self.env_a.id)).json()
        self.assertEqual([v["id"] for v in home["latest_videos"]], [video.id])

    def test_materials_list_shows_only_published_targeted_pdfs_and_summaries(self):
        pdf_item = self.pdf_item()
        summary = self.make("summary", body="نص الملخص")
        self.publish(summary)
        self.make("summary", body="مسودة")                              # draft: invisible
        other_grade = Grade.objects.create(environment=self.env_a, name="ثاني")
        hidden = self.make("summary", body="لصف آخر", grade_ids=[other_grade.id])
        self.publish(hidden)
        r = self.sc.get("/api/v1/student/materials/", **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual({row["id"] for row in r}, {pdf_item.id, summary.id})
        only_pdf = self.sc.get("/api/v1/student/materials/?kind=pdf", **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual([row["id"] for row in only_pdf], [pdf_item.id])
        self.assertEqual(self.sc.get("/api/v1/student/materials/?kind=video", **self.with_env(self.env_a.id)).status_code, 400)
        # list rows never carry the summary text, a path or a url
        for row in r:
            self.assertNotIn("body", row)
            self.assertNotIn("document_file", row)

    def test_detail_returns_the_summary_text_but_never_a_stored_path(self):
        summary = self.make("summary", body="النص الكامل")
        self.publish(summary)
        d = self.sc.get(f"/api/v1/student/materials/{summary.id}/", **self.with_env(self.env_a.id)).json()
        self.assertEqual(d["body"], "النص الكامل")
        item = self.pdf_item()
        d = self.sc.get(f"/api/v1/student/materials/{item.id}/", **self.with_env(self.env_a.id)).json()
        self.assertNotIn("documents/", str(d))
        self.assertEqual(d["original_filename"], "notes.pdf")

    def test_materials_detail_is_a_404_for_videos_drafts_and_other_audiences(self):
        video = self.make("video")
        self.publish(video)
        draft = self.make("summary", body="x")
        other_grade = Grade.objects.create(environment=self.env_a, name="ثاني")
        hidden = self.make("summary", body="x", grade_ids=[other_grade.id])
        self.publish(hidden)
        for item in (video, draft, hidden):
            self.assertEqual(self.sc.get(f"/api/v1/student/materials/{item.id}/",
                                         **self.with_env(self.env_a.id)).status_code, 404)

    def test_a_teacher_cannot_use_the_student_endpoints_and_anonymous_is_refused(self):
        self.assertIn(self.client_a.get("/api/v1/student/materials/", **self.with_env(self.env_a.id)).status_code, (401, 403))
        self.assertEqual(APIClient().get("/api/v1/student/materials/").status_code, 401)

    def test_ai_quiz_is_not_offered_for_pdfs_or_summaries(self):
        # An active trial so the plan gate lets the request through: the 404 must come from the kind rule.
        Subscription.objects.create(environment=self.env_a, trial_started_at=timezone.now())
        s = self.make("summary", body="ملخص طويل بما يكفي لتوليد اختبار منه بسهولة وبدون مشاكل أبدا")
        self.publish(s)
        r = self.sc.post("/api/v1/student/quizzes/", {"content_id": s.id}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 404)
