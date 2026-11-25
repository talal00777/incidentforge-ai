import secrets

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from workspaces.models import AlertWebhook, WebhookDelivery, Workspace, WorkspaceMembership
from workspaces.permissions import can_manage_workspace, user_role_for_workspace
from workspaces.serializers import (
    AlertWebhookCreateSerializer,
    AlertWebhookResponseSerializer,
    AlertWebhookUpdateSerializer,
    WebhookDeliverySerializer,
    WebhookTestRequestSerializer,
    WorkspaceCreateUpdateSerializer,
    WorkspaceMemberAddSerializer,
    WorkspaceMemberRoleUpdateSerializer,
    WorkspaceMemberSerializer,
    WorkspaceSummarySerializer,
    serialize_delivery,
    serialize_webhook,
    serialize_workspace,
)
from workspaces.webhooks import deliver_webhook

User = get_user_model()


def _unique_slug(base_name: str, explicit_slug: str = "") -> str:
    candidate = slugify(explicit_slug or base_name)[:72] or f"workspace-{secrets.token_hex(3)}"
    if len(candidate) < 3:
        candidate = f"{candidate}-{secrets.token_hex(2)}"
    if not Workspace.objects.filter(slug=candidate).exists():
        return candidate
    for _ in range(10):
        suffixed = f"{candidate[:68]}-{secrets.token_hex(3)}"
        if not Workspace.objects.filter(slug=suffixed).exists():
            return suffixed
    return f"ws-{secrets.token_hex(6)}"


class WorkspaceBaseView(APIView):
    permission_classes = [IsAuthenticated]

    def get_workspace(self, workspace_id, *, require_owner: bool = False) -> tuple[Workspace, str]:
        workspace = get_object_or_404(
            Workspace.objects.filter(memberships__user=self.request.user).distinct(),
            pk=workspace_id,
        )
        role = user_role_for_workspace(self.request.user, workspace)
        if not role:
            raise PermissionDenied("You do not belong to this workspace.")
        if require_owner and not can_manage_workspace(self.request.user, workspace):
            raise PermissionDenied("Only workspace owners can perform this action.")
        return workspace, role


class WorkspaceListCreateView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=None,
        responses={200: WorkspaceSummarySerializer(many=True)},
    )
    def get(self, request):
        memberships = {
            m.workspace_id: m.role for m in WorkspaceMembership.objects.filter(user=request.user)
        }
        workspaces = (
            Workspace.objects.filter(id__in=memberships.keys())
            .annotate(
                member_count=Count("memberships", distinct=True),
                incident_count=Count(
                    "incidents", filter=Q(incidents__deleted_at__isnull=True), distinct=True
                ),
                webhook_count=Count("webhooks", distinct=True),
            )
            .order_by("name", "id")
        )
        return Response(
            [
                serialize_workspace(
                    ws,
                    memberships[ws.id],
                    {
                        "member_count": ws.member_count,
                        "incident_count": ws.incident_count,
                        "webhook_count": ws.webhook_count,
                    },
                )
                for ws in workspaces
            ]
        )

    @extend_schema(
        tags=["workspaces"],
        request=WorkspaceCreateUpdateSerializer,
        responses={201: WorkspaceSummarySerializer},
    )
    @transaction.atomic
    def post(self, request):
        serializer = WorkspaceCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        explicit_slug = data.get("slug", "")
        if explicit_slug and Workspace.objects.filter(slug=explicit_slug).exists():
            raise ValidationError({"slug": "A workspace with this slug already exists."})
        workspace = Workspace.objects.create(
            name=data["name"],
            slug=_unique_slug(data["name"], explicit_slug),
            description=data.get("description", "").strip(),
            created_by=request.user,
        )
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=request.user,
            role=WorkspaceMembership.Role.OWNER,
        )
        return Response(
            serialize_workspace(
                workspace,
                WorkspaceMembership.Role.OWNER,
                {"member_count": 1, "incident_count": 0, "webhook_count": 0},
            ),
            status=status.HTTP_201_CREATED,
        )


