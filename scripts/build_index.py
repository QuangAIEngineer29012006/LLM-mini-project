"""Build (and optionally activate) a RAG index bundle from a corpus manifest.

python scripts/build_index.py --manifest data_config/corpus_manifest_v1.1.json --provider fake --activate
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from src.rag.embedder import FakeEmbedder, make_embedder  # noqa: E402
from src.rag.index import POINTER_PATHS, activate, build_bundle  # noqa: E402


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", default=str(ROOT / "data_config/corpus_manifest_v1.1.json"))
    parser.add_argument("--provider", choices=["fake", "gemini"], default="fake")
    parser.add_argument("--activate", action="store_true",
                        help="Trỏ con trỏ active của provider (gemini: artifacts/index_manifest.json, fake: index_manifest_fake.json) tới bundle")
    args = parser.parse_args(argv)
    embedder = FakeEmbedder() if args.provider == "fake" else make_embedder(Settings.from_env(), "gemini")
    bundle, manifest = build_bundle(args.manifest, embedder)
    print(json.dumps({"bundle": str(bundle.relative_to(ROOT)), "index_id": manifest["index_id"],
                      "chunk_count": manifest["chunk_count"], "chunks_by_access": manifest["chunks_by_access"]},
                     ensure_ascii=False))
    if args.activate:
        activate(bundle, POINTER_PATHS[args.provider])
        print("Đã activate:", manifest["index_id"])


if __name__ == "__main__":
    main()
