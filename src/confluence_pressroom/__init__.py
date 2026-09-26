"""Confluence-side Pressroom integration primitives for the Phase 1 rehearsal."""

from .dependency_pin import DependencyPin, load_dependency_pin
from .html_prepare import PREPARATION_VERSION, PreparedHTML, prepare_rendered_html
from .payload import CandidateArticle, build_publication_payload, payload_sha256
from .staging import PrivateStagingStore, StageLookup, StageReceipt

__all__ = [
    "CandidateArticle",
    "DependencyPin",
    "PREPARATION_VERSION",
    "PreparedHTML",
    "PrivateStagingStore",
    "StageLookup",
    "StageReceipt",
    "build_publication_payload",
    "load_dependency_pin",
    "payload_sha256",
    "prepare_rendered_html",
]
