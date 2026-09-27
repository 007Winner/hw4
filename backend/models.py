from pydantic import BaseModel, Field


class CustomerContext(BaseModel):
    user_id: int | None = None
    name: str | None = None
    email: str | None = None


class PageContext(BaseModel):
    product_id: str | None = None


class AgentDeps(BaseModel):
    customer: CustomerContext = Field(default_factory=CustomerContext)
    page_context: PageContext | None = None


class SizeStock(BaseModel):
    size: str
    quantity: int = Field(ge=0)
    in_stock: bool


class ProductCard(BaseModel):
    product_id: str
    name: str
    price: float
    garment_type: str
    description: str = ""
    colors: list[str] = Field(default_factory=list)
    image_url: str = ""
    inventory: list[SizeStock] = Field(default_factory=list)
    total_stock: int = 0


class ProductStockLookup(BaseModel):
    product_id: str
    name: str
    description: str
    price: float
    inventory: list[SizeStock] = Field(default_factory=list)


class ChatReply(BaseModel):
    reply: str
    products: list[ProductCard] = Field(default_factory=list)
