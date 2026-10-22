"""
The central Knowledge Base: who may curate it, and the draft -> published
lifecycle that decides what the AI is allowed to use.

Documented rules under test (glossary.md, 09-operations/knowledge-base.md,
01-product/scope.md):
  * the KB is curated by the Content Maintainer (role=team) ONLY;
  * teachers do not curate AI sources in V1 — and the Content Maintainer has
    no access to teacher educational records;
  * the KB is central/product-owned, so it is NOT tenant-scoped;
  * only PUBLISHED content is authoritative for AI consumption.
"""
from rest_framework.test import APIClient

from accounts.models import User
from accounts.testing import TestCase
from environments.models import Environment, EnvironmentMembership

from .models import KBDocument
from .retrieval import select_sources

PW = "Str0ng!Pass"
URL = "/api/v1/knowledge/documents/"
BODY = {"title": "قانون نيوتن الأول", "topic": "فيزياء",
        "body": "الجسم الساكن يبقى ساكنًا والجسم المتحرك يبقى متحركًا ما لم تؤثر عليه قوة خارجية."}


def team_client():
    # Team accounts log in with their `username` identifier (they are
    # provisioned by staff via `manage.py create_team_user`).
    User.objects.create_user(username="kb@madar", role=User.Role.TEAM, name="maintainer",
                             password=PW, is_active=True, is_verified=True)
    c = APIClient()
    r = c.post("/api/v1/auth/team/login/", {"identifier": "kb@madar", "password": PW})
    assert r.status_code == 200, r.content
    c.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
    return c


class KBAuthoringTests(TestCase):
    def setUp(self):
        self.c = team_client()

    def test_maintainer_creates_drafts_that_are_not_yet_authoritative(self):
        r = self.c.post(URL, BODY)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["status"], "draft")
        self.assertEqual(KBDocument.published.count(), 0)

    def test_status_cannot_be_forced_through_the_payload(self):
        r = self.c.post(URL, {**BODY, "status": "published", "version": 99})
        self.assertEqual(r.json()["status"], "draft")
        self.assertEqual(r.json()["version"], 1)

    def test_publish_then_unpublish_controls_ai_visibility(self):
        doc_id = self.c.post(URL, BODY).json()["id"]
        self.assertEqual(self.c.post(f"{URL}{doc_id}/publish/").json()["status"], "published")
        self.assertEqual(KBDocument.published.count(), 1)
        self.assertEqual(self.c.post(f"{URL}{doc_id}/unpublish/").json()["status"], "draft")
        self.assertEqual(KBDocument.published.count(), 0)

    def test_editing_a_published_document_bumps_the_version_so_answers_can_cite_exactly_what_they_used(self):
        doc_id = self.c.post(URL, BODY).json()["id"]
        self.c.post(f"{URL}{doc_id}/publish/")
        edited = self.c.patch(f"{URL}{doc_id}/", {"body": BODY["body"] + " وتُسمّى أيضًا قانون القصور الذاتي."})
        self.assertEqual(edited.status_code, 200, edited.content)
        self.assertEqual(edited.json()["version"], 2, "live source text changed, so its version must change")
        self.assertEqual(edited.json()["status"], "published")

    def test_a_save_that_changes_nothing_does_not_bump_the_version(self):
        doc_id = self.c.post(URL, BODY).json()["id"]
        self.c.post(f"{URL}{doc_id}/publish/")
        same = self.c.patch(f"{URL}{doc_id}/", {"title": BODY["title"]})
        self.assertEqual(same.json()["version"], 1)

    def test_editing_a_draft_does_not_bump_the_version(self):
        doc_id = self.c.post(URL, BODY).json()["id"]
        edited = self.c.patch(f"{URL}{doc_id}/", {"title": "عنوان جديد واضح"})
        self.assertEqual(edited.json()["version"], 1)

    def test_republishing_bumps_the_lightweight_version(self):
        doc_id = self.c.post(URL, BODY).json()["id"]
        self.assertEqual(self.c.post(f"{URL}{doc_id}/publish/").json()["version"], 1)
        self.assertEqual(self.c.post(f"{URL}{doc_id}/publish/").json()["version"], 2)

    def test_validation_rejects_empty_curation(self):
        self.assertEqual(self.c.post(URL, {"title": "x", "body": "short"}).status_code, 400)


class KBAuthorizationTests(TestCase):
    """Only role=team may reach the KB at all."""

    def setUp(self):
        self.doc = KBDocument.objects.create(**BODY)

    def _teacher(self):
        u = User.objects.create_user(role=User.Role.TEACHER, name="t", email="t@example.com",
                                     phone="201010000001", password=PW, is_active=True)
        env = Environment.objects.create(owner=u, name="E")
        EnvironmentMembership.objects.create(user=u, environment=env, role="owner")
        c = APIClient()
        tok = c.post("/api/v1/auth/teacher/login/", {"identifier": "t@example.com", "password": PW}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        return c

    def test_anonymous_cannot_read_or_write_the_knowledge_base(self):
        anon = APIClient()
        self.assertEqual(anon.get(URL).status_code, 401)
        self.assertEqual(anon.post(URL, BODY).status_code, 401)

    def test_a_teacher_cannot_curate_ai_sources(self):
        c = self._teacher()
        self.assertEqual(c.get(URL).status_code, 403)
        self.assertEqual(c.post(URL, BODY).status_code, 403)
        self.assertEqual(c.post(f"{URL}{self.doc.id}/publish/").status_code, 403)

    def test_the_knowledge_base_is_central_not_tenant_scoped(self):
        """No environment column: one KB serves the whole product."""
        self.assertFalse(any(f.name == "environment" for f in KBDocument._meta.get_fields()))


class KBRetrievalTests(TestCase):
    def test_only_published_documents_can_ground_an_answer(self):
        draft = KBDocument.objects.create(**BODY)
        self.assertEqual(select_sources("قانون نيوتن"), [])
        draft.publish()
        self.assertEqual([d.id for d in select_sources("قانون نيوتن")], [draft.id])

    def test_irrelevant_question_selects_nothing(self):
        KBDocument.objects.create(**BODY).publish()
        self.assertEqual(select_sources("طبخ المكرونة بالبشاميل"), [])

    def test_arabic_punctuation_does_not_break_matching(self):
        KBDocument.objects.create(**BODY).publish()
        self.assertTrue(select_sources("ما هو قانون نيوتن؟"))

    def test_retrieval_is_bounded(self):
        for i in range(6):
            KBDocument.objects.create(title=f"نيوتن {i}", topic="فيزياء", body=BODY["body"]).publish()
        self.assertLessEqual(len(select_sources("قانون نيوتن")), 3)
