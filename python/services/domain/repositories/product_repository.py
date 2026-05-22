"""Product 数据访问层。"""

from sqlalchemy import asc, case, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from models import CommentDB, ProductDB


class ProductRepository:
    """Product 相关的数据库操作，供 ProductService 使用。"""

    def __init__(self, db: Session):
        self._db = db

    def get(self, product_id: int) -> ProductDB | None:
        return self._db.query(ProductDB).filter(ProductDB.id == product_id).first()

    def list_products(
        self,
        skip: int,
        limit: int,
        search: str | None,
        category: str | None,
        direction: str,
        sort_by: str,
        sort_order: str,
    ) -> tuple[list[ProductDB], dict[str, str]]:
        query = self._db.query(ProductDB)

        keyword = search.strip() if search else ""
        if keyword:
            pattern = f"%{keyword}%"
            query = query.filter(
                or_(
                    ProductDB.name.ilike(pattern),
                    ProductDB.symbol.ilike(pattern),
                    ProductDB.category.ilike(pattern),
                )
            )

        if category and category != "all":
            query = query.filter(ProductDB.category == category)

        if direction == "up":
            query = query.filter(func.coalesce(ProductDB.change_percent, 0) >= 0)
        elif direction == "down":
            query = query.filter(func.coalesce(ProductDB.change_percent, 0) < 0)

        stats_query = query.with_entities(
            func.count(ProductDB.id),
            func.sum(func.coalesce(ProductDB.volume, 0)),
            func.sum(
                case((func.coalesce(ProductDB.change_percent, 0) >= 0, 1), else_=0)
            ),
            func.sum(
                case((func.coalesce(ProductDB.change_percent, 0) < 0, 1), else_=0)
            ),
        )
        total_count, total_volume, up_count, down_count = stats_query.one()

        categories = [
            row[0]
            for row in self._db.query(ProductDB.category)
            .filter(ProductDB.category.isnot(None), ProductDB.category != "")
            .distinct()
            .order_by(ProductDB.category.asc())
            .all()
        ]

        sort_column = {
            "change_percent": ProductDB.change_percent,
            "volume": ProductDB.volume,
            "current_price": ProductDB.current_price,
        }[sort_by]
        sort_expr = (
            desc(func.coalesce(sort_column, 0))
            if sort_order == "desc"
            else asc(func.coalesce(sort_column, 0))
        )

        products = (
            query.order_by(sort_expr, ProductDB.id.asc()).offset(skip).limit(limit).all()
        )

        from urllib.parse import quote

        headers = {
            "X-Total-Count": str(total_count or 0),
            "X-Total-Volume": str(total_volume or 0),
            "X-Up-Count": str(up_count or 0),
            "X-Down-Count": str(down_count or 0),
            "X-Categories": ",".join(quote(c) for c in categories),
        }
        return products, headers

    def list_comments(
        self,
        product_id: int,
        skip: int,
        limit: int,
    ) -> list[CommentDB]:
        return (
            self._db.query(CommentDB)
            .options(joinedload(CommentDB.user))
            .filter(CommentDB.product_id == product_id)
            .order_by(CommentDB.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
