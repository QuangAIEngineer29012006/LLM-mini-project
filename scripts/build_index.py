"""Build (and optionally activate) a RAG index from a corpus manifest.

python scripts/build_index.py --manifest data_config/corpus_manifest_v1.1.json --provider fake --activate
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag import gemini_bundle  # noqa: E402
from src.rag.embedder import FakeEmbedder  # noqa: E402
from src.rag.index import INDEX_ROOT, POINTER_PATHS, activate, build_bundle  # noqa: E402


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", default=str(ROOT / "data_config/corpus_manifest_v1.1.json"))
    parser.add_argument("--provider", choices=["fake", "gemini"], default="fake",
                        help="gemini: index của src/rag/gemini_index.py (tốn lượt gọi embedding); fake: bundle offline")
    parser.add_argument("--activate", action="store_true",
                        help="Trỏ con trỏ active của provider (gemini: artifacts/index_manifest.json, fake: index_manifest_fake.json) tới index")
    args = parser.parse_args(argv)
    if args.provider == "gemini":
        manifest = gemini_bundle.build(args.manifest, INDEX_ROOT)
        folder = INDEX_ROOT / f"{manifest['corpus_release']}-gemini"
    else:
        folder, manifest = build_bundle(args.manifest, FakeEmbedder())
    print(json.dumps({"index_dir": str(folder.relative_to(ROOT)), "index_id": manifest["index_id"],
                      "chunk_count": manifest["chunk_count"], "chunks_by_access": manifest["chunks_by_access"]},
                     ensure_ascii=False))
    if args.activate:
        if args.provider == "gemini":
            gemini_bundle.activate(folder, args.manifest, POINTER_PATHS["gemini"])
        else:
            activate(folder, POINTER_PATHS["fake"])
        print("Đã activate:", manifest["index_id"])


if __name__ == "__main__":
    main()
