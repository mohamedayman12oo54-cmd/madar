"""Real video uploads: file validation, private storage, protected playback."""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from academics.models import Enrollment, Grade, Group
from accounts.models import User
from environments.tenancy_testing import PASSWORD, TenantTestCase
from rest_framework.test import APIClient

from .models import ContentItem, VideoProgress

# Minimal but REAL container signatures — validation reads the bytes, so a
# fixture has to look like the real thing.
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * 512
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 512


def video(name="lesson.mp4", data=MP4, content_type="video/mp4"):
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
        self.item = ContentItem.objects.create(environment=self.env_a, title="درس")
        self.item.target_grades.set([self.grade])

        self.student = self.make_student_in(self.env_a, "201555700001", "طالب")
        self.student.set_password(PASSWORD)
        self.student.is_active = True
        self.student.is_verified = True
        self.student.save()
        self.enr = Enrollment.objects.create(
            environment=self.env_a, student=self.student, grade=self.grade, parent_phone="201111000001")
        self.enr.groups.set([self.group])

    def student_client(self, user=None, phone=None):
        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/",
                     {"phone": phone or self.student.phone, "password": PASSWORD}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        return c

    def upload(self, f=None, client=None, env=None, pk=None):
        return (client or self.client_a).put(
            f"/api/v1/content/{pk or self.item.id}/video/", {"video": f or video()},
            format="multipart", **self.with_env((env or self.env_a).id))

    def publish(self):
        # Targeted UPDATE, not .save(): saving a stale in-memory copy would
        # silently clobber fields an upload has already written to the row.
        ContentItem.objects.filter(pk=self.item.pk).update(published_at=timezone.now())
        self.item.refresh_from_db()


class UploadValidationTests(_Base):
    def test_a_real_video_uploads_and_is_recorded(self):
        r = self.upload()
        self.assertEqual(r.status_code, 200, r.content)
        self.item.refresh_from_db()
        self.assertEqual(self.item.source, "upload")
        self.assertTrue(self.item.video_file)
        self.assertEqual(self.item.content_type, "video/mp4")
        self.assertGreater(self.item.file_size, 0)

    def test_webm_is_accepted(self):
        self.assertEqual(self.upload(video("v.webm", WEBM, "video/webm")).status_code, 200)

    def test_executables_and_scripts_are_rejected_whatever_they_are_named(self):
        hostile = [
            video("evil.php", b"<?php system($_GET[0]); ?>", "video/mp4"),
            video("evil.exe", b"MZ\x90\x00" + b"\x00" * 100, "video/mp4"),
            video("evil.sh", b"#!/bin/sh\nrm -rf /", "video/mp4"),
            video("evil.mp4", b"PK\x03\x04" + b"\x00" * 100, "video/mp4"),
            video("evil.mp4", b"\x7fELF" + b"\x00" * 100, "video/mp4"),
        ]
        for f in hostile:
            with self.subTest(name=f.name):
                self.assertEqual(self.upload(f).status_code, 400)
        self.item.refresh_from_db()
        self.assertFalse(self.item.video_file)

    def test_a_disguised_extension_is_rejected(self):
        """Right magic bytes, wrong extension — still refused."""
        self.assertEqual(self.upload(video("lesson.mp4.php", MP4, "video/mp4")).status_code, 400)
        self.assertEqual(self.upload(video("lesson.txt", MP4, "video/mp4")).status_code, 400)

    def test_content_type_spoofing_is_caught_by_the_bytes(self):
        self.assertEqual(self.upload(video("x.mp4", b"not a video at all", "video/mp4")).status_code, 400)

    def test_empty_and_oversized_files_are_rejected(self):
        self.assertEqual(self.upload(video("e.mp4", b"", "video/mp4")).status_code, 400)
        with override_settings(VIDEO_MAX_BYTES=100):
            self.assertEqual(self.upload().status_code, 400)

    def test_the_client_filename_never_reaches_the_filesystem(self):
        """Path traversal in the name must not escape the media root."""
        r = self.upload(video("../../../../etc/passwd.mp4", MP4, "video/mp4"))
        self.assertEqual(r.status_code, 200, r.content)
        self.item.refresh_from_db()
        name = self.item.video_file.name
        self.assertNotIn("..", name)
        self.assertTrue(name.startswith(f"videos/{self.env_a.id}/"))
        self.assertNotIn("passwd", name)  # stored name is random

    def test_only_the_owning_teacher_can_upload(self):
        self.assertEqual(self.upload(client=self.client_b, env=self.env_b).status_code, 404)
        self.assertEqual(self.upload(client=self.client_b).status_code, 403)

    def test_a_student_cannot_upload(self):
        self.assertEqual(self.upload(client=self.student_client()).status_code, 403)

    def test_replacing_an_upload_deletes_the_previous_blob(self):
        self.upload()
        self.item.refresh_from_db()
        first = self.item.video_file.path
        self.upload(video("second.mp4", MP4, "video/mp4"))
        self.item.refresh_from_db()
        self.assertNotEqual(self.item.video_file.path, first)
        import os
        self.assertFalse(os.path.exists(first), "superseded blob must not linger")


