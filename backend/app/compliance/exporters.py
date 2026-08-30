"""Safe Exporters for Compliance Reports (JSON and CSV) with secret redaction."""

import csv
import io
import json
import re
from typing import Any

from app.compliance.schemas import ComplianceReport

SENSITIVE_KEY_PATTERNS = [
    r"api[_-]?key",
    r"secret",
    r"password",
    r"token",
    r"private[_-]?key",
    r"authorization",
]


def redact_secrets(data: Any) -> Any:
    """Recursively scrub sensitive keys and credential patterns."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if any(re.search(p, str(k), re.IGNORECASE) for p in SENSITIVE_KEY_PATTERNS):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = redact_secrets(v)
        return cleaned
    if isinstance(data, list):
        return [redact_secrets(item) for item in data]
    if isinstance(data, str) and len(data) > 30:
        if any(keyword in data.lower() for keyword in ["bearer ", "secret_key", "password="]):
            return "[REDACTED]"
    return data


class ComplianceExporter:
    """Exports compliance reports to JSON and CSV formats with automated secret scrubbing."""

    @classmethod
    def export_json(cls, report: ComplianceReport) -> str:
        """Export report to formatted JSON string with secret redaction."""
        raw_dict = report.model_dump(mode="json")
        scrubbed = redact_secrets(raw_dict)
        return json.dumps(scrubbed, indent=2, default=str)

    @classmethod
    def export_csv(cls, report: ComplianceReport) -> str:
        """Export report controls to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["Report ID", str(report.report_id)])
        writer.writerow(["Tenant ID", str(report.tenant_id)])
        writer.writerow(["Report Type", report.report_type])
        writer.writerow(["Reporting Period Start", report.reporting_period_start.isoformat()])
        writer.writerow(["Reporting Period End", report.reporting_period_end.isoformat()])
        writer.writerow(["Verification Status", report.verification_status])
        writer.writerow(["Audit Chain Head", report.audit_chain_head])
        writer.writerow(["Report Hash", report.report_hash])
        writer.writerow([])

        # Controls Table
        writer.writerow(["Control ID", "Category", "Name", "Status", "Description"])
        for c in report.controls:
            writer.writerow(
                [
                    c.control_id,
                    c.category,
                    c.name,
                    c.status.value,
                    c.description,
                ]
            )

        return output.getvalue()
