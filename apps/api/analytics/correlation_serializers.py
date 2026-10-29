from rest_framework import serializers


class RelationshipEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_id = serializers.UUIDField()
    line_start = serializers.IntegerField()
    line_end = serializers.IntegerField()
    occurred_at = serializers.DateTimeField(allow_null=True)
    timestamp_quality = serializers.CharField()
    severity = serializers.CharField()
    service = serializers.CharField(allow_blank=True)
    message = serializers.CharField(allow_blank=True)


class RelationshipGroupSerializer(serializers.Serializer):
    key = serializers.CharField()
    kind = serializers.ChoiceField(choices=["trace", "request"])
    event_count = serializers.IntegerField()
    service_count = serializers.IntegerField()
    services = serializers.ListField(child=serializers.CharField())
    first_at = serializers.DateTimeField(allow_null=True)
    last_at = serializers.DateTimeField(allow_null=True)
    unknown_time = serializers.IntegerField()
    truncated = serializers.BooleanField()
    events = RelationshipEventSerializer(many=True)


class ServiceTransitionSerializer(serializers.Serializer):
    from_service = serializers.CharField()
    to_service = serializers.CharField()
    count = serializers.IntegerField()
    event_ids = serializers.ListField(child=serializers.UUIDField())


class CorrelationSerializer(serializers.Serializer):
    version = serializers.CharField()
    total_events = serializers.IntegerField()
    correlated_groups = serializers.IntegerField()
    unknown_time = serializers.IntegerField()
    groups = RelationshipGroupSerializer(many=True)
    transitions = ServiceTransitionSerializer(many=True)
    timeline = RelationshipEventSerializer(many=True)
    timeline_truncated = serializers.BooleanField()
