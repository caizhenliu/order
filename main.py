# main.py
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status, Query, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
import uvicorn
from typing import List, Optional
import os
import shutil
from datetime import datetime
from starlette.middleware.sessions import SessionMiddleware

# 建立資料夾
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("static/images", exist_ok=True)

# 初始化 FastAPI
app = FastAPI(title="餐廳點餐管理系統")
app.add_middleware(SessionMiddleware, secret_key="some-random-secret-key")
security = HTTPBasic()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# 設定資料庫
SQLALCHEMY_DATABASE_URL = "sqlite:///./restaurant.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 定義資料模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)  # 密碼不再允許為空
    is_restaurant = Column(Boolean, default=False)
    
    orders = relationship("Order", back_populates="user")

class MenuItem(Base):
    __tablename__ = "menu_items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    description = Column(String, nullable=True)
    image_path = Column(String, nullable=True)  # 新增圖片路徑欄位
    
    order_items = relationship("OrderItem", back_populates="menu_item")

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    order_date = Column(String)
    total_price = Column(Float)
    
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"))
    quantity = Column(Integer)
    
    order = relationship("Order", back_populates="items")
    menu_item = relationship("MenuItem", back_populates="order_items")

class MenuSetting(Base):
    __tablename__ = "menu_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    full_menu_image = Column(String, nullable=True)  # 儲存總菜單圖片路徑

# 建立資料表
Base.metadata.create_all(bind=engine)

# 資料庫相依注入
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 初始化資料庫
def init_db():
    db = SessionLocal()
    
    # 檢查是否已有管理員帳號
    restaurant = db.query(User).filter(User.is_restaurant == True).first()
    if not restaurant:
        # 創建餐廳管理員帳號
        restaurant_user = User(username="restaurant", password="restaurant", is_restaurant=True)
        db.add(restaurant_user)
        
        # 創建一般用戶帳號
        customer = User(username="customer", password="customer", is_restaurant=False)
        db.add(customer)
        
        # 預設菜單項目
        menu_items = [
            MenuItem(name="漢堡", price=80, description="牛肉漢堡"),
            MenuItem(name="薯條", price=40, description="酥脆薯條"),
            MenuItem(name="可樂", price=30, description="冰涼可樂"),
            MenuItem(name="沙拉", price=60, description="新鮮蔬菜沙拉")
        ]
        db.add_all(menu_items)
        
        # 初始化菜單設定
        menu_setting = MenuSetting()
        db.add(menu_setting)
        
        db.commit()
    
    db.close()

# 獲取當前使用者
def get_current_user(request: Request, db: Session = Depends(get_db)):
    auth = request.session.get("auth")
    if not auth:
        return None
    
    user = db.query(User).filter(User.id == auth["user_id"]).first()
    return user

# 獲取菜單設定
def get_menu_settings(db: Session = Depends(get_db)):
    menu_setting = db.query(MenuSetting).first()
    if not menu_setting:
        menu_setting = MenuSetting()
        db.add(menu_setting)
        db.commit()
        db.refresh(menu_setting)
    return menu_setting

# 儲存上傳的圖片
def save_image(upload_file: UploadFile) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S%f")
    filename = f"{timestamp}.jpg"
    file_path = f"static/images/{filename}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    
    return f"/{file_path}"

# 路由

@app.on_event("startup")
async def startup_event():
    init_db()

# 主頁
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# 登入
@app.post("/login", response_class=HTMLResponse)
async def login(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...),
    is_student: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # 檢查登入類型（學生或管理員）
    is_restaurant = is_student != "true"
    
    # 檢查用戶是否存在
    user = db.query(User).filter(User.username == username).first()
    
    # 如果用戶不存在且是學生登入，創建新用戶
    if not user and not is_restaurant:
        user = User(username=username, password=password, is_restaurant=False)
        db.add(user)
        db.commit()
        db.refresh(user)
    # 如果用戶不存在且是管理員登入，或密碼不正確
    elif not user or user.password != password:
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error": "帳號或密碼不正確"
        })
    
    # 設置會話
    request.session["auth"] = {"user_id": user.id}
    
    # 根據用戶類型重定向
    if user.is_restaurant:
        return RedirectResponse(url="/restaurant/dashboard", status_code=303)
    else:
        return RedirectResponse(url="/customer/menu", status_code=303)

