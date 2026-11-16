"""Response models for the product read side (Req 9.10, 9.11)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class StockStatusOut(BaseModel):
    status: Literal['in_stock', 'low_stock', 'out_of_stock']
    quantity: int
    label: str


class VariationOut(BaseModel):
    id: int
    label: str
    priceDeltaSen: int
    priceSen: int
    isActive: bool
    stockQuantity: int


class ImageOut(BaseModel):
    id: int
    url: Optional[str]
    isDemo: bool


class ArtisanPublicOut(BaseModel):
    id: int
    name: str


class CategoryRef(BaseModel):
    id: int
    slug: str
    name: str


class ProductOut(BaseModel):
    id: str
    name: str
    description: str
    category: CategoryRef
    priceSen: int
    demoPriceSen: int
    isDemo: bool
    isActive: bool
    madeToOrder: bool
    images: list[ImageOut]
    variations: list[VariationOut]
    stock: StockStatusOut
    artisan: Optional[ArtisanPublicOut]
