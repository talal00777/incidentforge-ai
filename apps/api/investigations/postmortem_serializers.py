"""Explicit, versioned postmortem API schemas."""

from rest_framework import serializers


class PostmortemCreateSerializer(serializers.Serializer):
    investigation_id = serializers.UUIDField()
    expected_review_revision = serializers.IntegerField(min_value=1)


class PostmortemSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    investigation_id = serializers.UUIDField()
    review_revision_number = serializers.IntegerField(source="review_revision.number")
    content_sha256 = serializers.CharField()
    created_by_id = serializers.CharField()
    created_at = serializers.DateTimeField()


class PostmortemDetailSerializer(PostmortemSummarySerializer):
    content = serializers.JSONField()
