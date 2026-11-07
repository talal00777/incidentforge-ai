"""Human review DTOs; never edits the original AI investigation body."""

from rest_framework import serializers


class ReviewHypothesisSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0)
    decision = serializers.ChoiceField(
        choices=["needs_review", "reviewed", "accepted_as_working_hypothesis", "rejected"]
    )
    note = serializers.CharField(max_length=2000, allow_blank=True, trim_whitespace=True)


class ReviewUpdateSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(choices=["draft", "reviewed"])
    impact_notes = serializers.CharField(max_length=4000, allow_blank=True, trim_whitespace=True)
    remediation_notes = serializers.CharField(
        max_length=4000, allow_blank=True, trim_whitespace=True
    )
    hypotheses = ReviewHypothesisSerializer(many=True, allow_empty=True)

    def validate(self, attrs):
        expected_count = self.context["hypothesis_count"]
        decisions = attrs["hypotheses"]
        if len(decisions) != expected_count or any(
            item["index"] != i for i, item in enumerate(decisions)
        ):
            raise serializers.ValidationError(
                {"hypotheses": "Decisions must cover each hypothesis in report order."}
            )
        if attrs["status"] == "reviewed" and any(
            item["decision"] == "needs_review" for item in decisions
        ):
            raise serializers.ValidationError(
                {"status": "Resolve pending hypothesis reviews before completing."}
            )
        return attrs


class ReviewResponseSerializer(serializers.Serializer):
    revision = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["draft", "reviewed"])
    impact_notes = serializers.CharField(allow_blank=True)
    remediation_notes = serializers.CharField(allow_blank=True)
    hypotheses = ReviewHypothesisSerializer(many=True)
    updated_at = serializers.DateTimeField(allow_null=True)
