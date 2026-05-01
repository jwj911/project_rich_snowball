from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel, Field, field_validator
import html
import os
from dotenv import load_dotenv
import datetime
from datetime import timedelta, datetime as dt
from typing import List, Optional
import hashlib
import jwt
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
import logging

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

load_dotenv()

DATABASE_URL = "sqlite:///./futures_community.db"
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    comments = relationship("CommentDB", back_populates="user")

class ProductDB(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    current_price = Column(Float, nullable=False)
    change_percent = Column(Float, default=0)
    open_price = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    category = Column(String(20))
    margin = Column(Float, default=0)
    commission = Column(Float, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    comments = relationship("CommentDB", back_populates="product")

class CommentDB(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
    user = relationship("UserDB", back_populates="comments")
    product = relationship("ProductDB", back_populates="comments")

def init_db():
    Base.metadata.create_all(bind=engine)

app = FastAPI(title="期货交流社区 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.now(datetime.timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

logger = logging.getLogger(__name__)

def get_current_user(token: str, db: Session) -> Optional[UserDB]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return db.query(UserDB).filter(UserDB.id == int(user_id)).first()
    except PyJWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {e}")
        return None

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: dt

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ProductResponse(BaseModel):
    id: int
    name: str
    symbol: str
    current_price: float
    change_percent: float
    open_price: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[float]
    category: Optional[str]
    margin: Optional[float]
    commission: Optional[float]
    updated_at: dt

class CommentCreate(BaseModel):
    product_id: int
    content: str = Field(..., min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        return html.escape(v.strip())

class CommentResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    username: str
    content: str
    created_at: dt

class ProductDetailResponse(BaseModel):
    product: ProductResponse
    comments: List[CommentResponse]

@app.get("/")
def root():
    return {"message": "期货交流社区 API", "docs": "/docs"}

@app.post("/api/auth/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(UserDB).filter(
        (UserDB.username == user.username) | (UserDB.email == user.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名或邮箱已存在")

    db_user = UserDB(
        username=user.username,
        email=user.email,
        password_hash=hash_password(user.password)
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/api/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

from fastapi import Header

@app.get("/api/auth/me", response_model=UserResponse)
def get_me(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization.replace("Bearer ", "")
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")
    return user

@app.get("/api/products", response_model=List[ProductResponse])
def get_products(db: Session = Depends(get_db)):
    products = db.query(ProductDB).all()
    return products

@app.get("/api/products/{product_id}", response_model=ProductDetailResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="品种不存在")

    comments = db.query(CommentDB).filter(CommentDB.product_id == product_id)\
        .order_by(CommentDB.created_at.desc()).all()

    return {
        "product": product,
        "comments": [
            CommentResponse(
                id=c.id,
                product_id=c.product_id,
                user_id=c.user_id,
                username=c.user.username,
                content=c.content,
                created_at=c.created_at
            ) for c in comments
        ]
    }

@app.post("/api/comments", response_model=CommentResponse)
def create_comment(comment: CommentCreate, authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请登录后评论")
    token = authorization.replace("Bearer ", "")
    user = get_current_user(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 token")

    product = db.query(ProductDB).filter(ProductDB.id == comment.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="品种不存在")

    db_comment = CommentDB(
        product_id=comment.product_id,
        user_id=user.id,
        content=comment.content
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)

    return CommentResponse(
        id=db_comment.id,
        product_id=db_comment.product_id,
        user_id=db_comment.user_id,
        username=user.username,
        content=db_comment.content,
        created_at=db_comment.created_at
    )

@app.get("/api/comments/user/{username}", response_model=List[CommentResponse])
def get_user_comments(username: str, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    comments = db.query(CommentDB).filter(CommentDB.user_id == user.id)\
        .order_by(CommentDB.created_at.desc()).all()

    return [
        CommentResponse(
            id=c.id,
            product_id=c.product_id,
            user_id=c.user_id,
            username=user.username,
            content=c.content,
            created_at=c.created_at
        ) for c in comments
    ]

def init_mock_data():
    db = SessionLocal()

    if db.query(ProductDB).count() == 0:
        products = [
            {"name": "黄金", "symbol": "AU", "current_price": 453.2, "change_percent": 1.25, "open_price": 447.5, "high": 455.8, "low": 446.2, "volume": 152340, "category": "贵金属", "margin": 8, "commission": 15},
            {"name": "白银", "symbol": "AG", "current_price": 5420, "change_percent": -0.85, "open_price": 5465, "high": 5500, "low": 5380, "volume": 89420, "category": "贵金属", "margin": 9, "commission": 12},
            {"name": "铜", "symbol": "CU", "current_price": 68450, "change_percent": 2.15, "open_price": 67000, "high": 68800, "low": 66800, "volume": 125680, "category": "有色金属", "margin": 10, "commission": 18},
            {"name": "螺纹钢", "symbol": "RB", "current_price": 3680, "change_percent": -1.32, "open_price": 3730, "high": 3750, "low": 3650, "volume": 2156800, "category": "黑色系", "margin": 12, "commission": 8},
            {"name": "铁矿石", "symbol": "I", "current_price": 825, "change_percent": 0.78, "open_price": 818, "high": 835, "low": 812, "volume": 985420, "category": "黑色系", "margin": 11, "commission": 10},
            {"name": "原油", "symbol": "SC", "current_price": 528.5, "change_percent": -2.15, "open_price": 540.0, "high": 542.0, "low": 525.0, "volume": 425680, "category": "能源化工", "margin": 15, "commission": 20},
            {"name": "甲醇", "symbol": "MA", "current_price": 2580, "change_percent": 1.05, "open_price": 2555, "high": 2600, "low": 2540, "volume": 1856420, "category": "能源化工", "margin": 8, "commission": 6},
            {"name": "豆粕", "symbol": "M", "current_price": 3250, "change_percent": 0.45, "open_price": 3235, "high": 3280, "low": 3220, "volume": 652340, "category": "农产品", "margin": 10, "commission": 7},
            {"name": "玉米", "symbol": "C", "current_price": 2455, "change_percent": -0.62, "open_price": 2470, "high": 2485, "low": 2440, "volume": 425680, "category": "农产品", "margin": 8, "commission": 5},
            {"name": "棉花", "symbol": "CF", "current_price": 16850, "change_percent": 1.88, "open_price": 16540, "high": 16920, "low": 16480, "volume": 285640, "category": "农产品", "margin": 12, "commission": 14},
        ]
        for p in products:
            db.add(ProductDB(**p))

    if db.query(UserDB).count() == 0:
        users = [
            {"username": "trader001", "email": "trader001@example.com", "password_hash": hash_password("password123")},
            {"username": "investor_wang", "email": "wang@example.com", "password_hash": hash_password("password123")},
            {"username": "futures_master", "email": "master@example.com", "password_hash": hash_password("password123")},
        ]
        for u in users:
            db.add(UserDB(**u))
        db.commit()

        comments = [
            {"product_id": 1, "user_id": 1, "content": "黄金近期走势强劲，受避险情绪影响明显，建议关注450美元阻力位。"},
            {"product_id": 1, "user_id": 2, "content": "美联储加息预期降温，金价有望继续上攻。"},
            {"product_id": 3, "user_id": 3, "content": "铜价突破68000，需求端预期改善，短期内看好。"},
            {"product_id": 6, "user_id": 1, "content": "原油回落至520附近，OPEC+减产消息需持续关注。"},
            {"product_id": 4, "user_id": 2, "content": "螺纹钢库存下降，基本面转好信号出现。"},
        ]
        for c in comments:
            db.add(CommentDB(**c))

    db.commit()
    db.close()
    print("模拟数据初始化完成")

if __name__ == "__main__":
    init_db()
    init_mock_data()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
