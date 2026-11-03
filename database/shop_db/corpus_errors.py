"""Mã lỗi riêng cho phần Corpus Metadata & Đồng bộ SKU (TV1).

Kế thừa trực tiếp từ `DataServiceError` để đồng nhất quy ước `code` và `to_dict()`.
"""
from .errors import DataServiceError


class CorpusValidationError(DataServiceError):
    code = "corpus_validation_error"


class CorpusNotFound(DataServiceError):
    code = "corpus_doc_not_found"


class CorpusFileIntegrityError(DataServiceError):
    code = "corpus_file_integrity_error"


class SkuSyncMismatch(DataServiceError):
    code = "sku_sync_mismatch"


class CorpusAccessDenied(DataServiceError):
    code = "access_denied"


class CorpusVersionConflict(DataServiceError):
    code = "corpus_version_conflict"

