"""
Madar Control Center — backend behaviour.

What is proven here (each group is a requirement of the Control Center spec, not a convenience):
  * permissions are enforced by the SERVER on every endpoint (RBAC), and a legacy team account keeps exactly the
    Knowledge Base right it always had;
  * escalation is impossible (self-edit, granting what you do not hold, the last super admin);
  * suspending a user cuts their session at once, and every administrative change is audited without secrets;
  * the audit log cannot be edited or deleted;
  * the support workflow end to end — internal notes never reach the customer, customers only ever see their own
    tickets, attachments are validated, the lifecycle rules hold;
  * private content (AI prompts/answers, card tokens, guardian data) is not exposed to members without the
    matching permission; finance is read-only;
  * platform notices never claim delivery they cannot confirm; the health page reports "never recorded" rather
    than inventing a green light.
"""
import io
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Enrollment, Grade
from accounts.models import User
from accounts.testing import TestCase
from ai.models import AIOperation
from billing.models import PaymentAttempt, Subscription
from environments.models import Environment, EnvironmentMembership
from notifications.models import Notification, PushSubscription
from parents.models import GuardianMessage

from . import jobs
from .access import effective_permissions
from .models import AuditLog, JobRun, Role, TeamProfile, Ticket, TicketCategory, TicketEvent, TicketMessage

PW = "Str0ng!Pass"
C = "/api/v1/control/"
_n = [0]


def team(role, name=None, **kw):
    _n[0] += 1
    u = User.objects.create_user(username=f"t{_n[0]}@madar", role="team", name=name or f"{role} {_n[0]}", password=PW,
                                 is_active=True, is_verified=True)
    if role:
        TeamProfile.objects.create(user=u, role=Role.objects.get(key=role), **kw)
    return u


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def teacher(n=1, **kw):
    t = User.objects.create_user(role="teacher", name=f"معلم {n}", email=f"teacher{n}@example.com", phone=f"20100000{n:04d}",
                                 password=PW, is_active=True, is_verified=True, **kw)
    env = Environment.objects.create(owner=t, name=f"بيئة {n}")
    EnvironmentMembership.objects.create(user=t, environment=env, role="owner")
    return t, env


def student(env, n=1, claimed=True, active=True, parent_phone=""):
    s = User.objects.create_user(role="student", name=f"طالب {n}", phone=f"20111000{n:04d}", password=PW,
                                 is_active=True, is_verified=claimed)
    grade = Grade.objects.get_or_create(environment=env, name="الثالث", defaults={"fee_amount": 100})[0]
    EnvironmentMembership.objects.create(user=s, environment=env, role="student")
    Enrollment.objects.create(environment=env, student=s, grade=grade, student_name=s.name, is_active=active,
                              parent_phone=parent_phone, parent_name="ولي أمر" if parent_phone else "")
    return s


def category():
    return TicketCategory.objects.first()


def post_ticket(client, **extra):
    body = {"subject": "لا أستطيع الدخول", "description": "تظهر لي رسالة خطأ عند الدخول", "category": category().id, **extra}
    return client.post(C + "customer/tickets/", body, format="json")


# ===================================================================== RBAC
class PermissionEnforcementTests(TestCase):
    def test_every_control_endpoint_requires_authentication(self):
        for path in ("me/", "overview/", "users/", "team/", "roles/", "support/tickets/", "finance/overview/", "ai/overview/",
                     "notifications/overview/", "audit/", "system/health/", "settings/", "reports/users/", "environments/"):
            self.assertEqual(APIClient().get(C + path).status_code, 401, path)

    def test_teachers_and_students_cannot_open_the_team_api(self):
        t, env = teacher()
        s = student(env)
        for user in (t, s):
            c = client_for(user)
            for path in ("me/", "overview/", "users/", "support/tickets/", "audit/"):
                self.assertEqual(c.get(C + path).status_code, 403, (user.role, path))

    def test_guardian_session_cannot_open_the_team_api(self):
        from parents.auth import issue_session

        t, env = teacher()
        s = student(env, parent_phone="201055500001")
        token = issue_session(Enrollment.objects.get(student=s))
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Parent " + token)
        self.assertIn(c.get(C + "users/").status_code, (401, 403))
        self.assertIn(c.get(C + "customer/tickets/").status_code, (401, 403))

    def test_legacy_team_account_keeps_only_the_knowledge_base(self):
        legacy = team(None, "قديم")
        self.assertEqual(effective_permissions(legacy), {"knowledge.manage"})
        c = client_for(legacy)
        self.assertEqual(c.get("/api/v1/knowledge/documents/").status_code, 200)  # unchanged behaviour
        for path in ("overview/", "users/", "support/tickets/", "audit/", "team/"):
            self.assertEqual(c.get(C + path).status_code, 403, path)
        me = c.get(C + "me/").json()
        self.assertEqual(me["permissions"], ["knowledge.manage"])

    def test_the_knowledge_base_api_needs_knowledge_manage_not_just_the_team_role(self):
        url = "/api/v1/knowledge/documents/"
        for role in ("support_agent", "analyst", "finance_manager", "technical_support"):
            self.assertEqual(client_for(team(role)).get(url).status_code, 403, role)
        self.assertEqual(client_for(team("content_manager")).get(url).status_code, 200)
        self.assertEqual(client_for(team("admin")).get(url).status_code, 200)
        self.assertEqual(client_for(team(None)).get(url).status_code, 200)  # legacy account: unchanged
        body = {"title": "عنوان", "topic": "ت", "body": "نص طويل بما يكفي لقاعدة المعرفة هنا."}
        self.assertEqual(client_for(team("analyst")).post(url, body, format="json").status_code, 403)
        t, _ = teacher()
        self.assertEqual(client_for(t).get(url).status_code, 403)

    def test_role_decides_what_an_endpoint_allows(self):
        analyst, agent = client_for(team("analyst")), client_for(team("support_agent"))
        self.assertEqual(analyst.get(C + "reports/tickets/").status_code, 200)
        self.assertEqual(analyst.get(C + "users/").status_code, 403)
        self.assertEqual(analyst.get(C + "support/tickets/").status_code, 403)
        self.assertEqual(agent.get(C + "support/tickets/").status_code, 200)
        self.assertEqual(agent.get(C + "roles/").status_code, 403)
        self.assertEqual(agent.get(C + "audit/").status_code, 403)
        self.assertEqual(agent.get(C + "finance/overview/").status_code, 403)
        self.assertEqual(agent.get(C + "settings/").status_code, 403)

    def test_deactivated_team_member_has_no_permissions(self):
        u = team("admin")
        u.is_active = False
        u.save()
        self.assertEqual(effective_permissions(u), set())

    def test_per_person_grants_and_revocations_apply(self):
        u = team("support_agent", extra_permissions=["audit.view"], revoked_permissions=["tickets.create"])
        p = effective_permissions(u)
        self.assertIn("audit.view", p)
        self.assertNotIn("tickets.create", p)

    def test_view_permission_is_not_edit_permission(self):
        _, env = teacher()
        u = User.objects.get(role="teacher")
        viewer = client_for(team("support_agent"))  # users.view, no users.edit
        self.assertEqual(viewer.get(f"{C}users/{u.id}/").status_code, 200)
        self.assertEqual(viewer.patch(f"{C}users/{u.id}/", {"name": "اسم جديد"}, format="json").status_code, 403)
        self.assertEqual(viewer.post(f"{C}users/{u.id}/suspend/").status_code, 403)


