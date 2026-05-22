"""Product domain service."""
from fastapi import HTTPException

from schemas import CommentResponse, ProductDetailResponse, ProductResponse
from services.domain.repositories.product_repository import ProductRepository


class ProductService:
    """品种领域服务。

    通过构造函数接收 Repository，支持在单元测试中注入 MockRepository
    以脱离真实数据库进行测试。
    """

    def __init__(self, db, repository: ProductRepository | None = None):
        self._db = db
        self._repo = repository or ProductRepository(db)

    def list_products(
        self,
        skip: int,
        limit: int,
        search: str | None,
        category: str | None,
        direction: str,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[ProductResponse], dict[str, str]]:
        return self._repo.list_products(
            skip=skip,
            limit=limit,
            search=search,
            category=category,
            direction=direction,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def get_product_detail(
        self,
        product_id: int,
        comment_skip: int,
        comment_limit: int,
    ) -> ProductDetailResponse:
        product = self._repo.get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="品种不存在")

        comments = self._repo.list_comments(product_id, comment_skip, comment_limit)

        return {
            "product": product,
            "comments": [
                CommentResponse(
                    id=c.id,
                    product_id=c.product_id,
                    user_id=c.user_id,
                    username=c.user.username if c.user else "未知用户",
                    content=c.content,
                    price_level_id=c.price_level_id,
                    created_at=c.created_at,
                )
                for c in comments
            ],
        }