class WorkspaceDetailView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=None,
        responses={200: WorkspaceSummarySerializer},
    )
    def get(self, request, workspace_id):
        workspace, role = self.get_workspace(workspace_id)
        counts = {
            "member_count": workspace.memberships.count(),
            "incident_count": workspace.incidents.filter(deleted_at__isnull=True).count(),
            "webhook_count": workspace.webhooks.count(),
        }
        return Response(serialize_workspace(workspace, role, counts))

    @extend_schema(
        tags=["workspaces"],
        request=WorkspaceCreateUpdateSerializer,
        responses={200: WorkspaceSummarySerializer},
    )
    def patch(self, request, workspace_id):
        workspace, role = self.get_workspace(workspace_id, require_owner=True)
        serializer = WorkspaceCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "name" in data:
            workspace.name = data["name"]
        if "description" in data:
            workspace.description = data["description"].strip()
        if "slug" in data and data["slug"] and data["slug"] != workspace.slug:
            if Workspace.objects.filter(slug=data["slug"]).exclude(pk=workspace.pk).exists():
                raise ValidationError({"slug": "A workspace with this slug already exists."})
            workspace.slug = data["slug"]
        workspace.save()
        counts = {
            "member_count": workspace.memberships.count(),
            "incident_count": workspace.incidents.filter(deleted_at__isnull=True).count(),
            "webhook_count": workspace.webhooks.count(),
        }
        return Response(serialize_workspace(workspace, role, counts))

    @extend_schema(tags=["workspaces"], request=None, responses={204: None})
    def delete(self, request, workspace_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        workspace.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceMembersView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=None,
        responses={200: WorkspaceMemberSerializer(many=True)},
    )
    def get(self, request, workspace_id):
        workspace, _ = self.get_workspace(workspace_id)
        rows = workspace.memberships.select_related("user").order_by("created_at")
        return Response(
            [
                {
                    "id": str(row.id),
                    "user_id": str(row.user_id),
                    "email": row.user.email,
                    "first_name": row.user.first_name,
                    "last_name": row.user.last_name,
                    "role": row.role,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        )

    @extend_schema(
        tags=["workspaces"],
        request=WorkspaceMemberAddSerializer,
        responses={201: WorkspaceMemberSerializer},
    )
    @transaction.atomic
    def post(self, request, workspace_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        serializer = WorkspaceMemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_user = User.objects.get(
            email__iexact=serializer.validated_data["email"], is_active=True
        )
        if WorkspaceMembership.objects.filter(workspace=workspace, user=target_user).exists():
            raise ValidationError({"email": "This user is already a member of the workspace."})
        membership = WorkspaceMembership.objects.create(
            workspace=workspace,
            user=target_user,
            role=serializer.validated_data["role"],
        )
        return Response(
            {
                "id": str(membership.id),
                "user_id": str(target_user.id),
                "email": target_user.email,
                "first_name": target_user.first_name,
                "last_name": target_user.last_name,
                "role": membership.role,
                "created_at": membership.created_at,
            },
            status=status.HTTP_201_CREATED,
        )


class WorkspaceMemberDetailView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=WorkspaceMemberRoleUpdateSerializer,
        responses={200: WorkspaceMemberSerializer},
    )
    @transaction.atomic
    def patch(self, request, workspace_id, membership_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        membership = get_object_or_404(
            WorkspaceMembership.objects.select_related("user"),
            pk=membership_id,
            workspace=workspace,
        )
        serializer = WorkspaceMemberRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        next_role = serializer.validated_data["role"]
        if (
            membership.role == WorkspaceMembership.Role.OWNER
            and next_role != WorkspaceMembership.Role.OWNER
            and workspace.memberships.filter(role=WorkspaceMembership.Role.OWNER).count() <= 1
        ):
            raise ValidationError({"role": "Workspace must retain at least one owner."})
        membership.role = next_role
        membership.save(update_fields=["role"])
        return Response(
            {
                "id": str(membership.id),
                "user_id": str(membership.user_id),
                "email": membership.user.email,
                "first_name": membership.user.first_name,
                "last_name": membership.user.last_name,
                "role": membership.role,
                "created_at": membership.created_at,
            }
        )

    @extend_schema(tags=["workspaces"], request=None, responses={204: None})
    @transaction.atomic
    def delete(self, request, workspace_id, membership_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        membership = get_object_or_404(WorkspaceMembership, pk=membership_id, workspace=workspace)
        if (
            membership.role == WorkspaceMembership.Role.OWNER
            and workspace.memberships.filter(role=WorkspaceMembership.Role.OWNER).count() <= 1
        ):
            raise ValidationError({"detail": "Cannot remove the last workspace owner."})
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceWebhooksView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=None,
        responses={200: AlertWebhookResponseSerializer(many=True)},
    )
    def get(self, request, workspace_id):
        workspace, _ = self.get_workspace(workspace_id)
        hooks = workspace.webhooks.order_by("-created_at")
        return Response([serialize_webhook(item) for item in hooks])

    @extend_schema(
        tags=["workspaces"],
        request=AlertWebhookCreateSerializer,
        responses={201: AlertWebhookResponseSerializer},
    )
    def post(self, request, workspace_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        serializer = AlertWebhookCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        webhook = AlertWebhook.objects.create(
            workspace=workspace,
            name=data["name"].strip(),
            provider=data["provider"],
            target_url=data["target_url"],
            event_types=data["event_types"],
            min_severity=data["min_severity"],
            is_active=data["is_active"],
            created_by=request.user,
        )
        return Response(
            serialize_webhook(webhook, reveal_secret=True), status=status.HTTP_201_CREATED
        )


class WorkspaceWebhookDetailView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=AlertWebhookUpdateSerializer,
        responses={200: AlertWebhookResponseSerializer},
    )
    def patch(self, request, workspace_id, webhook_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        webhook = get_object_or_404(AlertWebhook, pk=webhook_id, workspace=workspace)
        serializer = AlertWebhookUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(webhook, field, value.strip() if isinstance(value, str) else value)
        webhook.save()
        return Response(serialize_webhook(webhook))

    @extend_schema(tags=["workspaces"], request=None, responses={204: None})
    def delete(self, request, workspace_id, webhook_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        webhook = get_object_or_404(AlertWebhook, pk=webhook_id, workspace=workspace)
        webhook.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceWebhookTestView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=WebhookTestRequestSerializer,
        responses={200: WebhookDeliverySerializer},
    )
    def post(self, request, workspace_id, webhook_id):
        workspace, _ = self.get_workspace(workspace_id, require_owner=True)
        webhook = get_object_or_404(
            AlertWebhook.objects.select_related("workspace"), pk=webhook_id, workspace=workspace
        )
        serializer = WebhookTestRequestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        delivery = deliver_webhook(
            webhook,
            "webhook.test",
            {
                "id": "",
                "title": f"Test alert from {workspace.name}",
                "severity": "high",
                "status": "investigating",
                "service_name": "checkout-api",
                "environment": "production",
            },
            dry_run=serializer.validated_data["dry_run"],
        )
        return Response(serialize_delivery(delivery))


class WorkspaceWebhookDeliveriesView(WorkspaceBaseView):
    @extend_schema(
        tags=["workspaces"],
        request=None,
        responses={200: WebhookDeliverySerializer(many=True)},
    )
    def get(self, request, workspace_id, webhook_id):
        workspace, _ = self.get_workspace(workspace_id)
        webhook = get_object_or_404(AlertWebhook, pk=webhook_id, workspace=workspace)
        rows = WebhookDelivery.objects.filter(webhook=webhook).order_by("-created_at")[:30]
        return Response([serialize_delivery(item) for item in rows])
