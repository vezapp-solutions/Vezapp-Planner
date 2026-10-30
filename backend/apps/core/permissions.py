"""Role matrix. Reads and writes are decided separately, per role."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.roles import ADMIN_ROLES, ALL_ROLES, PLANNER_ROLES, Role


class RoleMatrixPermission(BasePermission):
    read_roles = ALL_ROLES
    write_roles = ADMIN_ROLES

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        roles = self.read_roles if request.method in SAFE_METHODS else self.write_roles
        return user.role in roles


class AdminWrite(RoleMatrixPermission):
    """Everyone reads; Vezapp and Company Admins write (masters, settings)."""


class PlannerWrite(RoleMatrixPermission):
    """Everyone reads; Planners and admins write (schedules, plans, what-if)."""

    write_roles = PLANNER_ROLES


class AdminOnly(RoleMatrixPermission):
    """Only Vezapp and Company Admins, for reads as well as writes (user management)."""

    read_roles = ADMIN_ROLES


class VezappAdminOnly(RoleMatrixPermission):
    read_roles = frozenset({Role.VEZAPP_ADMIN})
    write_roles = frozenset({Role.VEZAPP_ADMIN})


class PlannerOnly(RoleMatrixPermission):
    """Planners and admins only, for reads as well as writes (uploads and their history)."""

    read_roles = PLANNER_ROLES
    write_roles = PLANNER_ROLES
