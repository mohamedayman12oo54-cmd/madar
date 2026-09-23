from rest_framework.permissions import BasePermission


class IsRole(BasePermission):
    """Factory-style role check: IsRole('teacher') -> permission class
    instance requiring request.user.role == 'teacher' (and authenticated)."""

    def __init__(self, role=None):
        self.role = role

    def __call__(self):
        return self

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == self.role
        )


IsTeacher = IsRole("teacher")
IsStudent = IsRole("student")
IsTeam = IsRole("team")