# 登出
@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    if hasattr(request, "session"):
        request.session.pop("auth", None)
    return RedirectResponse(url="/", status_code=303)

# 餐廳管理 - 訂單管理
@app.get("/restaurant/dashboard", response_class=HTMLResponse)
async def restaurant_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    orders = db.query(Order).order_by(Order.order_date.desc()).all()
    return templates.TemplateResponse("restaurant_dashboard.html", {
        "request": request, 
        "user": user,
        "orders": orders
    })

# 餐廳管理 - 使用者管理
@app.get("/restaurant/users", response_class=HTMLResponse)
async def restaurant_users(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    all_users = db.query(User).all()
    return templates.TemplateResponse("restaurant_users.html", {
        "request": request, 
        "user": user,
        "all_users": all_users
    })

# 餐廳管理 - 新增使用者
@app.post("/restaurant/users/add", response_class=HTMLResponse)
async def add_user(
    request: Request, 
    username: str = Form(...), 
    password: str = Form(...),
    is_restaurant: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    is_restaurant_bool = is_restaurant.lower() == "true"
    new_user = User(username=username, password=password, is_restaurant=is_restaurant_bool)
    db.add(new_user)
    db.commit()
    
    return RedirectResponse(url="/restaurant/users", status_code=303)

# 餐廳管理 - 更新使用者密碼
@app.post("/restaurant/users/update/{user_id}", response_class=HTMLResponse)
async def update_user(
    request: Request,
    user_id: int,
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user or not current_user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)

    if password != confirm_password:
        return RedirectResponse(url="/restaurant/users", status_code=303)

    target_user = db.query(User).filter(User.id == user_id).first()
    if target_user:
        target_user.password = password
        db.commit()

    return RedirectResponse(url="/restaurant/users", status_code=303)

# 餐廳管理 - 刪除使用者
@app.get("/restaurant/users/delete/{user_id}", response_class=HTMLResponse)
async def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user:
        db.delete(db_user)
        db.commit()
    
    return RedirectResponse(url="/restaurant/users", status_code=303)

# 餐廳管理 - 菜單管理
@app.get("/restaurant/menu", response_class=HTMLResponse)
async def restaurant_menu(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    menu_items = db.query(MenuItem).all()
    menu_settings = get_menu_settings(db)
    
    return templates.TemplateResponse("restaurant_menu.html", {
        "request": request, 
        "user": user,
        "menu_items": menu_items,
        "full_menu_image": menu_settings.full_menu_image
    })

# 餐廳管理 - 新增菜單項目
@app.post("/restaurant/menu/add", response_class=HTMLResponse)
async def add_menu_item(
    request: Request, 
    name: str = Form(...), 
    price: float = Form(...), 
    description: str = Form(...),
    item_image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    # 處理圖片上傳
    image_path = None
    if item_image and item_image.filename:
        image_path = save_image(item_image)
    
    new_item = MenuItem(name=name, price=price, description=description, image_path=image_path)
    db.add(new_item)
    db.commit()
    
    return RedirectResponse(url="/restaurant/menu", status_code=303)

# 餐廳管理 - 更新菜單項目
@app.post("/restaurant/menu/update/{item_id}", response_class=HTMLResponse)
async def update_menu_item(
    request: Request, 
    item_id: int,
    name: str = Form(...), 
    price: float = Form(...), 
    description: str = Form(...), 
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item:
        item.name = name
        item.price = price
        item.description = description
        db.commit()
    
    return RedirectResponse(url="/restaurant/menu", status_code=303)

# 餐廳管理 - 上傳菜單項目圖片
@app.post("/restaurant/menu/upload-image/{item_id}", response_class=HTMLResponse)
async def upload_menu_item_image(
    request: Request,
    item_id: int,
    item_image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item and item_image.filename:
        # 保存新圖片
        image_path = save_image(item_image)
        
        # 更新菜單項目
        item.image_path = image_path
        db.commit()
    
    return RedirectResponse(url="/restaurant/menu", status_code=303)

# 餐廳管理 - 上傳總菜單圖片
@app.post("/restaurant/menu/upload-full-menu", response_class=HTMLResponse)
async def upload_full_menu_image(
    request: Request,
    full_menu_image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    menu_settings = get_menu_settings(db)
    
    if full_menu_image.filename:
        # 保存新圖片
        image_path = save_image(full_menu_image)
        
        # 更新菜單設定
        menu_settings.full_menu_image = image_path
        db.commit()
    
    return RedirectResponse(url="/restaurant/menu", status_code=303)

# 餐廳管理 - 刪除菜單項目
@app.get("/restaurant/menu/delete/{item_id}", response_class=HTMLResponse)
async def delete_menu_item(request: Request, item_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_restaurant:
        return RedirectResponse(url="/", status_code=303)
    
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    
    return RedirectResponse(url="/restaurant/menu", status_code=303)

# 使用者 - 菜單瀏覽
@app.get("/customer/menu", response_class=HTMLResponse)
async def customer_menu(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    menu_items = db.query(MenuItem).all()
    menu_settings = get_menu_settings(db)
    
    return templates.TemplateResponse("customer_menu.html", {
        "request": request, 
        "user": user,
        "menu_items": menu_items,
        "full_menu_image": menu_settings.full_menu_image
    })

# 使用者 - 下單
@app.post("/customer/order", response_class=HTMLResponse)
async def place_order(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    form_data = await request.form()
    order_items = []
    total_price = 0
    
    for key, value in form_data.items():
        if key.startswith("quantity_") and int(value) > 0:
            item_id = int(key.split("_")[1])
            quantity = int(value)
            
            menu_item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
            if menu_item:
                order_items.append({"item": menu_item, "quantity": quantity})
                total_price += menu_item.price * quantity
    
    if order_items:
        # 創建訂單
        order = Order(
            user_id=user.id,
            order_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_price=total_price
        )
        db.add(order)
        db.flush()
        
        # 添加訂單項目
        for item in order_items:
            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=item["item"].id,
                quantity=item["quantity"]
            )
            db.add(order_item)
        
        db.commit()
        
        return RedirectResponse(url="/customer/orders", status_code=303)
    
    return RedirectResponse(url="/customer/menu", status_code=303)

# 使用者 - 訂單歷史
@app.get("/customer/orders", response_class=HTMLResponse)
async def customer_orders(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    orders = db.query(Order).filter(Order.user_id == user.id).order_by(Order.order_date.desc()).all()
    
    # 獲取訂單項目
    for order in orders:
        order.items_with_details = []
        for item in order.items:
            menu_item = db.query(MenuItem).filter(MenuItem.id == item.menu_item_id).first()
            order.items_with_details.append({
                "name": menu_item.name,
                "price": menu_item.price,
                "quantity": item.quantity,
                "subtotal": menu_item.price * item.quantity
            })
    
    return templates.TemplateResponse("customer_orders.html", {
        "request": request, 
        "user": user,
        "orders": orders
    })

# 主程式入口
if __name__ == "__main__":
    print("餐廳點餐管理系統啟動中...")
    print("預設帳號：")
    print("餐廳管理員 - username: restaurant, password: restaurant")
    print("預設之顧客 - username: customer, password: customer")
    print("管理員、顧客 - 輸入帳號及密碼登入")
    print("請訪問 http://localhost:8000 開始使用！")
    uvicorn.run(app, host="0.0.0.0", port=8000)