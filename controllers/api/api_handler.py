import hashlib
import json
import time
import uuid

from odoo import fields
from odoo.http import Response, request


class ApiHandler:
    def handle(self, endpoint, service_model, service_method):
        started = time.time()
        request_id = str(uuid.uuid4())
        requested_at = fields.Datetime.now()
        raw_payload = request.httprequest.get_data(cache=True, as_text=True) or "{}"
        payload_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        payload = {}
        result = False

        try:
            payload = json.loads(raw_payload)
            if not isinstance(payload, dict):
                result = self._response_service().error(
                    "invalid_payload",
                    "JSON payload must be an object.",
                    400,
                )
            else:
                service = request.env[service_model].sudo()
                result = getattr(service, service_method)(payload)
        except json.JSONDecodeError:
            result = self._response_service().error(
                "invalid_json",
                "Invalid JSON payload.",
                400,
            )
        except Exception as error:  # pragma: no cover - defensive API boundary
            result = self._response_service().error("internal_error", str(error), 500)

        finished_at = fields.Datetime.now()
        duration_ms = int((time.time() - started) * 1000)
        body = self._response_service().body(request_id, result)
        self._create_log(
            request_id,
            endpoint,
            requested_at,
            finished_at,
            duration_ms,
            payload,
            payload_hash,
            result,
            body,
        )

        return Response(
            json.dumps(body),
            status=result.get("http_status", 500),
            content_type="application/json; charset=utf-8",
        )

    def _response_service(self):
        return request.env["wt.api.response.service"].sudo()

    def _create_log(
        self,
        request_id,
        endpoint,
        requested_at,
        finished_at,
        duration_ms,
        payload,
        payload_hash,
        result,
        response_body,
    ):
        device = result.get("device")
        error = result.get("error") or {}
        request.env["wt.api.request.log"].sudo().create(
            {
                "request_id": request_id,
                "endpoint": endpoint,
                "method": request.httprequest.method,
                "status": "success" if result.get("ok") else "failed",
                "http_status": result.get("http_status"),
                "error_code": error.get("code"),
                "error_message": error.get("message"),
                "device_id": payload.get("device_id") if isinstance(payload, dict) else False,
                "device_record_id": device.id if device else False,
                "company_id": device.company_id.id if device else False,
                "employee_id": device.employee_id.id if device else False,
                "role": device.role if device else False,
                "request_ip": request.httprequest.remote_addr,
                "user_agent": request.httprequest.headers.get("User-Agent"),
                "duration_ms": duration_ms,
                "requested_at": requested_at,
                "finished_at": finished_at,
                "payload_hash": payload_hash,
                "payload": json.dumps(self._sanitize_payload(payload)),
                "response": json.dumps(self._sanitize_payload(response_body)),
            }
        )

    def _sanitize_payload(self, value):
        if isinstance(value, dict):
            sanitized = {}
            for key, item in value.items():
                if key.lower() in {"token", "password", "secret", "api_key"}:
                    sanitized[key] = "***"
                else:
                    sanitized[key] = self._sanitize_payload(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_payload(item) for item in value]
        return value
