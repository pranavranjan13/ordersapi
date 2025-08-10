from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json
import hmac
import hashlib

# Create the FastAPI app
app = FastAPI(
    title="My First Orders API",
    description="A simple API to manage products and orders",
    version="1.0.0"
)

# Simple in-memory storage (like a dictionary)
products_db = {}  # Will store: {id: product_data}
orders_db = {}    # Will store: {id: order_data}
next_product_id = 1
next_order_id = 1

# Data models (like forms that define what data looks like)
class Product(BaseModel):
    id: Optional[int] = None
    sku: str
    name: str
    price: float
    stock: int

class ProductCreate(BaseModel):
    sku: str
    name: str
    price: float
    stock: int

class Order(BaseModel):
    id: Optional[int] = None
    product_id: int
    quantity: int
    status: str = "PENDING"
    created_at: Optional[datetime] = None

class OrderCreate(BaseModel):
    product_id: int
    quantity: int

# Home page
@app.get("/")
def home():
    return {"message": "Welcome to my Orders API! Go to /docs to try it out"}

# PRODUCT ENDPOINTS - These handle products

@app.post("/products", status_code=201)
def create_product(product: ProductCreate):
    """Create a new product"""
    global next_product_id
    
    # Check if SKU already exists
    for existing_product in products_db.values():
        if existing_product["sku"] == product.sku:
            raise HTTPException(status_code=409, detail=f"Product with SKU '{product.sku}' already exists")
    
    # Check if price and stock are valid
    if product.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0")
    if product.stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    
    # Create the product
    new_product = {
        "id": next_product_id,
        "sku": product.sku,
        "name": product.name,
        "price": product.price,
        "stock": product.stock
    }
    
    products_db[next_product_id] = new_product
    next_product_id += 1
    
    return new_product

@app.get("/products")
def get_all_products():
    """Get all products"""
    return list(products_db.values())

@app.get("/products/{product_id}")
def get_product(product_id: int):
    """Get one specific product"""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")
    
    return products_db[product_id]

@app.put("/products/{product_id}")
def update_product(product_id: int, product_update: ProductCreate):
    """Update a product"""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")
    
    # Check if price and stock are valid
    if product_update.price <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0")
    if product_update.stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    
    # Update the product
    products_db[product_id].update({
        "sku": product_update.sku,
        "name": product_update.name,
        "price": product_update.price,
        "stock": product_update.stock
    })
    
    return products_db[product_id]

@app.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int):
    """Delete a product"""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")
    
    del products_db[product_id]
    return {"message": "Product deleted"}

# ORDER ENDPOINTS - These handle orders

@app.post("/orders", status_code=201)
def create_order(order: OrderCreate):
    """Create a new order"""
    global next_order_id
    
    # Check if product exists
    if order.product_id not in products_db:
        raise HTTPException(status_code=404, detail=f"Product with ID {order.product_id} not found")
    
    # Check if we have enough stock
    product = products_db[order.product_id]
    if product["stock"] < order.quantity:
        raise HTTPException(
            status_code=409, 
            detail=f"Not enough stock. Available: {product['stock']}, requested: {order.quantity}"
        )
    
    # Check if quantity is valid
    if order.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")
    
    # Reduce the stock
    products_db[order.product_id]["stock"] -= order.quantity
    
    # Create the order
    new_order = {
        "id": next_order_id,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "status": "PENDING",
        "created_at": datetime.now().isoformat()
    }
    
    orders_db[next_order_id] = new_order
    next_order_id += 1
    
    return new_order

@app.get("/orders")
def get_all_orders():
    """Get all orders"""
    return list(orders_db.values())

@app.get("/orders/{order_id}")
def get_order(order_id: int):
    """Get one specific order"""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail=f"Order with ID {order_id} not found")
    
    return orders_db[order_id]

@app.put("/orders/{order_id}")
def update_order_status(order_id: int, new_status: str):
    """Update order status (simple version)"""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail=f"Order with ID {order_id} not found")
    
    # Simple status validation
    allowed_statuses = ["PENDING", "PAID", "SHIPPED", "CANCELED"]
    if new_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {allowed_statuses}")
    
    orders_db[order_id]["status"] = new_status
    return orders_db[order_id]

@app.delete("/orders/{order_id}", status_code=204)
def delete_order(order_id: int):
    """Delete an order (only if PENDING)"""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail=f"Order with ID {order_id} not found")
    
    order = orders_db[order_id]
    if order["status"] != "PENDING":
        raise HTTPException(status_code=400, detail="Can only delete PENDING orders")
    
    del orders_db[order_id]
    return {"message": "Order deleted"}

# WEBHOOK ENDPOINT - This handles payment notifications

WEBHOOK_SECRET = "my-secret-key"  # In real life, this would be in environment variables

@app.post("/webhooks/payment")
async def payment_webhook(request_data: dict, signature: str = ""):
    """Handle payment notifications"""
    
    # Simple signature check (in real life this would be more complex)
    if signature != "valid-signature":
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Check if it's a payment success event
    if request_data.get("event") != "payment.succeeded":
        return {"message": "Event ignored"}
    
    order_id = request_data.get("order_id")
    if not order_id or order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Update order to PAID
    orders_db[order_id]["status"] = "PAID"
    
    return {"message": "Payment processed", "order_id": order_id}

# Add some sample data when the app starts
@app.on_event("startup")
def add_sample_data():
    """Add some sample products when the app starts"""
    global next_product_id
    
    sample_products = [
        {"sku": "BOOK-001", "name": "Python Programming Book", "price": 29.99, "stock": 10},
        {"sku": "LAPTOP-001", "name": "Gaming Laptop", "price": 999.99, "stock": 5},
        {"sku": "MOUSE-001", "name": "Wireless Mouse", "price": 25.00, "stock": 50}
    ]
    
    for product_data in sample_products:
        new_product = {
            "id": next_product_id,
            **product_data
        }
        products_db[next_product_id] = new_product
        next_product_id += 1