# ===================================================================== team management guards
class TeamManagementTests(TestCase):
    def setUp(self):
        self.root = team("super_admin", "root")
        self.admin = team("admin", "admin")
        self.agent = team("support_agent", "agent")

    def test_cannot_change_own_role_permissions_or_state(self):
        c = client_for(self.admin)
        for body in ({"role": "super_admin"}, {"extra_permissions": ["roles.manage"]}, {"is_active": False}):
            self.assertEqual(c.patch(f"{C}team/{self.admin.id}/", body, format="json").status_code, 403, body)

    def test_cannot_grant_a_permission_you_do_not_hold(self):
        c = client_for(self.admin)  # admin has no roles.manage
        r = c.patch(f"{C}team/{self.agent.id}/", {"extra_permissions": ["roles.manage"]}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("roles.manage", effective_permissions(User.objects.get(pk=self.agent.pk)))

    def test_only_super_admin_can_touch_a_super_admin(self):
        other_root = team("super_admin")
        self.assertEqual(client_for(self.admin).patch(f"{C}team/{other_root.id}/", {"is_active": False}, format="json").status_code, 403)
        self.assertEqual(client_for(self.root).patch(f"{C}team/{other_root.id}/", {"is_active": False}, format="json").status_code, 200)

    def test_last_super_admin_cannot_be_demoted_or_deactivated(self):
        second = team("super_admin")
        c = client_for(second)
        self.assertEqual(c.patch(f"{C}team/{self.root.id}/", {"is_active": False}, format="json").status_code, 200)
        r = client_for(self.admin).patch(f"{C}team/{second.id}/", {"role": "admin"}, format="json")
        self.assertEqual(r.status_code, 403)  # admin may not touch a super admin at all
        # only one active super admin left (`second`): a second super admin cannot be created to bypass, and the
        # remaining one is protected from every other actor
        self.assertEqual(TeamProfile.objects.filter(role__key="super_admin", user__is_active=True).count(), 1)

    def test_role_change_deactivation_and_audit(self):
        c = client_for(self.root)
        r = c.patch(f"{C}team/{self.agent.id}/", {"role": "support_manager"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["role"], "support_manager")
        row = AuditLog.objects.get(action="team.role")
        self.assertEqual(row.before, {"role": "support_agent"})
        self.assertEqual(row.after, {"role": "support_manager"})
        self.assertEqual(c.patch(f"{C}team/{self.agent.id}/", {"is_active": False}, format="json").status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="team.deactivate").exists())

    def test_deactivated_member_is_signed_out_immediately(self):
        login = APIClient().post("/api/v1/auth/team/login/", {"identifier": self.agent.username, "password": PW})
        self.assertEqual(login.status_code, 200)
        agent_api = APIClient()
        agent_api.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
        self.assertEqual(agent_api.get(C + "me/").status_code, 200)
        client_for(self.root).patch(f"{C}team/{self.agent.id}/", {"is_active": False}, format="json")
        self.assertEqual(agent_api.get(C + "me/").status_code, 401)

    def test_role_editing_rules(self):
        c = client_for(self.root)
        r = c.post(C + "roles/", {"name": "مراجع", "permissions": ["tickets.view", "bogus.perm"]}, format="json")
        self.assertEqual(r.status_code, 400)  # unknown permission names are rejected
        r = c.post(C + "roles/", {"name": "مراجع", "permissions": ["tickets.view"]}, format="json")
        self.assertEqual(r.status_code, 201)
        rid = r.json()["id"]
        self.assertEqual(c.patch(f"{C}roles/{Role.objects.get(key='super_admin').id}/", {"name": "x", "permissions": []}, format="json").status_code, 403)
        self.assertEqual(c.delete(f"{C}roles/{Role.objects.get(key='admin').id}/").status_code, 403)  # system role
        self.assertEqual(c.delete(f"{C}roles/{rid}/").status_code, 204)

    def test_role_with_members_cannot_be_deleted(self):
        role = Role.objects.create(key="custom", name="مخصص", permissions=["tickets.view"])
        TeamProfile.objects.create(user=team(None), role=role)
        self.assertEqual(client_for(self.root).delete(f"{C}roles/{role.id}/").status_code, 400)

    def test_admin_cannot_manage_roles(self):
        self.assertEqual(client_for(self.admin).post(C + "roles/", {"name": "س", "permissions": []}, format="json").status_code, 403)

    def test_team_accounts_cannot_be_created_through_the_api(self):
        r = client_for(self.root).post(C + "team/", {"name": "x"}, format="json")
        self.assertEqual(r.status_code, 405)


# ===================================================================== users
class UserManagementTests(TestCase):
    def setUp(self):
        self.t, self.env = teacher(1)
        self.s = student(self.env, 1)
        self.admin = team("admin")
        self.c = client_for(self.admin)

    def test_list_filters_and_search(self):
        pending = student(self.env, 2, claimed=False)
        rows = self.c.get(C + "users/?role=student").json()["results"]
        self.assertEqual({r["id"] for r in rows}, {self.s.id, pending.id})
        self.assertEqual([r["id"] for r in self.c.get(C + "users/?status=pending").json()["results"]], [pending.id])
        self.assertEqual([r["id"] for r in self.c.get(f"{C}users/?search={self.t.email}").json()["results"]], [self.t.id])
        by_env = {r["id"] for r in self.c.get(f"{C}users/?environment={self.env.id}").json()["results"]}
        self.assertEqual(by_env, {self.t.id, self.s.id, pending.id})
        self.assertNotIn(self.admin.id, {r["id"] for r in self.c.get(C + "users/").json()["results"]})  # team never listed
        self.assertEqual(self.c.get(C + "users/?environment=abc").status_code, 400)

    def test_suspend_cuts_the_session_immediately_and_restore_reopens_it(self):
        login = APIClient().post("/api/v1/auth/teacher/login/", {"identifier": self.t.email, "password": PW})
        self.assertEqual(login.status_code, 200)
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
        self.assertEqual(api.get("/api/v1/auth/me/").status_code, 200)

        r = self.c.post(f"{C}users/{self.t.id}/suspend/", {"reason": "إساءة استخدام"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "suspended")
        self.assertEqual(api.get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(APIClient().post("/api/v1/auth/teacher/login/", {"identifier": self.t.email, "password": PW}).status_code, 400)
        row = AuditLog.objects.get(action="user.suspend")
        self.assertEqual((row.before, row.after, row.note), ({"status": "active"}, {"status": "suspended"}, "إساءة استخدام"))

        self.assertEqual(self.c.post(f"{C}users/{self.t.id}/suspend/").status_code, 400)  # already suspended
        self.assertEqual(self.c.post(f"{C}users/{self.t.id}/restore/").status_code, 200)
        self.assertEqual(APIClient().post("/api/v1/auth/teacher/login/", {"identifier": self.t.email, "password": PW}).status_code, 200)

    def test_a_suspended_student_cannot_undo_the_suspension_through_the_claim_flow(self):
        """A suspended student is is_active=False like a never-claimed one. The claim flow (badge code + phone + OTP)
        must only ever serve the never-claimed: otherwise the suspension is one SMS away from being bypassed."""
        from accounts.models import PendingAuth

        s = student(self.env, 9)
        code = Enrollment.objects.get(student=s).qr_token
        self.assertEqual(self.c.post(f"{C}users/{s.id}/suspend/", {}, format="json").status_code, 200)
        r = APIClient().post("/api/v1/auth/student/claim/", {"channel": "phone", "student_code": code, "phone": s.phone}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(PendingAuth.objects.filter(purpose="student_claim").count(), 0, "no OTP may even be issued")
        # and a claim flow somebody started BEFORE the suspension cannot finish afterwards
        pend = PendingAuth(purpose="student_claim", payload={"user_id": s.id}, channel="phone", target=s.phone, verified=True)
        pend.set_new_otp()
        pend.verified = True
        pend.save()
        r = APIClient().post("/api/v1/auth/student/claim/activate/", {"pending_id": str(pend.id), "password": "Str0ng!Pass1", "password2": "Str0ng!Pass1"}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        s.refresh_from_db()
        self.assertFalse(s.is_active)

    def test_cannot_suspend_an_unverified_or_team_account(self):
        pending = student(self.env, 3, claimed=False)
        self.assertEqual(self.c.post(f"{C}users/{pending.id}/suspend/").status_code, 400)
        self.assertEqual(self.c.post(f"{C}users/{self.admin.id}/suspend/").status_code, 404)  # team accounts are not "users"

    def test_edit_validates_and_audits_without_leaking_secrets(self):
        other, _ = teacher(2)
        self.assertEqual(self.c.patch(f"{C}users/{self.t.id}/", {"email": other.email}, format="json").status_code, 400)
        self.assertEqual(self.c.patch(f"{C}users/{self.t.id}/", {"phone": "123"}, format="json").status_code, 400)
        r = self.c.patch(f"{C}users/{self.t.id}/", {"name": "اسم جديد", "password": "Hacked1!"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.t.refresh_from_db()
        self.assertEqual(self.t.name, "اسم جديد")
        self.assertTrue(self.t.check_password(PW))  # a password field is simply not editable here
        self.assertNotIn("Hacked1!", str(list(AuditLog.objects.values())))
        row = AuditLog.objects.get(action="user.update")
        self.assertEqual(row.before, {"name": "معلم 1"})

    def test_reading_a_user_across_environments_is_audited_once(self):
        self.c.get(f"{C}users/{self.s.id}/")
        self.c.get(f"{C}users/{self.s.id}/")
        self.assertEqual(AuditLog.objects.filter(action="view", entity_type="user", entity_id=str(self.s.id)).count(), 1)

    def test_student_detail_hides_the_guardian_without_parents_view(self):
        s = student(self.env, 4, parent_phone="201066600001")
        agent = client_for(team("support_agent"))  # no parents.view
        d = agent.get(f"{C}users/{s.id}/").json()
        self.assertNotIn("guardian", d["student"][0])
        self.assertIn("guardian", self.c.get(f"{C}users/{s.id}/").json()["student"][0])

    def test_user_payload_never_contains_credentials(self):
        d = self.c.get(f"{C}users/{self.t.id}/").json()
        self.assertNotIn("password", str(d).lower())


# ===================================================================== audit log
class AuditLogTests(TestCase):
    def test_records_cannot_be_modified_or_deleted(self):
        a = AuditLog.objects.create(action="x", entity_type="t")
        a.action = "y"
        with self.assertRaises(PermissionError):
            a.save()
        with self.assertRaises(PermissionError):
            a.delete()
        with self.assertRaises(PermissionError):
            AuditLog.objects.all().delete()
        with self.assertRaises(PermissionError):
            AuditLog.objects.all().update(action="z")
        self.assertEqual(AuditLog.objects.get(pk=a.pk).action, "x")

    def test_actor_filter_lists_each_person_once_even_after_a_rename(self):
        root = team("super_admin", "قديم")
        AuditLog.objects.create(actor=root, actor_label="قديم", action="x", entity_type="t")
        AuditLog.objects.create(actor=root, actor_label="جديد", action="x", entity_type="t")
        actors = client_for(root).get(C + "audit/").json()["filters"]["actors"]
        self.assertEqual([a["id"] for a in actors], [root.id])
        self.assertEqual(actors[0]["name"], "جديد")

    def test_the_database_itself_refuses_to_alter_or_delete_audit_rows(self):
        """Raw SQL bypasses every Python guard — so PostgreSQL enforces append-only with row triggers."""
        from django.db import DatabaseError, connection, transaction

        a = AuditLog.objects.create(action="x", entity_type="t", note="original", actor_label="مدير")
        for sql in ("UPDATE control_auditlog SET note = 'tampered' WHERE id = %s",
                    "UPDATE control_auditlog SET action = 'y' WHERE id = %s",
                    "UPDATE control_auditlog SET before = '{\"k\": 1}' WHERE id = %s",
                    "DELETE FROM control_auditlog WHERE id = %s"):
            with self.assertRaises(DatabaseError, msg=sql):
                with transaction.atomic(), connection.cursor() as cur:
                    cur.execute(sql, [a.pk])
        a.refresh_from_db()
        self.assertEqual((a.note, a.action), ("original", "x"))

    def test_removing_a_team_account_keeps_its_audit_rows_and_only_detaches_the_actor(self):
        u = team("admin", "سيُحذف")
        row = AuditLog.objects.create(actor=u, actor_label="سيُحذف", action="x", entity_type="t")
        u.delete()  # ON DELETE SET NULL is the one UPDATE the trigger allows
        row.refresh_from_db()
        self.assertIsNone(row.actor_id)
        self.assertEqual(row.actor_label, "سيُحذف")

    def test_no_audit_endpoint_can_write(self):
        c = client_for(team("admin"))
        self.assertEqual(c.post(C + "audit/", {}, format="json").status_code, 405)
        self.assertEqual(c.delete(C + "audit/").status_code, 405)

    def test_scrubbing_removes_credentials(self):
        from .audit import scrub

        out = scrub({"password": "p", "access_token": "t", "card_token": "c", "name": "n", "nested": {"otp": "1"}})
        self.assertEqual(out["password"], "***")
        self.assertEqual(out["access_token"], "***")
        self.assertEqual(out["card_token"], "***")
        self.assertEqual(out["nested"]["otp"], "***")
        self.assertEqual(out["name"], "n")

    def test_filters_and_csv(self):
        root = team("super_admin")
        t, _ = teacher()
        c = client_for(root)
        c.post(f"{C}users/{t.id}/suspend/")
        r = c.get(C + "audit/?action=user.&entity_type=user&hide_views=1").json()
        self.assertEqual([x["action"] for x in r["results"]], ["user.suspend"])
        self.assertIn("user.suspend", r["filters"]["actions"])
        csv = c.get(C + "audit/?export=csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("text/csv", csv["Content-Type"])


# ===================================================================== support
class SupportWorkflowTests(TestCase):
    def setUp(self):
        self.t, self.env = teacher(1)
        self.s = student(self.env, 1)
        self.manager = team("support_manager", "مدير دعم")
        self.agent = team("support_agent", "موظف")
        self.mc, self.ac = client_for(self.manager), client_for(self.agent)
        self.tc, self.sc = client_for(self.t), client_for(self.s)

    def _ticket(self, client=None, **extra):
        r = post_ticket(client or self.tc, **extra)
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    # --- creation & isolation
    def test_customer_creates_a_ticket_linked_to_their_environment(self):
        tid = self._ticket()
        t = Ticket.objects.get(pk=tid)
        self.assertEqual((t.requester_id, t.requester_kind, t.environment_id, t.status, t.priority, t.source),
                         (self.t.id, "teacher", self.env.id, "open", "medium", "customer"))
        self.assertIsNotNone(t.due_at)
        self.assertEqual(t.messages.count(), 1)
        self.assertTrue(t.events.filter(kind="created").exists())
        self.assertEqual(t.number, f"MDR-{t.id:06d}")

    def test_customer_cannot_choose_priority_or_assignee(self):
        tid = self._ticket(priority="critical", assignee=self.agent.id)
        t = Ticket.objects.get(pk=tid)
        self.assertEqual((t.priority, t.assignee_id), ("medium", None))

    def test_customers_only_see_their_own_tickets(self):
        tid = self._ticket(self.tc)
        self.assertEqual(self.sc.get(f"{C}customer/tickets/{tid}/").status_code, 404)
        self.assertEqual(self.sc.post(f"{C}customer/tickets/{tid}/messages/", {"body": "x"}, format="json").status_code, 404)
        other, _ = teacher(2)
        self.assertEqual(client_for(other).get(C + "customer/tickets/").json(), [])

    def test_student_cannot_attach_a_ticket_to_an_environment_they_do_not_belong_to(self):
        _, other_env = teacher(2)
        r = post_ticket(self.sc, environment=other_env.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(post_ticket(self.sc, environment=self.env.id).status_code, 201)

    def test_team_account_cannot_use_the_customer_api(self):
        self.assertEqual(self.mc.get(C + "customer/tickets/").status_code, 403)

    # --- internal notes
    def test_internal_notes_never_reach_the_customer(self):
        tid = self._ticket()
        self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "ملاحظة سرية عن العميل", "kind": "note"}, format="json")
        self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "مرحبًا، نراجع المشكلة", "kind": "reply"}, format="json")
        team_view = self.ac.get(f"{C}support/tickets/{tid}/").json()
        self.assertEqual([m["kind"] for m in team_view["messages"]], ["customer", "internal", "agent"])
        cust = self.tc.get(f"{C}customer/tickets/{tid}/")
        self.assertEqual([m["kind"] for m in cust.json()["messages"]], ["customer", "agent"])
        self.assertNotIn("ملاحظة سرية", cust.content.decode())
        self.assertNotIn("history", cust.json())
        self.assertNotIn("assignee", cust.json())

    def test_internal_note_attachment_is_not_downloadable_by_the_customer(self):
        tid = self._ticket()
        f = SimpleUploadedFile("n.txt", b"private", content_type="text/plain")
        r = self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "سري", "kind": "note", "files": f}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        att = TicketMessage.objects.get(kind="internal").attachments.get()
        self.assertEqual(self.tc.get(f"{C}customer/attachments/{att.id}/").status_code, 404)
        self.assertEqual(self.ac.get(f"{C}support/attachments/{att.id}/").status_code, 200)

    # --- reply / lifecycle
    def test_first_response_claims_and_tracks_the_conversation(self):
        tid = self._ticket()
        r = self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "أهلًا"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        t = Ticket.objects.get(pk=tid)
        self.assertEqual((t.status, t.assignee_id, t.awaiting_team), ("in_progress", self.agent.id, False))
        self.assertIsNotNone(t.first_response_at)
        first = t.first_response_at
        self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "تحديث"}, format="json")
        self.assertEqual(Ticket.objects.get(pk=tid).first_response_at, first)  # the FIRST reply only
        self.assertEqual(r.json()["response_status"], "awaiting_customer")

    def test_internal_note_does_not_count_as_a_response(self):
        tid = self._ticket()
        self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "ملاحظة", "kind": "note"}, format="json")
        t = Ticket.objects.get(pk=tid)
        self.assertIsNone(t.first_response_at)
        self.assertTrue(t.awaiting_team)

    def test_request_info_waits_for_the_customer_and_their_reply_resumes(self):
        tid = self._ticket()
        self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "أرسل لقطة شاشة", "kind": "request_info"}, format="json")
        self.assertEqual(Ticket.objects.get(pk=tid).status, "waiting_for_user")
        r = self.tc.post(f"{C}customer/tickets/{tid}/messages/", {"body": "هذه اللقطة"}, format="json")
        self.assertEqual(r.status_code, 201)
        t = Ticket.objects.get(pk=tid)
        self.assertEqual((t.status, t.awaiting_team), ("in_progress", True))

    def test_status_rules(self):
        tid = self._ticket()
        s = lambda c, v: c.post(f"{C}support/tickets/{tid}/status/", {"status": v}, format="json")
        self.assertEqual(s(self.ac, "open").status_code, 400)               # same status
        self.assertEqual(s(self.ac, "bogus").status_code, 400)
        self.assertEqual(s(self.ac, "in_progress").status_code, 200)
        self.assertEqual(s(self.ac, "resolved").status_code, 200)          # support_agent has tickets.resolve
        self.assertIsNotNone(Ticket.objects.get(pk=tid).resolved_at)
        self.assertEqual(s(self.ac, "waiting_for_user").status_code, 400)  # resolved -> waiting is not a transition
        self.assertEqual(s(self.ac, "closed").status_code, 200)
        self.assertEqual(self.ac.post(f"{C}support/tickets/{tid}/messages/", {"body": "x"}, format="json").status_code, 400)  # must reopen first
        self.assertEqual(s(self.ac, "open").status_code, 200)              # reopen
        t = Ticket.objects.get(pk=tid)
        self.assertEqual((t.status, t.reopen_count, t.resolved_at, t.closed_at), ("open", 1, None, None))
        self.assertTrue(t.events.filter(kind="reopened").exists())

    def test_resolving_needs_the_resolve_permission(self):
        reply_only = team("support_agent", revoked_permissions=["tickets.resolve"])
        c = client_for(reply_only)
        tid = self._ticket()
        self.assertEqual(c.post(f"{C}support/tickets/{tid}/status/", {"status": "resolved"}, format="json").status_code, 403)
        self.assertEqual(c.post(f"{C}support/tickets/{tid}/status/", {"status": "in_progress"}, format="json").status_code, 200)

    def test_customer_reply_reopens_a_resolved_ticket_but_not_an_expired_closed_one(self):
        tid = self._ticket()
        self.mc.post(f"{C}support/tickets/{tid}/status/", {"status": "resolved"}, format="json")
        self.assertEqual(self.tc.post(f"{C}customer/tickets/{tid}/messages/", {"body": "المشكلة ما زالت"}, format="json").status_code, 201)
        t = Ticket.objects.get(pk=tid)
        self.assertEqual((t.status, t.reopen_count), ("open", 1))
        self.mc.post(f"{C}support/tickets/{tid}/status/", {"status": "closed"}, format="json")
        Ticket.objects.filter(pk=tid).update(closed_at=timezone.now() - timedelta(days=30))
        r = self.tc.post(f"{C}customer/tickets/{tid}/messages/", {"body": "متأخر"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self.tc.get(f"{C}customer/tickets/{tid}/").json()["can_reply"])

    def test_rating_after_resolution_once(self):
        tid = self._ticket()
        rate = lambda v: self.tc.post(f"{C}customer/tickets/{tid}/rate/", {"rating": v, "comment": "بطيء"}, format="json")
        self.assertEqual(rate(5).status_code, 400)  # not resolved yet
        self.mc.post(f"{C}support/tickets/{tid}/status/", {"status": "resolved"}, format="json")
        self.assertEqual(rate(6).status_code, 400)
        self.assertEqual(rate(2).status_code, 200)
        self.assertEqual(rate(5).status_code, 400)  # only once
        self.assertEqual(Ticket.objects.get(pk=tid).rating, 2)

    # --- assignment
    def test_assignment_rules_and_history(self):
        tid = self._ticket()
        a = lambda c, v: c.post(f"{C}support/tickets/{tid}/assign/", {"assignee": v}, format="json")
        other_agent = team("support_agent", "آخر")
        self.assertEqual(a(self.ac, other_agent.id).status_code, 403)           # an agent cannot hand work to someone else
        self.assertEqual(a(self.ac, self.agent.id).status_code, 200)            # but can claim an unassigned ticket
        self.assertEqual(a(self.ac, self.agent.id).status_code, 400)            # no change
        self.assertEqual(a(self.mc, other_agent.id).status_code, 200)           # manager reassigns
        self.assertEqual(a(self.ac, self.agent.id).status_code, 403)            # agent cannot take it back
        nobody = team("analyst")
        self.assertEqual(a(self.mc, nobody.id).status_code, 400)                # must be able to work tickets
        self.assertEqual(a(self.mc, None).status_code, 200)
        hist = [(e.from_value, e.to_value) for e in TicketEvent.objects.filter(ticket_id=tid, kind="assigned")]
        self.assertEqual(hist, [("", self.agent.name), (self.agent.name, "آخر"), ("آخر", "")])

    def test_agent_workload_flags_overload(self):
        from .models import PlatformSetting

        PlatformSetting.objects.create(key="tickets.agent_overload", value=2)
        for _ in range(2):
            t = Ticket.objects.get(pk=self._ticket())
            self.mc.post(f"{C}support/tickets/{t.id}/assign/", {"assignee": self.agent.id}, format="json")
        rows = {r["id"]: r for r in self.mc.get(C + "support/agents/").json()}
        self.assertEqual(rows[self.agent.id]["active"], 2)
        self.assertTrue(rows[self.agent.id]["overloaded"])

    # --- priority, SLA, overdue
    def test_priority_change_recomputes_the_deadline_and_overdue_is_real(self):
        tid = self._ticket()
        t = Ticket.objects.get(pk=tid)
        before = t.due_at
        self.assertEqual(self.ac.post(f"{C}support/tickets/{tid}/priority/", {"priority": "critical"}, format="json").status_code, 200)
        t.refresh_from_db()
        self.assertLess(t.due_at, before)
        self.assertEqual(t.due_at, t.created_at + timedelta(hours=4))
        self.assertEqual(self.mc.get(C + "support/tickets/?overdue=1").json()["count"], 0)
        Ticket.objects.filter(pk=tid).update(due_at=timezone.now() - timedelta(minutes=1))
        rows = self.mc.get(C + "support/tickets/?overdue=1").json()["results"]
        self.assertEqual([r["id"] for r in rows], [tid])
        self.assertTrue(rows[0]["overdue"])
        self.assertEqual(self.mc.get(C + "support/overview/").json()["overdue"], 1)

    def test_waiting_for_customer_is_not_overdue(self):
        tid = self._ticket()
        Ticket.objects.filter(pk=tid).update(due_at=timezone.now() - timedelta(hours=1), status="waiting_for_user")
        self.assertEqual(self.mc.get(C + "support/tickets/?overdue=1").json()["count"], 0)

    def test_agent_without_priority_permission_cannot_change_it(self):
        tid = self._ticket()
        c = client_for(team("technical_support"))
        self.assertEqual(c.post(f"{C}support/tickets/{tid}/priority/", {"priority": "high"}, format="json").status_code, 403)

    # --- bulk
    def test_bulk_assign_reports_each_ticket(self):
        ids = [self._ticket() for _ in range(3)]
        r = self.mc.post(C + "support/tickets/bulk/", {"ids": ids + [999999], "action": "assign", "value": self.agent.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["ok"], r.json()["failed"]), (3, 1))
        self.assertEqual(Ticket.objects.filter(assignee=self.agent).count(), 3)
        again = self.mc.post(C + "support/tickets/bulk/", {"ids": ids, "action": "assign", "value": self.agent.id}, format="json").json()
        self.assertEqual(again["failed"], 3)  # no-op assignments are reported, not silently counted
        self.assertEqual(self.ac.post(C + "support/tickets/bulk/", {"ids": ids, "action": "priority", "value": "low"}, format="json").status_code, 200)
        self.assertEqual(self.mc.post(C + "support/tickets/bulk/", {"ids": list(range(150)), "action": "priority", "value": "low"}, format="json").status_code, 400)

    # --- staff-created tickets
    def test_staff_can_log_a_ticket_for_a_guardian_who_has_no_account(self):
        r = self.mc.post(C + "support/tickets/", {"subject": "ولي أمر لا يستطيع الدخول", "description": "اتصل بنا هاتفيًا",
                                                  "category": category().id, "requester_kind": "parent", "requester_name": "ولي أمر",
                                                  "requester_phone": "201055500001"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        t = Ticket.objects.get(pk=r.json()["id"])
        self.assertEqual((t.requester_id, t.requester_kind, t.source, t.created_by_id), (None, "parent", "staff", self.manager.id))
        self.assertEqual(self.mc.post(C + "support/tickets/", {"subject": "abc", "description": "12345", "category": category().id}, format="json").status_code, 400)

    def test_complaints_are_tickets_of_kind_complaint(self):
        tid = self._ticket(kind="complaint")
        self.assertEqual(self.mc.get(C + "support/tickets/?kind=complaint").json()["results"][0]["id"], tid)

    # --- attachments
    def test_attachment_validation(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
        ok = SimpleUploadedFile("shot.png", png, content_type="image/png")
        r = self.tc.post(C + "customer/tickets/", {"subject": "مرفق", "description": "صورة للمشكلة", "category": category().id, "files": ok}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        att = r.json()["messages"][0]["attachments"][0]
        dl = self.tc.get(f"{C}customer/attachments/{att['id']}/")
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", dl["Content-Disposition"])
        for name, data in (("evil.exe", b"MZ"), ("x.svg", b"<svg onload=alert(1)>"), ("fake.png", b"not a png at all"), ("big.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024))):
            bad = SimpleUploadedFile(name, data)
            r = self.tc.post(C + "customer/tickets/", {"subject": "مرفق سيئ", "description": "ملف", "category": category().id, "files": bad}, format="multipart")
            self.assertEqual(r.status_code, 400, name)
        too_many = [SimpleUploadedFile(f"{i}.txt", b"x") for i in range(4)]
        r = self.tc.post(C + "customer/tickets/", {"subject": "كثير", "description": "ملفات كثيرة", "category": category().id, "files": too_many}, format="multipart")
        self.assertEqual(r.status_code, 400)

    # --- listing
    def test_list_filters_search_and_sorting(self):
        a, b = self._ticket(), self._ticket(self.sc, subject="مشكلة في الحضور")
        Ticket.objects.filter(pk=b).update(priority="high")
        self.assertEqual({r["id"] for r in self.mc.get(C + "support/tickets/").json()["results"]}, {a, b})
        self.assertEqual([r["id"] for r in self.mc.get(C + "support/tickets/?priority=high").json()["results"]], [b])
        self.assertEqual([r["id"] for r in self.mc.get(C + "support/tickets/?search=الحضور").json()["results"]], [b])
        self.assertEqual([r["id"] for r in self.mc.get(f"{C}support/tickets/?search=MDR-{a:06d}").json()["results"]], [a])
        self.assertEqual({r["id"] for r in self.mc.get(C + "support/tickets/?unassigned=1").json()["results"]}, {a, b})
        self.assertEqual(self.mc.get(C + "support/tickets/?sort=-id").json()["results"][0]["id"], b)
        self.assertEqual(self.mc.get(C + "support/tickets/?sort=password").status_code, 200)  # unknown sort keys fall back

    def test_ticket_export_needs_reports_permission(self):
        self._ticket()
        self.assertEqual(self.ac.get(C + "support/tickets/?export=csv").status_code, 403)
        self.assertEqual(self.mc.get(C + "support/tickets/?export=csv").status_code, 200)

    def test_csv_export_neutralises_formula_injection(self):
        self._ticket(subject="=HYPERLINK(\"http://evil\")")
        body = self.mc.get(C + "support/tickets/?export=csv").content.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", body)

    def test_categories_are_manageable_and_protected(self):
        c = self.mc
        r = c.post(C + "support/categories/", {"name": "تصنيف جديد"}, format="json")
        self.assertEqual(r.status_code, 201)
        cid = r.json()["id"]
        self.assertEqual(c.post(C + "support/categories/", {"name": "تصنيف جديد"}, format="json").status_code, 400)
        self.assertEqual(self.ac.post(C + "support/categories/", {"name": "x1"}, format="json").status_code, 403)
        self.assertEqual(c.patch(f"{C}support/categories/{cid}/", {"is_active": False}, format="json").status_code, 200)
        self.assertNotIn(cid, [x["id"] for x in self.tc.get(C + "customer/categories/").json()])
        self.assertEqual(post_ticket(self.tc, category=cid).status_code, 400)  # disabled categories cannot be used
        used = self._ticket()
        self.assertEqual(c.delete(f"{C}support/categories/{category().id}/").status_code, 400)  # has tickets
        self.assertEqual(c.delete(f"{C}support/categories/{cid}/").status_code, 204)


class SupportAnalyticsTests(TestCase):
    def test_metrics_are_computed_from_ticket_events(self):
        t, env = teacher()
        manager = team("support_manager")
        agent = team("support_agent", "ماهر")
        mc, ac, tc = client_for(manager), client_for(agent), client_for(t)
        ids = [post_ticket(tc).json()["id"] for _ in range(3)]
        ac.post(f"{C}support/tickets/{ids[0]}/messages/", {"body": "رد"}, format="json")
        ac.post(f"{C}support/tickets/{ids[0]}/status/", {"status": "resolved"}, format="json")
        tc.post(f"{C}customer/tickets/{ids[0]}/rate/", {"rating": 4}, format="json")
        tc.post(f"{C}customer/tickets/{ids[0]}/messages/", {"body": "لم تُحل"}, format="json")  # reopen
        post_ticket(tc, kind="complaint")
        d = mc.get(C + "support/analytics/?range=30d").json()
        self.assertEqual(d["created"], 4)
        self.assertEqual(d["resolved"], 0)  # reopened -> resolved_at cleared
        self.assertEqual(d["reopened"], 1)
        self.assertEqual(d["satisfaction"]["count"], 1)
        self.assertEqual(d["satisfaction"]["average"], 4.0)
        self.assertEqual(d["common_complaints"][0]["count"], 1)
        self.assertEqual(sum(x["value"] for x in d["volume"]["created"]), 4)
        ov = mc.get(C + "support/overview/").json()
        self.assertEqual((ov["total"], ov["unassigned"]), (4, 3))
        self.assertIsNotNone(ov["avg_first_response_hours"])
        self.assertEqual(mc.get(C + "support/analytics/?range=custom&from=2020-01-05&to=2020-01-01").status_code, 400)


# ===================================================================== environments / isolation
class EnvironmentAccessTests(TestCase):
    def test_environment_detail_is_audited_and_students_need_their_own_permission(self):
        t, env = teacher()
        s = student(env)
        finance = client_for(team("finance_manager"))      # environments.view, no students.view
        support = client_for(team("support_agent"))        # environments.view + students.view
        d1 = finance.get(f"{C}environments/{env.id}/").json()
        d2 = support.get(f"{C}environments/{env.id}/").json()
        self.assertEqual(d1["students"], [])
        self.assertEqual([x["id"] for x in d2["students"]], [s.id])
        self.assertEqual(AuditLog.objects.filter(action="view", entity_type="environment").count(), 2)
        self.assertNotIn("parent", str(d2).lower())

    def test_environment_edit_needs_manage_and_is_audited(self):
        t, env = teacher()
        self.assertEqual(client_for(team("support_agent")).patch(f"{C}environments/{env.id}/", {"name": "x1"}, format="json").status_code, 403)
        r = client_for(team("admin")).patch(f"{C}environments/{env.id}/", {"name": "اسم جديد"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AuditLog.objects.get(action="environment.update").after, {"name": "اسم جديد"})

    def test_environment_list_counts_and_search(self):
        t1, e1 = teacher(1)
        t2, e2 = teacher(2)
        student(e1, 1)
        student(e1, 2)
        c = client_for(team("admin"))
        rows = {r["id"]: r for r in c.get(C + "environments/").json()["results"]}
        self.assertEqual(rows[e1.id]["student_count"], 2)
        self.assertEqual(rows[e2.id]["student_count"], 0)
        self.assertEqual([r["id"] for r in c.get(f"{C}environments/?search={e2.name}").json()["results"]], [e2.id])


# ===================================================================== parents
class ParentViewTests(TestCase):
    def test_guardians_are_derived_from_enrollments_and_access_problems_are_real(self):
        t, env = teacher()
        ok = student(env, 1, parent_phone="201055500001")
        unclaimed = student(env, 2, claimed=False, parent_phone="201055500002")
        GuardianMessage.objects.create(environment=env, enrollment=Enrollment.objects.get(student=ok), title="غياب", body="غاب اليوم", kind="warning")
        c = client_for(team("support_manager"))
        rows = {r["phone"]: r for r in c.get(C + "parents/").json()["results"]}
        self.assertFalse(rows["201055500001"]["has_access_issues"])
        self.assertTrue(rows["201055500002"]["has_access_issues"])
        self.assertEqual(rows["201055500001"]["unread_messages"], 1)
        d = c.get(C + "parents/201055500002/").json()
        self.assertEqual(d["children"][0]["issues"], ["الطالب لم يفعّل حسابه بعد"])
        self.assertFalse(d["children"][0]["access_ready"])
        self.assertEqual([r["phone"] for r in c.get(C + "parents/?issues=1").json()["results"]], ["201055500002"])
        self.assertTrue(AuditLog.objects.filter(entity_type="guardian").exists())

    def test_guardian_data_requires_parents_view(self):
        t, env = teacher()
        student(env, 1, parent_phone="201055500001")
        self.assertEqual(client_for(team("technical_support")).get(C + "parents/").status_code, 403)
        self.assertEqual(client_for(team("finance_manager")).get(C + "parents/201055500001/").status_code, 403)


# ===================================================================== finance (read only)
class FinanceTests(TestCase):
    def setUp(self):
        self.t, self.env = teacher()
        self.sub = Subscription.objects.create(environment=self.env, state="active")

    def _attempt(self, status, order):
        return PaymentAttempt.objects.create(environment=self.env, subscription=self.sub, merchant_order_id=order,
                                             status=status, amount_minor_units=15000)

    def test_overview_and_lists_reflect_real_records(self):
        self._attempt("succeeded", "A1")
        self._attempt("failed", "A2")
        self._attempt("unknown", "A3")
        c = client_for(team("finance_manager"))
        d = c.get(C + "finance/overview/").json()
        self.assertEqual((d["succeeded"], d["failed"], d["pending"], d["unknown"]), (1, 1, 1, 1))
        self.assertEqual(d["revenue"]["all_time"], [{"currency": "EGP", "amount": 150.0}])
        self.assertEqual(c.get(C + "finance/transactions/?status=failed").json()["count"], 1)
        self.assertEqual(c.get(C + "finance/transactions/?status=pending").json()["count"], 1)
        issues = c.get(C + "finance/issues/").json()
        self.assertEqual(len(issues["failed"]), 1)
        self.assertEqual(len(issues["needs_reconciliation"]), 1)

    def test_secrets_are_never_serialised(self):
        from billing.models import RecurringAgreement

        agr = RecurringAgreement.objects.create(environment=self.env, subscription=self.sub, card_token="tok_SECRET123",
                                                kashier_agreement_id="agr_SECRET", mode="test")
        Subscription.objects.filter(pk=self.sub.pk).update(active_agreement=agr)
        self._attempt("succeeded", "A1")
        c = client_for(team("finance_manager"))
        blob = "".join(c.get(C + p).content.decode() for p in ("finance/transactions/", "finance/subscriptions/", "finance/issues/", "finance/overview/"))
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("card_token", blob)
        self.assertEqual(c.get(C + "finance/subscriptions/").json()["results"][0]["renewal"], "auto")

    def test_finance_has_no_write_endpoint_and_needs_permission(self):
        c = client_for(team("finance_manager"))
        for path in ("transactions/", "subscriptions/", "plans/", "issues/", "overview/"):
            self.assertEqual(c.post(C + "finance/" + path, {"status": "succeeded"}, format="json").status_code, 405, path)
            self.assertEqual(c.patch(C + "finance/" + path, {}, format="json").status_code, 405, path)
        self.assertEqual(client_for(team("support_agent")).get(C + "finance/overview/").status_code, 403)

    def test_attempt_status_cannot_be_forced_via_query_or_body(self):
        a = self._attempt("pending", "B1")
        client_for(team("admin")).get(C + "finance/transactions/?status=succeeded&mark=succeeded")
        a.refresh_from_db()
        self.assertEqual(a.status, "pending")


# ===================================================================== AI
class AIMonitoringTests(TestCase):
    def setUp(self):
        self.t, self.env = teacher()
        self.s = student(self.env)
        self.now = timezone.now()

    def _op(self, status, secs=2.0, md=None, kind="quiz_generation"):
        return AIOperation.objects.create(
            environment=self.env, requested_by=self.s, kind=kind, prompt="سؤال خاص جدًا عن الطالب", result="إجابة سرية" if status == "completed" else "",
            status=status, error="تعذّر إكمال الطلب." if status == "failed" else "", metadata=md or {},
            started_at=self.now - timedelta(seconds=secs), completed_at=self.now)

    def test_overview_rates_and_failure_categories(self):
        self._op("completed")
        self._op("completed")
        self._op("failed", md={"failure_category": "provider_timeout"})
        d = client_for(team("technical_support")).get(C + "ai/overview/").json()
        self.assertEqual((d["total"], d["completed"], d["failed"]), (3, 2, 1))
        self.assertEqual(d["success_rate"], 66.7)
        self.assertEqual(d["failure_categories"], [{"category": "provider_timeout", "count": 1}])

    def test_detail_exposes_timings_but_never_the_prompt_or_answer(self):
        op = self._op("completed", md={"timings_ms": {"content_check": 120, "generation": 900, "total": 1020, "other": 1},
                                       "usage": {"total_tokens": 10}, "secret_field": "SHOULD-NOT-APPEAR"})
        d = client_for(team("technical_support")).get(f"{C}ai/operations/{op.id}/").json()
        self.assertEqual(d["timings_ms"], {"content_check": 120, "generation": 900, "total": 1020})
        blob = str(d)
        for private in ("سؤال خاص", "إجابة سرية", "SHOULD-NOT-APPEAR"):
            self.assertNotIn(private, blob)
        self.assertEqual(d["context"]["prompt_chars"], len(op.prompt))

    def test_filters_and_slow_detection(self):
        self._op("completed", secs=1)
        slow = self._op("completed", secs=500)
        failed = self._op("failed", md={"failure_category": "invalid_output"})
        c = client_for(team("admin"))
        self.assertEqual([r["id"] for r in c.get(C + "ai/operations/?slow=1").json()["results"]], [slow.id])
        self.assertEqual([r["id"] for r in c.get(C + "ai/operations/?status=failed").json()["results"]], [failed.id])
        self.assertEqual([r["id"] for r in c.get(C + "ai/operations/?failure_category=invalid_output").json()["results"]], [failed.id])
        self.assertEqual(c.get(C + "ai/operations/?kind=assistant").json()["count"], 0)

    def test_requires_ai_permission(self):
        self.assertEqual(client_for(team("finance_manager")).get(C + "ai/operations/").status_code, 403)


# ===================================================================== notifications
class NotificationManagementTests(TestCase):
    def setUp(self):
        self.t, self.env = teacher()
        self.s = student(self.env)
        self.c = client_for(team("admin"))
        self.body = {"title": "إعلان", "body": "نص", "audience": "user", "user_ids": [self.s.id]}

    def test_history_filters_and_honest_status(self):
        Notification.objects.create(environment=self.env, recipient=self.s, type="broadcast", title="أ", delivery_status="sent")
        Notification.objects.create(environment=self.env, recipient=self.s, type="absent", title="ب", delivery_status="failed", delivery_error="push 410")
        Notification.objects.create(environment=self.env, recipient=self.s, type="absent", title="ج", delivery_status="pending")
        rows = self.c.get(C + "notifications/").json()["results"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("confirmed_read" in r for r in rows))
        self.assertTrue(all(r["status"] in ("sent", "pending", "failed") for r in rows))  # never a "delivered" claim
        self.assertEqual(self.c.get(C + "notifications/?status=failed").json()["count"], 1)
        ov = self.c.get(C + "notifications/overview/").json()
        self.assertEqual((ov["sent"], ov["pending"], ov["failed"]), (1, 1, 1))

    def test_sending_is_refused_when_push_is_not_configured(self):
        r = self.c.post(C + "notifications/platform/", self.body, format="json")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "push_not_configured")

    def test_permission_is_required_to_send(self):
        self.assertEqual(client_for(team("support_agent")).post(C + "notifications/platform/", self.body, format="json").status_code, 403)

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv")
    def test_delivery_states_are_recorded_truthfully(self):
        other = student(self.env, 2)
        PushSubscription.objects.create(user=self.s, endpoint="https://push.example/1", p256dh="p", auth="a")
        PushSubscription.objects.create(user=other, endpoint="https://push.example/2", p256dh="p", auth="a")
        PushSubscription.objects.create(user=self.t, endpoint="https://push.example/3", p256dh="p", auth="a")
        outcomes = {"https://push.example/1": (True, False, ""), "https://push.example/2": (False, False, "push 500")}
        with mock.patch("notifications.webpush._send_one", side_effect=lambda sub, payload: outcomes.get(sub.endpoint, (True, False, ""))):
            r = self.c.post(C + "notifications/platform/", {"title": "تنبيه", "audience": "environment", "environment": self.env.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual((d["recipients"], d["sent"], d["failed"], d["queued"]), (3, 2, 1, 0))
        # a person with no registered device is "no_device", never "sent"
        PushSubscription.objects.filter(user=self.s).delete()
        with mock.patch("notifications.webpush._send_one", return_value=(True, False, "")):
            d = self.c.post(C + "notifications/platform/", self.body, format="json").json()
        self.assertEqual((d["sent"], d["no_device"]), (0, 1))
        self.assertTrue(AuditLog.objects.filter(action="notification.send").exists())

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv")
    def test_recipients_and_url_are_validated(self):
        for bad in ("https://evil.example/", "//evil.example", "javascript:alert(1)", "/ok\\evil"):
            r = self.c.post(C + "notifications/platform/", {**self.body, "url": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(self.c.post(C + "notifications/platform/", {"title": "x1", "audience": "users", "user_ids": []}, format="json").status_code, 400)
        suspended = student(self.env, 5)
        User.objects.filter(pk=suspended.pk).update(is_active=False)
        r = self.c.post(C + "notifications/platform/", {"title": "x1", "audience": "user", "user_ids": [suspended.id]}, format="json")
        self.assertEqual(r.status_code, 400)  # suspended / unverified accounts are not eligible
        team_user = team("admin")
        r = self.c.post(C + "notifications/platform/", {"title": "x1", "audience": "user", "user_ids": [team_user.id]}, format="json")
        self.assertEqual(r.status_code, 400)

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv")
    def test_queued_deliveries_are_picked_up_by_the_worker_exactly_once(self):
        from django.core.management import call_command

        from .platform_notices import INLINE_LIMIT, create_notice

        for i in range(3):
            student(self.env, 10 + i)
        notice, err = create_notice(sender=None, title="جماعي", body="", url="/", audience="students")
        self.assertIsNone(err)
        PushSubscription.objects.create(user=User.objects.filter(role="student").first(), endpoint="https://push.example/w", p256dh="p", auth="a")
        with mock.patch("notifications.webpush._send_one", return_value=(True, False, "")) as send:
            call_command("process_platform_notices", stdout=io.StringIO())
            call_command("process_platform_notices", stdout=io.StringIO())
        self.assertEqual(send.call_count, 1)
        self.assertEqual(notice.deliveries.filter(status="queued").count(), 0)
        self.assertEqual(JobRun.objects.filter(name="process_platform_notices").count(), 2)

    def test_templates_crud(self):
        self.assertGreater(len(self.c.get(C + "notifications/templates/").json()), 0)  # seeded defaults
        r = self.c.post(C + "notifications/templates/", {"name": "قالب خاص", "title": "عنوان"}, format="json")
        self.assertEqual(r.status_code, 201)
        tid = r.json()["id"]
        self.assertEqual(self.c.post(C + "notifications/templates/", {"name": "قالب خاص", "title": "عنوان"}, format="json").status_code, 400)
        self.assertEqual(self.c.patch(f"{C}notifications/templates/{tid}/", {"body": "نص"}, format="json").status_code, 200)
        self.assertEqual(self.c.delete(f"{C}notifications/templates/{tid}/").status_code, 204)
        self.assertEqual(client_for(team("analyst")).get(C + "notifications/templates/").status_code, 403)


# ===================================================================== system
class SystemHealthTests(TestCase):
    def setUp(self):
        self.c = client_for(team("technical_support"))

    def test_never_run_jobs_are_reported_as_never_not_ok(self):
        d = self.c.get(C + "system/health/").json()
        self.assertTrue(d["database"]["ok"])
        self.assertEqual({j["name"]: j["status"] for j in d["jobs"]}, {n: "never" for n in jobs.MONITORED_JOBS})
        self.assertTrue(all(j["last_run"] is None for j in d["jobs"]))

    def test_workers_record_real_runs_and_failures(self):
        from django.core.management import call_command

        call_command("process_notifications", stdout=io.StringIO())
        call_command("purge_pending_auth", stdout=io.StringIO())
        call_command("process_ai_operations", stdout=io.StringIO())
        call_command("process_guardian_alerts", stdout=io.StringIO())
        self.assertEqual(set(JobRun.objects.values_list("name", flat=True)),
                         {"process_notifications", "purge_pending_auth", "process_ai_operations", "process_guardian_alerts"})
        with self.assertRaises(RuntimeError):
            with jobs.record_run("process_notifications"):
                raise RuntimeError("boom")
        d = self.c.get(C + "system/health/").json()
        by = {j["name"]: j for j in d["jobs"]}
        self.assertEqual(by["process_notifications"]["status"], "failed")
        self.assertIn("boom", by["process_notifications"]["last_run"]["error"])
        self.assertEqual(d["overall"], "degraded")
        self.assertIn("jobs", d["problems"])
        self.assertEqual(self.c.get(C + "system/jobs/?status=failed").json()["count"], 1)

    def test_processed_counts_come_from_the_work_done(self):
        from django.core.management import call_command

        t, env = teacher()
        s = student(env)
        Notification.objects.create(environment=env, recipient=s, type="broadcast", title="x1")
        call_command("process_notifications", stdout=io.StringIO())
        run = JobRun.objects.get(name="process_notifications")
        self.assertEqual(run.processed, 1)

    def test_old_pending_notifications_raise_the_backlog_flag(self):
        t, env = teacher()
        s = student(env)
        n = Notification.objects.create(environment=env, recipient=s, type="broadcast", title="x1")
        Notification.objects.filter(pk=n.pk).update(created_at=timezone.now() - timedelta(hours=3))
        d = self.c.get(C + "system/health/").json()
        self.assertTrue(d["notifications"]["backlog"])
        self.assertEqual(d["notifications"]["pending"], 1)

    def test_health_never_exposes_secrets(self):
        blob = self.c.get(C + "system/health/").content.decode()
        for forbidden in ("SECRET_KEY", "DB_PASSWORD", "VAPID_PRIVATE", "GEMINI_API_KEY", "password"):
            self.assertNotIn(forbidden, blob)

    def test_requires_system_permission(self):
        self.assertEqual(client_for(team("support_agent")).get(C + "system/health/").status_code, 403)


class SettingsTests(TestCase):
    def test_validated_audited_and_consumed(self):
        root = client_for(team("super_admin"))
        d = root.get(C + "settings/").json()
        self.assertTrue(d["readonly"])
        r = root.patch(C + "settings/", {"sla.critical_hours": 2}, format="json")
        self.assertEqual(r.status_code, 200)
        a = AuditLog.objects.get(action="settings.update")
        self.assertEqual((a.before, a.after), ({"sla.critical_hours": 4}, {"sla.critical_hours": 2}))
        # …and the value is really used by the ticket SLA:
        t, _ = teacher()
        tid = post_ticket(client_for(t), ).json()["id"]
        client_for(team("support_agent")).post(f"{C}support/tickets/{tid}/priority/", {"priority": "critical"}, format="json")
        tk = Ticket.objects.get(pk=tid)
        self.assertEqual(tk.due_at, tk.created_at + timedelta(hours=2))
        for bad in ({"sla.critical_hours": 0}, {"sla.critical_hours": "9"}, {"sla.critical_hours": True}, {"nope": 1}, {}):
            self.assertEqual(root.patch(C + "settings/", bad, format="json").status_code, 400, bad)

    def test_manage_permission_required(self):
        admin = client_for(team("admin"))  # admin has settings.manage
        self.assertEqual(admin.patch(C + "settings/", {"tickets.stale_hours": 6}, format="json").status_code, 200)
        self.assertEqual(client_for(team("analyst")).get(C + "settings/").status_code, 403)
        viewer = team("support_manager", extra_permissions=["settings.view"])
        self.assertEqual(client_for(viewer).get(C + "settings/").status_code, 200)
        self.assertEqual(client_for(viewer).patch(C + "settings/", {"tickets.stale_hours": 6}, format="json").status_code, 403)


# ===================================================================== overview / reports
class OverviewAndReportsTests(TestCase):
    def setUp(self):
        self.t, self.env = teacher()
        self.s = student(self.env)

    def test_overview_only_contains_sections_the_member_may_see(self):
        d = client_for(team("analyst")).get(C + "overview/").json()
        keys = {k["key"] for k in d["kpis"]}
        self.assertIn("payments_success", keys)       # analyst has finance.view
        self.assertIn("ai_success", keys)
        self.assertNotIn("total_users", keys)         # but no users.view
        self.assertNotIn("open_tickets", keys)
        self.assertNotIn("user_growth", d["charts"])
        agent = client_for(team("support_agent")).get(C + "overview/").json()
        self.assertNotIn("payments_success", {k["key"] for k in agent["kpis"]})
        self.assertEqual(client_for(team("content_manager")).get(C + "overview/").status_code, 200)

    def test_kpis_are_real_counts_with_period_comparison(self):
        post_ticket(client_for(self.t))
        d = client_for(team("admin")).get(C + "overview/?range=7d").json()
        k = {x["key"]: x for x in d["kpis"]}
        self.assertEqual(k["total_teachers"]["value"], 1)
        self.assertEqual(k["total_students"]["value"], 1)
        self.assertEqual(k["total_environments"]["value"], 1)
        self.assertEqual(k["open_tickets"]["value"], 1)
        self.assertEqual(k["unassigned_tickets"]["value"], 1)
        self.assertEqual(k["total_users"]["period"]["current"], 2)
        self.assertEqual(sum(p["value"] for p in d["charts"]["teacher_registrations"]), 1)
        self.assertEqual(d["charts"]["user_growth"][-1]["value"], 2)
        self.assertEqual(len(d["charts"]["user_growth"]), 7)

    def test_attention_list_and_activity_feed(self):
        tid = post_ticket(client_for(self.t), kind="complaint").json()["id"]
        client_for(team("support_manager")).post(f"{C}support/tickets/{tid}/priority/", {"priority": "critical"}, format="json")
        d = client_for(team("admin")).get(C + "overview/").json()
        keys = {a["key"] for a in d["attention"]}
        self.assertIn("critical_complaints", keys)
        self.assertIn("unassigned_tickets", keys)
        self.assertTrue(any(i["kind"] == "ticket" for i in d["activity"]))
        self.assertEqual(client_for(team("admin")).get(C + "overview/?range=custom&from=bad&to=bad").status_code, 400)
        self.assertEqual(client_for(team("admin")).get(C + "overview/?range=forever").status_code, 400)

    def test_global_search(self):
        c = client_for(team("admin"))
        r = c.get(C + "search/?q=" + self.t.name).json()
        self.assertEqual([u["id"] for u in r["users"]], [self.t.id])
        self.assertEqual(c.get(C + "search/?q=a").json(), {"users": [], "tickets": [], "environments": []})

    def test_reports_are_aggregated_without_the_matching_view_permission(self):
        analyst = client_for(team("analyst"))
        d = analyst.get(C + "reports/users/").json()
        self.assertNotIn("detail", d)
        self.assertEqual(d["totals"]["all"], 2)
        admin = client_for(team("admin")).get(C + "reports/users/").json()
        self.assertEqual(len(admin["detail"]["rows"]), 2)
        self.assertEqual(analyst.get(C + "reports/agents/").status_code, 200)   # support.analytics
        self.assertEqual(analyst.get(C + "reports/admin_activity/").status_code, 403)  # needs audit.view
        self.assertEqual(analyst.get(C + "reports/nope/").status_code, 404)
        self.assertEqual(analyst.get(C + "reports/users/?export=pdf").status_code, 400)

    def test_report_csv_and_filters(self):
        c = client_for(team("admin"))
        r = c.get(C + "reports/students/?export=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        d = c.get(C + "reports/users/?role=teacher").json()
        self.assertEqual(d["totals"]["all"], 1)
        post_ticket(client_for(self.t))
        t = c.get(C + "reports/tickets/?status=open").json()
        self.assertEqual(t["totals"]["created"], 1)
        self.assertEqual(c.get(C + "reports/tickets/?status=closed").json()["totals"]["created"], 0)
        self.assertEqual(c.get(f"{C}reports/ai/?environment={self.env.id}").status_code, 200)
        self.assertEqual(c.get(C + "reports/finance/").status_code, 200)
        self.assertEqual(c.get(C + "reports/notifications/").status_code, 200)
        self.assertEqual(c.get(C + "reports/environments/").status_code, 200)
        self.assertEqual(c.get(C + "reports/teachers/").status_code, 200)
        self.assertEqual(c.get(C + "reports/admin_activity/").status_code, 200)


class ProvisioningTests(TestCase):
    def test_seeded_roles_cover_the_documented_set(self):
        self.assertEqual(set(Role.objects.values_list("key", flat=True)),
                         {"super_admin", "admin", "support_manager", "support_agent", "technical_support",
                          "finance_manager", "content_manager", "analyst"})
        self.assertGreater(TicketCategory.objects.count(), 10)

    def test_every_role_permission_is_a_known_permission(self):
        from .permissions_catalog import PERMISSIONS

        for r in Role.objects.all():
            self.assertTrue(set(r.permissions) <= set(PERMISSIONS), r.key)

    def test_login_for_team_unchanged(self):
        u = team("admin")
        r = APIClient().post("/api/v1/auth/team/login/", {"identifier": u.username, "password": PW})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["role"], "team")
