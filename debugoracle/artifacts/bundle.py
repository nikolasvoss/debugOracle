from .models import EvidenceBundle
from .repository import ArtifactLoadError, load_artifact, save_artifact

SnapshotLoadError = ArtifactLoadError


def load_bundle(path: str, *, strict: bool = False) -> EvidenceBundle:
    return load_artifact(path, strict=strict)


def save_bundle(bundle: EvidenceBundle, path: str) -> None:
    save_artifact(bundle, path)
