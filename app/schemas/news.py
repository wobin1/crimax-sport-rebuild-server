from pydantic import BaseModel
from typing import Optional


class NewsCreate(BaseModel):
    title: str
    content: str
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    is_published: bool = False


class NewsUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    is_published: Optional[bool] = None


class NewsOut(BaseModel):
    id: str
    title: str
    slug: str
    content: str
    excerpt: Optional[str]
    image_url: Optional[str]
    author_id: Optional[str]
    author_name: Optional[str]
    is_published: bool
    published_at: Optional[str]
    created_at: str
    updated_at: str
