import uuid

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """
    Manager for the custom User model.

    Madar users log in with different identifiers depending on role
    (teacher: phone or email, student: phone, team: email), so `username`
    is never typed by a human — it's an internal-only unique slug we
    auto-generate so the model can still build on Django's well-tested
    AbstractUser machinery (is_staff, is_superuser, permissions, admin…).
    """

    use_in_migrations = True

    def _generate_username(self):
        return f"u_{uuid.uuid4().hex[:20]}"

    def _create_user(self, password=None, **extra_fields):
        extra_fields.setdefault("username", self._generate_username())
        email = extra_fields.get("email")
        if email:
            extra_fields["email"] = self.normalize_email(email)
        user = self.model(**extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(password=password, **extra_fields)

    def create_superuser(self, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_verified", True)
        extra_fields.setdefault("role", "team")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(password=password, **extra_fields)