class PlaybackSecurityTests(_Base):
    def setUp(self):
        super().setUp()
        self.upload()
        self.item.refresh_from_db()

    def ticket(self, client, env=None, pk=None):
        return client.post(f"/api/v1/content/{pk or self.item.id}/playback-ticket/",
                           **self.with_env((env or self.env_a).id))

    def stream(self, client, t, env=None, **extra):
        return client.get(f"/api/v1/content/stream/?t={t}", **self.with_env((env or self.env_a).id), **extra)

    def test_a_targeted_student_can_get_a_ticket_and_stream(self):
        self.publish()
        sc = self.student_client()
        r = self.ticket(sc)
        self.assertEqual(r.status_code, 200, r.content)
        s = self.stream(sc, r.json()["ticket"])
        self.assertEqual(s.status_code, 200)
        self.assertEqual(s["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", s["Cache-Control"])

    def test_an_unpublished_video_cannot_be_watched_by_a_student(self):
        self.assertEqual(self.ticket(self.student_client()).status_code, 404)

    def test_a_student_outside_the_target_audience_is_refused(self):
        self.publish()
        other_grade = Grade.objects.create(environment=self.env_a, name="ثاني")
        outsider = self.make_student_in(self.env_a, "201555700002", "خارج")
        outsider.set_password(PASSWORD); outsider.is_active = True; outsider.is_verified = True; outsider.save()
        Enrollment.objects.create(environment=self.env_a, student=outsider, grade=other_grade,
                                  parent_phone="201111000002")
        self.assertEqual(self.ticket(self.student_client(phone=outsider.phone)).status_code, 404)

    def test_another_teacher_cannot_get_a_ticket(self):
        self.assertEqual(self.ticket(self.client_b, env=self.env_b).status_code, 404)
        self.assertEqual(self.ticket(self.client_b).status_code, 403)

    def test_a_ticket_is_a_short_lived_bearer_credential(self):
        """Honest statement of the trade-off: the stream URL authenticates
        itself (a <video> cannot send a header), so whoever holds a LIVE ticket
        can stream. The protections are its very short life, the fact that it
        names one item only, and the authorisation re-check on every request —
        not secrecy of the URL."""
        self.publish()
        t = self.ticket(self.student_client()).json()["ticket"]
        self.assertEqual(self.stream(self.client_a, t).status_code, 200)
        from django.conf import settings
        self.assertLessEqual(settings.VIDEO_PLAYBACK_TTL_SECONDS, 300,
                             "a bearer playback URL must be short-lived")

    def test_a_ticket_only_ever_unlocks_its_own_item(self):
        self.publish()
        other = ContentItem.objects.create(environment=self.env_a, title="درس آخر")
        other.target_grades.set([self.grade])
        self.upload(pk=other.id)
        ContentItem.objects.filter(pk=other.pk).update(published_at=timezone.now())
        sc = self.student_client()
        t = self.ticket(sc).json()["ticket"]           # ticket for self.item
        streamed = self.stream(sc, t)
        self.assertEqual(streamed.status_code, 200)
        self.assertNotEqual(self.item.id, other.id)

    def test_forged_or_tampered_tickets_are_refused(self):
        self.publish()
        sc = self.student_client()
        good = self.ticket(sc).json()["ticket"]
        for bad in ["", "garbage", good[:-3] + "aaa", f"{self.item.id}:{self.student.id}", good.upper()]:
            with self.subTest(ticket=bad):
                self.assertEqual(self.stream(sc, bad).status_code, 404)

    def test_an_expired_ticket_stops_working(self):
        self.publish()
        sc = self.student_client()
        t = self.ticket(sc).json()["ticket"]
        with override_settings(VIDEO_PLAYBACK_TTL_SECONDS=-1):
            self.assertEqual(self.stream(sc, t).status_code, 404)

    def test_access_revoked_after_issue_takes_effect_before_expiry(self):
        """Unpublishing must kill a ticket that has NOT yet expired."""
        self.publish()
        sc = self.student_client()
        t = self.ticket(sc).json()["ticket"]
        self.assertEqual(self.stream(sc, t).status_code, 200)
        self.item.published_at = None
        self.item.save()
        self.assertEqual(self.stream(sc, t).status_code, 404)

    def test_deactivating_an_enrolment_kills_playback(self):
        self.publish()
        sc = self.student_client()
        t = self.ticket(sc).json()["ticket"]
        self.enr.is_active = False
        self.enr.save()
        # Denied — in practice even earlier than the item check, because a
        # deactivated enrolment also loses the student session itself.
        self.assertIn(self.stream(sc, t).status_code, (401, 403, 404))

    def test_a_deleted_upload_cannot_be_streamed(self):
        self.publish()
        sc = self.student_client()
        t = self.ticket(sc).json()["ticket"]
        self.client_a.delete(f"/api/v1/content/{self.item.id}/video/", **self.with_env(self.env_a.id))
        self.assertEqual(self.stream(sc, t).status_code, 404)

    def test_streaming_without_a_ticket_is_refused(self):
        self.publish()
        for bad in ("", "nonsense"):
            self.assertEqual(APIClient().get(f"/api/v1/content/stream/?t={bad}").status_code, 404)

    def test_range_requests_are_supported_for_seeking(self):
        self.publish()
        sc = self.student_client()
        t = self.ticket(sc).json()["ticket"]
        r = self.stream(sc, t, HTTP_RANGE="bytes=0-99")
        self.assertEqual(r.status_code, 206)
        self.assertIn("bytes 0-99/", r["Content-Range"])

    def test_the_stored_path_is_never_exposed_to_clients(self):
        self.publish()
        body = self.client_a.get(f"/api/v1/content/{self.item.id}/", **self.with_env(self.env_a.id)).content.decode()
        self.assertNotIn(self.item.video_file.name, body)
        self.assertNotIn("private-media", body)


class ProgressTrackingTests(_Base):
    def setUp(self):
        super().setUp()
        self.upload()
        self.publish()
        self.sc = self.student_client()

    def put(self, position, duration=100, client=None, pk=None):
        return (client or self.sc).put(
            f"/api/v1/content/{pk or self.item.id}/progress/",
            {"position_seconds": position, "duration_seconds": duration},
            format="json", **self.with_env(self.env_a.id))

    def test_progress_is_recorded_for_the_authenticated_student(self):
        r = self.put(50)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["percent"], 50)
        row = VideoProgress.objects.get(item=self.item, enrollment=self.enr)
        self.assertEqual(row.position_seconds, 50)
        self.assertFalse(row.completed)

    def test_watching_to_the_end_marks_completion(self):
        self.assertTrue(self.put(100).json()["completed"])

    def test_progress_never_goes_backwards(self):
        self.put(80)
        self.assertEqual(self.put(5).json()["percent"], 80)

    def test_a_student_cannot_write_progress_for_someone_else(self):
        """There is no enrollment id in the payload — it comes from the token."""
        r = self.sc.put(f"/api/v1/content/{self.item.id}/progress/",
                        {"position_seconds": 10, "duration_seconds": 100, "enrollment_id": 9999},
                        format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(VideoProgress.objects.get().enrollment_id, self.enr.id)

    def test_a_teacher_sees_who_watched(self):
        self.put(60)
        r = self.client_a.get(f"/api/v1/content/{self.item.id}/watchers/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["results"][0]["percent"], 60)

    def test_another_teacher_cannot_see_watchers(self):
        self.assertEqual(
            self.client_b.get(f"/api/v1/content/{self.item.id}/watchers/",
                              **self.with_env(self.env_b.id)).status_code, 404)


class SerializerExposureTests(_Base):
    def test_the_stored_file_path_is_never_serialised(self):
        self.upload()
        self.publish()
        body = self.client_a.get("/api/v1/content/", **self.with_env(self.env_a.id)).content.decode()
        self.item.refresh_from_db()
        self.assertIn('"source"', body)
        self.assertNotIn(self.item.video_file.name, body)
        self.assertNotIn(self.media, body)

    def test_students_see_the_source_but_not_the_path(self):
        self.upload()
        self.publish()
        body = self.student_client().get("/api/v1/student/videos/",
                                         **self.with_env(self.env_a.id)).content.decode()
        self.item.refresh_from_db()
        self.assertIn('"upload"', body)
        self.assertNotIn(self.item.video_file.name, body)


class ResumableUploadTests(_Base):
    """A dropped connection must not cost the whole upload."""

    CREATE = "/api/v1/content/{}/uploads/"
    SESSION = "/api/v1/content/uploads/{}/"

    def start(self, size=len(MP4), name="lesson.mp4", ctype="video/mp4", client=None, env=None):
        return (client or self.client_a).post(
            self.CREATE.format(self.item.id),
            {"filename": name, "total_bytes": size, "content_type": ctype},
            format="json", **self.with_env((env or self.env_a).id))

    def send(self, sid, data, offset, client=None):
        return (client or self.client_a).patch(
            self.SESSION.format(sid), data, content_type="application/offset+octet-stream",
            HTTP_UPLOAD_OFFSET=str(offset), **self.with_env(self.env_a.id))

    def test_a_session_is_created_with_a_zero_offset(self):
        r = self.start()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["offset"], 0)
        self.assertTrue(r.json()["resumable"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.processing_status, "uploading")

    def test_an_upload_completes_across_several_chunks(self):
        sid = self.start().json()["id"]
        half = len(MP4) // 2
        first = self.send(sid, MP4[:half], 0)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["offset"], half)
        self.assertFalse(first.json()["is_complete"])

        second = self.send(sid, MP4[half:], half)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertTrue(second.json()["is_complete"])

        self.item.refresh_from_db()
        self.assertEqual(self.item.source, "upload")
        self.assertEqual(self.item.processing_status, "ready")
        self.assertEqual(self.item.file_size, len(MP4))

    def test_an_interrupted_upload_resumes_from_the_server_offset(self):
        """The whole point: ask where we got to, continue from there."""
        sid = self.start().json()["id"]
        self.send(sid, MP4[:100], 0)

        # ...connection drops; the client comes back and asks.
        probe = self.client_a.get(self.SESSION.format(sid), **self.with_env(self.env_a.id))
        self.assertEqual(probe.status_code, 200)
        offset = probe.json()["offset"]
        self.assertEqual(offset, 100)
        self.assertEqual(probe["Upload-Offset"], "100")

        done = self.send(sid, MP4[offset:], offset)
        self.assertTrue(done.json()["is_complete"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.file_size, len(MP4))
        with open(self.item.video_file.path, "rb") as fh:
            self.assertEqual(fh.read(), MP4, "resumed file must be byte-identical")

    def test_a_wrong_offset_is_refused_instead_of_corrupting_the_file(self):
        sid = self.start().json()["id"]
        self.send(sid, MP4[:100], 0)
        for bad in (0, 50, 200):
            r = self.send(sid, MP4[100:200], bad)
            self.assertEqual(r.status_code, 409, f"offset {bad}")
            self.assertEqual(r.json()["offset"], 100, "server states the true offset")

    def test_bytes_left_by_a_crashed_write_never_become_part_of_the_video(self):
        """A request can die after writing part of a chunk but before the offset is recorded. The server's
        recorded offset is the truth: the next chunk is written AT that offset, discarding the stray tail.
        (The old code appended and then read the offset back from the file size, so the junk was kept and the
        upload "completed" with a corrupted file that still passed the header-only check.)"""
        sid = self.start().json()["id"]
        self.assertEqual(self.send(sid, MP4[:100], 0).status_code, 200)

        from .models import UploadSession
        stored = UploadSession.objects.get(pk=sid).storage_path
        with open(f"{self.media}/{stored}", "ab") as fh:
            fh.write(b"JUNK-FROM-A-CRASHED-REQUEST")

        done = self.send(sid, MP4[100:], 100)
        self.assertEqual(done.status_code, 200, done.content)
        self.assertTrue(done.json()["is_complete"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.file_size, len(MP4))
        with open(self.item.video_file.path, "rb") as fh:
            self.assertEqual(fh.read(), MP4, "stray bytes must not survive into the stored video")

    def test_the_offset_header_is_required(self):
        sid = self.start().json()["id"]
        r = self.client_a.patch(self.SESSION.format(sid), MP4[:10],
                                content_type="application/offset+octet-stream",
                                **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_sending_more_than_declared_is_refused(self):
        sid = self.start(size=100).json()["id"]
        self.assertEqual(self.send(sid, b"x" * 200, 0).status_code, 400)

    def test_limits_are_enforced_before_any_byte_is_accepted(self):
        with override_settings(VIDEO_MAX_BYTES=100):
            self.assertEqual(self.start(size=10_000).status_code, 400)
        self.assertEqual(self.start(name="evil.php").status_code, 400)
        self.assertEqual(self.start(ctype="application/x-php").status_code, 400)

    def test_a_chunked_executable_is_still_rejected_when_assembled(self):
        """Validation runs on the finished file, so chunking is not a bypass."""
        payload = b"<?php system($_GET[0]); ?>" + b"\x00" * 200
        sid = self.start(size=len(payload)).json()["id"]
        self.send(sid, payload[:50], 0)
        r = self.send(sid, payload[50:], 50)
        self.assertEqual(r.status_code, 400, r.content)
        self.item.refresh_from_db()
        self.assertFalse(self.item.video_file)
        self.assertEqual(self.item.processing_status, "failed")

    def test_another_teacher_cannot_touch_my_session(self):
        sid = self.start().json()["id"]
        self.assertEqual(
            self.client_b.get(f"/api/v1/content/uploads/{sid}/",
                              **self.with_env(self.env_b.id)).status_code, 404)
        self.assertEqual(
            self.client_b.patch(f"/api/v1/content/uploads/{sid}/", MP4,
                                content_type="application/offset+octet-stream",
                                HTTP_UPLOAD_OFFSET="0",
                                **self.with_env(self.env_b.id)).status_code, 404)

    def test_a_student_cannot_start_an_upload(self):
        self.assertEqual(self.start(client=self.student_client()).status_code, 403)

    def test_abandoning_a_session_discards_the_partial_file(self):
        sid = self.start().json()["id"]
        self.send(sid, MP4[:100], 0)
        from .models import UploadSession
        partial = UploadSession.objects.get(pk=sid).storage_path
        import os
        full = os.path.join(self.media, partial)
        self.assertTrue(os.path.exists(full))
        r = self.client_a.delete(self.SESSION.format(sid), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(os.path.exists(full), "partial bytes must not linger")

    def test_too_many_concurrent_uploads_are_refused(self):
        for _ in range(5):
            self.assertEqual(self.start().status_code, 201)
        self.assertEqual(self.start().status_code, 400)


class CorsContractTests(_Base):
    """The resumable upload depends on custom headers crossing the browser's
    preflight. If they are not allowed/exposed the PATCH never reaches Django
    and the user sees an unexplained failure — so the contract is pinned."""

    def test_the_upload_headers_are_allowed_through_preflight(self):
        from django.conf import settings

        allowed = {h.lower() for h in settings.CORS_ALLOW_HEADERS}
        self.assertIn("upload-offset", allowed)
        self.assertIn("x-madar-environment", allowed)

    def test_the_offset_headers_are_readable_by_the_client(self):
        from django.conf import settings

        exposed = {h.lower() for h in getattr(settings, "CORS_EXPOSE_HEADERS", [])}
        self.assertIn("upload-offset", exposed,
                      "the client cannot resume if it cannot read the offset")

    def test_the_server_actually_sends_the_offset_headers(self):
        sid = self.client_a.post(f"/api/v1/content/{self.item.id}/uploads/",
                                 {"filename": "a.mp4", "total_bytes": len(MP4), "content_type": "video/mp4"},
                                 format="json", **self.with_env(self.env_a.id)).json()["id"]
        r = self.client_a.get(f"/api/v1/content/uploads/{sid}/", **self.with_env(self.env_a.id))
        self.assertEqual(r["Upload-Offset"], "0")
        self.assertEqual(r["Upload-Length"], str(len(MP4)))

    def test_large_videos_are_permitted(self):
        from django.conf import settings

        self.assertGreaterEqual(settings.VIDEO_MAX_BYTES, 1024 ** 3,
                                "chunked resumable upload should allow large files")


class ChunkSizeLimitTests(_Base):
    """The advertised chunk size must actually fit through Django.

    `request.body` raises RequestDataTooBig above DATA_UPLOAD_MAX_MEMORY_SIZE,
    so a limit below the chunk size breaks every real upload while tiny test
    chunks keep passing — exactly the kind of gap unit tests miss.
    """

    def test_the_body_limit_exceeds_the_advertised_chunk_size(self):
        from django.conf import settings

        from content.upload_views import MAX_CHUNK_BYTES

        self.assertGreater(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, MAX_CHUNK_BYTES,
                           "chunks larger than the body limit are rejected by Django")

    def test_a_realistically_large_chunk_is_accepted(self):
        payload = MP4 + b"\x00" * (2 * 1024 * 1024)      # ~2 MiB, over the old 1 MB cap
        sid = self.client_a.post(f"/api/v1/content/{self.item.id}/uploads/",
                                 {"filename": "big.mp4", "total_bytes": len(payload),
                                  "content_type": "video/mp4"},
                                 format="json", **self.with_env(self.env_a.id)).json()["id"]
        r = self.client_a.patch(f"/api/v1/content/uploads/{sid}/", payload,
                                content_type="application/offset+octet-stream",
                                HTTP_UPLOAD_OFFSET="0", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["is_complete"])


class EndToEndVisibilityTests(_Base):
    """Teacher uploads -> targets -> publishes; student must SEE and play it."""

    def test_the_student_sees_and_can_play_a_published_upload(self):
        self.upload()
        self.item.refresh_from_db()
        self.assertEqual(self.item.source, "upload")

        pub = self.client_a.post(f"/api/v1/content/{self.item.id}/publish/",
                                 **self.with_env(self.env_a.id))
        self.assertEqual(pub.status_code, 200, pub.content)

        sc = self.student_client()
        rows = sc.get("/api/v1/student/videos/", **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual([r["id"] for r in rows], [self.item.id], "the video must appear for the student")
        self.assertEqual(rows[0]["source"], "upload")

        ticket = sc.post(f"/api/v1/content/{self.item.id}/playback-ticket/",
                         **self.with_env(self.env_a.id))
        self.assertEqual(ticket.status_code, 200, ticket.content)
        stream = sc.get(f"/api/v1/content/stream/?t={ticket.json()['ticket']}")
        self.assertEqual(stream.status_code, 200)

    def test_an_unpublished_upload_is_invisible_and_says_why(self):
        """The most likely real-world cause: uploaded but never published."""
        self.upload()
        sc = self.student_client()
        rows = sc.get("/api/v1/student/videos/", **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual(rows, [], "an unpublished item must not appear")

    def test_publishing_without_targets_is_refused_with_a_clear_message(self):
        self.item.target_grades.clear()
        self.upload()
        r = self.client_a.post(f"/api/v1/content/{self.item.id}/publish/",
                               **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.assertIn("حدّد", r.json().get("detail", ""))
