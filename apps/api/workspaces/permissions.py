"""Workspace-aware RBAC and incident access helpers."""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

from incidents.models import Incident
from workspaces.models import Workspace, WorkspaceMembership

WRITE_ROLES = {WorkspaceMembership.Role.OWNER, WorkspaceMembership.Role.RESPONDER}


def accessible_incidents_queryset(user):
    """Return all non-deleted incidents owned by user or in a workspace they belong to."""
    return (
        Incident.objects.filter(deleted_at__isnull=True)
        .filter(Q(owner=user) | Q(workspace__memberships__user=user))
        .distinct()
    )


def user_role_for_workspace(user, workspace: Workspace) -> str | None:
    membership = (
        WorkspaceMembership.objects.filter(workspace=workspace, user=user)
        .values_list("role", flat=True)
        .first()
    )
    return membership


def can_manage_workspace(user, workspace: Workspace) -> bool:
    return user_role_for_workspace(user, workspace) == WorkspaceMembership.Role.OWNER


def user_role_for_incident(user, incident: Incident) -> str | None:
    if incident.owner_id == user.id:
        return WorkspaceMembership.Role.OWNER
    if incident.workspace_id:
        return (
            WorkspaceMembership.objects.filter(workspace_id=incident.workspace_id, user=user)
            .values_list("role", flat=True)
            .first()
        )
    return None


def can_edit_incident(user, incident: Incident) -> bool:
    role = user_role_for_incident(user, incident)
    return role in WRITE_ROLES


def can_delete_incident(user, incident: Incident) -> bool:
    role = user_role_for_incident(user, incident)
    return role == WorkspaceMembership.Role.OWNER


def get_accessible_incident_or_404(user, incident_id, *, require_write: bool = False) -> Incident:
    incident = get_object_or_404(accessible_incidents_queryset(user), pk=incident_id)
    if require_write and not can_edit_incident(user, incident):
        raise PermissionDenied("Your workspace role is read-only for this incident.")
    return incident
