from rest_framework import serializers


class TransferConsentSerializer(serializers.Serializer):
    accepted = serializers.BooleanField(required=True)
    snapshot_sha256 = serializers.RegexField(r"^[a-f0-9]{64}$")

    def validate_accepted(self, value):
        if value is not True:
            raise serializers.ValidationError("Explicit consent is required for each AI request.")
        return value


class InvestigationCreateSerializer(serializers.Serializer):
    snapshot_id = serializers.UUIDField()
    provider = serializers.CharField(max_length=32)
    model_id = serializers.CharField(max_length=160)
    temperature = serializers.FloatField(min_value=0, max_value=1)
    max_output_tokens = serializers.ChoiceField(choices=[512, 1024, 2048, 4096])
    prompt_profile = serializers.ChoiceField(
        choices=["zero_shot", "few_shot", "decomposed_verified"]
    )
    transmission_consent = TransferConsentSerializer(required=True)


class ProviderOptionSerializer(serializers.Serializer):
    name = serializers.CharField()
    models = serializers.ListField(child=serializers.CharField())
    available = serializers.BooleanField()


class FactSerializer(serializers.Serializer):
    statement = serializers.CharField()
    event_ids = serializers.ListField(child=serializers.UUIDField())


class HypothesisSerializer(serializers.Serializer):
    title = serializers.CharField()
    status = serializers.CharField()
    supporting_event_ids = serializers.ListField(child=serializers.UUIDField())
    contradicting_event_ids = serializers.ListField(child=serializers.UUIDField())
    alternative_explanations = serializers.ListField(child=serializers.CharField())
    further_checks = serializers.ListField(child=serializers.CharField())


class SuggestedActionSerializer(serializers.Serializer):
    action = serializers.CharField()
    safety = serializers.CharField()
    rationale_event_ids = serializers.ListField(child=serializers.UUIDField())


class ReportBodySerializer(serializers.Serializer):
    schema_version = serializers.CharField()
    incident_summary = serializers.CharField()
    observed_facts = FactSerializer(many=True)
    hypotheses = HypothesisSerializer(many=True)
    suggested_actions = SuggestedActionSerializer(many=True)
    limitations = serializers.ListField(child=serializers.CharField())


class InvestigationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    snapshot_id = serializers.UUIDField()
    snapshot_sha256 = serializers.CharField()
    provider = serializers.CharField()
    model_id = serializers.CharField()
    temperature = serializers.FloatField()
    max_output_tokens = serializers.IntegerField()
    prompt_profile = serializers.CharField()
    prompt_version = serializers.CharField()
    response_schema_version = serializers.CharField()
    input_tokens = serializers.IntegerField(allow_null=True)
    output_tokens = serializers.IntegerField(allow_null=True)
    consent_accepted_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class InvestigationDetailSerializer(InvestigationSummarySerializer):
    report = ReportBodySerializer()
