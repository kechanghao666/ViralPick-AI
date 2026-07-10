from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.services import local_knowledge_service


def main() -> None:
    status = local_knowledge_service.rebuild_knowledge_base()
    print(f"Knowledge base ready: {status['document_count']} documents")
    print(f"Updated at: {status['updated_at']}")


if __name__ == "__main__":
    main()
