import shutil
from pathlib import Path

from shop_db.sku_sync_service import REPO_ROOT, sync_from_manifest
from tests.helpers import DBTestCase

MANIFEST_V1_0 = REPO_ROOT / "data_config" / "corpus_manifest_v1.0.json"
MANIFEST_V1_1 = REPO_ROOT / "data_config" / "corpus_manifest_v1.1.json"


def copy_corpus_to_tmp(tmp_dir: str | Path) -> Path:
    """Sao chép toàn bộ `data_config/` sang thư mục tạm để test đột biến an toàn."""
    dst_root = Path(tmp_dir)
    shutil.copytree(REPO_ROOT / "data_config", dst_root / "data_config")
    return dst_root


class CorpusTestCase(DBTestCase):
    def setUp(self):
        super().setUp()
        self.sync_result = sync_from_manifest(self.conn, MANIFEST_V1_0, repo_root=REPO_ROOT)

