from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from app.core.http import HttpClient
from app.models import Product


class SiteScraper(ABC):
    def __init__(self, http: HttpClient):
        self.http = http

    @abstractmethod
    def iter_listing_urls(self, category: str, max_pages: int) -> Iterable[str]:
        """Generează URL-urile paginilor de listă (pag 1, 2, 3...)."""
        raise NotImplementedError

    @abstractmethod
    def parse_listing_page(self, html: str) -> List[str]:
        """Extrage link-urile către produsele individuale de pe o pagină de listă."""
        raise NotImplementedError

    @abstractmethod
    def parse_detail_page(self, html: str, url: str, category: str) -> Product:
        """Extrage datele complete ale unui produs de pe pagina sa dedicată."""
        raise NotImplementedError

    def filter_product(self, product: Product) -> bool:
        """Override în subclase pentru filtrare specifică site-ului. Default: păstrează tot."""
        return True