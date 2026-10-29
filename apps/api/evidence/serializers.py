from rest_framework import serializers

from evidence.selection import MAX_EVENTS, PRIVACY_POLICY_VERSION


class EvidenceSelectionSerializer(serializers.Serializer):
    event_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False, min_length=1, max_length=MAX_EVENTS
    )

    def validate_event_ids(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Duplicate event IDs are not allowed.")
        return values


class PrivacyConsentSerializer(serializers.Serializer):
    accepted = serializers.BooleanField(required=True)
    policy_version = serializers.ChoiceField(choices=[PRIVACY_POLICY_VERSION])

    def validate_accepted(self, value):
        if value is not True:
            raise serializers.ValidationError("Explicit consent is required.")
        return value


class EvidenceSnapshotCreateSerializer(EvidenceSelectionSerializer):
    expected_sha256 = serializers.RegexField(regex=r"^[a-f0-9]{64}$")
    privacy_consent = PrivacyConsentSerializer(required=True)


class EvidenceEntrySerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    source_id = serializers.UUIDField()
    source_sha256 = serializers.CharField()
    source_name = serializers.CharField()
    source_lines = serializers.ListField(child=serializers.IntegerField())
    occurred_at = serializers.DateTimeField(allow_null=True)
    timestamp_quality = serializers.CharField()
    severity = serializers.CharField(allow_blank=True)
    service = serializers.CharField(allow_blank=True)
    message = serializers.CharField(allow_blank=True)


class EvidencePreviewSerializer(serializers.Serializer):
    sha256 = serializers.CharField()
    event_count = serializers.IntegerField()
    characters = serializers.IntegerField()
    payload_bytes = serializers.IntegerField()
    selection_version = serializers.CharField()
    privacy_policy_version = serializers.CharField()
    entries = EvidenceEntrySerializer(many=True)
    transmitted = serializers.BooleanField()


class EvidenceSnapshotSerializer(EvidencePreviewSerializer):
    id = serializers.UUIDField()
    consent_accepted_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class EvidenceSnapshotSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    sha256 = serializers.CharField()
    event_count = serializers.IntegerField()
    characters = serializers.IntegerField()
    payload_bytes = serializers.IntegerField()
    selection_version = serializers.CharField()
    privacy_policy_version = serializers.CharField()
    consent_accepted_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
    transmitted = serializers.BooleanField()
