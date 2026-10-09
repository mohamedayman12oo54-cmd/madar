"""
Madar-owned seam for video storage/processing (ADR-009: Madar owns the
interface, the vendor sits behind it).

Two implementations are meaningful:

* `LocalStorageProvider` (default, implemented): Madar accepts the bytes
  itself and serves them through the authorised streaming view. Honest for the
  current scale, with no external account required.

* A hosted provider (Cloudflare Stream, Mux, S3 + MediaConvert, ...): the
  teacher's browser uploads **straight to the provider** using a credential
  this backend mints, so video bytes never pass through Django twice;
  transcoding to multiple bitrates, HLS packaging and CDN delivery happen
  there, and completion arrives by webhook.

The interface below is deliberately shaped for the second case — `direct_upload`
returns an endpoint the CLIENT uses — so adopting a provider is a new class
here, not a change to the domain, the API, or the player.

Nothing in this module fabricates provider behaviour: anything that genuinely
needs an account raises `ProviderUnavailable` rather than pretending.
"""
from dataclasses import dataclass, field

from django.conf import settings


class ProviderUnavailable(RuntimeError):
    """Raised when a capability needs infrastructure that is not configured."""


@dataclass
class DirectUpload:
    """What the client needs to send bytes somewhere that is not Django."""
    upload_url: str
    method: str = "PATCH"
    headers: dict = field(default_factory=dict)
    # Provider-side handle, stored so webhooks can be correlated to our row.
    provider_ref: str = ""
    resumable: bool = True


class VideoProvider:
    name = "base"
    # Does the provider transcode to adaptive bitrates and serve HLS?
    supports_transcoding = False

    def direct_upload(self, session) -> DirectUpload:  # pragma: no cover - interface
        raise NotImplementedError

    def playback(self, item):  # pragma: no cover - interface
        raise NotImplementedError

    def delete(self, item):  # pragma: no cover - interface
        raise NotImplementedError

    def verify_webhook(self, request) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class LocalStorageProvider(VideoProvider):
    """Madar stores and serves the file itself.

    Uploads are still resumable (see `content.upload_views`) — the resumable
    protocol is ours, not the provider's — and playback still goes through the
    signed-ticket streaming view. What this provider does NOT do is transcode:
    there is one rendition, the one the teacher uploaded.
    """

    name = "local"
    supports_transcoding = False

    def direct_upload(self, session) -> DirectUpload:
        # "Direct" here still means "not buffered through a second hop": the
        # client PATCHes chunks straight onto the upload session.
        return DirectUpload(
            upload_url=f"/api/v1/content/uploads/{session.id}/",
            method="PATCH",
            headers={"Upload-Offset": str(session.offset)},
            provider_ref=str(session.id),
            resumable=True,
        )

    def playback(self, item):
        if not item.video_file:
            raise ProviderUnavailable("لا يوجد ملف مرفوع.")
        # The ticket is minted by content.streaming; nothing public is returned.
        return {"kind": "madar", "item_id": item.id}

    def delete(self, item):
        if item.video_file:
            item.video_file.delete(save=False)

    def verify_webhook(self, request) -> bool:
        # Nothing external calls us in local mode.
        return False


_PROVIDERS = {LocalStorageProvider.name: LocalStorageProvider}


def get_provider() -> VideoProvider:
    name = getattr(settings, "VIDEO_PROVIDER", "local")
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise ProviderUnavailable(
            f"مزوّد الفيديو '{name}' غير مُنفَّذ. المتاح: {', '.join(_PROVIDERS)}."
        )
