from rest_framework import serializers

from ingestion.models import IngestionJob, LogSource


class UploadRequestSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(), allow_empty=False, min_length=1, max_length=5
    )


class UploadAcceptedSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=IngestionJob.State.choices)
    source_ids = serializers.ListField(child=serializers.UUIDField())


class SourceSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    filename = serializers.CharField()
    sha256 = serializers.CharField()
    byte_size = serializers.IntegerField()
    state = serializers.ChoiceField(choices=LogSource.State.choices)
    accepted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    warnings = serializers.JSONField()


class IngestionJobStatusSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=IngestionJob.State.choices)
    accepted = serializers.IntegerField()
    rejected = serializers.IntegerField()
    error_code = serializers.CharField(allow_blank=True)


class EventRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_id = serializers.UUIDField()
    line_start = serializers.IntegerField()
    line_end = serializers.IntegerField()
    occurred_at = serializers.DateTimeField(allow_null=True)
    observed_at = serializers.DateTimeField()
    timestamp_quality = serializers.CharField()
    severity = serializers.CharField(allow_blank=True)
    service = serializers.CharField(allow_blank=True)
    message = serializers.CharField()
    fingerprint = serializers.CharField()


class PaginatedEventsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = EventRecordSerializer(many=True)
