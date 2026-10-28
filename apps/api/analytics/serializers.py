from rest_framework import serializers


class CountBySeveritySerializer(serializers.Serializer):
    severity = serializers.CharField()
    count = serializers.IntegerField()


class CountByServiceSerializer(serializers.Serializer):
    service = serializers.CharField()
    count = serializers.IntegerField()


class FingerprintGroupSerializer(serializers.Serializer):
    fingerprint = serializers.CharField()
    count = serializers.IntegerField()
    event_ids = serializers.ListField(child=serializers.UUIDField())


class TimelineBucketSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    total = serializers.IntegerField()
    errors = serializers.IntegerField()


class AnomalySerializer(serializers.Serializer):
    status = serializers.CharField()
    reason = serializers.CharField(required=False)
    method = serializers.CharField(required=False)
    threshold = serializers.FloatField(required=False)
    buckets = serializers.ListField(child=serializers.DateTimeField())


class AnalysisSerializer(serializers.Serializer):
    algorithm_version = serializers.CharField()
    input_sha256 = serializers.CharField()
    bucket_minutes = serializers.IntegerField()
    total_events = serializers.IntegerField()
    error_events = serializers.IntegerField()
    missing_event_time = serializers.IntegerField()
    severity_counts = CountBySeveritySerializer(many=True)
    service_counts = CountByServiceSerializer(many=True)
    fingerprint_groups = FingerprintGroupSerializer(many=True)
    timeline = TimelineBucketSerializer(many=True)
    anomaly = AnomalySerializer()
    limitations = serializers.ListField(child=serializers.CharField())
