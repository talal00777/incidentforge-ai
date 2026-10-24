"""Assign server-generated correlation identifiers to HTTP requests."""

from collections.abc import Callable
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

from core.logging import request_id


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        correlation_id = str(uuid4())
        request.correlation_id = correlation_id
        token = request_id.set(correlation_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = correlation_id
            return response
        finally:
            request_id.reset(token)
