"""The first safe IMD adapter step: prove configuration without provider I/O.

IMD's official API page directs consumers to its API documentation and IP
whitelisting, and asks clients to cache responses and attribute IMD.  This
module intentionally stops before requesting a weather product.  It integrates
with the existing source-adapter port by recording an ``unavailable`` dry run.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import urlparse

from ffl.services.sources import AdapterRefreshResult, SourceUnavailable


IMD_API_DOCUMENTATION_URL = "https://mausam.imd.gov.in/responsive/apis.php"
_IMD_API_HOST = "api.imd.gov.in"
_IMD_SOURCE_KEY = "imd-weather"
_IMD_SOURCE_TYPE = "imd_access_dry_run"


@dataclass(frozen=True)
class IMDAccessReview:
    """The non-secret evidence that permits a future, separately built worker."""

    endpoint: str
    product_identifier: str
    egress_identity: str
    review_reference: str
    cache_ttl_seconds: int

    def validate(self) -> None:
        parsed = urlparse(self.endpoint)
        if (
            parsed.scheme != "https"
            or parsed.hostname != _IMD_API_HOST
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("IMD dry run requires an HTTPS api.imd.gov.in endpoint without credentials or query")
        for value, label in (
            (self.product_identifier, "product identifier"),
            (self.egress_identity, "egress identity"),
            (self.review_reference, "review reference"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("IMD access review requires a {0}".format(label))
        if (
            not isinstance(self.cache_ttl_seconds, int)
            or isinstance(self.cache_ttl_seconds, bool)
            or self.cache_ttl_seconds < 60
            or self.cache_ttl_seconds > 3600
        ):
            raise ValueError("IMD access review cache TTL must be between 60 and 3600 seconds")

    def source_registration_spec(self) -> Dict[str, object]:
        """Non-secret values for the canonical source registry; remains disabled."""
        self.validate()
        return {
            "source_key": _IMD_SOURCE_KEY,
            "display_name": "India Meteorological Department weather and warnings",
            "source_type": _IMD_SOURCE_TYPE,
            "purpose": "regional weather context",
            "authority_level": "official",
            "permitted_data_classes": ["forecast", "warning", "observation"],
            "schema_version": "imd-access-review-v1",
            "mapping_version": "imd-dry-run-v1",
            "default_coverage": {"country": "IN"},
            "endpoint": self.endpoint,
            "freshness_target_hours": None,
            "license_notes": (
                "Official IMD API access review {review}; product {product}; approved egress {egress}; "
                "cache TTL {ttl}s; retain IMD attribution. No provider request is enabled by this dry-run source."
            ).format(
                review=self.review_reference.strip(),
                product=self.product_identifier.strip(),
                egress=self.egress_identity.strip(),
                ttl=self.cache_ttl_seconds,
            ),
            "enabled": False,
        }


class IMDDryRunAdapter:
    """A SourceAdapter that validates the access plan and deliberately makes no call."""

    source_type = _IMD_SOURCE_TYPE
    requires_endpoint = True
    requires_credentials = False

    def __init__(self, review: IMDAccessReview):
        review.validate()
        self._review = review

    def fetch(self, source, credential: Optional[str], now: datetime) -> AdapterRefreshResult:
        """Never send an IMD request; source health must show the deliberate block."""
        del now
        if source.source_key != _IMD_SOURCE_KEY or source.authority_level != "official":
            raise SourceUnavailable("imd_source_mismatch")
        if source.endpoint != self._review.endpoint:
            raise SourceUnavailable("imd_endpoint_mismatch")
        if credential is not None:
            raise SourceUnavailable("imd_credential_not_supported")
        self._review.validate()
        raise SourceUnavailable("imd_network_not_enabled")
