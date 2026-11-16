"""Request models for artisan management (Req 23.1, 23.2). Each invalid field is reported separately (HTTP 422)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, StrictInt, StringConstraints
from typing_extensions import Annotated

Availability = Literal['available', 'busy', 'unavailable']

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Specialisation = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Story = Annotated[str, StringConstraints(max_length=2000)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254,
                                         pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')]
Address = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class ArtisanIn(BaseModel):
    """Create and edit body. On edit, omitted optional fields keep their value and `null` clears a contact field."""
    model_config = ConfigDict(extra='forbid')
    name: Name
    specialisation: Specialisation
    availability: Availability
    story: Optional[Story] = None
    phone: Optional[Phone] = None
    email: Optional[Email] = None
    address: Optional[Address] = None


class ProductArtisanLink(BaseModel):
    """`artisanId: null` unlinks the product."""
    model_config = ConfigDict(extra='forbid')
    artisanId: Optional[StrictInt]
