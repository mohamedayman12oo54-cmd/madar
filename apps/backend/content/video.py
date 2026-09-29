"""
Madar-owned Video interface (spec: "External video providers must NOT be
called directly from business logic. Madar owns an internal Video
interface/abstraction. The external provider is an implementation detail
behind that interface.").

Nothing in views/serializers/models ever builds a YouTube or Vimeo URL, or
even knows one exists — they call `describe_video()` and get back a
provider-neutral dict. Adding a new provider means adding one class here and
one line to `_PROVIDERS`; nothing else in the codebase changes.

Two properties worth stating explicitly:
- No network calls. This module only *constructs* URLs from a validated
  opaque reference — it never contacts a provider (no API keys exist in this
  project, and none are needed to embed a public video).
- Only a validated reference is ever stored, never a client-supplied URL.
  `validate_ref()` is strict per provider, so a stored value can't smuggle in
  a different host, a `javascript:` URL, or query-string tricks: the embed URL
  is always assembled from a fixed, known-good template by this module.
"""
import re
from dataclasses import dataclass
from typing import Optional


class VideoRefError(ValueError):
    pass


@dataclass(frozen=True)
class VideoInfo:
    provider: str
    embed_url: str
    thumbnail_url: Optional[str]

    def as_dict(self):
        return {"provider": self.provider, "embed_url": self.embed_url, "thumbnail_url": self.thumbnail_url}


class VideoProvider:
    name = ""
    label = ""

    def validate_ref(self, ref: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self, ref: str) -> VideoInfo:  # pragma: no cover - interface
        raise NotImplementedError


class YouTubeProvider(VideoProvider):
    name = "youtube"
    label = "YouTube"
    _ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

    def validate_ref(self, ref):
        ref = (ref or "").strip()
        if not self._ID.match(ref):
            raise VideoRefError("معرّف فيديو يوتيوب غير صالح (11 حرفًا).")
        return ref

    def describe(self, ref):
        return VideoInfo(
            provider=self.name,
            embed_url=f"https://www.youtube-nocookie.com/embed/{ref}",
            thumbnail_url=f"https://img.youtube.com/vi/{ref}/hqdefault.jpg",
        )


class VimeoProvider(VideoProvider):
    name = "vimeo"
    label = "Vimeo"
    _ID = re.compile(r"^[0-9]{6,12}$")

    def validate_ref(self, ref):
        ref = (ref or "").strip()
        if not self._ID.match(ref):
            raise VideoRefError("معرّف فيديو Vimeo غير صالح (أرقام فقط).")
        return ref

    def describe(self, ref):
        return VideoInfo(provider=self.name, embed_url=f"https://player.vimeo.com/video/{ref}", thumbnail_url=None)


_PROVIDERS = {p.name: p for p in (YouTubeProvider(), VimeoProvider())}
PROVIDER_CHOICES = [("none", "بدون فيديو")] + [(p.name, p.label) for p in _PROVIDERS.values()]


def validate_video(provider: str, ref: str) -> str:
    """Returns the normalized ref ('' for provider 'none'); raises VideoRefError."""
    if provider == "none":
        if ref:
            raise VideoRefError("لا يمكن تحديد معرّف فيديو بدون اختيار مزوّد.")
        return ""
    impl = _PROVIDERS.get(provider)
    if impl is None:
        raise VideoRefError("مزوّد فيديو غير مدعوم.")
    return impl.validate_ref(ref)


def describe_video(provider: str, ref: str) -> Optional[dict]:
    impl = _PROVIDERS.get(provider)
    if impl is None or not ref:
        return None
    return impl.describe(ref).as_dict()
