"""Quality ladder: real ffmpeg encodes + the security of serving them."""
import os
import shutil
import subprocess
import tempfile
from unittest import mock, skipUnless

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import TimestampSigner
from django.test import override_settings

from . import transcode
from .models import ContentItem, VideoRendition
from .streaming import SIGNER_SALT, issue_ticket
from .test_video import _Base, video

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def make_clip(height=720, seconds=2):
    """A REAL playable mp4, so ffprobe/ffmpeg exercise the true code path."""
    width = height * 16 // 9 // 2 * 2
    out = os.path.join(tempfile.mkdtemp(), "clip.mp4")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", out], check=True)
    with open(out, "rb") as fh:
        return fh.read()


class LadderUnitTests(_Base):
    def test_never_upscales(self):
        self.assertEqual(transcode.heights_for(720), [360, 480])
        self.assertEqual(transcode.heights_for(1080), [360, 480, 720])
        self.assertEqual(transcode.heights_for(360), [])
        self.assertEqual(transcode.heights_for(None), [])

    def test_missing_ffmpeg_is_harmless(self):
        self.upload()
        with mock.patch.object(transcode, "_bin", return_value=None):
            self.assertEqual(transcode.build_renditions(self.item.id), [])
        self.assertEqual(self.item.renditions.count(), 0)

    def test_a_fake_video_is_skipped_not_crashed(self):
        """MP4 fixtures with junk bytes: ffprobe cannot read them -> no renditions, no error."""
        self.upload()
        self.assertEqual(transcode.build_renditions(self.item.id), [])

    def test_ffmpeg_is_never_run_through_a_shell(self):
        self.upload()
        with mock.patch.object(transcode.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0)
            transcode._encode("/x/in.mp4", "/x/out.mp4", 360)
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("-nostdin", args[0])


@skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe not installed")
@override_settings(VIDEO_TRANSCODE=True, VIDEO_TRANSCODE_SYNC=True)
class RenditionPlaybackTests(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clip = make_clip(720)

    def setUp(self):
        super().setUp()
        r = self.upload(video("real.mp4", self.clip, "video/mp4"))
        self.assertEqual(r.status_code, 200, r.content)
        self.item.refresh_from_db()
        self.assertEqual(sorted(self.item.renditions.values_list("height", flat=True)), [360, 480])
        self.item.published_at = __import__("django").utils.timezone.now()
        self.item.save()

    def ticket(self, client, quality=None, pk=None):
        body = {"quality": quality} if quality is not None else {}
        return client.post(f"/api/v1/content/{pk or self.item.id}/playback-ticket/", body, format="json",
                           **self.with_env(self.env_a.id))

    def stream(self, client, t, **extra):
        return client.get(f"/api/v1/content/stream/?t={t}", **self.with_env(self.env_a.id), **extra)

    def body(self, resp):
        return b"".join(resp.streaming_content) if resp.streaming else resp.content

    def test_the_ticket_lists_the_available_qualities(self):
        r = self.ticket(self.student_client()).json()
        self.assertEqual(r["qualities"], [{"label": "480p", "height": 480}, {"label": "360p", "height": 360}])

    def test_a_chosen_quality_streams_that_rendition_not_the_original(self):
        sc = self.student_client()
        orig = self.stream(sc, self.ticket(sc).json()["ticket"])
        low = self.stream(sc, self.ticket(sc, "360p").json()["ticket"])
        self.assertEqual(orig.status_code, 200)
        self.assertEqual(low.status_code, 200)
        self.assertLess(int(low["Content-Length"]), int(orig["Content-Length"]))
        self.assertEqual(low["Content-Type"], "video/mp4")
        self.assertEqual(low["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", low["Cache-Control"])
        self.assertEqual(low["Content-Disposition"], "inline")
        rend = self.item.renditions.get(height=360)
        with open(rend.video_file.path, "rb") as fh:
            self.assertEqual(self.body(low), fh.read())

    def test_range_requests_work_on_renditions_so_seeking_works(self):
        sc = self.student_client()
        r = self.stream(sc, self.ticket(sc, 480).json()["ticket"], HTTP_RANGE="bytes=0-99")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Range"].split("/")[0], "bytes 0-99")
        self.assertEqual(len(self.body(r)), 100)

    def test_unknown_or_malicious_quality_is_a_400(self):
        sc = self.student_client()
        for bad in ("720p", "1080p", "9999", "0p", "360p; rm -rf /", "../../etc/passwd", "abc", [360], {"a": 1}, -360):
            with self.subTest(q=bad):
                self.assertEqual(self.ticket(sc, bad).status_code, 400)
        self.assertEqual(self.ticket(sc, "auto").status_code, 200)
        self.assertEqual(self.ticket(sc, "").status_code, 200)

    def test_quality_cannot_be_used_to_reach_another_items_rendition(self):
        other = ContentItem.objects.create(environment=self.env_a, title="آخر", published_at=self.item.published_at)
        other.target_grades.set([self.grade])
        self.upload(video("o.mp4"), pk=other.id)              # junk file: no renditions
        self.assertEqual(self.ticket(self.student_client(), "360p", pk=other.id).status_code, 400)

    def test_the_height_inside_a_ticket_cannot_be_edited(self):
        sc = self.student_client()
        t = self.ticket(sc, "360p").json()["ticket"]
        payload, ts, sig = t.rsplit(":", 2)
        forged = f"{payload.rsplit(':', 1)[0]}:480:{ts}:{sig}"
        self.assertEqual(self.stream(sc, forged).status_code, 404)

    def test_a_ticket_for_a_missing_rendition_is_404(self):
        sc = self.student_client()
        t = issue_ticket(self.item.id, self.student.id, 720)   # validly signed, but no 720p exists
        self.assertEqual(self.stream(sc, t).status_code, 404)

    def test_hand_signed_garbage_heights_are_refused(self):
        sc = self.student_client()
        for payload in (f"{self.item.id}:{self.student.id}:abc", f"{self.item.id}:{self.student.id}:1:2:3",
                        f"{self.item.id}:{self.student.id}:-5"):
            with self.subTest(p=payload):
                t = TimestampSigner(salt=SIGNER_SALT).sign(payload)
                self.assertEqual(self.stream(sc, t).status_code, 404)

    def test_revoking_access_kills_a_quality_ticket_immediately(self):
        sc = self.student_client()
        t = self.ticket(sc, "360p").json()["ticket"]
        self.assertEqual(self.stream(sc, t).status_code, 200)
        self.item.published_at = None
        self.item.save()
        self.assertEqual(self.stream(sc, t).status_code, 404)

    def test_a_quality_ticket_is_useless_after_the_enrolment_is_deactivated(self):
        sc = self.student_client()
        t = self.ticket(sc, 360).json()["ticket"]
        self.enr.is_active = False
        self.enr.save()
        self.assertEqual(self.stream(sc, t).status_code, 404)

    def test_an_outsider_student_gets_nothing(self):
        outsider = self.make_student_in(self.env_a, "201555700099", "غريب")
        outsider.set_password(__import__("environments.tenancy_testing", fromlist=["PASSWORD"]).PASSWORD)
        outsider.is_active = True
        outsider.is_verified = True
        outsider.save()
        from academics.models import Enrollment
        Enrollment.objects.create(environment=self.env_a, student=outsider, grade=self.grade.__class__.objects.create(
            environment=self.env_a, name="تاني"), parent_phone="201111000002")
        oc = self.student_client(phone=outsider.phone)
        self.assertEqual(self.ticket(oc, "360p").status_code, 404)

    def test_another_teacher_cannot_ask_for_a_quality_ticket(self):
        r = self.client_b.post(f"/api/v1/content/{self.item.id}/playback-ticket/", {"quality": "360p"}, format="json",
                               **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)

    def test_anonymous_cannot_ask_for_one(self):
        from rest_framework.test import APIClient
        r = APIClient().post(f"/api/v1/content/{self.item.id}/playback-ticket/", {"quality": "360p"}, format="json")
        self.assertIn(r.status_code, (401, 403))

    def test_the_stored_paths_never_leak_in_the_api(self):
        r = self.ticket(self.student_client(), "360p")
        blob = r.content.decode()
        for rend in self.item.renditions.all():
            self.assertNotIn(os.path.basename(rend.video_file.name), blob)
        self.assertNotIn("private-media", blob)
        self.assertNotIn(self.media, blob)

    def test_renditions_are_stored_with_random_server_names(self):
        for rend in self.item.renditions.all():
            self.assertRegex(rend.video_file.name, r"^videos/\d+/[A-Za-z0-9_-]{20,}\.mp4$")

    def test_replacing_the_video_deletes_old_renditions_and_blobs(self):
        old = [r.video_file.path for r in self.item.renditions.all()]
        self.assertTrue(all(os.path.exists(p) for p in old))
        self.upload(video("junk.mp4"))                       # junk: nothing new to encode
        self.assertEqual(self.item.renditions.count(), 0)
        self.assertFalse(any(os.path.exists(p) for p in old), "old renditions must not linger")

    def test_deleting_the_video_deletes_renditions_and_blobs(self):
        old = [r.video_file.path for r in self.item.renditions.all()]
        r = self.client_a.delete(f"/api/v1/content/{self.item.id}/video/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.item.renditions.count(), 0)
        self.assertFalse(any(os.path.exists(p) for p in old))

    def test_deleting_the_item_removes_the_blobs_too(self):
        old = [r.video_file.path for r in self.item.renditions.all()]
        self.item.delete()
        self.assertFalse(any(os.path.exists(p) for p in old))
        self.assertEqual(VideoRendition.objects.count(), 0)

    def test_a_video_replaced_mid_encode_discards_the_stale_output(self):
        VideoRendition.objects.all().delete()
        real_encode = transcode._encode

        def encode_then_replace(src, dst, h):
            ok = real_encode(src, dst, h)
            ContentItem.objects.filter(pk=self.item.id).update(video_file="videos/1/replaced.mp4")
            return ok

        with mock.patch.object(transcode, "_encode", side_effect=encode_then_replace):
            made = transcode.build_renditions(self.item.id)
        self.assertEqual(made, [])
        self.assertEqual(VideoRendition.objects.count(), 0)
        leftovers = [f for _, _, fs in os.walk(self.media) for f in fs]
        self.assertEqual(len(leftovers), 1, leftovers)       # only the original remains

    def test_rebuilding_is_idempotent(self):
        before = list(self.item.renditions.values_list("pk", flat=True))
        self.assertEqual(transcode.build_renditions(self.item.id), [])
        self.assertEqual(list(self.item.renditions.values_list("pk", flat=True)), before)

    def test_the_resumable_upload_path_also_builds_renditions(self):
        self.item.renditions.all().delete()
        data = self.clip
        c = self.client_a
        h = self.with_env(self.env_a.id)
        r = c.post(f"/api/v1/content/{self.item.id}/uploads/",
                   {"filename": "r.mp4", "total_bytes": len(data), "content_type": "video/mp4"}, format="json", **h)
        self.assertEqual(r.status_code, 201, r.content)
        sid = r.json()["id"]
        half = len(data) // 2
        for off, chunk in ((0, data[:half]), (half, data[half:])):
            p = c.patch(f"/api/v1/content/uploads/{sid}/", chunk, content_type="application/offset+octet-stream",
                        HTTP_UPLOAD_OFFSET=str(off), **h)
            self.assertEqual(p.status_code, 200, p.content)
        self.assertEqual(sorted(self.item.renditions.values_list("height", flat=True)), [360, 480])
