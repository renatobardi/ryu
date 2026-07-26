"""Testes de containment do storage local de attachments (path traversal)."""
from __future__ import annotations

import pytest


def test_sanitize_filename_strips_directories():
    from ryu.services.attachments import sanitize_filename

    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("a\\b\\c.txt") == "c.txt"
    assert sanitize_filename("") == "file"


@pytest.mark.parametrize("evil", ["..", "../fora.txt", "sub/../../fora.txt"])
def test_local_path_rejects_escape(evil):
    """_local_path nunca devolve caminho fora de uploads_dir/<att_id>."""
    from ryu.services.attachments import AttachmentError, _local_path

    with pytest.raises(AttachmentError):
        _local_path("att-123", evil)


def test_local_path_accepts_plain_filename():
    from pathlib import Path

    from ryu.config import settings
    from ryu.services.attachments import _local_path

    path = _local_path("att-123", "relatório final.pdf")
    assert path.name == "relatório final.pdf"
    assert path.parent.name == "att-123"
    # resolve() para casar com symlinks do tmpdir (macOS: /var → /private/var)
    assert path.is_relative_to(Path(settings.uploads_dir).resolve())
