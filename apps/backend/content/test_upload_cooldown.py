"""Starting a video upload: 5 tries, then a 5-minute cooldown with a timer, then the allowance is back."""
from unittest import mock

from django.core.cache import cache
from django.test import override_settings

from .test_video import MP4, _Base


class UploadCooldownTests(_Base):
    CREATE = "/api/v1/content/{}/uploads/"
    SESSION = "/api/v1/content/uploads/{}/"

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def start(self):
        return self.client_a.post(
            self.CREATE.format(self.item.id),
            {"filename": "lesson.mp4", "total_bytes": len(MP4), "content_type": "video/mp4"},
            format="json", **self.with_env(self.env_a.id))

    def abandon(self, response):
        self.client_a.delete(self.SESSION.format(response.json()["id"]), **self.with_env(self.env_a.id))

    def test_five_tries_then_the_sixth_is_locked_with_a_timer(self):
        for n in range(5):
            r = self.start()
            self.assertEqual(r.status_code, 201, f"try {n + 1}: {r.content}")
            self.abandon(r)
        locked = self.start()
        self.assertEqual(locked.status_code, 429)
        body = locked.json()
        self.assertEqual(body["code"], "upload_cooldown")
        self.assertTrue(295 <= body["retry_after_seconds"] <= 300, body)
        self.assertIn("(5)", body["detail"])  # says how many tries there were
        self.assertRegex(body["detail"], r"\d:\d\d")  # and how long is left (m:ss)

    def test_the_lock_ends_after_five_minutes_and_the_allowance_is_full_again(self):
        with mock.patch("accounts.throttles.time.time", return_value=1_000_000.0):
            for _ in range(5):
                self.abandon(self.start())
            self.assertEqual(self.start().status_code, 429)
        # 4:59 later — still locked, and the timer is about to hit zero.
        with mock.patch("accounts.throttles.time.time", return_value=1_000_299.0):
            r = self.start()
            self.assertEqual(r.status_code, 429)
            self.assertEqual(r.json()["retry_after_seconds"], 1)
        # past 5:00 — free again, with a full allowance of five.
        with mock.patch("accounts.throttles.time.time", return_value=1_000_301.0):
            for n in range(5):
                r = self.start()
                self.assertEqual(r.status_code, 201, f"try {n + 1}: {r.content}")
                self.abandon(r)
            self.assertEqual(self.start().status_code, 429)

    def test_chunks_of_a_running_upload_never_use_up_the_tries(self):
        r = self.start()
        sid = r.json()["id"]
        # many chunk requests (here: re-sends of the same bytes at the offset the server holds)
        for _ in range(30):
            self.client_a.get(self.SESSION.format(sid), **self.with_env(self.env_a.id))
        done = self.client_a.patch(
            self.SESSION.format(sid), MP4, content_type="application/offset+octet-stream",
            HTTP_UPLOAD_OFFSET="0", **self.with_env(self.env_a.id))
        self.assertEqual(done.status_code, 200, done.content)
        self.assertTrue(done.json()["is_complete"])
        # and only ONE try was used, so four more are still available
        for _ in range(4):
            self.assertEqual(self.start().status_code, 201)

    def test_the_numbers_are_settings(self):
        with override_settings(VIDEO_UPLOAD_ATTEMPTS=2, VIDEO_UPLOAD_COOLDOWN_SECONDS=60):
            self.abandon(self.start())
            self.abandon(self.start())
            r = self.start()
            self.assertEqual(r.status_code, 429)
            self.assertLessEqual(r.json()["retry_after_seconds"], 60)

    def test_one_teachers_lock_does_not_lock_another(self):
        for _ in range(5):
            self.abandon(self.start())
        self.assertEqual(self.start().status_code, 429)
        other = self.client_b.post(
            self.CREATE.format(self.item.id),
            {"filename": "x.mp4", "total_bytes": len(MP4), "content_type": "video/mp4"},
            format="json", **self.with_env(self.env_b.id))
        self.assertNotEqual(other.status_code, 429)
