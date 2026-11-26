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
    trace_id = serializers.CharField(allow_blank=True)
    message = serializers.CharField()
    fingerprint = serializers.CharField()


class PaginatedEventsSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = EventRecordSerializer(many=True)


class EventContextDetailSerializer(EventRecordSerializer):
    source_filename = serializers.CharField()
    source_sha256 = serializers.CharField()
    parser_version = serializers.CharField()


class EventContextResponseSerializer(serializers.Serializer):
    event = EventContextDetailSerializer()
    before = EventRecordSerializer(many=True)
    after = EventRecordSerializer(many=True)
    window = serializers.IntegerField()
    related_trace_count = serializers.IntegerField()
    same_fingerprint_count = serializers.IntegerField()


class FacetCountSerializer(serializers.Serializer):
    value = serializers.CharField()
    count = serializers.IntegerField()


class SourceFacetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    filename = serializers.CharField()
    count = serializers.IntegerField()


class FingerprintFacetSerializer(serializers.Serializer):
    fingerprint = serializers.CharField()
    count = serializers.IntegerField()
    sample_message = serializers.CharField()
    severity = serializers.CharField(allow_blank=True)
    service = serializers.CharField(allow_blank=True)


class EventFacetsResponseSerializer(serializers.Serializer):
    total_events = serializers.IntegerField()
    severities = FacetCountSerializer(many=True)
    services = FacetCountSerializer(many=True)
    sources = SourceFacetSerializer(many=True)
    top_fingerprints = FingerprintFacetSerializer(many=True)
